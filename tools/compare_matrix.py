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
SEEDS: tuple[int, ...] = (0, 1, 2)   # load() 가 실제 요약을 보고 덮어쓴다
LADDER = (("baseline", "arm1_rule", "상황 인지   arm1 − baseline"),
          ("arm1_rule", "arm2_rule", "정책 선택   arm2 − arm1"),
          ("arm2_rule", "proposed_rule", "선택적 개입 proposed − arm2"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def load(name: str) -> dict:
    rows = json.loads((MATRIX / name / "summary.json").read_text(encoding="utf-8"))
    return {(r["variant"], r["scenario"], r["seed"]): r for r in rows}


def narrow(*tables: dict) -> None:
    """실제로 돌아간 변형 · 시나리오 · 시드만 남긴다. 전역을 덮어쓴다.

    상수를 박아두면 시드를 늘리거나 변형 일부만 돌린 매트릭스에서 KeyError 가 나거나
    앞 3개만 조용히 쓰게 된다.
    """
    global VARIANTS, SCENARIOS, SEEDS
    common = set(tables[0])
    for t in tables[1:]:
        common &= set(t)
    VARIANTS = tuple(v for v in VARIANTS if any(k[0] == v for k in common))
    SCENARIOS = tuple(s for s in SCENARIOS if any(k[1] == s for k in common))
    SEEDS = tuple(sorted({k[2] for k in common}))


def rate(r: dict) -> float:
    return r["sla_violations"] / r["sla_scored"]


# t(0.975, df). 칸이 수십 개라 정규근사(1.96)를 쓰면 경계에서 유의하다고 잘못 읽는다.
_T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
         8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 14: 2.145, 16: 2.120,
         19: 2.093, 24: 2.064, 29: 2.045, 39: 2.023, 59: 2.001}


def t975(df: int) -> float:
    if df < 1:
        return float("inf")
    return next((v for k, v in sorted(_T975.items()) if df <= k), 1.96)


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
    narrow(B, A)
    missing = [k for v in VARIANTS for k in ((v, s, sd) for s in SCENARIOS for sd in SEEDS)
               if k not in B or k not in A]
    if missing:
        print(f"⚠ 두 매트릭스에 공통으로 없는 칸 {len(missing)}개는 뺐다: {missing[:4]} …"
              if len(missing) > 4 else f"⚠ 공통으로 없는 칸: {missing}")
    print(f"  칸 구성 — 변형 {len(VARIANTS)} × 시나리오 {len(SCENARIOS)} × 시드 {len(SEEDS)}"
          f" = {len(VARIANTS) * len(SCENARIOS) * len(SEEDS)}칸")
    keys = lambda v: [(v, s, sd) for s in SCENARIOS for sd in SEEDS]  # noqa: E731

    print(f"{b_name} → {a_name}\n\n비교군별 "
          f"({len(SCENARIOS) * len(SEEDS)}칸 평균 ± 칸 간 표준편차)")
    for v in VARIANTS:
        b = [rate(B[k]) for k in keys(v)]
        a = [rate(A[k]) for k in keys(v)]
        better = sum(1 for x, y in zip(b, a) if y < x - 1e-9)
        worse = sum(1 for x, y in zip(b, a) if y > x + 1e-9)
        ib = st.mean(B[k]["intervention_rate"] for k in keys(v))
        ia = st.mean(A[k]["intervention_rate"] for k in keys(v))
        pb = st.mean(B[k]["perception_accuracy"] for k in keys(v))
        pa = st.mean(A[k]["perception_accuracy"] for k in keys(v))
        n = len(b)
        # SLA 만 보면 "비용을 더 써서 좋아진 것" 과 구별이 안 된다.
        cb = st.mean(B[k].get("procurement_cost", 0.0) for k in keys(v))
        ca = st.mean(A[k].get("procurement_cost", 0.0) for k in keys(v))
        print(f"  {v:<14} SLA 위반율 {mean_sd(b)} → {mean_sd(a)} · 좋아짐 {better} · 같음 "
              f"{n - better - worse} · 나빠짐 {worse} · 개입률 {ib:.3f} → {ia:.3f} · 상황 인지 {pb:.3f} → {pa:.3f}")
        print(f"  {'':<14} 조달비 칸평균 {cb:,.0f} → {ca:,.0f}"
              + (f"  ({(ca - cb) / cb:+.0%})" if cb else ""))

    print(f"\n사다리 (같은 시나리오 · 시드 {len(SCENARIOS) * len(SEEDS)}쌍의 SLA 위반율 "
          f"차이, 음수가 좋아짐 · 95%CI 는 t분포)")
    for lo, hi, label in LADDER:
        if lo not in VARIANTS or hi not in VARIANTS:
            print(f"  {label:<30} — 이 매트릭스에 {lo}/{hi} 칸이 없다. 건너뜀")
            continue
        for tag, D in (("전", B), ("후", A)):
            d = [rate(D[(hi, s, sd)]) - rate(D[(lo, s, sd)]) for s in SCENARIOS for sd in SEEDS]
            g, w = sum(1 for x in d if x < -1e-9), sum(1 for x in d if x > 1e-9)
            # 평균만 내면 칸마다 부호가 갈리는 것을 못 본다.
            m, sd_ = st.mean(d), (st.stdev(d) if len(d) > 1 else 0.0)
            half = t975(len(d) - 1) * sd_ / (len(d) ** 0.5) if len(d) > 1 else 0.0
            flag = "0 포함 ← 방향 주장 불가" if (m - half) * (m + half) <= 0 else "0 불포함"
            print(f"  {label:<30} {tag}  {m:+.3f} ±{sd_:.3f}  [{m - half:+.3f}, {m + half:+.3f}] "
                  f"{flag}   좋아짐 {g} · 같음 {len(d) - g - w} · 나빠짐 {w}")
            # 풀링하면 한 시나리오의 큰 효과가 나머지의 0 에 희석되고 분산만 커진다.
            for s in SCENARIOS:
                ds = [rate(D[(hi, s, sd)]) - rate(D[(lo, s, sd)]) for sd in SEEDS]
                ms = st.mean(ds)
                sds = st.stdev(ds) if len(ds) > 1 else 0.0
                hs = t975(len(ds) - 1) * sds / (len(ds) ** 0.5) if len(ds) > 1 else 0.0
                fs = "0 포함" if (ms - hs) * (ms + hs) <= 0 else "0 불포함 ←"
                print(f"      {s:<16} {tag}  {ms:+.3f} ±{sds:.3f} "
                      f"[{ms - hs:+.3f}, {ms + hs:+.3f}] {fs}  "
                      + " ".join(f"{x:+.3f}" for x in ds))

    print(f"\n시나리오별 SLA 위반율 (시드 {len(SEEDS)}개 평균) 전 → 후")
    for s in SCENARIOS:
        cells = [f"{v.split('_')[0]} {st.mean(rate(B[(v, s, sd)]) for sd in SEEDS):.2f}→"
                 f"{st.mean(rate(A[(v, s, sd)]) for sd in SEEDS):.2f}" for v in VARIANTS]
        print(f"  {s:<14} " + " · ".join(cells))

    print(f"\n위반의 원인 ({len(VARIANTS) * len(SCENARIOS) * len(SEEDS)}칸 합) 전 → 후")
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
