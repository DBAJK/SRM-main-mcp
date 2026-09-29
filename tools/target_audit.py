"""D7 — ②의 목표표가 ①의 임계값과 어긋나는 크기를 잰다. (B 소유)

    .venv310/Scripts/python tools/target_audit.py
    .venv310/Scripts/python tools/target_audit.py --seeds 0,1,2 --steps 30

`rule.py TARGET_BY_SITUATION` 은 원본 `ml_orchestrator_demo.py:428~438`, `THRESHOLDS` 는
원본 `:174` 그대로인데 둘이 서로를 모른다. 목표표는 수요 배율만 보고 나눴고, 위반이
없어지는 배분은 수요/임계에 비례한다 — `a*ₖ ∝ traffic_k/(θₖ·capacityₖ)`
(⑤ `scoring.ideal_allocation`). `urllc` 만 θ=1.2 로 1.0 을 넘어서, 수요가 2배여도 배분이
2배 필요하지 않다. emergency 표는 `urllc` 를 0.7 까지 밀며 임계가 더 빡빡한 `embb`(0.9)·
`mmtc`(0.8)에서 빼앗는다.

출력 — 전제 검증 / 목표표 vs 실측 a* / θ 정규화 표 / 반사실 비교 / D7 의 설명 범위.

⚠️ 서버도 에이전트도 안 띄운다. 트래픽 생성이 배분과 무관하므로(`env.py _roll`) 궤적은
   (시나리오, 시드)로 정해지고 배분 전략만 사후에 갈아 끼운다. 조달은 없다고 본다.
⚠️ 구조적 스텝(Σneed > 1.0)은 제외한다 — 어떤 배분으로도 못 지키므로 목표표의 잘잘못이
   아니다 (`eval/breakdown.py` 와 같은 기준).
"""
from __future__ import annotations

import argparse
import random
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from srm_mcp.common.const import (ALLOC_CLIP, SLICE_KEYS,  # noqa: E402
                                  STABILITY_FACTOR, THRESHOLDS)
from srm_mcp.feedback import scoring  # noqa: E402
from srm_mcp.observe.env import (BASE_TRAFFIC, EVENT_MULTIPLIERS,  # noqa: E402
                                 TRAFFIC_CLIP, SliceEnv)
from srm_mcp.policy.rule import (TARGET_BY_SITUATION,  # noqa: E402
                                 TARGET_BY_SITUATION_THETA, TARGET_TABLE_DEFAULT,
                                 target_table_name)

SCENARIOS = ("normal", "emergency", "special_event", "iot_surge")
INIT = {"embb": 0.4, "urllc": 0.4, "mmtc": 0.2}
FEASIBLE_PRESSURE = 1.0   # eval/breakdown.py:40 과 같은 기준


def normalized_target(situation: str) -> dict[str, float]:
    """`BASE_TRAFFIC × 배율 / θ` 를 정규화. 새 상수를 만들지 않는다."""
    need = {k: BASE_TRAFFIC[k] * EVENT_MULTIPLIERS[situation][k] / THRESHOLDS[k]
            for k in SLICE_KEYS}
    total = sum(need.values())
    return {k: v / total for k, v in need.items()}


def trace(scenario: str, seed: int, steps: int) -> list[tuple[dict, dict]]:
    """(traffic, capacity) 궤적. 배분과 무관하므로 한 번만 뽑으면 된다."""
    env = SliceEnv()
    env.reset(run_id=f"_audit-{scenario}-s{seed}", scenario=scenario, seed=seed)
    out = []
    for _ in range(steps + 1):
        obs = env.get_observation()
        out.append((obs["traffic"], obs["capacity"]))
        env.step()
    return out


def pressure(traffic: dict, capacity: dict) -> float:
    """Σ need. 1.0 을 넘으면 재배분으로는 못 지킨다 (= `demand_pressure`)."""
    return sum(traffic[k] / (THRESHOLDS[k] * capacity[k]) for k in SLICE_KEYS)


def violations(alloc: dict, traffic: dict, capacity: dict) -> int:
    return sum(1 for k in SLICE_KEYS
               if traffic[k] / (alloc[k] * capacity[k]) > THRESHOLDS[k])


def actuate(current: dict, requested: dict) -> dict:
    """①의 `apply_allocation` 과 같은 순서 — 정규화 → 평활 → 클립 → 재정규화."""
    total = sum(requested.values())
    requested = {k: v / total for k, v in requested.items()}
    smoothed = {k: STABILITY_FACTOR * current[k] + (1 - STABILITY_FACTOR) * requested[k]
                for k in SLICE_KEYS}
    low, high = ALLOC_CLIP
    clipped = {k: min(max(v, low), high) for k, v in smoothed.items()}
    total = sum(clipped.values())
    return {k: v / total for k, v in clipped.items()}


def simulate(tr: list, policy, steps: int) -> tuple[int, int]:
    """(위반 스텝, 셀 수 있던 스텝). 구조적 스텝은 배분만 굴리고 세지 않는다."""
    alloc, bad, counted = dict(INIT), 0, 0
    for t in range(steps):
        alloc = actuate(alloc, policy(*tr[t]))
        if pressure(*tr[t + 1]) > FEASIBLE_PRESSURE:
            continue
        counted += 1
        if violations(alloc, *tr[t + 1]) > 0:
            bad += 1
    return bad, counted


def triple(d: dict) -> str:
    return "[" + " ".join(f"{d[k]:.3f}" for k in SLICE_KEYS) + "]"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--seeds", default="0,1,2")
    p.add_argument("--steps", type=int, default=30)
    args = p.parse_args()
    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]

    print(f"θ = {THRESHOLDS}   ← urllc 만 1.0 을 넘는다 (초과 가입을 견딘다)\n")

    print("0. 전제 검증 — θ 정규화 표가 성립하는 조건")
    worst_cap, clipped, cells = 0.0, 0, 0
    lo, hi = TRAFFIC_CLIP
    for sc in SCENARIOS:
        for seed in seeds:
            for traffic, capacity in trace(sc, seed, args.steps)[:args.steps]:
                worst_cap = max(worst_cap, max(capacity.values()) - min(capacity.values()))
                clipped += sum(1 for k in SLICE_KEYS
                               if traffic[k] <= lo + 1e-9 or traffic[k] >= hi - 1e-9)
                cells += len(SLICE_KEYS)
    print(f"   [{'PASS' if worst_cap < 1e-9 else 'FAIL'}] 슬라이스별 용량이 같다 — 차 최대 {worst_cap:.6f}")
    print("          같아야 a*ₖ ∝ traffic_k/θₖ 로 줄어든다")
    print(f"   [{'PASS' if clipped * 50 < cells else 'WARN'}] TRAFFIC_CLIP 이 거의 안 물린다 — {clipped}/{cells} 칸")
    print("          물리면 슬라이스 비율이 왜곡된다")
    worst_lit = max(abs(TARGET_BY_SITUATION_THETA[s][k] - normalized_target(s)[k])
                    for s in SCENARIOS for k in SLICE_KEYS)
    print(f"   [{'PASS' if worst_lit <= 5e-5 else 'FAIL'}] rule.py 의 θ 리터럴 == 유도값"
          f" — 최대 차 {worst_lit:.6f}")
    print(f"   [정보] SLICE_TARGET_TABLE = {target_table_name()}  (기본 {TARGET_TABLE_DEFAULT})")
    print()

    print("1. 목표표 vs 실측 a* 평균")
    print("   시나리오       목표표(원본)          a* 평균               목표 − a*")
    for sc in SCENARIOS:
        acc = []
        for seed in seeds:
            for traffic, capacity in trace(sc, seed, args.steps)[:args.steps]:
                acc.append(scoring.ideal_allocation(
                    {"traffic": traffic, "capacity": capacity}))
        mean = {k: st.mean(a[k] for a in acc) for k in SLICE_KEYS}
        tgt = TARGET_BY_SITUATION[sc]
        diff = "[" + " ".join(f"{tgt[k] - mean[k]:+.3f}" for k in SLICE_KEYS) + "]"
        print(f"   {sc:14} {triple(tgt)}  {triple(mean)}  {diff}")
    print("   → urllc 네 줄 모두 과잉 · mmtc 네 줄 모두 과소. θ 를 안 나눈 부호다.\n")

    print("2. θ 정규화 목표표 — BASE_TRAFFIC × 배율 / θ (새 상수 없음)")
    for sc in SCENARIOS:
        print(f"   {sc:14} {triple(TARGET_BY_SITUATION[sc])}  →  {triple(normalized_target(sc))}")
    print()

    print(f"3. 반사실 비교 — 시드 {seeds} · {args.steps}스텝 · 조달 없음 · 구조적 스텝 제외")
    grand: dict[str, list[int]] = {}
    for sc in SCENARIOS:
        strategies = [
            ("원본 목표표", lambda tf, cp, s=sc: dict(TARGET_BY_SITUATION[s])),
            ("θ 정규화 목표표", lambda tf, cp, s=sc: normalized_target(s)),
            ("a*(obs_t)", lambda tf, cp: scoring.ideal_allocation(
                {"traffic": tf, "capacity": cp})),
        ]
        agg = {name: [0, 0] for name, _ in strategies}
        struct = 0
        for seed in seeds:
            tr = trace(sc, seed, args.steps)
            struct += sum(1 for t in range(args.steps)
                          if pressure(*tr[t + 1]) > FEASIBLE_PRESSURE)
            for name, policy in strategies:
                bad, counted = simulate(tr, policy, args.steps)
                agg[name][0] += bad
                agg[name][1] += counted
        total_steps = args.steps * len(seeds)
        print(f"   == {sc} · 구조적 {struct}/{total_steps} 제외 ==")
        for name, (bad, counted) in agg.items():
            rate = f"{bad / counted:.3f}" if counted else "  —  "
            print(f"        {name:18} 위반 {bad:3}/{counted:3} = {rate}")
            g = grand.setdefault(name, [0, 0])
            g[0] += bad
            g[1] += counted
    print("\n   합계")
    for name, (bad, counted) in grand.items():
        print(f"        {name:18} 위반 {bad:3}/{counted:3} = {bad / counted:.3f}")

    print()
    print("4. D7 이 어디까지 설명하나 — 정답 라벨 고정 vs 라벨 섞기")
    print("   `baseline` 은 정답을 매 스텝 받아 한 목표에 고정되고, `arm1` 은 라벨이 흔들린다.")
    print("   흔들리는 쪽이 나은 시나리오에서만 '정답을 아는 것이 손해' 가 성립한다.")
    for sc in SCENARIOS:
        fixed = [0, 0]
        mixed = [0, 0]
        for seed in seeds:
            tr = trace(sc, seed, args.steps)
            rng = random.Random(seed)
            seq = [rng.choice(SCENARIOS) for _ in range(args.steps)]
            bad, counted = simulate(tr, lambda tf, cp, s=sc: dict(TARGET_BY_SITUATION[s]),
                                    args.steps)
            fixed[0] += bad
            fixed[1] += counted
            it = iter(seq)
            bad, counted = simulate(tr, lambda tf, cp, i=it: dict(TARGET_BY_SITUATION[next(i)]),
                                    args.steps)
            mixed[0] += bad
            mixed[1] += counted
        verdict = ("섞는 쪽이 낫다  ← D7 이 설명하는 칸" if mixed[0] < fixed[0]
                   else "정답 고정이 낫다 (D7 밖)")
        print(f"   {sc:14} 정답 고정 {fixed[0]:3}/{fixed[1]:3}={fixed[0] / fixed[1]:.3f}"
              f"   섞기 {mixed[0]:3}/{mixed[1]:3}={mixed[0] / mixed[1]:.3f}   {verdict}")
    print("   → 사다리 첫 칸을 D7 만으로는 설명 못 한다. 나머지는 C-9 · M-0c 몫이다.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
