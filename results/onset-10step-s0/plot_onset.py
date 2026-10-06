"""onset (평상시 1시간 → 재난 발생) · 10스텝 · seed 0 — original vs 오케스트레이터.

    py -3.14 results/onset-10step-s0/plot_onset.py

x 축은 관측 시점 t (0~10, 00:00~02:30). 재난 트래픽은 t=4(01:00)부터 들어온다(truth.jsonl).
위반은 결정 t 의 결과가 드러나는 obs_{t+1} 기준(⑤ 채점과 같음)이라 1~10 에만 찍힌다.
오케스트레이터 관측은 calls.jsonl 의 서버 반환값, original 은 결정 레코드 + obs_10 복원.
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

HERE = Path(__file__).resolve().parent
RUNS = HERE.parents[1] / "runs"
ORIG, ORCH = "original-onset-s0", "proposed-onset-s0"
K = ("embb", "urllc", "mmtc")
GREY, RED, GREEN = "#7f8c8d", "#c0392b", "#1e8449"
CAP = 1.6


def worst(util, thr):
    return max(util[k] / thr[k] for k in K)


truth = [json.loads(l) for l in open(RUNS / ORCH / "truth.jsonl", encoding="utf-8")]
onset = next(r["step"] for r in truth if r["is_emergency"])

obs, procs = {}, []
for line in open(RUNS / ORCH / "orchestrator" / "calls.jsonl", encoding="utf-8"):
    c = json.loads(line)
    if not c.get("ok"):
        continue
    if c["tool"] == "get_observation":
        obs.setdefault(c["result"]["step"], c["result"])
    elif c["tool"] == "step":
        o = c["result"]["observation"]
        obs[o["step"]] = o
    elif c["tool"] == "procure" and c["result"].get("status") == "active":
        procs.append((c["args"]["current_step"], c["result"]["vendor_id"], c["result"]["cost_total"]))
orch_dec = {r["step"]: r for r in json.load(open(RUNS / ORCH / "decisions.json", encoding="utf-8"))["decisions"]
            if r["kind"] == "decision"}
orig_dec = {r["step"]: r for r in json.load(open(RUNS / ORIG / "decisions.json", encoding="utf-8"))["decisions"]
            if r["kind"] == "decision"}

T = list(range(0, 11))
for t in range(0, 10):
    assert all(abs(orig_dec[t]["observation"]["traffic"][k] - obs[t]["traffic"][k]) < 1e-9 for k in K), t
o_obs = {t: orig_dec[t]["observation"] for t in range(10)}
last = orig_dec[9]["outcome"]["applied_allocation"]
o_obs[10] = {"utilization": {k: obs[10]["traffic"][k] / (last[k] * CAP) for k in K},
             "thresholds": obs[10]["thresholds"], "capacity": {k: CAP for k in K},
             "demand_pressure": sum(obs[10]["traffic"][k] / (obs[10]["thresholds"][k] * CAP) for k in K)}

S = {
    "original (기존 규칙)": {"c": GREY, "o": o_obs},
    "오케스트레이터 (Claude)": {"c": RED, "o": obs},
}
for s in S.values():
    s["w"] = [worst(s["o"][t]["utilization"], s["o"][t]["thresholds"]) for t in T]
    s["p"] = [s["o"][t]["demand_pressure"] for t in T]
    s["cap"] = [sum(s["o"][t]["capacity"].values()) for t in T]
    s["viol"] = [None] + [w > 1 for w in s["w"][1:]]
assert S["original (기존 규칙)"]["viol"][1:] == [any(orig_dec[t]["outcome"]["observed_violations"].values())
                                             for t in range(10)]
detected = next((t for t in range(10) if orch_dec[t]["situation"] == "emergency"), None)

fig, axes = plt.subplots(4, 1, figsize=(11, 14), sharex=True,
                         gridspec_kw={"height_ratios": [1.0, 1.0, 1.1, 0.8]})
for ax in axes:
    ax.axvspan(-0.5, onset - 0.5, color="#eaf2f8", zorder=0)
    ax.axvspan(onset - 0.5, 10.5, color="#fdedec", zorder=0)
    ax.grid(alpha=0.3)
    ax.set_xlim(-0.5, 10.6)
axes[0].text((onset - 1) / 2, 1.0, "평상시", transform=axes[0].get_xaxis_transform(), ha="center", va="bottom",
             fontsize=11, color="#2471a3", fontweight="bold")
axes[0].text((onset + 10) / 2, 1.0, f"재난 발생 ({onset}스텝 · {onset * 15 // 60:02d}:{onset * 15 % 60:02d})",
             transform=axes[0].get_xaxis_transform(), ha="center", va="bottom", fontsize=11, color=RED,
             fontweight="bold")

# ① 수요 압력 — 조달 기준
ax = axes[0]
ax.axhline(1.0, color="k", ls="--", lw=1)
ax.text(10.5, 1.01, "한계 1.0 (넘으면 어떤 배분으로도 SLA 불가 → 조달 기준)", fontsize=8.5, ha="right", va="bottom")
for name, s in S.items():
    ax.plot(T, s["p"], "-o", color=s["c"], lw=2, label=name)
ax.set_ylabel("수요 압력")
ax.legend(loc="upper left", fontsize=9)
ax.set_title("① 수요 압력 — 재난 뒤 서서히 오르다 한계를 넘는다", loc="left", fontsize=11, pad=22)

# ② 누적 위반
ax = axes[1]
for name, s in S.items():
    cum, n = [], 0
    for v in s["viol"][1:]:
        n += v
        cum.append(n)
    s["cum"] = cum
    ax.step(T[1:], cum, where="mid", color=s["c"], lw=3, label=f"{name} — 위반 {cum[-1]}회")
    ax.annotate(f"{cum[-1]}회", (10, cum[-1]), xytext=(6, -4), textcoords="offset points", color=s["c"],
                fontsize=12, fontweight="bold")
ax.fill_between(T[1:], S["오케스트레이터 (Claude)"]["cum"], S["original (기존 규칙)"]["cum"], step="mid",
                color=GREEN, alpha=0.12)
ax.set_ylim(0, 10.5)
ax.set_ylabel("누적 SLA 위반 (회)")
ax.legend(loc="upper left", fontsize=9)
ax.set_title("② 누적 SLA 위반", loc="left", fontsize=11)

# ③ 최악 부하율
ax = axes[2]
ax.axhline(1.0, color="k", ls="--", lw=1)
for name, s in S.items():
    ax.plot(T, s["w"], "-o", color=s["c"], lw=2, label=name)
    for t, w, v in zip(T, s["w"], s["viol"]):
        if v:
            ax.plot(t, w, "x", color=s["c"], ms=11, mew=2.5)
if detected is not None:
    ax.annotate(f"오케스트레이터가 재난 인식\n({detected}스텝, 정답 라벨 없이)", xy=(detected, 1.0),
                xytext=(detected + 0.9, 1.72), fontsize=9, color=RED,
                arrowprops=dict(arrowstyle="->", color=RED))
ax.set_ylabel("최악 슬라이스 부하율\n(이용률 ÷ 임계, 1 초과 = 위반 ×)")
ax.legend(loc="lower left", fontsize=9)
ax.set_title("③ 가장 위험한 슬라이스의 부하", loc="left", fontsize=11)

# ④ 용량 · 조달
ax = axes[3]
for name, s in S.items():
    ax.step(T, s["cap"], where="post", color=s["c"], lw=2.5, label=name)
for step_no, vendor, cost in procs:
    ax.annotate(f"벤더 직접 조달\n{vendor} · ${cost:,.0f}", xy=(step_no + 0.5, 3 * CAP),
                xytext=(step_no + 0.5, 3 * CAP + 0.55), ha="center", fontsize=8.5, color=RED,
                arrowprops=dict(arrowstyle="->", color=RED))
    for a in axes:
        a.axvline(step_no + 0.5, color=RED, ls=":", alpha=0.5)
ax.set_ylim(3 * CAP - 0.1, 3 * CAP + 0.95)
ax.set_ylabel("총 용량")
ax.set_title(f"④ 용량 — 기존 규칙은 고정, 오케스트레이터는 벤더 조달 {len(procs)}회", loc="left", fontsize=11)
ax.set_xticks(T, [f"{t}\n{t * 15 // 60:02d}:{t * 15 % 60:02d}" for t in T])
ax.set_xlabel("스텝 (1스텝 = 15분)")

o_cum, p_cum = S["original (기존 규칙)"]["cum"][-1], S["오케스트레이터 (Claude)"]["cum"][-1]
fig.suptitle(f"평상시 → 재난 발생 · 10스텝 (seed 0, 용량 1.6) — SLA 위반 {o_cum}회 → {p_cum}회",
             fontsize=13, fontweight="bold")
fig.tight_layout()
fig.savefig(HERE / "onset.png", dpi=150)
print("onset", onset, "| 인식", detected, "| 위반", o_cum, "→", p_cum, "| 조달", procs)
for t in T:
    print(t, " ".join(f"{n[:4]} p={s['p'][t]:.2f} w={s['w'][t]:.2f}{'X' if s['viol'][t] else ''}" for n, s in S.items()),
          orch_dec.get(t, {}).get("situation", ""))
