"""정답 누출 검사.

claude/flow/forbidden.md:3
  "baseline arm 을 제외한 모든 실행에서 아래 문자열이 에이전트 컨텍스트에
   0건이어야 한다. 도구 설명·반환값·오류 메시지 전부가 검사 대상이다.
   1건이라도 나오면 그 실행은 폐기한다."

사람 눈으로는 확인할 수 없으므로 코드로 강제한다. 5시간 돌린 뒤
폐기 판정을 받는 것보다 첫 스텝에서 죽는 게 낫다.
"""

import json
from typing import Any

FORBIDDEN = [
    "is_emergency",
    "is_special_event",
    "is_iot_surge",
    "ground_truth",
    "perception_accuracy",
    "escalation_precision",
]


class ForbiddenLeak(RuntimeError):
    """금지 문자열이 에이전트 컨텍스트에 들어왔다. 이 실행은 폐기 대상이다."""


class Guard:
    """에이전트 컨텍스트로 들어가는 모든 값을 통과시킨다.

    baseline arm 만 enabled=False 로 만든다. 단, 그 분기는 이 클래스 밖
    (arms/baseline.py) 에 두어 물리적으로 분리한다 — forbidden.md:17
    """

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.checked = 0

    def check(self, payload: Any, where: str) -> Any:
        """payload 를 그대로 돌려준다. 누출이 있으면 예외.

        where 는 어느 도구/단계에서 새어나왔는지 알려주는 라벨.
        """
        if not self.enabled:
            return payload

        self.checked += 1
        blob = _stringify(payload)
        hits = [t for t in FORBIDDEN if t in blob]
        if hits:
            raise ForbiddenLeak(
                f"{where}: 금지 문자열 {hits} 가 에이전트 컨텍스트에 노출됨. "
                f"이 실행은 폐기 대상이다 (flow/forbidden.md)."
            )
        return payload

    def check_text(self, text: str, where: str) -> str:
        """프롬프트에 직접 넣는 문자열용. 도구 설명·오류 메시지도 검사 대상이다."""
        return self.check(text, where)


def _stringify(payload: Any) -> str:
    """dict/list/스칼라를 전부 문자열로 눌러 키 이름까지 검사한다."""
    if isinstance(payload, str):
        return payload
    try:
        return json.dumps(payload, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(payload)
