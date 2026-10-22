"""BO 轮改前/改后探针（只读，零 LLM，$0）：raw 落盘面的读侧折叠与开关态可复核性。

三面测量：
  A 开关态可复核性——`--save-state` 的值是否进了任何归档工件；raw 目录留存面；
    `experiments/results/**` 的 git 跟踪态（决定"归档"到底在不在版本库里）。
  B 根因折叠复放——真实批次上 `analyze(with raw)` vs `analyze(without raw)`，
    数判定翻转的失败任务（`cross_file_root_cause` 的文档口径 vs 代码行为）；
    B2 再分一级：state 件在场但 `cross_file_deps` 键不存在的"键级缺席"。
  C 定位命中率折叠——四个归档 A/B 批次八臂**现场复算 vs 归档读数**（历史读数
    影响面），再展示四种"没测到"腿与"实测 0%"是否同形（改前四腿全塌 0.0，
    改后由 grade 分档）；C2 普查归档件里 focus 键的形态，用来证明口径改动
    不动历史读数。
  D compare_failures 读侧——单臂缺失是否披露、raw JSON 损坏是否抛穿、合法空
    产物 `{}` 与"件不存在"是否同形。

改前读数已登记在本轮手册（docs/reviews/ 的 BO 分册）：B 段 29 例失败里 14 例被
折成 DEP_GRAPH_INCOMPLETE、C 段四条"没测到"腿全塌成 0.0、D 段单臂缺失静默且
损坏件抛穿。本脚本本身只读不改，可随时重跑；它打印的是**当前代码状态**的读数，
所以改动前后各跑一次、把两侧读数分别登记，才是可复核的做法。

用法：.venv/bin/python scripts/tools/bo_raw_readside_fold_probe.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.compare_failures import build_report, load_state_artifact_status  # noqa: E402
from experiments.cross_file_root_cause import _load_results, analyze  # noqa: E402
from experiments.position_aware_ab import _locate_accuracy, _locate_stats, _locate_text  # noqa: E402

RESULTS = ROOT / "experiments" / "results"


def _iter_json_keys(obj: Any, acc: set[str]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            acc.add(str(k))
            _iter_json_keys(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            _iter_json_keys(v, acc)


def probe_a_switch_archivability() -> None:
    print("== A 开关态可复核性 ==")
    batch_jsons = sorted(RESULTS.rglob("benchmark_*.json"))
    raw_dirs = sorted(p for p in RESULTS.rglob("raw") if p.is_dir())
    hits = 0
    switch_keys: set[str] = set()
    for p in batch_jsons:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        keys: set[str] = set()
        _iter_json_keys(data, keys)
        if any("save_state" in k or "save-state" in k for k in keys):
            hits += 1
        switch_keys.update(k for k in keys if "raw" in k.lower() or "save" in k.lower())
    print(f"  批次 JSON={len(batch_jsons)} 份，含 save_state 类键的={hits} 份")
    print(f"  raw/ 目录={len(raw_dirs)} 个；归档键面里含 raw/save 字样的键={sorted(switch_keys)}")
    # provenance 是"批次可复核性"的正式面：直接读一份真实批次的 summary 顶层键
    sample = batch_jsons[0]
    top = sorted(json.loads(sample.read_text(encoding="utf-8")).keys())
    prov = sorted(json.loads(sample.read_text(encoding="utf-8")).get("provenance", {}))
    print(f"  样本 {sample.name}\n    summary 顶层键={top}")
    print(f"    provenance 键含 save_state？{'save_state' in prov}；provenance 键={prov}")
    r = subprocess.run(
        ["git", "check-ignore", "-v", "experiments/results/pa_l25h_n40/raw"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    print(f"  raw 路径命中忽略规则：{r.stdout.strip() or '未命中'}")
    tracked = subprocess.run(
        ["git", "ls-files", "experiments/results"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.splitlines()
    raw_files = [p for p in tracked if "/raw/" in p]
    owners = sorted({p.split("/raw/")[0] for p in raw_files})
    print(f"  raw 文件入库={len(raw_files)} 份，覆盖 {len(owners)} 个批次目录（磁盘上 raw/ 目录 {len(raw_dirs)} 个）")
    print(f"    入库归属={owners}")
    print("  ⇒ 落盘面是否随归档留存是**逐批次**事实：既不在 summary 里，也不能由忽略规则推出")


def probe_b_root_cause_fold() -> tuple[int, int, int]:
    print("\n== B 根因折叠复放（真实批次：带 raw vs 不带 raw） ==")
    n_arms = n_failed = n_flip = n_level1_flip = 0
    last_w: dict[str, Any] | None = None
    arms = PROBE_B_ARMS
    for batch, arm in arms:
        d = RESULTS / batch / arm
        js = sorted(d.glob("benchmark_*.json")) if d.is_dir() else []
        if not js:
            continue
        details = _load_results(str(js[0]))
        raw = d / "raw"
        w = analyze(details, str(raw) if raw.is_dir() else None, difficulty="")
        n = analyze(details, None, difficulty="")
        flips = [
            (a["task_id"], a["root_cause"], b["root_cause"], a["dep_edges"], b["dep_edges"])
            for a, b in zip(w["details"], n["details"], strict=False)
            if a["root_cause"] != b["root_cause"]
        ]
        n_arms += 1
        n_failed += w["total_failed"]
        n_flip += len(flips)
        last_w = w
        if batch.startswith("cross_file_ab_level1"):
            n_level1_flip += len(flips)
        print(
            f"  {batch}/{arm}: 失败={w['total_failed']} 带raw={w['root_cause_distribution']} 不带={n['root_cause_distribution']}"
        )
        for t, cw, cn, de, dne in flips:
            print(f"      翻转 {t}: 带 raw={cw}(dep_edges={de}) → 不带 raw={cn}(dep_edges={dne})")
    print(f"  == 汇总：{n_arms} 臂 / 失败 {n_failed} 例 / 判定翻转 {n_flip} 例 ==")
    print(f"  对照：level1（单文件，num_files=1）翻转 {n_level1_flip} 例 ⇒ 折叠只在多文件腿上开")
    if last_w is None:
        print("  覆盖度自证：本轮无臂可测")
    elif "raw_coverage" in last_w:
        print(
            "  覆盖度自证：analyze() 已带 raw_coverage / rule_evidence / unreachable_rules"
            f"（样例 by_status={last_w['raw_coverage']['by_status']}；"
            f"零证据档={last_w['unreachable_rules']}）"
        )
    else:
        print("  analyze() 返回值里没有任何 raw 覆盖度字段 ⇒ 报告自身不可自证用了多少 raw")
    return n_arms, n_failed, n_flip


PROBE_B_ARMS = (
    ("cross_file_ab_level3", "cross_file_on"),
    ("cross_file_ab_level3", "cross_file_off"),
    ("cross_file_ab_l35_bi_small", "cross_file_on"),
    ("cross_file_ab_l35_bi_small", "cross_file_off"),
    ("cross_file_ab_l3_bi_small", "cross_file_on"),
    ("cf_bi_l35_n40", "cross_file_on"),
    ("cf_bi_l35_n40", "cross_file_off"),
    ("cross_file_ab_level1", "cross_file_on"),
    ("cross_file_ab_level1", "cross_file_off"),
)


def probe_b2_state_key_presence() -> None:
    """两级缺席分层：整份 raw 件不可用（probe B）vs 单键不可用（本探针）。

    `cross_file_root_cause` 的 `len(deps) < num_files - 1` 判定读的是
    `(state or {}).get("cross_file_deps") or []`——state 在场但键缺席时同样
    得 0 条边。`run_benchmark.py:901` 之前 raw 白名单不含这两键，故旧批次
    的键缺席也是"工件没写"而非"依赖图真的空"。
    """
    print("\n== B2 键级缺席普查（带 raw 臂：件在但 cross_file_deps 键是否在场） ==")
    for batch, arm in PROBE_B_ARMS:
        raw = RESULTS / batch / arm / "raw"
        d = RESULTS / batch / arm
        js = sorted(d.glob("benchmark_*.json")) if d.is_dir() else []
        if not js:
            continue
        if not raw.is_dir():
            print(f"  {batch}/{arm}: raw 目录缺席（整件级缺席，见 probe B 翻转腿）")
            continue
        details = _load_results(str(js[0]))
        failed = [r for r in details if not r.get("passed")]
        census: dict[str, int] = {}
        for r in failed:
            p = raw / str(r.get("task_id", "")) / "aitester.json"
            if not p.exists():
                key = "件缺席"
            else:
                try:
                    st = json.loads(p.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    key = "件不可读"
                else:
                    key = "键缺席" if "cross_file_deps" not in st else "键在场"
            census[key] = census.get(key, 0) + 1
        print(f"  {batch}/{arm}: 失败 {len(failed)} 例 键级普查={census}")


def _write_state(out_dir: Path, task_id: str, payload: dict[str, Any]) -> None:
    p = out_dir / "raw" / task_id
    p.mkdir(parents=True, exist_ok=True)
    (p / "aitester.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def probe_c_locate_fold() -> None:
    print("\n== C 定位命中率：归档读数影响面 + 折叠腿分档 ==")
    for b in ("pa_l25h_n40_g8batch", "position_aware_synthetic", "pa_l25h_n40", "position_aware_ab_l25_small"):
        root = RESULTS / b
        j = json.loads((root / "position_aware_ab_raw.json").read_text(encoding="utf-8"))
        line = [f"  {b}: 归档 on={j['on']['locate_accuracy_pct']} off={j['off']['locate_accuracy_pct']}"]
        for arm, key in (("position_aware_on", "on"), ("position_aware_off", "off")):
            d = root / arm
            js = sorted(d.glob("benchmark_*.json"))
            if not js:
                line.append(f"    {arm}: 无批次 JSON")
                continue
            summary = json.loads(js[0].read_text(encoding="utf-8"))
            live = _locate_accuracy(str(d), summary)
            ntask = len([p for p in (d / "raw").iterdir() if p.is_dir()]) if (d / "raw").is_dir() else 0
            line.append(f"    {arm}: 现场复算={live} 归档={j[key]['locate_accuracy_pct']} raw task_dirs={ntask}")
        print("\n".join(line))
    print("  ⇒ 八臂现场复算与归档逐位相同：本轮读侧改动不动历史读数（raw 在跑批时确已落盘）")

    print("\n  -- 折叠腿 vs '实测 0%'（合成临时目录） --")
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        summary = {"results": {"aitester": {"details": [{"task_id": "task_1", "iterations": 2, "patch": "x"}]}}}
        # 腿 1：raw 目录不存在
        absent = _locate_stats(str(tdp / "no_such"), summary)
        # 腿 2：raw 存在但任务目录缺失（逐臂 continue ⇒ 分母静默收缩）
        d2 = tdp / "arm2"
        (d2 / "raw").mkdir(parents=True)
        partial = _locate_stats(str(d2), summary)
        # 腿 3：raw 在、文件在、定位真未命中 ⇒ 实测 0%
        d3 = tdp / "arm3"
        _write_state(d3, "task_1", {"position_aware_focus": {"focused": False, "function_name": "other"}})
        measured = _locate_stats(str(d3), summary)
        # 腿 4：raw 在、文件在、position_aware_focus 键缺失 ⇒ 改前计为未命中并计入分母
        d4 = tdp / "arm4"
        _write_state(d4, "task_1", {"task_metadata": {"suggested_function": "divide"}})
        nokey = _locate_stats(str(d4), summary)
        for label, st in (
            ("腿1 raw 目录缺席", absent),
            ("腿2 raw 在但任务件缺", partial),
            ("腿3 实测定位全未命中", measured),
            ("腿4 focus 键缺", nokey),
        ):
            print(f"    {label}: 数值={st['accuracy_pct']} 分档={st['grade']} 渲染={_locate_text(st)}")
        same_value = (
            len({absent["accuracy_pct"], partial["accuracy_pct"], measured["accuracy_pct"], nokey["accuracy_pct"]}) == 1
        )
        same_text = len({_locate_text(s) for s in (absent, partial, measured, nokey)}) == 1
        print(f"    四腿数值同形={same_value}（改前为 True：全塌 0.0）；四腿文本同形={same_text}")


def probe_c2_focus_key_census() -> None:
    """归档 PA 批次逐臂普查环节件里 position_aware_focus 的形态。

    决定"改分母口径（键缺席不再计为未命中）会不会让历史读数在重放时漂移"：
    只有"件在且键缺且该任务确已进入修复"那一部分才会移动分母。
    """
    print("\n== C2 position_aware_focus 形态普查（决定分母口径改动的影响面） ==")
    for b in ("pa_l25h_n40_g8batch", "position_aware_synthetic", "pa_l25h_n40", "position_aware_ab_l25_small"):
        for arm in ("position_aware_on", "position_aware_off"):
            d = RESULTS / b / arm
            js = sorted(d.glob("benchmark_*.json"))
            if not js:
                continue
            details = (json.loads(js[0].read_text(encoding="utf-8")).get("results") or {}).get("aitester", {}).get(
                "details"
            ) or []
            census: dict[str, int] = {}
            for row in details:
                p = d / "raw" / str(row.get("task_id", "")) / "aitester.json"
                if not p.exists():
                    key = "件缺席"
                else:
                    try:
                        st = json.loads(p.read_text(encoding="utf-8"))
                    except (json.JSONDecodeError, OSError):
                        key = "件不可读"
                    else:
                        focus = st.get("position_aware_focus")
                        if "position_aware_focus" not in st:
                            key = "键不存在"
                        elif not focus:
                            key = "键在且为空"
                        else:
                            key = "键在且有内容"
                census[key] = census.get(key, 0) + 1
            print(f"  {b}/{arm}: details={len(details)} 形态={census}")


def probe_d_compare_failures() -> None:
    print("\n== D compare_failures 读侧 ==")
    row = {
        "task_id": "t1",
        "error_category": "assertion",
        "patch": "x" * 40,
        "iterations": 2,
        "test_passed": False,
        "token_usage": {"total_tokens": 1},
    }
    inverted = [{"task_id": "t1", "full": dict(row), "base": dict(row, test_passed=True)}]
    single_marker = "环节级工件不可用"
    both_marker = "环节级产物缺失"
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        # 单臂缺失（full 有 / base 无）
        _write_state(tdp, "t1", {"test_plan": {"n": 1}, "generated_test": "def t():\n  pass", "patch": "p" * 40})
        (tdp / "raw" / "t1" / "plain_llm.json").write_text(
            json.dumps({"generated_test": "def b():\n  pass"}), encoding="utf-8"
        )
        os.remove(tdp / "raw" / "t1" / "plain_llm.json")
        single = build_report(inverted, "aitester", "plain_llm", str(tdp / "raw"))
        both = build_report(inverted, "aitester", "plain_llm", None)
        print(
            f"    单臂缺失：含 {single_marker}={single_marker in single}；含 {both_marker}={both_marker in single}"
            "（改前两者皆 False ⇒ 只有两臂都缺才披露）"
        )
        print(f"    两臂皆缺（未给 raw）：含 {both_marker}={both_marker in both}；含缺席形态={'缺席形态' in both}")
        # raw 存在但损坏
        _write_state(tdp, "t1", {})
        (tdp / "raw" / "t1" / "aitester.json").write_text("{ not json", encoding="utf-8")
        (tdp / "raw" / "t1" / "plain_llm.json").write_text("{}", encoding="utf-8")
        try:
            art, status = load_state_artifact_status(str(tdp / "raw"), "t1", "aitester")
            print(f"    损坏 JSON：不抛穿 ⇒ artifact={art} status={status}")
        except Exception as exc:
            print(f"    损坏 JSON：抛穿 {type(exc).__name__} ⇒ 整份报告中断")
        corrupt_report = build_report(inverted, "aitester", "plain_llm", str(tdp / "raw"))
        print(f"    损坏 JSON 进报告：含不可读披露={'环节件不可读' in corrupt_report}")
        # 合法空产物 {}（plain_llm 侧）：可读但零字段，不得与"件不存在"同形
        print(f"    空产物渲染：plain_llm 环节产物块={'**plain_llm 环节产物**' in corrupt_report}")


def main() -> int:
    print(f"ROOT={ROOT}")
    probe_a_switch_archivability()
    probe_b_root_cause_fold()
    probe_b2_state_key_presence()
    probe_c_locate_fold()
    probe_c2_focus_key_census()
    probe_d_compare_failures()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
