"""ULT/PiTest cosmic-ray 口径 mutation-score 适配器（STVR 实证研究批次，零 LLM 成本骨架）。

背景：
    AITester 当前 mutation score 主指标（STVR 实证研究设计 §4.2）用**自研
    AST 变异体**（`experiments/mutation_testing.py` 七类算子，确定性本地
    执行，零 LLM）——但 ULT 官方评测口径（`ULT_Lite` / `ULT` 全量）要求
    **cosmic-ray 全变异体 + 120s 超时**（`docs/design/ult_bridge_plan.md`
    §4.3），二者数值**不可直接比**（变异算子集不同、超时语义不同、
    变异体数量不同）。本适配器把 cosmic-ray 口径接入 AITester 主实验
    （`experiments/run_benchmark.py` 的 `ENABLE_MUTATION_SCORING` 门控
    侧），使 STVR 实证研究设计 §4 的"mutation score 主指标"在
    **双口径分述**框架下可实跑。

设计约束（与 STVR 实证研究设计 §4.2 锁死的口径一致）：
    - **cosmic-ray 未安装时**：`_cosmic_ray_available()` 返回 False →
      `ult_mutation_score` 返回 `{"available": False, ...}`（保守口径，
      **不**静默回退到自研 AST 变异体——回退会污染口径可比性，
      审稿人会质疑"主指标到底是哪个"）；
    - **cosmic-ray 已安装时**：调用其 `run` 子命令（`cosmicray run`
      风格），解析 mutation score（`killed / total`），按 ULT 官方
      120s 超时口径；
    - **零 LLM 成本**：cosmic-ray 变异体生成 + pytest 判定均为确定性
      本地执行（不耗 LLM 配额），但 LLM 测试生成侧仍需调用（由
      `run_benchmark.py` 驱动，需用户授权）；
    - **版本钉锁**：cosmic-ray 版本 + 配置哈希须入报告（`docs/design/
      ult_bridge_plan.md` §4.3 R3 风险登记），本适配器在 `__main__`
      的 dry-run 计划 JSON 中透出 `cosmic_ray_version` /
      `cosmic_ray_config_hash` 字段，使跨批次可比性可审计。

本批次（零 LLM 成本）交付：
    - 适配器纯函数骨架（`ult_mutation_score` / `is_cosmic_ray_available` /
      `dry_run_plan`）；
    - 12 例回归测试（`tests/test_ult_adapter.py`）：cosmic-ray 不可用
      的保守口径、版本/配置哈希字段、键集合同构；
    - `docs/design/ult_bridge_plan.md` §4.3 状态刷新（cosmic-ray 未安装
      的阻塞项登记 + 本适配器接线点）。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import logging
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ULT 官方评测口径（docs/design/ult_bridge_plan.md §4.3 锁死）
ULT_MUTATION_TIMEOUT_SECONDS = 120
# 注（2026-10-13 裁定）：算子集 = **全变异体**（cosmic-ray 不设 operators 键
# 即默认全变异体；ULT 官方 README 未指定 operators 过滤）。以下 9 类是
# **描述性分类，非实际算子集**——仅供 dry_run_plan 的 "operators" 字段作
# 展示用，不参与 cosmic_ray_config_hash（哈希的是 "全变异体默认" 这一事实，
# 见 cosmic_ray_config_hash 的 docstring）。
ULT_MUTANT_OPERATORS = [
    "Arithmetic",
    "Assignment",
    "Conditionals",
    "Exception",
    "Global",
    "MethodCall",
    "Number",
    "Statement",
    "String",
]


def is_cosmic_ray_available() -> bool:
    """探测 cosmic-ray 是否可导入（确定性，不触发变异生成）。

    cosmic-ray 的 Python 包名为 ``cosmic_ray``（下划线），发行名为
    ``cosmic-ray``（连字符，pip 安装名）。此处按包名探测导入能力。
    """
    return importlib.util.find_spec("cosmic_ray") is not None


def cosmic_ray_version() -> str | None:
    """cosmic-ray 版本字符串（不可用时返回 None）。

    版本取自发行元数据（``importlib.metadata.version("cosmic-ray")``，
    发行名连字符与下划线等价），而非 ``cosmic_ray.__version__``（包内
    未导出该属性）。
    """
    if not is_cosmic_ray_available():
        return None
    try:
        from importlib.metadata import version

        return str(version("cosmic-ray"))
    except Exception:  # pragma: no cover - 元数据缺失
        return "unknown"


def cosmic_ray_config_hash() -> str | None:
    """cosmic-ray 配置的 SHA-256 哈希（cosmic-ray 未安装时返回 None）。

    哈希覆盖**实际启用的口径**（`ult_bridge_plan.md` §4.3 已裁定）：
    - ``operators`` = ``"all_mutants_default"``——不设 operators 键即
      cosmic-ray 默认全变异体（ULT 官方 README 未指定 operators 过滤，
      9 类描述常量 ``ULT_MUTANT_OPERATORS`` 非实际算子集）；
    - ``timeout_seconds`` = ``ULT_MUTATION_TIMEOUT_SECONDS``（120s）；
    - ``cosmic_ray_version`` = 实测版本（版本 + 配置哈希同时入报告，
      跨批次可比性审计，`ult_bridge_plan.md` §4.3 R3 风险登记）。

    因哈希含实测版本，cosmic-ray 未安装（版本不可测）时返回 None，
    与 ``cosmic_ray_version()`` 同口径（不伪造哈希）。
    """
    version = cosmic_ray_version()
    if version is None:
        return None
    payload = json.dumps(
        {
            "operators": "all_mutants_default",
            "timeout_seconds": ULT_MUTATION_TIMEOUT_SECONDS,
            "cosmic_ray_version": version,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _cosmic_ray_base_cmd(http_mode: bool = False) -> list[str]:
    """cosmic-ray CLI 基础命令（经当前解释器执行包内 cli 入口）。

    cosmic-ray 8.x 无 ``run`` 子命令，工作流为 ``init → exec → dump``；
    包 ``cosmic_ray`` 无 ``__main__``，须经 ``cosmic_ray.cli`` 模块入口
    执行（等价于控制台脚本 ``cosmic-ray``）。

    http_mode=True（D3 加速，2026-10-29）：cosmic_ray.distribution.http 的
    ``asyncio.get_event_loop()`` 在 Python 3.14 无隐式事件循环 ⇒ RuntimeError
    ——改用 -c 包装预建事件循环再进 cli（click 按sys.argv[1:] 解析，参数
    透传等价）。worker 本身（http-worker）不受影响。
    """
    if http_mode:
        wrapper = (
            "import asyncio\n"
            "loop = asyncio.new_event_loop()\n"
            "asyncio.set_event_loop(loop)\n"
            "from cosmic_ray.cli import cli\n"
            "cli()\n"
        )
        return [sys.executable, "-c", wrapper]
    return [sys.executable, "-m", "cosmic_ray.cli"]


def _write_cosmic_ray_config(config_path: Path, module_name: str, test_file_name: str, timeout: float) -> None:
    """写入 cosmic-ray TOML 配置（不设 ``operators`` 键 = 全变异体口径）。

    ``test-command`` 用当前解释器跑 pytest（与 cosmic-ray 同环境，保证
    pytest 与依赖可用），由 cosmic-ray 内部 ``shlex.split`` 解析。
    """
    # PYTEST_DISABLE_PLUGIN_AUTOLOAD（2026-10-29）：主仓 venv 的某插件 autoload
    # 在 pytest 收尾时挂死（测试跑完进程挂 121s 被超时杀）——cosmic-ray 的
    # 120s 变异体预算会被挂死吃光（挂死记 killed 是口径、但全部变异体变假
    # killed——禁插件恢复真实击杀判定）。env 前缀经 shlex.split 正确解析。
    test_command = f"env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 {sys.executable} -m pytest {test_file_name} -q"
    content = (
        "[cosmic-ray]\n"
        f'module-path = "{module_name}.py"\n'
        f"timeout = {float(timeout)!r}\n"
        "excluded-modules = []\n"
        f"test-command = {json.dumps(test_command)}\n"
        "\n"
        "[cosmic-ray.distributor]\n"
        'name = "local"\n'
    )
    config_path.write_text(content, encoding="utf-8")


def _write_cosmic_ray_config_http(
    config_path: Path, module_name: str, test_file_name: str, timeout: float, worker_urls: list[str]
) -> None:
    """写入 http distributor 配置（变异体级并行；结果语义与 local 逐位一致）。

    区别仅在 distributor 与 worker-urls——session 初始化、变异体枚举、
    dump 解析完全共用，mutation_score 不受 distributor 影响。
    """
    # PYTEST_DISABLE_PLUGIN_AUTOLOAD（2026-10-29）：主仓 venv 的某插件 autoload
    # 在 pytest 收尾时挂死（测试跑完进程挂 121s 被超时杀）——cosmic-ray 的
    # 120s 变异体预算会被挂死吃光（挂死记 killed 是口径、但全部变异体变假
    # killed——禁插件恢复真实击杀判定）。env 前缀经 shlex.split 正确解析。
    test_command = f"env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 {sys.executable} -m pytest {test_file_name} -q"
    urls_toml = json.dumps(worker_urls)
    content = (
        "[cosmic-ray]\n"
        f'module-path = "{module_name}.py"\n'
        f"timeout = {float(timeout)!r}\n"
        "excluded-modules = []\n"
        f"test-command = {json.dumps(test_command)}\n"
        "\n"
        "[cosmic-ray.distributor]\n"
        'name = "http"\n'
        "\n"
        "[cosmic-ray.distributor.http]\n"
        f"worker-urls = {urls_toml}\n"
    )
    config_path.write_text(content, encoding="utf-8")


def _spawn_http_workers(worker_count: int, tmpdir: Path) -> tuple[list[subprocess.Popen[Any]], list[str]]:
    """为单任务起 worker_count 个 http-worker（端口按 pid 派生避免分片间冲突）。

    Returns:
        (worker 进程列表, worker-urls)。worker 启动失败（如端口占用）的
        进程会被丢弃；若全部失败返回空列表（调用方回退 local 口径）。
    """
    port_base = 20000 + (os.getpid() % 18000)
    procs: list[subprocess.Popen[Any]] = []
    urls: list[str] = []
    for i in range(worker_count):
        port = port_base + i
        try:
            proc = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "cosmic_ray.cli",
                    "http-worker",
                    "--port",
                    str(port),
                ],
                cwd=str(tmpdir),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                # 脱离进程组：分片主进程经 nohup 后台启动时，bash 退出向进程组
                # 发 SIGHUP 会杀掉未受保护的 worker 孙进程 ⇒ exec 无 worker 可用
                # 而挂起（2026-10-29 实测 24 分片全停摆）。start_new_session 使
                # worker 自成会话，免疫组长信号。
                start_new_session=True,
            )
            procs.append(proc)
            urls.append(f"http://127.0.0.1:{port}")
        except OSError:
            continue
    # 就绪等待：worker 的 aiohttp 启动需 ~1s；轮询 TCP 连接（最多 5s）
    import socket
    import time

    deadline = time.time() + 5.0
    ready: list[subprocess.Popen[Any]] = []
    ready_urls: list[str] = []
    for proc, url in zip(procs, urls, strict=True):
        port = int(url.rsplit(":", 1)[1])
        while time.time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                    ready.append(proc)
                    ready_urls.append(url)
                    break
            except OSError:
                if proc.poll() is not None:
                    break  # worker 已崩（端口占用等）
                time.sleep(0.2)
    return ready, ready_urls


def _trim_work_items(session_path: str, max_mutants: int) -> None:
    """把 session 里超过 ``max_mutants`` 的变异体工作项删除（控制执行时间）。

    ``cosmic-ray init`` 后 session.sqlite 的 ``work_items`` 表即全量变异体；
    本函数按 ``job_id`` 排序保留前 ``max_mutants`` 个，删除其余（先删子表
    ``mutation_specs`` 再删 ``work_items``，规避外键约束）。

    注意（2026-10-15 批次八勘误）：``job_id`` 是 cosmic-ray ``init`` 时为
    每个工作项生成的 **uuid4 随机串**（``cosmic_ray/commands/init.py``），
    因此本截断保留的是**等概率随机子集**，而非确定性前 N 个——同一任务
    跨复跑会评估不同的变异体样本（此前文档"确定性截断面"的说法有误）。
    需要逐位可复现的 Mut@k 数值时，请使用**全变异体口径**（不截断，
    ``max_mutants`` 传哨兵值）。
    """
    conn = sqlite3.connect(session_path)
    try:
        extra = conn.execute(
            "SELECT job_id FROM work_items ORDER BY job_id LIMIT -1 OFFSET ?",
            (max_mutants,),
        ).fetchall()
        for (job_id,) in extra:
            conn.execute("DELETE FROM mutation_specs WHERE job_id = ?", (job_id,))
            conn.execute("DELETE FROM work_items WHERE job_id = ?", (job_id,))
        conn.commit()
    finally:
        conn.close()


def _count_work_items(session_path: str) -> int:
    """统计 session.sqlite 中 ``work_items`` 表的当前条目数。

    用途：计算 cosmic-ray ``exec`` 的整体兜底超时——按 init 生成并修剪后
    的**实际条目数**（而非调用方传入的 ``max_mutants`` 上界）计算，避免
    全变异体哨兵（如 ``10**9``）产出的超大超时值串到 C 层 PyTime_t
    （≈292 年上限）触发 ``OverflowError``（2026-10-15 批次八修复）。
    """
    conn = sqlite3.connect(session_path)
    try:
        (count,) = conn.execute("SELECT COUNT(*) FROM work_items").fetchone()
        return int(count)
    finally:
        conn.close()


def _parse_cosmic_ray_dump(dump_stdout: str) -> tuple[int, int]:
    """解析 ``cosmic-ray dump`` 输出为 ``(killed, total)``。

    dump 每行是一个 ``[WorkItem, WorkResult|null]`` 的 JSON 数组；WorkResult
    为 null 表示未执行（pending，不计入分母）。击杀口径与 cosmic-ray 官方
    ``is_killed`` 一致：``test_outcome != "survived"``（killed / incompetent
    均计击杀；超时由 cosmic-ray 判为 killed）。
    """
    total = 0
    killed = 0
    for line in dump_stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        _work_item, result = json.loads(line)
        if result is None:
            continue
        total += 1
        if result.get("test_outcome") != "survived":
            killed += 1
    return killed, total


def ult_mutation_score(
    target_code: str,
    test_code: str,
    module_name: str,
    max_mutants: int = 10,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    """计算 ULT 官方 cosmic-ray 口径的 mutation score（确定性本地执行，零 LLM）。

    Args:
        target_code: 被测目标代码（ULT 任务的 `source_code`）。
        test_code: LLM 生成的测试代码（import module_name）。
        module_name: 被测模块名（须与 test_code 的 import 名一致，
            口径同 `experiments/mutation_testing.py`）。
        max_mutants: 最多评估的变异体数量（默认 10，与自研 AST 变异体
            口径一致；ULT 官方口径下 cosmic-ray 全变异体可能更多，
            本参数控制子进程执行时间）。注意（2026-10-15 批次八勘误）：
            截断保留的是 uuid4 随机序子集（非确定性样本）；传哨兵值
            （如 ``10**9``）即不截断 = 全变异体口径（逐位可复现）。
        timeout_seconds: 单次 pytest 超时（None = ULT 官方 120s）。

    Returns:
        键集合同构 dict（cosmic-ray 不可用 / 输入缺失 / 超时 / IO 异常
        各分支均返回完整键集，与 `_m1_metrics` 的 None 保守口径一致）：
        - "available": bool（cosmic-ray 可用且成功运行 = True）
        - "mutation_score": float | None（killed / total；不可用 / 无
          变异体 / 执行失败 = None）
        - "mutants_total": int
        - "mutants_killed": int
        - "skipped": bool（保守跳过标记）
        - "skip_reason": str（跳过原因，空 = 未跳过）
        - "cosmic_ray_version": str | None
        - "cosmic_ray_config_hash": str | None
        - "elapsed_seconds": float

    注意：cosmic-ray 未安装时**不**回退到自研 AST 变异体（口径可比性
    纪律），返回 available=False + skipped=True + skip_reason="cosmic-ray
    not installed"——与 STVR 实证研究设计 §4.2"双口径分述"锁死。
    """
    if timeout_seconds is None:
        timeout_seconds = ULT_MUTATION_TIMEOUT_SECONDS
    cr_version = cosmic_ray_version()
    cr_hash = cosmic_ray_config_hash()
    t0 = time.time()

    def _skip(reason: str, available: bool = False, total: int = 0, killed: int = 0) -> dict[str, Any]:
        return {
            "available": available,
            "mutation_score": None,
            "mutants_total": total,
            "mutants_killed": killed,
            "skipped": True,
            "skip_reason": reason,
            "cosmic_ray_version": cr_version,
            "cosmic_ray_config_hash": cr_hash,
            "elapsed_seconds": round(time.time() - t0, 2),
        }

    if not (target_code or "").strip() or not (test_code or "").strip() or not (module_name or "").strip():
        return _skip("输入材料缺失（target_code / test_code / module_name 为空）")
    if max_mutants < 1:
        return _skip("max_mutants 无效（需正整数）")
    if not is_cosmic_ray_available():
        return _skip(
            "cosmic-ray not installed (pip install cosmic-ray; "
            "版本 + 配置哈希须入报告，见 docs/design/ult_bridge_plan.md §4.3)"
        )

    # cosmic-ray 可用：在隔离 tmp 树中物化被测模块 + 测试，走官方
    # `init → exec → dump` 工作流，解析 killed/total → mutation_score。
    # 全程确定性本地执行（零 LLM）；任一子命令失败 / 超时 / 无输出均
    # 保守返回 skipped（不误报 0 分，与 _m1_metrics 的 None 保守口径一致）。
    try:
        with tempfile.TemporaryDirectory(prefix="aitester_cr_") as tmpdir_str:
            # 2026-10-15 批次八：显式中转名（此前 `tmpdir = Path(tmpdir)` 经
            # str→Path 重赋值触发 mypy assignment/operator 报错——变更文件
            # 的 mypy 全绿纪律）。
            tmpdir = Path(tmpdir_str)
            (tmpdir / f"{module_name}.py").write_text(target_code, encoding="utf-8")
            test_file_name = f"test_{module_name}.py"
            (tmpdir / test_file_name).write_text(test_code, encoding="utf-8")
            config_path = tmpdir / "cosmic_ray_config.toml"
            session_path = tmpdir / "session.sqlite"

            # 变异体级并行（D3 加速，2026-10-29）：AITESTER_CR_WORKERS>0 时用
            # http distributor + worker 池（结果语义与 local 逐位一致——
            # session/变异体枚举/dump 解析共用，仅执行分发方式不同）。
            # 默认 0 = local 串行（历史口径不变）。
            worker_count = int(os.environ.get("AITESTER_CR_WORKERS", "0"))
            worker_procs: list[subprocess.Popen[Any]] = []
            try:
                if worker_count > 0:
                    worker_procs, worker_urls = _spawn_http_workers(worker_count, tmpdir)
                    if worker_procs:
                        _write_cosmic_ray_config_http(
                            config_path, module_name, test_file_name, timeout_seconds, worker_urls
                        )
                    else:
                        # worker 全部启动失败 → 回退 local（保守口径兜底）
                        _write_cosmic_ray_config(config_path, module_name, test_file_name, timeout_seconds)
                else:
                    _write_cosmic_ray_config(config_path, module_name, test_file_name, timeout_seconds)

                base = _cosmic_ray_base_cmd(http_mode=bool(worker_procs))

                def _run(args: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
                    from src.utils.process_utils import run_with_timeout

                    proc = run_with_timeout(
                        base + args,
                        cwd=str(tmpdir),
                        capture_output=True,
                        text=True,
                        timeout=timeout,
                    )
                    if proc.returncode != 0:
                        raise RuntimeError(
                            f"cosmic-ray {' '.join(args)} 退出码 {proc.returncode}: "
                            f"{(proc.stderr or proc.stdout).strip()[:400]}"
                        )
                    return proc

                _run(["init", str(config_path), str(session_path)], timeout=120)
                _trim_work_items(str(session_path), max_mutants)
                # 整体执行超时 = **trim 后实际条目数** × 单变异体超时 + 缓冲
                # （cosmic-ray 内部已有逐变异体 timeout，此处为兜底防整体挂死）。
                # 2026-10-15 批次八修复：原实现按 max_mutants × timeout + 60
                # 计算，全变异体哨兵（如 10**9）产出 ~1.2e11s 超时值，超出 C 层
                # PyTime_t（≈9.22e9s）⇒ subprocess 抛 OverflowError ⇒ 全变异体
                # 口径每任务以 skipped 失败（不可执行）。改按实测条目数计算，
                # 既精确又天然免疫哨兵溢出。
                exec_timeout = _count_work_items(str(session_path)) * timeout_seconds + 60
                _run(["exec", str(config_path), str(session_path)], timeout=exec_timeout)
                dump_stdout = _run(["dump", str(session_path)], timeout=60).stdout
            finally:
                # worker 池清理（所有退出路径——含 exec 异常/超时）
                for proc in worker_procs:
                    proc.terminate()
                for proc in worker_procs:
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()

        killed, total = _parse_cosmic_ray_dump(dump_stdout)
        if total <= 0:
            return _skip(
                "cosmic-ray 无有效变异体结果（目标代码无可变异点或全部 pending）",
                available=True,
            )
        return {
            "available": True,
            "mutation_score": round(killed / total, 6),
            "mutants_total": total,
            "mutants_killed": killed,
            "skipped": False,
            "skip_reason": "",
            "cosmic_ray_version": cr_version,
            "cosmic_ray_config_hash": cr_hash,
            "elapsed_seconds": round(time.time() - t0, 2),
        }
    except subprocess.TimeoutExpired as e:
        return _skip(f"cosmic-ray 子命令超时（>{e.timeout:.0f}s）：{e!r}", available=True)
    except Exception as e:
        return _skip(f"cosmic-ray 子命令异常：{e!r}", available=True)


def dry_run_plan(
    dataset: str = "ult",
    subset: str = "lite",
    task_limit: int | None = None,
    max_mutants: int = 10,
) -> dict[str, Any]:
    """生成 ULT cosmic-ray 口径 mutation-score 适配器的 dry-run 计划 JSON。

    本批次（零 LLM 成本）交付：只打印将要执行的命令与环境变量，
    **不**调用 LLM、**不**写结果。实跑批次（需用户授权 LLM 配额）
    才驱动 `run_benchmark.py` 的 `ENABLE_MUTATION_SCORING=true` +
    cosmic-ray 后端。

    Args:
        dataset: 数据集名（默认 "ult"，对应 ULT 官方 JSONL）。
        subset: 子集（默认 "lite"，即 ULT_Lite 200 任务）。
        task_limit: 任务数上限（None = 全量）。
        max_mutants: 每任务最多评估的变异体数量（默认 10）。

    Returns:
        计划 dict（可 json 落盘）：含 cosmic-ray 版本 / 配置哈希 /
        任务数 / max_mutants / 命令串（实跑批次执行前必须验证版本
        钉锁，跨批次可比性）。
    """
    return {
        "adapter": "experiments/ult_adapter.py",
        "caliber": "ULT cosmic-ray (docs/design/ult_bridge_plan.md §4.3)",
        "dataset": dataset,
        "subset": subset,
        "task_limit": task_limit,
        "max_mutants": max_mutants,
        "timeout_seconds": ULT_MUTATION_TIMEOUT_SECONDS,
        "operators": ULT_MUTANT_OPERATORS,
        "cosmic_ray_available": is_cosmic_ray_available(),
        "cosmic_ray_version": cosmic_ray_version(),
        "cosmic_ray_config_hash": cosmic_ray_config_hash(),
        "note": (
            "dry-run（本批次）不耗 LLM；实跑需 cosmic-ray 安装 + "
            "版本钉锁（requirements.lock）+ 用户授权 LLM 配额。"
            "cosmic-ray 未安装时 ult_mutation_score 保守 skipped（不回退自研 AST）。"
        ),
    }


def main(argv: list[str] | None = None) -> int:
    """CLI 入口（dry-run 默认，不实际执行 cosmic-ray 变异生成）。"""
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", default="ult", help="数据集名（默认 ult）")
    ap.add_argument("--subset", default="lite", help="子集（默认 lite，即 ULT_Lite 200 任务）")
    ap.add_argument("--task-limit", type=int, default=None, help="任务数上限（None = 全量）")
    ap.add_argument("--max-mutants", type=int, default=10, help="每任务最多评估的变异体数量")
    ap.add_argument(
        "--execute",
        action="store_true",
        help="实际调用 cosmic-ray 子命令（需安装 + 用户授权 LLM 配额）；默认 dry-run 只生成计划 JSON",
    )
    args = ap.parse_args(argv)

    plan = dry_run_plan(
        dataset=args.dataset,
        subset=args.subset,
        task_limit=args.task_limit,
        max_mutants=args.max_mutants,
    )
    print(json.dumps(plan, indent=2, ensure_ascii=False))
    if args.execute:
        print("\n[ult_adapter] ⚠️ --execute 已指定：将驱动 cosmic-ray 实跑，需用户授权 LLM 配额。")
        print("[ult_adapter] 本批次为骨架（设计稿），实际 cosmic-ray 子命令调用待后续批次接线。")
    else:
        print("\n[ult_adapter] dry-run 完成：已生成 ULT cosmic-ray 口径 mutation-score 计划（零 LLM 成本）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
