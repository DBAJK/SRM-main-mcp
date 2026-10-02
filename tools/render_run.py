"""끝난 실행 하나를 그림 · 리포트로 — 원본 데모의 state_000.png · orchestration_*.png 에 해당하는 것.

    py -3.10 tools/render_run.py runs/_matrix/llm-check-theta/raw/proposed_orch-emergency-s0
    py -3.10 tools/render_run.py <실행 폴더> --out <출력 폴더> [--no-steps] [--every 5]

새로 시뮬레이션하지 않는다 — 실행이 남긴 기록(decisions.json · truth.jsonl · 오케스트레이터면 orchestrator/*.jsonl)
만 읽는다. LLM 도 서버도 안 띄운다. matplotlib 이 필요하다(.venv310 에는 없어 시스템 py -3.10 으로 돈다 —
TF 는 필요 없다).

산출 (기본 <실행 폴더>/viz/)
  state_000.png …    스텝마다 원본 visualize_state(ml_orchestrator_demo.py:643) 의 5칸 + MCP 정보
                     (고른 정책 · 개입 · 조달 · 보정량 · 판단한 상황 vs 정답)
  orchestration.png  전체 흐름 — 슬라이스별 적용 · 요청 · 필요(a*) · 개입 구간 · 정답 이벤트 · SLA 위반 · 조달 · 신뢰도
  report.md          (a) a* 근사 (b) 오류 · 종료 (c) emergency 긴급 배분 · 지연(평활) 분석

a* = normalize(traffic / (θ × capacity)) 를 **다음 관측**으로 계산한다(⑤ 채점과 같은 식, scoring.ideal_allocation).
지연 분석: 그 스텝의 요청(+보정량)이 평활 없이 곧바로 적용됐다면의 위반을 다시 계산한다(액추에이터의 평활만
뺀 반사실, 클립은 유지). "배분 목표가 틀렸나 · 늦게 따라갔나 · 어떤 배분으로도 불가능했나(압력>1)"를 가른다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from srm_mcp.common.const import ALLOC_CLIP, SLICE_KEYS, THRESHOLDS  # noqa: E402
from srm_mcp.feedback.scoring import distance, ideal_allocation      # noqa: E402

SITUATIONS = ("normal", "emergency", "special_event", "iot_surge")
SIT_COLOR = {"normal": "#ffffff", "emergency": "#f8d0d0", "special_event": "#d6e4f8", "iot_surge": "#d9f2d9"}
SLICE_COLOR = {"embb": "#3b6fb6", "urllc": "#c0392b", "mmtc": "#2e8b57"}
SLICE_TYPE = {"embb": "eMBB", "urllc": "URLLC", "mmtc": "mMTC"}


# ── 기록 읽기 ────────────────────────────────────────────────────
def _jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()] if path.is_file() else []


def truth_label(t: dict) -> str:
    for key, name in (("is_emergency", "emergency"), ("is_special_event", "special_event"),
                      ("is_iot_surge", "iot_surge")):
        if t.get(key):
            return name
    return "normal"


def _norm(a: dict) -> dict:
    tot = sum(float(a[k]) for k in SLICE_KEYS) or 1.0
    return {k: float(a[k]) / tot for k in SLICE_KEYS}


def instant(requested: dict, correction: Optional[dict]) -> dict:
    """평활 없이 곧바로 적용됐다면 — 요청 정규화 + 보정량 → 클립 → 재정규화 (액추에이터에서 평활만 뺀 것)."""
    r = _norm(requested)
    if correction:
        r = {k: r[k] + float(correction.get(k, 0.0) or 0.0) for k in SLICE_KEYS}
    low, high = ALLOC_CLIP
    c = {k: min(max(v, low), high) for k, v in r.items()}
    return _norm(c)


def violations_of(traffic: dict, alloc: dict, capacity: Optional[dict]) -> dict:
    # 옛 관측에는 capacity 가 없다 — scoring.ideal_allocation 과 같이 1.0 으로 본다
    capacity = capacity or {}
    return {k: float(traffic[k]) / (float(alloc[k]) * float(capacity.get(k, 1.0))) > THRESHOLDS[k]
            for k in SLICE_KEYS}


def _rule_correction(d: dict) -> Optional[dict]:
    """고정 루프 장부에는 보정량이 안 남는다. rule_based · 평활 뒤 방식이면 그때의 식으로 다시 만든다."""
    rat = d.get("rationale") or ""
    if d.get("escalated") or d.get("chosen_policy") != "rule_based" or "평활 뒤" not in rat:
        return None
    from srm_mcp.policy import rule
    table = "original" if "목표표 original" in rat else "theta" if "목표표 theta" in rat else None
    saved = os.environ.get("SLICE_TARGET_TABLE")
    try:
        if table:
            os.environ["SLICE_TARGET_TABLE"] = table
        return rule.correction_delta(rule.targets(d["situation"]), d["observation"])
    except Exception:                                    # noqa: BLE001 — 그림이 죽지 않게
        return None
    finally:
        if saved is None:
            os.environ.pop("SLICE_TARGET_TABLE", None)
        else:
            os.environ["SLICE_TARGET_TABLE"] = saved


def load_run(folder: Path) -> dict:
    book = json.loads((folder / "decisions.json").read_text(encoding="utf-8"))
    decs = sorted((d for d in book["decisions"] if d.get("kind") == "decision"), key=lambda d: d["step"])
    truth = {int(t["step"]): truth_label(t) for t in _jsonl(folder / "truth.jsonl")}
    od = folder / "orchestrator"
    calls, refs, osteps = _jsonl(od / "calls.jsonl"), _jsonl(od / "referee.jsonl"), _jsonl(od / "steps.jsonl")

    # 오케스트레이터는 apply_allocation 인자에 보정량이 남는다(게이트웨이가 붙였어도)
    corr_by_step: dict[int, dict] = {}
    for c in calls:
        if c.get("tool") == "apply_allocation" and c.get("ok") and (c.get("args") or {}).get("correction"):
            corr_by_step[int(c["step"])] = c["args"]["correction"]

    rows = []
    for i, d in enumerate(decs):
        t = int(d["step"])
        o = d.get("outcome") or {}
        nxt = decs[i + 1]["observation"] if i + 1 < len(decs) else None
        corr = corr_by_step.get(t) if calls else _rule_correction(d)
        row = {
            "step": t, "obs": d["observation"], "next": nxt, "truth": truth.get(t, "normal"),
            "situation": d.get("situation"), "policy": d.get("agent_policy") if d.get("escalated") else d.get("chosen_policy"),
            "escalated": bool(d.get("escalated")), "sla_met": o.get("sla_met"),
            "requested": o.get("requested_allocation") or d.get("allocation"),
            "applied": o.get("applied_allocation"), "violations": o.get("observed_violations") or {},
            "confidence": d.get("confidence") or {}, "slice_id": d.get("slice_id"), "vendor_id": d.get("vendor_id"),
            "cost": float(d.get("cost_total") or 0.0), "correction": corr,
            "shadow": o.get("shadow"),
        }
        if nxt is not None and row["applied"]:
            row["ideal"] = ideal_allocation(nxt)
            row["d_applied"] = distance(row["applied"], row["ideal"])
            if row["requested"]:
                row["d_requested"] = distance(_norm(row["requested"]), row["ideal"])
                row["instant_violations"] = violations_of(
                    nxt["traffic"], instant(row["requested"], None if row["escalated"] else corr), nxt.get("capacity"))
            row["pressure_next"] = float(nxt.get("demand_pressure") or 0.0)
            row["util_next"] = nxt.get("utilization")
        rows.append(row)
    return {"folder": folder, "config": book.get("config") or {}, "rows": rows,
            "calls": calls, "refs": refs, "osteps": osteps}


# ── 그림 ─────────────────────────────────────────────────────────
def _mpl():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    names = {f.name for f in font_manager.fontManager.ttflist}
    for cand in ("Malgun Gothic", "AppleGothic", "NanumGothic"):
        if cand in names:
            plt.rcParams["font.family"] = cand
            break
    plt.rcParams["axes.unicode_minus"] = False
    return plt


def render_state(run: dict, idx: int, out: Path, plt) -> None:
    rows = run["rows"]
    r = rows[idx]
    fig = plt.figure(figsize=(15, 8.5))
    gs = fig.add_gridspec(2, 3, height_ratios=[1, 1])
    ax1, ax2, ax3 = fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[0, 1]), fig.add_subplot(gs[0, 2])
    ax4, ax5 = fig.add_subplot(gs[1, 0]), fig.add_subplot(gs[1, 1:])
    xs = list(range(3))
    w = 0.26
    bars = [("요청", _norm(r["requested"]) if r["requested"] else None, "#bbbbbb"),
            ("적용", r["applied"], "#4a4a4a"), ("필요 a*", r.get("ideal"), "#e67e22")]
    for j, (name, a, col) in enumerate(bars):
        if a:
            ax1.bar([x + (j - 1) * w for x in xs], [a[k] for k in SLICE_KEYS], w, label=name, color=col)
    ax1.set_xticks(xs, [SLICE_TYPE[k] for k in SLICE_KEYS])
    ax1.set_ylim(0, 1)
    ax1.set_title("슬라이스 배분 (요청 · 적용 · 필요)")
    ax1.legend(fontsize=8)

    util = r.get("util_next") or r["obs"].get("utilization") or {}
    ax2.bar(xs, [util.get(k, 0) for k in SLICE_KEYS], color=[SLICE_COLOR[k] for k in SLICE_KEYS])
    for x, k in zip(xs, SLICE_KEYS):
        ax2.hlines(THRESHOLDS[k], x - 0.4, x + 0.4, colors="black", linestyles="--")
    ax2.set_xticks(xs, [SLICE_TYPE[k] for k in SLICE_KEYS])
    ax2.set_title("이용률 (적용 뒤 · 점선 = 임계)")

    lo = max(0, idx - 19)
    hist = rows[lo: idx + 1]
    for k in SLICE_KEYS:
        ax3.plot([h["step"] for h in hist], [h["obs"]["traffic"][k] for h in hist],
                 color=SLICE_COLOR[k], label=SLICE_TYPE[k])
    ax3.set_title("트래픽 이력 (최근 20스텝)")
    ax3.legend(fontsize=8)

    grid = [[1 if h["violations"].get(k) else 0 for h in hist] for k in SLICE_KEYS]
    ax4.imshow(grid, aspect="auto", cmap="Reds", vmin=0, vmax=1,
               extent=[hist[0]["step"] - 0.5, hist[-1]["step"] + 0.5, 2.5, -0.5])
    ax4.set_yticks(range(3), [SLICE_TYPE[k] for k in SLICE_KEYS])
    ax4.set_title("QoS 위반 (최근 20스텝 · 빨강 = 위반)")

    c = r["confidence"]
    lines = [
        f"스텝 {r['step']}   정답 {r['truth']}   판단 {r['situation']}" + ("   (맞음)" if r["situation"] == r["truth"] else "   (틀림)"),
        f"정책 {r['policy']}   {'개입(사람 호출)' if r['escalated'] else '자율'}",
        f"신뢰도 combined {c.get('combined')}   intrinsic {c.get('intrinsic')}   empirical {c.get('empirical')}",
        f"SLA {'충족' if r['sla_met'] else '위반' if r['sla_met'] is False else '—'}"
        + (f"   위반 슬라이스 {[SLICE_TYPE[k] for k, v in r['violations'].items() if v]}" if r["sla_met"] is False else ""),
        f"a* 거리 적용 {r.get('d_applied', float('nan')):.3f}   요청 {r.get('d_requested', float('nan')):.3f}"
        f"   다음 수요 압력 {r.get('pressure_next', float('nan')):.2f}",
        "보정량 " + (", ".join(f"{SLICE_TYPE[k]} {v:+.3f}" for k, v in r["correction"].items()) if r["correction"] else "없음"),
        "조달 " + (f"{r['slice_id']} · {r['vendor_id']} · 비용 {r['cost']:.0f}" if r["slice_id"] else "없음"),
    ]
    if r.get("instant_violations") is not None and r["sla_met"] is False:
        lines.append("평활 없이 곧바로 적용됐다면: " + ("충족 → 지연(평활) 탓" if not any(r["instant_violations"].values())
                                               else "그래도 위반"))
    if r["shadow"]:
        lines.append(f"가상 채점(제안대로였다면) {'충족' if r['shadow'].get('sla_met') else '위반'}")
    ax5.axis("off")
    ax5.set_facecolor(SIT_COLOR.get(r["truth"], "#ffffff"))
    ax5.text(0.01, 0.98, "\n".join(lines), va="top", ha="left", fontsize=11, transform=ax5.transAxes,
             bbox=dict(boxstyle="round", facecolor=SIT_COLOR.get(r["truth"], "#ffffff"), alpha=0.9))
    ax5.set_title("MCP 판단 · 실행")
    fig.suptitle(f"{run['folder'].name} — step {r['step']}", fontsize=13)
    fig.tight_layout()
    fig.savefig(out / f"state_{r['step']:03d}.png", dpi=80)
    plt.close(fig)


def render_orchestration(run: dict, out: Path, plt) -> None:
    rows = [r for r in run["rows"] if r.get("ideal")]
    steps = [r["step"] for r in rows]
    fig, axes = plt.subplots(5, 1, figsize=(15, 13), sharex=True,
                             gridspec_kw={"height_ratios": [1, 1, 1, 0.7, 0.8]})

    def shade(ax):
        for r in run["rows"]:
            ax.axvspan(r["step"] - 0.5, r["step"] + 0.5, color=SIT_COLOR[r["truth"]], zorder=0, lw=0)
            if r["escalated"]:
                ax.axvspan(r["step"] - 0.5, r["step"] + 0.5, ymin=0.92, ymax=1.0, color="#7d3c98", zorder=1, lw=0)

    for ax, k in zip(axes[:3], SLICE_KEYS):
        shade(ax)
        ax.plot(steps, [r["applied"][k] for r in rows], color=SLICE_COLOR[k], lw=2, label="적용")
        ax.plot(steps, [_norm(r["requested"])[k] if r["requested"] else None for r in rows],
                color=SLICE_COLOR[k], lw=1, ls=":", label="요청")
        ax.plot(steps, [r["ideal"][k] for r in rows], color="#e67e22", lw=1.5, ls="--", label="필요 a*")
        vx = [r["step"] for r in rows if r["violations"].get(k)]
        ax.scatter(vx, [0.02] * len(vx), marker="x", color="black", s=18, label="위반")
        px = [r["step"] for r in rows if r["slice_id"] and k in r["slice_id"]]
        ax.scatter(px, [0.95] * len(px), marker="v", color="black", s=40, label="조달")
        ax.set_ylim(0, 1)
        ax.set_ylabel(SLICE_TYPE[k])
        ax.legend(loc="upper right", fontsize=7, ncol=5)
    axes[0].set_title("배분 — 배경색 = 정답 상황(빨강 emergency · 파랑 special_event · 초록 iot_surge) · 위쪽 보라 띠 = 개입")

    ax = axes[3]
    shade(ax)
    ax.bar(steps, [1 if r["sla_met"] is False else 0 for r in rows], color="#c0392b", width=0.8, label="SLA 위반")
    ax.bar(steps, [-1 if (r["sla_met"] is False and r.get("instant_violations") is not None
                          and not any(r["instant_violations"].values())) else 0 for r in rows],
           color="#e67e22", width=0.8, label="평활만 없었으면 충족")
    ax.set_yticks([-1, 0, 1], ["지연", "", "위반"])
    ax.legend(loc="upper right", fontsize=7)

    ax = axes[4]
    shade(ax)
    ax.plot(steps, [r["confidence"].get("combined") for r in rows], color="black", label="combined")
    ax.plot(steps, [r["confidence"].get("empirical") for r in rows], color="#7d3c98", ls="--", label="empirical")
    ax.axhline(0.45, color="gray", ls=":", label="τ 0.45")
    ax.set_ylim(0, 1)
    ax.set_xlabel("step")
    ax.legend(loc="upper right", fontsize=7, ncol=3)
    fig.suptitle(f"{run['folder'].name} — 오케스트레이션 전체", fontsize=13)
    fig.tight_layout()
    fig.savefig(out / "orchestration.png", dpi=90)
    plt.close(fig)


# ── 리포트 ───────────────────────────────────────────────────────
def _mean(xs: list) -> Optional[float]:
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _f(x: Optional[float], nd: int = 3) -> str:
    return "—" if x is None else f"{x:.{nd}f}"


def report(run: dict) -> str:
    rows = run["rows"]
    scored = [r for r in rows if r["sla_met"] is not None]
    judged = [r for r in scored if r.get("ideal")]
    met = [r for r in judged if r["sla_met"]]
    viol = [r for r in judged if r["sla_met"] is False]
    cfg = run["config"]
    L = [f"# {run['folder'].name}", "",
         f"조건: scenario={cfg.get('scenario')} · seed={cfg.get('seed')} · arm={cfg.get('arm')} · driver={cfg.get('driver')}", "",
         f"스텝 {len(rows)} · SLA 충족 {sum(1 for r in scored if r['sla_met'])}/{len(scored)} · "
         f"개입 {sum(1 for r in rows if r['escalated'])} · 조달 {sum(1 for r in rows if r['slice_id'])} "
         f"(비용 {sum(r['cost'] for r in rows):.0f}) · 상황 판단 정확도 "
         f"{sum(1 for r in rows if r['situation'] == r['truth'])}/{len(rows)}", ""]

    # (a) a* 근사
    L += ["## (a) 필요 배분 a* 에 얼마나 맞췄나", "",
          "a* 는 다음 관측으로 계산한 '위반이 딱 없어지는 배분'. 거리 = L1/2 (0 = 같음).", "",
          "| | 스텝 | 적용 ↔ a* | 요청 ↔ a* |", "|---|---|---|---|",
          f"| SLA 충족 | {len(met)} | {_f(_mean([r['d_applied'] for r in met]))} | {_f(_mean([r.get('d_requested') for r in met]))} |",
          f"| SLA 위반 | {len(viol)} | {_f(_mean([r['d_applied'] for r in viol]))} | {_f(_mean([r.get('d_requested') for r in viol]))} |", ""]
    lag = [r for r in viol if r.get("instant_violations") is not None and not any(r["instant_violations"].values())]
    struct = [r for r in viol if r.get("pressure_next", 0) > 1.0]
    other = [r for r in viol if r not in lag and r not in struct]
    L += ["**위반의 원인 (지연 분석)**", "",
          f"- 어떤 배분으로도 불가능 (다음 수요 압력 > 1.0): **{len(struct)}** 스텝",
          f"- 평활만 없었으면 충족 — 요청은 맞았는데 늦게 따라감: **{len(lag)}** 스텝 {[r['step'] for r in lag] or ''}",
          f"- 요청한 배분 자체가 부족 — 목표가 틀림: **{len(other)}** 스텝 {[r['step'] for r in other] or ''}", ""]
    saved = [r for r in met if r.get("instant_violations") is not None and any(r["instant_violations"].values())]
    L += [f"- 반대로 **평활 덕에 충족** — 요청대로 곧바로 갔으면 위반이었을 스텝: **{len(saved)}** "
          f"{[r['step'] for r in saved] or ''} (평활은 늦게 따라가게도 하지만 잘못된 요청을 완충하기도 한다)", ""]

    # (b) 오류 · 종료
    L += ["## (b) 오류 · 종료", ""]
    if run["calls"]:
        bad = [c for c in run["calls"] if c.get("refused") or c.get("value_error") or not c.get("ok")]
        why = Counter((c.get("value_error") or c.get("error") or ("refused: " + str((c.get("result") or {}).get("error")))
                       )[:160] for c in bad)
        L += [f"- 도구 호출 {len(run['calls'])}회 중 실패 · 거부 **{len(bad)}**회"]
        for msg, n in why.most_common():
            L += [f"  - {n}회 — `{msg}`"]
        vc = Counter(v["code"] for r in run["refs"] for v in r["violations"])
        L += [f"- 심판 위반: {dict(vc) or '없음'} · 오류 스텝 {sum(1 for r in run['refs'] if any(v['severity'] == 'error' for v in r['violations']))}",
              f"- 기준 미달 정책을 두고 다른 정책으로 전환(D6): {[r['step'] for r in run['refs'] if r.get('switched_under_threshold')] or '없음'}",
              f"- LLM 실패 {sum(1 for s in run['osteps'] if s.get('llm_error'))} · 형식 위반 {sum(1 for s in run['osteps'] if s.get('malformed'))}"
              f" · 시도 {len(run['osteps'])} (스텝 {len({s['step'] for s in run['osteps']})})"]
        last = run["refs"][-1] if run["refs"] else {}
        L += [f"- 종료: 마지막 시도의 호출 끝 `{(last.get('order') or [])[-3:]}` · episode_done {last.get('episode_done')}"]
    else:
        L += ["- 고정 루프 실행 — 순서는 파이썬이 보장한다. 도구가 값으로 거부하면 루프가 즉시 멈추므로(ToolRefused) "
              "끝까지 기록이 있으면 오류 0이다."]
    expected = len(_jsonl(run["folder"] / "truth.jsonl"))
    L += [f"- 기록된 스텝 {len(rows)} / 정답 파일 스텝 {expected}", ""]

    # (c) emergency
    em = [r for r in judged if r["truth"] == "emergency"]
    L += ["## (c) emergency 긴급 배분 (URLLC)", ""]
    if not em:
        L += ["정답이 emergency 인 스텝이 없다.", ""]
    else:
        u = lambda xs, key: _mean([x[key]["urllc"] for x in xs if x.get(key)])   # noqa: E731
        lag_u = [r for r in em if r["violations"].get("urllc") and r.get("instant_violations") is not None
                 and not r["instant_violations"]["urllc"]]
        L += [f"| emergency {len(em)} 스텝 | URLLC 몫 |", "|---|---|",
              f"| 요청 평균 | {_f(_mean([_norm(r['requested'])['urllc'] for r in em if r['requested']]))} |",
              f"| 적용 평균 | {_f(u(em, 'applied'))} |",
              f"| 필요 a* 평균 | {_f(u(em, 'ideal'))} |", "",
              f"- URLLC 위반 **{sum(1 for r in em if r['violations'].get('urllc'))}/{len(em)}** · "
              f"그중 평활만 없었으면 URLLC 충족: **{len(lag_u)}**",
              f"- emergency 중 조달: {Counter(r['slice_id'].split('-')[1] for r in em if r['slice_id']) or '없음'}",
              f"- 판단한 상황: {dict(Counter(r['situation'] for r in em))}"]
        # 전환 직후 반응 — emergency 가 시작되고 적용 URLLC 가 필요량의 90% 에 닿기까지
        onsets = [i for i, r in enumerate(run["rows"]) if r["truth"] == "emergency"
                  and (i == 0 or run["rows"][i - 1]["truth"] != "emergency")]
        for i in onsets:
            reach = next((run["rows"][j]["step"] for j in range(i, len(run["rows"]))
                          if run["rows"][j]["truth"] == "emergency" and run["rows"][j].get("ideal")
                          and run["rows"][j]["applied"]["urllc"] >= 0.9 * run["rows"][j]["ideal"]["urllc"]), None)
            start = run["rows"][i]["step"]
            L += [f"- emergency 시작 스텝 {start} → 적용 URLLC 가 필요량 90% 에 닿은 스텝 "
                  f"{reach if reach is not None else '끝까지 못 닿음'}"
                  + (f" ({reach - start}스텝 걸림)" if reach is not None else "")]
        L += [""]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("run", help="실행 폴더 (decisions.json 이 있는 곳)")
    ap.add_argument("--out", default=None, help="출력 폴더 (기본 <실행 폴더>/viz)")
    ap.add_argument("--no-steps", action="store_true", help="스텝별 state_XXX.png 를 안 만든다")
    ap.add_argument("--every", type=int, default=1, help="스텝별 그림을 N스텝마다")
    args = ap.parse_args()
    folder = Path(args.run) if Path(args.run).is_absolute() else ROOT / args.run
    run = load_run(folder)
    out = Path(args.out) if args.out else folder / "viz"
    out.mkdir(parents=True, exist_ok=True)
    text = report(run)
    (out / "report.md").write_text(text, encoding="utf-8")
    plt = _mpl()
    render_orchestration(run, out, plt)
    n = 0
    if not args.no_steps:
        for i in range(0, len(run["rows"]), max(1, args.every)):
            render_state(run, i, out, plt)
            n += 1
    print(text)
    print(f"\n→ {out}  (orchestration.png · state_XXX.png {n}장 · report.md)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
