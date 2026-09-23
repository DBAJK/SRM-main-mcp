"""실행 리포트 — `runs/{run_id}/` 를 읽어 한 장의 HTML 로 그린다. (오프라인 · 의존성 없음)

    python -m eval.report {run_id}          → runs/{run_id}/report.html

정답(`truth.jsonl`)을 읽으므로 **에이전트 컨텍스트 밖**에서만 돈다 — `eval/score.py` 와
같은 자리다. 두 드라이버 모두 읽을 수 있고, 오케스트레이터 산출물(`orchestrator/`)이
있으면 도구 호출 · 절차 위반 · 비용 절도 함께 그린다.

무엇을 보여주나
  KPI 타일      개입 · SLA 위반 · 조달 · 인지 정확도 · 절차 준수 · 비용
  타임라인      스텝별 정답 상황 / LLM 판단 / 일치 / SLA / 개입 / 조달  (색 + 글자, 색만으로 안 읽음)
  신뢰도 추이   combined · intrinsic · empirical 선 + 임계 0.45 점선 + 개입 표식
  도구 호출     스텝별 완료/실패 호출 막대 + 절차 위반 수         (오케스트레이터만)
  혼동 행렬 · 조달 내역 · 스텝 상세 표(근거 문장 포함)

차트는 파이썬이 만든 인라인 SVG 다. 라이브러리도 네트워크도 필요 없다.
"""
from __future__ import annotations

import html
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval.score import (  # noqa: E402
    load_decisions, load_truth, perception_accuracy, transition_steps, truth_situation,
)
from srm_mcp.common import paths  # noqa: E402

THRESHOLD = 0.45   # agent/schema.py ESCALATION_THRESHOLD
SITUATIONS = ("normal", "emergency", "special_event", "iot_surge")
LETTER = {"normal": "–", "emergency": "E", "special_event": "S", "iot_surge": "I"}
KO = {"normal": "평시", "emergency": "긴급", "special_event": "행사", "iot_surge": "IoT 급증"}


# ── 데이터 ─────────────────────────────────────────────────────
def load_run(run_id: str) -> dict:
    rd = paths.run_dir(run_id)
    book = load_decisions(run_id)
    decisions = book["decisions"]

    truth_by_step: dict[int, str] = {}
    excluded: set[int] = set()
    if (rd / "truth.jsonl").exists():
        rows = load_truth(run_id)
        truth_by_step = {int(r["step"]): truth_situation(r) for r in rows}
        excluded = transition_steps(rows)

    orch: dict[int, dict] = {}
    summary: Optional[dict] = None
    od = rd / "orchestrator"
    if (od / "steps.jsonl").exists():
        for line in open(od / "steps.jsonl", encoding="utf-8"):
            if line.strip():
                r = json.loads(line)
                orch[int(r["step"])] = r
    if (od / "summary.json").exists():
        summary = json.loads((od / "summary.json").read_text(encoding="utf-8"))
    cands = load_candidates(od / "calls.jsonl") if (od / "calls.jsonl").exists() else {}

    steps: dict[int, dict] = {}
    for r in decisions:
        s = int(r["step"])
        row = steps.setdefault(s, {"step": s, "escalated": False})
        if r.get("kind") == "escalation":
            row["escalated"] = True
            row["escalation_reason"] = r.get("reason")
        else:
            row["decision"] = r
        if r.get("vendor_id"):
            row["procure"] = {"vendor_id": r.get("vendor_id"), "slice_id": r.get("slice_id"),
                              "cost_total": r.get("cost_total")}

    out = []
    for s in sorted(steps):
        row = steps[s]
        d = row.get("decision") or {}
        conf = d.get("confidence") or {}
        outcome = d.get("outcome") or {}
        o = orch.get(s) or {}
        v = o.get("verdict") or {}
        out.append({
            "step": s,
            "truth": truth_by_step.get(s),
            "excluded": s in excluded,
            "situation": d.get("situation"),
            "policy": d.get("chosen_policy"),
            "agent_policy": d.get("agent_policy"),
            "conf_situation": conf.get("situation"),
            "intrinsic": conf.get("intrinsic"),
            "empirical": conf.get("empirical"),
            "combined": conf.get("combined"),
            "sla_met": outcome.get("sla_met"),
            "error": outcome.get("error"),
            "violations_obs": outcome.get("observed_violations"),
            "escalated": row["escalated"],
            "escalation_reason": row.get("escalation_reason"),
            "procure": row.get("procure"),
            "rationale": d.get("rationale"),
            # 오케스트레이터
            "calls": v.get("calls"),
            "failed_calls": v.get("failed_calls"),
            "procedure": v.get("violations") or [],
            "order": v.get("order") or [],
            "turns": o.get("turns"),
            "cost_usd": o.get("cost_usd"),
            "elapsed": o.get("elapsed"),
            "reasoning": (o.get("answer") or {}).get("reasoning"),
            "situation_scores": (o.get("answer") or {}).get("situation_scores"),
            "malformed": o.get("malformed"),
            "llm_error": o.get("llm_error"),
            "cand": cands.get(s, {}),
        })

    return {
        "run_id": run_id,
        "config": book.get("config") or {},
        "steps": out,
        "truth_by_step": truth_by_step,
        "excluded": excluded,
        "decisions": decisions,
        "summary": summary,
        "has_truth": bool(truth_by_step),
        "has_orch": bool(orch),
    }


def load_candidates(path: Path) -> dict[int, dict]:
    """`calls.jsonl` 에서 스텝별 **후보와 그 값**을 꺼낸다.

    LLM 이 무엇을 놓고 골랐는지는 도구 반환값에 있다 — 정책별 confidence 는 ②,
    정책별 성적은 ⑤, 벤더 점수는 ③. 같은 도구를 여러 번 불렀으면 마지막 값을 쓴다
    (재시도 뒤의 것이 판단에 쓰인 값이다).
    """
    out: dict[int, dict] = {}
    for line in open(path, encoding="utf-8"):
        if not line.strip():
            continue
        e = json.loads(line)
        if not e.get("ok") or e.get("refused") or e.get("value_error"):
            continue
        s = int(e["step"]) if e.get("step") is not None else None
        if s is None:
            continue
        c = out.setdefault(s, {"policies": {}, "offerings": None, "procured": None,
                               "reliability": None, "demand": None, "situations_tried": []})
        t, r = e["tool"], e.get("result")
        if t == "get_reliability_table" and isinstance(r, dict):
            c["reliability"] = r
        elif t == "propose_allocation" and isinstance(r, dict):
            c["policies"][r.get("policy")] = r
            sit = (e.get("args") or {}).get("situation")
            if sit and sit not in c["situations_tried"]:
                c["situations_tried"].append(sit)
        elif t == "compare_policies" and isinstance(r, list):
            for p in r:
                if isinstance(p, dict):
                    c["policies"][p.get("policy")] = p
        elif t == "score_offerings" and isinstance(r, list):
            c["offerings"] = r
        elif t == "procure" and isinstance(r, dict) and r.get("vendor_id"):
            c["procured"] = r.get("vendor_id")
        elif t == "classify_demand" and isinstance(r, dict) and r.get("available"):
            c["demand"] = r
    return out


# ── 집계 ─────────────────────────────────────────────────────
def kpis(run: dict) -> dict:
    st = run["steps"]
    n = len(st)
    esc = sum(1 for r in st if r["escalated"])
    scored = [r for r in st if r["sla_met"] is not None]
    viol = sum(1 for r in scored if r["sla_met"] is False)
    proc = [r for r in st if r["procure"]]
    cost = sum(float(r["procure"]["cost_total"] or 0) for r in proc)
    k = {
        "steps": n, "escalations": esc,
        "autonomy": (1 - esc / n) if n else None,
        "sla_violations": viol, "sla_rate": (viol / len(scored)) if scored else None,
        "procurements": len(proc), "cost": cost,
    }
    if run["has_truth"]:
        pa = perception_accuracy(run["decisions"], run["truth_by_step"], run["excluded"])
        k["accuracy"] = pa["accuracy"]
        k["accuracy_n"] = pa["n"]
        k["confusion"] = pa["confusion"]
    if run["has_orch"]:
        clean = sum(1 for r in st if r["calls"] is not None and not r["procedure"])
        judged = sum(1 for r in st if r["calls"] is not None)
        k["adherence"] = (clean / judged) if judged else None
        k["clean"] = clean
        k["judged"] = judged
        k["llm_cost"] = sum(float(r["cost_usd"] or 0) for r in st)
        k["mean_calls"] = (sum(r["calls"] or 0 for r in st) / judged) if judged else None
        k["mean_elapsed"] = (sum(r["elapsed"] or 0 for r in st) / judged) if judged else None
    return k


# ── SVG 도우미 ───────────────────────────────────────────────
def _tick(n: int) -> int:
    """x축 눈금 간격. 스텝 수에 맞춰 1 · 5 · 10."""
    return 1 if n <= 12 else (5 if n <= 60 else 10)


def esc(s: Any) -> str:
    return html.escape("" if s is None else str(s), quote=True)


def fmt(v: Any, nd: int = 2, pct: bool = False) -> str:
    if v is None:
        return "–"
    if isinstance(v, bool):
        return "예" if v else "아니오"
    if isinstance(v, (int,)) and not pct:
        return f"{v:,}"
    try:
        x = float(v)
    except (TypeError, ValueError):
        # LLM 이 숫자 자리에 문자열을 넣은 경우가 있다 (confidence.situation 에 상황 이름).
        # 리포트는 그걸 그대로 보여 주는 게 맞다 — 고쳐 주면 형식 위반이 감춰진다.
        return str(v)
    return f"{x * 100:.1f}%" if pct else f"{x:.{nd}f}"


def timeline_svg(run: dict) -> str:
    st = run["steps"]
    n = len(st)
    if n == 0:
        return ""
    label_w, cell_h, gap = 84, 22, 2
    width = 1000
    cw = max(4, min(28, (width - label_w) // max(n, 1)))
    rows = [("정답 상황", "truth"), ("판단 상황", "situation"), ("일치", "match"),
            ("SLA", "sla"), ("개입", "esc"), ("조달", "proc")]
    if not run["has_truth"]:
        rows = [r for r in rows if r[1] not in ("truth", "match")]
    h = len(rows) * (cell_h + gap) + 28
    vbw = label_w + cw * n + 8
    # 스텝이 적을 때 100% 폭으로 늘리면 셀이 거대해진다. 실제 픽셀 폭을 주고 넘칠 때만 줄인다.
    out = [f'<svg class="viz" viewBox="0 0 {vbw} {h}" width="{vbw}" style="max-width:100%" '
           f'role="img" aria-label="스텝 타임라인">']
    for ri, (label, key) in enumerate(rows):
        y = ri * (cell_h + gap)
        out.append(f'<text x="{label_w - 8}" y="{y + cell_h / 2 + 4}" text-anchor="end" '
                   f'class="lbl">{esc(label)}</text>')
        for i, r in enumerate(st):
            x = label_w + i * cw
            cls, letter, tip = _cell(key, r)
            out.append(
                f'<rect x="{x}" y="{y}" width="{cw - 1}" height="{cell_h}" rx="3" class="cell {cls}" '
                f'data-tip="{esc(tip)}"/>')
            if cw >= 12 and letter:
                out.append(f'<text x="{x + (cw - 1) / 2}" y="{y + cell_h / 2 + 4}" text-anchor="middle" '
                           f'class="cell-txt">{esc(letter)}</text>')
    # x축 (10스텝마다)
    ya = len(rows) * (cell_h + gap) + 14
    for i in range(0, n, _tick(n)):
        out.append(f'<text x="{label_w + i * cw + 2}" y="{ya}" class="tick">{i}</text>')
    out.append("</svg>")
    return "".join(out)


def _cell(key: str, r: dict) -> tuple[str, str, str]:
    s = r["step"]
    if key == "truth":
        t = r["truth"]
        return f"sit-{t}", LETTER.get(t, "?"), f"step {s} · 정답 {KO.get(t, t)}" + (" (전환 스텝, 채점 제외)" if r["excluded"] else "")
    if key == "situation":
        t = r["situation"]
        tip = f"step {s} · 판단 {KO.get(t, t)} · 확신 {fmt(r['conf_situation'])}"
        return f"sit-{t}", LETTER.get(t, "?"), tip
    if key == "match":
        if r["excluded"]:
            return "neutral", "·", f"step {s} · 전환 스텝 — 채점 제외"
        ok = r["situation"] == r["truth"]
        return ("good" if ok else "bad"), ("✓" if ok else "✗"), \
            f"step {s} · {'일치' if ok else '불일치'}: 정답 {KO.get(r['truth'])} / 판단 {KO.get(r['situation'])}"
    if key == "sla":
        if r["sla_met"] is None:
            return "neutral", "", f"step {s} · 채점 없음 (마지막 스텝 또는 보고 누락)"
        v = r["violations_obs"] or {}
        bad = [k for k, b in v.items() if b]
        return ("good" if r["sla_met"] else "bad"), ("✓" if r["sla_met"] else "✗"), \
            f"step {s} · SLA {'충족' if r['sla_met'] else '위반: ' + ', '.join(bad)} · 오차 {fmt(r['error'], 3)}"
    if key == "esc":
        if r["escalated"]:
            return "warn", "!", f"step {s} · 사람 호출 · {r.get('escalation_reason') or ''}"
        return "empty", "", f"step {s} · 자율 처리 (combined {fmt(r['combined'], 3)})"
    if key == "proc":
        p = r["procure"]
        if p:
            return "proc", "$", f"step {s} · 조달 {p['vendor_id']} · {p['slice_id']} · 비용 {fmt(p['cost_total'], 1)}"
        return "empty", "", f"step {s} · 조달 없음"
    return "neutral", "", ""


def confidence_svg(run: dict) -> str:
    st = [r for r in run["steps"] if r["combined"] is not None]
    if not st:
        return ""
    W, H, ml, mr, mt, mb = 1000, 260, 44, 90, 16, 28
    pw, ph = W - ml - mr, H - mt - mb
    n = len(run["steps"])
    xs = lambda i: ml + (i / max(n - 1, 1)) * pw          # noqa: E731
    ys = lambda v: mt + (1 - max(0.0, min(1.0, float(v)))) * ph  # noqa: E731

    out = [f'<svg class="viz" viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="신뢰도 추이" '
           f'data-chart="line" data-n="{n}" data-ml="{ml}" data-pw="{pw}">']
    for g in (0.0, 0.25, 0.5, 0.75, 1.0):
        out.append(f'<line x1="{ml}" x2="{ml + pw}" y1="{ys(g)}" y2="{ys(g)}" class="grid"/>')
        out.append(f'<text x="{ml - 6}" y="{ys(g) + 4}" text-anchor="end" class="tick">{g:.2f}</text>')
    out.append(f'<line x1="{ml}" x2="{ml + pw}" y1="{ys(THRESHOLD)}" y2="{ys(THRESHOLD)}" class="thr"/>')

    series = [("combined", "결합", "s1"), ("intrinsic", "intrinsic", "s2"), ("empirical", "empirical", "s3")]
    end_labels: list[tuple[float, str]] = [(ys(THRESHOLD), f"임계 {THRESHOLD}")]
    for key, name, cls in series:
        pts = [(xs(r["step"]), ys(r[key])) for r in st if r.get(key) is not None]
        if not pts:
            continue
        d = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(pts))
        out.append(f'<path d="{d}" class="line {cls}"/>')
        end_labels.append((pts[-1][1], name))
    # 끝 라벨이 겹치지 않게 12px 간격으로 밀어낸다 (값이 비슷하면 반드시 겹친다)
    end_labels.sort()
    placed: list[float] = []
    for y, _ in end_labels:
        y_adj = y if not placed else max(y, placed[-1] + 12)
        placed.append(y_adj)
    for (y, name), y_adj in zip(end_labels, placed):
        out.append(f'<text x="{ml + pw + 8}" y="{y_adj + 4}" class="lbl">{esc(name)}</text>')
    # 개입 표식
    for r in run["steps"]:
        if r["escalated"] and r["combined"] is not None:
            x, y = xs(r["step"]), ys(r["combined"])
            out.append(f'<path d="M{x},{y - 9} L{x + 6},{y + 1} L{x - 6},{y + 1} Z" class="mark-warn" '
                       f'data-tip="step {r["step"]} · 사람 호출 · combined {fmt(r["combined"], 3)}"/>')
    # x축
    for i in range(0, n, _tick(n)):
        out.append(f'<text x="{xs(i)}" y="{H - 8}" text-anchor="middle" class="tick">{i}</text>')
    # 크로스헤어 + 히트 영역 (JS)
    out.append(f'<line class="xhair" x1="0" x2="0" y1="{mt}" y2="{mt + ph}" style="display:none"/>')
    for r in run["steps"]:
        i = r["step"]
        tip = (f"step {i} · 결합 {fmt(r['combined'], 3)} · intrinsic {fmt(r['intrinsic'], 3)} · "
               f"empirical {fmt(r['empirical'], 3)} · 판단 {KO.get(r['situation'], r['situation'])}"
               + (" · 사람 호출" if r["escalated"] else ""))
        half = pw / max(n - 1, 1) / 2
        out.append(f'<rect x="{xs(i) - half}" y="{mt}" width="{2 * half}" height="{ph}" class="hit" '
                   f'data-tip="{esc(tip)}" data-x="{xs(i):.1f}"/>')
    out.append("</svg>")
    return "".join(out)


def calls_svg(run: dict) -> str:
    st = [r for r in run["steps"] if r["calls"] is not None]
    if not st:
        return ""
    n = len(run["steps"])
    W, H, ml, mr, mt, mb = 1000, 200, 44, 16, 16, 28
    pw, ph = W - ml - mr, H - mt - mb
    vmax = max(max(r["calls"] for r in st), 1)
    bw = pw / max(n, 1)
    out = [f'<svg class="viz" viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="도구 호출">']
    for g in range(0, vmax + 1, max(1, vmax // 4)):
        y = mt + (1 - g / vmax) * ph
        out.append(f'<line x1="{ml}" x2="{ml + pw}" y1="{y}" y2="{y}" class="grid"/>')
        out.append(f'<text x="{ml - 6}" y="{y + 4}" text-anchor="end" class="tick">{g}</text>')
    for r in st:
        i = r["step"]
        w = max(2, min(bw - 2, 40))          # 스텝이 적어도 막대가 판을 덮지 않게 상한
        x = ml + i * bw + (bw - w) / 2
        ok = (r["calls"] or 0) - (r["failed_calls"] or 0)
        fail = r["failed_calls"] or 0
        y0 = mt + ph
        h_ok = ok / vmax * ph
        h_f = fail / vmax * ph
        codes = ", ".join(x["code"] for x in r["procedure"]) or "없음"
        tip = (f"step {i} · 호출 {r['calls']} (실패 {fail}) · 턴 {r['turns']} · "
               f"{fmt(r['elapsed'], 0)}초 · ${fmt(r['cost_usd'], 3)} · 위반: {codes}")
        out.append(f'<rect x="{x}" y="{y0 - h_ok}" width="{w}" height="{h_ok}" rx="3" class="bar s1" data-tip="{esc(tip)}"/>')
        if fail:
            out.append(f'<rect x="{x}" y="{y0 - h_ok - h_f - 2}" width="{w}" height="{h_f}" rx="3" class="bar serious" data-tip="{esc(tip)}"/>')
        if r["procedure"]:
            out.append(f'<text x="{x + w / 2}" y="{y0 - h_ok - h_f - 8}" text-anchor="middle" class="viol">'
                       f'{len(r["procedure"])}</text>')
    for i in range(0, n, _tick(n)):
        out.append(f'<text x="{ml + i * bw + bw / 2}" y="{H - 8}" text-anchor="middle" class="tick">{i}</text>')
    out.append("</svg>")
    return "".join(out)


# ── HTML ─────────────────────────────────────────────────────
def tile(label: str, value: str, sub: str = "", tone: str = "") -> str:
    return (f'<div class="tile {tone}"><div class="t-label">{esc(label)}</div>'
            f'<div class="t-value">{esc(value)}</div><div class="t-sub">{esc(sub)}</div></div>')


def confusion_table(conf: dict) -> str:
    if not conf:
        return "<p class='muted'>정답 파일이 없어 계산하지 않았다.</p>"
    preds = [s for s in SITUATIONS]
    rows = [f"<tr><th>정답 \\ 판단</th>{''.join(f'<th>{KO[p]}</th>' for p in preds)}</tr>"]
    for t in SITUATIONS:
        if t not in conf:
            continue
        cells = []
        for p in preds:
            v = conf[t].get(p, 0)
            cls = "good" if (p == t and v) else ("bad" if v else "")
            cells.append(f'<td class="num {cls}">{v or ""}</td>')
        rows.append(f"<tr><th>{KO[t]}</th>{''.join(cells)}</tr>")
    return f"<table class='mini'>{''.join(rows)}</table>"


def steps_table(run: dict) -> str:
    st = run["steps"]
    has_t, has_o = run["has_truth"], run["has_orch"]
    head = ["스텝"] + (["정답"] if has_t else []) + ["판단", "확신", "정책", "결합", "SLA", "개입", "조달"] \
        + (["호출/실패", "위반", "$"] if has_o else []) + ["근거"]
    rows = [f"<tr>{''.join(f'<th>{h}</th>' for h in head)}</tr>"]
    for r in st:
        p = r["procure"]
        cells = [f"<td class='num'>{r['step']}</td>"]
        if has_t:
            cells.append(f"<td class='sit-{r['truth']} swatch'>{KO.get(r['truth'], '–')}</td>")
        match_cls = "" if not has_t or r["excluded"] else ("good" if r["situation"] == r["truth"] else "bad")
        cells += [
            f"<td class='sit-{r['situation']} swatch {match_cls}'>{KO.get(r['situation'], r['situation'] or '–')}</td>",
            f"<td class='num'>{fmt(r['conf_situation'])}</td>",
            f"<td>{esc(r['policy'])}</td>",
            f"<td class='num'>{fmt(r['combined'], 3)}</td>",
            f"<td class='{'good' if r['sla_met'] else ('bad' if r['sla_met'] is False else '')}'>"
            f"{'✓' if r['sla_met'] else ('✗' if r['sla_met'] is False else '–')}</td>",
            f"<td class='{'warn' if r['escalated'] else ''}'>{'! 호출' if r['escalated'] else ''}</td>",
            f"<td>{esc(p['vendor_id']) + ' · ' + fmt(p['cost_total'], 0) if p else ''}</td>",
        ]
        if has_o:
            cells += [
                f"<td class='num'>{r['calls'] if r['calls'] is not None else '–'}"
                f"{'/' + str(r['failed_calls']) if r['failed_calls'] else ''}</td>",
                f"<td class='{'bad' if r['procedure'] else ''}'>{esc(', '.join(x['code'] for x in r['procedure']))}</td>",
                f"<td class='num'>{fmt(r['cost_usd'], 3)}</td>",
            ]
        cells.append(f"<td class='why'>{esc(r['reasoning'] or r['rationale'])}</td>")
        rows.append(f"<tr>{''.join(cells)}</tr>")
    return f"<table class='detail'>{''.join(rows)}</table>"


def _bars(rows: list[tuple[str, Optional[float], bool, str]], vmax: float = 1.0) -> str:
    """가로 막대 목록. rows = (이름, 값, 선택됨?, 덧말). 값이 None 이면 빈 막대에 덧말만."""
    out = ['<div class="bars">']
    for name, v, chosen, note in rows:
        pct = 0 if v is None else max(0.0, min(1.0, float(v) / vmax)) * 100
        out.append(
            f'<div class="bar-row{" chosen" if chosen else ""}">'
            f'<span class="bar-name">{esc(name)}</span>'
            f'<span class="bar-track"><span class="bar-fill" style="width:{pct:.1f}%"></span></span>'
            f'<span class="bar-val">{"–" if v is None else fmt(v, 2)}</span>'
            f'<span class="bar-note">{"✓ 선택" if chosen else ""}{(" · " if chosen and note else "") + esc(note) if note else ""}</span>'
            f'</div>')
    out.append("</div>")
    return "".join(out)


def candidates_section(run: dict) -> str:
    """스텝마다 '무엇을 놓고, 어떤 값으로, 무엇을 골랐나'. 오케스트레이터 실행에서만 채워진다."""
    st = run["steps"]
    cards = []
    for r in st:
        c = r.get("cand") or {}
        groups = []

        # 1) 상황 — LLM 이 낸 네 상황의 비율
        ss = r.get("situation_scores")
        if isinstance(ss, dict):
            rows = [(KO[s], ss.get(s), s == r["situation"], "") for s in SITUATIONS]
            note = ""
            if r["truth"] is not None:
                note = f"정답 {KO.get(r['truth'])}" + (" · 전환 스텝" if r["excluded"] else "")
            groups.append(("상황 비율", rows, note))
        elif c.get("situations_tried"):
            groups.append(("정찰한 상황", [(KO.get(s, s), None, s == r["situation"], "") for s in c["situations_tried"]],
                           "②에 물어본 상황들"))

        # 2) 정책 — ②의 confidence · ⑤의 effective
        pol = c.get("policies") or {}
        rel = c.get("reliability") or {}
        names = [p for p in ("rule_based", "lstm_forecast", "dqn") if p in pol or p in rel]
        if names:
            rows = []
            for p in names:
                pr = pol.get(p) or {}
                conf = pr.get("confidence")
                eff = (rel.get(p) or {}).get("effective")
                n = (rel.get(p) or {}).get("n")
                status = pr.get("status")
                note = (f"성적 {fmt(eff)} (n={n})" if eff is not None else "") + \
                       (f" · {status}" if status and status != "ok" else "")
                rows.append((p, conf if conf is not None else eff, p == r["policy"], note))
            groups.append(("정책 (②의 확신)", rows, "막대 = intrinsic confidence · 덧말 = ⑤ 성적"))

        # 3) 벤더 — ③의 점수
        offers = c.get("offerings")
        if offers:
            top = sorted(offers, key=lambda o: -float(o.get("score", 0)))[:5]
            rows = [(f"{o.get('vendor_id')} {o.get('name', '')}".strip(), float(o.get("score", 0)) / 100,
                     o.get("vendor_id") == c.get("procured"),
                     f"평점 {o.get('rating')} · 비용 {o.get('cost')}") for o in top]
            groups.append(("벤더 (③ 점수/100)", rows,
                           "조달함" if c.get("procured") else "점수만 보고 조달하지 않음"))

        # 4) 수요 분류기
        dm = c.get("demand")
        if dm and dm.get("probabilities"):
            rows = [(k, v, k == dm.get("dominant"), "") for k, v in dm["probabilities"].items()]
            groups.append(("수요 분류기 (②)", rows, f"margin {fmt(dm.get('margin'))}"))

        if not groups:
            continue
        head = (f"스텝 {r['step']} · 판단 {KO.get(r['situation'], r['situation'])} / {r['policy']}"
                + (" · 사람 호출" if r["escalated"] else "") + (" · 조달" if r["procure"] else ""))
        body = "".join(f'<div class="grp"><div class="grp-title">{esc(t)}</div>{_bars(rows)}'
                       f'<div class="grp-note">{esc(note)}</div></div>' for t, rows, note in groups)
        cards.append(f'<div class="cand"><div class="cand-head">{esc(head)}</div><div class="grps">{body}</div></div>')

    if not cards:
        return "<p class='muted'>후보 정보가 없다 (오케스트레이터 실행에서만 기록된다).</p>"
    n = len(cards)
    inner = "".join(cards)
    if n > 12:
        return f"<details><summary>{n}스텝 · 펼치기/접기</summary>{inner}</details>"
    return inner


def procurement_table(run: dict) -> str:
    ps = [r for r in run["steps"] if r["procure"]]
    if not ps:
        return "<p class='muted'>조달이 없었다.</p>"
    rows = ["<tr><th>스텝</th><th>슬라이스</th><th>벤더</th><th>비용</th><th>그 스텝 SLA</th></tr>"]
    for r in ps:
        p = r["procure"]
        rows.append(f"<tr><td class='num'>{r['step']}</td><td>{esc(p['slice_id'])}</td>"
                    f"<td>{esc(p['vendor_id'])}</td><td class='num'>{fmt(p['cost_total'], 1)}</td>"
                    f"<td class='{'good' if r['sla_met'] else 'bad'}'>{'✓ 충족' if r['sla_met'] else '✗ 위반'}</td></tr>")
    return f"<table class='mini'>{''.join(rows)}</table>"


CSS = """
:root{color-scheme:light;
 --page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;--ring:rgba(11,11,11,.10);
 --s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--s7:#4a3aa7;
 --good:#0ca30c;--warn:#fab219;--serious:#ec835a;--bad:#d03b3b;--neutral:#e1e0d9;--empty:#f0efec;--celltxt:#fff}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){color-scheme:dark;
 --page:#0d0d0d;--surface:#1a1a19;--ink:#fff;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);
 --s1:#3987e5;--s2:#d95926;--s3:#199e70;--s7:#9085e9;--neutral:#383835;--empty:#242423;--celltxt:#fff}}
:root[data-theme=dark]{color-scheme:dark;
 --page:#0d0d0d;--surface:#1a1a19;--ink:#fff;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);
 --s1:#3987e5;--s2:#d95926;--s3:#199e70;--s7:#9085e9;--neutral:#383835;--empty:#242423;--celltxt:#fff}
*{box-sizing:border-box}body{margin:0;background:var(--page);color:var(--ink);font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1080px;margin:0 auto;padding:24px 16px 48px}
h1{font-size:20px;margin:0 0 4px}h2{font-size:15px;margin:28px 0 8px;color:var(--ink2)}
.meta{color:var(--ink2);font-size:13px}.muted{color:var(--muted)}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-top:16px}
.tile{background:var(--surface);border:1px solid var(--ring);border-radius:10px;padding:12px 14px}
.t-label{font-size:12px;color:var(--ink2)}.t-value{font-size:24px;font-weight:600;margin:2px 0}.t-sub{font-size:12px;color:var(--muted)}
.tile.bad .t-value{color:var(--bad)}.tile.warn .t-value{color:#b47b00}.tile.good .t-value{color:#006300}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]) .tile.good .t-value{color:var(--good)}:root:not([data-theme=light]) .tile.warn .t-value{color:var(--warn)}}
.card{background:var(--surface);border:1px solid var(--ring);border-radius:10px;padding:12px 14px;overflow-x:auto}
.viz{display:block;max-width:100%}
.lbl{font-size:11px;fill:var(--ink2)}.tick{font-size:10px;fill:var(--muted)}
.grid{stroke:var(--grid);stroke-width:1}.thr{stroke:var(--muted);stroke-width:1.5;stroke-dasharray:4 4}
.line{fill:none;stroke-width:2;stroke-linejoin:round}.line.s1{stroke:var(--s1)}.line.s2{stroke:var(--s2)}.line.s3{stroke:var(--s3)}
.bar.s1{fill:var(--s1)}.bar.serious{fill:var(--serious)}.viol{font-size:10px;font-weight:600;fill:var(--bad)}
.mark-warn{fill:var(--warn);stroke:var(--surface);stroke-width:2}
.hit{fill:transparent}.xhair{stroke:var(--ink2);stroke-width:1;pointer-events:none}
.cell{stroke:var(--surface);stroke-width:1}.cell-txt{font-size:11px;font-weight:600;fill:var(--celltxt);pointer-events:none}
.sit-normal{fill:var(--axis)}.sit-emergency{fill:var(--s1)}.sit-special_event{fill:var(--s2)}.sit-iot_surge{fill:var(--s3)}.sit-None{fill:var(--empty)}
rect.good{fill:var(--good)}rect.bad{fill:var(--bad)}rect.warn{fill:var(--warn)}rect.proc{fill:var(--s7)}rect.neutral{fill:var(--neutral)}rect.empty{fill:var(--empty)}
.legend{display:flex;flex-wrap:wrap;gap:12px;font-size:12px;color:var(--ink2);margin-top:8px}
.legend span::before{content:"";display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:6px;vertical-align:-2px;background:var(--c)}
table{border-collapse:collapse;width:100%;font-size:12.5px}th,td{padding:5px 8px;border-bottom:1px solid var(--grid);text-align:left;vertical-align:top}
th{color:var(--ink2);font-weight:600;background:var(--surface);position:sticky;top:0;white-space:nowrap}
td:not(.why){white-space:nowrap}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
td.good{color:#006300}td.bad{color:var(--bad)}td.warn{color:#b47b00}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]) td.good{color:var(--good)}:root:not([data-theme=light]) td.warn{color:var(--warn)}}
td.swatch{border-left:4px solid var(--c,transparent)}
td.sit-normal{--c:var(--axis)}td.sit-emergency{--c:var(--s1)}td.sit-special_event{--c:var(--s2)}td.sit-iot_surge{--c:var(--s3)}
.detail td.why{max-width:460px;color:var(--ink2)}
.mini{width:auto}.mini td.num.good{background:color-mix(in srgb,var(--good) 18%,transparent)}.mini td.num.bad{background:color-mix(in srgb,var(--bad) 18%,transparent)}
details summary{cursor:pointer;color:var(--ink2);margin:6px 0}
.cand{border-top:1px solid var(--grid);padding:10px 0}.cand:first-child{border-top:0}
.cand-head{font-weight:600;font-size:13px;margin-bottom:6px}
.grps{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}
.grp-title{font-size:12px;color:var(--ink2);margin-bottom:4px}.grp-note{font-size:11px;color:var(--muted);margin-top:4px}
.bars{display:flex;flex-direction:column;gap:3px}
.bar-row{display:grid;grid-template-columns:96px 1fr 40px auto;gap:8px;align-items:center;font-size:12px;color:var(--ink2)}
.bar-row.chosen{color:var(--ink);font-weight:600}
.bar-name{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.bar-track{height:10px;background:var(--empty);border-radius:3px;overflow:hidden}
.bar-fill{display:block;height:100%;background:var(--s1);border-radius:3px}
.bar-row.chosen .bar-fill{background:var(--s1)}.bar-row:not(.chosen) .bar-fill{opacity:.45}
.bar-val{text-align:right;font-variant-numeric:tabular-nums}.bar-note{font-size:11px;color:var(--muted);white-space:nowrap}
.bar-row.chosen .bar-note{color:#006300}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]) .bar-row.chosen .bar-note{color:var(--good)}}
#tip{position:fixed;pointer-events:none;background:var(--ink);color:var(--page);padding:6px 9px;border-radius:6px;font-size:12px;max-width:420px;display:none;z-index:9}
footer{margin-top:28px;font-size:12px;color:var(--muted)}
"""

JS = """
const tip=document.getElementById('tip');
function show(e,t){tip.textContent=t;tip.style.display='block';move(e)}
function move(e){const x=Math.min(e.clientX+12,window.innerWidth-tip.offsetWidth-8);tip.style.left=x+'px';tip.style.top=(e.clientY+14)+'px'}
function hide(){tip.style.display='none'}
document.querySelectorAll('[data-tip]').forEach(el=>{
  el.addEventListener('mouseenter',e=>show(e,el.dataset.tip));el.addEventListener('mousemove',move);el.addEventListener('mouseleave',hide);
  el.addEventListener('focus',e=>show(e,el.dataset.tip));el.addEventListener('blur',hide);
});
document.querySelectorAll('svg[data-chart=line]').forEach(svg=>{
  const xh=svg.querySelector('.xhair');
  svg.querySelectorAll('.hit').forEach(h=>{
    h.addEventListener('mouseenter',()=>{xh.style.display='';xh.setAttribute('x1',h.dataset.x);xh.setAttribute('x2',h.dataset.x)});
    h.addEventListener('mouseleave',()=>{xh.style.display='none'});
  });
});
"""


def build_html(run: dict) -> str:
    k = kpis(run)
    cfg = run["config"] or {}
    sm = run["summary"] or {}
    driver = sm.get("driver") or ("orchestrator" if run["has_orch"] else "fixed")
    n = k["steps"]

    tiles = [
        tile("스텝", fmt(n), f"{sm.get('scenario') or cfg.get('scenario') or ''} · seed {sm.get('seed', cfg.get('seed', ''))}"),
        tile("개입 (사람 호출)", fmt(k["escalations"]), f"자율 처리율 {fmt(k['autonomy'], pct=True)}",
             "good" if k["escalations"] == 0 else ("warn" if k["autonomy"] and k["autonomy"] > 0.7 else "bad")),
        tile("SLA 위반", fmt(k["sla_violations"]), f"채점된 스텝의 {fmt(k['sla_rate'], pct=True)}",
             "good" if k["sla_violations"] == 0 else ("warn" if (k["sla_rate"] or 0) < 0.3 else "bad")),
        tile("조달", fmt(k["procurements"]), f"비용 {fmt(k['cost'], 1)}"),
    ]
    if run["has_truth"]:
        acc = k.get("accuracy")
        tiles.append(tile("상황 인지 정확도", fmt(acc, pct=True), f"전환 스텝 제외 n={k.get('accuracy_n')}",
                          "" if acc is None else ("good" if acc >= 0.7 else ("warn" if acc >= 0.5 else "bad"))))
    if run["has_orch"]:
        ad = k.get("adherence")
        tiles.append(tile("절차 준수", fmt(ad, pct=True), f"깨끗한 스텝 {k.get('clean')}/{k.get('judged')}",
                          "" if ad is None else ("good" if ad >= 0.95 else ("warn" if ad >= 0.8 else "bad"))))
        tiles.append(tile("LLM 비용", f"${fmt(k.get('llm_cost'), 2)}",
                          f"스텝당 호출 {fmt(k.get('mean_calls'), 1)} · {fmt(k.get('mean_elapsed'), 0)}초"))

    legend_sit = "".join(
        f'<span style="--c:var({c})">{KO[s]} ({LETTER[s]})</span>'
        for s, c in (("normal", "--axis"), ("emergency", "--s1"), ("special_event", "--s2"), ("iot_surge", "--s3")))
    legend_state = ('<span style="--c:var(--good)">✓ 충족·일치</span><span style="--c:var(--bad)">✗ 위반·불일치</span>'
                    '<span style="--c:var(--warn)">! 사람 호출</span><span style="--c:var(--s7)">$ 조달</span>'
                    '<span style="--c:var(--neutral)">· 전환 스텝(채점 제외)</span>')

    when = datetime.now().strftime("%Y-%m-%d %H:%M")
    model = sm.get("model") or cfg.get("model") or ""
    parts = [f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(run['run_id'])} 리포트</title>
<style>{CSS}</style></head><body><div id="tip" role="tooltip"></div><main>
<h1>{esc(run['run_id'])}</h1>
<div class="meta">드라이버 <b>{esc(driver)}</b>{' · 모델 ' + esc(model) if model else ''} · 생성 {when}
{' · 의도: ' + esc(sm.get('intent')) if sm.get('intent') else ''}</div>
<div class="tiles">{''.join(tiles)}</div>

<h2>스텝 타임라인 — 무슨 일이 있었나</h2>
<div class="card">{timeline_svg(run)}
<div class="legend">{legend_sit}</div><div class="legend">{legend_state}</div></div>

<h2>후보와 선택 — 무엇을 놓고 어떤 값으로 골랐나</h2>
<div class="card">{candidates_section(run)}
<p class="muted">상황 비율은 LLM 이 낸 값, 정책 확신은 ②, 정책 성적은 ⑤, 벤더 점수는 ③이 낸 값이다. 굵은 줄이 선택된 것.</p></div>

<h2>신뢰도 추이 — 왜 사람을 불렀나</h2>
<div class="card">{confidence_svg(run)}
<div class="legend"><span style="--c:var(--s1)">결합 combined = √(intrinsic × empirical)</span>
<span style="--c:var(--s2)">intrinsic (②가 낸 확신)</span><span style="--c:var(--s3)">empirical (⑤ 성적)</span>
<span style="--c:var(--warn)">▲ 사람 호출</span></div>
<p class="muted">결합 신뢰도가 점선 아래로 내려간 스텝에서 사람을 부른다.</p></div>
"""]
    if run["has_orch"]:
        parts.append(f"""<h2>도구 호출 — LLM 이 스텝마다 몇 번 움직였나</h2>
<div class="card">{calls_svg(run)}
<div class="legend"><span style="--c:var(--s1)">완료된 호출</span><span style="--c:var(--serious)">실패한 호출 (서버가 거부·예외 → LLM 이 재시도)</span>
<span>막대 위 숫자 = 절차 위반 수</span></div></div>
""")
    parts.append(f"""<h2>혼동 행렬 — 정답 vs 판단</h2>
<div class="card">{confusion_table(k.get('confusion', {}))}</div>

<h2>조달 내역</h2>
<div class="card">{procurement_table(run)}</div>

<h2>스텝 상세</h2>
<div class="card"><details{' open' if n <= 30 else ''}><summary>{n}스텝 · 펼치기/접기</summary>{steps_table(run)}</details></div>

<footer>원본: runs/{esc(run['run_id'])}/decisions.json · truth.jsonl{' · orchestrator/steps.jsonl' if run['has_orch'] else ''}.
정답 대조 지표는 여기서만 계산되며 에이전트에게는 보이지 않는다.</footer>
</main><script>{JS}</script></body></html>""")
    return "".join(parts)


def build_report(run_id: str, out: Optional[Path] = None) -> Path:
    run = load_run(run_id)
    out = out or (paths.run_dir(run_id) / "report.html")
    out.write_text(build_html(run), encoding="utf-8")
    return out


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python -m eval.report {run_id}", file=sys.stderr)
        sys.exit(1)
    print(build_report(sys.argv[1]))
