"""오케스트레이터 호스트 — 스텝 경계만 잡고, 스텝 안은 LLM 에게 맡긴다.

    run.py --driver orchestrator --scenario mixed --seed 0

한 에피소드:

    게이트웨이 기동 (서버 5개 + HTTP)
    reset(run_id, scenario, seed)               ← 호스트 직통. 실험 설정이라 LLM 몫이 아니다
    for t in range(total_steps):
        프롬프트 = 의도 + 직전 5스텝 요약 + "이번 스텝을 수행하라"
        claude -p  ──(MCP)──▶ 게이트웨이 ──▶ ①②③④⑤   ← 스텝 안의 모든 호출은 LLM 이 정한다
        심판이 호출 기록을 판정 (막지 않고 기록만)
        step 결과에 episode_done 이 서면 종료
    get_metrics                                  ← 호스트 직통

호스트가 **하지 않는 것**: 도구 호출 순서 결정 · 에스컬레이션 판정 · 조달 판단 · 벤더 선택.
전부 LLM 이 한다. 그래서 `agent/loop.py` 의 고정 루프가 이 구조의 대조군이 된다.

컨텍스트는 스텝마다 새로 만든다 (flow/loop.md §3.4). 120스텝 대화를 이어붙이면
후반에 100k 토큰을 넘고, 모델이 낡은 관측에 주의를 뺏긴다.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from ..guard import ForbiddenLeak, Guard
from ..llm import LLMError, extract_json
from ..llm.claude_cli import ClaudeCLI
from ..trace import brief
from .gateway import SERVER_NAME, Gateway
from .referee import RefereeLog, Verdict, judge

logger = logging.getLogger(__name__)

HERE = Path(__file__).resolve().parent
PROMPT_FILE = HERE / "prompt.md"

SITUATIONS = ("normal", "emergency", "special_event", "iot_surge")
RECENT_N = 5              # 프롬프트에 넣는 직전 스텝 요약 수 (flow/loop.md §3.4)
DEFAULT_STEP_TIMEOUT = 300.0
DEFAULT_STEP_BUDGET_USD = 0.50

# LLM 이 스텝 끝에 내는 요약. CLI 의 --json-schema 로 강제한다.
SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "situation": {"type": "string", "enum": list(SITUATIONS)},
        "situation_confidence": {"type": "number", "minimum": 0, "maximum": 1},
        # 네 상황을 각각 얼마나 그럴듯하게 봤나. "어떤 비율로 잡혀서 무엇이 선택됐나" 를
        # 리포트에 그리기 위한 것이고, 판단 자체는 여전히 situation 하나다.
        "situation_scores": {
            "type": "object",
            "properties": {s: {"type": "number", "minimum": 0, "maximum": 1} for s in SITUATIONS},
            "required": list(SITUATIONS),
        },
        "policy": {"type": "string"},
        "procured": {"type": "boolean"},
        "escalated": {"type": "boolean"},
        "reasoning": {"type": "string"},
    },
    "required": ["situation", "situation_confidence", "situation_scores", "policy",
                 "procured", "escalated", "reasoning"],
}


@dataclass
class StepReport:
    """스텝 하나의 결과. LLM 의 자기 보고(answer)와 심판의 사실(verdict)을 나란히 둔다."""

    step: int
    verdict: Verdict
    answer: Optional[dict] = None       # LLM 요약 JSON. 형식 위반이면 None
    malformed: bool = False
    llm_error: Optional[str] = None
    turns: int = 0
    cost_usd: float = 0.0
    elapsed: float = 0.0

    @property
    def situation(self) -> Optional[str]:
        return (self.answer or {}).get("situation")

    @property
    def policy(self) -> Optional[str]:
        return (self.answer or {}).get("policy")

    def summary_line(self) -> str:
        """다음 스텝 프롬프트에 들어가는 한 줄. 사실은 심판 것을 쓴다."""
        v = self.verdict
        viol = ",".join(x["code"] for x in v.violations) or "-"
        return (f"step {self.step} · situation={self.situation or '?'} · "
                f"policy={self.policy or '?'} · 개입={'예' if v.escalated else '아니오'} · "
                f"조달={'예' if v.procured else '아니오'} · sla_met={v.sla_met} · 위반={viol}")

    def as_row(self) -> dict:
        d = asdict(self)
        d["verdict"] = self.verdict.as_row()
        return d


@dataclass
class EpisodeResult:
    run_id: str
    reports: list[StepReport] = field(default_factory=list)
    metrics: Optional[dict] = None
    procedure: Optional[dict] = None
    llm_calls: int = 0
    llm_elapsed: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0


class OrchestratorHost:
    def __init__(
        self,
        run_id: str,
        root: Path,
        *,
        model: str = "sonnet",
        exe: Optional[str] = None,
        step_timeout: float = DEFAULT_STEP_TIMEOUT,
        step_budget_usd: float = DEFAULT_STEP_BUDGET_USD,
        desc_mode: str = "minimal",
        memory_mode: str = "warm",
        max_calls: int = 20,
        prompt_file: Path = PROMPT_FILE,
    ):
        self.run_id = run_id
        self.root = Path(root)
        self.out_dir = self.root / "runs" / run_id / "orchestrator"
        self.out_dir.mkdir(parents=True, exist_ok=True)

        self.guard = Guard(enabled=True)
        self.cli = ClaudeCLI(exe=exe, model=model, timeout=step_timeout)
        self.step_timeout = step_timeout
        self.step_budget_usd = step_budget_usd
        self.prompt_file = Path(prompt_file)
        # 시스템 프롬프트도 컨텍스트다. 금지 문자열이 있으면 시작 전에 죽는다.
        self.guard.check_text(self.prompt_file.read_text(encoding="utf-8"), "prompt.md")

        self.gateway = Gateway(
            run_id, self.out_dir,
            desc_mode=desc_mode, memory_mode=memory_mode,
            server_log_dir=self.root / "runs" / run_id / "servers",
            max_calls=max_calls, guard=self.guard,
        )
        self.referee = RefereeLog(self.out_dir / "referee.jsonl")
        self._steps_fh = open(self.out_dir / "steps.jsonl", "a", encoding="utf-8")
        self._mcp_config: Optional[Path] = None

    # ── 공개 ─────────────────────────────────────────────────────────
    def run_episode(
        self,
        scenario: str,
        seed: int,
        max_steps: Optional[int] = None,
        intent: Optional[str] = None,
        config: Optional[dict] = None,
    ) -> EpisodeResult:
        self.cli.require_login()
        # ④ 장부에 남길 실행 조건. LLM 이 기록 도구를 부를 때 게이트웨이가 끼워 넣는다.
        self.gateway.run_config = dict(config or {})
        url = self.gateway.start()
        self._mcp_config = self.gateway.write_mcp_config()
        logger.info("게이트웨이 %s · 도구 %d개 (%s)", url, len(self.gateway.exposed),
                    " ".join(self.gateway.exposed))

        info = self.gateway.call("observe", "reset", run_id=self.run_id,
                                 scenario=scenario, seed=seed)
        total = int(info.get("total_steps", 60))
        limit = total if max_steps is None else min(total, max_steps)

        result = EpisodeResult(run_id=self.run_id)
        try:
            for t in range(limit):
                logger.debug("─── 스텝 %d %s", t, "─" * 56)
                rep = self._run_step(t, total, intent, result.reports)
                result.reports.append(rep)
                self._steps_fh.write(json.dumps(rep.as_row(), ensure_ascii=False,
                                                default=str) + "\n")
                self._steps_fh.flush()

                if self.gateway.leak is not None:
                    raise self.gateway.leak
                if rep.verdict.episode_done:
                    break

            result.metrics = self.gateway.call("audit", "get_metrics")
        finally:
            result.procedure = self.referee.summary()
            result.llm_calls = self.cli.calls
            result.llm_elapsed = self.cli.elapsed
            result.tokens_in = self.cli.tokens_in
            result.tokens_out = self.cli.tokens_out
            result.cost_usd = self.cli.cost_usd
            self._write_summary(result, scenario, seed, intent)
        return result

    def close(self) -> None:
        self.referee.close()
        try:
            self._steps_fh.close()
        except OSError:
            pass
        self.gateway.stop()

    # ── 스텝 ─────────────────────────────────────────────────────────
    def _run_step(self, t: int, total: int, intent: Optional[str],
                  history: list[StepReport]) -> StepReport:
        self.gateway.begin_step(t)
        user = self._prompt(t, total, intent, history)
        self.guard.check_text(user, f"prompt[{t}]")
        logger.debug("  ▶ LLM 프롬프트 %s", brief(user),
                     extra={"full": f"  ▶ LLM 프롬프트\n{user}"})

        answer: Optional[dict] = None
        malformed = False
        llm_error: Optional[str] = None
        turns = 0
        cost_before = self.cli.cost_usd
        t0 = time.monotonic()

        try:
            env = self.cli.invoke(user, self._cli_args(), timeout=self.step_timeout)
            turns = int(env.get("num_turns", 0) or 0)
            if env.get("is_error") or env.get("returncode", 0) != 0:
                text = str(env.get("result", ""))
                if self.cli.is_auth_error(text):
                    raise LLMError(self.cli._hint())
                llm_error = f"CLI 오류: {text[:300]}"
            else:
                answer, malformed = self._parse(env)
        except LLMError as e:
            if self.cli.is_auth_error(str(e)):
                raise
            # 시간 초과 등. 스텝 안에서 무엇이 일어났는지는 심판이 호출 기록으로 판정한다.
            llm_error = str(e)

        elapsed = time.monotonic() - t0
        budget_hit = any(c.get("refused") for c in self.gateway.log.for_step(t))
        verdict = self.referee.add(judge(t, self.gateway.log.for_step(t), budget_hit))

        rep = StepReport(step=t, verdict=verdict, answer=answer, malformed=malformed,
                         llm_error=llm_error, turns=turns,
                         cost_usd=self.cli.cost_usd - cost_before, elapsed=elapsed)

        logger.info(
            "스텝 %d · %s/%s · %s · 호출 %d · 위반 %d · %.0f초 · $%.3f%s",
            t, rep.situation or "?", rep.policy or "?",
            "개입" if verdict.escalated else "자율",
            verdict.calls, len(verdict.violations), elapsed, rep.cost_usd,
            f" · LLM 실패: {brief(llm_error, 60)}" if llm_error else "",
        )
        if answer is not None:
            logger.debug("  ◀ LLM 요약 %s", brief(answer),
                         extra={"full": f"  ◀ LLM 요약 {json.dumps(answer, ensure_ascii=False)}"})
        return rep

    def _cli_args(self) -> list[str]:
        return [
            "--system-prompt-file", str(self.prompt_file),
            "--mcp-config", str(self._mcp_config),
            "--strict-mcp-config",             # 게이트웨이 외의 MCP 서버를 붙이지 않는다
            "--restricted",                    # Bash 등 코드 실행 도구 제거 · 설정 파일 무시
            "--tools", "",                     # 내장 도구 전부 제거. 남는 것은 게이트웨이 도구만
            "--allowedTools", f"mcp__{SERVER_NAME}",   # 게이트웨이 도구는 묻지 않고 실행
            "--json-schema", json.dumps(SUMMARY_SCHEMA),
            "--max-budget-usd", f"{self.step_budget_usd:.2f}",
        ]

    def _parse(self, env: dict) -> tuple[Optional[dict], bool]:
        """요약 JSON 을 꺼내 검증한다. 형식 위반은 고치지 않고 센다 — 측정 대상이다."""
        out = env.get("structured_output")
        if not isinstance(out, dict):
            try:
                out = extract_json(str(env.get("result", "")))
            except LLMError:
                return None, True

        try:
            if out["situation"] not in SITUATIONS:
                raise ValueError(f"situation: {out['situation']!r}")
            c = float(out["situation_confidence"])
            if not 0.0 <= c <= 1.0:
                raise ValueError(f"situation_confidence: {c}")
            if not isinstance(out.get("policy"), str) or not out["policy"]:
                raise ValueError(f"policy: {out.get('policy')!r}")
            scores = out.get("situation_scores")
            if not isinstance(scores, dict) or set(scores) != set(SITUATIONS) \
                    or not all(isinstance(v, (int, float)) and 0.0 <= v <= 1.0 for v in scores.values()):
                raise ValueError(f"situation_scores: {scores!r}")
            for k in ("procured", "escalated"):
                if not isinstance(out.get(k), bool):
                    raise ValueError(f"{k}: {out.get(k)!r}")
        except (KeyError, TypeError, ValueError) as e:
            logger.debug("  ◀ 요약 형식 위반: %s · %s", e, brief(out))
            return out, True

        self.guard.check(out, "llm_summary")
        return out, False

    def _prompt(self, t: int, total: int, intent: Optional[str],
                history: list[StepReport]) -> str:
        blocks = []
        if intent:
            blocks.append(f"[사람이 준 의도]\n{intent}")
        blocks.append(f"[스텝]\n{t} / {total}")

        recent = history[-RECENT_N:]
        if recent:
            blocks.append("[직전 스텝 요약]\n" + "\n".join(r.summary_line() for r in recent))
        else:
            blocks.append("[직전 스텝 요약]\n(첫 스텝)")

        blocks.append(
            "[이번 스텝]\n"
            "이 스텝을 처음부터 끝까지 수행하라. 도구는 네가 정한 순서로 직접 부른다. "
            "의무를 모두 이행한 뒤 요약 JSON 하나만 출력한다."
        )
        return "\n\n".join(blocks)

    def _write_summary(self, r: EpisodeResult, scenario: str, seed: int,
                       intent: Optional[str]) -> None:
        reps = r.reports
        n = len(reps)
        situations: dict[str, int] = {}
        policies: dict[str, int] = {}
        for x in reps:
            situations[str(x.situation)] = situations.get(str(x.situation), 0) + 1
            policies[str(x.policy)] = policies.get(str(x.policy), 0) + 1

        summary = {
            "run_id": r.run_id,
            "driver": "orchestrator",
            "scenario": scenario,
            "seed": seed,
            "intent": intent,
            "model": self.cli.model,
            "prompt_file": str(self.prompt_file.relative_to(self.root)),
            "steps": n,
            "escalations": sum(1 for x in reps if x.verdict.escalated),
            "sla_violations": sum(1 for x in reps if x.verdict.sla_met is False),
            "procurements": sum(1 for x in reps if x.verdict.procured),
            "situations": situations,
            "policies": policies,
            "malformed": sum(1 for x in reps if x.malformed),
            "llm_failures": sum(1 for x in reps if x.llm_error),
            "procedure": r.procedure,
            "metrics": r.metrics,
            "llm": {
                "calls": r.llm_calls,
                "elapsed_sec": round(r.llm_elapsed, 1),
                "tokens_in": r.tokens_in,
                "tokens_out": r.tokens_out,
                "cost_usd": round(r.cost_usd, 4),
                "mean_turns_per_step": round(sum(x.turns for x in reps) / n, 1) if n else None,
            },
            "gateway": {
                "tools_exposed": self.gateway.exposed,
                "budget_hits": self.gateway.budget_hits,
                "max_calls_per_step": self.gateway.max_calls,
            },
        }
        (self.out_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

        # 사람이 볼 리포트. 정답 파일을 읽으므로 에이전트가 끝난 뒤 호스트에서만 만든다.
        self.report_path: Optional[Path] = None
        try:
            from eval.report import build_report
            self.report_path = build_report(self.run_id)
        except Exception as e:  # 리포트 실패가 실행 결과를 지우면 안 된다
            logger.warning("리포트 생성 실패: %s", e)


def print_summary(r: EpisodeResult, host: OrchestratorHost) -> None:
    reps = r.reports
    if not reps:
        print("스텝이 실행되지 않았다.")
        return
    n = len(reps)
    esc = sum(1 for x in reps if x.verdict.escalated)
    viol = sum(1 for x in reps if x.verdict.sla_met is False)
    proc = sum(1 for x in reps if x.verdict.procured)
    situations: dict = {}
    policies: dict = {}
    for x in reps:
        situations[x.situation] = situations.get(x.situation, 0) + 1
        policies[x.policy] = policies.get(x.policy, 0) + 1

    print(f"\n── {r.run_id} (orchestrator) ──")
    print(f"  스텝        {n}")
    print(f"  개입        {esc}   (자율 처리율 {1 - esc / n:.3f})")
    print(f"  SLA 위반    {viol}")
    print(f"  조달        {proc}")
    print(f"  상황 판단   {situations}")
    print(f"  정책 사용   {policies}")
    if r.metrics:
        m = r.metrics
        print(f"  ④ 지표      steps={m.get('steps')} interventions={m.get('interventions')} "
              f"sla_violations={m.get('sla_violations')} cost={m.get('procurement_cost_total')}")
    p = r.procedure or {}
    print(f"  절차 준수   {p.get('procedure_adherence')}  (깨끗한 스텝 {p.get('clean_steps')}/{n} · "
          f"오류 스텝 {p.get('error_steps')} · 스텝당 호출 {p.get('mean_calls_per_step')})")
    if p.get("violations_by_code"):
        print(f"  위반 유형   {p['violations_by_code']}")
    print(f"  LLM         {r.llm_calls}회 · {r.llm_elapsed:.1f}초 (스텝당 {r.llm_elapsed / n:.1f}초) · "
          f"형식위반 {sum(1 for x in reps if x.malformed)} · 실패 {sum(1 for x in reps if x.llm_error)}")
    print(f"  토큰        입력 {r.tokens_in:,} · 출력 {r.tokens_out:,} · 비용 ${r.cost_usd:.4f} "
          f"(스텝당 ${r.cost_usd / n:.4f})")
    print(f"  기록        {host.out_dir}")
    if getattr(host, "report_path", None):
        print(f"  리포트      {host.report_path}   ← 브라우저로 열어 본다")
