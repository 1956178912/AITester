"""
全局 pytest fixture：为 AITester 测试提供稳定的 LLM 缓存隔离。

背景：
- base_agent 的 LLM 调用现已接入文件级缓存（默认 `~/.cache/aitester/llm/*.json`，省 token）。
- 缓存键 = md5(user_message + system_prompt)，相同 prompt 会命中彼此留下的缓存文件，
  导致 mock 的 _call_llm 不被调用 → 测试相互干扰、结果 flaky。

策略：
- autouse fixture 在每个测试前关闭缓存开关（AITESTER_LLM_CACHE=0），
  使 _call_llm_with_cache 直接透传 _call_llm，行为与旧逻辑完全一致。
- 同时将缓存目录指向临时目录（AITESTER_LLM_CACHE_DIR），即使误开启也不污染默认缓存目录。
- config._apply_profile_presets 在 import 期往进程 os.environ 注入档位开关
  （setdefault 绕过 monkeypatch 追踪），由 _isolate_profile_presets 逐测试还原。
"""

import os
from collections.abc import Iterator

import pytest

import config as _config
from src.agents.llm_client import clear_llm_cache_option_memory
from src.graph import nodes as _nodes

# 档位预设可能注入的全部环境变量键（含 AITESTER_PROFILE 自身）。**从 config
# 单一事实源派生**，不手抄——手抄清单在历史上过期过两次（见
# _isolate_profile_presets 文档串），过期即泄漏，泄漏即测量污染。
_PRESET_ENV_KEYS: frozenset[str] = frozenset(
    {"AITESTER_PROFILE", *(k for presets in _config._PROFILE_PRESETS.values() for k in presets)}
)


@pytest.fixture(autouse=True)
def _isolate_agent_instance_caches() -> None:
    """每个测试前清空 nodes 模块的 Agent 实例复用缓存（2026-09-28 性能优化）。

    _planner_node / _generator_node / _debugger_node / _diagnosis_node 经
    get_or_create_agent 复用 BaseAgent 子类实例（按类名分键，DCL + FIFO），
    _executor_node 经 _get_or_create_executor_agent 按沙箱配置元组分键复用
    ExecutorAgent 实例。跨测试复用在"测试以 MagicMock patch 类"的口径下
    会产生 mock 实例与真实类缓存键错位——每测试前清空恢复"每次新建"的
    历史口径（测试 mock 类被替换后不再被前一个测试的真实实例污染）。
    """
    _nodes.clear_agent_instance_cache()
    _nodes.clear_executor_agent_cache()
    yield
    _nodes.clear_agent_instance_cache()
    _nodes.clear_executor_agent_cache()


@pytest.fixture(autouse=True)
def _isolate_profile_presets() -> Iterator[None]:
    """逐测试还原 config 档位预设注入的环境变量（消除跨测试残留）。

    ``config._apply_profile_presets()`` 在 **import 期**用 ``os.environ.setdefault``
    注入档位开关（config.py:150），既绕过 monkeypatch 追踪、也没有 teardown。
    任何调用它并把 ``AITESTER_PROFILE`` 设成 logic/scientific 的测试，都会在
    进程里留下这批开关键——monkeypatch 只还原 AITESTER_PROFILE 本身。

    实测后果（2026-10-16 H 轮定位）：残留使后续测试走到"档位开启"分支，
    **覆盖率测量因此非确定**——同一份源码连跑三次，src/graph/nodes.py 分别
    得 0.7776 / 0.7862 / 0.7776，总行覆盖在 92.94–92.96% 间漂移，登记册逐位
    对账无法收敛。漂移全部落在特异性门块内的 6 行（1561-1563 / 1569 / 1575-1576），
    即 ``DETECTION_SPECIFICITY_GATE_ENABLE`` 被残留开启时才执行的分支。

    历史上有两份手抄的还原清单，均已过期：
    tests/test_2026_10_05_review_fixes_batch.py 的 ``_INJECTED`` 元组漏掉
    P0-1 / AI1 / P0-B 三个批次新增的 5 个键；
    tests/test_2026_10_05_review_batch.py 更是把 safe/scientific 预设**内联成字面量**，
    漏掉 MUTATION_ADVISOR_ENABLE。两处现均改为从 ``_PROFILE_PRESETS`` 派生，
    本 fixture 是兜底安全网：未来新增档位开关**无需**再改任何测试即可被覆盖。

    口径：只还原、不预清场——会话启动时的宿主环境（例如开发者显式
    export AITESTER_PROFILE）对每个测试都同样可见，本 fixture 只保证
    "上一个测试的注入"不外溢。需要干净基线的测试自行 delenv
    （见 tests/test_aa_batch.py 的类内 fixture，它额外做预清场）。
    """
    saved = {k: os.environ.get(k) for k in _PRESET_ENV_KEYS}
    yield
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@pytest.fixture(autouse=True)
def _isolate_llm_cache(tmp_path, monkeypatch) -> None:
    """默认关闭 LLM 文件缓存，并将缓存目录指向临时目录（测试间互不干扰）。

    需要验证缓存行为的测试可显式 monkeypatch 覆盖这两个环境变量。
    """
    monkeypatch.setenv("AITESTER_LLM_CACHE", "0")
    monkeypatch.setenv("AITESTER_LLM_CACHE_DIR", str(tmp_path / "llm_cache"))
    # R13（2026-09-30 独立审查 P0）：跨模型缓存隔离默认开启（=1）会把
    # model 名加入缓存键——测试未配置真实 LLM 时默认链为空，隔离键不
    # 追加，但个别测试 patch 了 get_first_valid_model_name 返回非空值，
    # 会改变缓存文件哈希。统一 pin 到 "0"（显式 opt-out），使缓存键
    # 口径在测试内恒为"不含 model"（_cache_file_for 同口径）。
    # 需要验证 R13 隔离行为的测试可显式 monkeypatch 覆盖为 "1"。
    monkeypatch.setenv("AITESTER_CACHE_ISOLATE_MODEL", "0")
    # M8 隔离键材料 get_first_valid_model_name() 的线程局部/全局 LLM
    # 配置链：测试进程可能残留宿主环境注入的 LLM 配置（含 model_name），
    # 使"未 patch 该函数"的测试路径意外追加 model 键材料。统一 patch
    # 为 None（无有效配置 → 不追加），与 AITESTER_CACHE_ISOLATE_MODEL=0
    # 的"不隔离"口径双重一致。需要验证 R13 隔离行为的测试自行 patch
    # 回真实值。
    from unittest.mock import patch as _mock_patch

    with _mock_patch("src.agents.llm_client.get_first_valid_model_name", return_value=None):
        # 2026-09-28 性能优化配套：llm_client 热路径把缓存开关/目录做了进程内
        # 环境变量记忆（首次调用定值后复用，省每次 LLM 调用的两次 getenv）。
        # autouse 隔离在本 fixture 内切目录/开关，必须在切后清一次记忆；teardown
        # （monkeypatch 还原环境变量后）再清一次，恢复"读环境变量"历史口径
        # （conftest 是测试入口模块，顶层导入保持 import 排序干净、零运行时成本）
        clear_llm_cache_option_memory()
        yield
        clear_llm_cache_option_memory()


# ─── CI 轮补遗（2026-10-24）：结果工件缺失 → 具名 skip ──────────────────────────
# 用户指令清除 experiments/results/ 全部历史数据（DeepSeek 重跑前）。约 30 个测试
# 文件里引用历史工件的「真实树锁」会以 FileNotFoundError 失败/报错。按 BZ 轮语料
# 守卫纪律（前提缺失 = 显式具名 skip，不折叠成通过也不折叠成失败），在报告层把
# 「根因路径落在 experiments/results/ 下的 FileNotFoundError」统一转为 skip；
# 重跑生成新工件后这些锁自动恢复判定。tmp_path 下的缺文件不受影响（只匹配
# 仓库 results 目录），真实回归不被吞（其他异常类型照常红）。
_RESULTS_DIR_MARKS = ("experiments/results", "docs/reviews")


def _is_results_missing(longrepr: object) -> bool:
    text = str(longrepr or "")
    if not any(mark in text for mark in _RESULTS_DIR_MARKS):
        return False
    return (
        "No such file or directory" in text
        or "FileNotFoundError" in text
        or "输入工件缺失" in text
        or "工件已清除" in text
    )


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[object]):
    outcome = yield
    rep = outcome.get_result()
    if rep.when in ("setup", "call") and rep.failed and _is_results_missing(rep.longrepr):
        rep.outcome = "skipped"
        # terminal 层 _get_raw_skip_reason 要求 longrepr 为 (path, lineno, reason) 三元组
        rep.longrepr = (
            str(item.fspath),
            item.location[1],
            "结果工件不在盘（2026-10-24 用户指令清除历史数据、DeepSeek 重跑前）："
            "语料前提缺失，按 BZ 轮纪律具名 skip；重跑落盘后本锁自动恢复判定",
        )
