"""실행 추적.

무엇이 언제 불렸는지 눈으로 따라갈 수 있게 한다. 기본은 꺼져 있고
`--trace` 로 켠다 — 로그가 판단에 영향을 주지 않도록 순수 관찰만 한다.

콘솔에는 한 줄 요약, 파일에는 전문을 남긴다. 프롬프트 전문이 콘솔을 덮으면
정작 봐야 할 호출 순서가 안 보이고, 그렇다고 버리면 "왜 그렇게 판단했나"를
나중에 확인할 수 없다.
"""

import json
import logging
from pathlib import Path
from typing import Any, Optional

# 서버 번호. 명세가 ①~⑤ 로 부르므로 로그도 같은 기호를 쓴다.
MARK = {
    "observe": "①",
    "policy": "②",
    "market": "③",
    "audit": "④",
    "feedback": "⑤",
}

CONSOLE_WIDTH = 96   # 콘솔 한 줄에 실을 반환값 길이
NOISY = ("fastmcp", "mcp", "httpx", "httpcore", "asyncio", "tensorflow")


def brief(v: Any, limit: int = CONSOLE_WIDTH) -> str:
    """dict/list 를 한 줄로 눌러 담는다. 길면 자른다."""
    if v is None:
        return "-"
    if isinstance(v, str):
        s = v
    else:
        try:
            s = json.dumps(v, ensure_ascii=False, separators=(",", ":"), default=str)
        except (TypeError, ValueError):
            s = str(v)
    s = " ".join(s.split())
    return s if len(s) <= limit else s[: limit - 1] + "…"


def setup(run_id: str, console: bool, root: Optional[Path] = None) -> Path:
    """추적 파일을 연다. **항상** 남긴다 — `console` 은 콘솔에도 쏟을지만 정한다.

    실행이 끝난 뒤 "그때 뭐가 오갔지"를 확인할 방법이 파일밖에 없고, 그 파일은
    실행 전에 플래그를 안 줬다고 사라지면 안 된다. 콘솔은 길어서 기본으로 끈다.
    """
    root = root or Path(__file__).resolve().parents[1]
    out = run_dir(run_id, root)
    path = out / "trace.log"

    fh = logging.FileHandler(path, mode="w", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(_FullFormatter("%(asctime)s %(message)s", "%H:%M:%S"))

    agent = logging.getLogger("agent")
    agent.setLevel(logging.DEBUG)
    agent.addHandler(fh)

    # 루트 핸들러(콘솔)는 기본이 NOTSET 이라 DEBUG 까지 다 찍는다. 명시로 막는다.
    for h in logging.getLogger().handlers:
        h.setLevel(logging.DEBUG if console else logging.INFO)

    # 서버·전송 계층 잡음은 덮는다. 보려는 건 에이전트의 판단 흐름이다.
    for name in NOISY:
        logging.getLogger(name).setLevel(logging.WARNING)

    return path


def run_dir(run_id: str, root: Optional[Path] = None) -> Path:
    root = root or Path(__file__).resolve().parents[1]
    out = root / "runs" / run_id
    out.mkdir(parents=True, exist_ok=True)
    return out


def server_log_dir(run_id: str, root: Optional[Path] = None) -> Path:
    """MCP 서버 프로세스별 stderr 를 받을 자리.

    서버는 각자 별도 프로세스라 예외·경고가 이쪽 로거를 거치지 않는다. 안 받아
    두면 서버가 왜 이상하게 답했는지 확인할 방법이 콘솔 스크롤백뿐이다.
    """
    out = run_dir(run_id, root) / "servers"
    out.mkdir(parents=True, exist_ok=True)
    return out


class _FullFormatter(logging.Formatter):
    """파일에는 자르지 않은 원문을 남긴다.

    호출부가 `extra={"full": ...}` 를 실어 보내면 콘솔용 짧은 메시지 대신 그걸
    쓴다. **레코드를 고치지 않는다** — 같은 레코드가 콘솔 핸들러로도 가므로,
    여기서 msg 를 갈아치우면 콘솔에도 전문이 쏟아진다.
    """

    def format(self, record: logging.LogRecord) -> str:
        full = getattr(record, "full", None)
        if full is None:
            return super().format(record)

        clone = logging.makeLogRecord(record.__dict__)
        clone.msg, clone.args = full, ()
        return super().format(clone)
