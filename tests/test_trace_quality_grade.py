"""experiments/trace_quality_grade.py 单元测试（轨迹质量分级 Lucky/Solid/Ideal）。"""

from experiments.trace_quality_grade import _lucky_signal, grade_trace


def _task_start() -> dict:
    return {"event": "task_start"}


def _executor(passed: bool) -> dict:
    return {"event": "node", "node": "executor", "output": {"passed": passed}}


def _should_debug(decision: str, reason: str = "") -> dict:
    out = {"decision": decision}
    if reason:
        out["output"] = {"reason": reason}
    return {"event": "node", "node": "_should_debug", **out}


def _task_end(passed: bool) -> dict:
    return {"event": "task_end", "passed": passed}


class TestGradeTrace:
    def test_ideal_single_pass(self):
        events = [_task_start(), _executor(True), _task_end(True)]
        assert grade_trace(events) == "ideal"

    def test_ideal_plain_llm_no_router(self):
        # plain_llm 臂：无 _should_debug 节点，单次执行通过
        events = [_task_start(), _executor(True), _task_end(True)]
        assert grade_trace(events) == "ideal"

    def test_solid_debug_loop(self):
        events = [
            _task_start(),
            _executor(False),
            _should_debug("debug"),
            _executor(True),
            _should_debug("done"),
            _task_end(True),
        ]
        assert grade_trace(events) == "solid"

    def test_lucky_repeated_retry(self):
        # 3 次 executor 才通过（反复试错）
        events = [
            _task_start(),
            _executor(False),
            _should_debug("debug"),
            _executor(False),
            _should_debug("debug"),
            _executor(True),
            _task_end(True),
        ]
        assert grade_trace(events) == "lucky"
        assert _lucky_signal(events) == "repeated_retry"

    def test_lucky_regen_test_gen(self):
        # 测试生成错误类再生成（抹红/弱化）
        events = [
            _task_start(),
            _executor(False),
            _should_debug("regenerate", reason="test_gen_diagnosis_early"),
            _executor(True),
            _task_end(True),
        ]
        assert grade_trace(events) == "lucky"
        assert _lucky_signal(events) == "regen_test_gen"

    def test_failed(self):
        events = [_task_start(), _executor(False), _task_end(False)]
        assert grade_trace(events) == "failed"

    def test_failed_no_task_end(self):
        events = [_task_start(), _executor(True)]
        assert grade_trace(events) == "failed"  # 无 task_end，保守判 failed

    def test_detection_first_regen_not_lucky(self):
        # 检出优先再生成（合理协议信号）→ 不算 Lucky
        events = [
            _task_start(),
            _executor(True),
            _should_debug("regenerate", reason="detection_first_all_green"),
            _executor(False),
            _task_end(True),
        ]
        assert grade_trace(events) == "solid"
