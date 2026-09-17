"""
测试执行器模块：在隔离环境中运行 pytest 测试并捕获结果。

支持超时配置、重试机制和覆盖率报告解析。
默认在本地环境执行，Docker 模式需要额外配置。

结构说明（优化轮次拆分）：本模块保留 ExecutorAgent 类主体与本地执行编排
（execute / _execute_local），其余能力拆分至四个子模块以保持单一职责：
- executor_imports: 导入路径自动修复（模块名提取 / sys.path 注入 / 相似名替换）
- executor_output: 执行结果解析（覆盖率 / 失败用例 / 错误信息）
- executor_modes: venv 沙箱与 Docker 隔离执行模式
- executor_runtime: 子进程运行、重试与临时资源清理
拆分后方法以模块函数实现、类属性挂载绑定，外部以
`ExecutorAgent.<method>` 形式调用的签名与语义保持不变（测试 patch 路径
`src.agents.executor.ExecutorAgent.<method>` 不受影响）。
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
from typing import Any

from src.agents.executor_imports import (
    apply_import_replacements,
    auto_fix_imports,
    build_sys_path_code,
    cached_search_module_path,
    extract_imports,
    extract_module_name_from_file,
    is_similar_module_name,
    resolve_module_paths,
)
from src.agents.executor_modes import execute_docker, execute_sandboxed
from src.agents.executor_output import build_error_info, parse_coverage, parse_failed_cases
from src.agents.executor_runtime import cleanup_sandbox, cleanup_temp_file, run_pytest_with_retry

logger = logging.getLogger(__name__)


class ExecutorAgent:
    """
    测试执行器：在本地或隔离沙箱中运行 pytest 测试。

    三种执行模式（互斥，优先级 Docker > venv 沙箱 > 本地）：
    - use_docker=True（4.3）：经 docker CLI 在容器内跑 pytest（镜像内置依赖，
      容器间完全隔离）。需本机安装 docker 且镜像已构建；docker 不可用时
      提前返回 dependency_install_failed 诊断，不静默降级到本地（避免
      "以为隔离了其实没有" 的实验口径混淆）。
    - use_venv=True：在临时沙箱目录 + 缓存 venv 中执行，PYTHONPATH 仅指向
      沙箱目录，被测代码的 import 不污染系统环境，任务间依赖互不冲突。
    - 默认：本地系统 Python 执行（历史行为）。

    属性:
        timeout: 单次测试最大运行时间（秒），可通过 EXECUTION_TIMEOUT 环境变量配置。
        use_docker: 是否使用 Docker 隔离执行（4.3，默认 False 保持历史口径）。
        use_venv: 是否使用 venv 沙箱隔离执行（默认 False，保持原有行为）。
        auto_install_deps: 是否自动安装缺失依赖（需 use_venv 生效）。
        dep_install_timeout: 依赖安装子进程超时秒数。
    """

    def __init__(
        self,
        timeout: int = 30,
        use_docker: bool = False,
        use_venv: bool = False,
        auto_install_deps: bool = False,
        dep_install_timeout: int = 120,
        docker_image: str = "aitester:latest",
    ) -> None:
        # timeout 从参数传入，默认 30 秒
        self.timeout = timeout
        self.use_docker = use_docker
        self.use_venv = use_venv
        self.auto_install_deps = auto_install_deps
        self.dep_install_timeout = dep_install_timeout
        self.docker_image = docker_image

    def execute(
        self,
        test_code: str,
        target_file: str,
        target_function: str | None = None,
    ) -> dict[str, Any]:
        """
        执行 pytest 测试并返回结果。
        失败时自动重试一次（防止偶发性环境干扰导致误判），最多尝试 2 次。

        Args:
            test_code: pytest 测试代码字符串。
            target_file: 被测代码文件路径。
            target_function: 指定要运行的测试函数名（可选）。

        Returns:
            包含以下键的字典：
            - passed (bool): 是否全部测试通过。
            - output (str): 测试输出文本。
            - coverage (float): 代码覆盖率（如有）。
            - failed_cases (List[dict]): 失败的用例列表。
            - error_info (dict): 错误详情（可选）。
        """
        # 4.3 Docker 隔离执行（优先级最高：镜像内置依赖 + 容器完全隔离）
        if self.use_docker:
            return self._execute_docker(test_code, target_file, target_function)

        # 隔离沙箱路径：venv + 临时目录执行，避免依赖冲突与环境污染（P1 优化）
        if self.use_venv:
            return self._execute_sandboxed(test_code, target_file, target_function)

        return self._execute_local(test_code, target_file, target_function)

    def _execute_local(
        self,
        test_code: str,
        target_file: str,
        target_function: str | None = None,
    ) -> dict[str, Any]:
        """本地系统 Python 执行路径（历史行为，保持原 execute 内联逻辑）。"""
        # 项目根 = 本文件上溯三层（src/agents/executor.py → 仓库根），与 workflow.py
        # 的 patch 白名单、cli/app.py 的根目录口径一致。此前只上溯两层得到 src/，
        # 导致 rglob 模块搜索与 pytest cwd 都少了一层：src 外的 examples/ 等目录
        # 模块搜不到、import 修复链路对非同名 helper 断裂
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        target_dir = os.path.dirname(os.path.abspath(target_file))

        fixed_test_code = self._auto_fix_imports(test_code, target_file, project_root)
        if fixed_test_code != test_code:
            logger.info("已自动修复模块导入路径")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(fixed_test_code)
            test_file = f.name

        try:
            env = os.environ.copy()
            # 4.1 脱敏审计：子进程执行的是 LLM 生成的任意测试代码，
            # LLM 的 API 凭证不得随环境继承进被测沙箱（泄露面 +
            # 生成代码意外外传向量）。剔除 API Key 类变量后注入。
            for secret_key in (
                "OPENAI_API_KEY",
                "OPENAI_BASE_URL",
                "ANTHROPIC_API_KEY",
                "API_KEY",
                "LLM_API_KEY",
                "LLM_CONFIG_API_KEY",
            ):
                env.pop(secret_key, None)
            # 尾随冒号防护：原 PYTHONPATH 未设置时直接拼接会产生 "<dir>:" 尾随空段
            # （sys.path 中空元素等价 CWD，同名文件可遮蔽第三方库）；空段过滤后 join
            env["PYTHONPATH"] = os.pathsep.join(
                [target_dir] + [p for p in (env.get("PYTHONPATH") or "").split(os.pathsep) if p]
            )

            python_path = sys.executable
            cmd = [
                python_path,
                "-m",
                "pytest",
                test_file,
                "-v",
                "--tb=short",
                f"--cov={target_dir}",
                "--cov-report=term",
            ]
            if target_function:
                cmd.extend(["-k", target_function])

            output, last_result = self._run_pytest_with_retry(cmd, env, project_root)
            # 检查是否需要立即返回（超时/环境问题）
            if isinstance(last_result, tuple) and last_result[0] == "EARLY_RETURN":
                return {
                    "passed": False,
                    "output": output,
                    "coverage": 0.0,
                    "failed_cases": [],
                    "error_info": last_result[1],
                }

            coverage = self._parse_coverage(output)
            failed_cases = self._parse_failed_cases(output)
            passed = last_result is not None and last_result.returncode == 0

            result_dict = {
                "passed": passed,
                "output": output,
                "coverage": coverage,
                "failed_cases": failed_cases,
            }

            if last_result and last_result.returncode != 0:
                result_dict["error_info"] = self._build_error_info(last_result, output)

            return result_dict
        finally:
            self._cleanup_temp_file(test_file)


# ─── 方法绑定：把子模块的纯函数以实例方法/静态方法形式挂回 ExecutorAgent ─────────
# 外部调用方（tests、graph/nodes、cli）与现有 patch 路径
# （src.agents.executor.ExecutorAgent.<method>）均以类属性方式访问，
# 绑定后行为与拆分前完全一致。
ExecutorAgent._run_pytest_with_retry = run_pytest_with_retry
ExecutorAgent._cleanup_temp_file = staticmethod(cleanup_temp_file)
ExecutorAgent._cleanup_sandbox = staticmethod(cleanup_sandbox)
ExecutorAgent._execute_sandboxed = execute_sandboxed
ExecutorAgent._execute_docker = execute_docker
ExecutorAgent._build_error_info = staticmethod(build_error_info)
ExecutorAgent._parse_coverage = staticmethod(parse_coverage)
ExecutorAgent._parse_failed_cases = staticmethod(parse_failed_cases)
ExecutorAgent._extract_module_name_from_file = staticmethod(extract_module_name_from_file)
ExecutorAgent._cached_search_module_path = staticmethod(cached_search_module_path)
ExecutorAgent._auto_fix_imports = staticmethod(auto_fix_imports)
ExecutorAgent._extract_imports = staticmethod(extract_imports)
ExecutorAgent._resolve_module_paths = staticmethod(resolve_module_paths)
ExecutorAgent._build_sys_path_code = staticmethod(build_sys_path_code)
ExecutorAgent._is_similar_module_name = staticmethod(is_similar_module_name)
ExecutorAgent._apply_import_replacements = staticmethod(apply_import_replacements)
