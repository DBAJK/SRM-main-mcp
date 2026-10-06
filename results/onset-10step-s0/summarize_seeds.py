"""onset · 10스텝 · seed 0~4 — original vs 오케스트레이터 요약표.

    py -3.14 results/onset-10step-s0/summarize_seeds.py

위반 = 결정 t 의 obs_{t+1} 에서 어느 슬라이스라도 이용률 > 임계 (④ 장부의 ⑤ 채점 결과).
과부하 초과분 = 채점 시점 최악 슬라이스 부하율(이용률 ÷ 임계)의 1 초과분 평균. 9 개 결정(t=0~8)의 obs_{t+1}
— 마지막 obs_10 은 original 기록에 관측이 없어 양쪽 모두 같은 기준(obs_1~9)으로 맞춘다.
"""
import json
import statistics as st
from pathlib import Path

RUNS = Path(__file__).resolve().parents[2] / "runs"
K = ("embb", "urllc", "mmtc")
SEEDS = range(5)


def decisions(run):
    book = json.load(open(RUNS / run / "decisions.json", encoding="utf-8"))
    return book["decisions"]


def summarize(run, orch):
    recs = decisions(run)
    dec = {r["step"]: r for r in recs if r["kind"] == "decision"}
    viol = sum(any(r["outcome"]["observed_violations"].values()) for r in dec.values() if r.get("outcome"))
    obs = {t: r["observation"] for t, r in dec.items()}
    if orch:   # LLM 이 옮겨 적은 관측 대신 서버 반환값
        for line in open(RUNS / run / "orchestrator" / "calls.jsonl", encoding="utf-8"):
            c = json.loads(line)
            if c.get("ok") and c["tool"] == "step":
                o = c["result"]["observation"]
                obs[o["step"]] = o
    excess = st.mean(max(0.0, max(obs[t]["utilization"][k] / obs[t]["thresholds"][k] for k in K) - 1)
                     for t in range(1, 10))
    procs = [r for r in dec.values() if r.get("vendor_id")]
    truth = [json.loads(l) for l in open(RUNS / run / "truth.jsonl", encoding="utf-8")]
    onset = next(r["step"] for r in truth if r["is_emergency"])
    detect = next((t for t in sorted(dec) if t >= onset and dec[t]["situation"] == "emergency"), None)
    false_alarm = sum(1 for t in sorted(dec) if t < onset and dec[t]["situation"] == "emergency")
    return {"viol": viol, "excess": excess, "procs": len(procs),
            "cost": sum(r.get("cost_total") or 0 for r in procs),
            "esc": sum(1 for r in recs if r["kind"] == "escalation"),
            "delay": None if detect is None else detect - onset, "false": false_alarm}


ARMS = [("original", "original (기존 규칙)", False),
        ("proposed", "오케스트레이터 · 조달 1.0", True),
        ("proposed_p08", "오케스트레이터 · 재난 시 조달 0.8", True)]


def ms(xs):
    return f"{st.mean(xs):.2f} ± {st.stdev(xs):.2f}" if len(xs) > 1 else f"{xs[0]:.2f}"


table = {}
for arm, label, orch in ARMS:
    rows = {}
    for s in SEEDS:
        try:
            rows[s] = summarize(f"{arm}-onset-s{s}", orch)
        except FileNotFoundError:
            pass
    table[arm] = rows

print("seed별 SLA 위반 (과부하 초과분) · 조달")
for s in SEEDS:
    cells = []
    for arm, _, orch in ARMS:
        r = table[arm].get(s)
        cells.append("—" if r is None else f"{r['viol']} ({r['excess']:.2f})" + (f" · 조달 {r['procs']}회 ${r['cost']:,.0f}" if orch else ""))
    print(f"  {s}: " + "  |  ".join(cells))

print()
print("평균")
for arm, label, orch in ARMS:
    rows = list(table[arm].values())
    if not rows:
        continue
    line = f"  {label:28s} 시드 {len(rows)} · 위반 {ms([r['viol'] for r in rows])} · 과부하 초과분 {ms([r['excess'] for r in rows])}"
    if orch:
        line += (f" · 조달 {ms([r['procs'] for r in rows])}회 · 비용 ${st.mean(r['cost'] for r in rows):,.0f}"
                 f" · 사람 호출 {ms([r['esc'] for r in rows])} · 인식 지연 {[r['delay'] for r in rows]}")
    print(line)
