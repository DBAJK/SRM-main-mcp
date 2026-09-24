#!/usr/bin/env python
"""본실험 배치 — 비교군 × 판단자 × 시나리오 × 시드를 차례로 돌리고 한곳에 모은다. (C · workplan C-5)

    .venv310\\Scripts\\python.exe tools\\run_matrix.py                 계획과 추정만 출력 (기본)
    .venv310\\Scripts\\python.exe tools\\run_matrix.py --go            실제로 돈다
    .venv310\\Scripts\\python.exe tools\\run_matrix.py --go --resume   끊긴 데서 이어서

**`--go` 없이는 아무것도 실행하지 않는다.** 전체 행렬은 LLM 호출이 수천 회라, 무엇을
얼마나 돌릴지 먼저 보이는 게 기본이어야 한다.

한 칸 = run.py 한 번 (별도 프로세스). 칸마다 --fresh · --memory-mode cold 로 격리한다 —
같은 시드면 같은 결과가 나와야 비교가 성립한다 (run.py _reset_vendors).

칸의 종류 (변형)
    baseline            상황=정답, LLM 없음                 (판단자 무관 — 한 번만)
    arm1_rule · arm1_llm   상황=에이전트, 정책·조달 규칙, 개입 없음
    arm2_rule · arm2_llm   + 정책 선택
    proposed_rule · proposed_llm  + 신뢰도 기반 개입         (고정 루프)
    proposed_orch       LLM 이 도구를 직접 든다              (오케스트레이터)

라벨의 첫 토큰이 비교군 동작을 정한다 (agent/arms kind_of). 판단자가 달라도 run_id 가
겹치지 않는다.

산출
    runs/_matrix/<이름>/plan.json      칸 목록
    runs/_matrix/<이름>/state.json     칸별 종료 코드 · 소요 · 사용량 (재시작 지점)
    runs/_matrix/<이름>/logs/<run_id>.log
    runs/_matrix/<이름>/summary.json · summary.csv   칸별 지표 한 줄씩

지표는 에이전트가 끝난 뒤 장부와 정답을 직접 읽어 만든다 (eval.breakdown · score).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
PYTHON = ROOT / ".venv310" / "Scripts" / "python.exe"

SCENARIOS = ("normal", "emergency", "special_event", "iot_surge", "mixed")
STEPS = {"mixed": 120}                       # 그 외 60 (observe env total_steps)
VARIANTS = ("baseline", "arm1_rule", "arm1_llm", "arm2_rule", "arm2_llm",
            "proposed_rule", "proposed_llm", "proposed_orch")

# 추정용 실측 (2026-09-23~24, sonnet). 구독 사용량 환산이며 별도 청구가 아니다.
PER_STEP = {                                 # (초, 사용량 환산 $)
    "rule": (0.05, 0.0),
    "llm": (17.4, 0.048),
    "orch": (40.0, 0.09),
}
STARTUP_SEC = 60                             # 서버 5개 기동 (TF 적재)


@dataclass
class Cell:
    variant: str
    scenario: str
    seed: int

    @property
    def arm(self) -> str:                    # run.py --arm 라벨
        return self.variant

    @property
    def mode(self) -> str:                   # rule · llm · orch
        if self.variant == "baseline":
            return "rule"
        return self.variant.rsplit("_", 1)[1]

    @property
    def run_id(self) -> str:
        return f"{self.arm}-{self.scenario}-s{self.seed}"

    def steps(self, limit: Optional[int]) -> int:
        n = STEPS.get(self.scenario, 60)
        return min(n, limit) if limit else n

    def argv(self, limit: Optional[int], model: str) -> list[str]:
        a = [str(PYTHON), "run.py", "--arm", self.arm, "--scenario", self.scenario,
             "--seed", str(self.seed), "--fresh", "--memory-mode", "cold"]
        if self.mode == "orch":
            a += ["--driver", "orchestrator", "--llm-model", model, "--quiet"]
        else:
            a += ["--driver", "fixed", "--backend", "mcp",
                  "--decider", "llm" if self.mode == "llm" else "rule"]
            if self.mode == "llm":
                a += ["--llm-model", model]
        if limit:
            a += ["--steps", str(limit)]
        return a

    def estimate(self, limit: Optional[int]) -> tuple[float, float]:
        sec, usd = PER_STEP[self.mode]
        n = self.steps(limit)
        return STARTUP_SEC + n * sec, n * usd


def build_plan(variants, scenarios, seeds) -> list[Cell]:
    # 싼 것부터 — LLM 없는 칸의 결과가 먼저 나온다
    order = {"rule": 0, "llm": 1, "orch": 2}
    cells = [Cell(v, s, sd) for v in variants for s in scenarios for sd in seeds]
    return sorted(cells, key=lambda c: (order[c.mode], VARIANTS.index(c.variant),
                                        SCENARIOS.index(c.scenario), c.seed))


# ── 실행 ────────────────────────────────────────────────────────────
_USD = re.compile(r"비용 \$([0-9.]+)")


def run_cell(c: Cell, limit, model, log_dir: Path) -> dict:
    log = log_dir / f"{c.run_id}.log"
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
    t0 = time.monotonic()
    usd = 0.0
    with open(log, "w", encoding="utf-8") as fh:
        p = subprocess.Popen(c.argv(limit, model), cwd=str(ROOT), env=env,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, encoding="utf-8", errors="replace", bufsize=1)
        for line in p.stdout:
            fh.write(line)
            m = _USD.search(line)
            if m:
                usd = float(m.group(1))
        p.wait()
    return {"exit": p.returncode, "elapsed_sec": round(time.monotonic() - t0, 1),
            "usd_equiv": round(usd, 4), "log": str(log.relative_to(ROOT))}


def collect(c: Cell) -> dict:
    """장부 · 정답에서 칸 하나의 지표를 뽑는다. 서버가 필요 없다."""
    from eval import breakdown                         # C 소유 — score.py 를 감싼다
    row = {"variant": c.variant, "scenario": c.scenario, "seed": c.seed, "run_id": c.run_id}
    try:
        b = breakdown.breakdown(c.run_id)
    except Exception as e:                             # noqa: BLE001 — 칸 하나가 전체를 죽이지 않게
        row["collect_error"] = f"{type(e).__name__}: {e}"
        return row

    book = json.loads((ROOT / "runs" / c.run_id / "decisions.json").read_text(encoding="utf-8"))
    decs = [r for r in book["decisions"] if r.get("kind") == "decision"]
    escs = [r for r in book["decisions"] if r.get("kind") == "escalation"]
    s, sp = b["score"], b["sla_split"]
    row.update(
        arm_kind=(b.get("config") or {}).get("arm_kind"),
        steps=len(decs),
        interventions=len(escs),
        intervention_rate=round(len(escs) / len(decs), 4) if decs else None,
        sla_scored=sp["scored"], sla_violations=sp["violations"],
        sla_avoidable=sp["avoidable"], sla_structural=sp["structural"],
        procurements=sum(1 for r in decs if r.get("slice_id")),
        procurement_cost=round(sum(float(r.get("cost_total") or 0) for r in decs), 2),
        perception_accuracy=s["perception_accuracy"]["accuracy"],
        escalation_precision=s["escalation_precision"]["precision"],
        referee_error_steps=b["referee"]["excluded"],
    )
    return row


# ── 진입점 ──────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description="본실험 배치 (기본: 계획만 출력)")
    ap.add_argument("--name", default=datetime.now().strftime("%Y%m%d"),
                    help="runs/_matrix/<name>/ 에 모인다")
    ap.add_argument("--variants", default=",".join(VARIANTS))
    ap.add_argument("--scenarios", default=",".join(SCENARIOS))
    ap.add_argument("--seeds", default="0,1,2")
    ap.add_argument("--steps", type=int, default=None, help="칸마다 스텝 상한 (시험용)")
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--budget-usd", type=float, default=20.0,
                    help="사용량 환산 누적 상한. 넘으면 다음 칸을 시작하지 않는다")
    ap.add_argument("--go", action="store_true", help="실제로 돈다. 없으면 계획만")
    ap.add_argument("--resume", action="store_true", help="state.json 에서 성공한 칸은 건너뛴다")
    args = ap.parse_args()

    variants = [v for v in args.variants.split(",") if v]
    bad = [v for v in variants if v not in VARIANTS]
    if bad:
        print(f"[오류] 모르는 변형 {bad}. 가능: {', '.join(VARIANTS)}", file=sys.stderr)
        return 1
    scenarios = [s for s in args.scenarios.split(",") if s]
    seeds = [int(x) for x in args.seeds.split(",") if x != ""]
    plan = build_plan(variants, scenarios, seeds)

    out = ROOT / "runs" / "_matrix" / args.name
    state_path = out / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else {}

    todo = [c for c in plan if not (args.resume and state.get(c.run_id, {}).get("exit") == 0)]
    tot_sec = sum(c.estimate(args.steps)[0] for c in todo)
    tot_usd = sum(c.estimate(args.steps)[1] for c in todo)
    by_mode: dict = {}
    for c in todo:
        by_mode[c.mode] = by_mode.get(c.mode, 0) + 1

    print(f"행렬 {args.name} · 칸 {len(plan)} (이번에 돌 칸 {len(todo)})")
    print(f"  변형   {', '.join(variants)}")
    print(f"  시나리오 {', '.join(scenarios)} · 시드 {seeds}"
          + (f" · 스텝 상한 {args.steps}" if args.steps else ""))
    print(f"  종류별  " + " · ".join(f"{k} {v}칸" for k, v in by_mode.items()))
    print(f"  추정    {tot_sec / 3600:.1f}시간 · 사용량 환산 ${tot_usd:.2f} "
          f"(구독 사용량 기준 · 별도 청구 아님) · 상한 ${args.budget_usd:.2f}")
    if tot_usd > args.budget_usd:
        print(f"  ⚠ 추정이 상한을 넘는다 — 상한에 닿으면 그 뒤 칸은 시작하지 않는다")

    if not args.go:
        print("\n계획만 출력했다. 실행하려면 --go")
        for c in todo[:12]:
            print("   ", " ".join(c.argv(args.steps, args.model)[1:]))
        if len(todo) > 12:
            print(f"    … 외 {len(todo) - 12}칸")
        return 0

    (out / "logs").mkdir(parents=True, exist_ok=True)
    (out / "plan.json").write_text(json.dumps([asdict(c) for c in plan], indent=2), encoding="utf-8")
    spent = sum(v.get("usd_equiv", 0) for v in state.values())

    for i, c in enumerate(todo, 1):
        if spent >= args.budget_usd:
            print(f"[상한] 누적 ${spent:.2f} ≥ ${args.budget_usd:.2f} — 남은 {len(todo) - i + 1}칸 보류. "
                  "--resume --budget-usd 로 이어간다")
            break
        print(f"[{i}/{len(todo)}] {c.run_id} ({c.mode}) …", flush=True)
        r = run_cell(c, args.steps, args.model, out / "logs")
        spent += r["usd_equiv"]
        state[c.run_id] = {**r, "variant": c.variant, "scenario": c.scenario, "seed": c.seed,
                           "finished": datetime.now().isoformat(timespec="seconds")}
        state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
        mark = "완료" if r["exit"] == 0 else f"실패(종료 {r['exit']}) — {r['log']}"
        print(f"       {mark} · {r['elapsed_sec']}초 · ${r['usd_equiv']:.3f} · 누적 ${spent:.2f}")

    # 요약 — 성공한 칸 전부 (이번에 안 돈 칸도 state 에 있으면 포함)
    rows = [collect(c) for c in plan if state.get(c.run_id, {}).get("exit") == 0]
    (out / "summary.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    if rows:
        keys = sorted({k for r in rows for k in r}, key=lambda k: (k not in rows[0], k))
        with open(out / "summary.csv", "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(rows)
    print(f"\n요약 {len(rows)}칸 → {(out / 'summary.csv').relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
