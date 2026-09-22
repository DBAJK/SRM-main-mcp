"""실제 MCP 서버 백엔드.

서버 5개를 **별도 프로세스로 stdio 기동**하고 도구 호출을 중계한다.
`MockBackend` 와 같은 `call(server, tool, args)` 인터페이스라
`loop.py` · `tools.py` · `deciders/` 는 한 줄도 바뀌지 않는다.

FastMCP 클라이언트가 async 인데 루프는 sync 다. 전용 스레드에서 이벤트 루프를
돌리고 호출마다 블로킹해 다리를 놓는다 — 세션이 프로세스 수명 내내 살아 있어야
하므로 호출마다 `asyncio.run()` 하는 방식은 쓸 수 없다.

전송 설정은 `tools/smoke_servers.py`(B 작성)를 따랐다.
"""

import asyncio
import os
import sys
import threading
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, Iterable, Optional

ROOT = Path(__file__).resolve().parents[2]

# 서버 이름 → 기동할 모듈. tools.py 가 쓰는 이름과 맞춘다.
MODULES = {
    "observe": "srm_mcp.observe.server",
    "policy": "srm_mcp.policy.server",
    "market": "srm_mcp.market.server",
    "audit": "srm_mcp.audit.server",
    "feedback": "srm_mcp.feedback.server",
}


class McpBackend:
    """5개 서버를 stdio 로 띄우고 도구 호출을 라우팅한다.

    Args:
        servers: 실제로 띄울 서버. None 이면 5개 전부.
        mock_for: 여기 있는 서버는 목으로 대신한다 (하이브리드 검증용).
        desc_mode: ②의 도구 설명 수위. `minimal`(주 실험) / `advisory`
        memory_mode: ③⑤의 상태 유지. `warm`(주 결과) / `cold`
    """

    def __init__(
        self,
        servers: Optional[Iterable[str]] = None,
        mock_for: Iterable[str] = (),
        desc_mode: str = "minimal",
        memory_mode: str = "warm",
        run_id: str = "agent",
        log_dir: Optional[Path] = None,
    ):
        self._mock_for = set(mock_for)
        self._names = [
            s for s in (servers or MODULES) if s not in self._mock_for
        ]
        unknown = set(self._names) - set(MODULES)
        if unknown:
            raise ValueError(f"모르는 서버: {sorted(unknown)}")

        self._env = {
            **os.environ,
            "PYTHONPATH": str(ROOT),
            "PYTHONIOENCODING": "utf-8",
            "SLICE_DESC_MODE": desc_mode,
            "SLICE_MEMORY_MODE": memory_mode,
            "SLICE_RUN_ID": run_id,
        }

        self._mock = None
        if self._mock_for:
            from .mock import MockBackend

            self._mock = MockBackend()

        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._loop.run_forever, name="mcp-backend", daemon=True
        )
        self._thread.start()

        # 서버마다 별도 프로세스라 stderr 가 이쪽 로거를 안 거친다. 파일로 받는다.
        self._log_dir = Path(log_dir) if log_dir else None
        if self._log_dir:
            self._log_dir.mkdir(parents=True, exist_ok=True)
        self._logs: list = []

        self._stack: Optional[AsyncExitStack] = None
        self._clients: dict[str, Any] = {}
        self._run(self._connect())

    # ── 공개 ──────────────────────────────────────────────────────────
    def call(self, server: str, tool: str, args: dict) -> Any:
        if server in self._mock_for:
            return self._mock.call(server, tool, args)
        return self._run(self._call(server, tool, args))

    @property
    def log_dir(self) -> Optional[Path]:
        return self._log_dir

    def close(self) -> None:
        """서버 프로세스를 정리한다. 안 부르면 데몬 스레드째 남는다."""
        if self._stack is not None:
            self._run(self._stack.aclose())
            self._stack = None
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)

        for fh in self._logs:
            try:
                fh.close()
            except OSError:
                pass
        self._logs.clear()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    @property
    def live(self) -> list[str]:
        """실제 프로세스로 뜬 서버."""
        return sorted(self._clients)

    # ── 내부 ──────────────────────────────────────────────────────────
    def _run(self, coro):
        """전용 루프에 코루틴을 던지고 결과를 기다린다."""
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result()

    async def _connect(self) -> None:
        from fastmcp import Client
        from fastmcp.client.transports import StdioTransport

        self._stack = AsyncExitStack()
        for name in self._names:
            kw = {}
            if self._log_dir:
                # StdioTransport(log_file=...) 가 그 서버의 stderr 를 여기로 돌린다.
                fh = open(self._log_dir / f"{name}.log", "w", encoding="utf-8",
                          errors="replace", buffering=1)
                self._logs.append(fh)
                kw["log_file"] = fh

            transport = StdioTransport(
                command=sys.executable,
                args=["-m", MODULES[name]],
                cwd=str(ROOT),
                env=self._env,
                **kw,
            )
            self._clients[name] = await self._stack.enter_async_context(
                Client(transport)
            )

    async def _call(self, server: str, tool: str, args: dict) -> Any:
        client = self._clients.get(server)
        if client is None:
            raise RuntimeError(
                f"서버 '{server}' 가 기동되지 않았다. live={self.live}"
            )
        result = await client.call_tool(tool, args)
        # FastMCP 는 CallToolResult 를 준다. .data 가 구조화된 반환값이다.
        return getattr(result, "data", result)
