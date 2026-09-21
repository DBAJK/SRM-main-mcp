"""② slice-policy — FastMCP 서버. (B 소유)

계약: `claude/spec/policy.md` · 설계서 §3 / §4 ②
무상태. 모델만 상주한다.

    SLICE_DESC_MODE=minimal python -m srm_mcp.policy.server

⚠️ FastMCP 는 함수 docstring 을 도구 설명으로 써서 LLM 컨텍스트에 그대로 넣는다.
   ②는 그 설명 자체가 실험 변수다(설계서 §6.3) — "평시 효율 우수" 는 사실상 "언제 이걸
   골라라" 는 조언이다. 그래서 LLM 이 볼 문자열은 `descriptions.py` 한 곳에서만 나오고,
   아래 docstring 은 개발자용으로만 남는다.
"""
from __future__ import annotations

import os
from typing import Any, Optional

from fastmcp import FastMCP

from ..common.store import to_builtin
from . import classify as classify_mod
from . import descriptions, dqn, lstm, rule

mcp = FastMCP("slice-policy")

POLICIES = ("rule_based", "lstm_forecast", "dqn")
SITUATIONS = ("normal", "emergency", "special_event", "iot_surge")

# LLM 이 보는 도구 설명. 무엇을 하는지와 호출 규약만 말한다.
TOOL_DESC = {
    "list_policies": "배분 정책 목록과 각 정책의 가용 여부.",
    "propose_allocation": (
        "한 정책으로 목표 배분을 제안한다. situation 은 필수이며 "
        "normal · emergency · special_event · iot_surge 중 하나다. "
        "정책이 쓸 수 없는 상태면 allocation 이 null 이고 status 에 사유가 담긴다."
    ),
    "compare_policies": (
        "전 정책을 같은 관측으로 한 번에 평가한다. 반환량이 propose_allocation 의 3배다."
    ),
    "classify_demand": "관측에서 어느 슬라이스 수요가 지배적인지 분류한다.",
}


def _tidy(proposal: dict[str, Any]) -> dict[str, Any]:
    """부동소수 꼬리를 자른다.

    `0.5562499999999999` 같은 값이 그대로 나가면 ④의 기록과 LLM 컨텍스트 양쪽에
    쓸모없는 자릿수가 쌓인다. 배분은 6자리(이중 반올림 방지), 신뢰도는 4자리.
    """
    if proposal.get("allocation"):
        proposal["allocation"] = {k: round(float(v), 6)
                                  for k, v in proposal["allocation"].items()}
    proposal["confidence"] = round(float(proposal["confidence"]), 4)
    return proposal


def _unavailable(policy: str, reason: str, rationale: str) -> dict[str, Any]:
    return {"policy": policy, "allocation": None, "confidence": 0.0,
            "in_distribution": False, "status": "unavailable",
            "reason": reason, "rationale": rationale}


def _check_situation(situation: str) -> None:
    """기본값을 주지 않는 것이 이 서버의 핵심이다.

    "normal" 을 기본값으로 두면 에이전트가 생략했을 때 조용히 평시로 처리되어 미탐이
    측정에서 사라진다. 값이 틀리면 조용히 넘기지 않고 계약 위반으로 막는다.
    """
    if situation not in SITUATIONS:
        raise ValueError(
            f"unknown situation: {situation!r}. 가능한 값: {list(SITUATIONS)}. "
            f"기본값은 없다 — 에이전트가 관측에서 추론해 명시해야 한다."
        )


def _check_policy(policy: str) -> None:
    if policy not in POLICIES:
        raise ValueError(f"unknown policy: {policy!r}. 가능한 값: {list(POLICIES)}")


def _propose(policy: str, observation: dict, situation: str,
             history: Optional[dict], recent_error: Optional[float]) -> dict[str, Any]:
    """정책 하나를 평가한다. **policy 필드는 요청받은 값 그대로 돌려준다** (정정 H)."""
    if policy == "rule_based":
        allocation = rule.propose(observation, situation)
        return {
            "policy": policy,
            "allocation": allocation,
            "confidence": rule.confidence(observation),
            "in_distribution": True,          # 규칙에는 학습 분포가 없다
            "status": "ok",
            "reason": None,
            "rationale": rule.rationale(observation, situation, allocation),
        }

    if policy == "lstm_forecast":
        return {"policy": policy, **lstm.propose(observation, history, recent_error)}

    ok, reason = dqn.available()
    if not ok:
        return _unavailable(policy, reason, "1차 범위에서 제외된 정책.")
    return {"policy": policy, **dqn.propose(observation)}


# ── 도구 ───────────────────────────────────────────────────────
@mcp.tool(description=TOOL_DESC["list_policies"])
def list_policies() -> list[dict]:
    """TensorFlow 적재에 실패하면 서버는 죽지 않고 해당 정책만 available=False 로 내린다.

    `available` 이 이 도구의 핵심이다 — 에이전트가 쓸 수 없는 정책을 고르지 않게 한다.
    """
    status = {
        "rule_based": (True, None),
        "lstm_forecast": lstm.available(),
        "dqn": dqn.available(),
    }
    return [{
        "name": name,
        "description": descriptions.describe(name),
        "requires": descriptions.REQUIRES[name],
        "available": status[name][0],
        "unavailable_reason": status[name][1],
    } for name in POLICIES]


@mcp.tool(description=TOOL_DESC["propose_allocation"])
def propose_allocation(
    policy: str,
    observation: dict,
    situation: str,                      # ⚠️ 필수. 기본값을 주지 않는다
    history: Optional[dict] = None,
    recent_error: Optional[float] = None,
) -> dict:
    """한 정책으로 목표 배분을 제안한다.

    situation — 에이전트가 관측에서 추론한 상황. 배분에 영향을 주는 것은 rule_based 뿐이지만
        모든 정책이 필수로 받는다. 에이전트가 매 결정마다 상황 판단을 명시하게 강제하고,
        그 값이 ④에 기록되어 perception_accuracy 의 입력이 되기 때문이다.
    recent_error — ⑤ `get_reliability_table()` 의 `{policy}.recent_error` 를 에이전트가
        중계한다(V4). ②는 무상태라 누적값을 가질 수 없다.

    ⚠️ 폴백 금지 (정정 H). 실패 시 다른 정책을 조용히 호출하지 않는다.
       `allocation: null` + `status` 로 돌려주고 `policy` 는 요청받은 값 그대로 둔다.
       대체 정책 선택은 에이전트의 일이고, 그게 이 연구의 주제다.

    평활·클립은 여기서 걸지 않는다 — ①의 `apply_allocation()` 소관 (설계서 §3.2).
    """
    _check_policy(policy)
    _check_situation(situation)
    return to_builtin(_tidy(_propose(policy, observation, situation, history, recent_error)))


@mcp.tool(description=TOOL_DESC["compare_policies"])
def compare_policies(
    observation: dict,
    situation: str,
    history: Optional[dict] = None,
    recent_errors: Optional[dict] = None,   # W6: {policy: float} 딕셔너리
) -> list[dict]:
    """전 정책을 평가한다. **사용 가능 여부와 무관하게 전부 반환한다.**

    recent_errors — ⑤ `get_reliability_table()` 출력을 그대로 넘긴다. 스칼라를 받으면
        모든 정책이 같은 오차 이력을 공유하는 셈이라 신뢰도 비교가 무의미해진다(W6).
        `{"lstm_forecast": 0.112}` 도, `{"lstm_forecast": {"recent_error": 0.112}}` 도 받는다.
    """
    _check_situation(situation)

    def error_of(policy: str) -> Optional[float]:
        if not recent_errors:
            return None
        entry = recent_errors.get(policy)
        if isinstance(entry, dict):
            entry = entry.get("recent_error")
        return None if entry is None else float(entry)

    return to_builtin([_tidy(_propose(p, observation, situation, history, error_of(p)))
                       for p in POLICIES])


@mcp.tool(description=TOOL_DESC["classify_demand"])
def classify_demand(observation: dict) -> dict:
    """지배 수요만 알려준다. 상황 판단은 하지 않는다 — 그건 에이전트의 몫이다."""
    return to_builtin(classify_mod.classify(observation))


if __name__ == "__main__":
    # 모델 적재는 기동 시 1회. 실패해도 죽지 않고 해당 정책만 내려간다.
    lstm.load()
    classify_mod.load()
    print(f"[slice-policy] desc_mode={os.environ.get('SLICE_DESC_MODE', 'minimal')} "
          f"lstm={lstm.available()[0]} classifier={classify_mod.available()[0]}",
          file=__import__("sys").stderr)
    mcp.run()
