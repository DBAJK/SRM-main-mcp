"""emergency 10스텝 — 기존 프로젝트(original) vs 우리 오케스트레이터(재난 시 조달 0.8). 스텝별 나란히 비교.

    py -3.10 results/emergency-10step-p08/plot_emergency.py [seed]     (기본 seed 0)

results/onset-10step-s0/plot_final.py 를 emergency(처음부터 재난)용으로 옮긴 것. 실행 기록:
runs/original-emergency-s{seed} (--steps 10) · runs/proposed_p08-emergency-s{seed} (오케스트레이터, prompt.md 기본 = 재난 시 0.8).

산출: original_s{seed}.png · orchestrator_s{seed}.png · final_s{seed}.png

관측은 서버가 실제로 돌려준 값만 쓴다 — 오케스트레이터는 calls.jsonl(get_observation · step 반환),
original 은 결정 레코드(파이썬 루프가 그대로 중계) + 마지막 obs_10 은 트래픽 ÷ (적용 배분 × 기본 용량) 복원.
SLA 위반 = 그 시점 어느 슬라이스라도 이용률 > 임계 (⑤ 채점과 같은 판정, 장부와 일치하는지 검사한다).
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

HERE = Path(__file__).resolve().parent
RUNS = HERE.parents[1] / "runs"
SEED = int(sys.argv[1]) if len(sys.argv) > 1 else 0
K = ("embb", "urllc", "mmtc")
T = list(range(0, 11))
CAP = 1.6
PROCURE_EMERGENCY, LIMIT = 0.8, 1.0
GREY, RED, BLUE, GREEN, ORANGE = "#5d6d7e", "#c0392b", "#2471a3", "#1e8449", "#d68910"


def load_orch(run):
    obs, procs = {}, []
    for line in open(RUNS / run / "orchestrator" / "calls.jsonl", encoding="utf-8"):
        c = json.loads(line)
        if not c.get("ok"):
            continue
        if c["tool"] == "get_observation":
            obs.setdefault(c["result"]["step"], c["result"])
        elif c["tool"] == "step":
            o = c["result"]["observation"]
            obs[o["step"]] = o
        elif c["tool"] == "procure" and c["result"].get("status") == "active":
            procs.append({"step": c["args"]["current_step"], "vendor": c["result"]["vendor_id"],
                          "slice": c["args"]["slice_type"], "cost": c["result"]["cost_total"]})
    return obs, procs


def load_orig(run, ref_obs):
    book = json.load(open(RUNS / run / "decisions.json", encoding="utf-8"))
    dec = {r["step"]: r for r in book["decisions"] if r["kind"] == "decision"}
    obs = {t: dec[t]["observation"] for t in range(10)}
    for t in range(10):     # 같은 시드 → 같은 트래픽이어야 비교가 성립한다
        assert all(abs(obs[t]["traffic"][k] - ref_obs[t]["traffic"][k]) < 1e-9 for k in K), t
    last, o10 = dec[9]["outcome"]["applied_allocation"], ref_obs[10]
    obs[10] = {"traffic": o10["traffic"], "thresholds": o10["thresholds"], "capacity": {k: CAP for k in K},
               "utilization": {k: o10["traffic"][k] / (last[k] * CAP) for k in K},
               "demand_pressure": sum(o10["traffic"][k] / (o10["thresholds"][k] * CAP) for k in K)}
    scored = [any(dec[t]["outcome"]["observed_violations"].values()) for t in range(10)]
    return obs, scored


def series(obs):
    w = [max(obs[t]["utilization"][k] / obs[t]["thresholds"][k] for k in K) for t in T]
    return {"p": [obs[t]["demand_pressure"] for t in T], "w": w,
            "cap": [sum(obs[t]["capacity"].values()) for t in T],
            "viol": [False] + [x > 1 for x in w[1:]]}       # t=0 은 결정 전 초기 상태라 채점하지 않는다


orch_obs, procs = load_orch(f"proposed_p08-emergency-s{SEED}")
orig_obs, orig_scored = load_orig(f"original-emergency-s{SEED}", orch_obs)
truth = [json.loads(l) for l in open(RUNS / f"proposed_p08-emergency-s{SEED}" / "truth.jsonl", encoding="utf-8")]
ONSET = next(r["step"] for r in truth if r["is_emergency"])   # emergency 는 0
orch_all = json.load(open(RUNS / f"proposed_p08-emergency-s{SEED}" / "decisions.json", encoding="utf-8"))["decisions"]
ESC = sum(1 for r in orch_all if r["kind"] == "escalation")
orch_dec = {r["step"]: r for r in json.load(open(RUNS / f"proposed_p08-emergency-s{SEED}" / "decisions.json",
                                                  encoding="utf-8"))["decisions"] if r["kind"] == "decision"}
DETECT = next((t for t in range(ONSET, 10) if orch_dec[t]["situation"] == "emergency"), None)

S_ORIG, S_ORCH = series(orig_obs), series(orch_obs)
assert S_ORIG["viol"][1:] == orig_scored, "복원한 위반이 장부의 채점과 다르다"
P_MAX = max(max(S_ORIG["p"]), max(S_ORCH["p"])) + 0.12
W_MAX = max(max(S_ORIG["w"]), max(S_ORCH["w"])) + 0.25
CAP_LO, CAP_HI = 3 * CAP - 0.15, 3 * CAP + 1.35
LABELS = [f"{t}\n{t * 15 // 60:02d}:{t * 15 % 60:02d}" for t in T]


def background(ax):
    ax.axvspan(-0.5, ONSET - 0.5, color="#eaf2f8", zorder=0)
    ax.axvspan(ONSET - 0.5, 10.5, color="#fdedec", zorder=0)
    ax.set_xlim(-0.5, 10.6)
    ax.grid(alpha=0.3)


def draw(axes, s, title, color, procurement):
    a1, a2, a3 = axes
    for ax in axes:
        background(ax)
    a1.text((ONSET + 10) / 2, 1.0, "재난 상황 (처음부터 emergency)",
            transform=a1.get_xaxis_transform(), ha="center", va="bottom", color=RED, fontweight="bold")

    # ① 수요 압력 + 조달 구간
    a1.axhspan(PROCURE_EMERGENCY, LIMIT, xmin=(ONSET - 0.5 + 0.5) / 11.1, color=ORANGE, alpha=0.22, zorder=1)
    a1.axhspan(LIMIT, 5, color="#e74c3c", alpha=0.10, zorder=1)
    a1.axhline(PROCURE_EMERGENCY, xmin=(ONSET + 0) / 11.1, color=ORANGE, ls="--", lw=1.2)
    a1.axhline(LIMIT, color="k", ls="--", lw=1)
    a1.text(-0.4, LIMIT + 0.01, "1.0 한계 — 넘으면 어떤 배분으로도 SLA 불가", fontsize=8, ha="left", va="bottom")
    a1.text(10.5, PROCURE_EMERGENCY + 0.01,
            "0.8 재난 시 조달 구간 (업계 기준: 부하 < 용량 80%)" if procurement else
            "0.8 조달 구간 — 기존 프로젝트는 조달 기능이 없어 대응 못 함",
            fontsize=8, ha="right", va="bottom", color="#9c640c")
    a1.plot(T, s["p"], "-o", color=color, lw=2.2, zorder=3)
    a1.set_ylim(0.45, P_MAX)
    a1.set_ylabel("수요 압력")
    a1.set_title("① 수요 압력 — 0.8 을 넘으면 조달 구간, 1.0 을 넘으면 한계", loc="left", fontsize=10.5, pad=20)

    # ② 매 스텝 SLA 상태
    a2.axhline(1.0, color="k", ls="--", lw=1)
    a2.axhspan(1.0, 10, color="#e74c3c", alpha=0.12, zorder=1)
    a2.text(10.5, 1.02, "SLA 위반 구간", fontsize=8, ha="right", va="bottom")
    a2.plot(T, s["w"], "-", color=color, lw=2, zorder=3)
    for t in T[1:]:
        ok = not s["viol"][t]
        a2.plot(t, s["w"][t], "o" if ok else "X", ms=9 if ok else 13, color=GREEN if ok else RED, zorder=4,
                mec="white", mew=0.8)
    a2.plot(0, s["w"][0], "o", ms=7, color="#aab7b8", zorder=4)
    n = sum(s["viol"])
    a2.text(0.01, 0.95, f"SLA 위반 {n}회 / 10", transform=a2.transAxes, fontsize=13, fontweight="bold",
            color=RED, va="top")
    a2.set_ylim(0.5, W_MAX)
    a2.set_ylabel("가장 위험한 슬라이스 부하\n(이용률 ÷ 임계)")
    a2.set_title("② 스텝별 SLA — 초록 ● 지킴 · 빨강 × 위반", loc="left", fontsize=10.5)

    # ③ 용량 + 벤더 조달
    a3.step(T, s["cap"], where="post", color=color, lw=2.5)
    if procurement:
        for i, p in enumerate(procs):
            for ax in axes:
                ax.axvline(p["step"] + 0.5, color=GREEN, ls=":", lw=1.3, alpha=0.8)
            a3.annotate(f"벤더 조달\n{p['vendor']}\n{p['slice']} +용량\n${p['cost']:,.0f}",
                        xy=(p["step"] + 0.5, 3 * CAP + 0.02), xytext=(p["step"] + 0.5, 3 * CAP + 0.62 + 0.0 * i),
                        ha="center", fontsize=7.5, color=GREEN, fontweight="bold",
                        arrowprops=dict(arrowstyle="->", color=GREEN))
            a1.annotate("조달", xy=(p["step"], s["p"][p["step"]]), xytext=(0, 12), textcoords="offset points",
                        ha="center", fontsize=8, color=GREEN, fontweight="bold")
        total = sum(p["cost"] for p in procs)
        a3.set_title(f"③ 용량 — 벤더 직접 조달 {len(procs)}회 · 가상 비용 ${total:,.0f}", loc="left", fontsize=10.5)
    else:
        a3.text(5, 3 * CAP + 0.55, "조달 기능 없음 — 용량 고정", ha="center", fontsize=12, color=GREY,
                fontweight="bold")
        a3.set_title("③ 용량 — 고정", loc="left", fontsize=10.5)
    a3.set_ylim(CAP_LO, CAP_HI)
    a3.set_ylabel("총 용량")
    a3.set_xticks(T, LABELS)
    a3.set_xlabel("스텝 (1스텝 = 15분)")
    return n


def figure(title, s, color, procurement, out, sub):
    fig, axes = plt.subplots(3, 1, figsize=(10, 11.5), sharex=True, gridspec_kw={"height_ratios": [1.1, 1.0, 0.75]})
    n = draw(axes, s, title, color, procurement)
    fig.suptitle(f"{title}\n{sub.format(n=n)}", fontsize=13, fontweight="bold")
    fig.tight_layout()
    fig.savefig(HERE / out, dpi=150)
    plt.close(fig)
    return n


n_orig = figure("기존 프로젝트 (원본 규칙)", S_ORIG, GREY, False, f"original_s{SEED}.png",
                "사람이 재난을 선언 · 조달 기능 없음 → SLA 위반 {n}회")
n_orch = figure("우리 프로젝트 (Claude 오케스트레이터)", S_ORCH, RED, True, f"orchestrator_s{SEED}.png",
                "재난을 스스로 인식 · 0.8 부터 벤더 직접 조달 → SLA 위반 {n}회")

fig, axes = plt.subplots(3, 2, figsize=(19, 11.5), sharex=True, gridspec_kw={"height_ratios": [1.1, 1.0, 0.75]})
draw(axes[:, 0], S_ORIG, "", GREY, False)
draw(axes[:, 1], S_ORCH, "", RED, True)
axes[0, 0].set_title("기존 프로젝트 (원본 규칙) — 조달 기능 없음\n① 수요 압력", loc="left", fontsize=12,
                     fontweight="bold", pad=20)
axes[0, 1].set_title("우리 프로젝트 (Claude 오케스트레이터) — 재난 시 0.8 부터 조달\n① 수요 압력", loc="left",
                     fontsize=12, fontweight="bold", pad=20)
detect = f"Claude 가 재난 인식 {DETECT * 15 // 60:02d}:{DETECT * 15 % 60:02d}" if DETECT is not None else ""
fig.suptitle(f"emergency · 10스텝 (seed {SEED}, 같은 트래픽) — SLA 위반 {n_orig}회 → {n_orch}회 · "
             f"벤더 조달 {len(procs)}회 · {detect} · 사람 호출 {ESC}회", fontsize=14, fontweight="bold")
fig.tight_layout()
fig.savefig(HERE / f"final_s{SEED}.png", dpi=130)
print(f"seed {SEED} | 위반 {n_orig} → {n_orch} | 조달 {[(p['step'], p['vendor'], p['cost']) for p in procs]} | 인식 {DETECT} | 호출 {ESC}")
