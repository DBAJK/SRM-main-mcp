#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""docs/*.md -> 단일 HTML -> Chrome headless -> PDF

시각 요약(표지·아키텍처·데이터 흐름·검증 차트)을 앞에 붙이고
본문 3개 문서를 이어 붙인다.

차트 색은 dataviz 스킬의 검증된 기본 팔레트를 쓴다.
  validate_palette.js "#2a78d6,#eb6834,#1baf7a" --mode light  -> ALL CHECKS PASS
  (aqua 대비 2.74 < 3:1 WARN -> 모든 막대에 직접 라벨을 달아 해소)
"""
import io, os, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"          # 산출물(PDF)만. 원본은 claude/
OUT_HTML = ROOT / "docs" / "_build" / "SRM-MCP-설계서.html"
OUT_PDF = ROOT / "docs" / "SRM-MCP-설계서.pdf"

# ── 팔레트 (dataviz references/palette.md) ──────────────────────────
S1, S2, S3 = "#2a78d6", "#eb6834", "#1baf7a"          # 카테고리 1~3
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, BASELINE = "#e1e0d9", "#c3c2b7"
SURFACE, PLANE = "#fcfcfb", "#f9f9f7"
CRITICAL, WARNING, GOOD = "#d03b3b", "#fab219", "#0ca30c"


# ── SVG 차트 ────────────────────────────────────────────────────────
def hbar_grouped(cats, series, colors, xmax, unit="%", w=680, row_h=54,
                 bar_h=18, gap=4, left=124, right=64, top=34):
    """가로 그룹 막대. series = [(이름, [값...]), ...]"""
    n = len(series)
    plot_w = w - left - right
    h = top + len(cats) * row_h + 34
    px = plot_w / xmax
    out = [f'<svg viewBox="0 0 {w} {h}" width="100%" role="img">']

    # 격자 (뒤로)
    step = 20 if xmax > 50 else 10
    for gx in range(0, int(xmax) + 1, step):
        x = left + gx * px
        out.append(f'<line x1="{x:.1f}" y1="{top-8}" x2="{x:.1f}" y2="{top+len(cats)*row_h-10}" '
                   f'stroke="{GRID}" stroke-width="1"/>')
        out.append(f'<text x="{x:.1f}" y="{top+len(cats)*row_h+8}" fill="{MUTED}" '
                   f'font-size="11" text-anchor="middle">{gx}{unit}</text>')
    # 기준선
    out.append(f'<line x1="{left}" y1="{top-8}" x2="{left}" y2="{top+len(cats)*row_h-10}" '
               f'stroke="{BASELINE}" stroke-width="1"/>')

    block = n * bar_h + (n - 1) * gap
    for i, cat in enumerate(cats):
        ytop = top + i * row_h + (row_h - 14 - block) / 2
        out.append(f'<text x="{left-12}" y="{ytop+block/2+4}" fill="{INK}" font-size="12.5" '
                   f'text-anchor="end">{cat}</text>')
        for j, (_, vals) in enumerate(series):
            v = vals[i]
            y = ytop + j * (bar_h + gap)
            bw = max(v * px, 1.5)
            # 데이터 끝만 4px 라운드 (기준선 쪽은 각짐)
            out.append(
                f'<path d="M{left} {y:.1f} h{bw-4:.1f} a4 4 0 0 1 4 4 v{bar_h-8} '
                f'a4 4 0 0 1 -4 4 h-{bw-4:.1f} z" fill="{colors[j]}"/>')
            out.append(f'<text x="{left+bw+7:.1f}" y="{y+bar_h-4.5:.1f}" fill="{INK2}" '
                       f'font-size="11.5" font-weight="600">{v}{unit}</text>')
    out.append("</svg>")
    return "\n".join(out)


def hbar_single(cats, vals, color, xmax, ref=None, ref_label="", unit="%", w=680):
    left, right, top, row_h, bar_h = 124, 70, 30, 40, 20
    plot_w = w - left - right
    h = top + len(cats) * row_h + 34
    px = plot_w / xmax
    out = [f'<svg viewBox="0 0 {w} {h}" width="100%" role="img">']
    for gx in range(0, int(xmax) + 1, 20):
        x = left + gx * px
        out.append(f'<line x1="{x:.1f}" y1="{top-8}" x2="{x:.1f}" y2="{top+len(cats)*row_h-8}" '
                   f'stroke="{GRID}" stroke-width="1"/>')
        out.append(f'<text x="{x:.1f}" y="{top+len(cats)*row_h+10}" fill="{MUTED}" '
                   f'font-size="11" text-anchor="middle">{gx}{unit}</text>')
    out.append(f'<line x1="{left}" y1="{top-8}" x2="{left}" y2="{top+len(cats)*row_h-8}" '
               f'stroke="{BASELINE}" stroke-width="1"/>')
    if ref is not None:
        rx = left + ref * px
        out.append(f'<line x1="{rx:.1f}" y1="{top-12}" x2="{rx:.1f}" y2="{top+len(cats)*row_h-8}" '
                   f'stroke="{MUTED}" stroke-width="1.5" stroke-dasharray="4 3"/>')
        out.append(f'<text x="{rx+5:.1f}" y="{top-16}" fill="{MUTED}" font-size="11">{ref_label}</text>')
    for i, cat in enumerate(cats):
        y = top + i * row_h + (row_h - bar_h) / 2 - 4
        v = vals[i]
        bw = max(v * px, 1.5)
        out.append(f'<text x="{left-12}" y="{y+bar_h-5:.1f}" fill="{INK}" font-size="12.5" '
                   f'text-anchor="end">{cat}</text>')
        out.append(f'<path d="M{left} {y:.1f} h{bw-4:.1f} a4 4 0 0 1 4 4 v{bar_h-8} '
                   f'a4 4 0 0 1 -4 4 h-{bw-4:.1f} z" fill="{color}"/>')
        out.append(f'<text x="{left+bw+7:.1f}" y="{y+bar_h-5:.1f}" fill="{INK2}" '
                   f'font-size="11.5" font-weight="600">{v}{unit}</text>')
    out.append("</svg>")
    return "\n".join(out)


def stacked100(cats, series, colors, w=680):
    """구성비 100% 누적 막대. 세그먼트 사이 2px 표면 간극."""
    left, right, top, row_h, bar_h = 124, 30, 34, 46, 24
    plot_w = w - left - right
    h = top + len(cats) * row_h + 16
    out = [f'<svg viewBox="0 0 {w} {h}" width="100%" role="img">']
    for i, cat in enumerate(cats):
        y = top + i * row_h
        out.append(f'<text x="{left-12}" y="{y+bar_h-7:.1f}" fill="{INK}" font-size="12.5" '
                   f'text-anchor="end">{cat}</text>')
        x = left
        for j, (_, vals) in enumerate(series):
            v = vals[i]
            seg = v * plot_w
            first, last = j == 0, j == len(series) - 1
            r0 = 4 if first else 0
            r1 = 4 if last else 0
            out.append(
                f'<path d="M{x+r0} {y} h{max(seg-2-r0-r1,0.5):.1f} '
                f'{"a4 4 0 0 1 4 4" if r1 else ""} v{bar_h-(8 if r1 else 0)} '
                f'{"a4 4 0 0 1 -4 4" if r1 else ""} h-{max(seg-2-r0-r1,0.5):.1f} '
                f'{"a4 4 0 0 1 -4 -4" if r0 else ""} v-{bar_h-(8 if r0 else 0)} '
                f'{"a4 4 0 0 1 4 -4" if r0 else ""} z" fill="{colors[j]}"/>')
            if seg > 54:
                out.append(f'<text x="{x+seg/2-1:.1f}" y="{y+bar_h/2+4:.1f}" fill="#ffffff" '
                           f'font-size="11.5" font-weight="700" text-anchor="middle">'
                           f'{round(v*100)}%</text>')
            x += seg
    out.append("</svg>")
    return "\n".join(out)


def legend(items):
    sw = "".join(
        f'<span class="lg"><span class="sw" style="background:{c}"></span>{n}</span>'
        for n, c in items)
    return f'<div class="legend">{sw}</div>'


# ── 시각 요약 섹션 ──────────────────────────────────────────────────
SC = ["normal", "emergency", "special_event", "iot_surge"]

CH_PRESSURE = hbar_grouped(
    SC,
    [("조정 전", [53, 74, 78, 70]), ("조정 후", [5.6, 27.7, 34.3, 28.5])],
    [S2, S1], xmax=80)

CH_PERCEPT = hbar_single(
    ["emergency", "special_event", "iot_surge", "normal"],
    [84.9, 79.8, 71.5, 50.5], S1, xmax=100,
    ref=25, ref_label="무작위 25%")

CH_SHARE = stacked100(
    SC,
    [("eMBB", [0.443, 0.296, 0.571, 0.369]),
     ("URLLC", [0.332, 0.534, 0.233, 0.277]),
     ("mMTC", [0.226, 0.171, 0.196, 0.354])],
    [S1, S2, S3])


def arch_svg():
    return f'''<svg viewBox="0 0 700 330" width="100%" role="img">
<rect x="150" y="6" width="400" height="52" rx="8" fill="{SURFACE}" stroke="{S1}" stroke-width="2"/>
<text x="350" y="28" text-anchor="middle" font-size="14" font-weight="700" fill="{INK}">AI 오케스트레이터 (C)</text>
<text x="350" y="46" text-anchor="middle" font-size="11.5" fill="{INK2}">인지 → 판단 → 실행 → 검증 → 기록</text>
<line x1="350" y1="58" x2="350" y2="80" stroke="{BASELINE}" stroke-width="1.5"/>
<line x1="24" y1="80" x2="676" y2="80" stroke="{INK}" stroke-width="2.5"/>
<text x="350" y="74" text-anchor="middle" font-size="11" font-weight="700" fill="{INK}"
      style="paint-order:stroke" stroke="{PLANE}" stroke-width="6">M C P  경 계</text>
{"".join(
    f"""<line x1="{x+62}" y1="80" x2="{x+62}" y2="104" stroke="{BASELINE}" stroke-width="1.5"/>
<rect x="{x}" y="104" width="124" height="112" rx="8" fill="{SURFACE}" stroke="{col}" stroke-width="1.5"/>
<circle cx="{x+18}" cy="{126}" r="11" fill="{col}"/>
<text x="{x+18}" y="{130}" text-anchor="middle" font-size="12" font-weight="700" fill="#fff">{i+1}</text>
<text x="{x+36}" y="{130}" font-size="12.5" font-weight="700" fill="{INK}">{name}</text>
<text x="{x+12}" y="{152}" font-size="11" fill="{INK2}">{role}</text>
<text x="{x+12}" y="{170}" font-size="11" fill="{MUTED}">도구 {tools}개 · {state}</text>
<text x="{x+12}" y="{194}" font-size="11" font-weight="700" fill="{col}">담당 {owner}</text>"""
    for i, (x, name, role, tools, state, owner, col) in enumerate([
        (24, "observe", "관측 · 실행", 6, "상태보유", "A", S1),
        (156, "policy", "정책 카탈로그", 4, "무상태", "B", S2),
        (288, "market", "조달", 5, "읽기위주", "B", S3),
        (420, "audit", "기록 · 측정", 4, "로그", "A", S1),
        (552, "feedback", "자기 개선", 2, "상태보유", "B", S2)]))}
<rect x="24" y="236" width="652" height="76" rx="8" fill="{PLANE}" stroke="{GRID}"/>
<text x="40" y="258" font-size="12" font-weight="700" fill="{INK}">에이전트만 생산하는 값 \u2014 연구의 기여 지점 전체</text>
{"".join(f'<rect x="{40+i*158}" y="270" width="146" height="28" rx="6" fill="{SURFACE}" stroke="{S1}" stroke-width="1.5"/>'
         f'<text x="{113+i*158}" y="288" text-anchor="middle" font-size="11.5" fill="{INK}">{t}</text>'
         for i, t in enumerate(["상황 판단 (situation)", "정책 선택", "조달 여부", "에스컬레이션"]))}
</svg>'''


def flow_svg():
    steps = [("1", "get_observation", "①", "obs_t 수신", S1),
             ("2", "LLM 판단", "\u2014", "situation · 정책 · 조달 · 호출", S2),
             ("2b", "procure → add_capacity", "③→①", "압력 ≥ 1.0 일 때만", S3),
             ("3", "record_decision", "④", "판단을 먼저 기록", S1),
             ("4", "apply_allocation", "①", "평활 · 클립 · 정규화", S1),
             ("5", "step", "①", "만료 회수 → 다음 트래픽", S1),
             ("6", "report_outcome", "⑤", "1스텝 지연 채점", S2)]
    rows = []
    for i, (no, name, srv, note, col) in enumerate(steps):
        y = 16 + i * 46
        dim = ' opacity="0.72"' if no == "2b" else ""
        dash = ' stroke-dasharray="4 3"' if no == "2b" else ""
        rows.append(f'''<g{dim}>
<rect x="18" y="{y}" width="664" height="36" rx="7" fill="{SURFACE}" stroke="{col}" stroke-width="1.5"{dash}/>
<circle cx="42" cy="{y+18}" r="13" fill="{col}"/>
<text x="42" y="{y+22.5}" text-anchor="middle" font-size="11.5" font-weight="700" fill="#fff">{no}</text>
<text x="66" y="{y+16}" font-size="12.5" font-weight="700" fill="{INK}">{name}</text>
<text x="66" y="{y+30}" font-size="11" fill="{INK2}">{note}</text>
<text x="664" y="{y+23}" text-anchor="end" font-size="13" fill="{MUTED}">{srv}</text>
</g>''')
        if i < len(steps) - 1:
            rows.append(f'<path d="M42 {y+36} v10" stroke="{BASELINE}" stroke-width="1.5"/>')
    return f'<svg viewBox="0 0 700 {16+len(steps)*46}" width="100%" role="img">{"".join(rows)}</svg>'


def tiles(items):
    return '<div class="tiles">' + "".join(
        f'<div class="tile"><div class="tv" style="color:{c}">{v}</div>'
        f'<div class="tl">{l}</div><div class="ts">{s}</div></div>'
        for v, l, s, c in items) + "</div>"


VISUAL = f'''
<section class="cover">
  <div class="ctag">Build-A-Thon SRM · 자율 네트워크 오케스트레이션</div>
  <h1>MCP 기반 5G 슬라이스<br>자율 오케스트레이션 설계서</h1>
  <p class="csub">MCP 서버 5개 · 도구 21개 · 3인 병렬 개발</p>
  <div class="cmeta">
    <div><b>수록</b> 도구 명세서 · 구현 설계서 · 역할 분담</div>
    <div><b>저장소</b> DBAJK/SRM-main-mcp</div>
    <div><b>작성</b> 2026-09-21</div>
  </div>
</section>

<section class="vs">
  <h2>한 장 요약</h2>
  {tiles([("5", "MCP 서버", "observe · policy · market · audit · feedback", S1),
          ("21", "도구", "입출력 계약 전체 명세", S1),
          ("4", "에이전트 생산 값", "이 넷이 연구의 기여", S2),
          ("31", "검증 지적", "정정 11 · 값 유실 20", CRITICAL)])}

  <h3>아키텍처와 담당</h3>
  {arch_svg()}
  <p class="cap">서버끼리는 직접 대화하지 않는다. 모든 값은 오케스트레이터를 거친다 \u2014
  그래서 하단 네 값만이 어느 서버에도 코드가 없는, 에이전트 고유의 산출물이다.</p>
</section>

<section class="vs">
  <h2>한 스텝의 제어 루프</h2>
  <p class="lead">MCP는 도구를 줄 뿐 <b>호출 순서를 강제하지 않는다.</b>
  따라서 루프는 파이썬이 돌리고, LLM은 2단계에서만 호출한다.</p>
  {flow_svg()}
  <div class="two">
    <div class="note"><b>채점은 1스텝 지연된다</b><br>
      t의 결정은 t+1의 관측으로 평가된다. <code>report_outcome</code>은 반드시
      <code>step()</code> 이후. 에피소드 마지막 결정은 채점 불가 \u2014 60스텝이면 유효 표본 59.</div>
    <div class="note"><b>기록이 실행보다 먼저다</b><br>
      3 → 4 순서. 판단만 하고 실행에 실패한 경우도 남는다. 조달(2b)만 예외이며,
      <code>record_decision</code>이 <code>slice_id</code>를 인자로 받기 때문이다.</div>
  </div>
</section>

<section class="vs">
  <h2>환경 검증 \u2014 실험에 신호가 있는가</h2>

  <h3>재배분으로 해결 불가한 스텝의 비율</h3>
  {legend([("조정 전", S2), ("조정 후", S1)])}
  {CH_PRESSURE}
  <p class="cap"><code>demand_pressure &gt; 1.0</code>은 <i>어떤 배분으로도 전 슬라이스 SLA를
  지킬 수 없다</i>를 뜻한다. 조정 전에는 <b>평시의 53%</b>가 그 상태였다 \u2014 SLA 지표가 포화되어
  비교군 간 차이가 드러나지 않는다. 상수 3개(<code>CAPACITY_BASE</code> 1.6,
  <code>CAPACITY_MAX</code> 2.6, <code>START_HOUR</code> 0)를 조정해 평시 5.6%로 내렸다.
  원 코드의 상수는 건드리지 않았다.</p>

  <div class="kv">
    <div><span>평시</span><b>94%가 재배분으로 해결 가능</b> → 조달 없이 푸는 것이 정답</div>
    <div><span>이벤트</span><b>28~34%가 재배분 불가</b> → 여기서만 조달이 정답</div>
  </div>

  <h3>트래픽 구성비 \u2014 상황 인지의 실제 근거</h3>
  {legend([("eMBB", S1), ("URLLC", S2), ("mMTC", S3)])}
  {CH_SHARE}
  <p class="cap">시간 요인(±30%)이 이벤트 효과와 비슷한 크기라 <b>절대량으로는 평시 피크와
  비상이 구분되지 않는다.</b> 세 슬라이스에 같은 배수가 곱해지므로 <b>구성비는 시간 요인에
  불변</b>이며, 여기서 신호가 나온다.</p>

  <h3>구성비만으로 얻는 상황 인지 정확도</h3>
  {CH_PERCEPT}
  <p class="cap">최근접중심 분류 기준 전체 <b>71.7%</b>. <code>normal</code>이 50.5%로 가장 낮다 \u2014
  나머지 셋 사이에 끼어 있어 잡음이 어느 쪽으로든 밀어낸다. <b>오탐이 구조적으로 많다</b>는 뜻이며,
  상황 판단 자체의 확신(<code>confidence.situation</code>)을 에스컬레이션 경로에 넣어야 하는 근거다.
  천장이 100%가 아니라는 점이 오히려 비교군 간 차이가 드러날 여지를 만든다.</p>
</section>

<section class="vs">
  <h2>검증 이력</h2>
  <p class="lead">설계는 세 번 검증했다. 각 단계에서 나온 지적이 다음 단계의 입력이 됐다.</p>
  <div class="steps">
    <div class="st"><b>1차 \u2014 코드 대조</b><span class="n">정정 A~K · 11건</span>
      기존 코드가 설계 전제와 어긋나는 것. <code>rule_based</code>가 정답 플래그를 직접 읽음,
      벽시계 사용, 벤더 데이터 두 벌, TF 미설치, 조달이 환경에 무반영.</div>
    <div class="st"><b>2차 \u2014 도구 계약</b><span class="n">V2~V10 · 9건</span>
      명세 자체의 값 유실. 생산자 없는 소비 4건, 소비자 없는 생산 5건.
      에스컬레이션 스텝이 통계에서 소멸하는 것이 가장 위험했다.</div>
    <div class="st"><b>3차 \u2014 전면 재검증</b><span class="n">W1~W11 · 11건</span>
      <code>capacity</code> 도입의 파급과 사각지대. 실행 생명주기 미정,
      ③이 현재 스텝을 모름, 비용 단위 4배 부풀림.</div>
  </div>
  <p class="cap"><b>죽은 기능은 계약의 구멍을 감춘다.</b> 정정 K로 조달이 살아나자
  W1·W2·W3가 동시에 드러났다. 1차 범위에서 제외한 <code>dqn</code>도 2차에 넣는 순간
  같은 일이 일어난다.</p>
</section>

<section class="vs">
  <h2>3인 병렬 개발</h2>
  <div class="roles">
    <div class="rl" style="border-color:{S1}">
      <div class="rh" style="color:{S1}">A \u2014 환경 · 측정</div>
      <div class="rb">① observe · ④ audit · 실험 하네스</div>
      <div class="rn">995줄 데모를 관측 가능한 시뮬레이터로 해체하고 논문의 숫자를 생산한다.
      <b>Day 0에 <code>srm_mcp/common/</code>을 먼저 내놓아야 B·C가 시작할 수 있다.</b></div>
    </div>
    <div class="rl" style="border-color:{S2}">
      <div class="rh" style="color:{S2}">B \u2014 모델 · 정책</div>
      <div class="rb">② policy · ③ market · ⑤ feedback</div>
      <div class="rn">TensorFlow를 되살리고 정책을 나란히 세운다.
      <b>0단계 모델 적재 검증이 전체의 전제</b> \u2014 Day 1 오전에 끝내고 공유.</div>
    </div>
    <div class="rl" style="border-color:{S3}">
      <div class="rh" style="color:{S3}">C \u2014 에이전트</div>
      <div class="rb">오케스트레이터 · 프롬프트 · 계약 검사</div>
      <div class="rn">코드량은 적고 반복 튜닝이 많다. <b>Day 1에 목 서버 5개</b>를 만들어
      본인이 막히지 않게 하고, 동시에 계약 검증 장치를 확보한다.</div>
    </div>
  </div>

  <h3>합류 지점</h3>
  <table class="ms">
    <tr><th>M1</th><td>배선</td><td>C의 루프가 <b>진짜 ③</b>을 호출해 벤더 5개 점수 수신</td></tr>
    <tr><th>M2</th><td>환경</td><td>동일 시드 2회 → <code>truth.jsonl</code> 바이트 동일 · fixtures 배포</td></tr>
    <tr><th>M3</th><td>폐루프</td><td>①②④⑤ 전부 진짜로 1스텝 왕복 + <code>outcome</code> 기록</td></tr>
    <tr><th>M3.5</th><td>계약</td><td><code>check_contract.py</code> 검사 4개 통과 · 값 유실 0건</td></tr>
    <tr><th>M4</th><td>비교군</td><td>4개 arm이 <code>mixed</code> 120스텝 완주 · 누출 검사 0건</td></tr>
    <tr><th>M5</th><td>결과</td><td>60회 실행 + 지표 산출 + 대표 그래프</td></tr>
  </table>
  <p class="cap"><b>M2에서 반드시 멈추고 확인한다.</b> 재현이 안 되는 채로 M3~M5를 쌓으면
  마지막에 전부 다시 돌려야 한다.</p>
</section>
'''


# ── CSS ─────────────────────────────────────────────────────────────
CSS = f'''
@page {{ size: A4; margin: 17mm 15mm 16mm; }}
@page :first {{ margin: 0; }}
* {{ box-sizing: border-box; }}
body {{
  font-family: "Malgun Gothic", "맑은 고딕", -apple-system, "Segoe UI", sans-serif;
  color: {INK}; background: #fff; margin: 0;
  font-size: 10.2pt; line-height: 1.62; word-break: keep-all;
}}
code, pre, .mono {{ font-family: "Cascadia Mono", Consolas, "D2Coding", monospace; }}

/* ── 표지 ── */
.cover {{
  height: 297mm; padding: 42mm 24mm 24mm; page-break-after: always;
  background: linear-gradient(160deg, {PLANE} 0%, #fff 58%);
  border-top: 9px solid {S1};
}}
.ctag {{ font-size: 10.5pt; color: {S1}; font-weight: 700; letter-spacing: .02em; }}
.cover h1 {{ font-size: 30pt; line-height: 1.28; margin: 14mm 0 6mm; letter-spacing: -.02em; }}
.csub {{ font-size: 12.5pt; color: {INK2}; margin: 0; }}
.cmeta {{ margin-top: 42mm; font-size: 10pt; color: {INK2}; border-top: 1px solid {GRID}; padding-top: 6mm; }}
.cmeta div {{ margin: 2.4mm 0; }}
.cmeta b {{ color: {MUTED}; font-weight: 600; display: inline-block; width: 19mm; }}

/* ── 시각 섹션 ── */
.vs {{ page-break-after: always; }}
.vs h2 {{
  font-size: 17pt; margin: 0 0 5mm; padding-bottom: 2.5mm;
  border-bottom: 2.5px solid {INK}; letter-spacing: -.01em;
}}
.vs h3 {{ font-size: 12.5pt; margin: 8mm 0 3mm; color: {INK}; }}
.lead {{ font-size: 10.6pt; color: {INK2}; margin: 0 0 5mm; }}
.cap {{ font-size: 9.3pt; color: {INK2}; line-height: 1.6; margin: 3mm 0 0;
        padding-left: 3mm; border-left: 2.5px solid {GRID}; }}
.legend {{ display: flex; gap: 14px; margin: 0 0 2mm 124px; font-size: 9.6pt; color: {INK2}; }}
.lg {{ display: inline-flex; align-items: center; gap: 5px; }}
.sw {{ width: 11px; height: 11px; border-radius: 3px; display: inline-block; }}

.tiles {{ display: flex; gap: 4mm; margin: 0 0 8mm; }}
.tile {{ flex: 1; border: 1px solid {GRID}; border-radius: 8px; padding: 4mm 4mm 3.4mm; background: {SURFACE}; }}
.tv {{ font-size: 25pt; font-weight: 700; line-height: 1; letter-spacing: -.02em; }}
.tl {{ font-size: 10pt; font-weight: 700; margin-top: 2mm; }}
.ts {{ font-size: 8.6pt; color: {MUTED}; margin-top: 1mm; line-height: 1.45; }}

.two {{ display: flex; gap: 4mm; margin-top: 5mm; }}
.note {{ flex: 1; font-size: 9.4pt; color: {INK2}; background: {PLANE};
         border-radius: 7px; padding: 3.4mm 4mm; line-height: 1.58; }}
.note b {{ color: {INK}; }}

.kv {{ margin: 5mm 0 0; }}
.kv div {{ font-size: 10pt; padding: 2.6mm 0; border-bottom: 1px solid {GRID}; }}
.kv span {{ display: inline-block; width: 22mm; color: {MUTED}; font-size: 9.4pt; }}

.steps {{ display: flex; gap: 4mm; }}
.st {{ flex: 1; border-top: 3px solid {S1}; padding-top: 3mm; font-size: 9.4pt;
       color: {INK2}; line-height: 1.58; }}
.st:nth-child(2) {{ border-color: {S2}; }}
.st:nth-child(3) {{ border-color: {CRITICAL}; }}
.st b {{ display: block; font-size: 10.4pt; color: {INK}; }}
.st .n {{ display: block; font-size: 9pt; color: {MUTED}; margin: .6mm 0 2mm; }}

.roles {{ display: flex; gap: 4mm; }}
.rl {{ flex: 1; border: 1px solid {GRID}; border-top-width: 4px; border-radius: 8px; padding: 4mm; }}
.rh {{ font-size: 11.5pt; font-weight: 700; }}
.rb {{ font-size: 9.6pt; color: {INK2}; margin: 1.6mm 0 2.6mm; }}
.rn {{ font-size: 9.2pt; color: {INK2}; line-height: 1.58; }}
.rn b {{ color: {INK}; }}
table.ms {{ width: 100%; border-collapse: collapse; font-size: 9.7pt; margin-top: 2mm; }}
table.ms th {{ width: 13mm; text-align: left; color: {S1}; font-size: 10pt; padding: 2.2mm 0; }}
table.ms td {{ padding: 2.2mm 0; border-bottom: 1px solid {GRID}; }}
table.ms td:first-of-type {{ width: 20mm; color: {MUTED}; }}

/* ── 본문 ── */
.doc {{ page-break-before: always; }}
.layer {{ height: 240mm; display:flex; align-items:center; }}
.lay {{ font-size: 34pt; font-weight: 700; color: {S1}; letter-spacing:-.02em; }}
.doc-hd {{ border-left: 5px solid {S1}; padding: 1mm 0 1mm 5mm; margin-bottom: 7mm; }}
.doc-hd .t {{ font-size: 19pt; font-weight: 700; letter-spacing: -.02em; }}
.doc-hd .s {{ font-size: 9.6pt; color: {MUTED}; margin-top: 1mm; }}
.doc h1 {{ font-size: 15.5pt; margin: 9mm 0 3.5mm; padding-bottom: 2mm;
           border-bottom: 2px solid {INK}; page-break-after: avoid; }}
.doc h2 {{ font-size: 13pt; margin: 8mm 0 3mm; padding-bottom: 1.6mm;
           border-bottom: 1px solid {GRID}; page-break-after: avoid; }}
.doc h3 {{ font-size: 11.4pt; margin: 6mm 0 2.4mm; page-break-after: avoid; }}
.doc h4 {{ font-size: 10.4pt; margin: 5mm 0 2mm; color: {INK2}; page-break-after: avoid; }}
.doc p, .doc li {{ font-size: 9.9pt; }}
.doc blockquote {{ margin: 3mm 0; padding: 2.6mm 4mm; background: {PLANE};
                   border-left: 3px solid {BASELINE}; border-radius: 0 6px 6px 0;
                   color: {INK2}; font-size: 9.5pt; }}
.doc blockquote p {{ margin: 1mm 0; font-size: 9.5pt; }}
table {{ width: 100%; border-collapse: collapse; margin: 3mm 0; font-size: 9.1pt;
         page-break-inside: avoid; }}
th {{ background: {PLANE}; text-align: left; font-weight: 700; }}
th, td {{ border: 1px solid {GRID}; padding: 1.8mm 2.4mm; vertical-align: top; }}
pre {{ background: {PLANE}; border: 1px solid {GRID}; border-radius: 6px;
       padding: 3mm 3.4mm; overflow-x: auto; font-size: 8.5pt; line-height: 1.5;
       page-break-inside: avoid; white-space: pre-wrap; word-break: break-all; }}
code {{ background: rgba(11,11,11,.055); padding: .3mm 1.1mm; border-radius: 3px; font-size: .92em; }}
pre code {{ background: none; padding: 0; font-size: 1em; }}
hr {{ border: 0; border-top: 1px solid {GRID}; margin: 6mm 0; }}
a {{ color: {S1}; text-decoration: none; }}
svg {{ page-break-inside: avoid; }}
h1, h2, h3, h4 {{ line-height: 1.34; }}
'''


CL = ROOT / "claude"

# claude/ 가 정본. 읽는 순서 = PDF 수록 순서.
DOC_ORDER = [
    ("계약", "spec/common.md"), ("계약", "spec/tools.md"),
    ("계약", "spec/observe.md"), ("계약", "spec/policy.md"),
    ("계약", "spec/market.md"), ("계약", "spec/audit.md"),
    ("계약", "spec/feedback.md"),
    ("흐름", "flow/loop.md"), ("흐름", "flow/data-chain.md"),
    ("흐름", "flow/errors.md"), ("흐름", "flow/forbidden.md"),
    ("구축", "build/runtime.md"), ("구축", "build/extract.md"), ("구축", "build/store.md"),
    ("구축", "build/formulas.md"), ("구축", "build/step0.md"),
    ("구축", "build/order.md"),
    ("근거", "rationale/corrections.md"), ("근거", "rationale/verification.md"),
    ("근거", "rationale/environment.md"), ("근거", "rationale/observe.md"),
    ("근거", "rationale/policy.md"), ("근거", "rationale/market.md"),
    ("근거", "rationale/audit.md"), ("근거", "rationale/feedback.md"),
    ("근거", "rationale/context-budget.md"),
    ("분담", "team/roles.md"),
]


def md2html(text):
    import markdown
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    return markdown.markdown(
        text, extensions=["tables", "fenced_code", "sane_lists", "attr_list"])


def render_docs():
    parts, seen = [], None
    for layer, rel in DOC_ORDER:
        src = (CL / rel).read_text(encoding="utf-8")
        m = re.match(r"\s*#\s+(.+)", re.sub(r"<!--.*?-->", "", src, flags=re.S))
        title = m.group(1).strip() if m else rel
        clean = re.sub(r"<!--.*?-->", "", src, flags=re.S)
        body = re.sub(r"\A\s*#\s+.*?\n", "", clean, count=1)
        if layer != seen:
            parts.append(f'<section class="doc layer"><div class="lay">{layer}</div></section>')
            seen = layer
        parts.append(f'<section class="doc"><div class="doc-hd">'
                     f'<div class="t">{title}</div><div class="s">claude/{rel}</div></div>'
                     f'{md2html(body)}</section>')
    return "\n".join(parts)


def main():
    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    html = (f'<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">'
            f'<title>SRM MCP 설계서</title><style>{CSS}</style></head><body>'
            f'{VISUAL}{render_docs()}</body></html>')
    OUT_HTML.write_text(html, encoding="utf-8")
    print(f"HTML  {OUT_HTML}  ({len(html)//1024} KB)")

    chrome = None
    for c in [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"]:
        if os.path.exists(c):
            chrome = c
            break
    if not chrome:
        print("브라우저를 찾지 못함 - HTML만 생성", file=sys.stderr)
        return 1

    cmd = [chrome, "--headless", "--disable-gpu", "--no-sandbox",
           "--no-pdf-header-footer", "--print-to-pdf-no-header",
           f"--print-to-pdf={OUT_PDF}", OUT_HTML.as_uri()]
    r = subprocess.run(cmd, capture_output=True, timeout=240)
    if OUT_PDF.exists():
        print(f"PDF   {OUT_PDF}  ({OUT_PDF.stat().st_size//1024} KB)")
        return 0
    print(r.stderr[-1500:].decode("utf-8","replace"), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
