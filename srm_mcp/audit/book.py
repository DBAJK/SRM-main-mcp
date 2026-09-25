"""④ 의 기록 본체 — `runs/{run_id}/decisions.json`. (A 소유)

`server.py` 는 이 모듈의 얇은 FastMCP 껍데기다. 도구 본체를 여기 두는 이유는 ③⑤와 같다 —
`fastmcp` 없이도 `tools/check_audit.py` 가 계약을 검사할 수 있어야 한다.

**④가 파일을 만들고 ⑤가 같은 레코드에 `outcome` 을 덧쓴다** (설계서 §2.1). 그래서 책을
메모리에 캐시하지 않는다 — 호출마다 디스크에서 읽는다. 캐시하면 ⑤가 덧쓴 `outcome` 을
못 보고 다음 기록에서 통째로 덮어써 채점 결과가 사라진다.
"""
from __future__ import annotations

import os
from typing import Any, Optional

from ..common import paths
from ..common.const import INIT_ALLOCATION, TAU
from ..common.store import read_json, to_builtin, write_json
from . import metrics

CONFIDENCE_KEYS = ("situation", "intrinsic", "empirical", "combined")

# 폴백은 항상 rule_based × normal 이다 (spec/audit.md).
# ④는 ②를 부를 수 없으므로(서버 간 직접 호출 금지) 그 목표 배분을 여기서 만든다.
# rule_based 의 situation="normal" 목표는 const.INIT_ALLOCATION 과 같은 값이다.
FALLBACK_POLICY = "rule_based"
FALLBACK_SITUATION = "normal"
FALLBACK_INSTRUCTION = (
    "사람 호출을 기록했다. 대기하지 말고 fallback_allocation 을 apply_allocation 에 넣어 "
    "이번 스텝을 진행한 뒤, step() 후 decision_id 로 report_outcome 을 호출하라."
)


# ── run_id · config ────────────────────────────────────────────
def env_run_id() -> Optional[str]:
    return os.environ.get("SLICE_RUN_ID") or None


def resolve_run_id(run_id: Optional[str]) -> Optional[str]:
    """에이전트(C)가 발급한 값. 인자 > 환경변수 순으로 찾는다."""
    return run_id or env_run_id()


def default_config() -> dict:
    """`decisions.json` 에 박아 두는 실행 조건. 60회 산출물이 섞이지 않게 한다.

    ④가 알 수 있는 것만 환경변수에서 읽는다. 나머지는 C가 `config` 인자로 넘긴다.
    """
    seed = os.environ.get("SLICE_SEED")
    return {
        "scenario": os.environ.get("SLICE_SCENARIO"),
        "seed": int(seed) if seed not in (None, "") else None,
        "arm": os.environ.get("SLICE_ARM"),
        "desc_mode": os.environ.get("SLICE_DESC_MODE", "minimal"),
        "memory_mode": os.environ.get("SLICE_MEMORY_MODE", "warm"),
        "tau": TAU,
    }


# ── 저장소 ─────────────────────────────────────────────────────
def load(run_id: str) -> dict:
    book = read_json(paths.decisions_json(run_id))
    if not isinstance(book, dict):
        return {"run_id": run_id, "config": default_config(), "decisions": []}
    book.setdefault("run_id", run_id)
    book.setdefault("config", default_config())
    book.setdefault("decisions", [])
    return book


def save(run_id: str, book: dict) -> None:
    write_json(paths.decisions_json(run_id), book)


def decision_id_for(run_id: str, step: int) -> str:
    """`{run_id}-{step:04d}`. ⑤가 정규식으로 run_id 를 되판다 — 제로패딩 4자리 고정."""
    return f"{run_id}-{int(step):04d}"


def escalation_id_for(run_id: str, step: int) -> str:
    return f"{run_id}-esc-{int(step):04d}"


# ── 오류 (flow/errors.md — 복구 가능한 것은 값으로) ────────────
def missing_run_id() -> dict:
    return {"error": "missing_run_id",
            "reason": "run_id 인자도 SLICE_RUN_ID 환경변수도 없다",
            "expected": "{arm}-{scenario}-s{seed}  예: exp-proposed-emergency-s0"}


def bad_confidence(confidence: Any) -> Optional[dict]:
    if not isinstance(confidence, dict):
        return {"error": "malformed_confidence", "got": type(confidence).__name__,
                "expected": {k: "float" for k in CONFIDENCE_KEYS}}
    missing = [k for k in CONFIDENCE_KEYS if confidence.get(k) is None]
    if missing:
        # situation 이 빠지면 상황 오판이 combined 에 반영되지 않아 에스컬레이션이
        # 일어나지 않는다. 조용히 채우지 않고 되돌린다.
        return {"error": "missing_confidence", "missing": missing,
                "expected": {k: "float" for k in CONFIDENCE_KEYS}}
    # 값이 있어도 float 로 안 바뀌면(예: LLM이 문자열을 넣음) 조용히 통과시키지 않는다.
    # 실측: haiku 가 confidence 값에 문자열을 넣은 사례 (todo-after-orchestrator.md 8번).
    bad_types = [k for k in CONFIDENCE_KEYS if not _is_floatable(confidence[k])]
    if bad_types:
        return {"error": "malformed_confidence", "bad_types": bad_types,
                "got": {k: confidence[k] for k in bad_types},
                "expected": {k: "float" for k in CONFIDENCE_KEYS}}
    return None


def _is_floatable(value: Any) -> bool:
    if isinstance(value, bool):  # bool 은 int 의 서브클래스라 float() 이 조용히 통과한다
        return False
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def _existing_decision(book: dict, step: int) -> Optional[dict]:
    return next((r for r in book["decisions"]
                 if int(r.get("step", -1)) == int(step) and r.get("kind") == "decision"),
                None)


# ── 도구 본체 ──────────────────────────────────────────────────
def record_decision(step: int, observation: dict, situation: str, chosen_policy: str,
                    allocation: dict, confidence: dict, rationale: str,
                    slice_id: Optional[str] = None, vendor_id: Optional[str] = None,
                    cost_total: Optional[float] = None,
                    in_distribution: Optional[bool] = None,
                    demand_class: Optional[dict] = None,
                    considered: Optional[list] = None,
                    run_id: Optional[str] = None,
                    config: Optional[dict] = None) -> dict:
    """판단을 실행(`apply_allocation`)보다 먼저 기록한다.

    실행 후 기록이면 실패 사례가 사라져 자율 처리율이 과대평가된다.

    `cost_total` 은 handover §4-③ 에서 이어 붙인 공급선이다 — ③의 조달 원장은 메모리에만
    있고 노출 도구가 없어서, 에이전트가 `procure().cost_total` 을 여기로 중계하지 않으면
    `get_metrics.procurement_cost_total` 이 영영 0 이다.

    같은 스텝에 두 번 기록하면 `sum(policy_usage)` 불변식이 깨진다. 에스컬레이션 뒤에
    또 부르는 것이 그 전형이라 시끄럽게 막는다.
    """
    resolved = resolve_run_id(run_id)
    if resolved is None:
        return missing_run_id()

    bad = bad_confidence(confidence)
    if bad is not None:
        return bad

    book = load(resolved)
    if config:
        book["config"] = {**book["config"], **config}

    duplicate = _existing_decision(book, step)
    if duplicate is not None:
        return {"error": "duplicate_decision", "step": int(step),
                "decision_id": duplicate["decision_id"],
                "reason": ("이 스텝에는 이미 결정 레코드가 있다. 에스컬레이션한 스텝이면 "
                           "record_escalation 이 폴백 결정을 이미 남겼다")}

    decision_id = decision_id_for(resolved, step)
    book["decisions"].append({
        "decision_id": decision_id,
        "step": int(step),
        "kind": "decision",
        "situation": situation,
        "chosen_policy": chosen_policy,
        "allocation": allocation,
        "confidence": confidence,
        "rationale": rationale,
        "slice_id": slice_id,
        "vendor_id": vendor_id,
        "cost_total": float(cost_total) if cost_total is not None else None,
        "in_distribution": in_distribution,
        "demand_class": demand_class,
        "considered": considered,
        "observation": observation,
        "outcome": None,
    })
    save(resolved, book)
    return to_builtin({"decision_id": decision_id, "recorded_at_step": int(step)})


def record_escalation(step: int, observation: dict, situation: str, reason: str,
                      confidence: dict,
                      slice_id: Optional[str] = None, vendor_id: Optional[str] = None,
                      cost_total: Optional[float] = None,
                      chosen_policy: Optional[str] = None,
                      run_id: Optional[str] = None,
                      config: Optional[dict] = None) -> dict:
    """한 호출이 `kind: "escalation"` 과 `kind: "decision"` 레코드를 같은 step 으로 남긴다.

    에스컬레이션한 스텝도 배분은 적용되고 SLA 결과가 나온다. `escalation_id` 만 주면
    `report_outcome(decision_id=?)` 을 부를 수 없어 **그 스텝의 결과가 통계에서 통째로
    사라진다** — 그런데 그건 정의상 가장 어려운 스텝이라, 빠지면 `sla_violations` 가
    과소 집계되고 핵심 논증이 편향된 표본 위에서 성립한다 (`rationale/audit.md`).

    폴백 결정 레코드의 `situation` 에는 **에이전트의 판단**을 그대로 남긴다. 폴백이 정책에
    먹인 라벨("normal")로 덮으면 상황 인지 측정의 입력이 사라진다. 먹인 라벨은
    `fallback_situation` 으로 따로 남긴다.

    `chosen_policy` 도 같은 원리다 — 실제로 실행된 것은 항상 `FALLBACK_POLICY`
    (rule_based)이고 그건 그대로 `chosen_policy` 에 남는다(⑤가 실행된 정책의 성적을
    기록해야 하므로). 에이전트가 원래 고르려던 정책은 `agent_policy` 에 따로 남긴다 —
    없으면 "에스컬레이션이 없었다면 무엇을 골랐을까"를 사후에 알 수 없다
    (workplan.md A-1).

    `slice_id` · `vendor_id` · `cost_total` 은 `record_decision` 과 같은 중계선이다.
    같은 이유로 여기에도 있어야 한다 — 에스컬레이션한 스텝에 조달했는데 이 셋을 받지
    못하면 그 조달이 **아무 데도 안 남는다.** 뒤이어 `record_decision` 을 부르는 길은
    `duplicate_decision` 으로 막혀 있으므로 복구 경로도 없다. 결과는 세 곳이 동시에 틀어진다 —
    `get_metrics.procurements` 와 `procurement_cost_total` 이 그만큼 적게 세고,
    ⑤ `report_outcome` 이 이 레코드에서 `vendor_id` 를 찾으므로 항상 `null` 이 되어
    ⑤→③ 레이팅 되먹임이 끊긴다. 그것도 하필 `demand_pressure` 가 가장 높아 조달이 가장
    필요한 스텝에서만 끊기므로, 마켓 자기 개선의 증거가 편향된 표본 위에 남는다.
    """
    resolved = resolve_run_id(run_id)
    if resolved is None:
        return missing_run_id()

    bad = bad_confidence(confidence)
    if bad is not None:
        return bad

    book = load(resolved)
    if config:
        book["config"] = {**book["config"], **config}

    duplicate = _existing_decision(book, step)
    if duplicate is not None:
        return {"error": "duplicate_decision", "step": int(step),
                "decision_id": duplicate["decision_id"],
                "reason": "이 스텝에는 이미 결정 레코드가 있다"}

    decision_id = decision_id_for(resolved, step)
    escalation_id = escalation_id_for(resolved, step)
    fallback = dict(INIT_ALLOCATION)

    book["decisions"].append({
        "decision_id": escalation_id,
        "step": int(step),
        "kind": "escalation",
        "situation": situation,
        "reason": reason,
        "confidence": confidence,
        "observation": observation,
    })
    book["decisions"].append({
        "decision_id": decision_id,
        "step": int(step),
        "kind": "decision",
        "situation": situation,
        "chosen_policy": FALLBACK_POLICY,
        "agent_policy": chosen_policy,
        "allocation": fallback,
        "confidence": confidence,
        "rationale": f"escalated: {reason}",
        "escalated": True,
        "escalation_id": escalation_id,
        "fallback_situation": FALLBACK_SITUATION,
        "fallback_allocation": fallback,
        # record_decision 과 같은 자리·같은 이름이다. ⑤와 metrics 가 kind 를 구분하지 않고
        # 이 세 필드만 보므로, 여기 담기면 에스컬레이션한 스텝의 조달도 그대로 집계된다.
        "slice_id": slice_id,
        "vendor_id": vendor_id,
        "cost_total": float(cost_total) if cost_total is not None else None,
        "in_distribution": None,
        "demand_class": None,
        "considered": None,
        "observation": observation,
        "outcome": None,
    })
    save(resolved, book)

    return to_builtin({
        "escalation_id": escalation_id,
        "decision_id": decision_id,
        "fallback_policy": FALLBACK_POLICY,
        "fallback_situation": FALLBACK_SITUATION,
        "fallback_allocation": fallback,
        "instruction": FALLBACK_INSTRUCTION,
    })


def get_decisions(n: int = 10, kind: Optional[str] = None, full: bool = False,
                  run_id: Optional[str] = None) -> list:
    """최근 n 건. 기본은 한 줄 요약이다.

    기본값이 spec 의 50 이 아니라 10 인 이유 — 각 레코드에 `observation` 이 통째로 들어
    있어 n=50 · full=true 면 약 10,500 토큰이다 (`rationale/context-budget.md`).
    전량 분석은 `eval/score.py` 가 파일을 직접 읽는다.
    """
    resolved = resolve_run_id(run_id)
    if resolved is None:
        return [missing_run_id()]

    records = load(resolved)["decisions"]
    if kind is not None:
        records = [r for r in records if r.get("kind") == kind]
    recent = records[-max(1, int(n)):]
    return to_builtin(recent if full else [metrics.summarize(r) for r in recent])


def get_metrics(window: Optional[int] = None, run_id: Optional[str] = None) -> dict:
    """관측만으로 계산되는 지표뿐이다 (`claude/flow/forbidden.md`).

    `build/order.md` 3단계 완료 판정이 곧 이 반환 필드 목록이다 — 정답 의존 지표가
    **부재**함을 확인한다.
    """
    resolved = resolve_run_id(run_id)
    if resolved is None:
        return missing_run_id()
    return to_builtin(metrics.aggregate(load(resolved)["decisions"], window))
