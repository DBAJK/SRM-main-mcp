"""original vs orchestrator — emergency 10스텝 비교 그림.

결정 레코드(kind=decision)의 관측(obs_t)과 채점(outcome = obs_{t+1})만 읽는다. 새로 시뮬레이션하지 않는다.
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

ROOT = Path(r"C:\aiagent\SRM-main-mcp\runs")
RUNS = {"original (기존 규칙)": sys.argv[1], "오케스트레이터 (Claude)": sys.argv[2]}
OUT = Path(sys.argv[3])
COLORS = {"original (기존 규칙)": "#7f8c8d", "오케스트레이터 (Claude)": "#c0392b"}


def server_obs(run):
    """오케스트레이터 실행이면 LLM 이 옮겨 적은 관측 대신 서버가 실제로 돌려준 관측을 쓴다."""
    calls = ROOT / run / "orchestrator" / "calls.jsonl"
    if not calls.exists():
        return None, None
    obs, nxt = {}, {}
    for line in open(calls, encoding="utf-8"):
        c = json.loads(line)
        if not c.get("ok"):
            continue
        if c["tool"] == "get_observation":
            obs[c["result"]["step"]] = c["result"]
        elif c["tool"] == "step":
            o = c["result"]["observation"]
            nxt[o["step"] - 1] = o
    return obs, nxt


def load(run):
    book = json.load(open(ROOT / run / "decisions.json", encoding="utf-8"))
    recs = [r for r in book["decisions"] if r.get("kind") == "decision"]
    s_obs, s_next = server_obs(run)
    rows = []
    for r in sorted(recs, key=lambda r: r["step"]):
        o = s_obs[r["step"]] if s_obs else r["observation"]
        out = r.get("outcome") or {}
        if s_next and r["step"] in s_next:
            out = {**out, "observed_violations": s_next[r["step"]]["violations"]}
        rows.append({
            "step": r["step"],
            "clock": f"{o['sim_time']['hour_of_day']:02d}:{(r['step'] * 15) % 60:02d}",
            "pressure": o["demand_pressure"],
            "urllc_util": o["utilization"]["urllc"],
            "cap_urllc": o["capacity"]["urllc"],
            "cap_total": sum(o["capacity"].values()),
            "viol_next": any((out.get("observed_violations") or {}).values()) if out else None,
            "vendor": r.get("vendor_id"),
            "cost": r.get("cost_total"),
            "escalated": bool(r.get("escalated")),
        })
    return rows


data = {k: load(v) for k, v in RUNS.items()}
fig, axes = plt.subplots(3, 1, figsize=(11, 10), sharex=True)

for name, rows in data.items():
    x = [r["step"] for r in rows]
    c = COLORS[name]
    axes[0].plot(x, [r["pressure"] for r in rows], "-o", color=c, label=name)
    axes[1].plot(x, [r["urllc_util"] for r in rows], "-o", color=c, label=name)
    axes[2].step(x, [r["cap_total"] for r in rows], where="post", color=c, label=name, lw=2)
    for r in rows:
        if r["vendor"]:
            for ax in axes:
                ax.axvline(r["step"], color=c, ls=":", alpha=0.6)
            axes[2].annotate(f"벤더 조달\n{r['vendor']}\n${r['cost']}", (r["step"], r["cap_total"]),
                             textcoords="offset points", xytext=(6, 8), fontsize=8, color=c)

axes[0].axhline(1.0, color="k", ls="--", lw=1)
axes[0].text(0, 1.01, "압력 1.0 = 어떤 배분으로도 전 슬라이스 SLA 불가 (조달 기준)", fontsize=8)
axes[0].set_ylabel("수요 압력")
axes[1].axhline(1.2, color="k", ls="--", lw=1)
axes[1].text(0, 1.21, "URLLC 임계 1.2", fontsize=8)
axes[1].set_ylabel("URLLC 이용률")
axes[2].set_ylabel("총 용량 (3 슬라이스 합)")
axes[2].set_xlabel("스텝 (1스텝 = 15분, 00:00 시작)")
first = next(iter(data.values()))
axes[2].set_xticks([r["step"] for r in first], [f"{r['step']}\n{r['clock']}" for r in first])
for ax in axes:
    ax.grid(alpha=0.3)
    ax.legend(loc="upper left", fontsize=8)
fig.suptitle("emergency · 10스텝 · seed 0 — original vs 오케스트레이터", fontsize=13)
fig.tight_layout()
fig.savefig(OUT, dpi=150)

for name, rows in data.items():
    n_v = sum(1 for r in rows if r["viol_next"])
    procs = [(r["step"], r["vendor"], r["cost"]) for r in rows if r["vendor"]]
    print(f"{name}: SLA 위반 {n_v}/{len(rows)} · 개입 {sum(r['escalated'] for r in rows)} · 조달 {procs}")
    for r in rows:
        print(f"  s{r['step']} {r['clock']} p={r['pressure']:.2f} urllc={r['urllc_util']:.2f} "
              f"cap={r['cap_total']:.2f} 위반(다음)={r['viol_next']} {r['vendor'] or ''}")
print("saved", OUT)
