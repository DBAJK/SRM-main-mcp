"""① slice-observe 자체 검사 — 계약과 실측치를 대조한다. (A 소유)

    python tools/check_observe.py

`build/order.md` 2단계 완료 판정이 여기 §1 이다 — **동일 시드 2회 실행 →
`truth.jsonl` 바이트 단위 동일.** 재현이 안 되면 이후 60회 비교가 전부 무의미하므로
여기서 반드시 멈춘다.

`fastmcp` 없이 돈다 (`observe/env.py` 와 `common/` 만 import 한다).
실제 stdio 왕복은 `tools/smoke_servers.py` 가 본다.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Windows 기본 콘솔은 cp949 라 '—' 한 글자에 UnicodeEncodeError 로 죽는다.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from srm_mcp.common import paths  # noqa: E402
from srm_mcp.common.const import (ALLOC_CLIP, CAPACITY_BASE, CAPACITY_MAX,  # noqa: E402
                                  FEATURE_COLUMNS, FORBIDDEN, INIT_ALLOCATION,
                                  SCENARIO_STEPS, THRESHOLDS)
from srm_mcp.observe import env as envmod  # noqa: E402
from srm_mcp.observe.env import SliceEnv  # noqa: E402

RUN = "_check-observe"

# rationale/environment.md 조정 후 실측 (60스텝 × 시드 10~20).
# 시드 수가 달라 소수점이 흔들리므로 ±3%p 를 허용한다.
EXPECTED_PRESSURE = {"normal": 5.6, "emergency": 27.7,
                     "special_event": 34.3, "iot_surge": 28.5}
EXPECTED_VIOLATION = {"normal": 68.4, "emergency": 75.2,
                      "special_event": 94.2, "iot_surge": 91.7}

failures: list[str] = []


def check(label: str, got, want, tol: float = 0.005) -> None:
    if isinstance(want, float) and isinstance(got, (int, float)):
        ok = abs(got - want) <= tol
    else:
        ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {label}: {got!r}" + ("" if ok else f"  (기대 {want!r})"))
    if not ok:
        failures.append(label)


def check_true(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f": {detail}" if detail else ""))
    if not ok:
        failures.append(label)


def warn(label: str, ok: bool, detail: str = "") -> None:
    """Day 0 에서 3인이 정할 사항. 실패로 세지 않되 매번 눈에 띄게 찍는다."""
    print(f"  {'PASS' if ok else 'WARN'}  {label}" + (f": {detail}" if detail else ""))


def run_episode(run_id: str, scenario: str, seed: int, steps: int) -> list[dict]:
    env = SliceEnv(run_id)
    result = env.reset(run_id, scenario, seed)
    observations = [result["observation"]]
    for _ in range(steps):
        observations.append(env.step(1)["observation"])
    return observations


def main() -> int:
    print("① slice-observe 검사\n")

    # ── 1. 재현성 — build/order.md 2단계 완료 판정 ─────────────
    print("1. 동일 시드 재현 (2단계 완료 판정)")
    first = run_episode(RUN, "emergency", 0, 60)
    truth_first = (paths.run_dir(RUN) / "truth.jsonl").read_bytes()
    second = run_episode(RUN, "emergency", 0, 60)
    truth_second = (paths.run_dir(RUN) / "truth.jsonl").read_bytes()

    check_true("truth.jsonl 바이트 단위 동일", truth_first == truth_second,
               f"{len(truth_first)} bytes")
    check("truth.jsonl 줄 수 = 1 + 60", len(truth_first.decode().splitlines()), 61)
    check_true("관측 전체 동일",
               all(a == b for a, b in zip(first, second)))
    other = run_episode(RUN, "emergency", 1, 10)
    check_true("다른 시드 → 다른 전개", other[5] != first[5])

    # ── 2. 정답 비노출 (flow/forbidden.md) ─────────────────────
    print("\n2. 정답 비노출")
    import json as _json
    blob = _json.dumps(first, ensure_ascii=False)
    leaked = [word for word in FORBIDDEN if word in blob]
    check_true("관측에 FORBIDDEN 문자열 0건", not leaked, str(leaked))

    server_src = (ROOT / "srm_mcp" / "observe" / "server.py").read_text(encoding="utf-8")
    leaked_src = [word for word in FORBIDDEN if word in server_src]
    check_true("server.py 전체에 FORBIDDEN 0건", not leaked_src, str(leaked_src))
    check_true("truth.jsonl 에는 라벨이 있다 (파일 전용 경로)",
               b"is_emergency" in truth_first)

    # ── 3. 관측 계약 ───────────────────────────────────────────
    print("\n3. 관측 계약")
    obs = first[12]
    check("step", obs["step"], 12)
    check("thresholds", obs["thresholds"], dict(THRESHOLDS))
    check("capacity 기본값", obs["capacity"]["urllc"], CAPACITY_BASE)
    check_true("violations 가 파이썬 bool",
               all(type(v) is bool for v in obs["violations"].values()))
    check_true("allocation 합 = 1.0", abs(sum(obs["allocation"].values()) - 1.0) < 1e-6)

    util = {k: obs["traffic"][k] / (obs["allocation"][k] * obs["capacity"][k])
            for k in ("embb", "urllc", "mmtc")}
    check("utilization = traffic/(alloc×cap)", obs["utilization"]["urllc"],
          round(util["urllc"], 6), tol=1e-6)
    pressure = sum(obs["traffic"][k] / (THRESHOLDS[k] * obs["capacity"][k])
                   for k in ("embb", "urllc", "mmtc"))
    check("demand_pressure = Σ traffic/(θ×cap)", obs["demand_pressure"],
          round(pressure, 6), tol=1e-6)
    check("sim_time 은 가상 시계 (step 12 → 3시)", obs["sim_time"]["hour_of_day"], 3)
    check("features 11차원", list(obs["features"]), list(FEATURE_COLUMNS))

    # ── 4. ②가 이 관측/이력을 실제로 소화하는가 (handover §2.2) ─
    print("\n4. ②의 features.py 소화 (handover §2.2-(1)(2))")
    try:
        from srm_mcp.policy import features as pfeatures
        vector = pfeatures.vector_from_observation(obs)
        check("vector_from_observation → 11차원", len(vector), 11)
        env = SliceEnv(RUN)
        env.reset(RUN, "normal", 0)
        for _ in range(12):
            env.step(1)
        history = env.get_history(10)
        window = pfeatures.window_from_history(history)
        check("window_from_history → (10, 11)", (len(window), len(window[0])), (10, 11))
        check("columns 가 정본 이름", history["columns"], list(FEATURE_COLUMNS))
        if pfeatures.ranges_available():
            outside = pfeatures.out_of_range(window)
            # 해소됨. 원본 create_feature_vector 의 분포는 dqn_training_data.csv 보다
            # 넓어 행 단위 이탈률이 day_of_week 100% · bs_count 28.4% · client_count 14.8%
            # 였고, 10행 창에서 하나만 벗어나도 false 라 lstm 신뢰도가 항상 0 이었다
            # (624창 중 통과 0). 눈금이 안 맞는 열과 진짜 신호를 나눠서 고쳤다 —
            #   · time_of_day · day_of_week : 학습 쪽이 U(0,1) 난수라 판정 기준이 못 된다
            #     → ②가 제외 (policy/features.py UNGATED_COLUMNS)
            #   · client_count · bs_count   : 학습에 실제 범위가 있는데 ①이 낮게 뽑았다
            #     → ①이 생성식 중심만 이동 (const.py CLIENT_COUNT_* · BS_COUNT_*)
            # 남는 이탈은 이용률뿐이고 그건 깎지 않는다 — 조달로 용량이 늘어 분포를
            # 벗어나는 것은 정직한 신호다 (rationale/observe.md).
            warn("in_distribution", not outside,
                 f"범위 밖: {outside}" if outside else "")
    except Exception as exc:                     # noqa: BLE001
        check_true("features.py 소화", False, f"{type(exc).__name__}: {exc}")

    # ── 5. apply_allocation 변형 파이프라인 ────────────────────
    print("\n5. apply_allocation (spec/observe.md 실측)")
    env = SliceEnv(RUN)
    env.reset(RUN, "normal", 0)
    applied = env.apply_allocation(0.20, 0.70, 0.10)
    check("accepted", applied["accepted"], True)
    check("normalized.embb", applied["normalized"]["embb"], 0.34, tol=0.0005)
    check("normalized.urllc", applied["normalized"]["urllc"], 0.49, tol=0.0005)
    check("normalized.mmtc", applied["normalized"]["mmtc"], 0.17, tol=0.0005)
    check("delta", applied["delta"], 0.21, tol=0.0005)
    check_true("정규화 불필요 — 합이 1이 아니어도 된다",
               abs(sum(SliceEnv(RUN).apply_allocation(2, 7, 1)["requested"].values()) - 1.0)
               < 1e-9)

    env2 = SliceEnv(RUN)
    env2.reset(RUN, "normal", 0)
    before = dict(env2.allocation)
    rejected = env2.apply_allocation(0.5, -0.1, 0.2)
    check("음수 → accepted false", rejected["accepted"], False)
    check("거부해도 배분 유지", rejected["normalized"],
          {k: round(v, 6) for k, v in before.items()})
    check_true("거부 사유에 슬라이스 이름", "urllc" in rejected["reason"],
               rejected["reason"])
    check("전부 0 → accepted false", env2.apply_allocation(0, 0, 0)["accepted"], False)
    low, high = ALLOC_CLIP
    for _ in range(30):
        env2.apply_allocation(0.98, 0.01, 0.01)
    check_true(f"클립 [{low}, {high}] 유지",
               all(low - 1e-9 <= v <= high + 1e-9 for v in env2.allocation.values()),
               str(env2.allocation))

    # ── 6. add_capacity · 만료 ─────────────────────────────────
    print("\n6. add_capacity · 만료 회수")
    env3 = SliceEnv(RUN)
    env3.reset(RUN, "emergency", 0)
    for _ in range(12):
        env3.step(1)
    pressure_before = env3.get_observation()["demand_pressure"]
    state = env3.add_capacity("URLLC", 0.25, 22, "slice-urllc-0012-v1")
    check("accepted", state["accepted"], True)
    check("capacity.urllc", state["capacity"]["urllc"], CAPACITY_BASE + 0.25, tol=1e-9)
    check_true("압력이 내려간다", state["demand_pressure"] < pressure_before,
               f"{pressure_before} → {state['demand_pressure']}")
    check_true("한 번으로 해소되지 않는 크기", pressure_before - state["demand_pressure"] < 0.2,
               f"Δ {round(pressure_before - state['demand_pressure'], 4)}")
    check("active_leases 1건", len(state["active_leases"]), 1)

    check("과거 만료 거부",
          env3.add_capacity("mMTC", 0.1, 5, "past")["accepted"], False)
    check("amount 범위 밖 거부",
          env3.add_capacity("mMTC", 0.9, 30, "big")["accepted"], False)
    check("알 수 없는 slice_type 거부",
          env3.add_capacity("URLCC", 0.1, 30, "typo")["accepted"], False)

    while env3.t < 22:
        env3.step(1)
    check("만료 후 회수", env3.get_observation()["capacity"]["urllc"], CAPACITY_BASE,
          tol=1e-9)
    check("만료된 리스 제거", len(env3.leases), 0)

    # 상한은 따로 본다 — 위 리스가 살아 있으면 만료 검사가 섞인다.
    env3b = SliceEnv(RUN)
    env3b.reset(RUN, "emergency", 0)
    for amount, slice_id in ((0.5, "a"), (0.5, "b"), (0.5, "c")):
        over = env3b.add_capacity("URLLC", amount, 40, slice_id)
    check_true(f"상한 {CAPACITY_MAX} 초과 거부", over["accepted"] is False,
               str(over["reason"]))
    check_true("용량 상한 유지",
               all(v <= CAPACITY_MAX + 1e-9 for v in over["capacity"].values()),
               str(over["capacity"]))

    # ── 7. get_history ────────────────────────────────────────
    print("\n7. get_history")
    env4 = SliceEnv(RUN)
    env4.reset(RUN, "normal", 0)
    for _ in range(3):
        env4.step(1)
    early = env4.get_history(10)  # reset 1행 + step 3행
    check("n_requested", early["n_requested"], 10)
    check("n_available (초반에는 적다)", early["n_available"], 4)
    for _ in range(9):
        env4.step(1)
    ordered = env4.get_history(10)["features"]
    check_true("오래된 것 → 최신 순",
               ordered[0][1] < ordered[-1][1],
               f"time_of_day {ordered[0][1]} → {ordered[-1][1]}")
    check("n 상한 100", env4.get_history(1000)["n_requested"], 100)

    # ── 8. step · 에피소드 ────────────────────────────────────
    print("\n8. step · 에피소드")
    env5 = SliceEnv(RUN)
    env5.reset(RUN, "normal", 0)
    check("n 상한 10", env5.step(1000)["steps_advanced"], 10)
    while not env5.step(10)["episode_done"]:
        pass
    check("normal total_steps", env5.t, SCENARIO_STEPS["normal"])
    check("에피소드 끝에서 더 안 간다", env5.step(5)["steps_advanced"], 0)

    env6 = SliceEnv(RUN)
    reset_result = env6.reset(RUN, "mixed", 0)
    check("mixed total_steps", reset_result["total_steps"], 120)
    check("reset 후 capacity", reset_result["capacity"]["embb"], CAPACITY_BASE)
    check("reset 후 allocation", reset_result["observation"]["allocation"],
          {k: round(v, 6) for k, v in INIT_ALLOCATION.items()})
    check("mixed 전환표", envmod.MIXED_SWITCHES,
          [(20, "special_event"), (50, "normal"), (60, "emergency"),
           (90, "normal"), (100, "iot_surge")])
    try:
        env6.reset(RUN, "nonsense", 0)
        check_true("알 수 없는 scenario → 예외", False)
    except ValueError:
        check_true("알 수 없는 scenario → 예외", True)

    # ── 9. 시나리오별 압력 (rationale/environment.md) ─────────
    print("\n9. 시나리오별 실측 (60스텝 × 시드 10, ±3%p 허용)")
    for scenario in ("normal", "emergency", "special_event", "iot_surge"):
        exceeded = violated = total = 0
        env7 = SliceEnv(RUN)
        for seed in range(10):
            obs = env7.reset(RUN, scenario, seed)["observation"]
            for _ in range(60):
                total += 1
                exceeded += obs["demand_pressure"] >= 1.0
                violated += any(obs["violations"].values())
                obs = env7.step(1)["observation"]
        check(f"{scenario} 압력 ≥ 1.0 (%)", round(exceeded / total * 100, 1),
              EXPECTED_PRESSURE[scenario], tol=3.0)
        check(f"{scenario} 초기 배분 위반 (%)", round(violated / total * 100, 1),
              EXPECTED_VIOLATION[scenario], tol=3.0)

    print(f"\n{'실패 ' + str(len(failures)) + '건: ' + ', '.join(failures) if failures else '전부 통과'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
