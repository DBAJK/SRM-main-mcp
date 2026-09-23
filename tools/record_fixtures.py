"""B·C가 ① 없이 개발할 수 있게 해주는 관측 녹화본. (A 소유)

`fixtures/*.jsonl`을 생성한다 — ①을 실제로 띄우지 않고도 이 파일만 보고
②(propose_allocation 등)와 C(프롬프트)를 개발·테스트할 수 있게 하는 "계약의 실행 가능한
예시"다 (`claude/team/roles.md` §2.3, "병렬화의 열쇠").

    python tools/record_fixtures.py

시나리오별 30스텝 관측(`obs_{scenario}.jsonl`)과, ②의 lstm_forecast 테스트용 피처
시퀀스(`history_emergency.jsonl`)를 만든다. 시드 고정이라 재실행해도 같은 파일이 나온다
(재현성 — `build/order.md` 2단계 판정과 같은 원칙).
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from srm_mcp.common import paths  # noqa: E402
from srm_mcp.observe.env import SliceEnv  # noqa: E402

FIXTURES_DIR = ROOT / "fixtures"
SEED = 0
N_STEPS = 30
HISTORY_SCENARIO = "emergency"
HISTORY_N = 30  # get_history 로 뽑을 시퀀스 길이. 10 이상이면 lstm_forecast 가 가용해진다.


def _fresh_env(run_id: str, scenario: str) -> SliceEnv:
    shutil.rmtree(paths.run_dir(run_id), ignore_errors=True)
    env = SliceEnv(run_id)
    env.reset(run_id, scenario=scenario, seed=SEED)
    return env


def record_observations(scenario: str, n_steps: int) -> list[dict]:
    """`scenario`를 `n_steps`만큼 돌리며 매 스텝 전의 관측을 기록한다."""
    run_id = f"_fixture-{scenario}"
    env = _fresh_env(run_id, scenario)
    rows = []
    for _ in range(min(n_steps, env.total_steps)):
        rows.append(env.get_observation())
        env.step(1)
    shutil.rmtree(paths.run_dir(run_id), ignore_errors=True)
    return rows


def record_history(scenario: str, n: int) -> list[dict]:
    """`get_history(n)`가 반환하는 피처 행을 한 줄에 하나씩. ②의 lstm_forecast 테스트용."""
    run_id = f"_fixture-history-{scenario}"
    env = _fresh_env(run_id, scenario)
    for _ in range(min(n, env.total_steps)):
        env.step(1)
    block = env.get_history(n)
    shutil.rmtree(paths.run_dir(run_id), ignore_errors=True)
    columns = block["columns"]
    return [{"columns": columns, "values": row} for row in block["features"]]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    for scenario in ("normal", "emergency", "mixed"):
        rows = record_observations(scenario, N_STEPS)
        out = FIXTURES_DIR / f"obs_{scenario}.jsonl"
        write_jsonl(out, rows)
        print(f"{out.relative_to(ROOT)}: {len(rows)}줄")

    history_rows = record_history(HISTORY_SCENARIO, HISTORY_N)
    out = FIXTURES_DIR / f"history_{HISTORY_SCENARIO}.jsonl"
    write_jsonl(out, history_rows)
    print(f"{out.relative_to(ROOT)}: {len(history_rows)}줄")


if __name__ == "__main__":
    main()