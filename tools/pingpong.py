"""①④ 를 모의로 세우고 ②③⑤ 진짜 서버와 핑퐁시킨다. (B 소유 — 임시 하네스)

    .venv310/Scripts/python tools/pingpong.py
    .venv310/Scripts/python tools/pingpong.py --scenario emergency --steps 40

A(①④)와 C(오케스트레이터)가 아직 없어서 값 연쇄를 끝까지 못 본다. 여기서는

    ① observe   모의 (이 파일)      — spec/observe.md 계약대로
    ② policy    **진짜** stdio 서버
    ③ market    **진짜** stdio 서버
    ④ audit     모의 (이 파일)      — spec/audit.md 의 decisions.json 형식
    ⑤ feedback  **진짜** stdio 서버
    에이전트     결정적 규칙 (LLM 자리)

⚠️ 이건 **A의 ① 구현이 아니다.** 값이 흐르는지 보려고 만든 검증용 더미다.
   난수 모델·시나리오 강도는 임의로 정했고, A의 판이 오면 통째로 버린다.
   `mcp/mock/` 은 C 소유라 `tools/` 에 두었다.

검증하는 것 두 가지
  1. 값 연쇄 — 9단계 각각에서 생산된 값이 다음 소비처에 실제로 도착하는가
  2. eMBB · URLLC · mMTC 값이 의미 있게 움직이는가 (합 1.0, 클립 범위,
     상황 라벨에 따라 배분이 갈리고 이용률이 반응하는가)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

try:
    from fastmcp import Client
    from fastmcp.client.transports import StdioTransport
except ImportError:
    sys.exit("fastmcp 가 없다. pip install -r requirements-mcp.txt")

from srm_mcp.common import paths  # noqa: E402
from srm_mcp.common.const import (ALLOC_CLIP, CAPACITY_MAX, FEATURE_COLUMNS,  # noqa: E402
                                  INIT_ALLOCATION, MINUTES_PER_STEP,
                                  SCENARIO_STEPS, SLICE_KEY_TO_TYPE, SLICE_KEYS,
                                  STABILITY_FACTOR, START_HOUR, TAU, THRESHOLDS)
from srm_mcp.common.store import write_json  # noqa: E402

# ── 모의 ① observe ────────────────────────────────────────────
# ⚠️ 여기 숫자는 **임의로 고른 것**이다. A의 ① 이 아니라, 계약의 거동이 눈에 보이도록
#    맞춘 값이다. 기준은 셋.
#      (1) 평시에는 INIT_ALLOCATION 으로 전 슬라이스가 임계 아래
#      (2) 상황을 **맞히면** 해당 규칙 목표로 SLA 충족, **틀리면** 위반
#          → SLA 가 상황 인지 정확도의 함수가 된다 (실험의 신호)
#      (3) emergency 만 demand_pressure ≥ 1.0 → 조달 없이는 해소 불가, 조달하면 해소
#          → ③ 마켓이 장식이 아니게 된다
#
#   평시  embb 0.16/0.4=0.40 · urllc 0.30/0.4=0.75 · mmtc 0.08/0.2=0.40   (θ 0.9/1.2/0.8)
#   비상  urllc 0.90 → 목표 {0.2,0.7,0.1} 에서 0.90/0.7=1.286 > 1.2 위반
#         조달로 용량 1.25 → 0.90/(0.7×1.25)=1.029 < 1.2 해소
BASE_TRAFFIC = {"embb": 0.16, "urllc": 0.30, "mmtc": 0.08}
SURGE = {"emergency": ("urllc", 3.0), "special_event": ("embb", 2.5),
         "iot_surge": ("mmtc", 3.0)}
# mixed 전환표 (spec/observe.md): 20 이벤트 on / 50 off / 60 비상 on / 90 off / 100 IoT on
MIXED_SWITCHES = [(20, "special_event"), (50, "normal"), (60, "emergency"),
                  (90, "normal"), (100, "iot_surge")]


class MockObserve:
    """spec/observe.md 계약을 따르는 최소 시뮬레이터. 도구 6개."""

    def reset(self, run_id: str, scenario: str = "normal", seed: int = 0) -> dict:
        self.run_id, self.scenario, self.seed = run_id, scenario, seed
        self.rng = np.random.default_rng(seed)
        self.total_steps = SCENARIO_STEPS.get(scenario, 60)
        self.t = 0
        self.allocation = dict(INIT_ALLOCATION)
        self.capacity = {k: 1.0 for k in SLICE_KEYS}
        self.leases: list[dict] = []
        self.history: list[list[float]] = []
        self.truth: list[dict] = []
        self._roll_traffic()
        return {"run_id": run_id, "scenario": scenario, "seed": seed,
                "capacity": dict(self.capacity), "total_steps": self.total_steps,
                "observation": self.get_observation()}

    # 정답 라벨. 도구로 절대 새어 나가지 않는다 — truth.jsonl 전용.
    def _active_situation(self) -> str:
        if self.scenario != "mixed":
            return self.scenario
        current = "normal"
        for at, name in MIXED_SWITCHES:
            if self.t >= at:
                current = name
        return current

    def _roll_traffic(self) -> None:
        situation = self._active_situation()
        traffic = dict(BASE_TRAFFIC)
        if situation in SURGE:
            key, mult = SURGE[situation]
            traffic[key] *= mult
        # 일중 변동 + 잡음. seed 로 완전히 고정된다.
        hour = (START_HOUR + self.t * MINUTES_PER_STEP / 60) % 24
        daily = 1.0 + 0.10 * math.sin(2 * math.pi * (hour - 8) / 24)
        self.traffic = {k: float(np.clip(v * daily + self.rng.normal(0, 0.012), 0.1, 2.0))
                        for k, v in traffic.items()}
        self.client_count = float(np.clip(0.55 + 0.15 * math.sin(2 * math.pi * hour / 24)
                                          + self.rng.normal(0, 0.02), 0.36, 1.0))
        self.bs_count = float(np.clip(0.70 + self.rng.normal(0, 0.03), 0.45, 0.99))
        self.truth.append({"run_id": self.run_id, "step": self.t,
                           "is_emergency": situation == "emergency",
                           "is_special_event": situation == "special_event",
                           "is_iot_surge": situation == "iot_surge"})
        self._push_features()

    def _utilization(self) -> dict:
        return {k: self.traffic[k] / (self.allocation[k] * self.capacity[k]) for k in SLICE_KEYS}

    def _push_features(self) -> None:
        hour = (START_HOUR + self.t * MINUTES_PER_STEP / 60) % 24
        util = self._utilization()
        # ⚠️ day_of_week 는 0 이 아니라 1/7 부터 시작한다. 학습 데이터의 최솟값이
        #    0.0003 이라 정확히 0.0 이면 in_distribution 이 false 가 되고, ②의 lstm
        #    신뢰도가 𝟙[in_distribution] 때문에 통째로 0 이 된다 (아래 [7] 참조).
        self.history.append([
            float(np.mean(list(self.traffic.values())) * 3),   # traffic_load
            hour / 24, (((self.t * MINUTES_PER_STEP // 1440) % 7) + 1) / 7,
            self.allocation["embb"], self.allocation["urllc"], self.allocation["mmtc"],
            min(util["embb"], 2.0), min(util["urllc"], 2.0), min(util["mmtc"], 2.0),
            self.client_count, self.bs_count,
        ])

    def get_observation(self) -> dict:
        util = self._utilization()
        hour = int((START_HOUR + self.t * MINUTES_PER_STEP / 60) % 24)
        pressure = sum(self.traffic[k] / (THRESHOLDS[k] * self.capacity[k]) for k in SLICE_KEYS)
        return {
            "step": self.t,
            "sim_time": {"hour_of_day": hour, "day_of_week": 0, "is_weekend": False},
            "traffic": dict(self.traffic),
            "allocation": dict(self.allocation),
            "utilization": {k: round(v, 4) for k, v in util.items()},
            "capacity": dict(self.capacity),
            "thresholds": dict(THRESHOLDS),
            "violations": {k: bool(util[k] > THRESHOLDS[k]) for k in SLICE_KEYS},
            "client_count": self.client_count, "bs_count": self.bs_count,
            "demand_pressure": round(pressure, 4),
            # ②의 classify_demand 가 쓰는 11차원. Day 0 확정 대상 (README 참조).
            "features": self.history[-1], "feature_columns": list(FEATURE_COLUMNS),
        }

    def apply_allocation(self, embb: float, urllc: float, mmtc: float) -> dict:
        """액추에이터. 정규화 → 평활 → 클립 → 재정규화 (ml_orchestrator_demo.py:458~462)."""
        req = {"embb": embb, "urllc": urllc, "mmtc": mmtc}
        if any(v < 0 or math.isnan(v) for v in req.values()) or sum(req.values()) <= 0:
            return {"accepted": False, "requested": None,
                    "normalized": dict(self.allocation), "delta": 0.0,
                    "reason": "rejected: invalid input; allocation unchanged"}
        total = sum(req.values())
        req = {k: v / total for k, v in req.items()}
        smoothed = {k: STABILITY_FACTOR * self.allocation[k] + (1 - STABILITY_FACTOR) * req[k]
                    for k in SLICE_KEYS}
        clipped = {k: min(max(v, ALLOC_CLIP[0]), ALLOC_CLIP[1]) for k, v in smoothed.items()}
        total = sum(clipped.values())
        self.allocation = {k: v / total for k, v in clipped.items()}
        delta = sum(abs(req[k] - self.allocation[k]) for k in SLICE_KEYS) / 2
        return {"accepted": True, "requested": req, "normalized": dict(self.allocation),
                "delta": round(delta, 4),
                "reason": f"smoothed({STABILITY_FACTOR}); within clip {list(ALLOC_CLIP)}"}

    def add_capacity(self, slice_type: str, amount: float,
                     expires_at_step: int, slice_id: str) -> dict:
        key = next(k for k, v in SLICE_KEY_TO_TYPE.items() if v == slice_type)
        if self.capacity[key] + amount > CAPACITY_MAX:
            return {"accepted": False, "capacity": dict(self.capacity),
                    "demand_pressure": self.get_observation()["demand_pressure"],
                    "active_leases": list(self.leases),
                    "reason": f"capacity_cap_exceeded: {key} {self.capacity[key]:.2f} "
                              f"+ {amount} > {CAPACITY_MAX}"}
        self.capacity[key] += amount
        self.leases.append({"slice_id": slice_id, "slice_type": slice_type,
                            "amount": amount, "expires_at_step": expires_at_step})
        return {"accepted": True, "capacity": dict(self.capacity),
                "demand_pressure": self.get_observation()["demand_pressure"],
                "active_leases": list(self.leases), "reason": None}

    def step(self, n: int = 1) -> dict:
        advanced = 0
        for _ in range(n):
            if self.t >= self.total_steps:
                break
            self.t += 1
            advanced += 1
            for lease in [x for x in self.leases if x["expires_at_step"] <= self.t]:
                key = next(k for k, v in SLICE_KEY_TO_TYPE.items() if v == lease["slice_type"])
                self.capacity[key] = max(1.0, self.capacity[key] - lease["amount"])
                self.leases.remove(lease)
            self._roll_traffic()
        return {"steps_advanced": advanced, "episode_done": self.t >= self.total_steps,
                "observation": self.get_observation()}

    def get_history(self, n: int = 10) -> dict:
        rows = self.history[-n:]
        return {"n_requested": n, "n_available": len(rows), "n": len(rows),
                "columns": list(FEATURE_COLUMNS), "features": rows}


# ── 모의 ④ audit ──────────────────────────────────────────────
class MockAudit:
    """decisions.json 을 설계서 §5.0 형식으로 쌓는다. ⑤가 이 파일을 읽고 덧쓴다."""

    def __init__(self, run_id: str, config: dict):
        self.run_id, self.path = run_id, paths.decisions_json(run_id)
        self.book = {"run_id": run_id, "config": config, "decisions": []}
        self._flush()

    def _flush(self) -> None:
        write_json(self.path, self.book)

    def _next_id(self, step: int) -> str:
        return f"{self.run_id}-{step:04d}"

    def record_decision(self, step: int, observation: dict, situation: str,
                        chosen_policy: str, allocation: dict, confidence: dict,
                        rationale: str, slice_id=None, vendor_id=None,
                        in_distribution=True, demand_class=None, considered=None) -> dict:
        decision_id = self._next_id(step)
        self.book["decisions"].append({
            "decision_id": decision_id, "step": step, "kind": "decision",
            "situation": situation, "chosen_policy": chosen_policy,
            "allocation": allocation, "confidence": confidence, "rationale": rationale,
            "slice_id": slice_id, "vendor_id": vendor_id,
            "in_distribution": in_distribution, "demand_class": demand_class,
            "considered": considered, "observation": observation, "outcome": None})
        self._flush()
        return {"decision_id": decision_id}

    def record_escalation(self, step: int, observation: dict, situation: str,
                          reason: str, confidence: dict,
                          fallback_allocation: dict) -> dict:
        decision_id = self._next_id(step)
        self.book["decisions"].append({
            "decision_id": decision_id, "step": step, "kind": "escalation",
            "situation": situation, "reason": reason, "confidence": confidence,
            "chosen_policy": "rule_based", "fallback_allocation": fallback_allocation,
            "allocation": fallback_allocation, "slice_id": None, "vendor_id": None,
            "observation": observation, "outcome": None})
        self._flush()
        return {"escalation_id": decision_id, "decision_id": decision_id,
                "fallback": fallback_allocation}

    def reload(self) -> None:
        """⑤가 outcome 을 덧쓴 뒤 다시 읽는다 (같은 파일을 공유한다)."""
        self.book = json.loads(self.path.read_text(encoding="utf-8"))


# ── 에이전트 자리 — LLM 대신 결정적 규칙 ──────────────────────
SITUATION_OF = {"urllc": "emergency", "embb": "special_event", "mmtc": "iot_surge"}


def infer_by_utilization(obs: dict) -> str:
    """⚠️ 함정 — 이용률로 상황을 판정한다. **진동한다.**

    `utilization = traffic / (allocation × capacity)` 이므로 이용률은 내가 방금 내린
    배분의 함수다. URLLC에 몰아주면 URLLC 이용률이 내려가고 eMBB가 올라가서, 다음 스텝에
    special_event 로 오판한다. 그러면 eMBB에 몰아주고 다시 URLLC가 터진다 — 액추에이터와
    닫힌 되먹임 고리를 만든다. C의 프롬프트가 피해야 할 바로 그 실패다.
    """
    over = {k: obs["utilization"][k] / obs["thresholds"][k] for k in SLICE_KEYS}
    worst = max(over, key=over.__getitem__)
    return "normal" if over[worst] <= 1.0 else SITUATION_OF[worst]


def infer_by_traffic(obs: dict, tolerance: float = 1.15) -> str:
    """수요 구성비로 판정한다. **트래픽은 외생 변수라 내 배분에 오염되지 않는다.**

    임계로 정규화한 수요의 비중을 `INIT_ALLOCATION`(설정상 기대 구성비, const.py 의 공개
    상수)과 비교한다. 정답도, 시나리오 강도도 쓰지 않는다.
    """
    need = {k: obs["traffic"][k] / obs["thresholds"][k] for k in SLICE_KEYS}
    total = sum(need.values())
    share = {k: v / total for k, v in need.items()}
    ratio = {k: share[k] / INIT_ALLOCATION[k] for k in SLICE_KEYS}
    worst = max(ratio, key=ratio.__getitem__)
    return SITUATION_OF[worst] if ratio[worst] > tolerance else "normal"


AGENTS = {"util": infer_by_utilization, "traffic": infer_by_traffic}


def choose_policy(proposals: list[dict], table: dict) -> tuple[dict, float]:
    """combined = √(intrinsic × effective) 가 가장 큰 가용 정책."""
    best, best_combined = None, -1.0
    for p in proposals:
        if p["status"] != "ok":
            continue
        eff = table.get(p["policy"], {}).get("effective", 0.5)
        combined = math.sqrt(max(p["confidence"], 0.0) * eff)
        if combined > best_combined:
            best, best_combined = p, combined
    return best, best_combined


# ── 핑퐁 ──────────────────────────────────────────────────────
ENV_BASE = {"PYTHONPATH": str(ROOT), "PYTHONIOENCODING": "utf-8",
            "SLICE_DESC_MODE": "minimal"}


def transport(module: str, env: dict) -> "StdioTransport":
    return StdioTransport(command=sys.executable, args=["-m", module],
                          cwd=str(ROOT), env=env)


async def run(scenario: str, steps: int, seed: int, verbose: bool,
              agent: str = "traffic") -> dict:
    import os
    run_id = f"pingpong-{scenario}-s{seed}"
    env = {**os.environ, **ENV_BASE, "SLICE_MEMORY_MODE": "cold", "SLICE_RUN_ID": run_id}
    shutil.rmtree(paths.run_dir(run_id), ignore_errors=True)

    env1 = MockObserve()
    env1.reset(run_id, scenario, seed)
    audit = MockAudit(run_id, {"scenario": scenario, "seed": seed, "arm": "proposed",
                               "desc_mode": "minimal", "tau": TAU})

    log: list[dict] = []
    chain = {"decision_id→report": 0, "vendor_id→update_rating": 0,
             "capacity_gain→add_capacity": 0, "recent_error→propose": 0,
             "procure→record_decision": 0}
    escalations = 0

    async with Client(transport("srm_mcp.policy.server", env)) as pol, \
               Client(transport("srm_mcp.market.server", env)) as mkt, \
               Client(transport("srm_mcp.feedback.server", env)) as fb:

        total = min(steps, env1.total_steps)
        for t in range(total):
            # 1. ① 관측
            obs = env1.get_observation()
            truth = env1.truth[-1]

            # 2. ⑤ 신뢰도 표 + ② 수요 분류 → 에이전트가 situation 추론
            table = (await fb.call_tool("get_reliability_table", {})).data
            demand = (await pol.call_tool("classify_demand", {"observation": obs})).data
            situation = AGENTS[agent](obs)
            if any(table[p]["recent_error"] is not None for p in table):
                chain["recent_error→propose"] += 1

            # 3. ② 정책 비교 → 에이전트가 선택
            hist = env1.get_history(10)
            proposals = (await pol.call_tool("compare_policies", {
                "observation": obs, "situation": situation, "history": hist,
                "recent_errors": table})).data
            chosen, combined = choose_policy(proposals, table)

            # 3b. 에스컬레이션 — combined < τ 면 개입 1회 + 안전 기본 동작
            escalated = chosen is None or combined < TAU
            if escalated:
                escalations += 1
                # 설계서 §3.5 — 사람이 올 때까지의 **안전 기본 동작**은
                # rule_based + situation="normal" 이다. 에이전트의 판단을 그대로
                # 쓰면 "사람을 불렀다"는 사실이 행동에 아무 영향을 주지 않아
                # 개입 지표가 장식이 된다.
                fallback = (await pol.call_tool("propose_allocation", {
                    "policy": "rule_based", "observation": obs,
                    "situation": "normal"})).data
                res = audit.record_escalation(
                    t, obs, situation,
                    f"combined {combined:.3f} < tau {TAU}",
                    {"intrinsic": chosen["confidence"] if chosen else 0.0,
                     "empirical": table["rule_based"]["effective"], "combined": combined},
                    fallback["allocation"])
                decision_id = res["decision_id"]
                allocation, policy = fallback["allocation"], "rule_based"
            else:
                allocation, policy = chosen["allocation"], chosen["policy"]

            # 4. ③ 조달 분기 — 기록보다 **앞선다** (spec/tools.md 4번)
            slice_id = vendor_id = None
            gain = 0.0
            if obs["demand_pressure"] >= 1.0:
                worst = max(SLICE_KEYS,
                            key=lambda k: obs["utilization"][k] / obs["thresholds"][k])
                stype = SLICE_KEY_TO_TYPE[worst]
                qos = {"latency": 1.0 if stype == "URLLC" else 20.0,
                       "bandwidth": 400 if stype == "URLLC" else 800,
                       "reliability": 99.99 if stype == "URLLC" else 99.5}
                ranked = (await mkt.call_tool("score_offerings", {
                    "slice_type": stype, "qos_requirements": qos})).data
                proc = (await mkt.call_tool("procure", {
                    "vendor_id": ranked[0]["vendor_id"], "slice_type": stype,
                    "qos_requirements": qos, "duration_steps": 10,
                    "current_step": t})).data
                if proc["status"] == "active":
                    cap = env1.add_capacity(stype, proc["capacity_gain"],
                                            proc["expires_at_step"], proc["slice_id"])
                    if cap["accepted"]:
                        chain["capacity_gain→add_capacity"] += 1
                        gain = proc["capacity_gain"]
                    slice_id, vendor_id = proc["slice_id"], proc["vendor_id"]
                    chain["procure→record_decision"] += 1

            # 5. ④ 기록 — slice_id · vendor_id 를 싣는다
            if not escalated:
                decision_id = audit.record_decision(
                    t, obs, situation, policy, allocation,
                    {"intrinsic": chosen["confidence"],
                     "empirical": table[policy]["effective"], "combined": round(combined, 4)},
                    chosen["rationale"], slice_id, vendor_id,
                    chosen["in_distribution"], demand.get("dominant"),
                    [p["policy"] for p in proposals if p["status"] == "ok"])["decision_id"]
            elif vendor_id:
                audit.book["decisions"][-1]["vendor_id"] = vendor_id
                audit.book["decisions"][-1]["slice_id"] = slice_id
                audit._flush()

            # 6~7. ① 적용 → 전진
            applied = env1.apply_allocation(**allocation)
            env1.step(1)
            obs_next = env1.get_observation()

            # 8. ⑤ 채점
            outcome = (await fb.call_tool("report_outcome", {
                "decision_id": decision_id, "observed": obs_next})).data
            # ⚠️ `"error" in outcome` 으로 판정하면 안 된다 — `error` 는 정상 Outcome 의
            #    필드(L1/2 거리)이기도 하다. 오류 봉투는 `{"error": "premature_scoring"}`
            #    처럼 같은 키를 쓰므로 키 유무로는 구분되지 않는다. 성공 필드로 판정한다.
            if "sla_met" not in outcome:
                raise RuntimeError(f"step {t}: {outcome}")
            chain["decision_id→report"] += 1
            audit.reload()

            # 9. ③ 레이팅 갱신
            if outcome["vendor_id"]:
                await mkt.call_tool("update_rating", {
                    "vendor_id": outcome["vendor_id"],
                    "outcome": {"sla_met": outcome["sla_met"], "decision_id": decision_id}})
                chain["vendor_id→update_rating"] += 1

            log.append({
                "t": t, "truth": _truth_label(truth), "situation": situation,
                "policy": policy, "escalated": escalated,
                "traffic": obs["traffic"], "allocation": allocation,
                "applied": applied["normalized"], "util_next": obs_next["utilization"],
                "violations": obs_next["violations"], "capacity": obs_next["capacity"],
                "pressure": obs["demand_pressure"], "gain": gain,
                "combined": round(combined, 4), "error": outcome["error"],
                "sla_met": outcome["sla_met"], "dominant": demand.get("dominant"),
                "lstm_status": _row(proposals, "lstm_forecast")["status"],
                "lstm_conf": _row(proposals, "lstm_forecast")["confidence"],
                "lstm_in_dist": _row(proposals, "lstm_forecast")["in_distribution"],
                "lstm_reason": _row(proposals, "lstm_forecast")["reason"],
            })

            if verbose:
                v = "".join("X" if obs_next["violations"][k] else "." for k in SLICE_KEYS)
                print(f"  t={t:3} truth={_truth_label(truth):13} 추론={situation:13} "
                      f"{policy:14} alloc=({allocation['embb']:.2f},{allocation['urllc']:.2f},"
                      f"{allocation['mmtc']:.2f}) → 적용=({applied['normalized']['embb']:.2f},"
                      f"{applied['normalized']['urllc']:.2f},{applied['normalized']['mmtc']:.2f}) "
                      f"util=({obs_next['utilization']['embb']:.2f},"
                      f"{obs_next['utilization']['urllc']:.2f},"
                      f"{obs_next['utilization']['mmtc']:.2f}) [{v}] "
                      f"err={outcome['error']:.3f}{' ESC' if escalated else ''}")

        final_table = (await fb.call_tool("get_reliability_table", {})).data
        ratings = {o["vendor_id"]: o["rating"] for o in
                   (await mkt.call_tool("list_offerings", {"slice_type": "URLLC"})).data}

    return {"run_id": run_id, "log": log, "chain": chain, "table": final_table,
            "ratings": ratings, "escalations": escalations, "truth": env1.truth}


def _row(proposals: list[dict], policy: str) -> dict:
    return next(p for p in proposals if p["policy"] == policy)


def _truth_label(row: dict) -> str:
    for key, name in (("is_emergency", "emergency"), ("is_special_event", "special_event"),
                      ("is_iot_surge", "iot_surge")):
        if row[key]:
            return name
    return "normal"


# ── 검증 ──────────────────────────────────────────────────────
failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f": {detail}" if detail else ""))
    if not ok:
        failures.append(label)


def verify(result: dict) -> None:
    log, chain = result["log"], result["chain"]
    n = len(log)

    print("\n[1] 값 연쇄 — 생산된 값이 소비처에 도착했는가")
    check("모든 스텝이 채점됐다 (decision_id → report_outcome)",
          chain["decision_id→report"] == n, f"{chain['decision_id→report']}/{n}")
    procured = sum(1 for r in log if r["gain"] > 0)
    check("capacity_gain → add_capacity", chain["capacity_gain→add_capacity"] == procured,
          f"{procured}회 조달, {chain['capacity_gain→add_capacity']}회 반영")
    check("vendor_id → update_rating (⑤→③ 되먹임)",
          chain["vendor_id→update_rating"] == chain["procure→record_decision"],
          f"조달 {chain['procure→record_decision']}회 → 레이팅 갱신 "
          f"{chain['vendor_id→update_rating']}회")
    check("recent_error → propose_allocation (⑤→②)",
          chain["recent_error→propose"] > 0, f"{chain['recent_error→propose']}스텝")

    book = json.loads(paths.decisions_json(result["run_id"]).read_text(encoding="utf-8"))
    scored = [d for d in book["decisions"] if d.get("outcome")]
    check("④ 레코드에 ⑤의 outcome 이 덧써졌다", len(scored) == n, f"{len(scored)}/{n}")
    with_vendor = [d for d in book["decisions"] if d.get("vendor_id")]
    check("④ 레코드에 vendor_id 가 실렸다 (조달 → 기록 순서)",
          len(with_vendor) == chain["procure→record_decision"],
          f"{len(with_vendor)}건")

    print("\n[2] eMBB · URLLC · mMTC 값이 유효한가")
    sums = [sum(r["applied"].values()) for r in log]
    check("적용 배분의 합 = 1.0", all(abs(s - 1.0) < 1e-6 for s in sums),
          f"min {min(sums):.6f} max {max(sums):.6f}")
    lo, hi = ALLOC_CLIP
    vals = [v for r in log for v in r["applied"].values()]
    check(f"각 슬라이스가 클립 범위 [{lo}, {hi}] 안",
          all(lo - 1e-6 <= v <= hi + 1e-6 for v in vals),
          f"min {min(vals):.3f} max {max(vals):.3f}")
    check("이용률이 traffic/(alloc×cap) 로 일관",
          all(r["util_next"][k] > 0 for r in log for k in SLICE_KEYS))
    check("error 가 [0, 1]", all(0.0 <= r["error"] <= 1.0 for r in log),
          f"평균 {np.mean([r['error'] for r in log]):.4f}")

    print("\n[3] 상황 라벨이 배분을 가르는가")
    by_situation: dict[str, list] = {}
    for r in log:
        by_situation.setdefault(r["situation"], []).append(r["allocation"])
    for name, allocs in sorted(by_situation.items()):
        mean = {k: float(np.mean([a[k] for a in allocs])) for k in SLICE_KEYS}
        print(f"        {name:14} n={len(allocs):3}  목표 평균 "
              f"eMBB {mean['embb']:.3f} · URLLC {mean['urllc']:.3f} · mMTC {mean['mmtc']:.3f}")
    check("상황별 목표 배분이 서로 다르다", len(by_situation) == 1 or len({
        tuple(round(float(np.mean([a[k] for a in v])), 3) for k in SLICE_KEYS)
        for v in by_situation.values()}) == len(by_situation))

    print("\n[4] 상황 인지 정확도 (오프라인 — 정답과 조인)")
    # 전환 스텝은 제외한다 (flow/forbidden.md). obs_t 는 전환 직전 트래픽을 반영한다.
    labels = [(r["truth"], r["situation"]) for r in log]
    switches = {i for i in range(1, len(labels)) if labels[i][0] != labels[i - 1][0]}
    graded = [(a, b) for i, (a, b) in enumerate(labels) if i not in switches]
    hit = sum(1 for a, b in graded if a == b)
    print(f"        {hit}/{len(graded)} = {hit / max(len(graded), 1) * 100:.1f}% "
          f"(전환 스텝 {len(switches)}개 제외)")
    confusion: dict[tuple, int] = {}
    for a, b in graded:
        confusion[(a, b)] = confusion.get((a, b), 0) + 1
    for (a, b), c in sorted(confusion.items(), key=lambda x: -x[1]):
        if a != b:
            print(f"          오판 {a} → {b}: {c}회")

    print("\n[5] 자기 개선 — 신뢰도와 레이팅이 움직였는가")
    for name, entry in result["table"].items():
        if entry["n"] > 0:
            print(f"        {name:14} r={entry['reliability']:.4f} n={entry['n']:3} "
                  f"effective={entry['effective']:.4f} recent_error={entry['recent_error']}")
    moved = [e for e in result["table"].values() if e["n"] > 0 and e["reliability"] != 0.5]
    check("신뢰도가 초기값에서 움직였다", bool(moved))
    check("recent_error 가 ②에 공급 가능한 상태",
          any(e["recent_error"] is not None for e in result["table"].values()))
    print(f"        벤더 레이팅(URLLC): {result['ratings']}")

    print("\n[7] ② 정책 가용성 — lstm_forecast 가 실제로 후보에 오르는가")
    ok_lstm = sum(1 for r in log if r.get("lstm_status") == "ok")
    in_dist = sum(1 for r in log if r.get("lstm_in_dist"))
    conf = [r["lstm_conf"] for r in log if r.get("lstm_status") == "ok"]
    print(f"        status=ok {ok_lstm}/{n} · in_distribution {in_dist}/{n}"
          + (f" · confidence 평균 {np.mean(conf):.4f}" if conf else ""))
    reasons = {r.get("lstm_reason") for r in log if r.get("lstm_reason")}
    for reason in reasons:
        print(f"        사유: {reason}")

    print("\n[6] SLA · 개입")
    met = sum(1 for r in log if r["sla_met"])
    print(f"        SLA 충족 {met}/{n} = {met / n * 100:.1f}%")
    print(f"        에스컬레이션 {result['escalations']}회 "
          f"({result['escalations'] / n * 100:.1f}%)")
    print(f"        조달 {sum(1 for r in log if r['gain'] > 0)}회, "
          f"평균 demand_pressure {np.mean([r['pressure'] for r in log]):.3f}")
    used = {}
    for r in log:
        used[r["policy"]] = used.get(r["policy"], 0) + 1
    print(f"        정책 사용: {used}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--scenario", default="all",
                   choices=["all", "normal", "emergency", "special_event",
                            "iot_surge", "mixed"])
    p.add_argument("--steps", type=int, default=30)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--agent", default="traffic", choices=["traffic", "util"],
                   help="situation 추론 신호: traffic(외생) | util(내생·진동)")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    scenarios = (["normal", "emergency", "special_event", "iot_surge"]
                 if args.scenario == "all" else [args.scenario])

    for scenario in scenarios:
        print("\n" + "=" * 78)
        print(f"시나리오 {scenario} · {args.steps}스텝 · seed {args.seed} · agent={args.agent}")
        print("=" * 78)
        result = asyncio.run(run(scenario, args.steps, args.seed, args.verbose, args.agent))
        verify(result)
        shutil.rmtree(paths.run_dir(result["run_id"]), ignore_errors=True)

    print("\n" + "=" * 78)
    print("실패 " + str(len(failures)) + "건: " + ", ".join(failures) if failures else "전부 통과")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
