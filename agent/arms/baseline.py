"""baseline — 기존 시스템의 재현. 사람이 CLI 로 상황을 알려준다.

원본은 `--emergency` 같은 CLI 플래그로 사람이 상황을 지정했다(ml_orchestrator_demo.py:429
`self.is_emergency`). 그걸 재현하려면 정답을 알아야 하므로 **이 비교군만 truth.jsonl 을
읽는다** (flow/forbidden.md:15~17).

⚠ 물리 분리. `agent/` 안에서 truth.jsonl 을 여는 코드는 **이 파일 하나뿐**이어야 한다.
   같은 함수에 `if arm == "baseline"` 으로 두면 실수로 다른 비교군에 정답이 샌다
   (forbidden.md:17). 다른 비교군은 이 모듈을 거치지 않는다.

정답은 파일에서 읽을 뿐 에이전트 컨텍스트(LLM 프롬프트 · 도구 반환값)로 들어가지 않는다.
이 판단자는 LLM 을 쓰지 않는다 — 사람이 이미 답을 줬으니 판단할 게 없다. Guard 는 켜둔다.
도구 반환값은 여전히 검사 대상이고, 정답은 그 경로로 오지 않는다.

정책은 rule_based 고정, 조달은 규칙(루프가 압력 ≥ 1.0 으로 거름), 개입 없음 — arm1 과
**상황 출처 하나만** 다르다 (rationale/corrections.md:82).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..schema import Decision, StepContext

# ① 이 _roll() 에서 관측과 같은 시점에 한 줄씩 쓴다 (srm_mcp/observe/env.py _truth_append).
# 스텝 t 의 관측을 받았을 때 정답 t 는 이미 파일에 있다.
TRUTH_FILE = "truth.jsonl"

# eval/score.py 의 매핑과 같다. 겹치면 안 되므로 둘 이상이면 죽는다.
_FLAG_TO_SITUATION = {
    "is_emergency": "emergency",
    "is_special_event": "special_event",
    "is_iot_surge": "iot_surge",
}


class TruthUnavailable(RuntimeError):
    """정답 줄이 없다. mock 백엔드이거나 ①이 아직 그 스텝을 쓰지 않았다."""


class BaselineDecider:
    arm = "baseline"

    def __init__(self, root: Path):
        self._runs = Path(root) / "runs"

    def __call__(self, ctx: StepContext, proposer: Any) -> Decision:
        situation = self._truth_situation(ctx.run_id, ctx.step)
        prop = proposer.propose("rule_based", situation)
        return Decision(
            situation=situation,
            policy=prop["policy"],
            allocation=prop.get("allocation"),
            conf_intrinsic=float(prop.get("confidence", 0.0)),
            conf_empirical=ctx.effective(prop["policy"]),
            conf_situation=1.0,          # 사람이 지정했다. 추론이 아니다
            rationale=f"baseline: 사람이 상황을 지정 ({situation}) | ②: {prop.get('rationale', '')}",
            procure=True,                # 규칙대로 — 루프가 압력 ≥ 1.0 일 때만 산다
            in_distribution=bool(prop.get("in_distribution", True)),
            considered=[],
            demand_class=ctx.demand_class,
            escalation=False,
        )

    def _truth_situation(self, run_id: str, step: int) -> str:
        path = self._runs / run_id / TRUTH_FILE
        if not path.is_file():
            raise TruthUnavailable(
                f"{path} 가 없다. baseline 은 실서버(--backend mcp)에서만 돈다 — "
                "정답 파일은 ① observe 서버가 쓴다.")
        with open(path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                row = json.loads(line)
                if int(row.get("step", -1)) != step:
                    continue
                active = [name for flag, name in _FLAG_TO_SITUATION.items() if row.get(flag)]
                if len(active) > 1:
                    raise TruthUnavailable(f"step {step} 정답 라벨이 겹쳤다: {row}")
                return active[0] if active else "normal"
        raise TruthUnavailable(f"step {step} 의 정답 줄이 {path} 에 없다")
