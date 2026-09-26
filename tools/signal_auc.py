"""M-1 — 개입 판정 신호가 SLA 위반을 얼마나 미리 가려내나(AUC) · 개입 연속 · 탈출.

    .venv310/Scripts/python tools/signal_auc.py m1-normal-s0 m1-emergency-s0
    .venv310/Scripts/python tools/signal_auc.py runs/_matrix/before-B1/raw/proposed_rule-normal-s0 --max-step 30

인자는 run_id(`runs/<run_id>/`) 또는 실행 폴더 경로. `decisions.json` 의 kind=decision 레코드를 쓴다.
AUC(1차 workplan §6): 위반 스텝(sla_met=False)을 양성으로 두고 신호를 "위험" 방향으로 맞춰 Mann-Whitney 로
계산한다 — combined · intrinsic · empirical 은 낮을수록 위험, worst u/θ(결정 시점 관측의 maxₖ uₖ/θₖ)는 높을수록
위험. 0.5 = 구분 못 함 · 1.0 = 완벽. "자율만" 은 개입 스텝을 뺀 것이다 — 개입 스텝의 SLA 는 폴백 배분의 결과라서.
표본이 30스텝 안팎이면 AUC 는 ±0.1 정도 흔들린다. 방향만 읽는다.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
THRESHOLDS = {"embb": 0.9, "urllc": 1.2, "mmtc": 0.8}
SIGNALS = (("combined", -1), ("intrinsic", -1), ("empirical", -1), ("worst u/θ", +1))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def auc(pos: list[float], neg: list[float]) -> float | None:
    if not pos or not neg:
        return None
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return round(wins / (len(pos) * len(neg)), 3)


def signal(d: dict, key: str) -> float | None:
    if key == "worst u/θ":
        obs = d.get("observation") or {}
        u, thr = obs.get("utilization") or {}, obs.get("thresholds") or THRESHOLDS
        return max(float(u[k]) / float(thr[k]) for k in THRESHOLDS) if u else None
    v = (d.get("confidence") or {}).get(key)
    return None if v is None else float(v)


def report(target: str, max_step: int | None) -> None:
    folder = Path(target) if Path(target).exists() else ROOT / "runs" / target
    book = json.loads((folder / "decisions.json").read_text(encoding="utf-8"))
    ds = sorted((d for d in book["decisions"] if d.get("kind") == "decision"), key=lambda d: d["step"])
    if max_step is not None:
        ds = [d for d in ds if d["step"] < max_step]
    esc = {d["step"] for d in book["decisions"] if d.get("kind") == "escalation"}
    scored = [d for d in ds if (d.get("outcome") or {}).get("sla_met") is not None]

    line = "".join("E" if d["step"] in esc else "." for d in ds)
    streak = best = exits = 0
    for i, ch in enumerate(line):
        streak = streak + 1 if ch == "E" else 0
        best = max(best, streak)
        exits += ch == "." and i > 0 and line[i - 1] == "E"
    viol = sum(1 for d in scored if d["outcome"]["sla_met"] is False)
    print(f"\n== {folder.name}  ({len(ds)}스텝 · 채점 {len(scored)} · SLA 위반 {viol})")
    print(f"   개입 {line.count('E')} · 최장 연속 {best} · 탈출 {exits} · {line}")
    for name, subset in (("전체", scored), ("자율만", [d for d in scored if d["step"] not in esc])):
        parts = []
        for key, sign in SIGNALS:
            pairs = [(sign * signal(d, key), d["outcome"]["sla_met"] is False)
                     for d in subset if signal(d, key) is not None]
            parts.append(f"{key} {auc([v for v, p in pairs if p], [v for v, p in pairs if not p])}")
        n_pos = sum(1 for d in subset if d["outcome"]["sla_met"] is False)
        print(f"   AUC [{name} · 위반 {n_pos}/{len(subset)}]  " + " · ".join(parts))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("runs", nargs="+", help="run_id 또는 실행 폴더")
    p.add_argument("--max-step", type=int, default=None, help="이 스텝 미만만 (긴 실행의 앞부분과 비교할 때)")
    args = p.parse_args()
    for r in args.runs:
        report(r, args.max_step)
    return 0


if __name__ == "__main__":
    sys.exit(main())
