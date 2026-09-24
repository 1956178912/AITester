"""
venv 沙箱执行模式（P1 依赖隔离）与 Docker 隔离执行模式（4.3）。

拆分自 executor.py（结构优化轮次）：executor.py 的类主体保留执行编排
（execute / _execute_local / _run_pytest_with_retry），本模块承载两种隔离执行
模式的完整实现（_execute_sandboxed / _prepare_dependencies / _execute_docker）。
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile
from typing import Any

from src.agents.executor_imports import auto_fix_imports, extract_module_name_from_file
from src.agents.executor_output import build_error_info, parse_coverage, parse_failed_cases
from src.agents.executor_runtime import cleanup_sandbox

logger = logging.getLogger(__name__)


def execute_sandboxed(
    self,
    test_code: str,
    target_file: str,
    target_function: str | None = None,
) -> dict[str, Any]:
    """在隔离沙箱中执行测试：临时目录 + 缓存 venv + 依赖自动安装。

    流程：
    1. 创建临时沙箱目录，拷入被测模块文件（按 target_file 的模块名）；
    2. 写入自动修复导入后的测试文件；
    3. 检测被测代码 + 测试代码缺失的第三方依赖：
       - auto_install_deps=True → 在 venv 内 pip install（仅影响 venv）；
       - auto_install_deps=False → 记录缺失清单到 error_info，照常执行
         （失败将由错误分类器归为 import_error，便于区分代码 bug 与环境问题）；
    4. 用 venv 解释器（或系统解释器）在沙箱目录运行 pytest，
       PYTHONPATH 仅指向沙箱目录，实现任务间依赖隔离；
    5. 清理沙箱目录（venv 保留缓存，相同依赖组合的任务复用）。

    Returns:
        与 execute() 相同结构的结果字典。
    """
    sandbox_dir = tempfile.mkdtemp(prefix="aitester_sandbox_")
    # 被测模块名：取 target_file 基名（与 extract_module_name_from_file 语义一致）
    module_name = extract_module_name_from_file(target_file)
    module_file = os.path.join(sandbox_dir, f"{module_name}.py")
    try:
        with open(target_file, encoding="utf-8") as f:
            target_source = f.read()
        with open(module_file, "w", encoding="utf-8") as f:
            f.write(target_source)
    except OSError as e:
        cleanup_sandbox(sandbox_dir)
        return {
            "passed": False,
            "output": f"读取被测文件失败: {e}",
            "coverage": 0.0,
            "failed_cases": [],
            "error_info": {"type": "file_not_found", "message": str(e), "file_path": target_file},
        }

    # 测试文件写入沙箱（导入修复以沙箱为搜索根，模块名与文件名天然对齐）
    fixed_test_code = auto_fix_imports(test_code, module_file, sandbox_dir)
    test_file = os.path.join(sandbox_dir, "test_generated.py")
    with open(test_file, "w", encoding="utf-8") as f:
        f.write(fixed_test_code)

    # ── 依赖检测与安装 ──────────────────────────────────────────────────
    env, python_path, dep_install_note, sandbox_error_info, missing_modules = _prepare_dependencies(
        self, target_source, fixed_test_code, module_file, sandbox_dir
    )

    # 依赖安装失败/venv 创建失败：测试结果将不可信（缺失依赖仍在），
    # 直接提前返回，让 Debugger 拿到准确的 dependency_install_failed 诊断
    if sandbox_error_info:
        cleanup_sandbox(sandbox_dir)
        return {
            "passed": False,
            "output": dep_install_note or "依赖处理失败",
            "coverage": 0.0,
            "failed_cases": [],
            "error_info": sandbox_error_info,
        }

    try:
        cmd = [
            python_path,
            "-m",
            "pytest",
            test_file,
            "-v",
            "--tb=short",
            f"--cov={sandbox_dir}",
            "--cov-report=term",
        ]
        if target_function:
            cmd.extend(["-k", target_function])

        output, last_result = self._run_pytest_with_retry(cmd, env, sandbox_dir)
        if isinstance(last_result, tuple) and last_result[0] == "EARLY_RETURN":
            result = {
                "passed": False,
                "output": output,
                "coverage": 0.0,
                "failed_cases": [],
                "error_info": last_result[1],
            }
        else:
            coverage = parse_coverage(output)
            failed_cases = parse_failed_cases(output)
            passed = last_result is not None and last_result.returncode == 0
            result = {
                "passed": passed,
                "output": output,
                "coverage": coverage,
                "failed_cases": failed_cases,
            }
            if last_result is not None and last_result.returncode != 0:
                result["error_info"] = build_error_info(last_result, output)
                result["error_info"]["missing_dependencies"] = sorted(missing_modules)

        # 依赖检测结论写入 dep_note，供 Debugger 与实验分析使用。
        # 注：原"安装失败优先覆盖 error_info"分支不可达（安装失败/venv 创建失败
        # 在上方依赖检测段已提前 return，此处 sandbox_error_info 必为 None），已删除
        if dep_install_note:
            result["dep_note"] = dep_install_note
        return result
    finally:
        # 清理临时沙箱（venv 缓存在 ~/.cache/aitester/venvs/，跨任务保留）
        cleanup_sandbox(sandbox_dir)


def _prepare_dependencies(
    self,
    target_source: str,
    fixed_test_code: str,
    module_file: str,
    sandbox_dir: str,
) -> tuple[dict[str, str], str, str, dict[str, Any] | None, set[str]]:
    """检测并安装缺失依赖，准备沙箱执行环境。

    Returns:
        (env, python_path, dep_install_note, sandbox_error_info, missing_modules) 五元组：
        env 为注入 PYTHONPATH 的环境变量副本，python_path 为执行解释器路径，
        dep_install_note 为依赖安装结论文本，sandbox_error_info 为安装失败诊断
        （成功时 None），missing_modules 为缺失模块集合。
    """
    # 函数内局部导入：保留测试 patch src.tools.dependency.* 的生效性
    # （模块顶层导入会在绑定后使 patch 失效，原实现即用局部导入）
    from src.tools.dependency import (
        create_venv,
        extract_imported_modules,
        find_missing_modules,
        install_packages,
        suggest_package_names,
        venv_cache_dir,
    )

    required_modules = extract_imported_modules(target_source + "\n" + fixed_test_code)
    missing_modules = find_missing_modules(required_modules, extra_search_files=[module_file])
    missing_packages = suggest_package_names(missing_modules)

    env = os.environ.copy()
    # 模块搜索路径以沙箱目录为首（追加原 PYTHONPATH 保留 pytest 等测试工具）；
    # 空段过滤防尾随冒号（语义同上，空元素等价 CWD 可遮蔽同名文件）
    env["PYTHONPATH"] = os.pathsep.join(
        [sandbox_dir] + [p for p in (env.get("PYTHONPATH") or "").split(os.pathsep) if p]
    )
    python_path = sys.executable
    dep_install_note = ""
    sandbox_error_info: dict[str, Any] | None = None

    if missing_packages and self.use_venv:
        # 创建/复用缓存 venv（相同依赖组合 + 当前 Python 版本共享，省 1-3s 重建开销）
        # 4.4 多版本缓存：venv_cache_dir 默认将 sys.version_info 前两位纳入 key，
        # 不同 Python 版本的 venv 隔离存放，避免交叉复用导致依赖不兼容
        venv_dir = venv_cache_dir(missing_packages)
        try:
            python_path = create_venv(venv_dir, timeout=self.dep_install_timeout)
            if self.auto_install_deps:
                ok, summary = install_packages(python_path, missing_packages, timeout=self.dep_install_timeout)
                dep_install_note = f"依赖安装{'成功' if ok else '失败'}: {summary}"
                if not ok:
                    sandbox_error_info = {
                        "type": "dependency_install_failed",
                        "message": f"缺失依赖安装失败: {missing_packages}",
                        "detail": summary,
                    }
        except RuntimeError as e:
            sandbox_error_info = {"type": "dependency_install_failed", "message": str(e), "detail": str(e)}

    return env, python_path, dep_install_note, sandbox_error_info, missing_modules


def execute_docker(
    self,
    test_code: str,
    target_file: str,
    target_function: str | None = None,
) -> dict[str, Any]:
    """4.3 Docker 隔离执行：经 docker CLI 在容器内跑 pytest。

    设计口径（保守，避免实验口径混淆）：
    - 容器镜像（默认 aitester:latest，对应仓库根 Dockerfile）内置全部
      依赖（构建期 pip install，Docker 层缓存复用），任务代码与测试
      代码经挂载卷传入，容器间完全隔离；
    - docker CLI 不存在时提前返回 docker_unavailable 诊断，不静默
      降级到本地执行（"以为隔离了其实没有" 会污染对比实验口径）；
    - 相比 venv 模式，镜像构建一次后每任务零安装开销（依赖预安装
      缓存天然生效），适合需要特定系统依赖的 SWE-bench 任务。

    Returns:
        与 execute() 相同结构的结果字典（额外携带 docker_image 字段，
        供实验分析记录执行模式差异）。
    """
    import shutil

    if shutil.which("docker") is None:
        return {
            "passed": False,
            "output": "docker CLI 未安装或不在 PATH 中，无法启用 Docker 隔离执行",
            "coverage": 0.0,
            "failed_cases": [],
            "error_info": {
                "type": "docker_unavailable",
                "message": "请安装 docker 并构建镜像：docker build -t aitester:latest .",
            },
            "docker_image": self.docker_image,
        }

    # 项目根 = 上溯三层（src/agents/executor_modes.py → 仓库根），与
    # executor.py 的本地执行路径、workflow.py 的 patch 白名单口径一致
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    module_name = extract_module_name_from_file(target_file)
    fixed_test_code = auto_fix_imports(test_code, target_file, project_root)

    # 临时目录承载被测模块与测试文件，经挂载卷传入容器（容器根文件系统
    # 只读语义由镜像 WORKDIR 保证，任务间无残留）
    sandbox_dir = tempfile.mkdtemp(prefix="aitester_docker_")
    try:
        target_source = ""
        with open(target_file, encoding="utf-8") as tf_src:
            target_source = tf_src.read()
        with open(os.path.join(sandbox_dir, f"{module_name}.py"), "w", encoding="utf-8") as mf:
            mf.write(target_source)
        with open(os.path.join(sandbox_dir, "test_generated.py"), "w", encoding="utf-8") as tf:
            tf.write(fixed_test_code)

        cmd = [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{sandbox_dir}:/workspace",
            "-w",
            "/workspace",
            self.docker_image,
            "python",
            "-m",
            "pytest",
            "test_generated.py",
            "-v",
            "--tb=short",
            "--cov=/workspace",
            "--cov-report=term",
        ]
        if target_function:
            cmd.extend(["-k", target_function])

        try:
            # 容器启动开销（镜像拉取/文件系统初始化）远大于本地子进程，
            # 超时下限放宽到 120s 避免误判
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=max(self.timeout, 120),
                env=os.environ,
            )
        except subprocess.TimeoutExpired as e:
            return {
                "passed": False,
                "output": f"Docker 执行超时（>{max(self.timeout, 120)}s）",
                "coverage": 0.0,
                "failed_cases": [],
                "error_info": {"type": "docker_timeout", "message": str(e)},
                "docker_image": self.docker_image,
            }

        output = result.stdout + result.stderr
        passed = result.returncode == 0
        result_dict = {
            "passed": passed,
            "output": output,
            "coverage": parse_coverage(output),
            "failed_cases": parse_failed_cases(output),
            "docker_image": self.docker_image,
        }
        if result.returncode != 0:
            # build_error_info 依赖 CompletedProcess.returncode，
            # 用鸭子类型对象适配（字段一致即可）
            fake_result = type(
                "_DockerResult",
                (),
                {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr},
            )()
            result_dict["error_info"] = build_error_info(fake_result, output)
        return result_dict
    except OSError as e:
        return {
            "passed": False,
            "output": f"读取被测文件失败: {e}",
            "coverage": 0.0,
            "failed_cases": [],
            "error_info": {"type": "file_not_found", "message": str(e), "file_path": target_file},
        }
    finally:
        cleanup_sandbox(sandbox_dir)
