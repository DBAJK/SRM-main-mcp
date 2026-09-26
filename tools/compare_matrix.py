"""두 매트릭스를 같은 칸끼리 비교한다 — 비교군 · 사다리 · 시나리오 · 위반 원인 · 개입 탈출.

    .venv310/Scripts/python tools/compare_matrix.py before-B1 after-B1

`runs/_matrix/<이름>/summary.json` 을 읽는다. 개입 탈출(proposed 칸)은 칸별 `decisions.json` 이 필요하다 —
`runs/_matrix/<이름>/raw/<run_id>/` 에 보관본이 있으면 그것을, 없으면 `runs/<run_id>/` 를 쓴다.
매트릭스는 run_id 가 같아 다음 매트릭스가 `runs/<run_id>/` 를 덮어쓰므로, 비교할 매트릭스는 raw 에
보관해 둔다(workplan-2 C-20). 규칙 판단자 칸은 결정적이라 차이는 전부 코드 변경에서 온다.
표준편차는 칸 간 모집단 표준편차다(1차 M-0 표와 같은 방식).
"""
from __future__ import annotations

import json
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "runs" / "_matrix"
VARIANTS = ("baseline", "arm1_rule", "arm2_rule", "proposed_rule")
SCENARIOS = ("normal", "emergency", "special_event", "iot_surge", "mixed")
SEEDS = (0, 1, 2)
LADDER = (("baseline", "arm1_rule", "상황 인지   arm1 − baseline"),
          ("arm1_rule", "arm2_rule", "정책 선택   arm2 − arm1"),
          ("arm2_rule", "proposed_rule", "선택적 개입 proposed − arm2"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def load(name: str) -> dict:
    rows = json.loads((MATRIX / name / "summary.json").read_text(encoding="utf-8"))
    return {(r["variant"], r["scenario"], r["seed"]): r for r in rows}


def rate(r: dict) -> float:
    return r["sla_violations"] / r["sla_scored"]


def mean_sd(xs: list[float]) -> str:
    return f"{st.mean(xs):.3f} ±{st.pstdev(xs):.3f}"


def escalation_line(name: str, run_id: str) -> str | None:
    """스텝마다 개입(E)인지 자율(.)인지. 원본이 없으면 None."""
    for base in (MATRIX / name / "raw" / run_id, ROOT / "runs" / run_id):
        path = base / "decisions.json"
        if path.exists():
            book = json.loads(path.read_text(encoding="utf-8"))
            ds = sorted((d for d in book["decisions"] if d.get("kind") == "decision"),
                        key=lambda d: d["step"])
            esc = {d["step"] for d in book["decisions"] if d.get("kind") == "escalation"}
            return "".join("E" if d["step"] in esc else "." for d in ds)
    return None


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    b_name, a_name = sys.argv[1], sys.argv[2]
    B, A = load(b_name), load(a_name)
    keys = lambda v: [(v, s, sd) for s in SCENARIOS for sd in SEEDS]  # noqa: E731

    print(f"{b_name} → {a_name}\n\n비교군별 (15칸 평균 ± 칸 간 표준편차)")
    for v in VARIANTS:
        b = [rate(B[k]) for k in keys(v)]
        a = [rate(A[k]) for k in keys(v)]
        better = sum(1 for x, y in zip(b, a) if y < x - 1e-9)
        worse = sum(1 for x, y in zip(b, a) if y > x + 1e-9)
        ib = st.mean(B[k]["intervention_rate"] for k in keys(v))
        ia = st.mean(A[k]["intervention_rate"] for k in keys(v))
        pb = st.mean(B[k]["perception_accuracy"] for k in keys(v))
        pa = st.mean(A[k]["perception_accuracy"] for k in keys(v))
        print(f"  {v:<14} SLA 위반율 {mean_sd(b)} → {mean_sd(a)} · 좋아짐 {better} · 같음 "
              f"{15 - better - worse} · 나빠짐 {worse} · 개입률 {ib:.3f} → {ia:.3f} · 상황 인지 {pb:.3f} → {pa:.3f}")

    print("\n사다리 (같은 시나리오 · 시드 15쌍의 SLA 위반율 차이, 음수가 좋아짐)")
    for lo, hi, label in LADDER:
        for tag, D in (("전", B), ("후", A)):
            d = [rate(D[(hi, s, sd)]) - rate(D[(lo, s, sd)]) for s in SCENARIOS for sd in SEEDS]
            g, w = sum(1 for x in d if x < -1e-9), sum(1 for x in d if x > 1e-9)
            print(f"  {label:<30} {tag}  {st.mean(d):+.3f}   좋아짐 {g} · 같음 {15 - g - w} · 나빠짐 {w}")

    print("\n시나리오별 SLA 위반율 (시드 3개 평균) 전 → 후")
    for s in SCENARIOS:
        cells = [f"{v.split('_')[0]} {st.mean(rate(B[(v, s, sd)]) for sd in SEEDS):.2f}→"
                 f"{st.mean(rate(A[(v, s, sd)]) for sd in SEEDS):.2f}" for v in VARIANTS]
        print(f"  {s:<14} " + " · ".join(cells))

    print("\n위반의 원인 (60칸 합) 전 → 후")
    for tag, D in (("전", B), ("후", A)):
        tot = sum(r["sla_violations"] for r in D.values())
        av = sum(r["sla_avoidable"] for r in D.values())
        sc = sum(r["sla_structural"] for r in D.values())
        print(f"  {tag}  위반 {tot} · 배분 탓 {av} ({av / tot:.0%}) · 구조적 {sc} ({sc / tot:.0%})")

    print("\n개입 탈출 — proposed 칸 (E=개입). 탈출 = 개입 다음 스텝이 자율")
    tot = {b_name: [0, 0, 0], a_name: [0, 0, 0]}
    for s in SCENARIOS:
        for sd in SEEDS:
            rid = f"proposed_rule-{s}-s{sd}"
            parts = []
            for name in (b_name, a_name):
                line = escalation_line(name, rid)
                if line is None:
                    parts.append("원본 없음")
                    continue
                exits = sum(1 for i in range(1, len(line)) if line[i - 1] == "E" and line[i] == ".")
                tot[name][0] += line.count("E")
                tot[name][1] += len(line)
                tot[name][2] += exits
                parts.append(f"개입 {line.count('E')}/{len(line)} · 탈출 {exits}")
            print(f"  {rid:<30} " + "  →  ".join(parts))
    for name, (e, n, x) in tot.items():
        if n:
            print(f"  합계 {name}: 개입 {e}/{n} ({e / n:.3f}) · 탈출 {x}회")
    return 0


if __name__ == "__main__":
    sys.exit(main())
