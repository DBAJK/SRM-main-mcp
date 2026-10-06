"""논문 본문용 그래프 (흑백 · 본문 폭 16cm) — 스텝별 판단 근거(수요 압력)와 판단 결과(다음 15분 SLA).

    py -3.10 results/paper/plot_process_graph.py [seed]     → results/paper/fig_graph_s{seed}.png (600dpi) · .pdf

x = 스텝 t 의 판단. 위 = 판단 시점의 수요 압력 (제안 시스템은 0.8 이상이면 벤더 조달 ▲ · 확신이 낮으면 사람 질문 ■).
아래 = 그 판단의 결과 — 다음 15분 관측에서 가장 위험한 슬라이스의 부하(이용률 ÷ 임계). 1 을 넘으면 SLA 위반(X).

실행 기록 (emergency · 10스텝 · 같은 트래픽): runs/original-emergency-s{seed} · runs/proposed_p08-emergency-s{seed}.
기존 프로젝트의 마지막(스텝 9 결과) 관측은 장부에 없어, 같은 트래픽 ÷ (적용 배분 × 기본 용량)으로 복원한다
(results/onset-10step-s0/plot_final.py 와 같은 방법 · 복원한 위반이 장부의 채점과 같은지 검사한다).
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
N, CAP, THRESHOLD = 10, 1.6, 0.8
K = ("embb", "urllc", "mmtc")
BLACK, GRAY, LIGHT = "#000000", "#7a7a7a", "#d9d9d9"


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
        applied = any(c["result"].get("accepted") for c in cs if c["tool"] == "add_capacity")
        ours.append({"vendor": proc["vendor_id"].replace("vendor-", "v") if proc else None, "applied": applied,
                     "human": any(c["tool"] == "record_escalation" for c in cs)})
    for t in range(N):
        ours[t]["pressure"] = obs[t]["demand_pressure"]
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
        scored = any(dec[t]["outcome"]["observed_violations"].values())
        assert (load > 1) == scored, f"step {t}: 복원한 위반이 장부와 다르다"
        assert abs(dec[t]["observation"]["traffic"]["urllc"] - obs[t]["traffic"]["urllc"]) < 1e-9, "트래픽이 다르다"
        orig.append({"pressure": dec[t]["observation"]["demand_pressure"], "load": load})
    return orig, ours


def main():
    orig, ours = load()
    x = list(range(N))
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(6.3, 4.9), sharex=True,
                                 gridspec_kw={"height_ratios": [1, 1], "hspace": 0.12})

    # 위 — 판단 근거: 수요 압력
    a1.plot(x, [d["pressure"] for d in orig], ls="--", marker="s", ms=4.5, mfc="white", color=GRAY, lw=1.3,
            label="기존 프로젝트 (사람 선언 · 고정표 · 조달 없음)")
    a1.plot(x, [d["pressure"] for d in ours], ls="-", marker="o", ms=4.5, color=BLACK, lw=1.6,
            label="제안 시스템 (Claude 오케스트레이터 + MCP)")
    a1.axhline(THRESHOLD, color=BLACK, ls=":", lw=0.9)
    a1.axhline(1.0, color=GRAY, lw=0.7)
    a1.text(N + 0.5, THRESHOLD, "조달 임계\n0.8", fontsize=6.8, va="center", ha="right")
    a1.text(N + 0.5, 1.0, "한계\n1.0", fontsize=6.8, va="center", ha="right", color=GRAY)
    lo = min(min(d["pressure"] for d in orig), min(d["pressure"] for d in ours))
    hi = max(max(d["pressure"] for d in orig), max(d["pressure"] for d in ours))
    y_buy, y_ask = hi + 0.14, lo - 0.1          # 맨 위 줄 = 벤더 조달, 맨 아래 줄 = 운영자 질문 (선과 겹치지 않게)
    a1.text(N + 0.5, y_buy, "벤더 조달", fontsize=7, va="center", ha="right", fontweight="bold")
    a1.text(N + 0.5, y_ask, "운영자 질문", fontsize=7, va="center", ha="right", fontweight="bold")
    for t, d in enumerate(ours):
        if d["vendor"]:
            a1.scatter(t, y_buy, marker="^", s=34, zorder=4,
                       **(dict(c=BLACK) if d["applied"] else dict(facecolors="white", edgecolors=BLACK, lw=0.9)))
            a1.text(t + 0.13, y_buy, d["vendor"], ha="left", va="center", fontsize=7)
            a1.plot([t, t], [d["pressure"] + 0.02, y_buy - 0.035], color=LIGHT, lw=0.8, zorder=1)
        if d["human"]:
            a1.scatter(t, y_ask, marker="s", s=28, c=BLACK, zorder=4)
    a1.set_ylim(lo - 0.17, hi + 0.21)
    a1.set_ylabel("판단 근거\n수요 압력", fontsize=8)

    # 아래 — 판단 결과: 다음 15분 SLA
    a2.axhspan(1.0, 3, color=LIGHT, alpha=0.6, lw=0, zorder=0)
    a2.axhline(1.0, color=BLACK, ls="--", lw=0.8)
    a2.text(N - 0.55, 1.02, "SLA 위반 구간", fontsize=7, ha="right", va="bottom")
    a2.plot(x, [d["load"] for d in orig], ls="--", color=GRAY, lw=1.3, zorder=2)
    a2.plot(x, [d["load"] for d in ours], ls="-", color=BLACK, lw=1.6, zorder=2)
    for t in x:
        lo_, lu = orig[t]["load"], ours[t]["load"]
        a2.scatter(t, lo_, zorder=3, **(dict(marker="X", s=36, c=GRAY) if lo_ > 1
                                         else dict(marker="s", s=22, facecolors="white", edgecolors=GRAY)))
        a2.scatter(t, lu, zorder=4, **(dict(marker="X", s=40, c=BLACK) if lu > 1 else dict(marker="o", s=22, c=BLACK)))
    vo = sum(d["load"] > 1 for d in orig)
    vu = sum(d["load"] > 1 for d in ours)
    a2.text(N - 0.25, orig[-1]["load"], f"위반 {vo}/{N}", fontsize=7.6, va="center", color=GRAY, fontweight="bold")
    a2.text(N - 0.25, ours[-1]["load"], f"위반 {vu}/{N}", fontsize=7.6, va="center", fontweight="bold")
    loads = [d["load"] for d in orig + ours]
    a2.set_ylim(min(loads) - 0.1, max(loads) + 0.12)
    a2.set_ylabel("판단 결과 (다음 15분)\n최약 슬라이스 부하", fontsize=8)
    a2.set_xticks(x, [f"{t}\n{t * 15 // 60}:{t * 15 % 60:02d}" for t in x], fontsize=7.2)
    a2.set_xlabel("판단 스텝 (1스텝 = 15분)", fontsize=8)

    for a in (a1, a2):
        a.set_xlim(-0.5, N + 0.55)
        a.grid(axis="y", color=LIGHT, lw=0.5)
        a.tick_params(labelsize=7.2)
        for sp in ("top", "right"):
            a.spines[sp].set_visible(False)
    handles, labels = a1.get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", bbox_to_anchor=(0.5, 0.04), ncol=2, fontsize=7, frameon=False,
               handlelength=2.6)
    fig.text(0.5, 0.008, "▲ 벤더 조달 (옆 = 고른 벤더, △ = 용량 상한으로 미반영)    ■ 운영자에게 질문    X SLA 위반",
             ha="center", fontsize=7)
    fig.subplots_adjust(left=0.13, right=0.97, top=0.98, bottom=0.2)
    for ext in ("png", "pdf"):
        fig.savefig(HERE / f"fig_graph_s{SEED}.{ext}", dpi=600)
    print(f"seed {SEED}: 위반 {vo} → {vu} · 조달 {sum(1 for d in ours if d['vendor'])} · 사람 질문 {sum(d['human'] for d in ours)}")


if __name__ == "__main__":
    main()
