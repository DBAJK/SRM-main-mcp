"""용량 1.6 vs 1.0 — original vs 오케스트레이터를 나란히 (emergency · 10스텝 · seed 0).

    py -3.14 results/emergency-10step-s0/plot_side_by_side.py

plot_story.py 와 같은 규칙으로 그린다:
- x 축은 채점 시점 obs_{t+1} (1~10). 위반 = 그 시점에 어느 슬라이스라도 이용률 > 임계.
- 오케스트레이터 관측은 calls.jsonl 의 step 반환값(서버가 실제로 돌려준 값).
- original 관측은 결정 레코드 + 마지막 obs_10 은 트래픽 ÷ (적용 배분 × 기본 용량)으로 복원.
  트래픽이 두 실행에서 같은지, 복원한 위반이 장부의 채점과 같은지 검사한다.
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

RUNS = Path(__file__).resolve().parents[2] / "runs"
OUT = Path(__file__).resolve().parent / "side_by_side.png"
K = ("embb", "urllc", "mmtc")
GREY, RED, GREEN = "#7f8c8d", "#c0392b", "#1e8449"
CASES = [
    (1.6, "original-emergency-s0", "proposed-emergency-s0", "용량 1.6 (우리 환경 기본값)"),
    (1.0, "original_cap10-emergency-s0", "proposed_cap10-emergency-s0", "용량 1.0 (원본과 같은 조건)"),
]
STEPS = list(range(1, 11))


def worst(util, thr):
    return max(util[k] / thr[k] for k in K)


def load(cap, orig_run, orch_run):
    nxt, procs, cost = {}, [], 0.0
    for line in open(RUNS / orch_run / "orchestrator" / "calls.jsonl", encoding="utf-8"):
        c = json.loads(line)
        if not c.get("ok"):
            continue
        if c["tool"] == "step":
            o = c["result"]["observation"]
            nxt[o["step"]] = o
        elif c["tool"] == "procure" and c["result"].get("status") == "active":
            procs.append((c["args"]["current_step"], c["result"]["vendor_id"], c["result"]["cost_total"]))
            cost += c["result"]["cost_total"]

    book = json.load(open(RUNS / orig_run / "decisions.json", encoding="utf-8"))
    recs = {r["step"]: r for r in book["decisions"] if r["kind"] == "decision"}
    for t in range(1, 10):
        assert all(abs(recs[t]["observation"]["traffic"][k] - nxt[t]["traffic"][k]) < 1e-9 for k in K), t
    w_orig = [worst(recs[t]["observation"]["utilization"], recs[t]["observation"]["thresholds"]) for t in range(1, 10)]
    last = recs[9]["outcome"]["applied_allocation"]
    w_orig.append(worst({k: nxt[10]["traffic"][k] / (last[k] * cap) for k in K}, nxt[10]["thresholds"]))
    assert [w > 1 for w in w_orig] == [any(recs[t]["outcome"]["observed_violations"].values()) for t in range(10)]

    return {
        "orig": {"w": w_orig, "cap": [3 * cap] * 10},
        "orch": {"w": [worst(nxt[t]["utilization"], nxt[t]["thresholds"]) for t in STEPS],
                 "cap": [sum(nxt[t]["capacity"].values()) for t in STEPS]},
        "procs": procs, "cost": cost,
    }


fig, axes = plt.subplots(3, 2, figsize=(17, 12), sharex=True,
                         gridspec_kw={"height_ratios": [1.1, 1.2, 0.8]})
w_max = 0
for col, (cap, orig_run, orch_run, title) in enumerate(CASES):
    d = load(cap, orig_run, orch_run)
    w_max = max(w_max, max(d["orig"]["w"]), max(d["orch"]["w"]))
    names = {"orig": ("original (기존 규칙)", GREY), "orch": ("오케스트레이터 (Claude)", RED)}

    # ① 누적 위반
    ax = axes[0, col]
    for key, (name, c) in names.items():
        cum, n = [], 0
        for w in d[key]["w"]:
            n += w > 1
            cum.append(n)
        d[key]["cum"] = cum
        ax.step(STEPS, cum, where="mid", color=c, lw=3, label=f"{name} — 위반 {cum[-1]}회")
        ax.annotate(f"{cum[-1]}회", (10, cum[-1]), xytext=(8, -4), textcoords="offset points",
                    color=c, fontsize=13, fontweight="bold")
    ax.fill_between(STEPS, d["orch"]["cum"], d["orig"]["cum"], step="mid", color=GREEN, alpha=0.12)
    gap = d["orig"]["cum"][-1] - d["orch"]["cum"][-1]
    ax.text(6, 0.6, f"줄인 SLA 위반 {gap}회", color=GREEN, fontsize=12, fontweight="bold", ha="center")
    ax.set_ylim(0, 10.8)
    ax.legend(loc="upper left", fontsize=10)
    ax.set_title(f"{title}\n① 누적 SLA 위반", loc="left", fontsize=12, fontweight="bold")

    # ② 최악 부하율
    ax = axes[1, col]
    ax.axhspan(1.0, 10, color="#f5b7b1", alpha=0.35)
    ax.axhline(1.0, color="k", ls="--", lw=1)
    for key, (name, c) in names.items():
        w = d[key]["w"]
        excess = sum(max(0.0, x - 1) for x in w) / len(w)
        ax.plot(STEPS, w, "-o", color=c, lw=2, label=f"{name} — 평균 초과분 {excess:.2f}")
        for t, x in zip(STEPS, w):
            if x > 1:
                ax.plot(t, x, "x", color=c, ms=11, mew=2.5)
    ax.legend(loc="upper left", fontsize=10)
    ax.set_title("② 가장 위험한 슬라이스의 부하 (1 초과 = 위반 ×)", loc="left", fontsize=11)

    # ③ 용량 · 조달
    ax = axes[2, col]
    for key, (name, c) in names.items():
        ax.step(STEPS, d[key]["cap"], where="post", color=c, lw=2.5, label=name)
    base = 3 * cap
    for step_no, vendor, cost in d["procs"]:
        ax.annotate(f"{vendor}\n${cost:,.0f}", xy=(step_no + 0.5, base), xytext=(step_no + 0.5, base + 0.95),
                    ha="center", fontsize=8, color=RED, arrowprops=dict(arrowstyle="->", color=RED, lw=0.8))
        for a in axes[:, col]:
            a.axvline(step_no + 0.5, color=RED, ls=":", alpha=0.45)
    ax.set_ylim(base - 0.15, base + 1.45)
    ax.set_title(f"③ 총 용량 — 벤더 조달 {len(d['procs'])}회 · 가상 비용 ${d['cost']:,.0f}", loc="left", fontsize=11)
    ax.set_xticks(STEPS, [f"{t}\n{(t * 15) // 60:02d}:{(t * 15) % 60:02d}" for t in STEPS])
    ax.set_xlabel("채점 시점 (1스텝 = 15분)")
    print(title, "| 위반", d["orig"]["cum"][-1], "→", d["orch"]["cum"][-1], "| 조달", len(d["procs"]), d["cost"])

for col in range(2):
    axes[1, col].set_ylim(0.5, w_max + 0.25)     # 두 칸 같은 눈금 — 높이를 바로 비교할 수 있게
    for a in axes[:, col]:
        a.grid(alpha=0.3)
        a.set_xlim(0.2, 10.8)
axes[0, 0].set_ylabel("누적 SLA 위반 (회)")
axes[1, 0].set_ylabel("최악 슬라이스 부하율\n(이용률 ÷ 임계)")
axes[2, 0].set_ylabel("총 용량 (3 슬라이스 합)")

fig.suptitle("emergency 10스텝 (seed 0) — 용량 가정에 따른 original vs 오케스트레이터\n"
             "여유가 있으면(1.6) 위반 횟수를 줄이고, 여유가 전혀 없으면(1.0) 횟수는 비슷하지만 과부하 정도를 낮춘다",
             fontsize=14, fontweight="bold")
fig.tight_layout()
fig.savefig(OUT, dpi=140)
print("saved", OUT)
