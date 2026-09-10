"""
src/graph/token_usage.py 单元测试（P0-2：token 消耗统计）。

覆盖：
- record/get/reset 的累计语义
- reset 返回重置前快照
- 线程隔离（工作线程累计不影响主线程）
- global_usage 跨线程聚合
- as_dict 可 JSON 序列化
"""

import json
import threading

import src.graph.token_usage as token_usage
from src.graph.token_usage import TokenUsage, get_usage, global_usage, record_usage, reset


class TestRecordAndGet:
    """单线程累计语义。"""

    def setup_method(self):
        reset()

    def test_record_accumulates(self):
        record_usage(100, 50, model="m1")
        record_usage(30, 10, model="m1")
        usage = get_usage()
        assert usage.input_tokens == 130
        assert usage.output_tokens == 60
        assert usage.total_tokens == 190
        assert usage.llm_calls == 2
        assert usage.by_model == {"m1": 190}

    def test_get_is_snapshot(self):
        record_usage(10, 5)
        before = get_usage()
        record_usage(1, 1)
        # get_usage 返回的是同一累计器的引用（快照语义：重置前读取多次一致）
        assert before.total_tokens == get_usage().total_tokens

    def test_reset_returns_previous(self):
        record_usage(10, 5)
        previous = reset()
        assert previous.total_tokens == 15
        assert get_usage().total_tokens == 0
        assert get_usage().llm_calls == 0


class TestThreadIsolation:
    """线程隔离：--parallel 模式下每任务独立统计。"""

    def test_worker_thread_independent(self):
        reset()
        record_usage(10, 5, model="main")

        def worker():
            token_usage.reset()
            token_usage.record_usage(100, 100, model="worker")
            captured.append(token_usage.get_usage().as_dict())

        captured: list[dict] = []
        t = threading.Thread(target=worker)
        t.start()
        t.join()

        # 主线程累计不受工作线程影响
        main_usage = get_usage()
        assert main_usage.input_tokens == 10
        assert main_usage.by_model == {"main": 15}
        # 工作线程累计正确
        assert captured[0]["total_tokens"] == 200
        assert captured[0]["llm_calls"] == 1


class TestGlobalUsage:
    """跨线程聚合。"""

    def test_global_aggregates_threads(self):
        reset()
        record_usage(10, 5)

        def worker():
            token_usage.reset()
            token_usage.record_usage(7, 3)

        t = threading.Thread(target=worker)
        t.start()
        t.join()

        total = global_usage()
        assert total.input_tokens == 17
        assert total.output_tokens == 8
        assert total.llm_calls == 2

    def test_as_dict_json_serializable(self):
        usage = TokenUsage(input_tokens=1, output_tokens=2, total_tokens=3, llm_calls=1, by_model={"m": 3})
        assert json.loads(json.dumps(usage.as_dict()))["total_tokens"] == 3


class TestRecordUsageErrors:
    """token 统计故障不影响主流程（_record_response_usage 容错）。"""

    def test_none_usage_noop(self):
        from src.agents.base_agent import _record_response_usage

        reset()
        _record_response_usage(None, "m")
        assert get_usage().llm_calls == 0

    def test_dict_usage_metadata(self):
        from src.agents.base_agent import _record_response_usage

        reset()
        _record_response_usage({"input_tokens": 10, "output_tokens": 5}, "m1")
        usage = get_usage()
        assert usage.input_tokens == 10
        assert usage.output_tokens == 5

    def test_openai_style_usage_object(self):
        from types import SimpleNamespace

        from src.agents.base_agent import _record_response_usage

        reset()
        usage_obj = SimpleNamespace(prompt_tokens=12, completion_tokens=6)
        _record_response_usage(usage_obj, "m2")
        usage = get_usage()
        assert usage.input_tokens == 12
        assert usage.output_tokens == 6
