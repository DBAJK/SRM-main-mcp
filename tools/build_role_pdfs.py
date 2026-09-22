#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""역할별(A/B/C) PDF 3종.

각 본은 [공통 계약 + 담당 상세]다. 공통을 빼면 자기 서버만 보고 계약을 깬다.
차트·팔레트·CSS는 build_pdf.py 것을 그대로 쓴다.
"""
import os, re, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_pdf as B

ROOT = B.ROOT
DOCS = B.DOCS
BUILD = DOCS / "_build"
S1, S2, S3 = B.S1, B.S2, B.S3
INK, INK2, MUTED = B.INK, B.INK2, B.MUTED
GRID, BASELINE, SURFACE, PLANE = B.GRID, B.BASELINE, B.SURFACE, B.PLANE
CRITICAL = B.CRITICAL


# ── 절 추출 ─────────────────────────────────────────────────────────
def sections(md):
    """[(level, title, body_with_heading)] — H2 단위, H3는 하위로 중첩."""
    lines = md.split("\n")
    idx = [i for i, l in enumerate(lines) if re.match(r"^##\s+|^###\s+", l)]
    out = []
    for k, i in enumerate(idx):
        j = idx[k + 1] if k + 1 < len(idx) else len(lines)
        lvl = 2 if lines[i].startswith("## ") else 3
        title = lines[i].lstrip("# ").strip()
        out.append((lvl, title, "\n".join(lines[i:j]).rstrip()))
    return out


def pick(md, rules):
    """rules: [(h2_정규식, None | [h3_정규식...])] — None이면 H2 전체(하위 H3 포함)."""
    secs = sections(md)
    keep, cur_h2, cur_rule = [], None, None
    for lvl, title, body in secs:
        if lvl == 2:
            cur_h2, cur_rule = title, None
            for pat, subs in rules:
                if re.search(pat, title):
                    cur_rule = (True, subs)
                    break
            if cur_rule:
                keep.append(body)
        else:
            if cur_rule and cur_rule[1] is None:
                keep.append(body)                       # H2 전체 채택
            elif cur_rule and any(re.search(p, title) for p in cur_rule[1]):
                keep.append(body)
    return "\n\n".join(keep)


# ── 공통 계약 (3명 모두) ────────────────────────────────────────────
CL = ROOT / "claude"

COMMON_FILES = [
    "spec/common.md", "spec/tools.md",
    "flow/loop.md", "flow/data-chain.md", "flow/errors.md", "flow/forbidden.md",
    "build/runtime.md", "build/store.md",
]
# team/roles.md 는 한 파일이므로 절 단위로 자른다
COMMON_ROLE_SEC = [(r"^0\. 병렬 개발의 전제", None), (r"^1\. Day 0", None),
                   (r"^5\. 왜 이렇게 묶었나", None), (r"^6\. 병렬화 장치", None),
                   (r"^7\. 합류 지점", None), (r"^8\. Day 0 체크리스트", None)]

ROLES = {
    "A": dict(
        name="A · 환경 · 측정", color=S1,
        servers=["① slice-observe", "④ slice-audit"],
        sub="시뮬레이터 해체 · 지표 산출 · 실험 하네스",
        tools=[("① observe", "get_observation · step · apply_allocation · get_history · add_capacity · reset"),
               ("④ audit", "record_decision · record_escalation · get_decisions · get_metrics")],
        produces=[("Observation", "① get_observation", "B(②) · C", "모든 판단의 입력"),
                  ("HistoryBlock", "① get_history", "B(②)", "LSTM 시퀀스 (n,11)"),
                  ("ApplyResult", "① apply_allocation", "C", "평활·클립 결과와 delta"),
                  ("decision_id", "④ record_decision", "B(⑤) · C", "채점의 키"),
                  ("fixtures/", "tools/record_fixtures.py", "B · C", "Day 2 배포 — 둘의 병렬화 열쇠"),
                  ("truth.jsonl", "① step (도구 아님)", "eval/score.py", "정답. 도구로 절대 노출 금지")],
        consumes=[("allocation", "B(②) propose_allocation", "① apply_allocation"),
                  ("situation · confidence", "C", "④ record_decision"),
                  ("capacity_gain", "B(③) procure", "① add_capacity"),
                  ("outcome", "B(⑤) report_outcome", "decisions.json 에 추가기입")],
        files=["spec/observe.md","spec/audit.md","rationale/corrections.md","rationale/verification.md","rationale/environment.md","rationale/observe.md","rationale/audit.md","rationale/context-budget.md","build/extract.md","build/order.md"],
        role_sec=[(r"^2\. A — 환경 · 측정", None)],
        charts=True,
    ),
    "B": dict(
        name="B · 모델 · 정책", color=S2,
        servers=["② slice-policy", "③ slice-market", "⑤ slice-feedback"],
        sub="TensorFlow 적재 · 정책 래핑 · 자기 개선",
        tools=[("② policy", "list_policies · propose_allocation · compare_policies · classify_demand"),
               ("③ market", "list_offerings · score_offerings · explain_score · procure · update_rating"),
               ("⑤ feedback", "report_outcome · get_reliability_table")],
        produces=[("PolicyProposal", "② propose_allocation", "C · A(④)", "allocation · confidence · status"),
                  ("DemandClass", "② classify_demand", "C · A(④)", "지배 수요. 상황 정답이 아님"),
                  ("ScoredOffering", "③ score_offerings", "C", "벤더 5곳 점수 내림차순"),
                  ("capacity_gain", "③ procure", "A(①) add_capacity", "조달을 환경에 반영하는 유일한 값"),
                  ("Outcome", "⑤ report_outcome", "C · A(④)", "sla_met · error · vendor_id"),
                  ("recent_error", "⑤ get_reliability_table", "② (C가 중계)", "②의 LSTM 신뢰도 공급선")],
        consumes=[("Observation · HistoryBlock", "A(①)", "② propose_allocation"),
                  ("situation", "C", "② propose_allocation — 기본값 없음"),
                  ("current_step", "A(①) observation.step", "③ procure"),
                  ("decision_id", "A(④)", "⑤ report_outcome")],
        files=["spec/policy.md","spec/market.md","spec/feedback.md","rationale/corrections.md","rationale/verification.md","rationale/policy.md","rationale/market.md","rationale/feedback.md","build/formulas.md","build/step0.md","build/extract.md","build/order.md"],
        role_sec=[(r"^3\. B — 모델 · 정책", None)],
        charts=False,
    ),
    "C": dict(
        name="C · 에이전트", color=S3,
        servers=["오케스트레이터", "프롬프트", "계약 검사"],
        sub="판단 로직 · 도구 호출 루프 · 목 서버",
        tools=[("전 서버", "21개 도구 전부를 호출한다 — 본문에 명세 전체를 수록"),
               ("직접 작성", "srm_mcp/mock/ 5개 · orchestrator/ · check_contract.py")],
        produces=[("run_id", "C 발급", "A(①) reset · A(④) 전체", "없으면 60회 실행이 섞인다"),
                  ("situation", "C 추론", "B(②) · A(④)", "관측에서 추론. 어떤 도구도 주지 않음"),
                  ("confidence.situation", "C 판단", "A(④)", "상황 오판 가능성 — 유일한 경로"),
                  ("confidence.combined", "C 계산", "A(④)", "세 값의 기하평균"),
                  ("정책 선택", "C 판단", "B(②) policy 인자", "신뢰도 비교 결과"),
                  ("에스컬레이션 판단", "C 판단", "A(④)", "combined < τ(0.45)")],
        consumes=[("Observation · ApplyResult", "A(①)", "판단 · 실행"),
                  ("PolicyProposal · ScoredOffering", "B(②③)", "정책·벤더 선택"),
                  ("Outcome · recent_error", "B(⑤)", "다음 판단에 반영"),
                  ("decision_id · fallback", "A(④)", "채점 · 에스컬레이션 후 진행")],
        files=["spec/observe.md","spec/policy.md","spec/market.md","spec/audit.md","spec/feedback.md","rationale/verification.md","rationale/environment.md","rationale/context-budget.md","build/formulas.md","build/order.md"],
        role_sec=[(r"^4\. C — 에이전트", None)],
        charts=True,
    ),
}


def iface_table(rows, headers):
    th = "".join(f"<th>{h}</th>" for h in headers)
    tr = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<table class="ifc"><tr>{th}</tr>{tr}</table>'


def cover(rid, cfg, total):
    return f'''<section class="cover" style="border-top-color:{cfg['color']}">
  <div class="ctag" style="color:{cfg['color']}">Build-A-Thon SRM · 역할본 {rid} / 3</div>
  <h1>MCP 기반 5G 슬라이스<br>자율 오케스트레이션 설계서</h1>
  <div class="crole" style="background:{cfg['color']}">{cfg['name']}</div>
  <p class="csub">{cfg['sub']}</p>
  <div class="cmeta">
    <div><b>담당</b> {' · '.join(cfg['servers'])}</div>
    <div><b>구성</b> 공통 계약 + 담당 상세 ({total}페이지)</div>
    <div><b>저장소</b> DBAJK/SRM-main-mcp</div>
    <div><b>작성</b> 2026-09-21</div>
  </div>
  <p class="cwarn">이 본은 전체 설계서에서 <b>{cfg['name'].split(' · ')[0]} 담당분</b>을 뽑은 것이다.
  앞의 <b>공통 계약</b>(공통 타입 · 도구 일람 · 데이터 연쇄 · 제어 루프 · 오류 규약 · 금지 필드)은
  <b>3명이 동일하게 읽는다.</b> 그 부분을 건너뛰면 자기 서버만 보고 계약을 깬다.</p>
</section>'''


def iface(rid, cfg):
    return f'''<section class="vs">
  <h2>내 범위</h2>
  <table class="ifc mine">
    {"".join(f"<tr><th>{s}</th><td>{t}</td></tr>" for s, t in cfg['tools'])}
  </table>

  <h3>내가 생산하는 값 — 남이 여기에 의존한다</h3>
  {iface_table(cfg['produces'], ["값", "출처", "소비자", "비고"])}

  <h3>내가 소비하는 값 — 없으면 내가 막힌다</h3>
  {iface_table(cfg['consumes'], ["값", "생산자", "쓰는 곳"] + ([] if len(cfg['consumes'][0]) == 3 else ["비고"]))}

  <p class="cap"><b>서버끼리는 직접 대화하지 않는다.</b> 위의 모든 값은 오케스트레이터(C)가 옮겨 심는다.
  내 도구가 남의 도구를 부르는 코드는 어디에도 없어야 한다 — 하나라도 있으면 §2.2 규약 위반이고,
  무상태 서버가 상태를 갖게 된다.</p>
</section>'''


def charts_page(rid):
    if rid == "A":
        return f'''<section class="vs">
  <h2>환경 검증 — A가 맞춰야 하는 숫자</h2>
  <p class="lead">①의 파라미터가 실험의 신호를 결정한다. 아래는 <b>A-2의 완료 판정 기준</b>이다.</p>
  <h3>재배분으로 해결 불가한 스텝의 비율</h3>
  {B.legend([("조정 전", S2), ("조정 후", S1)])}
  {B.CH_PRESSURE}
  <p class="cap">조정 전에는 <b>평시의 53%</b>가 어떤 배분으로도 SLA를 못 지키는 상태였다 —
  SLA 지표가 포화되어 비교군 간 차이가 드러나지 않는다. 상수 3개
  (<code>CAPACITY_BASE</code> 1.6, <code>CAPACITY_MAX</code> 2.6, <code>START_HOUR</code> 0)로
  평시 5.6%까지 내렸다. <b>원 코드의 상수는 건드리지 않는다.</b></p>
  <h3>구성비만으로 얻는 상황 인지 정확도</h3>
  {B.CH_PERCEPT}
  <p class="cap">A가 직접 만들지는 않지만 <code>eval/score.py</code>가 채점할 대상이다.
  <code>normal</code> 50.5%는 <b>오탐이 구조적으로 많다</b>는 뜻이므로, 매핑 규칙과
  전환 경계 제외를 <b>채점 전에</b> 코드에 고정해야 한다.</p>
</section>'''
    return f'''<section class="vs">
  <h2>C가 알아야 할 환경 특성</h2>
  <p class="lead">프롬프트 설계의 전제다. 에이전트가 무엇을 근거로 판단할 수 있는지가 여기서 정해진다.</p>
  <h3>트래픽 구성비 — 상황 인지의 실제 근거</h3>
  {B.legend([("eMBB", S1), ("URLLC", S2), ("mMTC", S3)])}
  {B.CH_SHARE}
  <p class="cap">시간 요인(±30%)이 이벤트 효과와 비슷한 크기라 <b>절대량으로는 평시 피크와 비상이
  구분되지 않는다.</b> 세 슬라이스에 같은 배수가 곱해지므로 구성비는 시간 요인에 불변이며,
  여기서 신호가 나온다. <b>프롬프트가 절대량을 보게 유도하면 안 된다.</b></p>
  <h3>구성비만으로 얻는 상황 인지 정확도</h3>
  {B.CH_PERCEPT}
  <p class="cap">전체 <b>71.7%</b>가 단일 스텝 참조점이다. 에이전트는 시계열·<code>violations</code>·
  <code>classify_demand</code>를 함께 보므로 더 잘할 수 있다. <code>normal</code> 50.5%는
  <b>오탐이 많다</b>는 뜻이며, <code>confidence.situation</code>을 에스컬레이션 경로에 넣어야 하는 근거다.</p>
</section>'''


EXTRA_CSS = f'''
.crole {{ display:inline-block; color:#fff; font-size:15pt; font-weight:700;
          padding:2.6mm 6mm; border-radius:7px; margin:0 0 5mm; }}
.cwarn {{ margin-top:10mm; font-size:9.4pt; color:{INK2}; background:{PLANE};
          border-radius:7px; padding:4mm 5mm; line-height:1.6; }}
.cwarn b {{ color:{INK}; }}
table.ifc {{ width:100%; border-collapse:collapse; font-size:9.2pt; margin:2mm 0 0; }}
table.ifc th {{ background:{PLANE}; text-align:left; font-weight:700;
                border:1px solid {GRID}; padding:2mm 2.6mm; }}
table.ifc td {{ border:1px solid {GRID}; padding:2mm 2.6mm; vertical-align:top; }}
table.ifc.mine th {{ width:26mm; color:{INK}; }}
table.ifc tr td:first-child {{ font-family:"Cascadia Mono",Consolas,monospace; font-size:8.8pt; }}
'''


def md2html(text):
    import markdown, re as _re
    text = _re.sub(r"<!--.*?-->", "", text, flags=_re.S)
    return markdown.markdown(
        text, extensions=["tables", "fenced_code", "sane_lists", "attr_list"])


def doc_section(rel, color, tag):
    src = re.sub(r"<!--.*?-->", "", (CL / rel).read_text(encoding="utf-8"), flags=re.S)
    m = re.match(r"\s*#\s+(.+)", src)
    title = m.group(1).strip() if m else rel
    body = re.sub(r"\A\s*#\s+.*?\n", "", src, count=1)
    return (f'<section class="doc"><div class="doc-hd" style="border-left-color:{color}">'
            f'<div class="t">{title}</div><div class="s">{tag} · claude/{rel}</div></div>'
            f'{md2html(body)}</section>')


def build(rid):
    cfg = ROLES[rid]
    body = [cover(rid, cfg, "—"), iface(rid, cfg)]
    if cfg["charts"]:
        body.append(charts_page(rid))

    for rel in COMMON_FILES:
        body.append(doc_section(rel, MUTED, "공통 계약"))
    roles_md = re.sub(r"<!--.*?-->", "", (CL / "team/roles.md").read_text(encoding="utf-8"), flags=re.S)
    common_roles = pick(roles_md, COMMON_ROLE_SEC)
    if common_roles.strip():
        body.append(f'<section class="doc"><div class="doc-hd" style="border-left-color:{MUTED}">'
                    f'<div class="t">3인 역할 분담 — 공통</div>'
                    f'<div class="s">공통 계약 · claude/team/roles.md</div></div>'
                    f'{md2html(common_roles)}</section>')

    for rel in cfg["files"]:
        body.append(doc_section(rel, cfg["color"], f"담당 {rid}"))
    own = pick(roles_md, cfg["role_sec"])
    if own.strip():
        body.append(f'<section class="doc"><div class="doc-hd" style="border-left-color:{cfg["color"]}">'
                    f'<div class="t">{cfg["name"]} — 작업 목록</div>'
                    f'<div class="s">담당 {rid} · claude/team/roles.md</div></div>'
                    f'{md2html(own)}</section>')

    html = (f'<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">'
            f'<title>SRM MCP 설계서 — {cfg["name"]}</title>'
            f'<style>{B.CSS}{EXTRA_CSS}</style></head><body>'
            f'{"".join(body)}</body></html>')

    BUILD.mkdir(parents=True, exist_ok=True)
    hp = BUILD / f"role-{rid}.html"
    hp.write_text(html, encoding="utf-8")
    pdf = DOCS / f"SRM-MCP-설계서_{rid}_{cfg['name'].split(' · ', 1)[1].replace(' ', '')}.pdf"

    chrome = next((c for c in [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"] if os.path.exists(c)), None)
    subprocess.run([chrome, "--headless", "--disable-gpu", "--no-sandbox",
                    "--no-pdf-header-footer", f"--print-to-pdf={pdf}", hp.as_uri()],
                   capture_output=True, timeout=240)
    n = len(re.findall(rb"/Type\s*/Page[^s]", pdf.read_bytes())) if pdf.exists() else 0
    print(f"{rid}  {pdf.name}   {pdf.stat().st_size//1024} KB · {n}p")
    return pdf


if __name__ == "__main__":
    for r in ["A", "B", "C"]:
        build(r)
