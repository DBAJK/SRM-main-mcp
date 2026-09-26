"""5개 서버 도구 21개의 호출 창구.

백엔드를 주입받는다 — 인프로세스 목이든 실제 MCP 서버든 루프 코드는 같다.
모든 반환값이 Guard 를 통과한다 (오류 메시지도 포함).

계약: claude/spec/tools.md
"""

import logging
from typing import Any, Optional, Protocol

from .guard import Guard
from .trace import MARK, brief

logger = logging.getLogger(__name__)


class Backend(Protocol):
    """도구 하나를 부르는 방법. 전송 방식을 여기서 갈라낸다."""

    def call(self, server: str, tool: str, args: dict) -> Any: ...


class Tools:
    """서버별 네임스페이스 없이 평평하게 노출한다.

    도구 이름이 5개 서버에 걸쳐 유일하므로 충돌이 없고, 호출부가 짧아진다.
    부작용 있는 도구는 호출 횟수를 센다 (spec/tools.md:29).
    """

    SIDE_EFFECTS = {
        "step",
        "apply_allocation",
        "add_capacity",
        "reset",
        "procure",
        "update_rating",
        "record_decision",
        "record_escalation",
        "report_outcome",
    }

    def __init__(self, backend: Backend, guard: Optional[Guard] = None):
        self._backend = backend
        self._guard = guard or Guard()
        self.calls: dict[str, int] = {}

    # ── 내부 ──────────────────────────────────────────────────────────
    def _call(self, server: str, tool: str, **args) -> Any:
        args = {k: v for k, v in args.items() if v is not None}
        out = self._backend.call(server, tool, args)
        self.calls[tool] = self.calls.get(tool, 0) + 1
        out = self._guard.check(out, f"{server}.{tool}")

        if logger.isEnabledFor(logging.DEBUG):
            mark = MARK.get(server, " ")
            logger.debug(
                "  %s %-24s → %s", mark, tool, brief(out),
                extra={"full": f"  {mark} {tool}({brief(args, 10**6)})"
                               f"\n      → {brief(out, 10**6)}"},
            )
        return out

    def reset_counts(self) -> dict:
        prev, self.calls = self.calls, {}
        return prev

    @property
    def side_effect_count(self) -> int:
        return sum(n for t, n in self.calls.items() if t in self.SIDE_EFFECTS)

    # ── ① observe ────────────────────────────────────────────────────
    def get_observation(self) -> dict:
        return self._call("observe", "get_observation")

    def step(self, n: int = 1) -> dict:
        return self._call("observe", "step", n=n)

    def apply_allocation(self, embb: float, urllc: float, mmtc: float) -> dict:
        return self._call(
            "observe", "apply_allocation", embb=embb, urllc=urllc, mmtc=mmtc
        )

    def get_history(self, n: int = 10) -> dict:
        return self._call("observe", "get_history", n=n)

    def add_capacity(
        self, slice_type: str, amount: float, expires_at_step: int, slice_id: str
    ) -> dict:
        return self._call(
            "observe",
            "add_capacity",
            slice_type=slice_type,
            amount=amount,
            expires_at_step=expires_at_step,
            slice_id=slice_id,
        )

    def reset(self, run_id: str, scenario: str = "normal", seed: int = 0) -> dict:
        return self._call(
            "observe", "reset", run_id=run_id, scenario=scenario, seed=seed
        )

    # ── ② policy ─────────────────────────────────────────────────────
    def list_policies(self) -> list:
        return self._call("policy", "list_policies")

    def propose_allocation(
        self,
        policy: str,
        observation: dict,
        situation: str,
        history: Optional[dict] = None,
        recent_error: Optional[float] = None,
    ) -> dict:
        # situation 은 기본값이 없다 (spec/policy.md:43)
        return self._call(
            "policy",
            "propose_allocation",
            policy=policy,
            observation=observation,
            situation=situation,
            history=history,
            recent_error=recent_error,
        )

    def compare_policies(
        self,
        observation: dict,
        situation: str,
        history: Optional[dict] = None,
        recent_errors: Optional[dict] = None,
    ) -> list:
        # 반환량이 propose 의 3배다. 정책 전환을 고민할 때만 (spec/policy.md:128)
        return self._call(
            "policy",
            "compare_policies",
            observation=observation,
            situation=situation,
            history=history,
            recent_errors=recent_errors,
        )

    def classify_demand(self, observation: dict) -> dict:
        return self._call("policy", "classify_demand", observation=observation)

    # ── ③ market ─────────────────────────────────────────────────────
    def list_offerings(
        self, slice_type: Optional[str] = None, region: Optional[str] = None
    ) -> list:
        return self._call(
            "market", "list_offerings", slice_type=slice_type, region=region
        )

    # 파라미터명은 qos_requirements 다. spec/tools.md 요약표는 qos 로 적혀
    # 있으나 상세 계약(spec/market.md:61,105,143)이 qos_requirements 이므로
    # 그쪽을 따른다. 키에 단위를 붙이지 않는다 — latency_ms 가 아니라 latency
    # (틀리면 전부 기본값으로 떨어져 모든 벤더가 같은 점수를 받는다).
    def score_offerings(self, slice_type: str, qos_requirements: dict) -> list:
        return self._call(
            "market",
            "score_offerings",
            slice_type=slice_type,
            qos_requirements=qos_requirements,
        )

    def explain_score(
        self, vendor_id: str, slice_type: str, qos_requirements: dict
    ) -> dict:
        return self._call(
            "market",
            "explain_score",
            vendor_id=vendor_id,
            slice_type=slice_type,
            qos_requirements=qos_requirements,
        )

    def procure(
        self,
        vendor_id: str,
        slice_type: str,
        qos_requirements: dict,
        duration_steps: int,
        current_step: int,
    ) -> dict:
        return self._call(
            "market",
            "procure",
            vendor_id=vendor_id,
            slice_type=slice_type,
            qos_requirements=qos_requirements,
            duration_steps=duration_steps,
            current_step=current_step,
        )

    def update_rating(self, vendor_id: str, outcome: dict) -> dict:
        return self._call(
            "market", "update_rating", vendor_id=vendor_id, outcome=outcome
        )

    # ── ④ audit ──────────────────────────────────────────────────────
    def record_decision(self, **kwargs) -> dict:
        # 필수: step, observation, situation, chosen_policy, allocation,
        #       confidence, rationale  (spec/audit.md:9~24)
        return self._call("audit", "record_decision", **kwargs)

    def record_escalation(
        self,
        step: int,
        observation: dict,
        situation: str,
        reason: str,
        confidence: dict,
        slice_id: Optional[str] = None,
        vendor_id: Optional[str] = None,
        cost_total: Optional[float] = None,
        chosen_policy: Optional[str] = None,
        config: Optional[dict] = None,
    ) -> dict:
        # 이 호출 자체가 개입 1회다 (spec/audit.md:53)
        # 조달 3필드는 record_decision 과 같은 중계선이다 (audit/server.py:84)
        # chosen_policy 는 에이전트가 고르려던 정책이다 (workplan A-1). ④는 실행된 폴백을
        # chosen_policy 에 그대로 두고 이 값을 agent_policy 로 따로 남긴다.
        return self._call(
            "audit",
            "record_escalation",
            step=step,
            observation=observation,
            situation=situation,
            reason=reason,
            confidence=confidence,
            slice_id=slice_id,
            vendor_id=vendor_id,
            cost_total=cost_total,
            chosen_policy=chosen_policy,
            config=config,
        )

    def get_decisions(self, n: int = 10, kind: Optional[str] = None) -> list:
        # 레코드마다 observation 이 통째로 들어 있다. n <= 10 (spec/audit.md:100)
        return self._call("audit", "get_decisions", n=n, kind=kind)

    def get_metrics(self, window: Optional[int] = None) -> dict:
        return self._call("audit", "get_metrics", window=window)

    # ── ⑤ feedback ───────────────────────────────────────────────────
    def report_outcome(self, decision_id: str, observed: dict) -> dict:
        # 반드시 step() 이후 (spec/feedback.md:12)
        return self._call(
            "feedback", "report_outcome", decision_id=decision_id, observed=observed
        )

    def get_reliability_table(self) -> dict:
        return self._call("feedback", "get_reliability_table")
