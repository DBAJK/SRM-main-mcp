"""논문 그림 1 (흑백 · 한 칸 · 본문 폭 16cm) — 스텝별 SLA 결과와 벤더 조달 시점. 기존 프로젝트 vs 제안 시스템.

    py -3.10 results/paper/plot_figure1.py [seed]     → results/paper/fig1_s{seed}.png (600dpi) · .pdf

y = 스텝 t 판단의 결과: 다음 15분 관측에서 가장 위험한 슬라이스의 부하(이용률 ÷ 임계). 1 을 넘으면 SLA 위반.
▲ = 제안 시스템이 그 스텝에 벤더에서 용량을 조달(옆 = 고른 벤더 번호, △ = 용량 상한으로 반영되지 않음).
데이터 · 복원 방법은 plot_process_graph.py 와 같다 (emergency · 10스텝 · 같은 트래픽).
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["pdf.fonttype"] = 42

HERE = Path(__file__).resolve().parent
RUNS = HERE.parents[1] / "runs"
SEED = int(sys.argv[1]) if len(sys.argv) > 1 else 3
N, CAP = 10, 1.6
K = ("embb", "urllc", "mmtc")
BLACK, GRAY, LIGHT = "#000000", "#7a7a7a", "#dcdcdc"


def worst(o):
    return max(o["utilization"][k] / o["thresholds"][k] for k in K)


def load():
    base = RUNS / f"proposed_p08-emergency-s{SEED}"
    steps = {s["step"]: s for s in (json.loads(l) for l in open(base / "orchestrator" / "steps.jsonl", encoding="utf-8"))}
    calls = [json.loads(l) for l in open(base / "orchestrator" / "calls.jsonl", encoding="utf-8")]
    obs, ours = {}, []
    for t in range(N):
        cs = [c for c in calls if c["step"] == t and c["attempt"] == steps[t]["attempt"] and c.get("ok")]
        obs.setdefault(t, next(c["result"] for c in cs if c["tool"] == "get_observation"))
        nxt = next(c["result"]["observation"] for c in cs if c["tool"] == "step")
        obs[nxt["step"]] = nxt
        proc = next((c["result"] for c in cs if c["tool"] == "procure" and c["result"].get("status") == "active"), None)
        ours.append({"vendor": proc["vendor_id"].replace("vendor-", "v") if proc else None,
                     "applied": any(c["result"].get("accepted") for c in cs if c["tool"] == "add_capacity")})
    for t in range(N):
        ours[t]["load"] = worst(obs[t + 1])

    book = json.load(open(RUNS / f"original-emergency-s{SEED}" / "decisions.json", encoding="utf-8"))["decisions"]
    dec = {r["step"]: r for r in book if r["kind"] == "decision"}
    orig = []
    for t in range(N):
        if t + 1 < N:
            nxt = dec[t + 1]["observation"]
        else:   # 마지막 결과 관측 복원 — 같은 트래픽 ÷ (적용 배분 × 기본 용량)
            a, o10 = dec[t]["outcome"]["applied_allocation"], obs[N]
            nxt = {"utilization": {k: o10["traffic"][k] / (a[k] * CAP) for k in K}, "thresholds": o10["thresholds"]}
        load = worst(nxt)
        assert (load > 1) == any(dec[t]["outcome"]["observed_violations"].values()), f"step {t}: 장부와 다르다"
        orig.append({"load": load})
    return orig, ours


def main():
    orig, ours = load()
    x = list(range(N))
    vo = sum(d["load"] > 1 for d in orig)
    vu = sum(d["load"] > 1 for d in ours)
    fig, ax = plt.subplots(figsize=(6.3, 3.0))

    ax.axhline(1.0, color=BLACK, lw=0.9)
    ax.text(N - 0.42, 1.02, "SLA 임계값", ha="left", va="bottom", fontsize=7.6)
    ax.plot(x, [d["load"] for d in orig], ls="--", marker="s", ms=4.2, mfc="white", color=GRAY, lw=1.4,
            label=f"기존 프로젝트 (SLA 위반 {vo}회)")
    yu = [d["load"] for d in ours]
    ax.plot(x, yu, ls="-", color=BLACK, lw=1.7, zorder=2)
    # 조달한 스텝은 점 자체를 ▲ 로 — 그 스텝 판단(조달 포함)의 결과가 이 값이다. 옆에 고른 벤더.
    for t, d in enumerate(ours):
        if d["vendor"]:
            ax.scatter(t, yu[t], marker="^", s=58, zorder=4, linewidths=1.0,
                       **(dict(c=BLACK, edgecolors=BLACK) if d["applied"] else dict(facecolors="white", edgecolors=BLACK)))
            ax.annotate(d["vendor"], (t, yu[t]), xytext=(0, 7), textcoords="offset points", ha="center",
                        va="bottom", fontsize=7.2)
        else:
            ax.scatter(t, yu[t], marker="o", s=20, c=BLACK, zorder=4)
    # 범례: 선은 원 표식으로, 조달 표식은 따로 한 줄
    ax.plot([], [], ls="-", marker="o", ms=4.2, color=BLACK, lw=1.7, label=f"제안 시스템 (SLA 위반 {vu}회)")
    ax.scatter([], [], marker="^", s=40, c=BLACK, label="용량 조달 (v: 선택 벤더)")

    loads = [d["load"] for d in orig + ours]
    ymin, ymax = min(loads), max(loads)
    ax.set_xlim(-0.4, N + 0.75)
    ax.set_ylim(ymin - 0.1, ymax + 0.12)
    ax.set_xticks(x, [str(t) for t in x], fontsize=7.2)
    ax.set_xlabel("스텝 (15분 간격)", fontsize=8)
    ax.set_ylabel("최대 슬라이스 부하율", fontsize=8)
    ax.tick_params(labelsize=7.2)
    ax.grid(axis="y", color=LIGHT, lw=0.5)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.legend(loc="upper left", fontsize=7.6, frameon=False, handlelength=2.6)
    fig.subplots_adjust(left=0.1, right=0.985, top=0.97, bottom=0.16)
    for ext in ("png", "pdf"):
        fig.savefig(HERE / f"fig1_s{SEED}.{ext}", dpi=600)
    print(f"seed {SEED}: 위반 {vo} → {vu} · 조달 {[d['vendor'] for d in ours if d['vendor']]}")


if __name__ == "__main__":
    main()
