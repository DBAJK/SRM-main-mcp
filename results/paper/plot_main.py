"""논문 본문 그림 1장 (흑백) — 누가 운영 판단을 했나 · 그 결과. 기존 프로젝트 vs 우리 프로젝트.

    py -3.10 results/paper/plot_main.py      → results/paper/fig_main.png (300dpi) · fig_main.pdf

조건: emergency · 10스텝 · seed 0~4 (판단 50번) · 같은 트래픽.
실행 기록: runs/original-emergency-s{0..4} · runs/proposed_p08-emergency-s{0..4}.

(a) 운영 판단 주체
    상황 판단   — 기존: 사람이 선언(--emergency). 우리: 시스템, 확신이 낮은 스텝만 사람에게 질문(record_escalation)
    용량 조달   — 수요 압력이 임계(0.8)를 넘은 스텝에서 누가 대응했나. 기존: 조달 기능 없음. 우리: 시스템이 벤더에서 조달
(b) SLA 위반 — outcome.observed_violations 중 하나라도 참인 스텝 수 (⑤ 채점과 같은 판정)
"""
import json
import statistics as st
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["pdf.fonttype"] = 42
plt.rcParams["hatch.linewidth"] = 0.8

HERE = Path(__file__).resolve().parent
RUNS = HERE.parents[1] / "runs"
SEEDS = [0, 1, 2, 3, 4]
THRESHOLD = 0.8
BLACK, GRAY, LIGHT = "#000000", "#777777", "#d9d9d9"


def collect(arm):
    steps = human = over = responded = 0
    viol = []
    for s in SEEDS:
        book = json.load(open(RUNS / f"{arm}-emergency-s{s}" / "decisions.json", encoding="utf-8"))["decisions"]
        by = {}
        for r in book:
            by.setdefault(r["step"], []).append(r)
        steps += len(by)
        human += sum(1 for rs in by.values() if any(r["kind"] == "escalation" for r in rs))
        for rs in by.values():
            r = rs[-1]
            if r["observation"]["demand_pressure"] >= THRESHOLD:
                over += 1
                responded += any(x.get("vendor_id") for x in rs)
        dec = {r["step"]: r for r in book if r["kind"] == "decision"}
        viol.append(sum(1 for r in dec.values() if any((r.get("outcome") or {}).get("observed_violations", {}).values())))
    return {"steps": steps, "human": human, "over": over, "responded": responded, "viol": viol}


ORIG, OURS = collect("original"), collect("proposed_p08")
ORIG["human"] = ORIG["steps"]          # 기존은 매 스텝 상황을 사람이 선언한 값으로 운영한다


def hbar(ax, y, parts, height=0.34):
    """parts = [(비율, 채움색, 빗금, 글)] 를 왼쪽부터 쌓는다."""
    left = 0.0
    for frac, fc, hatch, text in parts:
        if frac <= 0:
            continue
        ax.barh(y, frac * 100, left=left * 100, height=height, color=fc, edgecolor=BLACK, hatch=hatch, lw=0.8)
        if text:
            dark = fc == BLACK
            ax.text((left + frac / 2) * 100, y, text, ha="center", va="center", fontsize=7.6,
                    color="white" if dark else BLACK,
                    bbox=None if dark else dict(boxstyle="round,pad=0.15", fc="white", ec="none"))
        left += frac


def main():
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(7.0, 2.9), gridspec_kw={"width_ratios": [1.75, 1], "wspace": 0.38})

    # (a) 운영 판단 주체
    o, u = ORIG, OURS
    rows = [
        (3.0, "기존", [(1.0, BLACK, None, f"사람 {o['human']}/{o['steps']} (100%)")]),
        (2.6, "우리", [((u["steps"] - u["human"]) / u["steps"], "white", "////",
                       f"시스템 {u['steps'] - u['human']}/{u['steps']} ({(u['steps'] - u['human']) / u['steps']:.0%})"),
                      (u["human"] / u["steps"], BLACK, None, "")]),
        (1.4, "기존", [(1.0, "white", None, f"대응 없음 0/{o['over']} (조달 기능 없음)")]),
        (1.0, "우리", [(u["responded"] / u["over"], "white", "////",
                       f"시스템이 벤더 조달 {u['responded']}/{u['over']} ({u['responded'] / u['over']:.0%})")]),
    ]
    for y, who, parts in rows:
        hbar(ax, y, parts)
        ax.text(-2, y, who, ha="right", va="center", fontsize=8.5)
    ax.text(101, 2.6, f"사람에게\n질문 {u['human']}", ha="left", va="center", fontsize=7.2)
    ax.text(-15, 2.8, "상황 판단\n(50스텝)", ha="right", va="center", fontsize=8.5, fontweight="bold")
    ax.text(-15, 1.2, f"임계 초과 시\n용량 확보\n(압력 ≥ {THRESHOLD})", ha="right", va="center", fontsize=8.5,
            fontweight="bold")
    ax.set_xlim(0, 100)
    ax.set_ylim(0.6, 3.4)
    ax.set_yticks([])
    ax.set_xticks([0, 25, 50, 75, 100], ["0", "25", "50", "75", "100%"], fontsize=7.5)
    ax.set_title("(a) 운영 판단을 누가 했나", fontsize=9.5, loc="left", x=-0.42)
    ax.legend(handles=[Patch(fc=BLACK, ec=BLACK, label="사람"), Patch(fc="white", ec=BLACK, hatch="////", label="시스템"),
                       Patch(fc="white", ec=BLACK, label="대응 없음")],
              loc="upper center", bbox_to_anchor=(0.5, -0.13), ncol=3, fontsize=7.5, frameon=False)

    # (b) 결과 — SLA 위반
    for i, (d, fc, hatch, name) in enumerate(((o, BLACK, None, "기존"), (u, "white", "////", "우리"))):
        m = st.mean(d["viol"])
        bx.bar(i, m, width=0.55, color=fc, edgecolor=BLACK, hatch=hatch, lw=0.8)
        bx.scatter([i + (j - 2) * 0.07 for j in range(5)], d["viol"], s=12, color="white", edgecolor=BLACK, lw=0.7, zorder=3)
        bx.text(i, max(m, max(d["viol"])) + 0.35, f"{m:.1f}회", ha="center", va="bottom", fontsize=9, fontweight="bold")
    mo, mu = st.mean(o["viol"]), st.mean(u["viol"])
    bx.text(0.5, 11.3, f"-{(1 - mu / mo) * 100:.0f}% · 5개 시드 모두 감소", ha="center", fontsize=7.8)
    bx.set_xticks([0, 1], ["기존", "우리"], fontsize=8.5)
    bx.set_ylim(0, 12)
    bx.set_yticks([0, 2, 4, 6, 8, 10])
    bx.set_ylabel("SLA 위반 (회 / 10스텝)", fontsize=8)
    bx.tick_params(labelsize=7.5)
    bx.set_title("(b) 결과 — SLA 위반", fontsize=9.5, loc="left")
    for a in (ax, bx):
        for sp in ("top", "right"):
            a.spines[sp].set_visible(False)
    bx.grid(axis="y", color=LIGHT, lw=0.6)
    bx.set_axisbelow(True)

    fig.subplots_adjust(left=0.2, right=0.98, top=0.88, bottom=0.2)
    for ext in ("png", "pdf"):
        fig.savefig(HERE / f"fig_main.{ext}", dpi=300)
    print(f"상황 판단 시스템 {u['steps'] - u['human']}/{u['steps']} · 임계 초과 대응 기존 0/{o['over']} 우리 "
          f"{u['responded']}/{u['over']} · SLA {mo:.1f} → {mu:.1f}")


if __name__ == "__main__":
    main()
