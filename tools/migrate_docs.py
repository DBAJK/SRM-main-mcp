#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""docs/*.md -> claude/ 로 이관. claude/ 를 단일 정본으로 만든다.

spec/ 은 이미 docs/TOOLS.md 에서 나왔으므로 건드리지 않는다(별도 수정).
여기서는 claude/ 에 아직 없는 것만 옮긴다.
"""
import re, shutil, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
CL = ROOT / "claude"


def sections(md):
    lines = md.split("\n")
    idx = [i for i, l in enumerate(lines) if re.match(r"^##\s+|^###\s+", l)]
    out = []
    for k, i in enumerate(idx):
        j = idx[k + 1] if k + 1 < len(idx) else len(lines)
        lvl = 2 if lines[i].startswith("## ") else 3
        out.append((lvl, lines[i].lstrip("# ").strip(),
                    "\n".join(lines[i:j]).rstrip()))
    return out


def pick(md, rules):
    keep, rule = [], None
    for lvl, title, body in sections(md):
        if lvl == 2:
            rule = next((s for p, s in rules if re.search(p, title)), "MISS")
            if rule != "MISS":
                keep.append(body)
            else:
                rule = None
        elif rule is not None:
            if rule is None or rule == [] or rule is True:
                keep.append(body)
            elif isinstance(rule, list) and any(re.search(p, title) for p in rule):
                keep.append(body)
            elif rule == "ALL":
                keep.append(body)
    return "\n\n".join(keep)


def take(md, h2_patterns, demote=1):
    """지정한 H2들(하위 H3 포함)을 뽑고 제목 수준을 demote 단계 올린다."""
    keep, on = [], False
    for lvl, title, body in sections(md):
        if lvl == 2:
            on = any(re.search(p, title) for p in h2_patterns)
        if on:
            keep.append(body)
    txt = "\n\n".join(keep)
    if demote:
        txt = re.sub(r"^###", "#" * (3 - demote), txt, flags=re.M)
        txt = re.sub(r"^## ", "#" * (2 - demote) + " ", txt, flags=re.M)
    return txt


HDR = "<!-- docs/ 에서 이관. claude/ 가 정본이다. -->\n\n"

PLAN = [
    # (원본, 대상, H2 패턴들, 문서 제목, 한 줄 설명)
    ("MCP-design.md", "flow/loop.md", [r"^3\. 제어 루프 계약"],
     "제어 루프 계약",
     "1스텝의 시간 규약 · 액추에이터 · 고정 루프 · 컨텍스트 · 에스컬레이션 정의"),
    ("MCP-design.md", "build/runtime.md", [r"^2\. 런타임 구조"],
     "런타임 구조",
     "프로세스 구성 · 저장소 레이아웃 · 기술 스택"),
    ("MCP-design.md", "build/store.md", [r"^5\. 공유 데이터 스키마"],
     "공유 데이터 스키마",
     "실행 생명주기 · decisions.json · reliability.json · truth.jsonl · vendors.json"),
    ("MCP-design.md", "build/formulas.md", [r"^6\. 미결 사항 해소안"],
     "산출식",
     "내재적 신뢰도 · 경험적 신뢰도 · 도구 설명 수위"),
    ("MCP-design.md", "build/step0.md", [r"^7\. 0단계"],
     "0단계 — 모델 적재 검증",
     "TF 2.15.1 고정 · 검증 6항목 · 실패 시 분기"),
    ("MCP-design.md", "build/order.md", [r"^8\. 구현 순서", r"^9\. 남은 미결"],
     "구현 순서와 미결 사항",
     "단계별 완료 판정 · ③ 서버 골격 · 남은 결정"),
    ("MCP-design.md", "rationale/corrections.md", [r"^1\. 코드 대조 검증"],
     "정정 A~K — 코드 대조 검증",
     "기존 코드가 설계 전제와 어긋나는 것 11건"),
    ("MCP-design.md", "rationale/verification.md", [r"^1\.5 도구 계약 검증", r"^1\.6 전면 재검증"],
     "계약 검증 — 값 유실 20건",
     "생산자 없는 소비 · 소비자 없는 생산 · 근본 원인 3패턴 · 재발 방지"),
    ("MCP-design.md", "rationale/environment.md", [r"^1\.7 환경 검증"],
     "환경 검증 — 실험에 신호가 있는가",
     "시나리오별 압력 실측 · 상수 재조정 · 상황 인지 상한"),
]


def main():
    changed = []
    for src, dst, pats, title, sub in PLAN:
        md = (DOCS / src).read_text(encoding="utf-8")
        body = take(md, pats)
        if not body.strip():
            print(f"  !! 빈 결과: {dst} ({pats})", file=sys.stderr)
            continue
        p = CL / dst
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"{HDR}# {title}\n\n{sub}\n\n{body}\n", encoding="utf-8")
        changed.append((dst, len(body)))

    # 역할 분담 — 통째로
    roles = (DOCS / "ROLES.md").read_text(encoding="utf-8")
    roles = re.sub(r"\A#\s+.*?\n(?:>.*\n)*", "", roles).strip()
    p = CL / "team/roles.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"{HDR}# 3인 역할 분담\n\n"
                 f"저장소 `DBAJK/SRM-main-mcp` · 브랜치 `feature/kim` · `feature/lee` · `feature/choi`\n\n"
                 f"{roles}\n", encoding="utf-8")
    changed.append(("team/roles.md", len(roles)))

    # 1단계 원본 보존
    p = CL / "origin/decomposition.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(DOCS / "MCP-decomposition.md", p)
    changed.append(("origin/decomposition.md", p.stat().st_size))

    for d, n in changed:
        print(f"  {d:34} {n//1024:4} KB")


if __name__ == "__main__":
    main()
