"""그림 — 운영 정책 변경: 오케스트레이터는 프롬프트 문단, 고정 루프는 코드. 그리고 그 변경의 효과(onset 10스텝 · 5시드).

    py -3.10 results/paper/plot_policy_change.py      → results/paper/fig_policy_change.png

데이터 출처
- 프롬프트 diff: 커밋 256e2b0 agent/orchestrator/prompt.md (+8 −3)
- original · 오케스트레이터(1.0 · 0.8): results/onset-10step-s0/seeds_summary.txt (2026-10-06 세션)
- 고정 루프(1.0): 같은 조건 재실행 runs/proposed_rule-onset-s0~4 — 시드별로 오케스트레이터 1.0 과 위반 · 조달 · 사람 호출이 같다
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

for cand in ("Malgun Gothic", "AppleGothic", "NanumGothic"):
    if cand in {f.name for f in font_manager.fontManager.ttflist}:
        plt.rcParams["font.family"] = cand
        break
plt.rcParams["axes.unicode_minus"] = False

SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
GRAY, BLUE, ORANGE = "#8a8984", "#2a78d6", "#eb6834"      # 원본(기준) · 규칙 1.0 · 재난 시 0.8 (validate_palette PASS)

SEEDS = [0, 1, 2, 3, 4]
DATA = {   # seeds_summary.txt
    "기존 프로젝트\n(원본 규칙)":        {"viol": [8, 6, 8, 7, 6], "proc": [0, 0, 0, 0, 0], "cost": [0, 0, 0, 0, 0], "c": GRAY},
    "오케스트레이터\n조달 기준 1.0":      {"viol": [4, 5, 7, 6, 7], "proc": [2, 0, 1, 2, 0], "cost": [1225, 0, 625, 1175, 0], "c": BLUE},
    "오케스트레이터\n재난 시 0.8 (문단 수정)": {"viol": [4, 5, 6, 4, 6], "proc": [3, 2, 5, 4, 2], "cost": [1875, 1000, 2575, 2475, 1225], "c": ORANGE},
}

PROMPT_DIFF = [
    ("-", "조달: demand_pressure 가 1.0 이상일 때만 조달한다. 1.0 미만이면 배분을"),
    ("-", "  다시 나누는 것만으로 … 사는 것은 비용만 쓰는 일이다."),
    ("-", "  1.0 이상이면 어떤 배분으로도 모자라니 조달이 유일한 해법이다."),
    ("+", "조달 기준은 이번 스텝에 네가 판단한 상황에 따라 다르다."),
    ("+", "  · emergency 로 판단했으면 demand_pressure 가 0.8 이상일 때 조달한다."),
    ("+", "    긴급 통신(URLLC)이 끊기는 대가가 크므로 한계(1.0)에 닿기 전에 확보한다."),
    ("+", "    0.8 은 \"부하를 용량의 80% 미만으로 유지\" 운영 기준이다. …"),
    ("+", "  · 그 밖의 상황이면 demand_pressure 가 1.0 이상일 때만 조달한다. …"),
]
CODE_CHANGE = [
    (" ", "# agent/deciders/rule.py:107 — 지금은 상황과 무관한 전역 기준"),
    ("-", "procure = ctx.demand_pressure >= procure_pressure()"),
    ("+", "procure = ctx.demand_pressure >= procure_pressure(situation)"),
    (" ", ""),
    (" ", "# agent/schema.py — 기준을 상황별로 나누는 함수로 바꿔야 한다"),
    ("+", "def procure_pressure(situation):"),
    ("+", "    return 0.8 if situation == \"emergency\" else 1.0"),
    (" ", ""),
    (" ", "# + 검사(check_mock) 수정 · 재배포 · 회귀 측정"),
]


def diff_panel(ax, title, sub, lines):
    ax.set_facecolor(SURFACE)
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_color(GRID)
    ax.set_title(title, loc="left", fontsize=13, color=INK, fontweight="bold", pad=24)
    ax.text(0.0, 1.015, sub, transform=ax.transAxes, va="bottom", fontsize=10, color=INK2)
    y = 0.93
    for mark, text in lines:
        bg = {"-": "#fbe3e3", "+": "#e2f3e8"}.get(mark)
        if bg:
            ax.axhspan(y - 0.085, y + 0.02, xmin=0.0, xmax=1.0, color=bg, lw=0)
        ax.text(0.015, y - 0.03, (mark if mark != " " else " ") + "   " + text, transform=ax.transAxes,
                va="center", fontsize=9.3, color=INK if mark != " " else INK2)
        y -= 0.105
    ax.set_ylim(0, 1)


def metric_panel(ax, key, title, unit, fmt):
    names = list(DATA)
    for i, n in enumerate(names):
        vals = DATA[n][key]
        mean = sum(vals) / len(vals)
        ax.bar(i, mean, width=0.62, color=DATA[n]["c"], zorder=2)
        ax.scatter([i + (j - 2) * 0.08 for j in range(5)], vals, s=22, color=SURFACE,
                   edgecolor=INK2, linewidth=0.9, zorder=3)
        top = max(mean, max(vals))
        ax.text(i, top + ax_max(key) * 0.05, fmt(mean), ha="center", va="bottom", fontsize=11,
                color=INK, fontweight="bold")
    ax.set_xticks(range(len(names)), names, fontsize=9, color=INK2)
    ax.set_title(title, loc="left", fontsize=12, color=INK)
    ax.set_ylabel(unit, color=INK2)
    ax.set_ylim(0, ax_max(key) * 1.25)
    ax.grid(axis="y", color=GRID, zorder=0)
    ax.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=INK2)


def ax_max(key):
    return max(max(d[key]) for d in DATA.values())


def main():
    fig = plt.figure(figsize=(16, 10.5), facecolor=SURFACE)
    gs = fig.add_gridspec(2, 3, height_ratios=[1.15, 1], hspace=0.32, wspace=0.28)
    diff_panel(fig.add_subplot(gs[0, 0:2]), "① 오케스트레이터 — 프롬프트 문단 수정",
               "agent/orchestrator/prompt.md · +8 / -3 줄 · 코드 변경 0 · 운영자가 자연어로 바꿀 수 있다", PROMPT_DIFF)
    diff_panel(fig.add_subplot(gs[0, 2]), "② 고정 루프 — 코드 수정 필요",
               "같은 정책을 넣으려면 (아직 미반영 — 지금도 1.0)", CODE_CHANGE)
    metric_panel(fig.add_subplot(gs[1, 0]), "proc", "③ 행동이 바뀌었다 — 조달 횟수", "회 / 10스텝", lambda v: f"{v:.1f}회")
    metric_panel(fig.add_subplot(gs[1, 1]), "viol", "④ 결과 — SLA 위반 (낮을수록 좋음)", "회 / 10스텝", lambda v: f"{v:.1f}회")
    metric_panel(fig.add_subplot(gs[1, 2]), "cost", "⑤ 대가 — 벤더 조달 비용", "가상 비용 ($)", lambda v: f"${v:,.0f}")
    fig.suptitle("운영 정책 변경 \"재난이면 압력 0.8부터 조달\" — 프롬프트 한 문단으로 반영되고 행동 · 결과가 바뀐다",
                 fontsize=15, color=INK, fontweight="bold", y=0.985)
    fig.text(0.5, 0.012, "평상시 1시간 → 재난(onset) · 10스텝 · seed 0~4 · 막대·숫자 = 평균, 점 = 시드별.  "
             "고정 루프(기준 1.0)는 같은 조건에서 시드별로 오케스트레이터 1.0 과 위반 · 조달 · 사람 호출이 모두 같았다(평균 위반 5.8).",
             ha="center", fontsize=9.5, color=INK2)
    out = Path(__file__).with_name("fig_policy_change.png")
    fig.savefig(out, dpi=150, facecolor=SURFACE)
    print(f"→ {out}")


if __name__ == "__main__":
    main()
