"""채점 분리 — score.py 를 고치지 않고 감싼다. (C 소유 · workplan C-2)

    .venv310\\Scripts\\python.exe -m eval.breakdown {run_id}

`eval/score.py` 는 A 소유이고 이 저장소는 남의 파일을 고치지 않는다. 그래서 그 공개
함수(`load_truth` · `perception_accuracy` · …)를 그대로 불러 두 가지를 덧붙인다.

1. **구조적 실패 분리** — 합이 1인 어떤 배분으로도 못 지키는 스텝을 따로 센다.
   `Σ need = demand_pressure` 이므로 압력이 1.0 을 넘으면 재배분으로는 불가능하고
   조달만이 해법이다 (observe/server.py 도구 설명). 이 실패를 정책·판단 탓으로 세면
   조달이 필요했던 상황에서 배분만 벌을 받는다. **제외가 아니라 분리**다 — 조달 판단을
   평가하는 데는 오히려 이 스텝들이 핵심이다.

   ⚠ 시점: SLA 는 `step()` 뒤의 관측 obs_{t+1} 로 채점된다(⑤ report_outcome). 그러니
   "그 위반을 배분으로 피할 수 있었나"는 **obs_{t+1} 의 압력**으로 판정해야 한다.
   결정 레코드의 `observation` 은 obs_t 라 한 스텝 어긋난다 — rationale/audit.md 가
   `violations` 로 SLA 를 세면 안 된다고 경고한 것과 같은 함정이다. 다음 스텝 레코드의
   관측을 쓴다. 마지막 스텝은 다음 관측이 없어 `unknown` 으로 둔다.

2. **심판 오류 스텝 제외** — 오케스트레이터에서 LLM 이 절차를 어긴 스텝(심판 severity
   `error`: 기록 없음 · 전진 없음 · 보고 없음 …)은 채점 데이터 자체가 왜곡된다
   (agent/orchestrator/referee.py 머리말). 그 스텝을 `perception_accuracy` ·
   `escalation_precision` 에서 빼고, **뺀 수를 함께 보고한다.** 조용히 빼면 절차를 많이
   어긴 실행이 오히려 깨끗해 보인다. 고정 루프는 심판 기록이 없으므로 제외 0.

정답 파일을 읽으므로 **에이전트가 끝난 뒤에만** 돈다 (flow/forbidden.md).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval import score  # noqa: E402  (A 소유 — 읽기만 한다)
from srm_mcp.common import paths  # noqa: E402

FEASIBLE_PRESSURE = 1.0   # Σ need = 1 이 배분 총량. 넘으면 재배분으로 불가능


# ── 로드 ───────────────────────────────────────────────────────
def load_referee(run_id: str) -> list[dict]:
    """오케스트레이터 실행만 있다. 고정 루프는 파이썬이 순서를 보장해 위반이 정의상 0."""
    path = paths.run_dir(run_id) / "orchestrator" / "referee.jsonl"
    if not path.is_file():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _decision_records(decisions: list[dict]) -> dict[int, dict]:
    return {int(r["step"]): r for r in decisions if r.get("kind") == "decision"}


# ── 1. 구조적 실패 ─────────────────────────────────────────────
def structural_split(decisions: list[dict]) -> dict:
    """SLA 위반을 배분으로 피할 수 있었던 것 / 없던 것 / 판정 불가로 나눈다."""
    by_step = _decision_records(decisions)
    out = {"scored": 0, "violations": 0,
           "avoidable": 0, "structural": 0, "unknown": 0,
           "structural_steps": [], "pressure_source": "obs_{t+1}"}

    for step in sorted(by_step):
        rec = by_step[step]
        outcome = rec.get("outcome")
        if not outcome:                      # 마지막 결정 — 채점될 다음 관측이 없다
            continue
        out["scored"] += 1
        if outcome.get("sla_met"):
            continue
        out["violations"] += 1

        nxt = by_step.get(step + 1)
        if nxt is None or "observation" not in nxt:
            out["unknown"] += 1
            continue
        pressure = float(nxt["observation"].get("demand_pressure", 0.0))
        if pressure > FEASIBLE_PRESSURE:
            out["structural"] += 1
            out["structural_steps"].append(step)
        else:
            out["avoidable"] += 1
    return out


# ── 2. 심판 오류 스텝 제외 ─────────────────────────────────────
def referee_error_steps(referee_rows: list[dict]) -> set[int]:
    return {int(r["step"]) for r in referee_rows
            if any(v.get("severity") == "error" for v in (r.get("violations") or []))}


def scored_without(run_id: str, excluded: set[int]) -> dict:
    """score.py 의 두 지표를 excluded 스텝을 뺀 결정만으로 다시 계산한다."""
    truth_rows = score.load_truth(run_id)
    truth_by_step = {int(r["step"]): score.truth_situation(r) for r in truth_rows}
    transitions = score.transition_steps(truth_rows)
    decisions = [r for r in score.load_decisions(run_id)["decisions"]
                 if int(r["step"]) not in excluded]
    return {
        "perception_accuracy": score.perception_accuracy(
            decisions, truth_by_step, transitions),
        "escalation_precision": score.escalation_precision(decisions, truth_by_step),
    }


# ── 실행 ───────────────────────────────────────────────────────
def breakdown(run_id: str) -> dict:
    base = score.score_run(run_id)
    book = score.load_decisions(run_id)
    referee = load_referee(run_id)
    errors = referee_error_steps(referee)

    result = {
        "run_id": run_id,
        "config": book.get("config"),
        "score": base,                                   # score.py 그대로
        "sla_split": structural_split(book["decisions"]),
        "referee": {
            "present": bool(referee),
            "steps_judged": len(referee),
            "error_steps": sorted(errors),
            "excluded": len(errors),
        },
    }
    # 제외할 게 있을 때만 다시 계산한다. 없으면 score 와 같다.
    result["score_excluding_referee_errors"] = (
        scored_without(run_id, errors) if errors else None)
    return result


def _fmt(r: dict) -> str:
    s, sp, rf = r["score"], r["sla_split"], r["referee"]
    pa, ep = s["perception_accuracy"], s["escalation_precision"]
    cfg = r.get("config") or {}
    lines = [
        f"{r['run_id']}",
        f"  조건  scenario={cfg.get('scenario')} seed={cfg.get('seed')} arm={cfg.get('arm')} "
        f"driver={cfg.get('driver')} intent={'있음' if cfg.get('intent') else '없음'}",
        "",
        f"  상황 인지 정확도   {pa['accuracy']}   ({pa['correct']}/{pa['n']})",
        f"  개입 정밀도        {ep['precision']}   ({ep['correct']}/{ep['n']})",
        "",
        f"  SLA 위반 {sp['violations']}/{sp['scored']}",
        f"    배분으로 피할 수 있었음   {sp['avoidable']}",
        f"    구조적 (압력>1.0)         {sp['structural']}   {sp['structural_steps'] or ''}",
        f"    판정 불가 (다음 관측 없음) {sp['unknown']}",
        "",
    ]
    if rf["present"]:
        lines.append(f"  심판 {rf['steps_judged']}스텝 · 오류 스텝 {rf['excluded']} {rf['error_steps'] or ''}")
        ex = r["score_excluding_referee_errors"]
        if ex:
            lines.append(f"    제외 후 정확도 {ex['perception_accuracy']['accuracy']} · "
                         f"정밀도 {ex['escalation_precision']['precision']}")
    else:
        lines.append("  심판 기록 없음 (고정 루프 — 위반 정의상 0)")
    return "\n".join(lines)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        print("usage: python -m eval.breakdown {run_id} [--json]", file=sys.stderr)
        sys.exit(1)
    out = breakdown(args[0])
    if "--json" in sys.argv:
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        print(_fmt(out))
