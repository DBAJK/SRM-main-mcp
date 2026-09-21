"""③ slice-market 자체 검사 — 설계서의 실측치와 대조한다. (B 소유)

    python tools/check_market.py

`claude/spec/market.md` 의 예시 값은 engine.py 를 실제로 실행해 얻은 것이다. 추출본이
원본과 같은 값을 내는지 여기서 못 박는다. fastmcp 없이 돌아가므로 0단계 전에도 쓸 수 있다
(`scoring.py` 와 `common/const.py` 만 import 한다).

도구 자체(procure · update_rating)는 fastmcp 가 필요하므로 여기서는 산술만 검증한다.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from srm_mcp.common import paths  # noqa: E402
from srm_mcp.common.const import (GAIN_SCALE, RATING_DELTA, REFERENCE_BANDWIDTH,  # noqa: E402
                              cost_per_step)
from srm_mcp.common.store import read_json  # noqa: E402
from srm_mcp.market import scoring  # noqa: E402

QOS = {"latency": 1.0, "bandwidth": 400, "reliability": 99.99}

# spec/market.md — score_offerings("URLLC", QOS) 실측값
EXPECTED_RANKING = [
    ("vendor-1", 99.20), ("vendor-5", 98.00), ("vendor-3", 97.60),
    ("vendor-4", 91.76), ("vendor-2", 86.20),
]

# spec/market.md — explain_score("vendor-1", "URLLC", QOS) 실측값
EXPECTED_CONTRIBUTIONS = {"latency": 30.00, "bandwidth": 8.57, "reliability": 21.43,
                          "reputation": 19.20, "price": 20.00}
EXPECTED_WEIGHTS = {"latency": 0.35, "bandwidth": 0.10, "reliability": 0.25,
                    "reputation": 0.20, "price": 0.20}

failures: list[str] = []


def check(label: str, got, want, tol: float = 0.005) -> None:
    ok = abs(got - want) <= tol if isinstance(want, float) else got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {label}: {got!r}" + ("" if ok else f"  (기대 {want!r})"))
    if not ok:
        failures.append(label)


def main() -> int:
    vendors = read_json(paths.VENDORS_JSON)
    if vendors is None:
        print("data/vendors.json 이 없다. python tools/bootstrap_vendors.py 먼저.", file=sys.stderr)
        return 1

    print("1. score_offerings('URLLC', qos) — 순위와 점수")
    scored = sorted(
        ((v["id"], round(scoring.score_offering(v, "URLLC", QOS), 2)) for v in vendors),
        key=lambda row: row[1], reverse=True,
    )
    for rank, ((got_id, got_score), (want_id, want_score)) in enumerate(
            zip(scored, EXPECTED_RANKING), start=1):
        check(f"rank {rank} 벤더", got_id, want_id)
        check(f"rank {rank} 점수", got_score, want_score)

    print("\n2. explain_score('vendor-1', 'URLLC', qos) — 분해 (정정 J)")
    vendor1 = next(v for v in vendors if v["id"] == "vendor-1")
    bd = scoring.breakdown(vendor1, "URLLC", QOS)
    check("total = score_offerings 의 score", round(bd["total"], 2), 99.20)
    check("기여분 합 = total", round(sum(bd["contributions"].values()), 2), round(bd["total"], 2))
    for criterion, want in EXPECTED_CONTRIBUTIONS.items():
        check(f"contributions[{criterion}]", round(bd["contributions"][criterion], 2), want)
    for criterion, want in EXPECTED_WEIGHTS.items():
        check(f"weights[{criterion}]", round(bd["weights"][criterion], 4), want)
    check("total ≠ 92.00 (get_score_breakdown 의 rating 오독)",
          abs(round(bd["total"], 2) - 92.00) > 0.01, True)

    print("\n3. procure 산술 — vendor-1 URLLC, duration_steps=10, current_step=12 (W2·W3)")
    urllc = vendor1["offerings"]["URLLC"]
    check("cost_total (2500.0 이 아니다)", round(cost_per_step(urllc["cost"]) * 10, 2), 625.0)
    check("capacity_gain",
          round(urllc["bandwidth"] / REFERENCE_BANDWIDTH["URLLC"] * GAIN_SCALE, 4), 0.25)
    check("expires_at_step", 12 + 10, 22)
    for vendor_id, want_gain in (("vendor-2", 0.20), ("vendor-1", 0.25), ("vendor-3", 0.30)):
        bw = next(v for v in vendors if v["id"] == vendor_id)["offerings"]["URLLC"]["bandwidth"]
        check(f"capacity_gain[{vendor_id}]",
              round(bw / REFERENCE_BANDWIDTH["URLLC"] * GAIN_SCALE, 4), want_gain)

    print("\n4. update_rating 산술 — δ 비대칭")
    up, down = RATING_DELTA
    check("δ(sla_met)", up, 0.05)
    check("δ(위반)", down, -0.20)
    check("vendor-1 위반 1회: 4.80 → 4.60", round(min(5.0, max(1.0, 4.80 + down)), 2), 4.60)
    check("상한 클립: 4.98 + 0.05 → 5.00", round(min(5.0, max(1.0, 4.98 + up)), 2), 5.00)

    print(f"\n{'실패 ' + str(len(failures)) + '건: ' + ', '.join(failures) if failures else '전부 통과'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
