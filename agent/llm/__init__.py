"""LLM 주입 지점.

`backends/` 가 전송(목 ↔ 실제 MCP)을 갈아끼우듯, 여기는 판단 모델을
갈아끼운다. `deciders/llm.py` 는 이 Protocol 만 알고 구현체는 모른다.

세 번째 주입 지점이다:
    Backend  — 도구를 어떻게 부르나
    Decider  — 누가 판단하나
    LLM      — 그 판단자가 무엇으로 생각하나
"""

import json
import re
from typing import Protocol

__all__ = ["LLM", "LLMError", "extract_json"]


class LLMError(RuntimeError):
    """LLM 호출이 실패했다. 조용히 넘기지 않는다 (CLAUDE.md 조용한 폴백 금지)."""


class LLM(Protocol):
    """한 번 묻고 한 번 받는다. 대화 상태를 갖지 않는다.

    스텝 간 문맥을 남기지 않는 것은 의도다 — 남기면 앞 스텝의 판단이
    뒤 스텝을 물들여 스텝별 독립 채점이 깨진다.
    """

    def ask(self, system: str, user: str) -> str: ...


_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def extract_json(text: str) -> dict:
    """모델 응답에서 JSON 객체 하나를 꺼낸다.

    코드펜스로 감싸거나 앞뒤에 말을 붙이는 경우를 흡수한다. 그 이상은
    흡수하지 않는다 — 형식을 못 지키는 것 자체가 측정 대상이다.
    """
    if not text or not text.strip():
        raise LLMError("빈 응답")

    m = _FENCE.search(text)
    blob = m.group(1) if m else text

    start, end = blob.find("{"), blob.rfind("}")
    if start < 0 or end <= start:
        raise LLMError(f"JSON 객체를 찾지 못했다: {text[:200]!r}")

    try:
        out = json.loads(blob[start : end + 1])
    except json.JSONDecodeError as e:
        raise LLMError(f"JSON 파싱 실패({e}): {blob[start:end + 1][:200]!r}") from e

    if not isinstance(out, dict):
        raise LLMError(f"객체가 아니다: {type(out).__name__}")
    return out
