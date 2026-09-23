"""Claude CLI 를 LLM 으로 쓴다.

`claude -p` 를 자식 프로세스로 띄우고 한 번 묻는다. 별도 SDK·API 키 배선이
필요 없고, 데스크톱 앱이 이미 깔아둔 실행 파일을 그대로 쓴다.

**중립 작업 디렉터리에서 실행한다.** 프로젝트 폴더에서 띄우면 CLI 가
`CLAUDE.md` 와 `claude/` 명세를 자동으로 읽어 들이는데, 거기에는 금지
문자열(`is_emergency` …)과 상황 판정 기준이 그대로 적혀 있다. 판단자가
그걸 보면 그 실행은 폐기 대상이다 (claude/flow/forbidden.md).
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

from . import LLMError, extract_json

# 데스크톱 앱이 번들하는 위치. 버전 폴더가 여러 개면 가장 높은 것을 쓴다.
_BUNDLE = Path(os.environ.get("APPDATA", "")) / "Claude" / "claude-code"

# 프로젝트 파일이 하나도 없는 디렉터리. CLAUDE.md 자동 탐색을 굶긴다.
_NEUTRAL_CWD = Path(tempfile.gettempdir()) / "srm-agent-llm-cwd"

# 경로를 직접 지정하고 싶을 때. --llm-exe 와 같은 일을 한다.
EXE_ENV = "SLICE_CLAUDE_EXE"

# 번들 경로가 안 열리는 셸을 위한 사본 위치. 저장소 옆에 둔다.
_ROOT = Path(__file__).resolve().parents[2]
_SIBLINGS = (
    _ROOT / "claude-cli" / "claude.exe",
    _ROOT.parent / "claude-cli" / "claude.exe",
)

LOGIN_HINT = (
    "Claude CLI 에 로그인돼 있지 않다. 자격증명 입력은 사람이 해야 한다.\n"
    "  구독 계정   <claude.exe> auth login\n"
    "  API 과금    <claude.exe> auth login --console\n"
    "  SSO         <claude.exe> auth login --sso\n"
    "  또는 환경변수 ANTHROPIC_API_KEY 설정\n"
    "확인          <claude.exe> auth status   → loggedIn: true\n"
    "맨몸 `claude` 는 대화형 TUI 라 터미널 환경을 탄다. auth login 을 쓴다."
)


def find_exe() -> str:
    """환경변수 → PATH → 앱 번들 → 저장소 옆 사본 순으로 찾는다.

    번들 경로(`%APPDATA%\\Claude`)를 셸에 따라 열지 못하는 경우가 있어
    (앱 내장 터미널에서 CommandNotFound), 마지막에 저장소 옆 사본을 본다.
    """
    from shutil import which

    tried = []

    env = os.environ.get(EXE_ENV)
    if env:
        if Path(env).is_file():
            return env
        tried.append(f"{EXE_ENV}={env} (없음)")

    for name in ("claude", "claude.exe"):
        found = which(name)
        if found:
            return found
    tried.append("PATH")

    if _BUNDLE.is_dir():
        cands = [p for p in _BUNDLE.glob("*/claude.exe") if p.is_file()]
        if cands:
            def ver(p: Path):
                try:
                    return tuple(int(x) for x in p.parent.name.split("."))
                except ValueError:
                    return (0,)
            return str(max(cands, key=ver))
    tried.append(str(_BUNDLE / "*" / "claude.exe"))

    for sib in _SIBLINGS:
        if sib.is_file():
            return str(sib)
        tried.append(str(sib))

    raise LLMError(
        "claude 실행 파일을 찾지 못했다. 찾아본 곳:\n  "
        + "\n  ".join(tried)
        + f"\n해결: --llm-exe <경로>  또는  환경변수 {EXE_ENV} 설정"
    )


class ClaudeCLI:
    """`claude -p` 한 번 호출 = 판단 한 번.

    Args:
        exe: 실행 파일 경로. None 이면 자동 탐색.
        model: `sonnet` / `opus` / `haiku` 또는 전체 모델 ID.
        timeout: 한 호출의 제한 시간(초).
    """

    def __init__(
        self,
        exe: Optional[str] = None,
        model: str = "sonnet",
        timeout: float = 120.0,
    ):
        self.exe = exe or find_exe()
        self.model = model
        self.timeout = timeout

        # 실험 보고용. 스텝당 1~2회 호출이 쌓인다.
        self.calls = 0
        self.elapsed = 0.0
        # 논문에 비용을 적으려면 추정이 아니라 실측이 필요하다. CLI 봉투가 준다.
        self.tokens_in = 0
        self.tokens_out = 0
        self.cost_usd = 0.0

        _NEUTRAL_CWD.mkdir(parents=True, exist_ok=True)

    def ask(self, system: str, user: str) -> str:
        """판단자용 — 도구 없이 한 번 묻는다. 결과 본문만 돌려준다."""
        env = self.invoke(
            user,
            ["--system-prompt", system,   # 기본 시스템 프롬프트를 통째로 대체한다
             "--strict-mcp-config"],      # MCP 서버를 붙이지 않는다
        )
        return self._text_of(env)

    def invoke(self, user: str, extra: list[str], timeout: Optional[float] = None) -> dict:
        """`claude -p` 를 한 번 띄우고 **봉투 전체**를 돌려준다.

        오케스트레이터가 쓴다 — MCP 설정 · 도구 허용 · 구조화 출력 스키마 같은
        추가 플래그를 `extra` 로 넘기고, `structured_output` · `num_turns` 를 봉투에서
        직접 읽는다. 사용량·비용 집계는 여기서 한다.
        """
        cmd = [
            self.exe,
            "-p",
            "--output-format", "json",
            "--model", self.model,
            "--no-session-persistence",  # 스텝 간 문맥을 남기지 않는다
            *extra,
        ]

        t0 = time.monotonic()
        try:
            proc = subprocess.run(
                cmd,
                input=user,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout or self.timeout,
                cwd=str(_NEUTRAL_CWD),
            )
        except subprocess.TimeoutExpired as e:
            raise LLMError(f"{timeout or self.timeout}초 안에 응답이 없었다") from e
        finally:
            self.calls += 1
            self.elapsed += time.monotonic() - t0

        return self._envelope(proc)

    # ── 내부 ──────────────────────────────────────────────────────────
    def _envelope(self, proc: subprocess.CompletedProcess) -> dict:
        """stdout 을 봉투 dict 로. 사용량·비용을 누적한다.

        --output-format json 이 안 먹어 본문이 그대로 온 경우는
        `{"result": <본문>, "_raw": True}` 로 감싼다.
        """
        raw = (proc.stdout or "").strip()
        if not raw:
            err = (proc.stderr or "").strip() or f"종료 코드 {proc.returncode}"
            raise LLMError(f"CLI 가 아무것도 내지 않았다: {err[:300]}")

        try:
            env = json.loads(raw)
        except json.JSONDecodeError:
            if proc.returncode != 0:
                raise LLMError(f"CLI 실패({proc.returncode}): {raw[:300]}") from None
            return {"result": raw, "_raw": True, "returncode": proc.returncode}

        u = env.get("usage") or {}
        self.tokens_in += int(u.get("input_tokens", 0) or 0) + \
            int(u.get("cache_read_input_tokens", 0) or 0) + \
            int(u.get("cache_creation_input_tokens", 0) or 0)
        self.tokens_out += int(u.get("output_tokens", 0) or 0)
        self.cost_usd += float(env.get("total_cost_usd", 0.0) or 0.0)
        env["returncode"] = proc.returncode
        return env

    def _text_of(self, env: dict) -> str:
        """봉투에서 본문을 꺼낸다. 종료 코드 0 이어도 is_error 가 설 수 있다 — 인증 실패."""
        text = env.get("result", "")
        if env.get("is_error") or env.get("returncode", 0) != 0:
            if self.is_auth_error(text):
                raise LLMError(self._hint())
            raise LLMError(f"CLI 오류: {str(text)[:300]}")
        return text

    @staticmethod
    def is_auth_error(text: Any) -> bool:
        s = str(text)
        return "Not logged in" in s or "/login" in s

    def auth_status(self) -> dict:
        """`claude auth status` 를 그대로 돌려준다."""
        try:
            proc = subprocess.run(
                [self.exe, "auth", "status"],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=30, cwd=str(_NEUTRAL_CWD),
            )
        except (OSError, subprocess.TimeoutExpired) as e:
            return {"loggedIn": False, "raw": str(e)[:200]}
        try:
            return json.loads((proc.stdout or "").strip())
        except json.JSONDecodeError:
            return {"loggedIn": False, "raw": (proc.stdout or proc.stderr or "")[:300]}

    def require_login(self) -> None:
        """로그인 안 됐으면 첫 스텝 전에 죽는다. 60스텝 돌다 죽는 것보다 낫다."""
        if not self.auth_status().get("loggedIn"):
            raise LLMError(self._hint())

    def _hint(self) -> str:
        return LOGIN_HINT.replace("<claude.exe>", f'"{self.exe}"')

    def ask_json(self, system: str, user: str) -> dict:
        return extract_json(self.ask(system, user))

    def __repr__(self) -> str:
        return f"ClaudeCLI(model={self.model!r}, calls={self.calls})"


if __name__ == "__main__":
    # 배선 점검:  python -m agent.llm.claude_cli
    cli = ClaudeCLI()
    print(f"실행 파일 {cli.exe}")
    print(f"인증     {cli.auth_status()}")
    try:
        got = cli.ask_json(
            "너는 JSON 만 낸다. 다른 말을 붙이지 않는다.",
            '{"ok": true} 를 그대로 출력해라.',
        )
        print(f"응답 {got} · {cli.elapsed:.1f}초")
    except LLMError as e:
        print(f"[실패] {e}", file=sys.stderr)
        raise SystemExit(1)
