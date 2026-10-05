#!/usr/bin/env python
"""run_matrix 의 규칙 칸을 한 프로세스 안에서 돌린다 — MCP 전송만 뺀 같은 코드. (C)

    .venv310\\Scripts\\python.exe tools\\fast_matrix.py --name exp1
    .venv310\\Scripts\\python.exe tools\\fast_matrix.py --name exp2 --env SLICE_TARGET_TABLE=original
    .venv310\\Scripts\\python.exe tools\\fast_matrix.py --name exp1 --check after-F   # 동등성 확인

왜 — run_matrix 는 칸마다 서버 5개를 stdio 로 띄워 칸당 ~35초(60칸 35분)라 반복 실험에 느리다.
여기서는 서버 모듈의 도구 함수를 같은 프로세스에서 직접 부른다. 루프(agent/loop.py) · 판단자 ·
비교군 · 서버 코드는 **그대로** 쓰고 바뀌는 것은 전송뿐이다:

  · 인자와 반환을 JSON 으로 한 번 왕복시킨다 — MCP 직렬화와 같은 값이 오가고, 서버가 돌려준 객체를
    에이전트가 공유하지 않는다.
  · 칸마다 run.py --fresh --memory-mode cold 와 같은 초기화를 한다: runs/<run_id> 삭제 ·
    벤더 평판 초기화(bootstrap --force) · SLICE_RUN_ID · ③의 조달 가드(_last_step) 리셋.
  · ② 모델은 서버 기동 때처럼 한 번 적재한다 (policy/server.py __main__).

규칙 판단자 칸(baseline · arm1_rule · arm2_rule · proposed_rule)만 돈다. LLM · 오케스트레이터 칸은 run_matrix 로.
결과 폴더 형식(raw/ · state.json · summary.json · summary.csv)은 run_matrix 와 같아 census_runs ·
compare_matrix 가 그대로 읽는다. `--check <매트릭스>` 는 같은 칸의 summary 를 비교해 다르면 실패한다.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RULE_VARIANTS = ("baseline", "arm1_rule", "arm2_rule", "proposed_rule")


def _set_env(pairs: list[str]) -> dict:
    env = {}
    for pair in pairs:
        key, _, value = pair.partition("=")
        if not key or not _:
            raise SystemExit(f"--env 는 KEY=VALUE 형식이다: {pair!r}")
        os.environ[key] = value
        env[key] = value
    return env


class InprocBackend:
    """`call(server, tool, args)` — McpBackend 와 같은 인터페이스. 서버 모듈을 직접 부른다."""

    def __init__(self, modules: dict):
        self._modules = modules

    def call(self, server: str, tool: str, args: dict):
        fn = getattr(self._modules[server], tool)
        fn = getattr(fn, "fn", fn)                     # fastmcp 버전에 따라 Tool 객체일 수 있다
        out = fn(**json.loads(json.dumps(args)))
        return json.loads(json.dumps(out))


def load_servers() -> dict:
    """서버 모듈 5개. 환경변수(SLICE_MEMORY_MODE · SLICE_DESC_MODE)를 먼저 정한 뒤 부른다."""
    from srm_mcp.audit import server as audit
    from srm_mcp.feedback import server as feedback
    from srm_mcp.market import server as market
    from srm_mcp.observe import server as observe
    from srm_mcp.policy import classify, lstm
    from srm_mcp.policy import server as policy
    with contextlib.redirect_stdout(io.StringIO()):
        lstm.load()
        classify.load()
    print(f"② 모델: lstm={lstm.available()[0]} · classifier={classify.available()[0]}")
    return {"observe": observe, "policy": policy, "market": market,
            "audit": audit, "feedback": feedback}


def run_cell(cell, modules: dict, limit, extra_env: dict) -> dict:
    """run.py --driver fixed --backend mcp --decider rule --fresh --memory-mode cold 한 번과 같다."""
    from agent import arms
    from agent.deciders import rule as rule_mod
    from agent.guard import Guard
    from agent.loop import run_episode
    from agent.tools import Tools
    from bootstrap_vendors import bootstrap

    run_id = cell.run_id
    book = ROOT / "runs" / run_id
    if book.exists():
        shutil.rmtree(book)
    with contextlib.redirect_stdout(io.StringIO()):
        if bootstrap(force=True) != 0:
            raise RuntimeError("벤더 부트스트랩 실패")
    os.environ["SLICE_RUN_ID"] = run_id
    modules["market"]._last_step = -1                  # 프로세스가 새로 뜬 것과 같게
    modules["market"]._procurements.clear()
    modules["feedback"]._run_id = None
    if hasattr(rule_mod, "reset_run"):
        rule_mod.reset_run(run_id)
    else:                                              # 반복 2 이전 판단자 (이전 코드와 비교할 때)
        rule_mod._traffic_seen.pop(run_id, None)

    kind = arms.kind_of(cell.variant)
    base = rule_mod.rule_decider if arms.needs_base_decider(kind) else None
    decide = arms.make(kind, base, ROOT)
    tools = Tools(InprocBackend(modules), Guard(enabled=True))
    config = {"scenario": cell.scenario, "seed": cell.seed, "arm": cell.variant, "arm_kind": kind,
              "repeat": None, "driver": "fixed", "intent": None, "steps_limit": limit,
              "desc_mode": os.environ.get("SLICE_DESC_MODE", "minimal"), "memory_mode": "cold",
              "backend": "inproc", "decider": "rule", "env": extra_env or None}
    t0 = time.monotonic()
    try:
        human = None
        if kind == "proposed":                         # run.py human_for 와 같다 — 개입 때 상황 라벨을 답하는 사람
            from agent.arms.baseline import human_label_responder
            human = human_label_responder(ROOT)
        run_episode(tools, decide, run_id, scenario=cell.scenario, seed=cell.seed,
                    max_steps=limit, config=config, human=human)
        code, err = 0, None
    except Exception as e:                             # noqa: BLE001 — 칸 하나가 전체를 죽이지 않게
        code, err = 1, f"{type(e).__name__}: {e}"
    return {"exit": code, "error": err, "elapsed_sec": round(time.monotonic() - t0, 2), "usd_equiv": 0.0}


def check(out: Path, ref_name: str) -> int:
    """같은 칸의 summary 숫자 열이 기준 매트릭스와 같은가. 다르면 칸·열을 찍고 1."""
    ref_path = ROOT / "runs" / "_matrix" / ref_name / "summary.json"
    ref = {r["run_id"]: r for r in json.loads(ref_path.read_text(encoding="utf-8"))}
    new = {r["run_id"]: r for r in json.loads((out / "summary.json").read_text(encoding="utf-8"))}
    skip = {"source", "run_id", "variant", "scenario", "seed", "n_repeats"}
    diffs, compared = [], 0
    for rid, row in new.items():
        if rid not in ref:
            continue
        compared += 1
        for k, v in row.items():
            if k in skip or k not in ref[rid]:
                continue
            if ref[rid][k] != v:
                diffs.append((rid, k, ref[rid][k], v))
    print(f"\n동등성 — 기준 {ref_name} 와 같은 칸 {compared}개 비교 · 다른 값 {len(diffs)}개")
    for d in diffs[:20]:
        print(f"  {d[0]:32} {d[1]:22} 기준 {d[2]!r} · 여기 {d[3]!r}")
    return 1 if diffs or not compared else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--name", required=True, help="runs/_matrix/<name>/ 에 모인다")
    ap.add_argument("--variants", default=",".join(RULE_VARIANTS))
    ap.add_argument("--scenarios", default="normal,emergency,special_event,iot_surge,mixed")
    ap.add_argument("--seeds", default="0,1,2")
    ap.add_argument("--steps", type=int, default=None, help="칸마다 스텝 상한 (시험용)")
    ap.add_argument("--env", action="append", default=[], metavar="KEY=VALUE",
                    help="이 실행에만 줄 환경변수 (예: SLICE_TARGET_TABLE=original). 여러 번 줄 수 있다")
    ap.add_argument("--summary-only", action="store_true",
                    help="돌리지 않고 raw/ · state.json 으로 summary 만 다시 만든다 (지표 열을 추가했을 때)")
    ap.add_argument("--check", default=None, metavar="MATRIX",
                    help="끝난 뒤 같은 칸의 summary 를 이 매트릭스와 비교한다 (동등성 확인)")
    args = ap.parse_args()

    os.environ["SLICE_MEMORY_MODE"] = "cold"
    os.environ.setdefault("SLICE_DESC_MODE", "minimal")
    extra_env = _set_env(args.env)

    from run_matrix import archive_cell, build_plan, write_summary
    variants = [v for v in args.variants.split(",") if v]
    bad = [v for v in variants if v not in RULE_VARIANTS]
    if bad:
        print(f"[오류] 규칙 칸만 돈다: {bad} 는 run_matrix 로", file=sys.stderr)
        return 1
    plan = build_plan(variants, [s for s in args.scenarios.split(",") if s],
                      [int(x) for x in args.seeds.split(",") if x != ""])

    out = ROOT / "runs" / "_matrix" / args.name
    if args.summary_only:
        state = json.loads((out / "state.json").read_text(encoding="utf-8"))
        write_summary(out, plan, state)
        return check(out, args.check) if args.check else 0
    (out / "raw").mkdir(parents=True, exist_ok=True)
    (out / "plan.json").write_text(json.dumps(
        {"runner": "fast_matrix (inproc)", "env": extra_env,
         "cells": [{"variant": c.variant, "scenario": c.scenario, "seed": c.seed, "run_id": c.run_id}
                   for c in plan]}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"행렬 {args.name} · 칸 {len(plan)} · inproc" + (f" · env {extra_env}" if extra_env else ""))

    modules = load_servers()
    state: dict = {}
    t0 = time.monotonic()
    for i, c in enumerate(plan, 1):
        r = run_cell(c, modules, args.steps, extra_env)
        r["raw"] = archive_cell(c, out / "raw")
        state[c.run_id] = {**r, "variant": c.variant, "scenario": c.scenario, "seed": c.seed,
                           "repeat": None, "finished": datetime.now().isoformat(timespec="seconds")}
        if r["exit"] != 0:
            print(f"[{i}/{len(plan)}] {c.run_id} 실패 — {r['error']}")
    (out / "state.json").write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    failed = sum(1 for v in state.values() if v["exit"] != 0)
    print(f"완료 {len(plan) - failed}/{len(plan)} · {time.monotonic() - t0:.0f}초")
    write_summary(out, plan, state)
    if args.check:
        return check(out, args.check)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
