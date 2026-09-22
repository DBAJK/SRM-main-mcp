"""⑤ slice-feedback 자체 검사 — 설계서의 실측치와 완료 판정을 대조한다. (B 소유)

    python tools/check_feedback.py

`claude/spec/feedback.md` 의 예시 응답과 ROLES.md §3.2 의 B-3 완료 판정 2개를 건다.

    · warm 120스텝에서 reliability.json 값이 실제로 움직인다
    · report_outcome 이 applied · requested · actuator_delta 를 모두 반환 (V5)

①이 아직 없으므로 합성 관측으로 돌린다. 산출물은 `runs/_check-feedback-s0/` 와
`data/reliability.json` 의 임시본이며, 끝나면 지운다 — 실제 실행 데이터를 건드리지 않는다.
"""
from __future__ import annotations

import shutil
import sys
import types
from pathlib import Path

# Windows 기본 콘솔은 cp949 라 '—' 한 글자에 UnicodeEncodeError 로 죽는다.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:  # noqa: SIM105
    import fastmcp  # noqa: F401
except ImportError:
    stub = types.ModuleType("fastmcp")

    class _FastMCP:
        def __init__(self, name): self.name = name
        def tool(self, *_a, **_kw): return lambda fn: fn
        def run(self): raise RuntimeError("스텁이다")

    stub.FastMCP = _FastMCP
    sys.modules["fastmcp"] = stub
    print("fastmcp 없음 — 스텁으로 도구 함수만 검사한다\n")

import os  # noqa: E402

RUN_ID = "_check-feedback-s0"
os.environ["SLICE_MEMORY_MODE"] = "cold"      # data/reliability.json 을 안 건드린다
os.environ["SLICE_RUN_ID"] = RUN_ID

from srm_mcp.common import paths  # noqa: E402
from srm_mcp.common.store import read_json, write_json  # noqa: E402
from srm_mcp.feedback import reliability, scoring  # noqa: E402
from srm_mcp.feedback import server as s  # noqa: E402

failures: list[str] = []


def check(label: str, got, want, tol: float = 0.0005) -> None:
    ok = abs(got - want) <= tol if isinstance(want, float) and isinstance(got, float) else got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {label}: {got!r}" + ("" if ok else f"  (기대 {want!r})"))
    if not ok:
        failures.append(label)


def seed_book(decisions: list[dict]) -> None:
    write_json(paths.decisions_json(RUN_ID), {
        "run_id": RUN_ID,
        "config": {"scenario": "emergency", "seed": 0, "arm": "proposed",
                   "desc_mode": "minimal", "tau": 0.45},
        "decisions": decisions,
    })


def decision(step: int, policy: str = "rule_based", vendor_id=None) -> dict:
    return {"decision_id": f"{RUN_ID}-{step:04d}", "step": step, "kind": "decision",
            "situation": "emergency", "chosen_policy": policy,
            "allocation": {"embb": 0.20, "urllc": 0.70, "mmtc": 0.10},
            "confidence": {"intrinsic": 0.556, "empirical": 0.88, "combined": 0.70},
            "rationale": "합성", "vendor_id": vendor_id}


def cleanup() -> None:
    shutil.rmtree(paths.run_dir(RUN_ID), ignore_errors=True)


def main() -> int:
    cleanup()

    # spec/feedback.md 예시 — step() 후의 관측
    observed = {"step": 13,
                "traffic":     {"embb": 0.550, "urllc": 0.720, "mmtc": 0.180},
                "allocation":  {"embb": 0.340, "urllc": 0.490, "mmtc": 0.170},
                "utilization": {"embb": 1.618, "urllc": 1.469, "mmtc": 1.059},
                "violations":  {"embb": True, "urllc": True, "mmtc": True},
                "capacity":    {"embb": 1.0, "urllc": 1.0, "mmtc": 1.0}}

    print("1. spec/feedback.md 예시 — report_outcome")
    seed_book([decision(12)])
    write_json(paths.run_dir(RUN_ID) / "reliability.json",
               {**reliability.initial_table(),
                "rule_based": {"r": 0.880, "n": 10, "alpha": 0.2, "errors": []}})
    out = s.report_outcome(f"{RUN_ID}-0012", observed)

    check("sla_met", out["sla_met"], False)
    check("policy", out["policy"], "rule_based")
    check("error", round(out["error"], 3), 0.086)
    check("ideal_allocation",
          {k: round(v, 3) for k, v in out["ideal_allocation"].items()},
          {"embb": 0.426, "urllc": 0.418, "mmtc": 0.157})
    check("reliability_before", round(out["reliability_before"], 3), 0.880)
    check("reliability_after  (0.8 × 0.880)", round(out["reliability_after"], 3), 0.704)

    print("\n2. 완료 판정 — V5 요청값·적용값·액추에이터 차이")
    check("applied_allocation", out["applied_allocation"],
          {"embb": 0.340, "urllc": 0.490, "mmtc": 0.170})
    check("requested_allocation", out["requested_allocation"],
          {"embb": 0.20, "urllc": 0.70, "mmtc": 0.10})
    check("actuator_delta", round(out["actuator_delta"], 3), 0.210)
    check("observed_violations", out["observed_violations"],
          {"embb": True, "urllc": True, "mmtc": True})
    # ⚠️ ROLES.md §3.1 B-3 와 설계서는 요청 기준 error 를 0.316 이라 적었으나, 같은 문서가
    #    제시한 입력({0.20,0.70,0.10} vs 이상 {0.426,0.418,0.157})에 L1/2 를 적용하면
    #    0.282 다. 적용 기준 0.086 과 actuator_delta 0.210 은 정확히 재현되므로 산식은 맞고
    #    0.316 쪽이 어긋난 것으로 본다. 주장("기준이 다르면 배가 넘게 벌어진다")은 그대로 성립.
    requested_error = scoring.distance(out["requested_allocation"], out["ideal_allocation"])
    check("요청 기준 error", round(requested_error, 3), 0.282)
    check("적용 기준의 3배 이상으로 벌어진다", requested_error / out["error"] > 3.0, True)
    check("vendor_id", out["vendor_id"], None)

    print("\n3. ④ 레코드에 outcome 이 덧붙는다")
    book = read_json(paths.decisions_json(RUN_ID))
    record = book["decisions"][0]
    check("outcome 존재", record.get("outcome") is not None, True)
    check("scored_at_step", record["outcome"]["scored_at_step"], 13)
    check("두 번 채점 거부", s.report_outcome(f"{RUN_ID}-0012", observed).get("error"),
          "already_scored")

    print("\n4. 호출 순서 위반 — step() 전 채점 (flow/errors.md)")
    seed_book([decision(12), decision(20)])
    early = s.report_outcome(f"{RUN_ID}-0020", {**observed, "step": 20})
    check("premature_scoring", early.get("error"), "premature_scoring")
    print(f"        reason: {early.get('reason')}")
    check("없는 decision_id", s.report_outcome(f"{RUN_ID}-9999", observed).get("error"),
          "unknown_decision")
    check("형식 위반", s.report_outcome("abc", observed).get("error"),
          "malformed_decision_id")

    print("\n5. capacity 를 빼면 안 된다")
    doubled = {**observed, "capacity": {"embb": 2.0, "urllc": 1.0, "mmtc": 1.0}}
    check("capacity 1.0 vs 2.0 의 ideal 이 다르다",
          scoring.ideal_allocation(observed) != scoring.ideal_allocation(doubled), True)
    print(f"        capacity×1 → {({k: round(v, 3) for k, v in scoring.ideal_allocation(observed).items()})}")
    print(f"        capacity×2 → {({k: round(v, 3) for k, v in scoring.ideal_allocation(doubled).items()})}")

    print("\n6. 축소 보정 — 첫 성공 1회로 1.0이 되지 않는다 (설계서 §6.2)")
    r1, n1 = reliability.update(0.5, 0, True)
    check("r (1회 성공)", round(r1, 4), 0.6)
    check("effective (1회 성공)", round(reliability.effective(r1, n1), 4), 0.5167)
    check("effective(0.910, 120)", round(reliability.effective(0.910, 120), 3), 0.894)
    check("effective(0.840, 95)", round(reliability.effective(0.840, 95), 3), 0.823)
    check("effective(0.420, 6)", round(reliability.effective(0.420, 6), 3), 0.456)

    print("\n7. 완료 판정 — warm 120스텝에서 reliability 가 움직인다")
    cleanup()
    seed_book([decision(t) for t in range(120)])
    write_json(paths.run_dir(RUN_ID) / "reliability.json", reliability.initial_table())

    start = s.get_reliability_table()["rule_based"]
    trail = []
    for t in range(119):
        # 앞 60스텝은 위반, 뒤는 충족 — 신뢰도가 따라오는지 본다
        violated = t < 60
        obs = {**observed, "step": t + 1,
               "violations": {k: violated for k in ("embb", "urllc", "mmtc")}}
        s.report_outcome(f"{RUN_ID}-{t:04d}", obs)
        if t in (0, 30, 59, 60, 70, 90, 118):
            trail.append((t, round(s.get_reliability_table()["rule_based"]["reliability"], 3)))
    end = s.get_reliability_table()["rule_based"]

    for step, value in trail:
        print(f"        step {step:3}  r = {value}")
    check("n 이 119회 누적", end["n"], 119)
    check("r 이 초기값에서 움직였다", end["reliability"] != start["reliability"], True)
    check("위반 구간 끝에서 r 이 낮다", trail[2][1] < 0.1, True)
    check("충족 구간 끝에서 r 이 높다", trail[-1][1] > 0.9, True)
    check("recent_error 가 채워진다", end["recent_error"] is not None, True)
    print(f"        최종: {end}")

    print("\n8. recent_error — ②의 공급선 (V4)")
    check("표본 없으면 null", reliability.recent_error([]), None)
    check("1건이면 그 값", reliability.recent_error([0.3]), 0.3)
    check("최근 N회만 유지", len(reliability.push_error([0.1] * 9, 0.2)), 5)
    check("최근 값에 더 큰 가중", reliability.recent_error([0.0, 0.0, 0.0, 0.0, 0.6]) > 0.1, True)

    cleanup()
    print(f"\n{'실패 ' + str(len(failures)) + '건: ' + ', '.join(failures) if failures else '전부 통과'}")
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        cleanup()
