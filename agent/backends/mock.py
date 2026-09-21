"""인프로세스 목 백엔드.

A·B가 실제 서버를 내놓기 전까지 루프를 돌리기 위한 임시물이다.
**시뮬레이션 충실도는 목표가 아니다** — 응답 형태가 명세와 맞는지,
호출 순서가 성립하는지를 검증하는 것이 목적이다.

실제 서버가 나오면 backends/mcp.py 로 갈아끼운다. 루프 코드는 바뀌지 않는다.

주의: 여기서 나가는 값에 FORBIDDEN 키가 없어야 한다. Guard 가 잡는다.
"""

import math
import random
from typing import Any

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
        self.reliability = {
            "rule_based": {"r": 0.9, "n": 0, "err": 0.1},
            "lstm_forecast": {"r": 0.8, "n": 0, "err": 0.15},
            "dqn": {"r": 0.4, "n": 0, "err": 0.4},
        }
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

        target = {
            "emergency": {"embb": 0.2, "urllc": 0.7, "mmtc": 0.1},
            "special_event": {"embb": 0.6, "urllc": 0.3, "mmtc": 0.1},
            "iot_surge": {"embb": 0.3, "urllc": 0.3, "mmtc": 0.4},
            "normal": {"embb": 0.4, "urllc": 0.4, "mmtc": 0.2},
        }[situation]
        util, thr = observation["utilization"], observation["thresholds"]
        slack = min(abs(util[k] - thr[k]) / thr[k] for k in SLICES)
        return {
            "policy": policy,
            "allocation": target,
            "confidence": round(0.50 + 0.30 * min(1.0, slack), 3),
            "in_distribution": True,
            "status": "ok",
            "reason": None,
            "rationale": f"situation={situation} → 목표 {list(target.values())}.",
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
        did = f"{self.run_id}-{kw['step']:04d}"
        self.decisions[did] = {**kw, "kind": "decision"}
        return {"decision_id": did, "recorded_at_step": kw["step"]}

    def _record_escalation(self, step, observation, situation, reason, confidence) -> dict:
        self.escalations += 1
        did = f"{self.run_id}-{step:04d}"
        fb = self._propose_allocation("rule_based", observation, "normal")
        self.decisions[did] = {
            "step": step, "kind": "decision", "chosen_policy": "rule_based",
            "situation": "normal", "allocation": fb["allocation"],
        }
        return {
            "escalation_id": f"{self.run_id}-esc-{step:04d}",
            "decision_id": did,
            "fallback_policy": "rule_based",
            "fallback_situation": "normal",
            "fallback_allocation": fb["allocation"],
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

        st = self.reliability[policy]
        before = st["r"]
        st["r"] = 0.8 * st["r"] + 0.2 * (1.0 if sla else 0.0)
        st["n"] += 1
        st["err"] = 0.8 * st["err"] + 0.2 * error

        rec["outcome"] = {"sla_met": sla, "error": round(error, 3),
                          "scored_at_step": observed["step"]}
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
            "reliability_before": round(before, 3),
            "reliability_after": round(st["r"], 3),
        }

    def _get_reliability_table(self) -> dict:
        out = {}
        for p, st in self.reliability.items():
            n = st["n"]
            out[p] = {
                "reliability": round(st["r"], 3),
                "n": n,
                "effective": round((st["r"] * n + 0.5 * 5) / (n + 5), 3),
                "recent_error": round(st["err"], 3),
            }
        return out

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
