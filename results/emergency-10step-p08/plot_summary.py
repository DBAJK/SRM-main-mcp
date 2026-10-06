"""emergency 10스텝 · seed 0~4 요약 — 기존 프로젝트 vs 우리 오케스트레이터(재난 시 조달 0.8).

    py -3.10 results/emergency-10step-p08/plot_summary.py      → summary.png · summary.txt

실행 기록: runs/original-emergency-s{0..4} · runs/proposed_p08-emergency-s{0..4} (둘 다 --steps 10).
SLA 위반 = 결정 레코드의 outcome.observed_violations 중 하나라도 참 (⑤ 채점과 같은 판정).
"""
import json
import statistics as st
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

HERE = Path(__file__).resolve().parent
RUNS = HERE.parents[1] / "runs"
SEEDS = [0, 1, 2, 3, 4]
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
GRAY, ORANGE = "#8a8984", "#eb6834"


def stats(run):
    book = json.load(open(RUNS / run / "decisions.json", encoding="utf-8"))["decisions"]
    viol = sum(1 for r in book if any((r.get("outcome") or {}).get("observed_violations", {}).values()))
    proc = [r for r in book if r.get("vendor_id")]
    esc = sum(1 for r in book if r["kind"] == "escalation")
    first = next((r["step"] for r in sorted(book, key=lambda r: r["step"]) if r.get("situation") == "emergency"), None)
    usd = None
    steps = RUNS / run / "orchestrator" / "steps.jsonl"
    if steps.exists():   # Claude CLI 가 스텝마다 남긴 cost_usd (구독 사용량 환산 · 실제 청구 아님)
        import re
        usd = round(sum(float(x) for x in re.findall(r'"cost_usd":\s*([0-9.]+)', steps.read_text(encoding="utf-8"))), 2)
    return {"viol": viol, "proc": len(proc), "cost": sum(r.get("cost_total") or 0 for r in proc),
            "esc": esc, "first": first, "usd": usd, "vendors": sorted({r["vendor_id"] for r in proc})}


ORIG = [stats(f"original-emergency-s{s}") for s in SEEDS]
ORCH = [stats(f"proposed_p08-emergency-s{s}") for s in SEEDS]


def style(ax, title, ylabel):
    ax.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", fontsize=12, color=INK)
    ax.set_ylabel(ylabel, color=INK2)
    ax.grid(axis="y", color=GRID, zorder=0)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=INK2)


def bars(ax, key, title, ylabel, fmt, first_label=None):
    data = [("기존 프로젝트", [r[key] for r in ORIG], GRAY), ("오케스트레이터\n(재난 시 0.8)", [r[key] for r in ORCH], ORANGE)]
    top = max(max(v) for _, v, _ in data) or 1
    for i, (name, vals, c) in enumerate(data):
        m = st.mean(vals)
        ax.bar(i, m, width=0.6, color=c, zorder=2)
        ax.scatter([i + (j - 2) * 0.09 for j in range(5)], vals, s=24, color=SURFACE, edgecolor=INK2, lw=0.9, zorder=3)
        label = first_label if (i == 0 and first_label) else fmt(m)
        ax.text(i, max(m, max(vals)) + top * 0.05, label, ha="center", va="bottom", fontsize=11, fontweight="bold", color=INK)
    ax.set_xticks([0, 1], [d[0] for d in data], fontsize=9.5, color=INK2)
    ax.set_ylim(0, top * 1.3)
    style(ax, title, ylabel)


def main():
    fig, axes = plt.subplots(1, 4, figsize=(19, 6), facecolor=SURFACE, gridspec_kw={"width_ratios": [1.4, 1, 1, 1]})
    ax = axes[0]
    by_val = {}
    for s, a, b in zip(SEEDS, ORIG, ORCH):
        ax.plot([0, 1], [a["viol"], b["viol"]], color=GRID, lw=1.5, zorder=1)
        ax.scatter([0], [a["viol"]], s=60, color=GRAY, zorder=3)
        ax.scatter([1], [b["viol"]], s=60, color=ORANGE, zorder=3)
        by_val.setdefault(b["viol"], []).append(str(s))
    for v, ss in by_val.items():   # 같은 값의 시드는 이름표 하나로
        ax.text(1.06, v, "seed " + "·".join(ss), va="center", fontsize=8.5, color=INK2)
    mo, mr = st.mean(r["viol"] for r in ORIG), st.mean(r["viol"] for r in ORCH)
    ax.plot([0, 1], [mo, mr], color=INK, lw=2.5, zorder=2)
    ax.text(-0.08, mo, f"평균 {mo:.1f}", ha="right", va="center", fontsize=11, fontweight="bold", color=INK)
    ax.text(0.92, mr, f"평균 {mr:.1f}", ha="right", va="center", fontsize=11, fontweight="bold", color=INK)
    ax.set_xticks([0, 1], ["기존 프로젝트", "오케스트레이터\n(재난 시 0.8)"], fontsize=9.5, color=INK2)
    ax.set_xlim(-0.45, 1.45)
    ax.set_ylim(0, 10.5)
    style(ax, "① SLA 위반 — 시드별 짝 비교 (낮을수록 좋음)", "회 / 10스텝")
    bars(axes[1], "proc", "② 벤더 조달 횟수", "회 / 10스텝", lambda v: f"{v:.1f}회")
    bars(axes[2], "cost", "③ 벤더 조달 비용", "가상 비용 ($)", lambda v: f"${v:,.0f}")
    bars(axes[3], "esc", "④ 사람 개입", "회 / 10스텝", lambda v: f"{v:.1f}회", first_label="선언 + 상시 감시")
    axes[3].text(1, axes[3].get_ylim()[1] * 0.62, "확신이 낮을 때만\n사람에게 상황 질문", ha="center", va="center",
                 fontsize=9.5, color=INK2)
    better = sum(1 for a, b in zip(ORIG, ORCH) if b["viol"] < a["viol"])
    same = sum(1 for a, b in zip(ORIG, ORCH) if b["viol"] == a["viol"])
    fig.suptitle(f"emergency · 10스텝 · seed 0~4 — SLA 위반 평균 {mo:.1f}회 → {mr:.1f}회 "
                 f"(개선 {better} · 같음 {same} · 악화 {5 - better - same} 시드)", fontsize=15, fontweight="bold", color=INK)
    fig.tight_layout()
    fig.savefig(HERE / "summary.png", dpi=150, facecolor=SURFACE)

    lines = ["seed | 기존 위반 | 오케 위반 | 조달 · 비용 · 벤더 | 사람 호출 | 재난 인식 첫 스텝 | Claude 사용량 환산"]
    for s, a, b in zip(SEEDS, ORIG, ORCH):
        lines.append(f"  {s}  |    {a['viol']}     |    {b['viol']}     | {b['proc']}회 · ${b['cost']:,.0f} · {','.join(b['vendors']) or '-'}"
                     f" | {b['esc']} | {b['first']} | {b['usd']}")
    lines.append(f"평균 | {mo:.1f} | {mr:.1f} | {st.mean(r['proc'] for r in ORCH):.1f}회 · ${st.mean(r['cost'] for r in ORCH):,.0f}"
                 f" | {st.mean(r['esc'] for r in ORCH):.1f} | — | ")
    (HERE / "summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
