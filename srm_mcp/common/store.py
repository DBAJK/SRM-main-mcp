"""원자적 JSON 읽기/쓰기. (A 소유 · 임시 스텁)

설계서 §2 — 락은 두지 않는다 (에이전트가 순차 호출). 다만 쓰기는 원자적으로 한다:
tmp 에 쓴 뒤 os.replace(). 중단 시 파일이 깨지는 것만 막으면 충분하다.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def read_json(path: Path, default: Any = None) -> Any:
    if not Path(path).exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def to_builtin(obj: Any) -> Any:
    """numpy → 파이썬 기본형. **모든 반환 경계에서 통과시킨다** (spec/common.md).

    violations 가 정확히 np.bool_ 라 그대로 반환하면 json.dumps 가 죽는다.
    np.float64 는 우연히 통과하므로 한참 잘 돌다가 violations 에서만 터진다.
    """
    if isinstance(obj, dict):
        return {k: to_builtin(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_builtin(v) for v in obj]
    if hasattr(obj, "tolist"):          # np.ndarray, np.generic
        return obj.tolist()
    if hasattr(obj, "item"):            # np.bool_, np.float64
        return obj.item()
    return obj
