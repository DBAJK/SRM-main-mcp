"""LLM 판단자.

rule.py 가 임의의 임계값으로 하던 세 가지를 LLM 이 한다:
    상황 추론 · 정책 선택 · 조달 판단

**계산은 하지 않는다.** 배분 숫자는 ②가, 경험적 신뢰도는 ⑤가, combined 와
에스컬레이션은 schema.py 가 낸다. LLM 이 만드는 값은 자기 판단과 그 판단에
대한 확신뿐이다 — 신뢰도 공식에 손을 대면 개입률이 모델 기분에 따라 흔들려
비교가 무의미해진다.

정답 플래그를 보지 않는다. 프롬프트는 전부 도구 반환값에서 나오고, 그
반환값은 이미 Guard 를 통과한 것이다. 응답도 한 번 더 검사한다.
"""

import json
import logging
from typing import Any, Optional

from ..guard import Guard
from ..llm import LLM, LLMError
from ..schema import Decision, StepContext
from ..trace import brief

logger = logging.getLogger(__name__)

SITUATIONS = ("normal", "emergency", "special_event", "iot_surge")
POLICIES = ("rule_based", "lstm_forecast", "dqn")

SYSTEM = """\
너는 5G 네트워크 슬라이싱 오케스트레이터다. 매 스텝 관측을 받아 세 가지를 정한다.

1. situation — 지금 망이 어떤 상황인지
     normal         특이사항 없음
     emergency      긴급 통신 수요가 지배적
     special_event  대규모 인파·행사성 트래픽이 지배적
     iot_surge      다수 소형 단말의 접속이 지배적
2. policy — 배분을 누구에게 맡길지. 가능한 것만 고른다.
3. procure — 외부 벤더에게서 용량을 조달할지

판단 근거는 주어진 숫자와 사람이 준 의도뿐이다. 정답 라벨은 주어지지 않는다.

정책 선택 기준:
  effective 는 그 정책의 과거 성적(0~1)이고 n 은 표본 수다. n=0 이면 effective 는
  성적이 아니라 사전값이므로, 성적표를 쌓은 정책과 같은 자로 비교할 수 없다.
  recent_error 가 크면 최근 빗나가고 있다.
  성적이 높은 쪽이 기본이지만, 상황이 평소와 다르다고 보면 바꿔도 된다.

  알아둘 것: n=0 인 정책의 recent_error 는 실측이 아니라 사전값이다(⑤가 유도한다).
  그래서 한 번도 안 써본 정책도 확신이 τ 아래로 깔리지는 않지만, 그 수치는 성적이
  아니므로 n 이 쌓인 정책의 recent_error 와 같은 자로 읽지 않는다.

조달 기준:
  demand_pressure 는 수요가 가용 용량을 넘는 정도다. 1.0 이상이면 배분을
  어떻게 나눠도 모자란다는 뜻이다. 조달에는 비용이 든다.

반드시 아래 JSON 객체 하나만 출력한다. 설명·코드펜스·머리말을 붙이지 않는다.

{"situation": "<위 넷 중 하나>",
 "situation_confidence": <0.0~1.0, 그 상황 판단이 얼마나 확실한가>,
 "policy": "<가능한 정책 중 하나>",
 "procure": <true 또는 false>,
 "reasoning": "<왜 그렇게 봤는지 한국어 한 문장>"}

situation_confidence 는 상황 판단에 대한 확신만 말한다. 배분의 정확도나
정책의 성적을 뜻하지 않는다 — 그 둘은 다른 데서 계산된다. 애매하면 낮게 준다.
"""


class LlmDecider:
    """Decider 인터페이스. loop.py 는 이게 LLM 인지 규칙인지 모른다."""

    def __init__(
        self,
        llm: LLM,
        guard: Optional[Guard] = None,
        max_retries: int = 1,
    ):
        self._llm = llm
        self._guard = guard or Guard(enabled=True)
        self._max_retries = max_retries

        # 실험 보고용
        self.malformed = 0
        self.policy_switches = 0

    def __call__(self, ctx: StepContext, proposer) -> Decision:
        ans = self._ask(ctx, failure=None)
        situation = ans["situation"]

        prop = proposer.propose(ans["policy"], situation)

        considered: list = []
        if prop.get("status") != "ok":
            # ②는 조용한 폴백을 하지 않는다 (spec/policy.md:58). 대안을 고르는
            # 것은 판단이므로 LLM 에게 다시 묻는다 — 여기가 규칙판단자와
            # 갈리는 지점이다. rule.py 는 무조건 rule_based 로 떨어뜨린다.
            considered.append(
                {
                    "policy": ans["policy"],
                    "confidence": prop.get("confidence", 0.0),
                    "status": prop.get("status"),
                }
            )
            self.policy_switches += 1
            retry = self._ask(ctx, failure={**considered[0],
                                            "reason": prop.get("reason")})
            situation = retry["situation"]
            prop = proposer.propose(retry["policy"], situation)
            ans = retry

        return Decision(
            situation=situation,
            policy=prop["policy"],
            allocation=prop.get("allocation"),
            conf_intrinsic=float(prop.get("confidence", 0.0)),   # ②가 낸 값
            conf_empirical=ctx.effective(prop["policy"]),        # ⑤가 낸 값
            conf_situation=ans["situation_confidence"],          # LLM 이 낸 값
            rationale=self._rationale(ans, prop),
            procure=ans["procure"],
            in_distribution=bool(prop.get("in_distribution", True)),
            considered=considered,
            demand_class=ctx.demand_class,
        )

    # ── 내부 ──────────────────────────────────────────────────────────
    def _ask(self, ctx: StepContext, failure: Optional[dict]) -> dict:
        """묻고 검증한다. 형식을 못 지키면 한 번 고쳐 묻고, 그래도면 던진다.

        형식 위반을 조용히 정규화하지 않는다 — LLM 이 얼마나 형식을 지키는지가
        논문의 측정 대상이라, 감춰버리면 그 수치가 사라진다.
        """
        user = self._prompt(ctx, failure)
        self._guard.check_text(user, f"llm.prompt(step={ctx.step})")

        last: Optional[str] = None
        for attempt in range(self._max_retries + 1):
            ask = user if last is None else f"{user}\n\n직전 응답이 거부됐다: {last}\n형식을 지켜 다시 답해라."
            logger.debug(
                "  ▸ LLM 질의 %d자%s", len(ask), " (재질의)" if last else "",
                extra={"full": f"  ▸ LLM 질의\n{_indent(SYSTEM)}\n  ── 입력 ──\n{_indent(ask)}"},
            )
            raw = self._llm.ask(SYSTEM, ask)
            self._guard.check_text(raw, f"llm.response(step={ctx.step})")
            logger.debug(
                "  ◂ LLM 응답 %s", brief(raw),
                extra={"full": f"  ◂ LLM 응답\n{_indent(raw)}"},
            )

            try:
                from ..llm import extract_json

                return self._validate(extract_json(raw), ctx)
            except (LLMError, ValueError) as e:
                self.malformed += 1
                last = str(e)
                logger.warning("스텝 %d LLM 응답 거부(%d): %s", ctx.step, attempt + 1, last)

        raise LLMError(f"스텝 {ctx.step}: {self._max_retries + 1}회 모두 형식 위반 — {last}")

    def _validate(self, out: dict, ctx: StepContext) -> dict:
        sit = out.get("situation")
        if sit not in SITUATIONS:
            raise ValueError(f"situation 이 {SITUATIONS} 밖: {sit!r}")

        pol = out.get("policy")
        if pol not in POLICIES:
            raise ValueError(f"policy 가 {POLICIES} 밖: {pol!r}")

        try:
            conf = float(out.get("situation_confidence"))
        except (TypeError, ValueError):
            raise ValueError(
                f"situation_confidence 가 수가 아니다: {out.get('situation_confidence')!r}"
            ) from None
        if not 0.0 <= conf <= 1.0:
            raise ValueError(f"situation_confidence 가 0~1 밖: {conf}")

        if not isinstance(out.get("procure"), bool):
            raise ValueError(f"procure 가 bool 이 아니다: {out.get('procure')!r}")

        return {
            "situation": sit,
            "policy": pol,
            "situation_confidence": conf,
            "procure": out["procure"],
            "reasoning": str(out.get("reasoning", "")).strip(),
        }

    def _prompt(self, ctx: StepContext, failure: Optional[dict]) -> str:
        blocks = []

        if ctx.intent:
            blocks.append(f"[사람이 준 의도]\n{ctx.intent}")

        blocks.append(f"[스텝]\n{ctx.step}")
        blocks.append(f"[관측]\n{_j(ctx.observation)}")

        if ctx.demand_class:
            blocks.append(f"[수요 분류기]\n{_j(ctx.demand_class)}")

        blocks.append(f"[정책별 성적]\n{_j(ctx.reliability)}")
        blocks.append(f"[사용 가능한 정책]\n{', '.join(_available(ctx))}")

        if failure:
            blocks.append(
                f"[직전 시도 실패]\n{_j(failure)}\n"
                "이 정책은 이번 스텝에 쓸 수 없다. 다른 정책을 골라라."
            )

        return "\n\n".join(blocks)

    @staticmethod
    def _rationale(ans: dict, prop: dict) -> str:
        """④에 남는 근거. 사람이 나중에 읽을 유일한 문장이다."""
        mine = ans.get("reasoning") or "(근거 없음)"
        theirs = prop.get("rationale", "")
        return f"{mine} | ②{prop.get('policy')}: {theirs}" if theirs else mine


def _available(ctx: StepContext) -> list[str]:
    """이번 스텝에 실제로 시도할 수 있는 정책.

    lstm_forecast 는 이력 10스텝이 전제다 (spec/policy.md:150). dqn 은 1차
    범위 밖이라 ②가 unavailable 을 낸다 — 목록에 넣지 않고, LLM 이 굳이
    고르면 실패 경로가 받아낸다.
    """
    out = ["rule_based"]
    if (ctx.history or {}).get("n_available", 0) >= 10:
        out.append("lstm_forecast")
    return out


def _j(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, sort_keys=True, default=str)


def _indent(text: str, pad: str = "      ") -> str:
    """추적 파일에 프롬프트 전문을 남길 때 본문과 구분되게 민다."""
    return "\n".join(pad + line for line in text.splitlines())
