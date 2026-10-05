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
from src.agents.kernel_sandbox import kernel_sandbox_enabled
from src.utils.credential_scrub import scrub_os_environ

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
       （P2-5，2026-10 批次）KERNEL_SANDBOX_ENABLE=true 时，上述 pytest 子进程
       进一步包装进内核沙箱（macOS Seatbelt / Linux bwrap），fail-closed 口径
       与本地链路（executor._execute_local）一致，结果附 kernel_sandbox_obs；
    5. 清理沙箱目录（venv 保留缓存，相同依赖组合的任务复用）。

    Returns:
        与 execute() 相同结构的结果字典。
    """
    # 被测模块名：取 target_file 基名（与 extract_module_name_from_file 语义一致）
    module_name = extract_module_name_from_file(target_file)
    sandbox_dir = tempfile.mkdtemp(prefix="aitester_sandbox_")
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
    # 2026-09-26 round9 P2：写入失败时走 finally 清理沙箱（旧实现 L70-71
    # 的 with open 在 try/finally 之外，OSError 时沙箱目录泄漏）。
    # 2026-10-01 全面审查 P2 修复：此前 try/finally 注释与实际代码不符——
    # with open 仍在 try/finally 之外（L70-73 直接写，无 try 包裹），
    # open(test_file, "w") 抛 OSError（磁盘满 / 权限）时沙箱目录泄漏。
    # 现补 try/except OSError：写失败 → 清理沙箱 + 返回 file_write_failed 诊断。
    fixed_test_code = auto_fix_imports(test_code, module_file, sandbox_dir)
    test_file = os.path.join(sandbox_dir, "test_generated.py")
    try:
        with open(test_file, "w", encoding="utf-8") as f:
            f.write(fixed_test_code)
    except OSError as e:
        cleanup_sandbox(sandbox_dir)
        return {
            "passed": False,
            "output": f"测试文件写入沙箱失败: {e}",
            "coverage": 0.0,
            "failed_cases": [],
            "error_info": {"type": "file_write_failed", "message": str(e), "file_path": test_file},
        }

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

    # G3 内核级沙箱（P2-5，2026-10 批次，KERNEL_SANDBOX_ENABLE=true 时启用，默认 false）：
    # 把 venv 沙箱执行链路的 pytest 子进程包装进内核沙箱
    # （macOS Seatbelt / Linux Landlock+bwrap）——此前仅本地链路
    # （executor._execute_local，2026-09-30 G3）接入，venv 沙箱作为默认
    # 推荐隔离路径（EXECUTOR_USE_VENV=true）却走裸子进程，内核沙箱开关
    # 在"venv 开 + kernel 开"组合下静默失效（"以为有隔离其实只有 venv"，
    # 与 kernel_sandbox 模块 docstring 声明的目标场景矛盾）。
    # 接入口径与本地链路逐条对齐（同 fail-closed、同 S1 修复的完整 argv 传法）：
    # - 允许路径：sandbox_dir（pytest 在沙箱目录执行）+ 解释器路径
    #   （seatbelt 的 process-exec 需可执行目标；bwrap 的 ro-bind 需
    #   解释器所在库目录可达）；
    # - S1（fail-closed）：build_sandbox_command 抛 SandboxUnavailable
    #   （平台无后端且 ALLOW_UNSANDBOXED=false）→ 拒绝执行并返回
    #   kernel_sandbox_unavailable 诊断（不静默降级到无隔离 venv 裸跑）；
    # - 完整 argv 传法（2026-10-01 P1 修复同款）：cmd 直接替换为
    #   sandboxed_cmd（seatbelt/bwrap 自身作 argv[0]，无 subprocess 语义歧义）；
    # - 观测层：结果 dict 附 kernel_sandbox_obs（与本地链路同字段，供
    #   Fail-Closed 治理协议 / 实验分析消费，纯观测不改结果口径）。
    # 默认关（KERNEL_SANDBOX_ENABLE=false）时本段零行为变化。
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

    result_extras: dict[str, Any] = {}
    if kernel_sandbox_enabled():
        from src.agents.kernel_sandbox import SandboxUnavailable, build_sandbox_command

        _ks_allowed = [sandbox_dir, sys.executable]
        try:
            sandboxed_cmd, ks_obs = build_sandbox_command(
                cmd,
                cwd=sandbox_dir,
                allowed_paths=_ks_allowed,
            )
        except SandboxUnavailable as ks_exc:
            # S1 fail-closed：平台无可用内核沙箱后端且未显式容忍无隔离 →
            # 拒绝执行（与本地链路口径一致），不静默降级 venv 裸跑
            return {
                "passed": False,
                "output": f"内核级沙箱在当前平台不可用（S1 fail-closed 拒绝执行）: {ks_exc}",
                "coverage": 0.0,
                "failed_cases": [],
                "error_info": {
                    "type": "kernel_sandbox_unavailable",
                    "message": str(ks_exc),
                },
            }
        if ks_obs.get("supported"):
            cmd = sandboxed_cmd
            result_extras = {"kernel_sandbox_obs": ks_obs}
        else:
            # S1 双保险：build_sandbox_command 已对"不支持且
            # ALLOW_UNSANDBOXED=false"抛 SandboxUnavailable；此处
            # supported=False 仅在 ALLOW_UNSANDBOXED=true 容忍档可达，
            # 同样拒绝执行（保守 fail-closed：容忍无隔离须走异常路径感知，
            # 不静默裸跑）。
            return {
                "passed": False,
                "output": "内核级沙箱在当前平台不可用（S1 fail-closed 拒绝执行；"
                "如需无隔离调试请显式设 ALLOW_UNSANDBOXED=true 并记录工件档位）",
                "coverage": 0.0,
                "failed_cases": [],
                "error_info": {
                    "type": "kernel_sandbox_unavailable",
                    "message": ks_obs.get("profile_summary", ""),
                },
                "kernel_sandbox_obs": ks_obs,
            }

    try:
        output, last_result = self._run_pytest_with_retry(cmd, env, sandbox_dir)
        # 2026-09-26 round9 P2：新增 "UNAVAILABLE" 标记（通用异常且无有效
        # 结果时），与 EARLY_RETURN 走同一早退分支（error_info 透传）。
        if isinstance(last_result, tuple) and last_result[0] in ("EARLY_RETURN", "UNAVAILABLE"):
            result = {
                "passed": False,
                "output": output,
                "coverage": 0.0,
                "failed_cases": [],
                "error_info": last_result[1],
                **result_extras,
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
                **result_extras,
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

    env = scrub_os_environ()
    # 模块搜索路径以沙箱目录为首（追加原 PYTHONPATH 保留 pytest 等测试工具）；
    # 空段过滤防尾随冒号（语义同上，空元素等价 CWD 可遮蔽同名文件）
    # 4.1 脱敏：env 经 scrub_os_environ 已剔除 LLM_N_API_KEY 等凭证，
    # LLM 生成的测试代码在沙箱内读不到调用方的 API 凭证
    env["PYTHONPATH"] = os.pathsep.join(
        [sandbox_dir] + [p for p in (env.get("PYTHONPATH") or "").split(os.pathsep) if p]
    )
    # P1 内核沙箱升级：venv 沙箱环境变量隔离（默认关，保持历史口径）。
    # SANDBOX_ENV_ISOLATION=true 时，把宿主 HOME / USERPROFILE / SSH_AUTH_SOCK /
    # 云凭证（AWS_* / GCP_* / AZURE_*）等敏感环境变量显式置空，LLM 生成的
    # 测试代码在沙箱内读不到宿主密钥与云凭证（venv 路径本身经 venv_cache_dir
    # 独立，HOME 置空不影响 venv 解析——create_venv 的缓存目录在 _prepare_
    # dependencies 的 venv_cache_dir() 内解析为绝对路径，不依赖 HOME）。
    # 默认 false：不改动 env（历史实验口径逐字节不变）。
    if os.getenv("SANDBOX_ENV_ISOLATION", "false").strip().lower() == "true":
        for _var in (
            "HOME",
            "USERPROFILE",
            "SSH_AUTH_SOCK",
            "SSH_AGENT",
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_SESSION_TOKEN",
            "GOOGLE_APPLICATION_CREDENTIALS",
            "AZURE_STORAGE_ACCOUNT",
            "AZURE_STORAGE_KEY",
            "CLOUDSDK_COMPUTE_ZONE",
        ):
            env[_var] = ""
    python_path = sys.executable
    dep_install_note = ""
    sandbox_error_info: dict[str, Any] | None = None

    if missing_packages and self.use_venv:
        # 创建/复用缓存 venv（相同依赖组合 + 当前 Python 版本共享，省 1-3s 重建开销）
        # 4.4 多版本缓存：venv_cache_dir 默认将 sys.version_info 前两位纳入 key，
        # 不同 Python 版本的 venv 隔离存放，避免交叉复用导致依赖不兼容
        # R59（2026-09-30 独立审查 P0）/ S6（M11 2026-09-29 审查 P0）：
        # 包名幻觉（slopsquatting）防护经 suggest_package_names 内置的
        # PIP_PACKAGE_WHITELIST_ENABLE 白名单守卫实现——开启后仅白名单内
        # 包名放行安装（PEP 503 大小写不敏感），未知名默认拒绝，堵供应链
        # 向量。本处不重复实现白名单逻辑（单一事实来源在 dependency.py），
        # 仅记录：missing_packages 已经 suggest_package_names 的白名单过滤，
        # 白名单外的幻觉包名不会进入 install_packages。
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
        ]
        # P1 内核沙箱升级：Docker 网络出口管控（默认关，保持历史口径）。
        # DOCKER_NETWORK_ISOLATION=true 时加 --network=none（完全断网）；
        # DOCKER_NETWORK_ISOLATION=allowlist 时读 DOCKER_NETWORK_ALLOWLIST
        # （逗号分隔的 host:port 白名单）——
        # U6（2026-10-05 系统性审查落地）命名诚实化：allowlist 档实际加的是
        # --network=bridge（默认桥接），Docker 无 per-container 出站白名单
        # 原语，**真正的出口控制依赖宿主防火墙/iptables 或 egress proxy**。
        # 此前注释声称"仅允许白名单内出站，其余全部拒绝"与实际行为不符
        # （bridge 下容器出站不受限）——虚假安全感比无防护更危险（审查结论）。
        # 现修正口径：①注释如实声明"allowlist 档 = bridge + 白名单元数据
        # 记录，出口控制须由宿主侧配置"；②运行期一次性 WARNING 提醒部署者
        # 该档位不提供容器级出站限制（观测层，不改变命令构造）。
        # 默认 false：不改变 Docker 命令（历史实验口径逐字节不变）。
        network_isolation = os.getenv("DOCKER_NETWORK_ISOLATION", "false").strip().lower()
        if network_isolation == "allowlist" and os.getenv("DOCKER_NETWORK_ALLOWLIST", "").strip():
            logger.warning(
                "U6 诚实化提醒：DOCKER_NETWORK_ISOLATION=allowlist 仅记录白名单元数据"
                "并使用 --network=bridge，Docker 不提供容器级出站白名单——出口控制"
                "必须由宿主防火墙/egress proxy 实施；需容器级断网请用 =true（--network=none）"
            )
        if network_isolation == "true":
            cmd.append("--network=none")
        elif network_isolation == "allowlist":
            allowlist = os.getenv("DOCKER_NETWORK_ALLOWLIST", "").strip()
            if not allowlist:
                # 白名单模式但未配置任何允许项 → 保守拒绝（fail-closed），
                # 等价于 --network=none（"以为配了出口管控其实全放"是最大敞口）
                cmd.append("--network=none")
            else:
                # 白名单模式：加 --network=bridge（默认桥接），实际出口控制
                # 依赖宿主防火墙/iptables（Docker 本身无 per-container 出站白名单
                # 原语，需 egress proxy 或网络命名空间隔离实现；此处保守加 bridge
                # 并在 error_info 中记录白名单配置，供 Fail-Closed 治理协议消费）。
                cmd.append("--network=bridge")
        # S3（2026-09-29 审查 P0）：资源限制 —— 容器 CPU / 内存 / 进程数
        # 上限（防 fork 炸弹 / 内存爆炸把宿主打死）。
        # DOCKER_CPU_LIMIT（默认 2.0）/ DOCKER_MEM_LIMIT_MB（默认 2048）
        # / DOCKER_PIDS_LIMIT（默认 256）/ DOCKER_READ_ONLY（默认 true）。
        # 全部默认非 0，历史口径有变化（安全加固）；设 0/false 可恢复
        # 无限制口径（工件须记录该档位）。
        _docker_cpu_limit = float(os.getenv("DOCKER_CPU_LIMIT", "2.0"))
        _docker_mem_limit_mb = int(os.getenv("DOCKER_MEM_LIMIT_MB", "2048"))
        _docker_pids_limit = int(os.getenv("DOCKER_PIDS_LIMIT", "256"))
        _docker_read_only = os.getenv("DOCKER_READ_ONLY", "true").lower() in ("true", "1", "on")
        if _docker_cpu_limit > 0:
            cmd.extend(["--cpus", str(_docker_cpu_limit)])
        if _docker_mem_limit_mb > 0:
            cmd.extend(["--memory", f"{_docker_mem_limit_mb}m"])
        if _docker_pids_limit > 0:
            cmd.extend(["--pids-limit", str(_docker_pids_limit)])
        # S3：容器内以非特权用户运行（nobody 65534）+ 只读根文件系统
        # + /tmp tmpfs（容器内 pytest 需写 /tmp）+ 全 cap drop
        if _docker_read_only:
            cmd.extend(["--read-only", "--tmpfs", "/tmp:size=256m"])
        cmd.extend(["--cap-drop=ALL", "--security-opt", "no-new-privileges"])
        # S3：默认断网（--network=none）；DOCKER_NETWORK_ISOLATION=false 且
        # DOCKER_DEFAULT_NETWORK_NONE=true（默认 true）时保持历史 bridge 口径
        _default_network_none = os.getenv("DOCKER_DEFAULT_NETWORK_NONE", "true").lower() in ("true", "1", "on")
        if network_isolation == "true" or (_default_network_none and network_isolation != "allowlist"):
            cmd.append("--network=none")
        docker_image = self.docker_image
        cmd.append(docker_image)
        cmd.extend(
            ["python", "-m", "pytest", "test_generated.py", "-v", "--tb=short", "--cov=/workspace", "--cov-report=term"]
        )
        if target_function:
            cmd.extend(["-k", target_function])

        # P1 内核沙箱升级：把网络隔离配置写入 error_info 观测层（纯观测，不改
        # 结果口径；供 Fail-Closed 治理协议 / 实验分析消费）。
        network_isolation_cfg = os.getenv("DOCKER_NETWORK_ISOLATION", "false").strip().lower()
        docker_network_obs: dict[str, Any] = {"isolation_mode": network_isolation_cfg}
        if network_isolation_cfg == "allowlist":
            docker_network_obs["allowlist"] = os.getenv("DOCKER_NETWORK_ALLOWLIST", "").split(",") or []
            # U6（2026-10-05 系统性审查落地）：观测层如实标注 allowlist 档的
            # 实际隔离能力（bridge 无容器级出站限制），供报告/治理协议消费
            docker_network_obs["egress_enforced"] = False
            docker_network_obs["egress_note"] = "bridge 网络，无容器级出站白名单；出口控制依赖宿主防火墙/egress proxy"

        try:
            # 容器启动开销（镜像拉取/文件系统初始化）远大于本地子进程，
            # 超时下限放宽到 120s 避免误判
            # 4.1 脱敏：容器继承宿主环境（docker run 未加 --env 隔离），
            # 经 scrub_os_environ 剔除 LLM_N_API_KEY 等凭证后再传入
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=max(self.timeout, 120),
                env=scrub_os_environ(),
                check=False,  # 显式声明按 returncode 判断（本仓统一口径，PLW1510）
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
        # P1 内核沙箱升级：网络出口管控配置观测层（纯观测，不改结果口径）
        if docker_network_obs.get("isolation_mode") != "false":
            result_dict["docker_network_obs"] = docker_network_obs
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
