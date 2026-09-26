"""규칙 판단자 — LLM 자리를 메우는 임시 구현.

LLM 을 붙이기 전에 루프 구조를 안정화하기 위한 것이다. 논문의 비교군이
아니다 (비교군은 arms/ 가 정의한다).

이 파일이 하는 일이 곧 decide.py 가 LLM 으로 대체할 일이다:
  situation 추론 · 정책 선택 · 조달 판단
에스컬레이션은 Decision 이 파생시킨다 (schema.py).
"""

from ..schema import Decision, HISTORY_N, PROCURE_PRESSURE, StepContext

# 이용률이 임계의 몇 배를 넘으면 그 슬라이스가 지배적이라고 볼지
DOMINANT_RATIO = 1.15


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

    정답 플래그를 쓰지 않는다 — 어차피 ①이 주지 않는다.
    이용률 / 임계값 비가 가장 큰 슬라이스를 보고 해당 상황으로 판정하고,
    1등과 2등의 간격을 확신으로 삼는다. 간격이 좁으면 어느 상황인지 애매하다.
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
    return {"urllc": "emergency", "embb": "special_event", "mmtc": "iot_surge"}[top], conf


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
