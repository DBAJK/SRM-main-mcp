"""④ slice-audit — FastMCP 서버. (A 소유)

계약: `claude/spec/audit.md` · 설계서 §4 ④ · 기록 파일 `runs/{run_id}/decisions.json`

    SLICE_RUN_ID=exp-proposed-emergency-s0 python -m srm_mcp.audit.server

도구 본체는 `book.py` 에 있다 — `fastmcp` 없이 `tools/check_audit.py` 가 계약을 검사할 수
있어야 하기 때문이다. 이 파일은 설명과 배선만 담당한다.

`run_id` 는 에이전트(C)가 발급한다. 도구 인자로 넘기거나 서버 기동 시 `SLICE_RUN_ID` 로
준다. ①의 `reset(run_id=...)` 과 **같은 값**이어야 실행 단위 산출물이 step 으로 조인된다.

⚠️ FastMCP 는 함수 docstring 을 도구 설명으로 쓴다. LLM 이 볼 문자열은 TOOL_DESC 에만 둔다.
⚠️ 정답 의존 지표는 반환하지 않는다 (`claude/flow/forbidden.md`). ④의 반환값은 에이전트
   컨텍스트에 그대로 들어가므로, 그걸 넣으면 ①에서 막은 라벨이 ④를 통해 우회 도달한다.
"""
from __future__ import annotations

import sys
from typing import Optional

from fastmcp import FastMCP

from ..common import paths
from . import book

mcp = FastMCP("slice-audit")

TOOL_DESC = {
    "record_decision": (
        "판단 한 건을 기록한다. apply_allocation 보다 **먼저** 부른다. "
        "situation 은 이번 스텝에 대한 너의 상황 판단이고, "
        "confidence 는 situation · intrinsic · empirical · combined 네 값이 모두 필요하다. "
        "조달했다면 slice_id · vendor_id · cost_total 을 같이 넘긴다 — "
        "vendor_id 가 여기 남아야 결과 보고 때 되돌려받는다. "
        "한 스텝에 한 번만 호출한다. decision_id 를 돌려준다."
    ),
    "record_escalation": (
        "사람 호출을 기록한다. **호출한 것 자체가 개입 1회이며 응답을 기다리지 않는다.** "
        "이 한 번의 호출이 개입 기록과 폴백 결정을 같은 step 으로 함께 남기므로 "
        "record_decision 을 또 부르면 안 된다. "
        "이번 스텝에 조달했다면 slice_id · vendor_id · cost_total 을 여기에 같이 넘긴다 — "
        "record_decision 과 같은 자리이며, 여기 넘기지 않으면 그 조달은 기록되지 않는다. "
        "fallback_allocation 과 decision_id 를 돌려주며, instruction 에 다음 행동이 적혀 있다."
    ),
    "get_decisions": (
        "최근 결정 n 건. kind 로 decision · escalation 을 거를 수 있다. "
        "full=false(기본)면 한 줄 요약만 오고, true 면 관측이 통째로 딸려와 매우 길어진다."
    ),
    "get_metrics": (
        "집계 지표. window 를 주면 최근 n 스텝만 본다. "
        "steps 는 채점이 끝난 결정 수라 기록된 결정 수보다 1 작은 것이 정상이다. "
        "mttr 은 위반이 시작된 스텝부터 전부 해소된 스텝까지의 평균 길이이고, "
        "복구되지 않은 채 끝난 구간은 unresolved 로 따로 센다."
    ),
}


@mcp.tool(description=TOOL_DESC["record_decision"])
def record_decision(step: int, observation: dict, situation: str, chosen_policy: str,
                    allocation: dict, confidence: dict, rationale: str,
                    slice_id: Optional[str] = None, vendor_id: Optional[str] = None,
                    cost_total: Optional[float] = None,
                    in_distribution: Optional[bool] = None,
                    demand_class: Optional[dict] = None,
                    considered: Optional[list] = None,
                    run_id: Optional[str] = None,
                    config: Optional[dict] = None) -> dict:
    """`book.record_decision` 그대로. 판단은 실행보다 먼저 기록한다."""
    return book.record_decision(step, observation, situation, chosen_policy, allocation,
                                confidence, rationale, slice_id, vendor_id, cost_total,
                                in_distribution, demand_class, considered, run_id, config)


@mcp.tool(description=TOOL_DESC["record_escalation"])
def record_escalation(step: int, observation: dict, situation: str, reason: str,
                      confidence: dict,
                      slice_id: Optional[str] = None, vendor_id: Optional[str] = None,
                      cost_total: Optional[float] = None,
                      run_id: Optional[str] = None,
                      config: Optional[dict] = None) -> dict:
    """한 호출이 개입 레코드와 폴백 결정 레코드를 같은 step 으로 남긴다.

    조달 3필드는 `record_decision` 과 같은 중계선이다 — 여기 없으면 에스컬레이션한 스텝의
    조달이 아무 데도 안 남고, 뒤이어 `record_decision` 을 부르는 길은 막혀 있다.
    """
    return book.record_escalation(step, observation, situation, reason, confidence,
                                  slice_id, vendor_id, cost_total, run_id, config)


@mcp.tool(description=TOOL_DESC["get_decisions"])
def get_decisions(n: int = 10, kind: Optional[str] = None, full: bool = False,
                  run_id: Optional[str] = None) -> list:
    """기본은 한 줄 요약. `full=True` 는 관측이 통째로 딸려오므로 컨텍스트를 크게 먹는다."""
    return book.get_decisions(n, kind, full, run_id)


@mcp.tool(description=TOOL_DESC["get_metrics"])
def get_metrics(window: Optional[int] = None, run_id: Optional[str] = None) -> dict:
    """관측만으로 계산되는 지표뿐이다 (`claude/flow/forbidden.md`)."""
    return book.get_metrics(window, run_id)


if __name__ == "__main__":
    run_id = book.env_run_id()
    print(f"[slice-audit] run_id={run_id} "
          f"decisions={paths.decisions_json(run_id or '<unset>')}", file=sys.stderr)
    mcp.run()
