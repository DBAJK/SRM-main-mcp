"""규칙 판단자 — LLM 자리를 메우는 임시 구현.

LLM 을 붙이기 전에 루프 구조를 안정화하기 위한 것이다. 논문의 비교군이
아니다 (비교군은 arms/ 가 정의한다).

이 파일이 하는 일이 곧 decide.py 가 LLM 으로 대체할 일이다:
  situation 추론 · 정책 선택 · 조달 판단
에스컬레이션은 Decision 이 파생시킨다 (schema.py).
"""

import math
import os
from statistics import NormalDist
from typing import Optional

from srm_mcp.policy.rule import DEMAND_BASE, DEMAND_MULT, DEMAND_NOISE

from ..schema import Decision, HISTORY_N, PROCURE_PRESSURE, StepContext

# 이용률이 임계의 몇 배를 넘으면 그 슬라이스가 지배적이라고 볼지 (utilization 방식)
DOMINANT_RATIO = 1.15

# ── 상황 추론 신호 (workplan-2 C-23 · 2026-09-29) ────────────────────────────
#
# 옛 방식(utilization)은 이용률/임계를 봤다. 이용률은 배분의 결과라, 판단자가 emergency 로
# 보고 URLLC 에 더 주면 다음 스텝엔 증상이 사라져 normal 로 돌아선다 — 60스텝 × 12칸에서
# 이벤트 시나리오 정확도 0.10~0.25. 트래픽은 배분·조달과 무관하다(env.py _roll · 같은 시드
# 규칙 vs Claude 트래픽 차 0). 그래서 트래픽 **구성비**를 평시 구성비와 비교한다.
#   · 구성비로 나누는 이유 — 일·주 주기가 세 슬라이스에 같은 배율(최대 ×1.5)을 곱한다. 절대값은
#     평시 낮 시간을 이벤트로 오판한다(normal 0.14). 구성비에서는 공통 배율이 상쇄된다.
#   · 창 평균 이유 — 트래픽 잡음 σ 0.1 이 mmtc 평시값 0.2 의 절반이다.
# 평시 구성비는 ①의 생성 상수가 아니라 **측정값**이다: normal · 시드 10~14 (매트릭스 시드 0~2 와
# 겹치지 않음) · 300스텝 평균, `runs/_matrix/calib-normal`. "운영자가 평소 구성을 안다"는 가정.
# 창 5 · 기준 1.2 는 시드 0~2 장부로 고른 값이다(오프라인 평균 정확도 0.97) — 두 개뿐이지만
# 같은 시드로 고른 것이라 M-0c 수치는 낙관 쪽일 수 있다.
NORMAL_TRAFFIC_SHARE = {"embb": 0.444, "urllc": 0.3311, "mmtc": 0.225}
SHARE_RATIO = 1.2          # 구성비가 평시의 몇 배를 넘으면 그 슬라이스가 지배적인가
TRAFFIC_WINDOW = 5         # 최근 몇 스텝을 평균하나

SLICE_TO_SITUATION = {"urllc": "emergency", "embb": "special_event", "mmtc": "iot_surge"}

# ── 우도 HMM (2026-10-03 · 반복 2) — 기본값 ────────────────────────────────────────
#
# C-23 은 구성비를 평시와 비교하는 문턱(1.2)이라 두 가지를 놓친다. (1) 잡음이 큰 mmtc 구성비가 평시에도
# 문턱을 넘어 normal 을 iot_surge 로 부른다 (after-F arm1 의 normal 오답 32건 중 21건). (2) 각 이벤트의
# 수요 모양(어느 슬라이스가 몇 배인가)을 안 쓰고 1등 슬라이스만 본다. 그래서 상황마다 "이 트래픽이 나올
# 우도"를 계산하고, 상황은 잘 안 바뀐다는 사전(머무름 0.98)으로 스텝을 이어 붙인다 — HMM 전진 필터.
#   우도: 가설 s 의 수요 모양 B·M_s 에 수준 f 를 최소제곱으로 맞추고(일·주 주기라 스텝마다), 잡음
#         σ·M_s 의 정규 우도. 트래픽 하한 0.1 에 붙은 값은 "그 이하"로 본다(중도절단).
#   모형은 ② rule_based `theta_z` 와 **같은 수요 모형**(rule.DEMAND_*)을 한 곳에서 읽는다 — 같은 지식이
#   두 곳에서 갈라지지 않게. 구성비는 시드 10~19 측정과 0.002 안에서 같다.
#   머무름 0.98 은 조정 시드 10~19 로 골랐다 (0.95 → 0.968 · 0.98 → 0.972 · 0.99 → 0.972).
# 측정 (SliceEnv 궤적 · 전환 스텝 제외): 조정 시드 C-23 0.932 → 0.972, 평가 시드 0~2 0.956 → 0.982.
# 확신(conf_situation)은 고른 상황의 사후확률이다.
SITUATION_SIGNAL_DEFAULT = "likelihood"
SITUATIONS = ("normal", "emergency", "special_event", "iot_surge")
LIKELIHOOD_STAY = 0.98
TRAFFIC_FLOOR = 0.1          # ① TRAFFIC_CLIP 하한
_NORMAL = NormalDist()

# 실행별 최근 트래픽. 판단자는 매 스텝 새로 불리는 함수라 여기 들고 있는다.
# 같은 스텝을 다시 판단(재시도)해도 한 번만 센다 — step 을 키로 쓴다.
_traffic_seen: dict[str, dict[int, dict]] = {}
# 실행별 스텝마다의 사후 로그확률 (우도 HMM). 같은 스텝을 다시 판단해도 직전 스텝에서 다시 계산한다.
_belief: dict[str, dict[int, dict[str, float]]] = {}


def reset_run(run_id: str) -> None:
    """한 프로세스에서 같은 run_id 를 다시 돌릴 때(tools/fast_matrix) 이전 상태를 버린다."""
    _traffic_seen.pop(run_id, None)
    _belief.pop(run_id, None)


def situation_signal() -> str:
    """`AGENT_SITUATION_SIGNAL` = likelihood(기본) | traffic(C-23) | utilization(옛 방식). 호출마다 읽는다."""
    name = os.environ.get("AGENT_SITUATION_SIGNAL", SITUATION_SIGNAL_DEFAULT).lower()
    return name if name in ("likelihood", "traffic", "utilization") else SITUATION_SIGNAL_DEFAULT


def rule_decider(ctx: StepContext, proposer) -> Decision:
    situation, conf_situation = infer_situation(ctx)
    policy = pick_policy(ctx)

    prop = proposer.propose(policy, situation)

    # 정책이 실패하면 다른 정책으로 한 번 더 시도한다.
    # ②는 조용한 폴백을 하지 않으므로(spec/policy.md:58) 여기가 그 판단 지점이다.
    considered = []
    if prop.get("status") != "ok":
        considered.append(
            {"policy": policy, "confidence": prop.get("confidence", 0.0),
             "status": prop.get("status")}
        )
        policy = "rule_based"
        prop = proposer.propose(policy, situation)

    return Decision(
        situation=situation,
        policy=prop["policy"],
        allocation=prop.get("allocation"),
        correction=prop.get("correction"),   # ② rule_based 의 보정량 (D1-b)
        conf_intrinsic=float(prop.get("confidence", 0.0)),
        conf_empirical=ctx.effective(prop["policy"]),
        conf_situation=conf_situation,
        rationale=prop.get("rationale", ""),
        procure=ctx.demand_pressure >= PROCURE_PRESSURE,
        in_distribution=bool(prop.get("in_distribution", True)),
        considered=considered,
        demand_class=ctx.demand_class,
    )


def infer_situation(ctx: StepContext) -> tuple[str, float]:
    """관측만으로 상황을 추론한다. (상황, 그 판단에 대한 확신) 을 낸다.

    정답 플래그를 쓰지 않는다 — 어차피 ①이 주지 않는다. 신호는 `situation_signal()`.
    """
    signal = situation_signal()
    if signal == "likelihood":
        return _infer_from_likelihood(ctx)
    if signal == "traffic":
        return _infer_from_traffic(ctx)
    return _infer_from_utilization(ctx)


def _logsumexp(values: list[float]) -> float:
    top = max(values)
    return top + math.log(sum(math.exp(v - top) for v in values))


def traffic_loglik(traffic: dict, situation: str) -> float:
    """상황 가설 하나에서 이 트래픽이 나올 로그우도 (위 주석의 식). 수준 f 는 최소제곱으로 맞춘다."""
    mult = DEMAND_MULT[situation]
    keys = list(DEMAND_BASE)
    free = [k for k in keys if traffic[k] > TRAFFIC_FLOOR + 1e-9] or keys
    level = (sum(DEMAND_BASE[k] * traffic[k] / mult[k] for k in free)
             / sum(DEMAND_BASE[k] ** 2 for k in free))
    level = max(0.5, min(2.0, level))
    ll = 0.0
    for k in keys:
        mean = mult[k] * DEMAND_BASE[k] * level
        sd = DEMAND_NOISE * mult[k]
        if traffic[k] <= TRAFFIC_FLOOR + 1e-9:
            ll += math.log(max(_NORMAL.cdf((TRAFFIC_FLOOR - mean) / sd), 1e-300))
        else:
            z = (traffic[k] - mean) / sd
            ll += -0.5 * z * z - math.log(sd)
    return ll


def _forward(prev: Optional[dict[str, float]], traffic: dict) -> dict[str, float]:
    """전진 필터 한 스텝 — 직전 사후 로그확률(없으면 균등)과 이번 트래픽 → 이번 스텝의 사후 로그확률."""
    if prev is None:
        prev = {s: math.log(1 / len(SITUATIONS)) for s in SITUATIONS}
    stay = math.log(LIKELIHOOD_STAY)
    switch = math.log((1 - LIKELIHOOD_STAY) / (len(SITUATIONS) - 1))
    traffic = {k: float(v) for k, v in traffic.items()}
    post = {s: _logsumexp([prev[p] + (stay if p == s else switch) for p in SITUATIONS])
               + traffic_loglik(traffic, s)
            for s in SITUATIONS}
    norm = _logsumexp(list(post.values()))
    return {s: v - norm for s, v in post.items()}


def situation_posterior(traffics: list[dict], anchors: Optional[dict[int, str]] = None) -> dict[str, float]:
    """트래픽 열(오래된 것부터)의 마지막 스텝 사후확률 — 규칙 판단자와 같은 필터를 처음부터 돌린다.

    오케스트레이터 게이트웨이의 `estimate_situation` · `compute_confidence` 가 쓴다 — 두 드라이버가 같은 계산을 쓴다.
    `anchors` 는 {열 위치: 사람이 답한 라벨} — 그 위치에서 믿음을 답한 라벨 0.99 로 둔다(absorb_label 과 같다).
    """
    logp = None
    for i, traffic in enumerate(traffics):
        logp = _forward(logp, traffic)
        label = (anchors or {}).get(i)
        if label in SITUATIONS:
            rest = (1 - HUMAN_ANSWER_BELIEF) / (len(SITUATIONS) - 1)
            logp = {s: math.log(HUMAN_ANSWER_BELIEF if s == label else rest) for s in SITUATIONS}
    return {s: math.exp(v) for s, v in (logp or {}).items()}


HUMAN_ANSWER_BELIEF = 0.99   # 사람이 답한 라벨에 두는 사후확률 — 다음 스텝 필터는 여기서 이어진다


def absorb_label(run_id: str, step: int, label: str) -> None:
    """개입 때 사람이 답한 상황을 믿음에 반영한다 (2026-10-05 개입 재설계).

    반영하지 않으면 다음 스텝에도 같은 불확실성으로 또 묻는다 — 10시드 mixed 사람 호출 19.2 → 반영 8.0 회,
    SLA 는 같다. 원본 운영자의 선언이 다음 변화까지 유지되던 것과 같다.
    """
    if label not in SITUATIONS:
        return
    rest = (1 - HUMAN_ANSWER_BELIEF) / (len(SITUATIONS) - 1)
    _belief.setdefault(run_id, {})[step] = {
        s: math.log(HUMAN_ANSWER_BELIEF if s == label else rest) for s in SITUATIONS}


def _infer_from_likelihood(ctx: StepContext) -> tuple[str, float]:
    """우도 HMM 전진 필터 한 스텝. (사후확률 최대 상황, 그 사후확률)."""
    seen = _belief.setdefault(ctx.run_id, {})
    earlier = [s for s in seen if s < ctx.step]
    post = _forward(seen[max(earlier)] if earlier else None, ctx.observation["traffic"])
    seen[ctx.step] = post
    best = max(post, key=post.get)
    return best, math.exp(post[best])


def _infer_from_traffic(ctx: StepContext) -> tuple[str, float]:
    """최근 TRAFFIC_WINDOW 스텝 트래픽 평균의 구성비 ÷ 평시 구성비. 가장 큰 배율이
    SHARE_RATIO 미만이면 normal, 아니면 그 슬라이스의 상황. 확신은 utilization 방식과 같은
    모양 — 1등과 2등 배율의 간격(normal 이면 기준까지의 여유)."""
    seen = _traffic_seen.setdefault(ctx.run_id, {})
    seen[ctx.step] = dict(ctx.observation["traffic"])
    steps = sorted(s for s in seen if s <= ctx.step)[-TRAFFIC_WINDOW:]
    keys = list(NORMAL_TRAFFIC_SHARE)
    avg = {k: sum(float(seen[s][k]) for s in steps) / len(steps) for k in keys}
    total = sum(avg.values())
    if total <= 0:
        return "normal", 0.5
    ratio = {k: (avg[k] / total) / NORMAL_TRAFFIC_SHARE[k] for k in keys}

    ordered = sorted(ratio.values(), reverse=True)
    top = max(ratio, key=ratio.get)
    if ratio[top] < SHARE_RATIO:
        return "normal", min(1.0, 0.5 + (SHARE_RATIO - ratio[top]))
    return SLICE_TO_SITUATION[top], min(1.0, 0.5 + (ordered[0] - ordered[1]))


def _infer_from_utilization(ctx: StepContext) -> tuple[str, float]:
    """옛 방식. 이용률 / 임계값 비가 가장 큰 슬라이스를 보고 해당 상황으로 판정하고,
    1등과 2등의 간격을 확신으로 삼는다. 간격이 좁으면 어느 상황인지 애매하다.
    ⚠️ 이용률은 배분의 결과라 대응하면 증상이 사라진다 — 위 C-23 주석.
    """
    obs = ctx.observation
    util, thr = obs["utilization"], obs["thresholds"]
    ratio = {k: util[k] / max(thr[k], 1e-9) for k in util}

    ordered = sorted(ratio.values(), reverse=True)
    margin = ordered[0] - ordered[1]
    conf = min(1.0, 0.5 + margin)

    top = max(ratio, key=ratio.get)
    if ratio[top] < DOMINANT_RATIO:
        # 임계에 못 미치면 평시로 본다. 1등이 임계에 가까울수록 확신이 낮다.
        return "normal", min(1.0, 0.5 + (DOMINANT_RATIO - ratio[top]))
    return SLICE_TO_SITUATION[top], conf


def pick_policy(ctx: StepContext) -> str:
    """검증된 정책 중 경험적 신뢰도가 가장 높은 것을 고른다.

    이력이 10스텝 미만이면 lstm_forecast 는 어차피 unavailable 이므로 제외한다
    (spec/policy.md:150).

    ⚠️ n=0 인 정책을 effective 로 같이 줄 세우면 안 된다. 그 값은 성적이 아니라
    사전값(0.5)이고, 성적표를 쌓은 정책은 0.5 아래로 내려가므로 **한 번도 안
    써본 정책이 항상 이긴다.**

    그래서 검증된 정책이 하나라도 있으면 그 안에서만 고른다. 부작용으로 이
    판단자는 lstm_forecast 를 쓰지 않는다. **의도된 동작이다** (workplan-2 C-13) —
    이 판단자는 비교군의 기준선이라 고정해 두고, 미검증 정책을 언제 시험할지라는
    판단은 LLM · 오케스트레이터 칸에서 잰다.

    예전에는 여기에 "고르면 확신이 τ 아래라 개입으로 튕긴다"는 근거도 있었다
    (recent_error 가 null → ② 기본값 0.5 → conf 0.2231). B-3 이후 ⑤가 n=0 에
    사전값 0.2 를 내므로 lstm 의 conf 는 0.549 > τ 다 — 그 근거는 사라졌고, 남은
    근거는 위의 "같은 자로 비교할 수 없다" 하나다.
    """
    candidates = ["rule_based"]
    if (ctx.history or {}).get("n_available", 0) >= HISTORY_N:
        candidates.append("lstm_forecast")

    proven = [p for p in candidates if ctx.samples(p) > 0]
    return max(proven or candidates, key=ctx.effective)


# 루프가 개입 때 사람의 답을 넘겨주는 자리 (loop.run_step 이 getattr 로 찾는다).
rule_decider.on_human_label = absorb_label
