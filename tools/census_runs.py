"""끝난 실행 여러 개를 render_run 과 같은 기준으로 묶어 센다 — 기록만 읽으므로 무료.

    py -3.10 tools/census_runs.py runs/_matrix/after-D runs/_matrix/after-D-theta
    py -3.10 tools/census_runs.py --orch runs        # orchestrator/calls.jsonl 이 있는 실행만

인자는 매트릭스 폴더(raw/ 아래 칸들) 또는 실행 폴더. 같은 (변형, arm) 끼리 시드 · 시나리오를 합친다.

  (a) a* 근사 — 적용 배분과 a* 의 거리, SLA 충족 / 위반 스텝 각각
      위반 원인 — 불가능(다음 수요 압력 > 1) · 평활 지연(곧바로 갔으면 충족) · 목표 부족(나머지)
      평활 덕에 충족 — 요청대로 곧바로 갔으면 위반이었을 스텝
  (b) 슬라이스별 위반률 — 동일 가중 SLA 와 별개로 URLLC 만 따로 본다
  (c) emergency 정답 스텝의 URLLC — 요청 · 적용 · a* 평균, URLLC 위반
  (d) 오류 · 종료 — 오케스트레이터 실행만 (도구 거부 메시지별 횟수 · 심판 코드 · 기록 스텝/정답 스텝)
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from collections import Counter, defaultdict
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_run import _f, _jsonl, _mean, _norm, load_run  # noqa: E402

SLICES = ("embb", "urllc", "mmtc")


def run_folders(target: Path) -> list[Path]:
    if (target / "decisions.json").is_file():
        return [target]
    base = target / "raw" if (target / "raw").is_dir() else target
    return sorted(p for p in base.iterdir() if (p / "decisions.json").is_file())


def arm_of(folder: Path) -> str:
    return folder.name.split("-")[0]


def summarize(runs: list[dict]) -> dict:
    rows = [r for run in runs for r in run["rows"]]
    judged = [r for r in rows if r["sla_met"] is not None and r.get("ideal")]
    met = [r for r in judged if r["sla_met"]]
    viol = [r for r in judged if r["sla_met"] is False]
    lag = [r for r in viol if r.get("instant_violations") is not None and not any(r["instant_violations"].values())]
    impossible = [r for r in viol if r.get("pressure_next", 0) > 1.0]
    target = [r for r in viol if r not in lag and r not in impossible]
    saved = [r for r in met if r.get("instant_violations") is not None and any(r["instant_violations"].values())]
    em = [r for r in judged if r["truth"] == "emergency"]
    return {
        "cells": len(runs), "steps": len(judged),
        "sla": len(met) / len(judged) if judged else None,
        "esc": sum(r["escalated"] for r in rows) / len(rows) if rows else None,
        "d_met": _mean([r["d_applied"] for r in met]), "d_viol": _mean([r["d_applied"] for r in viol]),
        "viol": len(viol), "impossible": len(impossible), "lag": len(lag), "target": len(target), "saved": len(saved),
        "slice_viol": {k: sum(bool(r["violations"].get(k)) for r in judged) / len(judged) if judged else None
                       for k in SLICES},
        "em": len(em),
        "em_req": _mean([_norm(r["requested"])["urllc"] for r in em if r["requested"]]),
        "em_app": _mean([r["applied"]["urllc"] for r in em]),
        "em_ideal": _mean([r["ideal"]["urllc"] for r in em]),
        "em_urllc_viol": sum(bool(r["violations"].get("urllc")) for r in em),
        "em_sla": sum(1 for r in em if r["sla_met"]) / len(em) if em else None,
    }


def pct(x) -> str:
    return "—" if x is None else f"{100 * x:.1f}%"


def tables(groups: dict[tuple, list[dict]]) -> str:
    L = ["### (a) a* 근사 · 위반 원인", "",
         "| 변형 | arm | 칸 | 스텝 | SLA | 개입 | 충족 d(a*) | 위반 d(a*) | 위반 | 불가능 | 평활 지연 | 목표 부족 | 평활 덕 충족 |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    S = {key: summarize(runs) for key, runs in groups.items()}
    for (var, arm), s in S.items():
        L.append(f"| {var} | {arm} | {s['cells']} | {s['steps']} | {pct(s['sla'])} | {pct(s['esc'])} | "
                 f"{_f(s['d_met'])} | {_f(s['d_viol'])} | {s['viol']} | {s['impossible']} | {s['lag']} | "
                 f"{s['target']} | {s['saved']} |")
    L += ["", "### (b) 슬라이스별 위반률 (전 스텝)", "",
          "| 변형 | arm | eMBB | URLLC | mMTC |", "|---|---|---|---|---|"]
    for (var, arm), s in S.items():
        v = s["slice_viol"]
        L.append(f"| {var} | {arm} | {pct(v['embb'])} | {pct(v['urllc'])} | {pct(v['mmtc'])} |")
    L += ["", "### (c) emergency 정답 스텝 — URLLC", "",
          "| 변형 | arm | 스텝 | SLA | URLLC 위반 | 요청 URLLC | 적용 URLLC | a* URLLC |", "|---|---|---|---|---|---|---|---|"]
    for (var, arm), s in S.items():
        if s["em"]:
            L.append(f"| {var} | {arm} | {s['em']} | {pct(s['em_sla'])} | {s['em_urllc_viol']}/{s['em']} "
                     f"({pct(s['em_urllc_viol'] / s['em'])}) | {_f(s['em_req'])} | {_f(s['em_app'])} | {_f(s['em_ideal'])} |")
    return "\n".join(L)


def errors(runs: list[dict]) -> str:
    L = ["### (d) 오케스트레이터 오류 · 종료", "",
         "| 실행 | 호출 | 실패·거부 | 심판 | D6 전환 | LLM 실패 | 기록/정답 스텝 |", "|---|---|---|---|---|---|---|"]
    why: Counter = Counter()
    codes: Counter = Counter()
    for run in runs:
        bad = [c for c in run["calls"] if c.get("refused") or c.get("value_error") or not c.get("ok")]
        for c in bad:
            msg = c.get("value_error") or c.get("error") or ("refused: " + str((c.get("result") or {}).get("error")))
            why[(c.get("tool"), str(msg)[:110])] += 1
        vc = Counter(v["code"] for r in run["refs"] for v in r["violations"])
        codes.update(vc)
        expected = len(_jsonl(run["folder"] / "truth.jsonl"))
        L.append(f"| {run['folder'].name} | {len(run['calls'])} | {len(bad)} | {dict(vc) or '—'} | "
                 f"{sum(1 for r in run['refs'] if r.get('switched_under_threshold'))} | "
                 f"{sum(1 for s in run['osteps'] if s.get('llm_error'))} | {len(run['rows'])}/{expected} |")
    L += ["", f"합계 — 호출 {sum(len(r['calls']) for r in runs)} · 실패·거부 {sum(why.values())} · 심판 {dict(codes)}", "",
          "| 횟수 | 도구 | 메시지 |", "|---|---|---|"]
    L += [f"| {n} | {tool} | `{msg}` |" for (tool, msg), n in why.most_common()]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("targets", nargs="+", type=Path)
    ap.add_argument("--orch", action="store_true", help="orchestrator/calls.jsonl 이 있는 실행만 찾아 (d) 까지")
    args = ap.parse_args()

    groups: dict[tuple, list[dict]] = defaultdict(list)
    orch_runs: list[dict] = []
    seen: set[str] = set()
    for target in args.targets:
        folders = (sorted(p.parent.parent for p in target.rglob("orchestrator/calls.jsonl"))
                   if args.orch else run_folders(target))
        for folder in folders:
            # run_matrix 가 raw/ 로 복사한 칸은 같은 실행이다 — 두 번 세지 않는다
            calls = folder / "orchestrator" / "calls.jsonl"
            if calls.is_file():
                digest = hashlib.sha1(calls.read_bytes()).hexdigest()
                if digest in seen:
                    continue
                seen.add(digest)
            run = load_run(folder)
            groups[("orch" if args.orch else target.name, arm_of(folder))].append(run)
            if run["calls"]:
                orch_runs.append(run)
    print(tables(groups))
    if orch_runs:
        print()
        print(errors(orch_runs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
