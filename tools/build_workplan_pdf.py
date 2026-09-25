#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""claude/team/workplan.md -> 사람용 요약 + 원문 부록 -> HTML -> Chrome headless -> PDF

    .venv310\\Scripts\\python.exe tools\\build_workplan_pdf.py
    -> docs/작업계획.pdf

build_pdf.py 와 같은 경로(markdown -> HTML -> Chrome)와 같은 팔레트를 쓴다.
요약(표지 · 진행도 · 인과 그림 · 결정 · 담당 · 순서)은 여기서 그리고,
상세는 workplan.md 를 그대로 부록으로 붙인다 — 진실은 md 한 곳에만 둔다.
"""
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "claude" / "team" / "workplan.md"
OUT_HTML = ROOT / "docs" / "_build" / "작업계획.html"
OUT_PDF = ROOT / "docs" / "작업계획.pdf"

# 팔레트 — build_pdf.py 와 동일 (dataviz 검증 팔레트)
S1, S2, S3 = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, BASELINE = "#e1e0d9", "#c3c2b7"
SURFACE, PLANE = "#fcfcfb", "#f9f9f7"
CRITICAL, WARNING, GOOD = "#d03b3b", "#fab219", "#0ca30c"

FONT = '"Malgun Gothic","Apple SD Gothic Neo","Noto Sans KR",system-ui,sans-serif'
MONO = 'Consolas,"Cascadia Mono",ui-monospace,monospace'


# ── SVG 조각 ────────────────────────────────────────────────────────
def _box(x, y, w, h, label, fill=SURFACE, stroke=GRID, color=INK, dash=False, fs=13):
    d = ' stroke-dasharray="5 4"' if dash else ""
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="1.4"{d}/>'
            f'<text x="{x + w / 2}" y="{y + h / 2 + fs * 0.36}" text-anchor="middle" '
            f'font-size="{fs}" fill="{color}" font-family={FONT!r}>{label}</text>')


def _arrow(x1, y1, x2, y2, color=INK2, w=1.6):
    return (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" '
            f'stroke-width="{w}" marker-end="url(#ah)"/>')


def _defs():
    return (f'<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" '
            f'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M0,0 L10,5 L0,10 z" fill="{INK2}"/></marker>'
            f'<marker id="ahr" viewBox="0 0 10 10" refX="9" refY="5" '
            f'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M0,0 L10,5 L0,10 z" fill="{CRITICAL}"/></marker></defs>')


def loop_svg():
    """원본의 닫힌 고리 vs 현재의 열린 고리."""
    W, H = 700, 250
    o = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" '
         f'aria-label="원본과 현재의 배분 흐름">', _defs()]

    def row(y, title, steps, gap_idx=None, note=None):
        o.append(f'<text x="0" y="{y - 14}" font-size="12" fill="{MUTED}" '
                 f'font-family={FONT!r} font-weight="600">{title}</text>')
        bw, bh, gx = 104, 40, 22
        x = 0
        for i, (lab, kind) in enumerate(steps):
            if kind == "gap":
                o.append(_box(x, y, bw, bh, lab, fill="#fff", stroke=CRITICAL,
                              color=CRITICAL, dash=True, fs=12))
            elif kind == "hi":
                o.append(_box(x, y, bw, bh, lab, fill="#e8f5ee", stroke=S3, fs=13))
            else:
                o.append(_box(x, y, bw, bh, lab, fs=13))
            if i < len(steps) - 1:
                o.append(_arrow(x + bw, y + bh / 2, x + bw + gx - 2, y + bh / 2))
            x += bw + gx
        return x - gx

    # 원본: 닫힌 고리
    end = row(40, "원본  ml_orchestrator_demo.py:429~461  (한 함수)",
              [("관측", "n"), ("목표표", "n"), ("평활", "n"), ("위반 보정", "hi"), ("적용", "n")])
    # 되먹임 화살표 (적용 → 관측)
    o.append(f'<path d="M{end - 52},80 L{end - 52},104 L52,104 L52,82" fill="none" '
             f'stroke="{S3}" stroke-width="1.6" marker-end="url(#ah)"/>')
    o.append(f'<text x="{end / 2}" y="119" text-anchor="middle" font-size="11.5" '
             f'fill="{S3}" font-family={FONT!r}>이용률이 임계를 넘으면 배분을 고친다</text>')

    # 현재: 열린 고리
    row(170, "현재  ② rule.py  +  ① env.py  (서버 두 개로 분리)",
        [("관측", "n"), ("목표표 ②", "n"), ("평활 ①", "n"), ("(빠짐)", "gap"), ("적용 ①", "n")])
    o.append(f'<text x="0" y="238" font-size="11.5" fill="{CRITICAL}" font-family={FONT!r}>'
             f'평활이 ①로 가면서 보정을 걸 자리가 사라졌다 → ②는 관측을 읽지 않는다 → 출력 4가지</text>')
    o.append("</svg>")
    return "".join(o)


def chain_svg():
    """세 층 인과 + 자기강화 고리."""
    W, H = 700, 270
    o = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="세 층 인과">', _defs()]
    layers = [
        (S2, "1층 · 기원", "위반 보정 누락", "배분이 관측에 반응 못 함 → SLA 위반의 60~90%가 배분 탓"),
        (CRITICAL, "2층 · 증폭", "개입 스텝 귀속 오류", "폴백 상수의 실패가 정책 점수로 → r 0.50 → 0.20"),
        (S1, "3층 · 지표 무효", "개입 판정 공식", "선행 위험 신호가 없음 → AUC 0.49~0.68 → 논문 지표 무의미"),
    ]
    y = 14
    for i, (c, tag, head, body) in enumerate(layers):
        o.append(f'<rect x="0" y="{y}" width="{W}" height="64" rx="8" fill="{PLANE}" '
                 f'stroke="{GRID}"/>')
        o.append(f'<rect x="0" y="{y}" width="6" height="64" rx="3" fill="{c}"/>')
        o.append(f'<text x="18" y="{y + 24}" font-size="11.5" fill="{c}" font-weight="700" '
                 f'font-family={FONT!r}>{tag}</text>')
        o.append(f'<text x="130" y="{y + 24}" font-size="14" fill="{INK}" font-weight="700" '
                 f'font-family={FONT!r}>{head}</text>')
        o.append(f'<text x="18" y="{y + 48}" font-size="12" fill="{INK2}" '
                 f'font-family={FONT!r}>{body}</text>')
        if i < 2:
            o.append(_arrow(W / 2, y + 66, W / 2, y + 86))
        y += 90
    # 2층 자기강화 고리 — viewBox 안에 머물도록 제어점을 W 안쪽으로 둔다
    o.append(f'<path d="M{W - 40},{104 + 30} C {W - 6},{104 + 30} {W - 6},{104 + 66} {W - 40},{104 + 66}" '
             f'fill="none" stroke="{CRITICAL}" stroke-width="1.6" stroke-dasharray="4 3" '
             f'marker-end="url(#ahr)"/>')
    o.append(f'<text x="{W - 12}" y="{104 + 88}" text-anchor="end" font-size="11" fill="{CRITICAL}" '
             f'font-family={FONT!r}>개입 → 폴백 실패 → r↓ → 더 개입</text>')
    o.append("</svg>")
    return "".join(o)


def timeline_svg():
    W, H = 700, 200
    o = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="순서">', _defs()]
    phases = [
        ("지금 바로", "B-3 A-1 A-2 A-3\nC-1 C-2 C-3\nC-4 C-6 C-9", S3),
        ("팀 회의", "D1 위반 보정\nD3 조달 시점", WARNING),
        ("수정", "B-1 B-2\nC-5", S1),
        ("M-1 재측정", "AUC 다시 계산\n→ D2 확정", S2),
        ("M-2 본실험", "4×5×3×2\nrun_matrix", INK2),
    ]
    n = len(phases)
    bw, gap = 118, 27
    x = 0
    for i, (title, body, c) in enumerate(phases):
        o.append(f'<rect x="{x}" y="30" width="{bw}" height="110" rx="8" fill="{SURFACE}" '
                 f'stroke="{GRID}" stroke-width="1.4"/>')
        o.append(f'<rect x="{x}" y="30" width="{bw}" height="8" rx="4" fill="{c}"/>')
        o.append(f'<text x="{x + bw / 2}" y="62" text-anchor="middle" font-size="13" '
                 f'font-weight="700" fill="{INK}" font-family={FONT!r}>{title}</text>')
        for j, line in enumerate(body.split("\n")):
            o.append(f'<text x="{x + bw / 2}" y="{88 + j * 20}" text-anchor="middle" '
                     f'font-size="12" fill="{INK2}" font-family={MONO!r}>{line}</text>')
        if i < n - 1:
            o.append(_arrow(x + bw, 85, x + bw + gap - 2, 85))
        x += bw + gap
    o.append(f'<text x="0" y="178" font-size="11.5" fill="{MUTED}" font-family={FONT!r}>'
             f'D2(개입 판정 공식)는 M-1 결과를 보고 정한다 — 귀속 오류가 걷힌 뒤의 값이어야 한다</text>')
    o.append("</svg>")
    return "".join(o)


def bar(label, pct, color, note=""):
    return (f'<div class="bar"><div class="bl">{label}</div>'
            f'<div class="bt"><div class="bf" style="width:{pct}%;background:{color}"></div></div>'
            f'<div class="bn">{note}</div></div>')


# ── 요약 본문 ───────────────────────────────────────────────────────
def digest():
    return f'''
<section class="cover">
  <div class="kicker">SRM-main-mcp · 2026-09-24</div>
  <h1>작업 계획<br><span>실험이 성립하기까지</span></h1>
  <p class="lead">인프라는 끝났다. 실험은 원본에서 끊긴 피드백 루프 하나 때문에 아직 시작되지 못했고,
  그 위에 얹힌 개입 판정 공식은 위험을 재지 않아 논문의 핵심 지표가 지금은 무의미하다.</p>
  <div class="nums">
    <div><b>60~90%</b><span>SLA 위반 중<br>배분 탓</span></div>
    <div><b>0.49</b><span>개입 판정의<br>SLA 예측력 (AUC)</span></div>
    <div><b>3</b><span>코드 전에<br>정할 결정</span></div>
  </div>
</section>

<section>
  <h2>지금 어디까지 왔나</h2>
  {bar("배선 · 서버 5개 · 드라이버 2종 · 채점기 · 재현성", 100, S3, "완료")}
  {bar("실험 장치 · 비교군 · 집계 · 배치", 45, S1, "arms/ · run_matrix 없음")}
  {bar("결정 · 위반 보정 · 개입 공식 · 조달 시점", 0, WARNING, "회의 필요")}
  {bar("결과 · 논문 표에 들어갈 수치", 0, CRITICAL, "측정 불가 상태")}
  <p class="note">"구축은 끝났고 나머지는 조정"은 절반만 맞다. 조정 중 하나(개입 판정 공식)가
  논문의 축을 흔들 수 있다.</p>
</section>

<section>
  <h2>왜 지금 결과가 이런가</h2>
  <h3>원본에서 끊긴 것</h3>
  {loop_svg()}
  <h3>그 위에 쌓인 것</h3>
  {chain_svg()}
</section>

<section>
  <h2>근거 — 전부 실서버 실측</h2>
  <table class="ev">
    <tr><th>관측</th><th>값</th><th>뜻</th></tr>
    <tr><td>SLA 위반 중 배분 탓 (나머지는 압력>1.0)</td><td class="m">19/21 · 12/20</td><td>normal · emergency 30스텝. 조달이 아니라 배분이 관측에 반응하지 않아서</td></tr>
    <tr><td>개입 스텝의 적용 배분 = 폴백 상수</td><td class="m">18/18 · 19/19</td><td>성적표의 60%가 정책이 하지 않은 일의 점수</td></tr>
    <tr><td><code>rule_based</code> 신뢰도 r</td><td class="m">0.500 → 0.200</td><td>120스텝 동안 붕괴 — 정책이 나빠서가 아니라 개입했기 때문</td></tr>
    <tr><td><code>combined</code> 의 SLA 예측력</td><td class="m">0.683 / 0.487</td><td>normal / emergency. 0.5 = 무작위</td></tr>
    <tr><td><code>intrinsic</code> 단독</td><td class="m">0.487 / 0.463</td><td>분기 명확성을 잴 뿐 위험이 아님</td></tr>
    <tr><td><code>worst u/θ</code> (관측에 있는 값)</td><td class="m good">0.857 / 0.608</td><td>가장 좋은 신호가 공식 밖에 있다</td></tr>
    <tr><td><code>lstm_forecast</code> 선택 → 개입</td><td class="m">47 / 47</td><td>표본이 영원히 0. 정책 선택 실증 불가</td></tr>
    <tr><td>조달 제약(1.0) 전 → 후</td><td class="m">5회 → 1회</td><td>스텝당 $0.109 → $0.082. 두 드라이버 비교가 공정해짐</td></tr>
  </table>
</section>

<section>
  <h2>먼저 정해야 할 것 — 코드보다 먼저</h2>
  <div class="cards">
    <div class="card"><div class="ch" style="border-color:{S2}">D1 · 위반 보정</div>
      <p>원본 <code>:446~457</code>. 임계를 넘은 슬라이스에 더 주고 여유 있는 데서 뺀다. kim이 <em>"Day 0에 3인이 정할 사항"</em>으로 남겨둔 것.</p>
      <p class="rec"><b>권고</b> 환경변수 스위치. 기존 기준은 켬(원본 동작). 끈 값은 상황인지 순도 논증용.</p></div>
    <div class="card"><div class="ch" style="border-color:{S1}">D2 · 개입 판정 공식</div>
      <p><code>√(intrinsic × empirical) &lt; 0.45</code>. 원본에 없던 신규 설계. 두 항 모두 선행 위험 신호가 아니다.</p>
      <p class="rec"><b>권고</b> 귀속 오류(B-2)를 고친 뒤 <b>다시 잰 값</b>으로 정한다. τ=0.45는 유지하고 민감도를 보고.</p></div>
    <div class="card"><div class="ch" style="border-color:{S3}">D3 · 조달 시점</div>
      <p>1.0을 넘은 뒤 사면 용량은 다음 스텝에 반영 → 그 스텝 위반 확정. 반응형이다.</p>
      <p class="rec"><b>권고</b> 고정 루프는 1.0 유지(기존 기준), 오케스트레이터만 추세 선제 허용 → <b>그 차이가 기여</b>. 단 D1 이후.</p></div>
  </div>
</section>

<section>
  <h2>누가 무엇을</h2>
  <div class="owners">
    <div class="own"><div class="oh" style="background:{S2}">B · kim · ②③⑤</div>
      <ul>
        <li><b>B-1</b> <code>policy/rule.py</code> 위반 보정 이식 <span class="dep">← D1</span></li>
        <li><b>B-2</b> <code>feedback/server.py:143</code> 개입 스텝은 r 갱신 제외</li>
        <li><b>B-3</b> <code>feedback/reliability.py:60</code> lstm 봉인 해제</li>
        <li><b>B-4</b> <code>rule.py</code> "안전 하한" 독스트링 정정</li>
      </ul></div>
    <div class="own"><div class="oh" style="background:{S1}">A · choi · ①④</div>
      <ul>
        <li><b>A-1</b> <code>audit/book.py:234</code> <code>agent_policy</code> 필드</li>
        <li><b>A-2</b> <code>audit/book.py</code> confidence 타입 검사</li>
        <li><b>A-3</b> <code>observe/</code> Observation 에 <code>features</code> 블록 — classify_demand 가 매 스텝 죽는다</li>
      </ul></div>
    <div class="own"><div class="oh" style="background:{S3}">C · lee · 에이전트</div>
      <ul>
        <li><b>C-1</b> intent 를 장부에 기록</li>
        <li><b>C-2</b> <code>eval/score.py</code> 구조적·오류 스텝 분리</li>
        <li><b>C-3</b> <code>referee.py</code> 개입 무시 규칙</li>
        <li><b>C-4</b> <code>arms/</code> 3종 · escalate 필드화</li>
        <li><b>C-5</b> <code>tools/run_matrix.py</code></li>
        <li><b>C-6</b> <code>vendors.json</code> 추적 해제</li>
        <li><b>C-7</b> 개입 공식 <span class="dep">← D2 · M-1</span></li>
        <li><b>C-8</b> 선제 조달 프롬프트 <span class="dep">← D3 · B-1</span></li>
        <li><b>C-9</b> <code>run_matrix</code> orch·llm 칸 시드당 반복 — 같은 시드에서 실행마다 다르다</li>
      </ul></div>
  </div>
  <h3>순서</h3>
  {timeline_svg()}
  <p class="note"><b>지금 바로</b> 줄은 반나절이고 서로 독립이다. 회의 전에 끝내두면 D1이 나는 순간 B-1 → M-1로 간다.
  결정 전에 본실험 60회를 돌리면 전부 다시 돌리게 된다.</p>
</section>
'''


# ── 부록: workplan.md 원문 ──────────────────────────────────────────
def appendix():
    import markdown
    text = SRC.read_text(encoding="utf-8")
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    body = re.sub(r"\A\s*#\s+.*?\n", "", text, count=1)
    html = markdown.markdown(body, extensions=["tables", "fenced_code", "sane_lists", "attr_list"])
    return (f'<section class="appx"><div class="ah"><div class="t">부록 · 작업 계획 원문</div>'
            f'<div class="s">claude/team/workplan.md — AI 가 그대로 실행할 수 있게 쓴 것</div></div>'
            f'{html}</section>')


CSS = f'''
@page {{ size: A4; margin: 16mm 15mm 18mm; }}
* {{ box-sizing: border-box; }}
body {{ margin:0; color:{INK}; background:#fff; font-family:{FONT}; font-size:12.5px; line-height:1.62; }}
section {{ page-break-after: always; }}
section:last-child {{ page-break-after: auto; }}
h1 {{ font-size:34px; line-height:1.15; margin:18px 0 20px; letter-spacing:-.01em; }}
h1 span {{ display:block; font-size:20px; color:{INK2}; font-weight:500; margin-top:6px; }}
h2 {{ font-size:19px; margin:0 0 14px; padding-bottom:8px; border-bottom:2px solid {INK}; }}
h3 {{ font-size:14px; color:{INK2}; margin:22px 0 8px; font-weight:600; }}
p {{ margin:8px 0; }}
code {{ font-family:{MONO}; font-size:11.5px; background:{PLANE}; padding:1px 5px; border-radius:4px; }}
pre {{ font-family:{MONO}; font-size:10.8px; line-height:1.5; background:{PLANE}; border:1px solid {GRID};
       border-radius:6px; padding:10px 12px; white-space:pre-wrap; word-break:break-word; }}
pre code {{ background:none; padding:0; }}
.cover {{ padding-top:60px; }}
.kicker {{ font-size:12px; color:{MUTED}; letter-spacing:.08em; text-transform:uppercase; }}
.lead {{ font-size:15px; line-height:1.7; color:{INK2}; max-width:560px; margin:0 0 36px; }}
.nums {{ display:flex; gap:18px; }}
.nums > div {{ flex:1; border:1px solid {GRID}; border-radius:10px; padding:16px 18px; background:{SURFACE}; }}
.nums b {{ display:block; font-size:38px; line-height:1; margin-bottom:8px; }}
.nums span {{ font-size:12px; color:{INK2}; line-height:1.4; }}
.bar {{ display:grid; grid-template-columns:270px 1fr 150px; gap:12px; align-items:center; margin:10px 0; }}
.bl {{ font-size:12.5px; }}
.bt {{ height:12px; background:{GRID}; border-radius:6px; overflow:hidden; }}
.bf {{ height:100%; border-radius:6px; }}
.bn {{ font-size:11.5px; color:{MUTED}; }}
.note {{ font-size:12px; color:{INK2}; background:{PLANE}; border-left:3px solid {BASELINE}; padding:8px 12px; margin-top:16px; }}
table.ev {{ width:100%; border-collapse:collapse; font-size:12px; }}
table.ev th, table.ev td {{ text-align:left; padding:8px 8px; border-bottom:1px solid {GRID}; vertical-align:top; }}
table.ev th {{ font-size:11px; color:{MUTED}; font-weight:600; }}
td.m {{ font-family:{MONO}; white-space:nowrap; }}
td.good {{ color:{GOOD}; font-weight:700; }}
.cards {{ display:grid; grid-template-columns:1fr 1fr 1fr; gap:14px; }}
.card {{ border:1px solid {GRID}; border-radius:10px; padding:14px; background:{SURFACE}; font-size:12px; }}
.ch {{ font-weight:700; font-size:13.5px; border-left:4px solid; padding-left:8px; margin-bottom:10px; }}
.rec {{ background:{PLANE}; border-radius:6px; padding:8px 10px; margin-top:10px; }}
.owners {{ display:grid; grid-template-columns:1fr 1fr 1fr; gap:14px; }}
.own {{ border:1px solid {GRID}; border-radius:10px; overflow:hidden; background:{SURFACE}; }}
.oh {{ color:#fff; font-weight:700; padding:8px 12px; font-size:13px; }}
.own ul {{ list-style:none; margin:0; padding:10px 12px; font-size:12px; }}
.own li {{ padding:5px 0; border-bottom:1px dashed {GRID}; }}
.own li:last-child {{ border-bottom:0; }}
.dep {{ color:{WARNING}; font-size:11px; }}
.appx .ah {{ border-bottom:2px solid {INK}; padding-bottom:8px; margin-bottom:16px; }}
.appx .ah .t {{ font-size:19px; font-weight:700; }}
.appx .ah .s {{ font-size:11.5px; color:{MUTED}; }}
.appx h2 {{ font-size:16px; border-bottom:1px solid {GRID}; margin-top:26px; }}
.appx h3 {{ font-size:13.5px; color:{INK}; }}
.appx table {{ width:100%; border-collapse:collapse; font-size:11.5px; margin:8px 0 14px; }}
.appx th, .appx td {{ text-align:left; padding:6px 7px; border-bottom:1px solid {GRID}; vertical-align:top; }}
.appx th {{ font-size:11px; color:{MUTED}; }}
.appx ul, .appx ol {{ padding-left:20px; }}
.appx li {{ margin:3px 0; }}
.appx blockquote {{ margin:8px 0; padding:6px 12px; border-left:3px solid {BASELINE}; color:{INK2}; }}
'''


def main():
    if not SRC.is_file():
        print(f"[오류] {SRC} 가 없다", file=sys.stderr)
        return 1
    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    html = (f'<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">'
            f'<title>작업 계획 — 실험이 성립하기까지</title><style>{CSS}</style></head><body>'
            f'{digest()}{appendix()}</body></html>')
    OUT_HTML.write_text(html, encoding="utf-8")
    print(f"HTML  {OUT_HTML}  ({len(html) // 1024} KB)")

    chrome = next((c for c in [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ] if os.path.exists(c)), None)
    if not chrome:
        print("브라우저를 찾지 못함 - HTML만 생성", file=sys.stderr)
        return 1

    cmd = [chrome, "--headless", "--disable-gpu", "--no-sandbox",
           "--no-pdf-header-footer", f"--print-to-pdf={OUT_PDF}", OUT_HTML.as_uri()]
    r = subprocess.run(cmd, capture_output=True, timeout=240)
    if OUT_PDF.exists():
        print(f"PDF   {OUT_PDF}  ({OUT_PDF.stat().st_size // 1024} KB)")
        return 0
    print(r.stderr[-1500:].decode("utf-8", "replace"), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
