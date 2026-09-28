#!/usr/bin/env python
"""본실험 배치 — 비교군 × 판단자 × 시나리오 × 시드를 차례로 돌리고 한곳에 모은다. (C · workplan C-5)

    .venv310\\Scripts\\python.exe tools\\run_matrix.py                 계획과 추정만 출력 (기본)
    .venv310\\Scripts\\python.exe tools\\run_matrix.py --go            실제로 돈다
    .venv310\\Scripts\\python.exe tools\\run_matrix.py --go --resume   끊긴 데서 이어서
    .venv310\\Scripts\\python.exe tools\\run_matrix.py --go --repeats 3  LLM 칸을 3회씩 (C-9)

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

반복 (--repeats N · C-9)
    LLM · 오케스트레이터 칸은 같은 시드여도 실행마다 다르다 (1번째 스텝의 우연이 "직전 5스텝
    요약"을 타고 에피소드를 정한다). 그래서 llm · orch 변형만 N 회 돌리고 (run_id `-rK` 접미,
    run.py --repeat K) 요약은 칸당 한 행으로 접는다 — 숫자 지표는 반복 평균, `sla_violation_rate`
    · `intervention_rate` · `perception_accuracy` 는 `_sd` 도 같이. 반복별 원본 행은
    summary_repeats.json 에 남긴다. 규칙 판단자 칸은 결정적이라(같은 시드 2회 완전 일치,
    2026-09-23) 반복하지 않는다. --repeat-rule 은 그 배선을 무료로 검증할 때만 쓴다 (sd 0).

산출
    runs/_matrix/<이름>/plan.json      칸 목록
    runs/_matrix/<이름>/state.json     칸별 종료 코드 · 소요 · 사용량 (재시작 지점)
    runs/_matrix/<이름>/logs/<run_id>.log
    runs/_matrix/<이름>/summary.json · summary.csv   칸별 지표 한 줄씩 (반복은 접어서)
    runs/_matrix/<이름>/summary_repeats.json         반복별 원본 행 (--repeats ≥ 2 일 때)
    runs/_matrix/<이름>/raw/<run_id>/  칸별 원본 보관본 (장부 · 정답 · 심판 · 추적) — C-20

run_id 가 `{arm}-{scenario}-s{seed}` 라 다음 매트릭스가 같은 칸을 돌리면 `runs/<run_id>/` 를
--fresh 로 지우고 덮어쓴다. 그래서 칸이 끝날 때마다 `runs/<run_id>/` 를 `raw/` 에 복사하고,
요약도 보관본이 있으면 그것을 읽는다 (--resume 으로 안 돈 칸도 이 매트릭스의 것으로 집계된다).
tools/compare_matrix.py 는 이미 raw/ 를 먼저 찾는다.

지표는 에이전트가 끝난 뒤 장부와 정답을 직접 읽어 만든다 (eval.breakdown · score).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import statistics as st
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# 팀 표준은 .venv310 (Python 3.10 + TF). 없는 PC 에서는 이 스크립트를 띄운 인터프리터로 칸을 돈다
# — 서버 5개는 .venv(3.14) 에서도 뜨고 LSTM 만 model_not_loaded 다.
_VENV310 = ROOT / ".venv310" / "Scripts" / "python.exe"
PYTHON = _VENV310 if _VENV310.is_file() else Path(sys.executable)

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
    repeat: Optional[int] = None             # 같은 조건의 K번째 (1부터). None 이면 단일

    @property
    def arm(self) -> str:                    # run.py --arm 라벨
        return self.variant

    @property
    def key(self) -> tuple:                  # 반복을 접는 단위
        return (self.variant, self.scenario, self.seed)

    @property
    def base_id(self) -> str:                # 반복 접미 없는 칸 이름
        return f"{self.arm}-{self.scenario}-s{self.seed}"

    @property
    def mode(self) -> str:                   # rule · llm · orch
        if self.variant == "baseline":
            return "rule"
        return self.variant.rsplit("_", 1)[1]

    @property
    def run_id(self) -> str:
        return self.base_id + (f"-r{self.repeat}" if self.repeat is not None else "")

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
        if self.repeat is not None:
            a += ["--repeat", str(self.repeat)]
        return a

    def estimate(self, limit: Optional[int]) -> tuple[float, float]:
        sec, usd = PER_STEP[self.mode]
        n = self.steps(limit)
        return STARTUP_SEC + n * sec, n * usd


def build_plan(variants, scenarios, seeds, repeats: int = 1, repeat_rule: bool = False) -> list[Cell]:
    # 싼 것부터 — LLM 없는 칸의 결과가 먼저 나온다. 반복은 칸 안에서 r1, r2 … 순.
    order = {"rule": 0, "llm": 1, "orch": 2}
    cells = []
    for v in variants:
        for s in scenarios:
            for sd in seeds:
                c = Cell(v, s, sd)
                if repeats > 1 and (c.mode != "rule" or repeat_rule):
                    cells += [Cell(v, s, sd, k) for k in range(1, repeats + 1)]
                else:
                    cells.append(c)
    return sorted(cells, key=lambda c: (order[c.mode], VARIANTS.index(c.variant),
                                        SCENARIOS.index(c.scenario), c.seed, c.repeat or 0))


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


def archive_cell(c: Cell, raw_dir: Path) -> Optional[str]:
    """`runs/<run_id>/` 를 `raw/<run_id>/` 로 복사한다 (C-20). 원본이 없으면 None.

    다음 매트릭스가 같은 run_id 를 --fresh 로 지우기 전에 이 매트릭스의 몫을 떼어 둔다.
    같은 칸을 다시 돌리면(--resume 없이) 보관본도 새것으로 바뀐다.
    """
    src = ROOT / "runs" / c.run_id
    if not src.is_dir():
        return None
    dst = raw_dir / c.run_id
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    return str(dst.relative_to(ROOT))


def collect(c: Cell, raw_dir: Path) -> dict:
    """장부 · 정답에서 칸 하나의 지표를 뽑는다. 서버가 필요 없다.

    raw/<run_id>/ 보관본이 있으면 그것을 읽는다 — runs/<run_id>/ 는 다른 매트릭스가
    덮어썼을 수 있다. eval 은 경로를 전부 paths.RUNS_DIR 로 푸므로 그 값만 잠시 바꾼다.
    """
    from eval import breakdown                         # C 소유 — score.py 를 감싼다
    from srm_mcp.common import paths
    row = {"variant": c.variant, "scenario": c.scenario, "seed": c.seed, "run_id": c.run_id}
    base = raw_dir if (raw_dir / c.run_id / "decisions.json").is_file() else ROOT / "runs"
    row["source"] = str((base / c.run_id).relative_to(ROOT))
    saved = paths.RUNS_DIR
    paths.RUNS_DIR = base
    try:
        b = breakdown.breakdown(c.run_id)
    except Exception as e:                             # noqa: BLE001 — 칸 하나가 전체를 죽이지 않게
        row["collect_error"] = f"{type(e).__name__}: {e}"
        return row
    finally:
        paths.RUNS_DIR = saved

    book = json.loads((base / c.run_id / "decisions.json").read_text(encoding="utf-8"))
    decs = [r for r in book["decisions"] if r.get("kind") == "decision"]
    escs = [r for r in book["decisions"] if r.get("kind") == "escalation"]
    s, sp = b["score"], b["sla_split"]
    row.update(
        arm_kind=(b.get("config") or {}).get("arm_kind"),
        steps=len(decs),
        interventions=len(escs),
        intervention_rate=round(len(escs) / len(decs), 4) if decs else None,
        sla_scored=sp["scored"], sla_violations=sp["violations"],
        sla_violation_rate=round(sp["violations"] / sp["scored"], 4) if sp["scored"] else None,
        sla_avoidable=sp["avoidable"], sla_structural=sp["structural"],
        procurements=sum(1 for r in decs if r.get("slice_id")),
        procurement_cost=round(sum(float(r.get("cost_total") or 0) for r in decs), 2),
        perception_accuracy=s["perception_accuracy"]["accuracy"],
        escalation_precision=s["escalation_precision"]["precision"],
        referee_error_steps=b["referee"]["excluded"],
    )
    return row


_SD_OF = {                                   # 평균 옆에 표본 표준편차를 붙일 지표 → 그 열 이름
    "sla_violation_rate": "sla_violation_sd",   # workplan C-9 판정 이름
    "intervention_rate": "intervention_rate_sd",
    "perception_accuracy": "perception_accuracy_sd",
}


def fold(rows: list[dict]) -> list[dict]:
    """반복 행을 칸당 한 행으로 접는다 (C-9).

    같은 (variant, scenario, seed) 의 행이 하나면 그대로(n_repeats 1). 둘 이상이면 숫자 지표는
    평균, _SD_OF 는 표본 표준편차(`_sd`)를 붙이고 run_id 는 접미 없는 칸 이름, 반복별 run_id 는
    `repeat_run_ids` 에. 수집 실패 행(collect_error)은 평균에서 빼고 `n_failed` 로 센다.
    """
    groups: dict[tuple, list[dict]] = {}
    for r in rows:
        groups.setdefault((r["variant"], r["scenario"], r["seed"]), []).append(r)

    out = []
    for key, rs in groups.items():
        ok = [r for r in rs if "collect_error" not in r]
        if len(rs) == 1:
            out.append({**rs[0], "n_repeats": 1})
            continue
        base = {"variant": key[0], "scenario": key[1], "seed": key[2],
                "run_id": re.sub(r"-r\d+$", "", rs[0]["run_id"]),
                "n_repeats": len(ok), "n_failed": len(rs) - len(ok),
                "repeat_run_ids": [r["run_id"] for r in rs]}
        if not ok:
            base["collect_error"] = "; ".join(r["collect_error"] for r in rs)
            out.append(base)
            continue
        base["arm_kind"] = ok[0].get("arm_kind")
        numeric = [k for k, v in ok[0].items()
                   if isinstance(v, (int, float)) and not isinstance(v, bool)
                   and k not in ("seed", "n_repeats")]
        for k in numeric:
            xs = [r[k] for r in ok if isinstance(r.get(k), (int, float))]
            if not xs:
                base[k] = None
                continue
            base[k] = round(st.mean(xs), 4)
            if k in _SD_OF:
                base[_SD_OF[k]] = round(st.stdev(xs), 4) if len(xs) > 1 else 0.0
        out.append(base)
    return out


# ── 진입점 ──────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description="본실험 배치 (기본: 계획만 출력)")
    ap.add_argument("--name", default=datetime.now().strftime("%Y%m%d"),
                    help="runs/_matrix/<name>/ 에 모인다")
    ap.add_argument("--variants", default=",".join(VARIANTS))
    ap.add_argument("--scenarios", default=",".join(SCENARIOS))
    ap.add_argument("--seeds", default="0,1,2")
    ap.add_argument("--repeats", type=int, default=1,
                    help="llm · orch 칸을 몇 번씩 돌리나 (run_id -rK). 규칙 칸은 결정적이라 1회")
    ap.add_argument("--repeat-rule", action="store_true",
                    help="규칙 칸도 --repeats 만큼 (배선 검증용 — 결과는 같아 sd 0)")
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
    if args.repeats < 1:
        print("[오류] --repeats 는 1 이상", file=sys.stderr)
        return 1
    plan = build_plan(variants, scenarios, seeds, args.repeats, args.repeat_rule)

    out = ROOT / "runs" / "_matrix" / args.name
    state_path = out / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else {}

    todo = [c for c in plan if not (args.resume and state.get(c.run_id, {}).get("exit") == 0)]
    tot_sec = sum(c.estimate(args.steps)[0] for c in todo)
    tot_usd = sum(c.estimate(args.steps)[1] for c in todo)
    by_mode: dict = {}
    for c in todo:
        by_mode[c.mode] = by_mode.get(c.mode, 0) + 1

    n_cells = len({c.key for c in plan})
    print(f"행렬 {args.name} · 칸 {n_cells} · 실행 {len(plan)} (이번에 돌 실행 {len(todo)})"
          + (f" · 반복 {args.repeats}회" if args.repeats > 1 else ""))
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
    raw_dir = out / "raw"
    raw_dir.mkdir(exist_ok=True)
    (out / "plan.json").write_text(
        json.dumps([{**asdict(c), "run_id": c.run_id} for c in plan], indent=2), encoding="utf-8")
    spent = sum(v.get("usd_equiv", 0) for v in state.values())

    for i, c in enumerate(todo, 1):
        if spent >= args.budget_usd:
            print(f"[상한] 누적 ${spent:.2f} ≥ ${args.budget_usd:.2f} — 남은 {len(todo) - i + 1}칸 보류. "
                  "--resume --budget-usd 로 이어간다")
            break
        print(f"[{i}/{len(todo)}] {c.run_id} ({c.mode}) …", flush=True)
        r = run_cell(c, args.steps, args.model, out / "logs")
        r["raw"] = archive_cell(c, raw_dir)            # 실패한 칸도 남긴다 — 원인이 원본에 있다
        spent += r["usd_equiv"]
        state[c.run_id] = {**r, "variant": c.variant, "scenario": c.scenario, "seed": c.seed,
                           "repeat": c.repeat,
                           "finished": datetime.now().isoformat(timespec="seconds")}
        state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
        mark = "완료" if r["exit"] == 0 else f"실패(종료 {r['exit']}) — {r['log']}"
        print(f"       {mark} · {r['elapsed_sec']}초 · ${r['usd_equiv']:.3f} · 누적 ${spent:.2f}")

    # 요약 — 성공한 실행 전부 (이번에 안 돈 칸도 state 에 있으면 포함). 반복은 칸당 한 행으로.
    raw_rows = [collect(c, raw_dir) for c in plan if state.get(c.run_id, {}).get("exit") == 0]
    rows = fold(raw_rows)
    if any(c.repeat is not None for c in plan):
        (out / "summary_repeats.json").write_text(
            json.dumps(raw_rows, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    if rows:
        keys = sorted({k for r in rows for k in r}, key=lambda k: (k not in rows[0], k))
        with open(out / "summary.csv", "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(rows)
    print(f"\n요약 {len(rows)}칸 (실행 {len(raw_rows)}) → {(out / 'summary.csv').relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
