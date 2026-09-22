"""① slice-observe — FastMCP 서버. (A 소유)

계약: `claude/spec/observe.md` · 설계서 §4 ①

    SLICE_RUN_ID=exp-proposed-emergency-s0 python -m srm_mcp.observe.server

상태 전부를 보유한다 — 배분 · 용량 · 리스 · 이력. `reset()` 이 그 전부를 초기화하며
②③④⑤의 상태는 건드리지 않는다 (설계서 §5.0).

⚠️ FastMCP 는 함수 docstring 을 도구 설명으로 써서 LLM 컨텍스트에 그대로 넣는다.
   아래 docstring 은 구현 지침이라 그대로 나가면 §6.3 의 desc_mode 실험이 오염된다.
   그래서 `@mcp.tool(description=...)` 로 LLM 이 볼 설명을 분리했다 — TOOL_DESC 한 곳에서만
   고친다. **설명은 숫자의 의미와 호출 규약만 말하고 "그러니 이렇게 하라" 는 넣지 않는다.**
"""
from __future__ import annotations

import os
import sys

from fastmcp import FastMCP

from ..common.const import SEQUENCE_LENGTH
from ..common.store import to_builtin
from .env import DEFAULT_RUN_ID, SliceEnv

mcp = FastMCP("slice-observe")

TOOL_DESC = {
    "get_observation": (
        "현재 관측. utilization 은 traffic / (allocation × capacity), "
        "violations 는 utilization > thresholds, "
        "demand_pressure 는 Σ traffic / (thresholds × capacity) 이며 "
        "1.0 을 넘으면 합이 1인 어떤 배분으로도 세 슬라이스를 동시에 임계 아래로 둘 수 없다. "
        "sim_time 은 가상 시계이고 벽시계가 아니다."
    ),
    "step": (
        "시뮬레이션을 n 스텝(1~10, 기본 1) 전진시킨다. "
        "만료된 용량을 먼저 회수한 뒤 다음 트래픽을 만든다. "
        "전진 후 관측의 utilization 은 직전에 적용된 배분으로 계산된다."
    ),
    "apply_allocation": (
        "배분을 적용한다. 합이 1일 필요는 없다 — 서버가 정규화한다. "
        "정규화 → 평활(0.7 × 현재 + 0.3 × 요청) → 클립[0.1, 0.8] → 재정규화 순으로 변형되며, "
        "normalized 가 실제 적용값이고 delta 는 요청과 적용의 거리다. "
        "accepted: false 는 음수·NaN·전부 0 일 때뿐이고 그때는 기존 배분이 유지된다."
    ),
    "get_history": (
        "최근 n 스텝(1~100, 기본 10)의 11차원 피처. 오래된 것부터 최신 순이고 "
        "columns 가 열 순서다. n_available 이 요청보다 적을 수 있다."
    ),
    "add_capacity": (
        "조달한 슬라이스를 환경에 반영한다. slice_type 은 eMBB · URLLC · mMTC, "
        "amount 는 0 초과 0.5 이하, expires_at_step 은 현재 step 보다 커야 한다. "
        "슬라이스당 용량 상한이 있어 초과하면 accepted: false 로 돌아온다."
    ),
    "reset": (
        "에피소드를 초기화한다. run_id 는 필수이며 이 실행의 식별자로 쓰인다. "
        "scenario 는 normal · emergency · special_event · iot_surge · mixed, "
        "seed 는 정수이고 같은 seed 는 같은 전개를 만든다. "
        "용량과 배분이 기본값으로 돌아가고 활성 조달은 전부 회수된다."
    ),
}

# 에피소드가 곧 ①의 수명이다. 프로세스 하나에 환경 하나.
# reset() 없이 시작해도 죽지 않는다 — seed=0 · scenario="normal" 로 자동 초기화한다
# (`flow/errors.md`). 다만 run_id 가 임시값이라 ④와 조인되지 않으므로 C는 반드시 reset 한다.
_env = SliceEnv(os.environ.get("SLICE_RUN_ID") or DEFAULT_RUN_ID)


# ── 도구 ───────────────────────────────────────────────────────
@mcp.tool(description=TOOL_DESC["get_observation"])
def get_observation() -> dict:
    """부작용 없음. 같은 스텝에서 몇 번을 불러도 같은 값이다."""
    return to_builtin(_env.get_observation())


@mcp.tool(description=TOOL_DESC["step"])
def step(n: int = 1) -> dict:
    """상태 전진. 에피소드 끝에 걸리면 steps_advanced 가 요청보다 적다.

    상한 10 — 에이전트가 실수로 n=1000 을 넣으면 에피소드가 한 번에 끝난다.
    """
    return to_builtin(_env.step(n))


@mcp.tool(description=TOOL_DESC["apply_allocation"])
def apply_allocation(embb: float, urllc: float, mmtc: float) -> dict:
    """액추에이터. 평활·클립·정규화가 전부 여기서 일어난다 (설계서 §3.2).

    ②의 정책에는 평활이 없다 — 양쪽에 다 있으면 0.7이 두 번 걸려 배분이 거의 안 움직인다.
    """
    return to_builtin(_env.apply_allocation(embb, urllc, mmtc))


@mcp.tool(description=TOOL_DESC["get_history"])
def get_history(n: int = SEQUENCE_LENGTH) -> dict:
    """②의 lstm_forecast 입력 시퀀스.

    columns 를 매번 반환하는 이유 — ②가 순서를 재유도하지 않게 하고 불일치를 런타임에
    검출할 수 있게 한다. 순서가 바뀌면 LSTM 이 조용히 틀린다.
    """
    return to_builtin(_env.get_history(n))


@mcp.tool(description=TOOL_DESC["add_capacity"])
def add_capacity(slice_type: str, amount: float,
                 expires_at_step: int, slice_id: str) -> dict:
    """③ `procure()` 의 capacity_gain · expires_at_step · slice_id 를 에이전트가 중계한다.

    반드시 `step()` **전**에 부른다. 뒤로 가면 용량이 다음 스텝부터 반영되어 조달한
    바로 그 스텝은 효과를 못 본다 (W1).
    """
    return to_builtin(_env.add_capacity(slice_type, amount, expires_at_step, slice_id))


@mcp.tool(description=TOOL_DESC["reset"])
def reset(run_id: str, scenario: str = "normal", seed: int = 0) -> dict:
    """①만 초기화한다. ②③④⑤의 상태는 남는다 (설계서 §5.0).

    run_id 는 ④에도 **같은 값**을 넘겨야 실행 단위 산출물이 step 으로 조인된다.
    """
    return to_builtin(_env.reset(run_id, scenario, seed))


if __name__ == "__main__":
    print(f"[slice-observe] run_id={_env.run_id} scenario={_env.scenario} "
          f"seed={_env.seed} total_steps={_env.total_steps}", file=sys.stderr)
    mcp.run()
