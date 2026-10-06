"""그래프에 쓴 값을 CSV 로 — emergency 10스텝 · seed 0~4 · 기존 프로젝트(original) vs 제안 시스템(Claude CLI 오케스트레이터).

    python results/emergency-10step-p08/export_data.py      → data/per_step.csv · data/summary.csv

입력은 같은 폴더의 runs/ (실행 기록 원본 그대로). 값의 정의는 그림 스크립트와 같다.
- max_load: 그 스텝 판단의 결과(다음 15분 관측)에서 세 슬라이스의 이용률 ÷ 임계값 중 최댓값. 1 초과 = SLA 위반.
- demand_pressure: 판단 시점의 Σ 트래픽 ÷ (임계값 × 용량).
- 기존 프로젝트의 마지막 스텝 결과 관측은 장부에 없어, 같은 트래픽 ÷ (적용 배분 × 기본 용량 1.6)으로 복원한다.
"""
import csv
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
RUNS = HERE / "runs"
OUT = HERE / "data"
SEEDS, N, CAP = [0, 1, 2, 3, 4], 10, 1.6
K = ("embb", "urllc", "mmtc")


def worst(o):
    return max(o["utilization"][k] / o["thresholds"][k] for k in K)


def ours(seed):
    base = RUNS / f"proposed_p08-emergency-s{seed}"
    steps = {s["step"]: s for s in (json.loads(l) for l in open(base / "orchestrator" / "steps.jsonl", encoding="utf-8"))}
    calls = [json.loads(l) for l in open(base / "orchestrator" / "calls.jsonl", encoding="utf-8")]
    obs, rows = {}, []
    for t in range(N):
        cs = [c for c in calls if c["step"] == t and c["attempt"] == steps[t]["attempt"] and c.get("ok")]
        obs.setdefault(t, next(c["result"] for c in cs if c["tool"] == "get_observation"))
        nxt = next(c["result"]["observation"] for c in cs if c["tool"] == "step")
        obs[nxt["step"]] = nxt
        proc = next((c for c in cs if c["tool"] == "procure" and c["result"].get("status") == "active"), None)
        adds = [c for c in cs if c["tool"] == "add_capacity"]
        applied = [c for c in adds if c["result"].get("accepted")]
        rank = next((c["result"] for c in cs if c["tool"] == "score_offerings"), None)
        conf = next((c["result"] for c in cs if c["tool"] == "compute_confidence"), {})
        rows.append({
            "situation": steps[t]["answer"].get("situation"),
            "situation_confidence": conf.get("situation_confidence"),
            "asked_operator": int(any(c["tool"] == "record_escalation" for c in cs)),
            "procured": int(proc is not None),
            "vendor": proc["result"]["vendor_id"] if proc else "",
            "slice": proc["args"]["slice_type"] if proc else "",
            "lease_steps": proc["args"].get("duration_steps") if proc else "",
            "capacity_bought": proc["result"].get("capacity_gain") if proc else "",
            "capacity_applied": applied[-1]["args"].get("amount") if applied else ("" if not proc else 0),
            "cost": proc["result"].get("cost_total") if proc else 0,
            "top_vendor_score": rank[0]["score"] if rank else "",
            "tool_calls": len(cs),
            "claude_usd": round(steps[t].get("cost_usd") or 0, 4),
        })
    for t in range(N):
        rows[t]["demand_pressure"] = round(obs[t]["demand_pressure"], 4)
        rows[t]["max_load"] = round(worst(obs[t + 1]), 4)
    return rows, obs


def original(seed, ref_obs):
    book = json.load(open(RUNS / f"original-emergency-s{seed}" / "decisions.json", encoding="utf-8"))["decisions"]
    dec = {r["step"]: r for r in book if r["kind"] == "decision"}
    rows = []
    for t in range(N):
        if t + 1 < N:
            nxt = dec[t + 1]["observation"]
        else:
            a, o10 = dec[t]["outcome"]["applied_allocation"], ref_obs[N]
            nxt = {"utilization": {k: o10["traffic"][k] / (a[k] * CAP) for k in K}, "thresholds": o10["thresholds"]}
        load = worst(nxt)
        assert (load > 1) == any(dec[t]["outcome"]["observed_violations"].values()), (seed, t)
        rows.append({"situation": dec[t]["situation"], "situation_confidence": "", "asked_operator": 0,
                     "procured": 0, "vendor": "", "slice": "", "lease_steps": "", "capacity_bought": "",
                     "capacity_applied": "", "cost": 0, "top_vendor_score": "", "tool_calls": "", "claude_usd": "",
                     "demand_pressure": round(dec[t]["observation"]["demand_pressure"], 4), "max_load": round(load, 4)})
    return rows


COLS = ["seed", "system", "step", "time", "situation", "situation_confidence", "asked_operator", "demand_pressure",
        "procured", "vendor", "slice", "lease_steps", "capacity_bought", "capacity_applied", "cost",
        "top_vendor_score", "max_load", "sla_violation", "tool_calls", "claude_usd"]


def main():
    OUT.mkdir(exist_ok=True)
    per, summ = [], []
    for s in SEEDS:
        ou, obs = ours(s)
        og = original(s, obs)
        for name, rows in (("original", og), ("proposed", ou)):
            for t, r in enumerate(rows):
                per.append({"seed": s, "system": name, "step": t, "time": f"{t * 15 // 60}:{t * 15 % 60:02d}",
                            **r, "sla_violation": int(r["max_load"] > 1)})
            summ.append({"seed": s, "system": name,
                         "sla_violations": sum(int(r["max_load"] > 1) for r in rows),
                         "procurements": sum(r["procured"] for r in rows),
                         "cost": sum(r["cost"] or 0 for r in rows),
                         "operator_questions": sum(r["asked_operator"] for r in rows),
                         "claude_usd": round(sum(r["claude_usd"] or 0 for r in rows), 2) if name == "proposed" else ""})
    with open(OUT / "per_step.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(per)
    with open(OUT / "summary.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(summ[0]))
        w.writeheader()
        w.writerows(summ)
    for name in ("original", "proposed"):
        rs = [r for r in summ if r["system"] == name]
        print(f"{name:9} 위반 {[r['sla_violations'] for r in rs]} 평균 {sum(r['sla_violations'] for r in rs) / len(rs):.1f}"
              f" · 조달 {sum(r['procurements'] for r in rs)} · 질문 {sum(r['operator_questions'] for r in rs)}")
    print(f"→ {OUT / 'per_step.csv'} ({len(per)}행) · {OUT / 'summary.csv'} ({len(summ)}행)")


if __name__ == "__main__":
    main()
