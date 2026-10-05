"""도구 게이트웨이 — LLM 과 서버 5개 사이의 단일 관문.

Claude CLI 는 이 게이트웨이 하나에 MCP(HTTP) 로 붙는다. 게이트웨이는

  1. `McpBackend` 로 ①~⑤ 를 **한 번** 기동해 에피소드 내내 붙들고 있다.
     ①은 배분·용량·이력을 메모리에 들고 있어, CLI 가 스텝마다 서버를 새로 띄우면
     상태가 사라진다. 그래서 stdio 가 아니라 HTTP 다.
  2. 서버가 광고한 도구를 **이름·설명·입력 스키마 그대로** 재노출한다.
     설명을 고치면 ②의 `SLICE_DESC_MODE` 실험이 오염된다.
  3. 모든 반환값을 `Guard` 에 통과시킨다 (flow/forbidden.md).
  4. 호출 하나하나를 스텝 단위로 기록한다 — 심판(`referee.py`)의 입력이다.
  5. 스텝당 호출 상한을 넘으면 **값으로** 거부한다 (flow/errors.md).

`reset` 은 재노출하지 않는다. 에피소드 초기화는 실험 설정이라 호스트가 직접 부른다.
LLM 이 실수로 부르면 60스텝 기록이 사라지는데, 그건 "판단"이 아니라 사고다.

여기에 **판단은 없다.** 어느 도구를 언제 부를지는 전부 LLM 이 정한다.
"""

from __future__ import annotations

import asyncio
import json
import logging
import socket
import threading
import time
from pathlib import Path
from typing import Any, Optional

from fastmcp import FastMCP
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.tools import Tool, ToolResult
from pydantic import PrivateAttr

from ..backends.mcp import McpBackend
from ..guard import ForbiddenLeak, Guard
from ..deciders.rule import situation_posterior
from ..schema import (ESCALATION_THRESHOLD, SITUATION_ESCALATION_THRESHOLD, escalation_check,
                      escalation_mode)
from ..trace import MARK, brief

logger = logging.getLogger(__name__)

# CLI 의 mcp.json 에 등록하는 서버 이름. 도구는 `mcp__slice__<tool>` 로 보인다.
SERVER_NAME = "slice"

# LLM 에 내보내지 않는 도구. 실험 설정은 호스트 소관이다.
HIDDEN = {("observe", "reset")}

DEFAULT_MAX_CALLS = 20

# 실행 조건(config)을 끼워 넣을 ④ 기록 도구.
RECORD_TOOLS = frozenset({"record_decision", "record_escalation"})

# 콘솔 추적의 경로 표기. 같은 서버 도구라도 누가 불렀는지 한눈에 갈리게.
VIA_MCP = "[MCP→LLM]"    # CLI 안의 LLM 이 MCP(HTTP) 로 게이트웨이를 거쳐 부른 것
VIA_HOST = "[host    ]"  # 호스트가 직통으로 부른 것 (reset · get_metrics). LLM 은 모른다
ARGS_WIDTH = 72          # 콘솔에 실을 인자 요약 길이

# 게이트웨이 자체 도구. 서버 어디에도 없고 에이전트 쪽 공식(schema.py)을 그대로 옮겼다.
CONFIDENCE_DESC = (
    "결합 신뢰도를 계산한다. combined = √(intrinsic × empirical). "
    "intrinsic 은 propose_allocation 이 낸 confidence, "
    "empirical 은 get_reliability_table 의 그 정책 effective 다. "
    "escalate 가 true 면 record_decision 대신 record_escalation 을 부른다. 기본 판정은 상황 확신이다 — "
    f"지금까지 관측한 트래픽으로 본 상황 사후확률의 최댓값(situation_confidence)이 {SITUATION_ESCALATION_THRESHOLD} "
    "미만이면 escalate 가 true 다(에이전트가 지금 상황을 확신하지 못할 때만 사람을 부른다). "
    f"예전 판정(combined 가 {ESCALATION_THRESHOLD} 미만이거나 empirical 이 하한 미만)은 trigger 로 함께 알려준다."
)


# 게이트웨이 자체 도구 둘째 (반복 5 · 2026-10-03). 고정 루프의 규칙 판단자가 쓰는 상황 추론(우도 HMM)을
# 오케스트레이터 LLM 도 쓸 수 있게 내놓는다. LLM 은 매 스텝 관측 하나와 직전 요약만 보는데, 한 스텝 트래픽은
# 잡음이 커서(σ 0.1 이 mmtc 평균의 절반) Claude 의 상황 인지가 0.65~0.75 에 머물렀다(9/29 · TF 환경).
# 판단을 대신하지 않는다 — 근거를 하나 더 줄 뿐이고, situation 은 여전히 LLM 이 정한다.
SITUATION_DESC = (
    "지금까지 관측한 트래픽의 슬라이스 구성으로 상황별 사후확률을 낸다. 상황마다 수요 모양(어느 슬라이스 "
    "수요가 몇 배가 되는가)과 트래픽 잡음으로 우도를 매기고, 상황은 잘 바뀌지 않는다는 사전으로 스텝을 잇는다. "
    "이용률은 배분의 결과라 대응하면 증상이 사라지지만 트래픽은 배분과 무관하다. 추정이지 정답이 아니다 — "
    "situation 은 네가 정한다. get_observation 뒤에 부른다."
)


class CallLog:
    """스텝 단위 호출 기록. 심판이 읽고, 파일(calls.jsonl)에도 남는다."""

    def __init__(self, path: Path):
        self.step: Optional[int] = None
        self.attempt: Optional[int] = None
        self.entries: list[dict] = []
        self._seq = 0
        self._fh = open(path, "a", encoding="utf-8")
        self._lock = threading.Lock()

    def begin_step(self, step: int, attempt: Optional[int] = None) -> None:
        """step 은 환경 스텝, attempt 는 호스트의 시도 번호.

        LLM 이 스텝을 끝내지 못하면(환경이 전진하지 않으면) 호스트가 같은 step 을 다시
        시도한다. 그때 step 은 같고 attempt 가 다르다 — 심판·호출 상한은 시도 단위다.
        """
        with self._lock:
            self.step = step
            self.attempt = step if attempt is None else attempt
            self._seq = 0

    def record(self, **entry: Any) -> dict:
        with self._lock:
            self._seq += 1
            row = {"step": self.step, "attempt": self.attempt, "seq": self._seq,
                   "ts": time.time(), **entry}
            self.entries.append(row)
            self._fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
            self._fh.flush()
            return row

    def for_step(self, step: int) -> list[dict]:
        return [e for e in self.entries if e["step"] == step]

    def current(self) -> list[dict]:
        """지금 시도의 호출만. 같은 스텝의 앞선 시도는 섞지 않는다."""
        return [e for e in self.entries if e["attempt"] == self.attempt]

    def close(self) -> None:
        try:
            self._fh.close()
        except OSError:
            pass


class PassthroughTool(Tool):
    """서버 도구 하나를 그대로 전달한다. 스키마·설명은 서버가 낸 것."""

    _server: str = PrivateAttr()
    _backend: McpBackend = PrivateAttr()

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        # backend.call 은 전용 스레드의 루프를 블로킹으로 기다린다. 이 루프를 막지 않게 스레드로.
        out = await asyncio.to_thread(self._backend.call, self._server, self.name, arguments)
        return _to_result(out)


class GatewayMiddleware(Middleware):
    """호출 상한 · Guard · 기록. 도구 종류를 가리지 않고 한 곳에서 건다."""

    def __init__(self, gw: "Gateway"):
        self._gw = gw

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        gw = self._gw
        name = context.message.name
        args = dict(context.message.arguments or {})
        server = gw.server_of.get(name, "gateway")
        mark = MARK.get(server, "⌂")
        step = gw.log.step

        # 실행 조건을 ④ 장부에 남긴다. 고정 루프는 loop.py 가 넘기는데, 여기서는 LLM 이
        # 기록 도구를 직접 부르므로 게이트웨이가 끼워 넣는다. 판단이 아니라 메타데이터라
        # LLM 의 몫이 아니고, LLM 이 config 를 넣었더라도 호스트 값이 이긴다 — arm 이나
        # scenario 를 LLM 이 바꿔 적으면 산출물이 다른 실행으로 오인된다.
        if name in RECORD_TOOLS and gw.run_config:
            args["config"] = {**(args.get("config") or {}), **gw.run_config}
            context = context.copy(
                message=context.message.model_copy(update={"arguments": args}))

        # 위반 보정량(D1-b)을 게이트웨이가 붙인다. ② rule_based 는 목표 배분과 보정량을 따로 내고, ①이
        # 평활 뒤에 보정량을 더한다(원본 순서). 그런데 LLM 이 보정량을 옮기는 걸 잊으면 보정이 통째로 사라진다
        # (관측의 features · recent_error 를 빠뜨린 실측이 있다). 그래서 이번 시도에 ②가 낸 rule_based 배분과
        # **같은 배분**을 적용·기록하면 그 제안의 보정량을 끼워 넣는다. 판단을 바꾸지 않는다 — LLM 이 고른 배분에
        # 그 배분의 짝을 붙일 뿐이고, LLM 이 직접 넣었으면 건드리지 않는다.
        injected = None
        if name == "apply_allocation" and args.get("correction") is None:
            injected = gw.correction_for({k: args.get(k) for k in ("embb", "urllc", "mmtc")})
            if injected is not None:
                args["correction"] = injected
        elif name == "record_escalation" and args.get("agent_correction") is None:
            injected = gw.correction_for(args.get("agent_allocation"))
            if injected is not None:
                args["agent_correction"] = injected
        if injected is not None:
            context = context.copy(
                message=context.message.model_copy(update={"arguments": args}))

        # 사람에게 묻기 (2026-10-05 개입 재설계). LLM 이 record_escalation 을 부르면 불려 온 사람이 원본 운영자처럼
        # 지금 상황 라벨을 답하고, 게이트웨이가 그 라벨의 rule_based 배분을 받아 ④에 넘긴다 — ④가 폴백 대신 그것을
        # 적용 · 기록하고 LLM 은 반환된 fallback_allocation 을 적용한다. 사람의 답은 이 경로로만 들어온다.
        human_answer = None
        if name == "record_escalation" and gw.human is not None and isinstance(args.get("observation"), dict):
            human_answer = gw.ask_human(int(args.get("step", gw.log.step or 0)), args["observation"])
            if human_answer is not None:
                args.update(human_answer)
                context = context.copy(
                    message=context.message.model_copy(update={"arguments": args}))

        if step is not None and len(gw.log.current()) >= gw.max_calls:
            out = {
                "error": "call_budget_exceeded",
                "detail": f"이 스텝의 도구 호출이 {gw.max_calls}회를 넘었다. "
                          "판단을 요약 JSON 으로 마무리하라.",
            }
            gw.log.record(server=server, tool=name, args=args, refused=True, result=out)
            gw.budget_hits += 1
            logger.debug("  %s %s %s(%s)\n        ✗ 상한 초과 — 게이트웨이가 값으로 거부",
                         VIA_MCP, mark, name, brief(args, ARGS_WIDTH))
            return _to_result(out)

        t0 = time.monotonic()
        error: Optional[str] = None
        try:
            result = await call_next(context)
        except Exception as e:  # 도구가 예외를 냈다 — 계약 위반 (flow/errors.md)
            error = f"{type(e).__name__}: {e}"
            gw.log.record(server=server, tool=name, args=args, ok=False, error=error,
                          elapsed=time.monotonic() - t0)
            # 서버가 예외를 냈다 = 인자가 계약을 어겼다 (flow/errors.md). LLM 은 이 문구를
            # 받아 스스로 고친다. 콘솔에는 "왜" 가 보여야 하므로 메시지를 그대로 싣는다.
            logger.debug("  %s %s %s(%s)\n        ✗ 예외 — %s",
                         VIA_MCP, mark, name, brief(args, ARGS_WIDTH), brief(error, 200))
            raise

        payload = _payload_of(result)
        try:
            gw.guard.check(payload, f"{server}.{name}")
        except ForbiddenLeak as leak:
            # 폐기 사유를 남기고 LLM 에게도 돌려주지 않는다.
            gw.leak = leak
            gw.log.record(server=server, tool=name, args=args, ok=False, leak=str(leak))
            raise

        gw.log.record(
            server=server, tool=name, args=args, ok=True,
            result=payload, elapsed=time.monotonic() - t0,
            **_extract(name, payload),
            **({"correction_injected": True} if injected is not None else {}),
        )
        if name in ("propose_allocation", "compare_policies"):
            gw.remember_corrections(payload)
        if name in ("get_observation", "step"):
            gw.remember_traffic(name, payload)
        # 콘솔: 경로(MCP) · 서버 · 함수(인자 요약) → 반환 요약. 파일: 인자·반환 전문.
        logger.debug(
            "  %s %s %s(%s)\n        → %s",
            VIA_MCP, mark, name, brief(args, ARGS_WIDTH), brief(payload),
            extra={"full": f"  {VIA_MCP} {mark} {name}({brief(args, 10**6)})"
                           f"\n        → {brief(payload, 10**6)}"},
        )
        return result


class Gateway:
    """서버 5개 + 게이트웨이 도구를 HTTP 로 내보내는 프로세스 내 서버."""

    def __init__(
        self,
        run_id: str,
        out_dir: Path,
        desc_mode: str = "minimal",
        memory_mode: str = "warm",
        server_log_dir: Optional[Path] = None,
        max_calls: int = DEFAULT_MAX_CALLS,
        guard: Optional[Guard] = None,
        host: str = "127.0.0.1",
        port: int = 0,
        human: Optional[Any] = None,
    ):
        self.run_id = run_id
        # 개입 때 불려 올 사람 (2026-10-05 개입 재설계) — (run_id, step) → 지금 상황 라벨. 없으면 예전 D4 폴백.
        self.human = human
        self.human_labels: dict[int, str] = {}     # 사람이 답한 스텝 → 라벨. 상황 추정이 반영한다
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.max_calls = max_calls
        self.guard = guard or Guard(enabled=True)
        self.leak: Optional[ForbiddenLeak] = None
        self.budget_hits = 0
        self.corrections: list[tuple[dict, dict]] = []   # 이번 시도의 (rule_based 배분, 보정량) — D1-b
        # 에피소드에서 관측된 스텝별 트래픽 — estimate_situation 의 입력 (반복 5). reset 이 비운다.
        self.traffic_by_step: dict[int, dict] = {}
        self.server_of: dict[str, str] = {}
        # 호스트가 에피소드 시작 전에 채운다. ④ 기록 도구 호출에 끼워 넣는다.
        self.run_config: dict[str, Any] = {}

        self.backend = McpBackend(
            desc_mode=desc_mode, memory_mode=memory_mode,
            run_id=run_id, log_dir=server_log_dir,
        )
        self.log = CallLog(self.out_dir / "calls.jsonl")

        self._host = host
        self._port = port or _free_port(host)
        self._mcp = self._build()
        self._server = None
        self._thread: Optional[threading.Thread] = None

    # ── 공개 ─────────────────────────────────────────────────────────
    @property
    def url(self) -> str:
        return f"http://{self._host}:{self._port}/mcp"

    @property
    def exposed(self) -> list[str]:
        return sorted(self.server_of)

    def call(self, server: str, tool: str, **args: Any) -> Any:
        """호스트 전용 직통 — reset · get_metrics. LLM 의 호출 기록에 섞이지 않는다."""
        args = {k: v for k, v in args.items() if v is not None}
        out = self.backend.call(server, tool, args)
        out = self.guard.check(out, f"{server}.{tool}")
        if tool == "reset":
            self.traffic_by_step = {}
            self.human_labels = {}
            self.remember_traffic("reset", out)
        logger.debug(
            "  %s %s %s(%s)\n        → %s",
            VIA_HOST, MARK.get(server, " "), tool, brief(args, ARGS_WIDTH), brief(out),
            extra={"full": f"  {VIA_HOST} {MARK.get(server, ' ')} {tool}({brief(args, 10**6)})"
                           f"\n        → {brief(out, 10**6)}"},
        )
        return out

    def begin_step(self, step: int, attempt: Optional[int] = None) -> None:
        self.log.begin_step(step, attempt)
        self.corrections = []

    def situation_estimate(self) -> Optional[dict[str, float]]:
        """관측된 트래픽 열의 상황 사후확률 — 사람이 답한 스텝은 그 라벨로 고정(규칙 판단자의 absorb_label 과 같다)."""
        steps = sorted(self.traffic_by_step)
        if not steps:
            return None
        anchors = {i: self.human_labels[s] for i, s in enumerate(steps) if s in self.human_labels}
        return situation_posterior([self.traffic_by_step[s] for s in steps], anchors)

    def ask_human(self, step: int, observation: dict) -> Optional[dict]:
        """불려 온 사람의 답 → {human_situation, human_allocation}. 배분을 못 받으면 None (④ D4 폴백)."""
        label = self.human(self.run_id, step)
        prop = self.backend.call("policy", "propose_allocation",
                                 {"policy": "rule_based", "observation": observation, "situation": label})
        if not isinstance(prop, dict) or not prop.get("allocation"):
            return None
        self.human_labels[step] = label
        return {"human_situation": label, "human_allocation": prop["allocation"]}

    def remember_traffic(self, tool: str, payload: Any) -> None:
        """관측(get_observation · step · reset 결과)의 트래픽을 스텝별로 모은다. 같은 스텝은 덮어쓴다."""
        obs = payload if tool == "get_observation" else (payload or {}).get("observation")
        if isinstance(obs, dict) and isinstance(obs.get("traffic"), dict) and "step" in obs:
            self.traffic_by_step[int(obs["step"])] = dict(obs["traffic"])

    def remember_corrections(self, payload: Any) -> None:
        """② 결과에서 rule_based 제안의 (배분, 보정량) 을 모은다. compare_policies 는 목록이다."""
        props = payload if isinstance(payload, list) else [payload]
        for p in props:
            if (isinstance(p, dict) and p.get("policy") == "rule_based"
                    and isinstance(p.get("allocation"), dict) and isinstance(p.get("correction"), dict)):
                self.corrections.append((p["allocation"], p["correction"]))

    def correction_for(self, allocation: Any) -> Optional[dict]:
        """이번 시도에 ②가 낸 rule_based 배분과 같은 배분이면 그 보정량. 아니면 None."""
        if not isinstance(allocation, dict):
            return None
        try:
            want = {k: float(allocation[k]) for k in ("embb", "urllc", "mmtc")}
        except (KeyError, TypeError, ValueError):
            return None
        total = sum(want.values()) or 1.0
        want = {k: v / total for k, v in want.items()}      # ①은 정규화하므로 비율로 비교
        for alloc, corr in reversed(self.corrections):
            t = sum(float(v) for v in alloc.values()) or 1.0
            if all(abs(float(alloc[k]) / t - want[k]) <= 1e-4 for k in want):
                return dict(corr)
        return None

    def start(self) -> str:
        import uvicorn

        # FastMCP 는 도구 예외를 자기 로거로 "Error calling tool 'x'" 라고 한 줄 더 찍는다.
        # 원인 없는 중복이라 끈다 — 같은 예외를 미들웨어가 인자·메시지와 함께 이미 남긴다.
        logging.getLogger("fastmcp").setLevel(logging.CRITICAL)
        logging.getLogger("FastMCP").setLevel(logging.CRITICAL)

        app = self._mcp.http_app(path="/mcp")
        config = uvicorn.Config(app, host=self._host, port=self._port,
                                log_level="warning", access_log=False)
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run,
                                        name="orchestrator-gateway", daemon=True)
        self._thread.start()
        _wait_port(self._host, self._port)
        return self.url

    def write_mcp_config(self, path: Optional[Path] = None) -> Path:
        """CLI 가 읽을 mcp.json. 게이트웨이 하나만 등록한다."""
        path = path or (self.out_dir / "servers.json")
        cfg = {"mcpServers": {SERVER_NAME: {"type": "http", "url": self.url}}}
        path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        return path

    def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=10)
        self.log.close()
        self.backend.close()

    # ── 내부 ─────────────────────────────────────────────────────────
    def _build(self) -> FastMCP:
        mcp = FastMCP(f"slice-gateway[{self.run_id}]")

        for server in self.backend.live:
            for t in self.backend.list_tools(server):
                if (server, t.name) in HIDDEN:
                    continue
                schema = getattr(t, "input_schema", None) or getattr(t, "inputSchema", None) \
                    or {"type": "object", "properties": {}}
                tool = PassthroughTool(
                    name=t.name,
                    description=t.description or "",
                    parameters=schema,
                )
                tool._server = server
                tool._backend = self.backend
                mcp.add_tool(tool)
                self.server_of[t.name] = server

        @mcp.tool(name="compute_confidence", description=CONFIDENCE_DESC)
        def compute_confidence(intrinsic: float, empirical: float) -> dict:
            chk = escalation_check(intrinsic, empirical)   # 고정 루프와 같은 함수 (schema.py)
            out = {
                "intrinsic": round(float(intrinsic), 4),
                "empirical": round(float(empirical), 4),
                "combined": round(chk["combined"], 4),
                "threshold": ESCALATION_THRESHOLD,
                "empirical_floor": chk["empirical_floor"],
                "escalate": chk["escalate"],
                "trigger": chk["trigger"],
            }
            # 기본 판정은 상황 확신 (고정 루프 schema.Decision.escalate 와 같은 규칙 · 2026-10-05).
            post = self.situation_estimate() if escalation_mode() == "situation" else None
            if post:
                conf = max(post.values())
                out.update(situation_confidence=round(conf, 4),
                           situation_threshold=SITUATION_ESCALATION_THRESHOLD,
                           escalate=conf < SITUATION_ESCALATION_THRESHOLD,
                           trigger="situation" if conf < SITUATION_ESCALATION_THRESHOLD else None,
                           confidence_formula_trigger=chk["trigger"])
            return out

        self.server_of["compute_confidence"] = "gateway"

        @mcp.tool(name="estimate_situation", description=SITUATION_DESC)
        def estimate_situation() -> dict:
            steps = sorted(self.traffic_by_step)
            if not steps:
                return {"error": "no_observation",
                        "detail": "관측한 트래픽이 없다. get_observation 을 먼저 부른다."}
            # 규칙 판단자(고정 루프)와 같은 필터를 이 에피소드에서 관측된 트래픽 열에 돌린다 (사람이 답한 스텝 반영).
            post = self.situation_estimate()
            return {"step": steps[-1], "steps_used": len(steps),
                    "posterior": {s: round(p, 4) for s, p in post.items()},
                    "most_likely": max(post, key=post.get)}

        self.server_of["estimate_situation"] = "gateway"
        mcp.add_middleware(GatewayMiddleware(self))
        return mcp


# ── 도우미 ───────────────────────────────────────────────────────────
def _to_result(out: Any) -> ToolResult:
    text = json.dumps(out, ensure_ascii=False, default=str)
    if isinstance(out, dict):
        return ToolResult(content=text, structured_content=out)
    return ToolResult(content=text)


def _payload_of(result: Any) -> Any:
    """ToolResult → 검사·기록용 파이썬 값."""
    sc = getattr(result, "structured_content", None)
    if sc is not None:
        return sc
    content = getattr(result, "content", None)
    if isinstance(content, list):
        texts = [getattr(c, "text", None) for c in content]
        texts = [t for t in texts if t is not None]
        if len(texts) == 1:
            try:
                return json.loads(texts[0])
            except (json.JSONDecodeError, TypeError):
                return texts[0]
        return texts
    return result


def _extract(tool: str, payload: Any) -> dict:
    """심판·요약이 바로 쓰는 몇 가지 값만 꺼내 둔다."""
    if not isinstance(payload, dict):
        return {}
    keep = {}
    if tool in ("record_decision", "record_escalation"):
        keep["decision_id"] = payload.get("decision_id")
    if tool == "step":
        keep["episode_done"] = bool(payload.get("episode_done", False))
        keep["obs_step"] = (payload.get("observation") or {}).get("step")
    if tool == "report_outcome":
        keep["sla_met"] = payload.get("sla_met")
        keep["vendor_id"] = payload.get("vendor_id")
    if tool == "compute_confidence":
        keep["escalate"] = payload.get("escalate")
        keep["combined"] = payload.get("combined")
    if tool == "procure":
        keep["vendor_id"] = payload.get("vendor_id")
        keep["cost_total"] = payload.get("cost_total")
    # 값으로 돌려준 거부 (flow/errors.md). 코드는 문자열이다 — ⑤ report_outcome 의
    # `error` 는 배분 오차(float)라 거부가 아니다.
    if isinstance(payload.get("error"), str):
        keep["value_error"] = payload["error"]
    if payload.get("accepted") is False or payload.get("status") == "rejected":
        keep["value_error"] = keep.get("value_error") or payload.get("status") or "not_accepted"
    return keep


def _free_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return s.getsockname()[1]


def _wait_port(host: str, port: int, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.2)
            try:
                s.connect((host, port))
                return
            except OSError:
                time.sleep(0.1)
    raise RuntimeError(f"게이트웨이가 {timeout}초 안에 {host}:{port} 를 열지 않았다")
