"""④ 의 지표 집계. (A 소유)

`decisions.json` 의 레코드 배열 하나만 보고 계산한다. **정답이 필요한 지표는 여기 없다** —
`eval/score.py` 가 오프라인으로 `runs/{run_id}/truth.jsonl` 과 조인해 따로 낸다
(`claude/flow/forbidden.md`).

집계 불변식 (`spec/audit.md`)

    steps              = 채점된 결정 수        (60스텝 에피소드 → 59)
    sum(policy_usage)  = 기록된 결정 수        (60)
    Σ ⑤의 n            = 채점된 결정 수        (59)

`sum(policy_usage)` 와 `steps` 가 1 차이나는 것은 정상이다 — 마지막 결정은 채점될
다음 스텝이 없다. 2 이상 벌어지면 ②의 조용한 폴백이나 `report_outcome` 누락을 의심한다.
"""
from __future__ import annotations

from typing import Any, Optional

from ..common.const import SLICE_KEYS


def decision_records(records: list[dict]) -> list[dict]:
    """kind == "decision" 만. 에스컬레이션한 스텝도 여기에 폴백 결정이 한 건 있다."""
    return [r for r in records if r.get("kind") == "decision"]


def escalation_records(records: list[dict]) -> list[dict]:
    return [r for r in records if r.get("kind") == "escalation"]


def in_window(records: list[dict], window: Optional[int]) -> list[dict]:
    """최근 `window` 스텝. None 이면 전체."""
    if window is None or not records:
        return list(records)
    last = max(int(r.get("step", 0)) for r in records)
    floor = last - int(window) + 1
    return [r for r in records if int(r.get("step", 0)) >= floor]


def _mean_triple(rows: list[dict]) -> dict:
    if not rows:
        return {k: 0.0 for k in SLICE_KEYS}
    return {k: round(sum(float(row.get(k, 0.0)) for row in rows) / len(rows), 6)
            for k in SLICE_KEYS}


def violation_timeline(decisions: list[dict]) -> list[tuple[int, bool]]:
    """(step, 위반이 하나라도 있는가) 를 시간순으로.

    출처는 각 결정의 `observation.violations` 다. 이것은 obs_t 이므로 a_{t-1} 의 결과이고,
    **구간의 길이를 재는 데는 그 1스텝 이동이 상쇄된다** — 시작도 끝도 같은 기준으로
    읽기 때문이다. 마지막 결정의 `outcome.observed_violations` 가 있으면 한 칸 더 붙여
    에피소드 끝의 복구를 놓치지 않는다.

    ⚠️ `sla_violations` 를 이 타임라인으로 세면 안 된다 (`rationale/audit.md`).
       그쪽 출처는 ⑤가 덧붙인 `outcome.sla_met` 하나뿐이다.
    """
    timeline: list[tuple[int, bool]] = []
    for record in sorted(decisions, key=lambda r: int(r.get("step", 0))):
        flags = (record.get("observation") or {}).get("violations") or {}
        timeline.append((int(record.get("step", 0)), any(bool(v) for v in flags.values())))
    if decisions:
        last = max(decisions, key=lambda r: int(r.get("step", 0)))
        outcome = last.get("outcome") or {}
        observed = outcome.get("observed_violations")
        if isinstance(observed, dict):
            timeline.append((int(outcome.get("scored_at_step", last.get("step", 0)) or 0),
                             any(bool(v) for v in observed.values())))
    return timeline


def mttr(decisions: list[dict]) -> tuple[Optional[float], int]:
    """(평균 복구 길이, 복구되지 않은 구간 수).

    위반이 시작된 스텝부터 전부 해소된 스텝까지의 길이. 정답을 쓰지 않는다.
    복구되지 않은 채 끝난 구간은 평균에서 빼고 `unresolved` 로 따로 보고한다 —
    조용히 빼면 MTTR 이 좋아 보인다.
    """
    lengths: list[int] = []
    unresolved = 0
    start: Optional[int] = None
    for step, violated in violation_timeline(decisions):
        if violated and start is None:
            start = step
        elif not violated and start is not None:
            lengths.append(step - start)
            start = None
    if start is not None:
        unresolved = 1
    mean = round(sum(lengths) / len(lengths), 4) if lengths else None
    return mean, unresolved


def aggregate(records: list[dict], window: Optional[int] = None) -> dict:
    """`spec/audit.md` 의 Metrics. 관측만으로 계산되는 지표뿐이다."""
    scoped = in_window(records, window)
    decisions = decision_records(scoped)
    escalations = escalation_records(scoped)
    scored = [r for r in decisions if isinstance(r.get("outcome"), dict)]

    steps = len(scored)
    interventions = len(escalations)

    observations = [r.get("observation") or {} for r in decisions]
    mean_recovery, unresolved = mttr(decisions)

    policy_usage: dict[str, int] = {}
    for record in decisions:
        name = record.get("chosen_policy")
        if name:
            policy_usage[name] = policy_usage.get(name, 0) + 1

    procured = [r for r in decisions if r.get("slice_id")]

    return {
        "steps": steps,
        "interventions": interventions,
        # steps 가 0 이면 비율이 정의되지 않는다. 1.0 으로 채우면 "전부 자율" 로 읽혀 거짓이다.
        "autonomous_rate": (round(1 - interventions / steps, 6) if steps else None),
        # ⚠️ observation.violations 로 세지 않는다 — 1스텝 어긋나고 step 0 의 초기 상태가
        #    아무 결정의 책임도 아닌 채로 섞여 들어간다 (rationale/audit.md).
        "sla_violations": sum(1 for r in scored if r["outcome"].get("sla_met") is False),
        "mean_utilization": _mean_triple([o.get("utilization") or {} for o in observations]),
        "policy_usage": policy_usage,
        "mttr": mean_recovery,
        "unresolved": unresolved,
        "procurements": len(procured),
        "procurement_cost_total": round(
            sum(float(r.get("cost_total") or 0.0) for r in decisions), 4),
        "mean_capacity": _mean_triple([o.get("capacity") or {} for o in observations]),
        "pressure_exceeded": sum(1 for o in observations
                                 if float(o.get("demand_pressure") or 0.0) >= 1.0),
    }


def summarize(record: dict) -> dict[str, Any]:
    """`get_decisions` 가 observation 을 통째로 싣는 것을 피할 때 쓰는 한 줄 요약.

    레코드 하나에 observation 이 통째로 들어 있어 n=50 이면 약 10,500 토큰이다
    (`rationale/context-budget.md`).
    """
    outcome = record.get("outcome") or {}
    return {
        "decision_id": record.get("decision_id"),
        "step": record.get("step"),
        "kind": record.get("kind"),
        "situation": record.get("situation"),
        "chosen_policy": record.get("chosen_policy"),
        "allocation": record.get("allocation"),
        "combined": (record.get("confidence") or {}).get("combined"),
        "sla_met": outcome.get("sla_met"),
        "error": outcome.get("error"),
    }
