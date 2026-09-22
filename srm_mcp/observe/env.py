"""① 의 시뮬레이터 본체. (A 소유)

`ml_orchestrator_demo.py` 에서 **추출(copy-and-adapt)** 했다. import 하지 않는다
(`claude/build/extract.md`).

| 원본 | 위치 | 조치 |
|---|---|---|
| `generate_traffic()`      | `:286` | `datetime.now()` → 가상 시계, `np.random` → `self.rng` (정정 F) |
| `update_utilization()`    | `:467` | 분모에 `capacity` 를 곱한다 (정정 K) |
| `create_feature_vector()` | `:490` | 동일 치환 |
| `thresholds`              | `:174` | 그대로 |
| 위반 판정                  | `:563` | 그대로 |
| `run()` · `visualize_*` · 5번째 스텝 벤더 특수처리 | | **폐기** |

⚠️ 이 파일에만 정답 라벨이 있다. `runs/{run_id}/truth.jsonl` 로만 나가고 **어떤 도구도
   읽지 않는다** (`claude/flow/forbidden.md`). 관측에도 실리지 않는다.

⚠️ 난수 소비 순서가 곧 재현성이다. 한 스텝에 정확히 5회를 정해진 순서로 뽑는다 —
   트래픽 잡음 3 → client_count 1 → bs_count 1. 순서를 바꾸면 같은 시드에서 다른 전개가
   나오고 `build/order.md` 2단계 판정(동일 시드 2회 → truth.jsonl 바이트 동일)이 깨진다.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Optional

import numpy as np

from ..common import paths
from ..common.const import (ALLOC_CLIP, BS_COUNT_BAND, BS_COUNT_BASE, CAPACITY_BASE,
                            CAPACITY_MAX, CLIENT_COUNT_AMPLITUDE, CLIENT_COUNT_BAND,
                            CLIENT_COUNT_BASE, FEATURE_COLUMNS, INIT_ALLOCATION,
                            MINUTES_PER_STEP, SCENARIO_STEPS, SEQUENCE_LENGTH,
                            SLICE_KEY_TO_TYPE, SLICE_KEYS, SLICE_TYPES, STABILITY_FACTOR,
                            START_DAY_OF_WEEK, START_HOUR, THRESHOLDS)

# ── 원본 :289~:333 의 트래픽 모델. ①만 쓰므로 여기 둔다 ─────────
BASE_TRAFFIC = {"embb": 0.4, "urllc": 0.3, "mmtc": 0.2}   # :289
DAILY_AMPLITUDE = 0.3                                      # :296
WEEKLY_AMPLITUDE = 0.2                                     # :299
TRAFFIC_NOISE_SIGMA = 0.1                                  # :305
TRAFFIC_CLIP = (0.1, 2.0)                                  # :326

# :310~:324. 상황 라벨 하나가 슬라이스별 배율을 정한다.
EVENT_MULTIPLIERS = {
    "emergency":     {"embb": 0.8, "urllc": 2.0, "mmtc": 0.9},
    "special_event": {"embb": 1.5, "urllc": 0.8, "mmtc": 1.0},
    "iot_surge":     {"embb": 0.9, "urllc": 0.9, "mmtc": 1.8},
    "normal":        {"embb": 1.0, "urllc": 1.0, "mmtc": 1.0},
}

# `mixed` 전환표. test_scenarios.py:92 는 초 단위(duration=60, interval=0.5)라
# 스텝 = 초 × 2 로 옮겼다 (`build/extract.md`). 세 라벨은 상호 배타적이다.
MIXED_SWITCHES = [(20, "special_event"), (50, "normal"), (60, "emergency"),
                  (90, "normal"), (100, "iot_surge")]

STEP_RANGE = (1, 10)          # rationale/observe.md — n=1000 으로 에피소드를 끝내지 못하게
HISTORY_RANGE = (1, 100)
HISTORY_KEEP = 100            # 원본 :534 와 동일
AMOUNT_RANGE = (0.0, 0.5)     # 0 < amount <= 0.5
DEFAULT_RUN_ID = "_unnamed-normal-s0"


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, int(value)))


class SliceEnv:
    """에피소드 하나. `reset()` 이 ①의 상태를 **전부** 초기화한다 (설계서 §5.0)."""

    def __init__(self, run_id: str = DEFAULT_RUN_ID) -> None:
        self.reset(run_id)

    # ── 생명주기 ───────────────────────────────────────────────
    def reset(self, run_id: str, scenario: str = "normal", seed: int = 0) -> dict:
        if not run_id:
            raise ValueError("run_id 는 필수다. 형식 {arm}-{scenario}-s{seed}. "
                             "①의 기록과 ④의 decision_id 가 이 값으로 조인된다.")
        if scenario not in SCENARIO_STEPS:
            raise ValueError(f"unknown scenario: {scenario!r}. "
                             f"가능한 값: {sorted(SCENARIO_STEPS)}")

        self.run_id = str(run_id)
        self.scenario = scenario
        self.seed = int(seed)
        self.rng = np.random.default_rng(self.seed)
        self.total_steps = SCENARIO_STEPS[scenario]

        self.t = 0
        self.allocation = dict(INIT_ALLOCATION)
        self.capacity = {k: CAPACITY_BASE for k in SLICE_KEYS}   # 활성 조달 전부 회수
        self.leases: list[dict] = []
        self.history: list[list[float]] = []

        self._truth_path = paths.run_dir(self.run_id) / "truth.jsonl"
        self._truth_reset()
        self._roll()

        return {"run_id": self.run_id, "scenario": self.scenario, "seed": self.seed,
                "capacity": dict(self.capacity), "total_steps": self.total_steps,
                "observation": self.get_observation()}

    # ── 가상 시계 (정정 F) ─────────────────────────────────────
    def _clock(self) -> dict:
        minutes = START_HOUR * 60 + self.t * MINUTES_PER_STEP
        hour_of_day = int(minutes // 60) % 24
        day_of_week = (START_DAY_OF_WEEK + int(minutes // 1440)) % 7
        return {"hour_of_day": hour_of_day, "day_of_week": day_of_week,
                "is_weekend": day_of_week >= 5}

    # ── 전개 ───────────────────────────────────────────────────
    def _label(self) -> str:
        """현재 스텝의 정답 라벨. **절대 도구로 나가지 않는다.**"""
        if self.scenario != "mixed":
            return self.scenario
        active = "normal"
        for at, name in MIXED_SWITCHES:
            if self.t >= at:
                active = name
        return active

    def _roll(self) -> None:
        """트래픽·단말·기지국을 뽑고 피처 한 줄을 쌓는다. 난수 5회 (순서 고정)."""
        clock = self._clock()
        time_of_day = clock["hour_of_day"] / 24.0
        day_norm = clock["day_of_week"] / 6.0

        daily = DAILY_AMPLITUDE * math.sin(2 * math.pi * time_of_day)     # :296
        weekly = WEEKLY_AMPLITUDE * (1 - day_norm)                        # :299

        noise = self.rng.normal(0, TRAFFIC_NOISE_SIGMA, 3)                # 난수 1~3
        multiplier = EVENT_MULTIPLIERS[self._label()]
        traffic = {}
        for i, key in enumerate(SLICE_KEYS):
            # 원본 순서 그대로: 시간 패턴 → 잡음 → 이벤트 배율 → 클립 (:302~:326)
            value = BASE_TRAFFIC[key] * (1 + daily + weekly) + float(noise[i])
            traffic[key] = float(np.clip(value * multiplier[key], *TRAFFIC_CLIP))
        self.traffic = traffic

        # :516~:518. 모양(일주기 사인 · 정규 잡음)과 난수 소비는 원본 그대로이고,
        # 중심만 학습 분포 안으로 옮겼다 (const.py CLIENT_COUNT_* · BS_COUNT_*).
        # 원본 값은 학습 하한보다 체계적으로 낮아 ②의 in_distribution 이 상시 false 가
        # 되었고, 그건 환경에 대한 신호가 아니라 두 분포의 눈금이 안 맞은 것이다.
        # ⚠️ 이용률이 학습 범위를 벗어나는 것은 여전히 깎지 않는다 — 조달로 용량이 늘어
        #    분포를 벗어나는 것은 정직한 신호다 (rationale/observe.md).
        low, high = CLIENT_COUNT_BAND
        self.client_count = float(np.clip(
            CLIENT_COUNT_BASE
            + CLIENT_COUNT_AMPLITUDE * math.sin(time_of_day * 2 * math.pi)
            + 0.05 * float(self.rng.standard_normal()), low, high))       # 난수 4
        low, high = BS_COUNT_BAND
        self.bs_count = float(np.clip(
            BS_COUNT_BASE + 0.1 * float(self.rng.standard_normal()), low, high))   # 난수 5

        self._push_features(time_of_day, day_norm)
        self._truth_append()

    def _push_features(self, time_of_day: float, day_norm: float) -> None:
        """11차원 고정. 컬럼 순서는 `const.FEATURE_COLUMNS` 정본을 따른다.

        `capacity` 는 들어가지 않는다 — 학습된 가중치가 11차원을 기대한다
        (`rationale/observe.md` 알려진 한계).
        """
        util = self._utilization()
        self.history.append([
            float(sum(self.traffic.values()) / 3.0),   # traffic_load  (:509)
            time_of_day, day_norm,
            self.allocation["embb"], self.allocation["urllc"], self.allocation["mmtc"],
            util["embb"], util["urllc"], util["mmtc"],
            self.client_count, self.bs_count,
        ])
        if len(self.history) > HISTORY_KEEP:
            self.history = self.history[-HISTORY_KEEP:]

    def _utilization(self) -> dict:
        """traffic / (allocation × capacity). 정정 K 로 분모에 용량 배수가 붙었다."""
        return {k: self.traffic[k] / (self.allocation[k] * self.capacity[k])
                for k in SLICE_KEYS}

    def _demand_pressure(self) -> float:
        """Σ traffic / (θ × capacity). 1.0 을 넘으면 어떤 배분으로도 전 슬라이스 SLA 불가."""
        return sum(self.traffic[k] / (THRESHOLDS[k] * self.capacity[k]) for k in SLICE_KEYS)

    # ── 도구 본체 ──────────────────────────────────────────────
    def get_observation(self) -> dict:
        util = self._utilization()
        row = self.history[-1]
        return {
            "step": self.t,
            "sim_time": self._clock(),
            "traffic": {k: round(self.traffic[k], 6) for k in SLICE_KEYS},
            "allocation": {k: round(self.allocation[k], 6) for k in SLICE_KEYS},
            "utilization": {k: round(util[k], 6) for k in SLICE_KEYS},
            "capacity": {k: round(self.capacity[k], 6) for k in SLICE_KEYS},
            "thresholds": dict(THRESHOLDS),
            # np.bool_ 를 그대로 내보내면 json.dumps 가 죽는다 (spec/common.md)
            "violations": {k: bool(util[k] > THRESHOLDS[k]) for k in SLICE_KEYS},
            "client_count": round(self.client_count, 6),
            "bs_count": round(self.bs_count, 6),
            "demand_pressure": round(self._demand_pressure(), 6),
            # ②의 classify_demand 가 쓰는 11차원 (handover §4-② — features 블록).
            # 나머지 필드만으로는 traffic_load · time_of_day 를 만들 수 없다.
            "features": {name: round(value, 6)
                         for name, value in zip(FEATURE_COLUMNS, row)},
        }

    def step(self, n: int = 1) -> dict:
        """만료 회수 → 용량 재계산 → traffic_{t+1} → utilization_{t+1} → 라벨 기록.

        **만료가 트래픽 생성보다 먼저다.** 나중에 하면 이미 만료된 용량으로 이용률이
        계산되어 한 스텝씩 유리해진다.

        이용률은 **직전에 적용한 배분**으로 계산된다 — step() 직후의 관측이 곧
        직전 결정의 성적표다. 그래서 ⑤의 report_outcome 은 반드시 step() 이후다.
        """
        requested = _clamp(n, *STEP_RANGE)
        advanced = 0
        for _ in range(requested):
            if self.t >= self.total_steps:
                break
            self.t += 1
            advanced += 1
            self._expire_leases()
            self._roll()
        return {"steps_advanced": advanced,
                "episode_done": self.t >= self.total_steps,
                "observation": self.get_observation()}

    def apply_allocation(self, embb: float, urllc: float, mmtc: float) -> dict:
        """정규화 → 평활(0.7) → 클립[0.1, 0.8] → 재정규화 (`:458~462`).

        거부는 **입력이 비정상일 때만**이고, 거부되어도 기존 배분은 유지된다 —
        환경이 배분 없이 동작할 수는 없다.
        """
        requested = {"embb": embb, "urllc": urllc, "mmtc": mmtc}
        bad = self._reject_reason(requested)
        if bad is not None:
            return {"accepted": False, "requested": None,
                    "normalized": {k: round(self.allocation[k], 6) for k in SLICE_KEYS},
                    "delta": 0.0, "reason": f"rejected: {bad}; allocation unchanged"}

        total = sum(float(v) for v in requested.values())
        requested = {k: float(v) / total for k, v in requested.items()}

        smoothed = {k: STABILITY_FACTOR * self.allocation[k]
                       + (1 - STABILITY_FACTOR) * requested[k] for k in SLICE_KEYS}
        low, high = ALLOC_CLIP
        clipped = {k: min(max(v, low), high) for k, v in smoothed.items()}
        was_clipped = any(abs(clipped[k] - smoothed[k]) > 1e-12 for k in SLICE_KEYS)
        total = sum(clipped.values())
        self.allocation = {k: v / total for k, v in clipped.items()}

        delta = sum(abs(requested[k] - self.allocation[k]) for k in SLICE_KEYS) / 2
        return {
            "accepted": True,
            "requested": {k: round(requested[k], 6) for k in SLICE_KEYS},
            "normalized": {k: round(self.allocation[k], 6) for k in SLICE_KEYS},
            "delta": round(delta, 6),
            "reason": (f"smoothed({STABILITY_FACTOR}); "
                       + (f"clipped to [{low}, {high}]" if was_clipped
                          else f"within clip [{low}, {high}]")),
        }

    @staticmethod
    def _reject_reason(requested: dict) -> Optional[str]:
        for key, value in requested.items():
            if value is None:
                return f"missing value in {key}"
            value = float(value)
            if math.isnan(value) or math.isinf(value):
                return f"non-finite value in {key}({value})"
            if value < 0:
                return f"negative value in {key}({value})"
        if sum(float(v) for v in requested.values()) <= 0:
            return "all values are zero"
        return None

    def get_history(self, n: int = SEQUENCE_LENGTH) -> dict:
        """오래된 것 → 최신 순. `n_available < 10` 이면 ②의 lstm_forecast 를 못 쓴다."""
        requested = _clamp(n, *HISTORY_RANGE)
        rows = self.history[-requested:]
        return {"n_requested": requested, "n_available": len(rows), "n": len(rows),
                "columns": list(FEATURE_COLUMNS),
                "features": [[round(v, 6) for v in row] for row in rows]}

    def add_capacity(self, slice_type: str, amount: float,
                     expires_at_step: int, slice_id: str) -> dict:
        """③의 procure() 출력을 에이전트가 중계해 환경에 반영한다.

        거부되어도 ③의 조달은 이미 일어났다 — 비용은 청구되고 용량은 안 늘어난다.
        호출 전에 `Observation.capacity` 로 상한을 확인하는 것이 에이전트 몫이다.
        """
        reason = self._capacity_reject(slice_type, amount, expires_at_step)
        if reason is not None:
            return self._capacity_state(accepted=False, reason=reason)

        key = SLICE_KEY_OF[slice_type]
        self.capacity[key] = self.capacity[key] + float(amount)
        self.leases.append({"slice_id": slice_id, "slice_type": slice_type,
                            "amount": float(amount),
                            "expires_at_step": int(expires_at_step)})
        return self._capacity_state(accepted=True, reason=None)

    def _capacity_reject(self, slice_type: str, amount: float,
                         expires_at_step: int) -> Optional[str]:
        if slice_type not in SLICE_KEY_OF:
            return f"unknown_slice_type: {slice_type!r}. 가능한 값: {list(SLICE_TYPES)}"
        low, high = AMOUNT_RANGE
        if not (low < float(amount) <= high):
            return f"amount_out_of_range: {amount} not in ({low}, {high}]"
        if int(expires_at_step) <= self.t:
            return (f"already_expired: expires_at_step {expires_at_step} "
                    f"<= current step {self.t}")
        key = SLICE_KEY_OF[slice_type]
        if self.capacity[key] + float(amount) > CAPACITY_MAX + 1e-9:
            return (f"capacity_cap_exceeded: {key} {self.capacity[key]:.2f} "
                    f"+ {amount} > {CAPACITY_MAX}")
        return None

    def _capacity_state(self, accepted: bool, reason: Optional[str]) -> dict:
        return {"accepted": accepted,
                "capacity": {k: round(self.capacity[k], 6) for k in SLICE_KEYS},
                "demand_pressure": round(self._demand_pressure(), 6),
                "active_leases": [dict(lease) for lease in self.leases],
                "reason": reason}

    def _expire_leases(self) -> None:
        """만료된 리스를 회수한다. 용량은 CAPACITY_BASE 아래로 내려가지 않는다."""
        expired = [lease for lease in self.leases if lease["expires_at_step"] <= self.t]
        for lease in expired:
            key = SLICE_KEY_OF[lease["slice_type"]]
            self.capacity[key] = max(CAPACITY_BASE, self.capacity[key] - lease["amount"])
            self.leases.remove(lease)

    # ── 라벨 기록 — 파일 전용 (flow/forbidden.md) ──────────────
    def _truth_row(self) -> dict:
        active = self._label()
        flags = {f"is_{name}": active == name
                 for name in ("emergency", "special_event", "iot_surge")}
        # 시나리오를 나중에 추가하다 겹치면 채점 기준이 조용히 무너진다.
        assert sum(flags.values()) <= 1, f"라벨이 겹쳤다: step {self.t} {flags}"
        return {"run_id": self.run_id, "step": self.t, **flags}

    def _truth_reset(self) -> None:
        """재실행이 append 로 쌓이면 '동일 시드 → 바이트 동일' 판정이 깨진다."""
        path: Path = self._truth_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")

    def _truth_append(self) -> None:
        line = json.dumps(self._truth_row(), ensure_ascii=False)
        with open(self._truth_path, "a", encoding="utf-8", newline="\n") as f:
            f.write(line + "\n")


# vendors.json 대소문자 키 → 소문자 슬라이스 키. 섞으면 조용히 틀린다.
SLICE_KEY_OF = {v: k for k, v in SLICE_KEY_TO_TYPE.items()}
