"""original vs 오케스트레이터 — "왜 오케스트레이터인가"를 한 장으로.

    py -3.14 results/emergency-10step-s0/plot_story.py

x 축은 "채점된 시점" = 결정 t 의 결과가 드러나는 관측 obs_{t+1} (1~10, 00:15~02:30).
SLA 위반 = obs_{t+1} 에서 어느 한 슬라이스라도 이용률 > 임계 (⑤ report_outcome 과 같은 판정).
최악 부하율 = max_k utilization_k / threshold_k — 1 을 넘으면 그 시점 위반.

관측은 서버가 실제로 돌려준 값만 쓴다. 오케스트레이터는 calls.jsonl 의 step 반환값,
original 은 결정 레코드의 관측(파이썬 루프가 그대로 중계) + 마지막 obs_10 은
트래픽(시드로 결정, 행동과 무관 — 아래에서 두 실행의 트래픽이 같은지 검사) ÷ (적용 배분 × 용량)으로 복원.
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

RUNS = Path(__file__).resolve().parents[2] / "runs"
OUT = Path(__file__).resolve().parent / "story.png"
K = ("embb", "urllc", "mmtc")
GREY, RED, GREEN = "#7f8c8d", "#c0392b", "#1e8449"


def decisions(run):
    book = json.load(open(RUNS / run / "decisions.json", encoding="utf-8"))
    return sorted([r for r in book["decisions"] if r["kind"] == "decision"], key=lambda r: r["step"])


def orch_series(run):
    nxt, procs = {}, []
    for line in open(RUNS / run / "orchestrator" / "calls.jsonl", encoding="utf-8"):
        c = json.loads(line)
        if not c.get("ok"):
            continue
        if c["tool"] == "step":
            o = c["result"]["observation"]
            nxt[o["step"]] = o
        elif c["tool"] == "procure" and c["result"].get("status") == "active":
            procs.append((c["args"]["current_step"], c["result"]["vendor_id"], c["result"]["cost_total"]))
    return nxt, procs


def worst(o):
    return max(o["utilization"][k] / o["thresholds"][k] for k in K)


orch_next, procs = orch_series("proposed-emergency-s0")
orig = decisions("original-emergency-s0")
orig_obs = {r["step"]: r["observation"] for r in orig}
# obs_10 복원: 트래픽은 시드로만 정해진다 — 두 실행 트래픽이 같은지 먼저 확인
for t in range(1, 10):
    assert all(abs(orig_obs[t]["traffic"][k] - orch_next[t]["traffic"][k]) < 1e-9 for k in K), t
last = orig[-1]["outcome"]["applied_allocation"]
o10 = orch_next[10]
orig_obs[10] = {"utilization": {k: o10["traffic"][k] / (last[k] * 1.6) for k in K},
                "thresholds": o10["thresholds"], "capacity": {k: 1.6 for k in K}}

steps = list(range(1, 11))
labels = [f"{(t * 15) // 60:02d}:{(t * 15) % 60:02d}" for t in steps]
series = {
    "original (기존 규칙)": {"w": [worst(orig_obs[t]) for t in steps],
                            "cap": [sum(orig_obs[t]["capacity"].values()) for t in steps], "c": GREY},
    "오케스트레이터 (Claude)": {"w": [worst(orch_next[t]) for t in steps],
                              "cap": [sum(orch_next[t]["capacity"].values()) for t in steps], "c": RED},
}
# 장부의 채점 결과와 일치하는지
assert [w > 1 for w in series["original (기존 규칙)"]["w"]] == \
       [any(r["outcome"]["observed_violations"].values()) for r in orig]

fig, axes = plt.subplots(3, 1, figsize=(11, 11), sharex=True,
                         gridspec_kw={"height_ratios": [1.1, 1.2, 0.8]})

# ① 누적 SLA 위반
ax = axes[0]
for name, s in series.items():
    cum, n = [], 0
    for w in s["w"]:
        n += w > 1
        cum.append(n)
    s["cum"] = cum
    ax.step(steps, cum, where="mid", color=s["c"], lw=3, label=f"{name} — 위반 {cum[-1]}회")
    ax.annotate(f"{cum[-1]}회", (steps[-1], cum[-1]), xytext=(8, -4), textcoords="offset points",
                color=s["c"], fontsize=13, fontweight="bold")
gap = series["original (기존 규칙)"]["cum"][-1] - series["오케스트레이터 (Claude)"]["cum"][-1]
ax.fill_between(steps, series["오케스트레이터 (Claude)"]["cum"], series["original (기존 규칙)"]["cum"],
                step="mid", color=GREEN, alpha=0.12)
ax.text(5.5, 6.2, f"막아낸 SLA 위반 {gap}회", color=GREEN, fontsize=12, fontweight="bold", ha="center")
ax.set_ylabel("누적 SLA 위반 (회)")
ax.set_ylim(0, 10.5)
ax.legend(loc="upper left", fontsize=10)
ax.set_title("① 누적 SLA 위반 — 같은 트래픽, 같은 시작", loc="left", fontsize=11)

# ② 최악 슬라이스 부하율
ax = axes[1]
ax.axhspan(1.0, 2.0, color="#f5b7b1", alpha=0.35)
ax.axhline(1.0, color="k", ls="--", lw=1)
ax.text(10.45, 1.02, "SLA 위반 구간", fontsize=9, ha="right", va="bottom")
for name, s in series.items():
    ax.plot(steps, s["w"], "-o", color=s["c"], lw=2, label=name)
    for t, w in zip(steps, s["w"]):
        if w > 1:
            ax.plot(t, w, "x", color=s["c"], ms=11, mew=2.5)
ax.set_ylim(0.6, max(max(s["w"]) for s in series.values()) + 0.15)
ax.set_ylabel("최악 슬라이스 부하율\n(이용률 ÷ 임계)")
ax.legend(loc="upper left", fontsize=10)
ax.set_title("② 가장 위험한 슬라이스의 부하 — 1 을 넘으면 위반 (×)", loc="left", fontsize=11)

# ③ 용량 · 벤더 조달
ax = axes[2]
for name, s in series.items():
    ax.step(steps, s["cap"], where="post", color=s["c"], lw=2.5, label=name)
for step_no, vendor, cost in procs:
    ax.annotate(f"벤더 직접 조달\n{vendor} · ${cost:,.0f}", xy=(step_no + 0.5, 4.8), xytext=(step_no + 0.5, 5.2),
                ha="center", fontsize=8.5, color=RED,
                arrowprops=dict(arrowstyle="->", color=RED))
    for a in axes:
        a.axvline(step_no + 0.5, color=RED, ls=":", alpha=0.5)
ax.set_ylim(4.7, 5.75)
ax.set_ylabel("총 용량")
ax.legend(loc="upper center", fontsize=10)
ax.set_title("③ 용량 — 기존 규칙은 고정, 오케스트레이터는 필요할 때 벤더에서 직접 확보", loc="left", fontsize=11)
ax.set_xticks(steps, [f"{t}\n{l}" for t, l in zip(steps, labels)])
ax.set_xlabel("채점 시점 (1스텝 = 15분)")
for a in axes:
    a.grid(alpha=0.3)
    a.set_xlim(0.5, 10.7)

fig.suptitle("emergency 10스텝 (seed 0) — 오케스트레이터는 SLA 위반을 9회 → 4회로 줄였다\n"
             "사람 개입 0회 · 상황 인식 10/10 · 벤더 조달 3회 · Claude 비용 $0.86",
             fontsize=13, fontweight="bold")
fig.tight_layout()
fig.savefig(OUT, dpi=150)
for name, s in series.items():
    print(name, "위반", s["cum"][-1], [round(w, 2) for w in s["w"]])
print("조달", procs, "\nsaved", OUT)
