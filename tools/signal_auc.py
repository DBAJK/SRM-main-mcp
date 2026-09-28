"""M-1 — 개입 판정 신호가 SLA 위반을 얼마나 미리 가려내나(AUC) · 개입 연속 · 탈출.

    .venv310/Scripts/python tools/signal_auc.py m1-normal-s0 m1-emergency-s0
    .venv310/Scripts/python tools/signal_auc.py runs/_matrix/before-B1/raw/proposed_rule-normal-s0 --max-step 30

인자는 run_id(`runs/<run_id>/`) 또는 실행 폴더 경로. `decisions.json` 의 kind=decision 레코드를 쓴다.
AUC(1차 workplan §6): 위반 스텝(sla_met=False)을 양성으로 두고 신호를 "위험" 방향으로 맞춰 Mann-Whitney 로
계산한다 — combined · intrinsic · empirical 은 낮을수록 위험, worst u/θ(결정 시점 관측의 maxₖ uₖ/θₖ)는 높을수록
위험. 0.5 = 구분 못 함 · 1.0 = 완벽. "자율만" 은 개입 스텝을 뺀 것이다 — 개입 스텝의 SLA 는 폴백 배분의 결과라서.
⚠️ **AUC 옆의 ± 는 95%CI 반폭(Hanley–McNeil)이다.** 30스텝(위반 19 · 충족 11)이면 ±0.22 라
0.5 와 구분되지 않는다 — `(0.5포함)` 이 붙으면 그 신호는 **구분력을 주장할 수 없다**.
±0.10 까지 줄이려면 약 120스텝이 필요하다 — `--pool` 로 시드 · 시나리오를 묶는다(단, 한 실행 안의
스텝은 독립이 아니라 묶은 CI 는 낙관적이다). 1차 §2 D2 의 판정 기준(0.7 유지 / 0.6 미만 게이트)은
30~60스텝 단일 실행으로는 **판정 불가**다 — AUC 0.7 의 CI 가 [0.51, 0.89] 로 0.6 과 겹친다.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
THRESHOLDS = {"embb": 0.9, "urllc": 1.2, "mmtc": 0.8}
SIGNALS = (("combined", -1), ("intrinsic", -1), ("empirical", -1), ("worst u/θ", +1))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def auc(pos: list[float], neg: list[float]) -> tuple[float, float] | None:
    """(AUC, 95%CI 반폭). 반폭은 Hanley–McNeil 근사다.

    맨숫자만 내면 30스텝짜리 AUC 0.49 를 "무작위보다 나쁘다" 로 읽게 된다. 실제로는
    위반 19 · 충족 11 에서 95%CI 가 ±0.22 라 0.5 와 구분되지 않는다.
    """
    if not pos or not neg:
        return None
    m, n = len(pos), len(neg)
    a = sum((p > q) + 0.5 * (p == q) for p in pos for q in neg) / (m * n)
    q1, q2 = a / (2 - a), 2 * a * a / (1 + a)
    var = (a * (1 - a) + (m - 1) * (q1 - a * a) + (n - 1) * (q2 - a * a)) / (m * n)
    return a, 1.96 * math.sqrt(max(var, 0.0))


def signal(d: dict, key: str) -> float | None:
    if key == "worst u/θ":
        obs = d.get("observation") or {}
        u, thr = obs.get("utilization") or {}, obs.get("thresholds") or THRESHOLDS
        return max(float(u[k]) / float(thr[k]) for k in THRESHOLDS) if u else None
    v = (d.get("confidence") or {}).get(key)
    return None if v is None else float(v)


def load(target: str, max_step: int | None) -> tuple[str, list[dict], set, list[dict]]:
    """(이름, 결정 레코드, 개입 스텝, 채점된 레코드)."""
    folder = Path(target) if Path(target).exists() else ROOT / "runs" / target
    book = json.loads((folder / "decisions.json").read_text(encoding="utf-8"))
    ds = sorted((d for d in book["decisions"] if d.get("kind") == "decision"), key=lambda d: d["step"])
    if max_step is not None:
        ds = [d for d in ds if d["step"] < max_step]
    esc = {d["step"] for d in book["decisions"] if d.get("kind") == "escalation"}
    scored = [d for d in ds if (d.get("outcome") or {}).get("sla_met") is not None]
    return folder.name, ds, esc, scored


def auc_lines(rows: list[tuple[dict, bool]]) -> list[str]:
    """rows = [(결정 레코드, 개입했나)]. 전체 · 자율만 두 줄."""
    out = []
    for name, subset in (("전체", [d for d, _ in rows]), ("자율만", [d for d, e in rows if not e])):
        parts = []
        for key, sign in SIGNALS:
            pairs = [(sign * signal(d, key), d["outcome"]["sla_met"] is False)
                     for d in subset if signal(d, key) is not None]
            r = auc([v for v, p in pairs if p], [v for v, p in pairs if not p])
            if r is None:
                parts.append(f"{key} —")
            else:
                a, h = r
                # 0.5 를 포함하면 그 신호는 위반을 가려내지 못한다는 뜻이다.
                parts.append(f"{key} {a:.3f}±{h:.3f}{'' if abs(a - 0.5) > h else '(0.5포함)'}")
        n_pos = sum(1 for d in subset if d["outcome"]["sla_met"] is False)
        out.append(f"   AUC [{name} · 위반 {n_pos}/{len(subset)}]  " + " · ".join(parts))
    return out


def report(target: str, max_step: int | None) -> list[tuple[dict, bool]]:
    name, ds, esc, scored = load(target, max_step)
    line = "".join("E" if d["step"] in esc else "." for d in ds)
    streak = best = exits = 0
    for i, ch in enumerate(line):
        streak = streak + 1 if ch == "E" else 0
        best = max(best, streak)
        exits += ch == "." and i > 0 and line[i - 1] == "E"
    viol = sum(1 for d in scored if d["outcome"]["sla_met"] is False)
    rows = [(d, d["step"] in esc) for d in scored]
    print(f"\n== {name}  ({len(ds)}스텝 · 채점 {len(scored)} · SLA 위반 {viol})")
    print(f"   개입 {line.count('E')} · 최장 연속 {best} · 탈출 {exits} · {line}")
    print("\n".join(auc_lines(rows)))
    return rows


def expand(targets: list[str]) -> list[str]:
    """`runs/_matrix/after-B1/raw/proposed_rule-*` 같은 패턴을 폴더 목록으로 (PowerShell 은 안 펼친다)."""
    out = []
    for t in targets:
        if any(ch in t for ch in "*?["):
            base = Path(t) if Path(t).is_absolute() else ROOT / t
            hits = sorted(p for p in base.parent.glob(base.name) if (p / "decisions.json").is_file())
            out += [str(p) for p in hits]
        else:
            out.append(t)
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("runs", nargs="+", help="run_id · 실행 폴더 · 또는 * 패턴")
    p.add_argument("--max-step", type=int, default=None, help="이 스텝 미만만 (긴 실행의 앞부분과 비교할 때)")
    p.add_argument("--pool", action="store_true",
                   help="실행을 합쳐 한 번 더 AUC 를 낸다 (시드 · 시나리오 묶기, workplan-2 C-20d). "
                        "한 실행 안의 스텝은 서로 독립이 아니라 CI 는 실제보다 좁게 나온다")
    p.add_argument("--quiet", action="store_true", help="--pool 일 때 실행별 출력을 생략")
    args = p.parse_args()
    targets = expand(args.runs)
    if not targets:
        print("대상 실행이 없다", file=sys.stderr)
        return 1
    pooled: list[tuple[dict, bool]] = []
    for r in targets:
        if args.pool and args.quiet:
            _, _, esc, scored = load(r, args.max_step)
            pooled += [(d, d["step"] in esc) for d in scored]
        else:
            pooled += report(r, args.max_step)
    if args.pool:
        esc_n = sum(1 for _, e in pooled if e)
        print(f"\n== 합침 · 실행 {len(targets)}개 · 채점 {len(pooled)} · 개입 {esc_n}")
        print("\n".join(auc_lines(pooled)))
        print("   ⚠ 한 실행 안의 스텝은 서로 이어져 있어 독립 표본이 아니다 — 이 CI 는 낙관적이다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
