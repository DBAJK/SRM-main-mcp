"""논문 본문용 그림 — 스텝별 판단 과정 (흑백 · 본문 폭 16cm). 기존 프로젝트 vs 제안 시스템(Claude CLI 오케스트레이터).

    py -3.10 results/paper/plot_process_paper.py [seed]     → results/paper/fig_process_s{seed}.png (600dpi) · .pdf

제목은 넣지 않는다 — 논문 캡션이 설명한다. 실행 기록 (emergency · 10스텝 · 같은 트래픽):
runs/original-emergency-s{seed} · runs/proposed_p08-emergency-s{seed} (오케스트레이터 calls.jsonl · steps.jsonl · decisions.json).
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
N = 10
THRESHOLD = 0.8
BLACK, GRAY, LIGHT, BAND = "#000000", "#6e6e6e", "#c8c8c8", "#efefef"


def violated(rec):
    return any((rec.get("outcome") or {}).get("observed_violations", {}).values())


def load():
    ob = json.load(open(RUNS / f"original-emergency-s{SEED}" / "decisions.json", encoding="utf-8"))["decisions"]
    od = {r["step"]: r for r in ob if r["kind"] == "decision"}
    orig = [{"pressure": od[t]["observation"]["demand_pressure"], "viol": violated(od[t])} for t in range(N)]

    base = RUNS / f"proposed_p08-emergency-s{SEED}"
    steps = {s["step"]: s for s in (json.loads(l) for l in open(base / "orchestrator" / "steps.jsonl", encoding="utf-8"))}
    calls = [json.loads(l) for l in open(base / "orchestrator" / "calls.jsonl", encoding="utf-8")]
    book = json.load(open(base / "decisions.json", encoding="utf-8"))["decisions"]
    ours = []
    for t in range(N):
        cs = [c for c in calls if c["step"] == t and c["attempt"] == steps[t]["attempt"] and c.get("ok")]
        obs = next(c["result"] for c in cs if c["tool"] == "get_observation")
        proc = next((c["result"] for c in cs if c["tool"] == "procure" and c["result"].get("status") == "active"), None)
        adds = [bool(c["result"].get("accepted")) for c in cs if c["tool"] == "add_capacity"]
        recs = [r for r in book if r["step"] == t]
        rec = next((r for r in recs if r["kind"] == "decision"), recs[-1])
        ours.append({"pressure": obs["demand_pressure"], "human": any(c["tool"] == "record_escalation" for c in cs),
                     "vendor": proc["vendor_id"].replace("vendor-", "v") if proc else None,
                     "applied": any(adds), "viol": violated(rec)})
    return orig, ours


def main():
    orig, ours = load()
    rows = [  # (그룹, 이름, y)
        ("기존", "상황 판단", 6.6), ("기존", "용량 확보", 5.8), ("기존", "SLA", 5.0),
        ("제안", "상황 판단", 3.6), ("제안", "수요 압력", 2.8), ("제안", "벤더 조달", 2.0), ("제안", "SLA", 1.2),
    ]
    Y = {(g, n): y for g, n, y in rows}
    fig, ax = plt.subplots(figsize=(6.3, 3.5))

    # 행 배경 · 이름 · 그룹 표시
    for g, n, y in rows:
        if n in ("상황 판단", "벤더 조달") or (g == "기존" and n == "SLA"):
            ax.axhspan(y - 0.4, y + 0.4, color=BAND, lw=0, zorder=0)
        ax.text(-0.62, y, n, ha="right", va="center", fontsize=8)
    for label, top, bottom in (("기존\n프로젝트", 7.0, 4.6), ("제안\n시스템", 4.0, 0.8)):
        ax.plot([-2.05, -2.05], [bottom + 0.05, top - 0.05], color=BLACK, lw=0.8, clip_on=False)
        ax.text(-2.15, (top + bottom) / 2, label, ha="right", va="center", fontsize=8.5, fontweight="bold")
    ax.axhline(4.3, color=BLACK, lw=0.6)

    for t in range(N):
        o, u = orig[t], ours[t]
        # 기존 — 사람이 처음 한 번 선언한 상황으로 고정표 운영
        if t == 0:
            ax.scatter(t, Y["기존", "상황 판단"], marker="s", s=38, c=BLACK, zorder=3)
        else:
            ax.scatter(t, Y["기존", "상황 판단"], marker="s", s=16, facecolors="white", edgecolors=GRAY, zorder=3)
        if o["pressure"] >= THRESHOLD:
            ax.scatter(t, Y["기존", "용량 확보"], marker="x", s=30, c=BLACK, lw=1.1, zorder=3)
        ax.scatter(t, Y["기존", "SLA"], **(dict(marker="X", s=48, c=BLACK) if o["viol"]
                                           else dict(marker="o", s=40, facecolors="white", edgecolors=BLACK, lw=1)), zorder=3)
        # 제안 — 시스템이 판단, 확신이 낮을 때만 사람에게 질문 · 압력 0.8 이상이면 벤더 조달
        if u["human"]:
            ax.scatter(t, Y["제안", "상황 판단"], marker="s", s=38, c=BLACK, zorder=3)
        else:
            ax.scatter(t, Y["제안", "상황 판단"], marker="o", s=22, c=BLACK, zorder=3)
        ax.text(t, Y["제안", "수요 압력"], f"{u['pressure']:.2f}", ha="center", va="center", fontsize=7.4,
                fontweight="bold" if u["pressure"] >= THRESHOLD else "normal",
                color=BLACK if u["pressure"] >= THRESHOLD else GRAY)
        if u["vendor"]:
            ax.scatter(t, Y["제안", "벤더 조달"] + 0.08, marker="^", s=46, zorder=3,
                       **(dict(c=BLACK) if u["applied"] else dict(facecolors="white", edgecolors=BLACK, lw=1)))
            ax.text(t, Y["제안", "벤더 조달"] - 0.27, u["vendor"], ha="center", va="center", fontsize=7.2)
        ax.scatter(t, Y["제안", "SLA"], **(dict(marker="X", s=48, c=BLACK) if u["viol"]
                                           else dict(marker="o", s=40, facecolors="white", edgecolors=BLACK, lw=1)), zorder=3)

    # 오른쪽 합계
    vo, vu = sum(d["viol"] for d in orig), sum(d["viol"] for d in ours)
    over = sum(1 for d in orig if d["pressure"] >= THRESHOLD)
    np_, nh = sum(1 for d in ours if d["vendor"]), sum(1 for d in ours if d["human"])
    right = [(Y["기존", "상황 판단"], "사람 선언"), (Y["기존", "용량 확보"], f"대응 0/{over}"),
             (Y["기존", "SLA"], f"위반 {vo}/{N}"), (Y["제안", "상황 판단"], f"사람 질문 {nh}"),
             (Y["제안", "벤더 조달"], f"조달 {np_}회"), (Y["제안", "SLA"], f"위반 {vu}/{N}")]
    for y, txt in right:
        ax.text(N - 0.35, y, txt, ha="left", va="center", fontsize=7.8,
                fontweight="bold" if txt.startswith("위반") else "normal")

    ax.set_xlim(-0.6, N + 1.3)
    ax.set_ylim(0.55, 7.15)
    ax.set_yticks([])
    ax.set_xticks(range(N), [f"{t}\n{t * 15 // 60}:{t * 15 % 60:02d}" for t in range(N)], fontsize=7.4)
    ax.set_xlabel("스텝 (1스텝 = 15분)", fontsize=8)
    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
    ax.tick_params(axis="x", length=2)
    for t in range(N):
        ax.axvline(t + 0.5, color=LIGHT, lw=0.4, zorder=0)

    legend = ("■ 사람 판단    ● 시스템 판단    × 압력 0.8 초과인데 대응 수단 없음    ○ SLA 충족    X SLA 위반\n"
              "▲ 벤더 조달 (아래 = 고른 벤더, △ = 용량 상한으로 미반영)    굵은 숫자 = 수요 압력 ≥ 0.8 (조달 임계)")
    fig.text(0.5, 0.012, legend, ha="center", va="bottom", fontsize=7, color=BLACK, linespacing=1.5)
    fig.subplots_adjust(left=0.2, right=0.985, top=0.98, bottom=0.25)
    for ext in ("png", "pdf"):
        fig.savefig(HERE / f"fig_process_s{SEED}.{ext}", dpi=600)
    print(f"seed {SEED}: 위반 {vo} → {vu} · 조달 {np_} · 사람 질문 {nh} · 기존 임계 초과 {over}")


if __name__ == "__main__":
    main()
