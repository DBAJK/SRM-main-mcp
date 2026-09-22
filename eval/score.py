"""오프라인 채점 — `truth.jsonl` × `decisions.json` 조인. (A 소유)

`perception_accuracy`·`escalation_precision`은 정답(`is_emergency` 등)이 있어야 계산되는
지표라 ④ `get_metrics()`는 반환하지 않는다 (`claude/flow/forbidden.md`). 여기서만,
에이전트 컨텍스트 밖에서 오프라인으로 계산한다.

    python -m eval.score {run_id}

매핑 규칙과 전환 경계 제외는 `claude/flow/forbidden.md`에서 채점 전에 못 박은 것을
그대로 따른다 — 채점 후에 정하면 유리한 쪽으로 해석할 수 있기 때문이다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from srm_mcp.common import paths  # noqa: E402

TRUTH_FLAG_TO_SITUATION = {
    "is_emergency": "emergency",
    "is_special_event": "special_event",
    "is_iot_surge": "iot_surge",
}


# ── 로드 ───────────────────────────────────────────────────────
def load_truth(run_id: str) -> list[dict]:
    path = paths.run_dir(run_id) / "truth.jsonl"
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    rows.sort(key=lambda r: r["step"])
    return rows


def load_decisions(run_id: str) -> dict:
    with open(paths.decisions_json(run_id), encoding="utf-8") as f:
        return json.load(f)


# ── 매핑 (flow/forbidden.md) ──────────────────────────────────
def truth_situation(row: dict) -> str:
    """전부 false → normal, is_X만 true → X, 둘 이상 → assert (겹치면 안 된다)."""
    active = [name for flag, name in TRUTH_FLAG_TO_SITUATION.items() if row.get(flag)]
    assert len(active) <= 1, f"라벨이 겹쳤다: step {row.get('step')} {row}"
    return active[0] if active else "normal"


def transition_steps(truth_rows: list[dict]) -> set[int]:
    """정답이 직전 스텝과 달라진 스텝. perception_accuracy 판정에서 제외한다.

    obs_t는 전환 직전의 트래픽을 반영하므로, 전환 스텝을 미탐으로 세면 원리적으로
    맞힐 수 없는 것을 틀렸다고 세는 셈이다 (`flow/forbidden.md`).
    """
    steps: set[int] = set()
    prev: Optional[str] = None
    for row in truth_rows:
        cur = truth_situation(row)
        if prev is not None and cur != prev:
            steps.add(int(row["step"]))
        prev = cur
    return steps


# ── 지표 ───────────────────────────────────────────────────────
def perception_accuracy(decisions: list[dict], truth_by_step: dict[int, str],
                        excluded_steps: set[int]) -> dict:
    """`kind: "decision"` 레코드의 `situation` vs 정답.

    에스컬레이션한 스텝의 폴백 결정 레코드도 포함한다 — `book.record_escalation`이
    `situation`에 에이전트의 원래 판단을 그대로 남기기 때문이다 (`fallback_situation`과
    다른 필드). 여기서 빼면 가장 어려운 스텝들이 인지 정확도 표본에서 빠진다.
    """
    total = 0
    correct = 0
    confusion: dict[str, dict[str, int]] = {}
    for record in decisions:
        if record.get("kind") != "decision":
            continue
        step = int(record["step"])
        if step in excluded_steps:
            continue
        truth_label = truth_by_step.get(step)
        if truth_label is None:
            continue
        predicted = record.get("situation")
        total += 1
        correct += int(predicted == truth_label)
        confusion.setdefault(truth_label, {})
        confusion[truth_label][predicted] = confusion[truth_label].get(predicted, 0) + 1

    return {
        "n": total,
        "correct": correct,
        "accuracy": round(correct / total, 6) if total else None,
        "confusion": confusion,  # {정답: {예측: 건수}}
    }


def escalation_precision(decisions: list[dict], truth_by_step: dict[int, str]) -> dict:
    """에스컬레이션이 옳았는가 = 그 스텝의 정답이 실제로 `normal`이 아니었는가.

    (조작적 정의 — `MCP-decomposition.md` §6의 "정답 상황에서 사람의 판단이 실제로
    필요했는지"를 가장 단순하게 기계화한 것. 팀 합의로 더 정교하게 바꿀 수 있다.)

    전환 경계는 제외하지 않는다 — perception_accuracy와 달리, 에스컬레이션은 "상황을
    못 읽어서 사람을 부른 것"의 타당성을 보는 것이라 전환 스텝이라도 실제로 이상
    상황이면 옳은 호출이다.
    """
    escalations = [r for r in decisions if r.get("kind") == "escalation"]
    total = len(escalations)
    correct = 0
    for record in escalations:
        truth_label = truth_by_step.get(int(record["step"]))
        if truth_label is not None and truth_label != "normal":
            correct += 1

    return {
        "n": total,
        "correct": correct,
        "precision": round(correct / total, 6) if total else None,
    }


# ── 실행 ───────────────────────────────────────────────────────
def score_run(run_id: str) -> dict:
    truth_rows = load_truth(run_id)
    truth_by_step = {int(row["step"]): truth_situation(row) for row in truth_rows}
    excluded = transition_steps(truth_rows)

    decisions = load_decisions(run_id)["decisions"]

    return {
        "run_id": run_id,
        "perception_accuracy": perception_accuracy(decisions, truth_by_step, excluded),
        "escalation_precision": escalation_precision(decisions, truth_by_step),
        "excluded_transition_steps": sorted(excluded),
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python -m eval.score {run_id}", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(score_run(sys.argv[1]), indent=2, ensure_ascii=False))
