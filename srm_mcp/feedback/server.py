"""⑤ slice-feedback — FastMCP 서버. (B 소유)

계약: `claude/spec/feedback.md` · 설계서 §4 ⑤ / §6.2

    SLICE_MEMORY_MODE=warm python -m srm_mcp.feedback.server

상태 보유. `reliability.json` 의 위치가 실험 변수다 (설계서 §5.0).

    warm  data/reliability.json          전체 실행에 걸쳐 누적. **주 결과**
    cold  runs/{run_id}/reliability.json 시나리오마다 초기화. 대조군

⑤는 `vendors.json` 에 직접 쓰지 않는다. `vendor_id` 를 결과에 실어 보내면 에이전트가
③ `update_rating()` 을 호출한다 — 서버 간 직접 호출 금지.

⚠️ FastMCP 는 함수 docstring 을 도구 설명으로 쓴다. LLM 이 볼 문자열은 TOOL_DESC 에만 둔다.
"""
from __future__ import annotations

import os
import re
import sys
from typing import Any, Optional

from fastmcp import FastMCP

from ..common import paths
from ..common.store import read_json, to_builtin, write_json
from . import reliability, scoring

mcp = FastMCP("slice-feedback")

TOOL_DESC = {
    "report_outcome": (
        "한 결정을 채점하고 정책 신뢰도를 갱신한다. observed 는 step() **이후**의 관측이어야 "
        "한다. vendor_id 가 돌아오면 그 값으로 마켓의 레이팅을 갱신할 수 있다."
    ),
    "get_reliability_table": (
        "정책별 경험적 신뢰도. effective 는 표본이 적을 때를 보정한 값이고, "
        "recent_error 는 배분 제안 시 넘길 수 있다."
    ),
}

# decision_id = "{run_id}-{step:04d}" (§5.0). ⑤는 run_id 인자를 받지 않으므로 여기서 되돌린다.
DECISION_ID_RE = re.compile(r"^(?P<run_id>.+)-(?P<step>\d{4})$")

# cold 모드에서 reliability.json 이 어느 실행 폴더에 있는지 알려면 run_id 가 필요하다.
# report_outcome 이 본 마지막 run_id 를 쓰고, 환경변수로 덮어쓸 수 있다.
_run_id: Optional[str] = None


def _memory_mode() -> str:
    return os.environ.get("SLICE_MEMORY_MODE", "warm")


def _current_run_id() -> Optional[str]:
    return os.environ.get("SLICE_RUN_ID") or _run_id


def _reliability_path():
    run_id = _current_run_id()
    if _memory_mode() == "warm" or run_id is None:
        return paths.RELIABILITY_WARM
    return paths.run_dir(run_id) / "reliability.json"


def _load_table() -> dict[str, Any]:
    stored = read_json(_reliability_path())
    table = reliability.initial_table()
    if isinstance(stored, dict):
        for name, entry in stored.items():
            table[name] = {**reliability.initial_entry(), **entry}
    return table


def _save_table(table: dict[str, Any]) -> None:
    write_json(_reliability_path(), table)


def _load_decisions(run_id: str) -> Optional[dict]:
    return read_json(paths.decisions_json(run_id))


def _find_decision(book: dict, decision_id: str) -> Optional[dict]:
    return next((d for d in book.get("decisions", [])
                 if d.get("decision_id") == decision_id), None)


def _requested_allocation(record: dict) -> Optional[dict]:
    """요청했던 배분. 에스컬레이션 레코드는 `fallback_allocation` 이 요청값이다."""
    if record.get("kind") == "escalation":
        return record.get("fallback_allocation") or record.get("allocation")
    return record.get("allocation")


# ── 도구 ───────────────────────────────────────────────────────
@mcp.tool(description=TOOL_DESC["report_outcome"])
def report_outcome(decision_id: str, observed: dict) -> dict:
    """결정 하나를 채점하고 신뢰도를 갱신한다.

    ⚠️ 반드시 ①.step() **이후**에 호출한다. observed 는 obs_{t+1} 이다 —
       `obs_{t+1}.allocation` 이 t에 적용된 배분, `obs_{t+1}.traffic` 이 그 배분이
       감당해야 했던 수요다. step() 전 호출은 `premature_scoring` 으로 되돌린다.

    V5 — 요청값과 적용값을 둘 다 남긴다. 호출 순서상 `record_decision`(3)이
        `apply_allocation`(4)보다 먼저라 ④에는 요청값만 남는데 `error` 는 적용값 기준이다.
        기준이 다르면 "정책이 나빴나, 액추에이터가 막았나" 를 구분할 수 없다
        (spec 예시에서 0.086 vs 0.316, 4배 차이). 요청값은 `decisions.json` 에서 조회한다.

    부작용: ④의 해당 레코드에 `outcome` 을 덧붙이고, `reliability.json` 을 갱신한다.
    """
    global _run_id

    matched = DECISION_ID_RE.match(decision_id)
    if matched is None:
        return {"error": "malformed_decision_id", "decision_id": decision_id,
                "expected": "{run_id}-{step:04d}  예: exp-proposed-emergency-s0-0012"}

    run_id = matched.group("run_id")
    book = _load_decisions(run_id)
    if book is None:
        return {"error": "unknown_run", "run_id": run_id,
                "looked_for": str(paths.decisions_json(run_id))}

    record = _find_decision(book, decision_id)
    if record is None:
        recent = [d.get("decision_id") for d in book.get("decisions", [])][-5:]
        return {"error": "unknown_decision", "decision_id": decision_id, "recent": recent}

    if record.get("outcome") is not None:
        # 두 번 채점하면 신뢰도가 이중 반영된다. 복구 가능한 순서 실수로 본다.
        return {"error": "already_scored", "decision_id": decision_id,
                "scored_at_step": record["outcome"].get("scored_at_step")}

    decision_step = int(record.get("step", int(matched.group("step"))))
    observed_step = int(observed.get("step", -1))
    if observed_step <= decision_step:
        return {"error": "premature_scoring",
                "reason": f"decision at step {decision_step}, observed step {observed_step}; "
                          f"expected >= {decision_step + 1}"}

    _run_id = run_id

    policy = record.get("chosen_policy") or (
        "rule_based" if record.get("kind") == "escalation" else None)
    if policy not in reliability.POLICIES:
        return {"error": "unknown_policy_in_decision", "decision_id": decision_id,
                "chosen_policy": record.get("chosen_policy"),
                "expected": list(reliability.POLICIES)}

    applied = {k: float(v) for k, v in (observed.get("allocation") or {}).items()}
    requested = _requested_allocation(record)
    ideal = scoring.ideal_allocation(observed)

    met = scoring.sla_met(observed.get("violations"))
    error = scoring.distance(applied, ideal)
    actuator_delta = scoring.distance(applied, requested) if requested else 0.0

    table = _load_table()
    entry = table[policy]
    before = float(entry["r"])
    after, n = reliability.update(before, int(entry["n"]), met)
    entry["r"], entry["n"] = after, n
    entry["errors"] = reliability.push_error(entry.get("errors", []), error)
    _save_table(table)

    outcome = {
        "sla_met": met,
        "policy": policy,
        "error": round(error, 4),
        # 배분은 6자리로 둔다. 4자리로 깎으면 소비 측에서 다시 반올림할 때
        # 이중 반올림으로 값이 한 칸 어긋난다 (0.425534 → 0.4255 → 0.425 ≠ 0.426).
        "ideal_allocation": {k: round(v, 6) for k, v in ideal.items()},
        "applied_allocation": applied,
        "requested_allocation": requested,
        "actuator_delta": round(actuator_delta, 4),
        "observed_violations": scoring.violations_view(observed.get("violations")),
        "vendor_id": record.get("vendor_id"),
        "reliability_before": round(before, 4),
        "reliability_after": round(after, 4),
    }

    # ④의 레코드에 덧붙인다 (분리 설계서 §2.1 — ④가 만들고 ⑤가 같은 레코드에 기입).
    record["outcome"] = {
        "sla_met": met,
        "error": round(error, 4),
        "scored_at_step": observed_step,
        "applied_allocation": applied,
        "requested_allocation": requested,
        "actuator_delta": round(actuator_delta, 4),
        "observed_violations": outcome["observed_violations"],
    }
    write_json(paths.decisions_json(run_id), book)

    return to_builtin(outcome)


@mcp.tool(description=TOOL_DESC["get_reliability_table"])
def get_reliability_table() -> dict:
    """정책별 경험적 신뢰도.

        {policy}.effective    → ④ `record_decision` 의 `confidence.empirical`
        {policy}.recent_error → ② `propose_allocation` 의 `recent_error` (에이전트가 중계, V4)

    두 종류의 신뢰도를 종합하는 것은 에이전트만 한다 — ②의 `confidence` 는 **이번 입력**에
    대한 확신이고, 여기 `effective` 는 그 정책이 **평소** 얼마나 맞았나다.
    """
    return to_builtin({name: reliability.view(name, entry)
                       for name, entry in _load_table().items()})


if __name__ == "__main__":
    print(f"[slice-feedback] memory_mode={_memory_mode()} "
          f"reliability={_reliability_path()}", file=sys.stderr)
    mcp.run()
