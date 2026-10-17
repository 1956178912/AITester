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
from src.utils.credential_scrub import scrub_os_environ
from src.utils.env_utils import env_flag

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
      沙箱目录，被测代码的 import 不污染系统环境，任务间依赖互不冲突；
      P2-5（2026-10 批次）起，KERNEL_SANDBOX_ENABLE=true 时该链路的 pytest
      子进程进一步包装进内核沙箱（macOS Seatbelt / Linux bwrap），
      fail-closed 口径与本地链路一致（结果附 kernel_sandbox_obs 观测层）。
    - 默认：本地系统 Python 执行（历史行为）；KERNEL_SANDBOX_ENABLE=true 时
      经内核沙箱包装（G3，2026-09-30 接入）。

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
        use_docker: bool | None = None,
        use_venv: bool | None = None,
        auto_install_deps: bool = False,
        dep_install_timeout: int = 120,
        docker_image: str = "aitester:latest",
    ) -> None:
        # R10（2026-09-30 独立审查 N8，P1）：use_docker / use_venv 缺省（None）
        # 时回落 config 值（EXECUTOR_USE_DOCKER / EXECUTOR_USE_VENV）——
        # 节点层与直接构造两条路径同口径；显式传 bool 时尊重调用方
        # （测试 / 消融实验可显式关沙箱，不退化为 config 默认）。
        from config import EXECUTOR_USE_DOCKER, EXECUTOR_USE_VENV as _CFG_VENV  # isort: skip

        if use_docker is None:
            use_docker = EXECUTOR_USE_DOCKER
        if use_venv is None:
            use_venv = _CFG_VENV
        # timeout 从参数传入，默认 30 秒
        self.timeout = timeout
        self.use_docker = use_docker
        self.use_venv = use_venv
        self.auto_install_deps = auto_install_deps
        self.dep_install_timeout = dep_install_timeout
        self.docker_image = docker_image
        # G3 内核级沙箱（KERNEL_SANDBOX_ENABLE=true 时启用，默认 false）：
        # 本地 / venv 沙箱执行链路把 pytest 子进程包装进内核沙箱
        # （macOS Seatbelt / Linux Landlock+bwrap）；Docker 链路已有
        # 容器级出口管控，不走本开关。不支持当前平台时 fail-closed
        # （拒绝执行，不静默降级到无隔离本地——与 executor_modes 的
        # docker_unavailable 同口径，避免"以为隔离了其实没有"污染
        # 对比实验）。_kernel_sandbox_executable / _kernel_sandbox_obs
        # 观测层：executable 记录沙箱工具名（sandbox-exec / bwrap，
        # 2026-10-01 P1 修复后完整命令作 argv 直接传入，executable 字段
        # 仅作观测/校验用途），obs 记录沙箱 profile 摘要。
        self._kernel_sandbox_executable: str | None = None
        self._kernel_sandbox_obs: dict[str, Any] = {}

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
            # 类属性运行期绑定（见文件底部 ExecutorAgent._execute_docker = execute_docker），
            # mypy 按类签名校验报 attr-defined，显式忽略
            return self._execute_docker(test_code, target_file, target_function)  # type: ignore[attr-defined]

        # 隔离沙箱路径：venv + 临时目录执行，避免依赖冲突与环境污染（P1 优化）
        if self.use_venv:
            return self._execute_sandboxed(test_code, target_file, target_function)  # type: ignore[attr-defined]

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

        fixed_test_code = self._auto_fix_imports(test_code, target_file, project_root)  # type: ignore[attr-defined]
        if fixed_test_code != test_code:
            logger.info("已自动修复模块导入路径")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(fixed_test_code)
            test_file = f.name

        try:
            # 4.1 脱敏审计：子进程执行的是 LLM 生成的任意测试代码，
            # LLM 的 API 凭证不得随环境继承进被测沙箱（泄露面 +
            # 生成代码意外外传向量）。按动态模式剔除 LLM_N_API_KEY 等
            # （credential_scrub，三条执行链路共用，避免固定名单漂移）。
            env = scrub_os_environ()
            # S4（2026-09-29 审查 P0）：最小环境白名单——此前
            # env = scrub_os_environ() 保留全部继承环境（HOME / PATH /
            # LD_LIBRARY_PATH / PYTHONPATH / AWS_* / OPENAI_* / GITHUB_*），
            # LLM 生成代码内 os.environ 可整包读取并外传。现收敛到
            # EXECUTOR_ENV_WHITELIST 环境变量（逗号分隔，默认最小集
            # PATH,HOME,LANG,LC_ALL,PYTHONPATH），同时保留 4.1 脱敏。
            _env_whitelist_raw = os.getenv("EXECUTOR_ENV_WHITELIST", "").strip()
            if _env_whitelist_raw:
                _env_whitelist = {k.strip() for k in _env_whitelist_raw.split(",") if k.strip()}
                env = {k: v for k, v in env.items() if k in _env_whitelist}
            else:
                _env_whitelist = {"PATH", "HOME", "LANG", "LC_ALL", "PYTHONPATH"}
                env = {k: v for k, v in env.items() if k in _env_whitelist}
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

            # 2026-10-10 独立审查修复（P0，实跑两次复现）：**pytest 插件级超时**。
            #
            # 根因：被测缺陷实现若陷入死循环（本批实测 `to_base` 等），LLM 生成的
            # 测试会在被测代码里永不返回。此时 `executor_runtime` 的
            # `subprocess.run(timeout=30)` 到点后只 kill **直接子进程**，而 pytest
            # 自身的子进程/孙进程继续持有 stdout/stderr 管道写端 →
            # `communicate()` 等 EOF **永久阻塞** → 整臂挂死、批次 JSON 从不写出
            # （实测证据：主进程 %CPU 0.0、持有 3 个 PIPE、子进程 98.7% CPU 空转）。
            #
            # 为什么在**命令层**加超时而不是改 subprocess 调用层：pytest-timeout
            # 在**测试内部**触发，进程正常退出并返回非零 rc，因此
            # `subprocess.run` 的返回契约、超时分类（error_info.type）与既有
            # 12 个 mock `subprocess.run` 的测试全部无需改动——属最小侵入。
            #
            # 口径：默认**关**（ADR-0003 默认行为不变）；置
            # `PYTEST_TIMEOUT_ENABLE=true` 时生效，秒数取 `PYTEST_TIMEOUT_SECONDS`
            # （默认 20 < EXECUTION_TIMEOUT 30，确保插件先于外层墙钟触发，
            # 使外层走"正常返回"而非"超时 kill"路径）。
            if env_flag("PYTEST_TIMEOUT_ENABLE"):
                try:
                    _pto = max(1, int(os.getenv("PYTEST_TIMEOUT_SECONDS", "20")))
                except ValueError:
                    _pto = 20
                cmd.extend([f"--timeout={_pto}", "--timeout-method=thread"])

            # G3 内核级沙箱（KERNEL_SANDBOX_ENABLE=true 时启用，默认 false）：
            # 把本地执行链路的 pytest 子进程包装进内核沙箱
            # （macOS Seatbelt / Linux Landlock+bwrap）。fail-closed：
            # 当前平台无可用沙箱后端时直接拒绝执行（不静默降级到无隔离
            # 本地——避免"以为隔离了其实没有"污染对比实验口径，
            # 与 executor_modes 的 docker_unavailable 同口径）。
            #
            # N-2（2026-10-17）接线修复：此前只放行 [target_dir]，解释器自身
            # （venv/bin/python 字面路径 / framework Python.app / venv 根）与
            # pytest 临时目录均不可见 → `sandbox-exec: execvp() of
            # '.../.venv/bin/python' failed: Operation not permitted`（rc=71），
            # 且被误分类为 test_failure。现按"exec 仅执行 / read 只读 / write
            # 读写"细分放行面：
            #   - exec：解释器 argv[0] 字面 + realpath + framework 安装根；
            #   - read：项目根（pytest 读配置但**不得写仓库根**）+ venv 根 +
            #     framework 安装根 + TMPDIR；
            #   - write：TMPDIR（pytest 临时文件 / coverage 数据文件）。
            # 同时沙箱内禁写 .pyc/.pytest_cache、coverage 数据落 TMPDIR，
            # 避免写仓库根造成工件污染与安全面扩大。
            from src.agents.kernel_sandbox import (
                SandboxUnavailable,
                build_sandbox_command,
                interpreter_sandbox_allowances,
                kernel_sandbox_enabled,
                sandbox_launch_failure,
            )

            _ks_tmpdir = tempfile.gettempdir()
            if kernel_sandbox_enabled():
                # 沙箱模式专有：不写字节码/不写 pytest cache/coverage 数据落 TMPDIR
                if not any(arg == "-p" and "no:cacheprovider" in cmd for arg in cmd):
                    cmd.extend(["-p", "no:cacheprovider"])
                env["PYTHONDONTWRITEBYTECODE"] = "1"
                # 显式传 TMPDIR（默认 exec 环境白名单不含它）：pytest/tempfile 的
                # 临时目录必须与沙箱放行的可写路径一致，否则 tempfile 探测失败
                # （No usable temporary directory found）。
                env["TMPDIR"] = _ks_tmpdir
                env["COVERAGE_FILE"] = os.path.join(_ks_tmpdir, f".coverage_kernelsandbox_{os.getpid()}.data")
                _ks_allow = interpreter_sandbox_allowances(python_path)
                try:
                    sandboxed_cmd, obs = build_sandbox_command(
                        cmd,
                        cwd=project_root,
                        allowed_paths=[target_dir],
                        cwd_rw=False,
                        exec_paths=_ks_allow["exec_paths"],
                        read_paths=[project_root, _ks_tmpdir, *_ks_allow["read_paths"]],
                        write_paths=[_ks_tmpdir],
                    )
                except SandboxUnavailable as ks_exc:
                    # S1（2026-09-29 审查 P0）fail-closed：平台无可用沙箱后端且
                    # 未显式 ALLOW_UNSANDBOXED → 拒绝执行（显式错误类型，不裸跑）。
                    return {
                        "passed": False,
                        "output": f"内核级沙箱在当前平台不可用（S1 fail-closed 拒绝执行）: {ks_exc}",
                        "coverage": 0.0,
                        "failed_cases": [],
                        "error_info": {"type": "kernel_sandbox_unavailable", "message": str(ks_exc)},
                    }
                if obs.get("supported"):
                    self._kernel_sandbox_obs = obs
                    # 2026-10-01 全面审查 P1 修复：保留完整 sandboxed_cmd 作为 argv
                    # （seatbelt/bwrap 的 argv[0] 即工具自身），_kernel_sandbox_executable
                    # 仅作观测/校验用途。
                    self._kernel_sandbox_executable = sandboxed_cmd[0]
                    cmd = sandboxed_cmd
                else:
                    # S1（2026-09-29 审查 P0）：fail-closed —— obs["supported"]=False
                    # 时拒绝执行，返回 error_info type=kernel_sandbox_unavailable。
                    return {
                        "passed": False,
                        "output": "内核级沙箱在当前平台不可用（S1 fail-closed 拒绝执行；"
                        "如需无隔离调试请显式设 ALLOW_UNSANDBOXED=true 并记录工件档位）",
                        "coverage": 0.0,
                        "failed_cases": [],
                        "error_info": {
                            "type": "kernel_sandbox_unavailable",
                            "message": obs.get("profile_summary", ""),
                        },
                        "kernel_sandbox_obs": obs,
                    }

            output, last_result = self._run_pytest_with_retry(cmd, env, project_root)  # type: ignore[attr-defined]
            # 检查是否需要立即返回（超时/环境问题/通用异常无有效结果）
            # 2026-09-26 round9 P2：新增 "UNAVAILABLE" 标记（通用异常且无有效
            # 结果时），与 EARLY_RETURN 走同一早退分支（error_info 透传）。
            if isinstance(last_result, tuple) and last_result[0] in ("EARLY_RETURN", "UNAVAILABLE"):
                result_early: dict[str, Any] = {
                    "passed": False,
                    "output": output,
                    "coverage": 0.0,
                    "failed_cases": [],
                    "error_info": last_result[1],
                }
                # N-2：沙箱启动/配置失败显式归因（不得误报为 test_failure；
                # 不新增 ErrorCategory 枚举值，error_info.type 为自由字符串）
                _ks_launch_error = sandbox_launch_failure(output) if self._kernel_sandbox_obs else None
                if _ks_launch_error:
                    result_early["error_info"] = {
                        "type": "kernel_sandbox_unavailable",
                        "message": _ks_launch_error,
                    }
                    result_early["kernel_sandbox_launch_failed"] = True
                if self._kernel_sandbox_obs:
                    result_early["kernel_sandbox_obs"] = self._kernel_sandbox_obs
                return result_early

            coverage = self._parse_coverage(output)  # type: ignore[attr-defined]
            failed_cases = self._parse_failed_cases(output)  # type: ignore[attr-defined]
            passed = last_result is not None and last_result.returncode == 0

            result_dict = {
                "passed": passed,
                "output": output,
                "coverage": coverage,
                "failed_cases": failed_cases,
            }
            # G3 内核级沙箱观测层（纯观测，不改结果口径；供 Fail-Closed
            # 治理协议 / 实验分析消费，与 Docker 链路的 docker_network_obs 同向）
            if self._kernel_sandbox_obs:
                result_dict["kernel_sandbox_obs"] = self._kernel_sandbox_obs

            if last_result and last_result.returncode != 0:
                result_dict["error_info"] = self._build_error_info(last_result, output)  # type: ignore[attr-defined]
                # N-2（2026-10-17）：沙箱启动/配置失败（profile 语法/exec 被拒/
                # bwrap 配置错）→ 显式 kernel_sandbox_unavailable，不得记为
                # test_failure（否则 Debugger 会去"修代码"、失败归因与 M1 观测口径
                # 被污染）。仅用 error_info.type 显式值，不新增 ErrorCategory 枚举。
                _ks_launch_error = sandbox_launch_failure(output) if self._kernel_sandbox_obs else None
                if _ks_launch_error:
                    result_dict["error_info"] = {
                        "type": "kernel_sandbox_unavailable",
                        "returncode": last_result.returncode,
                        "message": _ks_launch_error,
                    }
                    result_dict["kernel_sandbox_launch_failed"] = True
            # 执行路径结束（成功/失败）：清理实例级内核沙箱状态，
            # 避免下次调用（含关闭开关的场景）透传旧观测层
            self._kernel_sandbox_executable = None
            self._kernel_sandbox_obs = {}

            return result_dict
        finally:
            self._cleanup_temp_file(test_file)  # type: ignore[attr-defined]


# ─── 方法绑定：把子模块的纯函数以实例方法/静态方法形式挂回 ExecutorAgent ─────────
# 外部调用方（tests、graph/nodes、cli）与现有 patch 路径
# （src.agents.executor.ExecutorAgent.<method>）均以类属性方式访问，
# 绑定后行为与拆分前完全一致。
# 类型说明：模块期属性赋值不改变类签名，mypy 会报 attr-defined；
# 逐行 # type: ignore[attr-defined] 声明这是有意的运行期绑定（测试 patch 路径依赖）。
ExecutorAgent._run_pytest_with_retry = run_pytest_with_retry  # type: ignore[attr-defined]
ExecutorAgent._cleanup_temp_file = staticmethod(cleanup_temp_file)  # type: ignore[attr-defined]
ExecutorAgent._cleanup_sandbox = staticmethod(cleanup_sandbox)  # type: ignore[attr-defined]
ExecutorAgent._execute_sandboxed = execute_sandboxed  # type: ignore[attr-defined]
ExecutorAgent._execute_docker = execute_docker  # type: ignore[attr-defined]
ExecutorAgent._build_error_info = staticmethod(build_error_info)  # type: ignore[attr-defined]
ExecutorAgent._parse_coverage = staticmethod(parse_coverage)  # type: ignore[attr-defined]
ExecutorAgent._parse_failed_cases = staticmethod(parse_failed_cases)  # type: ignore[attr-defined]
ExecutorAgent._extract_module_name_from_file = staticmethod(extract_module_name_from_file)  # type: ignore[attr-defined]
ExecutorAgent._cached_search_module_path = staticmethod(cached_search_module_path)  # type: ignore[attr-defined]
ExecutorAgent._auto_fix_imports = staticmethod(auto_fix_imports)  # type: ignore[attr-defined]
ExecutorAgent._extract_imports = staticmethod(extract_imports)  # type: ignore[attr-defined]
ExecutorAgent._resolve_module_paths = staticmethod(resolve_module_paths)  # type: ignore[attr-defined]
ExecutorAgent._build_sys_path_code = staticmethod(build_sys_path_code)  # type: ignore[attr-defined]
ExecutorAgent._is_similar_module_name = staticmethod(is_similar_module_name)  # type: ignore[attr-defined]
ExecutorAgent._apply_import_replacements = staticmethod(apply_import_replacements)  # type: ignore[attr-defined]
