"""스텝별 판단 과정 (흑백) — 기존 프로젝트 vs 우리 오케스트레이터(Claude CLI + MCP), 벤더 조달 과정 포함.

    py -3.10 results/emergency-10step-p08/plot_process.py [seed]      → process_s{seed}.png · .pdf

실행 기록 (emergency · 10스텝 · 같은 트래픽)
- 기존 프로젝트: runs/original-emergency-s{seed}/decisions.json
- 오케스트레이터: runs/proposed_p08-emergency-s{seed}/orchestrator/{calls,steps}.jsonl — Claude 가 스텝마다 부른 MCP 도구 ·
  인자 · 반환이 그대로 남아 있다(벤더 점수 순위 · 조달 · 용량 반영 · 평판 갱신 포함).

결과 행은 그 스텝 판단의 결과(다음 15분 관측의 SLA)다 — ⑤ 채점 · decisions.json outcome 과 같은 판정.
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
SEED = int(sys.argv[1]) if len(sys.argv) > 1 else 0
N = 10
THRESHOLD = 0.8
BLACK, DARK, GRAY, LIGHT, ROWBG = "#000000", "#404040", "#8c8c8c", "#d0d0d0", "#f2f2f2"
SHORT = {"vendor-1": "v1", "vendor-2": "v2", "vendor-3": "v3", "vendor-4": "v4", "vendor-5": "v5"}


# ── 데이터 ────────────────────────────────────────────────────────
def load_original():
    book = json.load(open(RUNS / f"original-emergency-s{SEED}" / "decisions.json", encoding="utf-8"))["decisions"]
    by = {r["step"]: r for r in book if r["kind"] == "decision"}
    return [{"pressure": by[t]["observation"]["demand_pressure"],
             "alloc": by[t]["allocation"],
             "viol": any((by[t].get("outcome") or {}).get("observed_violations", {}).values())} for t in range(N)]


def load_orchestrator():
    base = RUNS / f"proposed_p08-emergency-s{SEED}"
    steps = {s["step"]: s for s in (json.loads(l) for l in open(base / "orchestrator" / "steps.jsonl", encoding="utf-8"))}
    calls = [json.loads(l) for l in open(base / "orchestrator" / "calls.jsonl", encoding="utf-8")]
    book = json.load(open(base / "decisions.json", encoding="utf-8"))["decisions"]
    out = []
    for t in range(N):
        att = steps[t]["attempt"]
        cs = [c for c in calls if c["step"] == t and c["attempt"] == att and c.get("ok")]
        tools = [c["tool"] for c in cs]
        obs = next(c["result"] for c in cs if c["tool"] == "get_observation")
        conf = next((c["result"] for c in cs if c["tool"] == "compute_confidence"), {})
        esc = next((c["result"] for c in cs if c["tool"] == "record_escalation"), None)
        ranking, proc, rating = None, None, None
        adds = []          # add_capacity 시도들 (반영 여부 · 양) — 거부되면 Claude 가 양을 바꿔 다시 부르기도 한다
        for c in cs:
            if c["tool"] == "score_offerings":
                ranking = c["result"]
            elif c["tool"] == "procure" and c["result"].get("status") == "active":
                proc = {**c["result"], "slice": {"URLLC": "URLLC", "MMTC": "mMTC", "EMBB": "eMBB"}.get(
                            c["args"]["slice_type"].upper(), c["args"]["slice_type"]),
                        "duration": c["args"].get("duration_steps"), "ranking": ranking}
            elif c["tool"] == "add_capacity":
                adds.append((bool(c["result"].get("accepted")), float(c["args"].get("amount", 0))))
            elif c["tool"] == "update_rating":
                rating = c["result"]
        applied = any(a for a, _ in adds)
        applied_amount = next((amt for a, amt in reversed(adds) if a), None)
        retried = len(adds) > 1 and not adds[0][0] and applied
        recs = [r for r in book if r["step"] == t]
        rec = next((r for r in recs if r["kind"] == "decision"), recs[-1])
        ans = steps[t]["answer"]
        out.append({"pressure": obs["demand_pressure"], "tools": tools, "n_calls": len(cs),
                    "situation": ans.get("situation"), "sit_conf": conf.get("situation_confidence", ans.get("situation_confidence")),
                    "escalated": esc is not None, "human_label": (esc or {}).get("fallback_situation"),
                    "ranking": ranking, "proc": proc, "applied": applied, "applied_amount": applied_amount,
                    "retried": retried, "rating": rating,
                    "viol": any((rec.get("outcome") or {}).get("observed_violations", {}).values())})
    return out


ORIG = load_original()
ORCH = load_orchestrator()
X = list(range(N))
TLABEL = [f"스텝 {t}\n{t * 15 // 60}:{t * 15 % 60:02d}" for t in X]


# ── 그리기 도구 ───────────────────────────────────────────────────
def lanes(ax, rows):
    """rows = [(이름, 도구 설명)] 위에서 아래로. y = 행 번호(위가 큼)."""
    n = len(rows)
    for i, (name, tool) in enumerate(rows):
        y = n - 1 - i
        if i % 2 == 0:
            ax.axhspan(y - 0.5, y + 0.5, color=ROWBG, zorder=0, lw=0)
        ax.text(-0.75, y + 0.12, name, ha="right", va="center", fontsize=8.2, fontweight="bold")
        if tool:
            ax.text(-0.75, y - 0.2, tool, ha="right", va="center", fontsize=6.4, color=DARK)
    ax.set_ylim(-0.5, n - 0.5)
    ax.set_xlim(-0.6, N + 0.35)          # 오른쪽 끝에 위반 횟수를 적을 자리
    ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.tick_params(axis="x", length=0)
    for t in X:
        ax.axvline(t + 0.5, color=LIGHT, lw=0.6, zorder=0)
    return {name: n - 1 - i for i, (name, _) in enumerate(rows)}


def dot(ax, x, y, kind, text=None, dy=-0.3, fs=6.4):
    style = {"sys": dict(marker="o", s=26, c=BLACK),
             "human": dict(marker="s", s=70, c=BLACK),
             "keep": dict(marker="s", s=22, facecolors="white", edgecolors=GRAY),
             "table": dict(marker="s", s=30, facecolors="white", edgecolors=BLACK),
             "none": dict(marker="x", s=36, c=GRAY),
             "query": dict(marker="D", s=30, c=BLACK),
             "buy": dict(marker="^", s=80, c=BLACK),
             "buy_rejected": dict(marker="^", s=80, facecolors="white", edgecolors=BLACK),
             "met": dict(marker="o", s=70, facecolors="white", edgecolors=BLACK, linewidths=1.2),
             "viol": dict(marker="X", s=95, c=BLACK)}[kind]
    ax.scatter([x], [y], zorder=3, **style)
    if text:
        ax.text(x, y + dy, text, ha="center", va="center", fontsize=fs, color=BLACK, zorder=4)


# ── 그림 ─────────────────────────────────────────────────────────
def main():
    fig = plt.figure(figsize=(14, 13.2))
    gs = fig.add_gridspec(4, 3, height_ratios=[1.05, 1.55, 3.1, 1.55], hspace=0.36, wspace=0.32,
                          left=0.15, right=0.985, top=0.92, bottom=0.07)
    axA = fig.add_subplot(gs[0, :])
    axB = fig.add_subplot(gs[1, :], sharex=axA)
    axC = fig.add_subplot(gs[2, :], sharex=axA)

    # (A) 수요 압력 — 왜 조달했나
    po, pr = [d["pressure"] for d in ORIG], [d["pressure"] for d in ORCH]
    axA.plot(X, po, ls="--", marker="s", ms=5, mfc="white", color=DARK, lw=1.4, label="기존 프로젝트")
    axA.plot(X, pr, ls="-", marker="o", ms=5, color=BLACK, lw=1.8, label="우리 오케스트레이터")
    axA.axhline(THRESHOLD, color=BLACK, ls=":", lw=1)
    axA.axhline(1.0, color=GRAY, ls="-", lw=0.8)
    axA.text(1.55, THRESHOLD + 0.01, "조달 임계 0.8 (재난 시)", ha="left", va="bottom", fontsize=7.2)
    axA.text(1.55, 1.0 + 0.01, "한계 1.0 — 넘으면 어떤 배분으로도 SLA 불가", ha="left", va="bottom", fontsize=7.2, color=DARK)
    for t, d in enumerate(ORCH):
        if d["proc"]:
            axA.annotate("▲조달", (t, d["pressure"]), xytext=(0, -9), textcoords="offset points", ha="center",
                         va="top", fontsize=6.8)
    axA.set_ylabel("수요 압력\n(판단 시점)", fontsize=8.5)
    axA.set_ylim(min(po + pr) - 0.08, max(max(po + pr) + 0.12, 1.08))
    axA.legend(loc="upper left", fontsize=7.5, frameon=False, ncol=2)
    axA.grid(axis="y", color=LIGHT, lw=0.6)
    for sp in ("top", "right"):
        axA.spines[sp].set_visible(False)
    axA.tick_params(labelbottom=False, labelsize=7.5)
    axA.set_title("(A) 판단 시점의 수요 압력 — 0.8 을 넘으면 우리 오케스트레이터는 벤더 조달에 들어간다", loc="left", fontsize=10)

    # (B) 기존 프로젝트
    rowsB = [("① 관측", "시뮬레이터 상태"), ("② 상황 판단", "사람이 --emergency 선언"),
             ("③ 배분", "고정표 + 평활"), ("④ 용량 확보", "조달 기능 없음"), ("결과", "다음 15분 SLA")]
    yB = lanes(axB, rowsB)
    nvo = sum(d["viol"] for d in ORIG)
    for t, d in enumerate(ORIG):
        dot(axB, t, yB["① 관측"], "sys")
        if t == 0:
            dot(axB, t, yB["② 상황 판단"], "human", "사람 선언\nemergency", dy=-0.36)
        else:
            dot(axB, t, yB["② 상황 판단"], "keep")
        a = d["alloc"]
        dot(axB, t, yB["③ 배분"], "table", "0.2/0.7/0.1" if t == 0 else None)
        if d["pressure"] >= THRESHOLD:
            dot(axB, t, yB["④ 용량 확보"], "none", "대응 불가", dy=-0.3)
        dot(axB, t, yB["결과"], "viol" if d["viol"] else "met")
    axB.plot([0.15, N - 0.6], [yB["② 상황 판단"]] * 2, color=GRAY, lw=0.8, zorder=1)
    axB.text(N - 0.3, yB["결과"], f"위반\n{nvo}/{N}", ha="left", va="center", fontsize=8.5, fontweight="bold")
    axB.tick_params(labelbottom=False)
    axB.set_title("(B) 기존 프로젝트 — 사람이 선언한 상황과 고정표로 운영, 임계를 넘어도 용량을 늘릴 수 없다", loc="left", fontsize=10)

    # (C) 우리 오케스트레이터
    rowsC = [("① 관측", "get_observation"), ("② 상황 판단", "estimate_situation → Claude"),
             ("③ 배분안", "propose_allocation (rule_based)"), ("④ 개입 판단", "compute_confidence (확신 < 0.9 → 사람)"),
             ("⑤ 벤더 조회", "list_offerings · score_offerings"), ("⑥ 벤더 조달", "procure → add_capacity"),
             ("⑦ 기록 · 적용", "record → apply → step → report"), ("결과", "다음 15분 SLA")]
    yC = lanes(axC, rowsC)
    nvr = sum(d["viol"] for d in ORCH)
    for t, d in enumerate(ORCH):
        dot(axC, t, yC["① 관측"], "sys")
        if d["escalated"]:
            dot(axC, t, yC["② 상황 판단"], "human", f"사람 답\n{d['human_label']}", dy=-0.36)
        else:
            dot(axC, t, yC["② 상황 판단"], "sys", f"{d['situation']}\n확신 {d['sit_conf']:.2f}", dy=-0.33, fs=6)
        dot(axC, t, yC["③ 배분안"], "sys")
        if d["escalated"]:
            dot(axC, t, yC["④ 개입 판단"], "human", f"확신 {d['sit_conf']:.2f}\n→ 사람 호출", dy=-0.36, fs=6)
        else:
            dot(axC, t, yC["④ 개입 판단"], "sys")
        if d["ranking"]:
            top = d["ranking"][0]
            dot(axC, t, yC["⑤ 벤더 조회"], "query", f"1위 {SHORT[top['vendor_id']]} {top['score']:.1f}", dy=-0.3)
        if d["proc"]:
            p = d["proc"]
            label = f"{SHORT[p['vendor_id']]} · {p['slice']}\n+{p['capacity_gain']:.2f} · ${p['cost_total']:,.0f}"
            if d["applied"] and d["retried"]:
                # 첫 반영이 상한 초과로 거부 → Claude 가 거부 사유를 읽고 양을 줄여 다시 반영
                label = (f"{SHORT[p['vendor_id']]} · {p['slice']} · ${p['cost_total']:,.0f}\n"
                         f"구매 {p['capacity_gain']:.2f} → 상한 거부\n→ {d['applied_amount']:.2f} 로 줄여 재반영")
                dot(axC, t, yC["⑥ 벤더 조달"], "buy", label, dy=-0.43, fs=5.6)
            elif d["applied"]:
                dot(axC, t, yC["⑥ 벤더 조달"], "buy", label, dy=-0.36, fs=6)
            else:
                dot(axC, t, yC["⑥ 벤더 조달"], "buy_rejected", label + "\n반영 거부(용량 상한)", dy=-0.42, fs=5.8)
        dot(axC, t, yC["⑦ 기록 · 적용"], "sys")
        dot(axC, t, yC["결과"], "viol" if d["viol"] else "met")
    axC.text(N - 0.3, yC["결과"], f"위반\n{nvr}/{N}", ha="left", va="center", fontsize=8.5, fontweight="bold")
    axC.set_xticks(X, TLABEL, fontsize=7.5)
    for t, d in enumerate(ORCH):
        axC.text(t, yC["① 관측"] - 0.3, f"도구 {d['n_calls']}회", ha="center", va="center", fontsize=6.3, color=DARK)
    nproc = sum(1 for d in ORCH if d["proc"])
    nesc = sum(1 for d in ORCH if d["escalated"])
    axC.set_title(f"(C) 우리 오케스트레이터 (Claude CLI + MCP 서버 5개) — 매 스텝 도구를 직접 골라 판단 · "
                  f"벤더 조달 {nproc}회 · 사람 질문 {nesc}회", loc="left", fontsize=10)

    # (D) 벤더를 가져오는 과정 — 대표 조달 스텝 2개
    procs = [(t, d) for t, d in enumerate(ORCH) if d["proc"]]
    picks = []
    if procs:
        picks.append(procs[0])
        first_vendor = procs[0][1]["proc"]["vendor_id"]
        switch = next(((t, d) for t, d in procs[1:] if d["proc"]["vendor_id"] != first_vendor), None)
        picks.append(switch or procs[-1])
    axF = fig.add_subplot(gs[3, 0])
    axF.axis("off")
    if procs:
        t0, d0 = procs[0]
        seq = d0["tools"]
        lines, line = [], ""
        for i, tool in enumerate(seq):
            piece = tool + ("  →  " if i < len(seq) - 1 else "")
            if len(line) + len(piece) > 44:
                lines.append(line)
                line = ""
            line += piece
        lines.append(line)
        axF.set_title(f"(D) 스텝 {t0} 에서 Claude 가 부른 MCP 도구 순서 ({len(seq)}회)", loc="left", fontsize=9.5)
        axF.text(0.0, 0.92, f"수요 압력 {d0['pressure']:.2f} ≥ 0.8  →  벤더 조달 경로", fontsize=8, fontweight="bold",
                 transform=axF.transAxes, va="top")
        axF.text(0.0, 0.76, "\n".join(lines), fontsize=7.4, transform=axF.transAxes, va="top", linespacing=1.6)
    all_scores = [r["score"] for _, d in picks for r in (d["proc"]["ranking"] or d["ranking"] or [])]
    lo = (min(all_scores) - 6) if all_scores else 0          # 두 차트 같은 눈금 — 점수 차이를 과장하지 않는다
    for k, (t, d) in enumerate(picks[:2]):
        ax = fig.add_subplot(gs[3, 1 + k])
        rk = d["proc"]["ranking"] or d["ranking"] or []
        names = [f"{r['vendor_id']}" for r in rk][::-1]
        scores = [r["score"] for r in rk][::-1]
        chosen = d["proc"]["vendor_id"]
        ax.barh(names, scores, color=[BLACK if n == chosen else "white" for n in names], edgecolor=BLACK, lw=0.8, height=0.6)
        for i, (n, s) in enumerate(zip(names, scores)):
            ax.text(s + 0.4, i, f"{s:.1f}" + ("  ← 선택" if n == chosen else ""), va="center", fontsize=7.2)
        ax.set_xlim(lo, 106)
        ax.tick_params(labelsize=7.2)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
        rt = d["rating"] or {}
        first = picks[0][1]["proc"]
        if k == 0:
            why = "점수 1위 벤더에서 조달"
        elif d["proc"]["slice"] != first["slice"]:
            why = f"다른 슬라이스({d['proc']['slice']})라 벤더 순위가 다르다"
        elif chosen != first["vendor_id"]:
            why = f"같은 슬라이스인데 {SHORT[first['vendor_id']]} 평판이 떨어져 순위가 바뀌었다"
        else:
            why = "같은 벤더가 계속 1위"
        ax.set_title(f"스텝 {t} · {d['proc']['slice']} 벤더 점수 (score_offerings) — {chosen} 선택\n{why}",
                     loc="left", fontsize=8.6)
        ax.set_xlabel(f"벤더 점수 (QoS · 가격 · 평판)   |   그 스텝 결과 뒤 {chosen} 평판 "
                      f"{rt.get('rating_before', '?')} → {rt.get('rating_after', '?')}", fontsize=7.2)

    fig.suptitle(f"재난(emergency) 상황 · seed {SEED} · 10스텝 (15분 × 10, 같은 트래픽) — 스텝별 판단 과정\n"
                 f"SLA 위반 {nvo}회 → {nvr}회 · 벤더 직접 조달 {nproc}회 · 사람 질문 {nesc}회",
                 fontsize=12.5, fontweight="bold")
    legend = ("●  시스템이 수행     ■  사람     □  고정표 · 선언 유지     ×  임계 초과인데 대응 불가     "
              "◆  벤더 조회     ▲  벤더 조달(흰 ▲ = 반영 거부)     ○  SLA 충족     X  SLA 위반")
    fig.text(0.15, 0.012, legend, fontsize=7.6, color=DARK)
    for ext in ("png", "pdf"):
        fig.savefig(HERE / f"process_s{SEED}.{ext}", dpi=200)
    print(f"seed {SEED}: 위반 {nvo} → {nvr} · 조달 {nproc} · 사람 질문 {nesc}")


if __name__ == "__main__":
    main()
