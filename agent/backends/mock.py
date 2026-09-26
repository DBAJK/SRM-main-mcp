"""인프로세스 목 백엔드.

A·B가 실제 서버를 내놓기 전까지 루프를 돌리기 위한 임시물이다.
**시뮬레이션 충실도는 목표가 아니다** — 응답 형태가 명세와 맞는지,
호출 순서가 성립하는지를 검증하는 것이 목적이다.

실제 서버가 나오면 backends/mcp.py 로 갈아끼운다. 루프 코드는 바뀌지 않는다.

주의: 여기서 나가는 값에 FORBIDDEN 키가 없어야 한다. Guard 가 잡는다.

**계약이 바뀌는 식은 베끼지 않고 서버 모듈을 그대로 쓴다** (workplan-2 C-14). ② rule_based ·
⑤ 신뢰도 · ④ confidence 검사가 그렇다 — 셋 다 순수 함수라 서버를 띄우지 않고 부를 수 있다.
베껴 두었다가 B-1 · B-2 · B-3 · A-2 가 들어온 뒤 목만 옛 계약으로 남았던 것이 이유다.
시뮬레이션 수치(용량 · 트래픽)는 여전히 실제와 다르다 — 목은 배선 검증용이고 수치 비교에 쓰지 않는다.
"""

import math
import random
from typing import Any

from srm_mcp.audit.book import bad_confidence        # ④ A-2 — 키 누락 · 숫자 아님 거부
from srm_mcp.common.const import INIT_ALLOCATION     # ④ 폴백 배분 (book.py 와 같은 상수)
from srm_mcp.feedback import reliability as rel      # ⑤ EMA · 축소 · recent_error 사전값(B-3)
from srm_mcp.policy import rule                      # ② rule_based — 위반 보정(B-1) 포함

# ⑤가 개입 스텝의 성적을 담는 자리 (B-2). feedback/server.py 의 FALLBACK_BUCKET 과 같은 이름.
# 정책이 아니므로 get_reliability_table 에는 안 나간다.
FALLBACK_BUCKET = "fallback"

SLICES = ("embb", "urllc", "mmtc")
THRESHOLDS = {"embb": 0.9, "urllc": 1.2, "mmtc": 0.8}
STABILITY = 0.7  # spec/observe.md:100

TOTAL_STEPS = {
    "normal": 60,
    "emergency": 60,
    "special_event": 60,
    "iot_surge": 60,
    "mixed": 120,
}

# 시나리오별 트래픽 배수. 실제 ①은 ml_orchestrator_demo.py:286 을 쓴다.
MULT = {
    "normal": {"embb": 1.0, "urllc": 1.0, "mmtc": 1.0},
    "emergency": {"embb": 1.0, "urllc": 2.0, "mmtc": 1.0},
    "special_event": {"embb": 1.5, "urllc": 1.0, "mmtc": 1.0},
    "iot_surge": {"embb": 1.0, "urllc": 1.0, "mmtc": 1.8},
}

REFERENCE_BANDWIDTH = {"eMBB": 1100, "URLLC": 500, "mMTC": 120}
GAIN_SCALE = 0.25
CAPACITY_MAX = 2.0
MINUTES_PER_STEP = 15

VENDORS = [
    {"vendor_id": "vendor-1", "name": "TelcoNet Solutions", "bandwidth": 500.0, "cost": 250.0, "rating": 4.8},
    {"vendor_id": "vendor-2", "name": "GlobalConnect 5G", "bandwidth": 400.0, "cost": 220.0, "rating": 4.5},
    {"vendor_id": "vendor-3", "name": "NextGen Networks", "bandwidth": 600.0, "cost": 300.0, "rating": 4.9},
]


class MockBackend:
    """5개 서버를 한 객체로 흉내 낸다."""

    def __init__(self, seed: int = 0):
        self._rng = random.Random(seed)
        self.run_id = "mock"
        self.scenario = "normal"
        self.total_steps = 60
        self.step_no = 0
        self.allocation = {"embb": 0.4, "urllc": 0.4, "mmtc": 0.2}
        self.capacity = {k: 1.0 for k in SLICES}
        self.leases: list[dict] = []
        self.history: list[list[float]] = []
        self.decisions: dict[str, dict] = {}
        self.escalations = 0
        self.procurements = 0
        self.cost_total = 0.0
        # ⑤ initial_entry 그대로 — r₀ 0.5 · n 0 · errors []. n=0 의 recent_error 는
        # view() 가 1 − POLICY_PRIOR 로 유도한다 (B-3). 예전 값(r 0.9/0.8/0.4 · err 0.1/0.15/0.4)은
        # 실서버와 달라서, 목으로 잡은 회귀가 실서버에서 재현되지 않았다.
        self.reliability = rel.initial_table()
        self._traffic = self._gen_traffic()

    # ── 라우팅 ────────────────────────────────────────────────────────
    def call(self, server: str, tool: str, args: dict) -> Any:
        fn = getattr(self, f"_{tool}", None)
        if fn is None:
            raise NotImplementedError(f"목에 없는 도구: {server}.{tool}")
        return fn(**args)

    # ── ① observe ────────────────────────────────────────────────────
    def _get_observation(self) -> dict:
        util = {
            k: self._traffic[k] / max(self.allocation[k] * self.capacity[k], 1e-9)
            for k in SLICES
        }
        # Σᵢ traffic / (θ × capacity). 평균이 아니라 합이다 (spec/observe.md:23,
        # 범위 0~3). 1.0 초과면 재배분만으로는 해결 불가.
        pressure = sum(
            self._traffic[k] / (THRESHOLDS[k] * self.capacity[k]) for k in SLICES
        )
        hour = (self.step_no * MINUTES_PER_STEP // 60) % 24
        return {
            "step": self.step_no,
            "sim_time": {"hour_of_day": hour, "day_of_week": 0, "is_weekend": False},
            "traffic": {k: round(self._traffic[k], 3) for k in SLICES},
            "allocation": {k: round(self.allocation[k], 3) for k in SLICES},
            "utilization": {k: round(util[k], 3) for k in SLICES},
            "capacity": {k: round(self.capacity[k], 3) for k in SLICES},
            "thresholds": dict(THRESHOLDS),
            "violations": {k: bool(util[k] > THRESHOLDS[k]) for k in SLICES},
            "client_count": 0.6,
            "bs_count": 0.5,
            "demand_pressure": round(pressure, 3),
        }

    def _step(self, n: int = 1) -> dict:
        advanced = 0
        for _ in range(n):
            if self.step_no >= self.total_steps:
                break
            self.step_no += 1
            self._expire()          # 만료가 트래픽 생성보다 먼저 (spec/observe.md:68)
            self._traffic = self._gen_traffic()
            self._push_history()
            advanced += 1
        return {
            "steps_advanced": advanced,
            "episode_done": self.step_no >= self.total_steps,
            "observation": self._get_observation(),
        }

    def _apply_allocation(self, embb: float, urllc: float, mmtc: float) -> dict:
        req = {"embb": embb, "urllc": urllc, "mmtc": mmtc}
        if any(v is None or v < 0 or math.isnan(v) for v in req.values()) or sum(req.values()) <= 0:
            return {
                "accepted": False,
                "requested": None,
                "normalized": dict(self.allocation),
                "delta": 0.0,
                "reason": "rejected: invalid input; allocation unchanged",
            }
        s = sum(req.values())
        norm = {k: v / s for k, v in req.items()}
        sm = {k: STABILITY * self.allocation[k] + (1 - STABILITY) * norm[k] for k in SLICES}
        cl = {k: min(max(v, 0.1), 0.8) for k, v in sm.items()}
        t = sum(cl.values())
        final = {k: v / t for k, v in cl.items()}
        delta = sum(abs(norm[k] - final[k]) for k in SLICES) / 2
        self.allocation = final
        return {
            "accepted": True,
            "requested": {k: round(norm[k], 3) for k in SLICES},
            "normalized": {k: round(final[k], 3) for k in SLICES},
            "delta": round(delta, 3),
            "reason": f"smoothed({STABILITY}); within clip [0.1, 0.8]",
        }

    def _get_history(self, n: int = 10) -> dict:
        avail = self.history[-n:]
        return {
            "n_requested": n,
            "n_available": len(avail),
            "columns": [
                "traffic_load", "hour_of_day", "day_of_week",
                "embb_allocation", "urllc_allocation", "mmtc_allocation",
                "embb_utilization", "urllc_utilization", "mmtc_utilization",
                "client_count", "bs_count",
            ],
            "features": avail,
        }

    def _add_capacity(self, slice_type, amount, expires_at_step, slice_id) -> dict:
        key = slice_type.lower()
        if self.capacity[key] + amount > CAPACITY_MAX:
            return {
                "accepted": False,
                "capacity": {k: round(self.capacity[k], 3) for k in SLICES},
                "demand_pressure": self._get_observation()["demand_pressure"],
                "active_leases": list(self.leases),
                "reason": f"capacity_cap_exceeded: {key} {self.capacity[key]:.2f} + {amount:.2f} > {CAPACITY_MAX}",
            }
        self.capacity[key] += amount
        self.leases.append(
            {"slice_id": slice_id, "slice_type": slice_type,
             "amount": amount, "expires_at_step": expires_at_step}
        )
        return {
            "accepted": True,
            "capacity": {k: round(self.capacity[k], 3) for k in SLICES},
            "demand_pressure": self._get_observation()["demand_pressure"],
            "active_leases": list(self.leases),
            "reason": None,
        }

    def _reset(self, run_id: str, scenario: str = "normal", seed: int = 0) -> dict:
        self.__init__(seed=seed)
        self.run_id = run_id
        self.scenario = scenario
        self.total_steps = TOTAL_STEPS.get(scenario, 60)
        self._traffic = self._gen_traffic()
        self._push_history()
        return {
            "run_id": run_id,
            "scenario": scenario,
            "capacity": dict(self.capacity),
            "seed": seed,
            "total_steps": self.total_steps,
            "observation": self._get_observation(),
        }

    # ── ② policy ─────────────────────────────────────────────────────
    def _list_policies(self) -> list:
        return [
            {"name": "rule_based", "description": "임계값 기반 배분. 상황 라벨을 입력으로 받는다.",
             "requires": None, "available": True, "unavailable_reason": None},
            {"name": "lstm_forecast", "description": "시계열 모델 기반 배분. 관측 이력 10스텝 필요.",
             "requires": "history >= 10", "available": True, "unavailable_reason": None},
            {"name": "dqn", "description": "강화학습 정책 기반 배분.",
             "requires": "trained weights", "available": False,
             "unavailable_reason": "no trained weights"},
        ]

    def _propose_allocation(self, policy, observation, situation,
                            history=None, recent_error=None) -> dict:
        if policy == "dqn":
            return self._fail(policy, "unavailable", "no trained weights")
        if policy == "lstm_forecast":
            n = (history or {}).get("n_available", 0)
            if n < 10:
                return self._fail(policy, "unavailable", f"history_insufficient: {n} < 10")
            err = 0.5 if recent_error is None else recent_error
            return {
                "policy": policy,
                "allocation": self._normalize_target(observation),
                "confidence": round(math.exp(-3 * err), 3),
                "in_distribution": True,
                "status": "ok",
                "reason": None,
                "rationale": f"최근 예측 오차 {err:.3f} 기준 시계열 추정.",
            }

        # ② rule_based 를 그대로 부른다 — 목표표 · 위반 보정(SLICE_RULE_CORRECTION) · 확신 ·
        # 근거 문장까지 실서버와 같다. 반올림은 ②의 _tidy 와 같게 (배분 6자리 · 신뢰도 4자리).
        allocation = rule.propose(observation, situation)
        return {
            "policy": policy,
            "allocation": {k: round(float(v), 6) for k, v in allocation.items()},
            "confidence": round(float(rule.confidence(observation)), 4),
            "in_distribution": True,
            "status": "ok",
            "reason": None,
            "rationale": rule.rationale(observation, situation, allocation),
        }

    def _compare_policies(self, observation, situation, history=None,
                          recent_errors=None) -> list:
        errs = recent_errors or {}
        return [
            self._propose_allocation(
                p, observation, situation, history,
                (errs.get(p) or {}).get("recent_error") if isinstance(errs.get(p), dict) else errs.get(p),
            )
            for p in ("rule_based", "lstm_forecast", "dqn")
        ]

    def _classify_demand(self, observation) -> dict:
        util = observation["utilization"]
        tot = sum(util.values()) or 1.0
        probs = {
            "eMBB": round(util["embb"] / tot, 3),
            "URLLC": round(util["urllc"] / tot, 3),
            "mMTC": round(util["mmtc"] / tot, 3),
        }
        ordered = sorted(probs.values(), reverse=True)
        return {
            "dominant": max(probs, key=probs.get),
            "probabilities": probs,
            "margin": round(ordered[0] - ordered[1], 3),
            "available": True,
        }

    # ── ③ market ─────────────────────────────────────────────────────
    def _list_offerings(self, slice_type=None, region=None) -> list:
        return [dict(v, slice_type=slice_type or "URLLC") for v in VENDORS]

    def _score_offerings(self, slice_type, qos_requirements) -> list:
        out = []
        for v in VENDORS:
            score = 60 + v["rating"] * 6 + (v["bandwidth"] / 100)
            out.append({
                "rank": 0, "vendor_id": v["vendor_id"], "name": v["name"],
                "score": round(min(score, 100.0), 2),
                "rating": v["rating"], "cost": v["cost"],
            })
        out.sort(key=lambda o: o["score"], reverse=True)
        for i, o in enumerate(out, 1):
            o["rank"] = i
        return out

    def _explain_score(self, vendor_id, slice_type, qos_requirements) -> dict:
        s = next(o for o in self._score_offerings(slice_type, qos_requirements)
                 if o["vendor_id"] == vendor_id)
        return {
            "total": s["score"],
            "criteria_scores": {"latency": 1.0, "bandwidth": 1.0, "reliability": 1.0,
                                "reputation": round(s["rating"] / 5, 3), "price": 1.0},
            "weights": {"latency": 0.35, "bandwidth": 0.10, "reliability": 0.25,
                        "reputation": 0.20, "price": 0.20},
            "contributions": {},
            "explanation": "목 구현. 실제 값은 engine.py 분해가 필요하다.",
        }

    def _procure(self, vendor_id, slice_type, qos_requirements,
                 duration_steps, current_step) -> dict:
        if current_step < self.step_no:
            return {"slice_id": None, "status": "rejected", "vendor_id": vendor_id,
                    "cost_total": 0.0, "capacity_gain": 0.0, "expires_at_step": 0,
                    "reason": f"stale_step: {current_step} < {self.step_no}"}
        v = next(x for x in VENDORS if x["vendor_id"] == vendor_id)
        gain = (v["bandwidth"] / REFERENCE_BANDWIDTH[slice_type]) * GAIN_SCALE
        cost = v["cost"] * duration_steps * (MINUTES_PER_STEP / 60)
        self.procurements += 1
        self.cost_total += cost
        return {
            "slice_id": f"slice-{slice_type.lower()}-{current_step:04d}-{vendor_id[-1]}",
            "status": "active",
            "vendor_id": vendor_id,
            "cost_total": round(cost, 1),
            "capacity_gain": round(gain, 3),
            "expires_at_step": current_step + duration_steps,
            "reason": None,
        }

    def _update_rating(self, vendor_id, outcome) -> dict:
        v = next(x for x in VENDORS if x["vendor_id"] == vendor_id)
        before = v["rating"]
        v["rating"] = min(max(before + (0.05 if outcome["sla_met"] else -0.20), 1.0), 5.0)
        return {"vendor_id": vendor_id, "rating_before": round(before, 2),
                "rating_after": round(v["rating"], 2),
                "delta": round(v["rating"] - before, 2)}

    # ── ④ audit ──────────────────────────────────────────────────────
    def _record_decision(self, **kw) -> dict:
        # ④와 같은 검사 — confidence 네 키가 있고 숫자여야 한다 (A-2). 값으로 돌려준다.
        bad = bad_confidence(kw.get("confidence"))
        if bad:
            return bad
        did = f"{self.run_id}-{kw['step']:04d}"
        self.decisions[did] = {**kw, "kind": "decision"}
        return {"decision_id": did, "recorded_at_step": kw["step"]}

    def _record_escalation(self, step, observation, situation, reason, confidence,
                           slice_id=None, vendor_id=None, cost_total=None,
                           chosen_policy=None, config=None, **_) -> dict:
        # 실제 ④(audit/server.py:78) 와 같은 인자를 받는다. 고정 시그니처였을 때는
        # 조달 3필드나 config 가 넘어오면 TypeError 로 죽었다.
        bad = bad_confidence(confidence)
        if bad:
            return bad
        self.escalations += 1
        did = f"{self.run_id}-{step:04d}"
        # 폴백은 ④처럼 INIT_ALLOCATION 상수다 (book.py). rule_based 제안을 쓰면 B-1 이후
        # 위반 보정이 섞여 실서버와 달라진다.
        fallback = dict(INIT_ALLOCATION)
        self.decisions[did] = {
            "step": step, "kind": "decision", "chosen_policy": "rule_based",
            # 에이전트가 고르려던 정책 (A-1). 실행된 것은 폴백이라 chosen_policy 와 따로 둔다.
            "agent_policy": chosen_policy,
            # 에이전트의 판단을 보존한다 (audit/book.py:185). 폴백 라벨로 덮으면
            # 상황 인지 측정의 입력이 사라진다 — 실제 ④가 그렇게 한다.
            "situation": situation, "fallback_situation": "normal",
            "allocation": fallback, "escalated": True,
            "slice_id": slice_id, "vendor_id": vendor_id, "cost_total": cost_total,
        }
        return {
            "escalation_id": f"{self.run_id}-esc-{step:04d}",
            "decision_id": did,
            "fallback_policy": "rule_based",
            "fallback_situation": "normal",
            "fallback_allocation": dict(fallback),
            "instruction": "사람 호출을 기록했다. 대기하지 말고 fallback_allocation 을 "
                           "apply_allocation 에 넣어 진행한 뒤 report_outcome 을 호출하라.",
        }

    def _get_decisions(self, n=10, kind=None) -> list:
        recs = list(self.decisions.values())
        if kind:
            recs = [r for r in recs if r.get("kind") == kind]
        return recs[-n:]

    def _get_metrics(self, window=None) -> dict:
        scored = [d for d in self.decisions.values() if "outcome" in d]
        usage: dict = {}
        for d in self.decisions.values():
            p = d.get("chosen_policy")
            if p:
                usage[p] = usage.get(p, 0) + 1
        steps = len(scored)
        return {
            "steps": steps,
            "interventions": self.escalations,
            "autonomous_rate": round(1 - self.escalations / steps, 3) if steps else 1.0,
            "sla_violations": sum(1 for d in scored if not d["outcome"]["sla_met"]),
            "mean_utilization": {k: 0.0 for k in SLICES},
            "policy_usage": usage,
            "mttr": 0.0,
            "unresolved": 0,
            "procurements": self.procurements,
            "procurement_cost_total": round(self.cost_total, 1),
            "mean_capacity": {k: round(self.capacity[k], 3) for k in SLICES},
            "pressure_exceeded": 0,
        }

    # ── ⑤ feedback ───────────────────────────────────────────────────
    def _report_outcome(self, decision_id, observed) -> dict:
        rec = self.decisions.get(decision_id)
        if rec is None:
            return {"error": "unknown_decision", "decision_id": decision_id}
        if observed["step"] <= rec["step"]:
            return {"error": "premature_scoring",
                    "reason": f"decision at step {rec['step']}, observed step {observed['step']}; expected >= {rec['step'] + 1}"}

        sla = not any(observed["violations"].values())
        policy = rec.get("chosen_policy", "rule_based")
        ideal = self._normalize_target(observed)
        applied = observed["allocation"]
        error = sum(abs(applied[k] - ideal[k]) for k in SLICES) / 2

        # B-2 — 개입 레코드는 정책 성적을 갱신하지 않는다. 적용된 것은 폴백 상수이지 정책의
        # 제안이 아니기 때문이다. 채점은 그대로 하고 성적은 fallback 칸에 (feedback/server.py 와 같다).
        escalated = bool(rec.get("escalated"))
        st = self.reliability[policy]
        before = float(st["r"])
        if escalated:
            after = before
            fb = self.reliability.setdefault(FALLBACK_BUCKET, rel.initial_entry())
            fb["r"], fb["n"] = rel.update(float(fb["r"]), int(fb["n"]), sla)
            fb["errors"] = rel.push_error(fb.get("errors", []), error)
        else:
            after, n = rel.update(before, int(st["n"]), sla)
            st["r"], st["n"] = after, n
            st["errors"] = rel.push_error(st.get("errors", []), error)

        rec["outcome"] = {"sla_met": sla, "error": round(error, 3),
                          "scored_at_step": observed["step"],
                          "counted_in_reliability": not escalated}
        return {
            "sla_met": sla,
            "policy": policy,
            "error": round(error, 3),
            "ideal_allocation": {k: round(ideal[k], 3) for k in SLICES},
            "applied_allocation": dict(applied),
            "requested_allocation": rec.get("allocation"),
            "actuator_delta": 0.0,
            "observed_violations": dict(observed["violations"]),
            "vendor_id": rec.get("vendor_id"),
            "reliability_before": round(before, 4),
            "reliability_after": round(after, 4),
            "counted_in_reliability": not escalated,
        }

    def _get_reliability_table(self) -> dict:
        # ⑤ view() 그대로 — n=0 이면 recent_error 가 정책 사전값에서 나온다 (B-3).
        # fallback 칸은 정책이 아니므로 내보내지 않는다 (B-2).
        return {p: rel.view(p, st) for p, st in self.reliability.items()
                if p in rel.POLICIES}

    # ── 내부 ─────────────────────────────────────────────────────────
    def _gen_traffic(self) -> dict:
        # 기본 배분 [0.4, 0.4, 0.2]·용량 1.0 에서 평시에는 임계 아래에 있도록
        # 잡는다. util = traffic / (alloc × cap) 이므로 상한은 각각
        # 0.36 / 0.48 / 0.16 이다. 배수가 걸리면 그때 위반이 발생한다.
        base = {"embb": 0.28, "urllc": 0.34, "mmtc": 0.12}
        m = MULT.get(self._active_scenario(), MULT["normal"])
        daily = 1.0 + 0.3 * math.sin(2 * math.pi * self.step_no / 96)
        return {
            k: min(max(base[k] * m[k] * daily + self._rng.gauss(0, 0.03), 0.1), 2.0)
            for k in SLICES
        }

    def _active_scenario(self) -> str:
        """mixed 의 구간 전환. spec/observe.md:189"""
        if self.scenario != "mixed":
            return self.scenario
        s = self.step_no
        if 20 <= s < 50:
            return "special_event"
        if 60 <= s < 90:
            return "emergency"
        if s >= 100:
            return "iot_surge"
        return "normal"

    def _expire(self) -> None:
        keep = []
        for lz in self.leases:
            if lz["expires_at_step"] <= self.step_no:
                self.capacity[lz["slice_type"].lower()] -= lz["amount"]
            else:
                keep.append(lz)
        self.leases = keep

    def _push_history(self) -> None:
        o = self._get_observation()
        self.history.append([
            sum(o["traffic"].values()) / 3,
            o["sim_time"]["hour_of_day"] / 24,
            o["sim_time"]["day_of_week"] / 6,
            o["allocation"]["embb"], o["allocation"]["urllc"], o["allocation"]["mmtc"],
            o["utilization"]["embb"], o["utilization"]["urllc"], o["utilization"]["mmtc"],
            o["client_count"], o["bs_count"],
        ])
        self.history = self.history[-100:]

    def _normalize_target(self, obs: dict) -> dict:
        """a* = normalize(traffic / (thresholds × capacity))  spec/feedback.md:32"""
        raw = {
            k: obs["traffic"][k] / (obs["thresholds"][k] * obs["capacity"][k])
            for k in SLICES
        }
        s = sum(raw.values()) or 1.0
        return {k: raw[k] / s for k in SLICES}

    def _fail(self, policy: str, status: str, reason: str) -> dict:
        return {"policy": policy, "allocation": None, "confidence": 0.0,
                "in_distribution": False, "status": status, "reason": reason,
                "rationale": "추론하지 않음."}
