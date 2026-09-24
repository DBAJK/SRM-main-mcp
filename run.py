#!/usr/bin/env python3
"""에이전트 실행기.

드라이버 둘 (CLAUDE.md 절대 규칙 7):
  --driver fixed         파이썬이 순서를 정하고 LLM 은 판단만 (agent/loop.py). 기본.
                         목 백엔드 + 규칙 판단자로 배선을 검증하고, 실제 서버와 LLM 은
                         각각 --backend mcp, --decider llm 으로 갈아끼운다.
  --driver orchestrator  LLM 이 게이트웨이의 도구를 직접 들고 스텝의 흐름을 잡는다
                         (agent/orchestrator/). 항상 실서버 + Claude CLI.

사용 예
  python run.py --scenario emergency --steps 20
  python run.py --scenario mixed --seed 1 --backend mcp --decider llm
  python run.py --driver orchestrator --scenario mixed --seed 0 --fresh
"""

import argparse
import logging
import shutil
import subprocess
import sys
from pathlib import Path

from agent.backends.mock import MockBackend
from agent.deciders.rule import rule_decider
from agent.guard import ForbiddenLeak, Guard
from agent.llm import LLMError
from agent.loop import ToolRefused, run_episode
from agent.tools import Tools
from agent.trace import server_log_dir
from agent.trace import setup as setup_trace

ROOT = Path(__file__).resolve().parent
SCENARIOS = ("normal", "emergency", "special_event", "iot_surge", "mixed")


def build_backend(args):
    if args.backend == "mock":
        return MockBackend(seed=args.seed)

    from agent.backends.mcp import McpBackend

    mock_for = [s.strip() for s in args.mock_for.split(",") if s.strip()]
    run_id = f"{args.arm}-{args.scenario}-s{args.seed}"
    return McpBackend(
        mock_for=mock_for,
        desc_mode=args.desc_mode,
        memory_mode=args.memory_mode,
        run_id=run_id,
        log_dir=server_log_dir(run_id, ROOT),
    )


def _ensure_vendors() -> None:
    """③의 data/vendors.json 이 없으면 원본에서 만든다 (평판은 건드리지 않는다).

    vendors.json 은 .gitignore 대상이고 git 에서 추적하지 않는다. 새로 받은 저장소나
    추적 해제 커밋을 pull 한 작업 트리에는 이 파일이 없어, 그대로 두면 ③이
    "vendors.json 이 없다" 로 멈춘다. --force 없이 부르면 있을 때는 덮어쓰지 않는다
    (tools/bootstrap_vendors.py) — warm 누적 평판을 지키면서 빈자리만 채운다.
    """
    if (ROOT / "data" / "vendors.json").is_file():
        return
    script = ROOT / "tools" / "bootstrap_vendors.py"
    r = subprocess.run([sys.executable, str(script)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", cwd=str(ROOT))
    if r.returncode != 0:
        raise SystemExit(f"벤더 부트스트랩 실패:\n{r.stdout}\n{r.stderr}")
    print("[init] ③ data/vendors.json 생성 (원본에서)")


def _reset_vendors() -> None:
    """③의 평판을 초기 상태로 되돌린다.

    SLICE_MEMORY_MODE=cold 는 ⑤의 reliability.json 만 runs/ 로 격리한다. ③의
    data/vendors.json 은 그 변수를 보지 않고, 부트스트랩이 정한다
    (market/server.py:9~10 — "cold 는 시나리오마다 bootstrap_vendors.py --force").

    안 하면 앞선 실행이 남긴 평판이 다음 실행의 벤더 순위를 바꿔, 같은 시드로
    돌려도 결과가 갈린다 (2026-09-22 측정: 15스텝 2회에 조달 벤더가
    vendor-5 ↔ vendor-3 로 갈리며 개입 1회 ↔ 4회).
    """
    script = ROOT / "tools" / "bootstrap_vendors.py"
    if not script.exists():
        print(f"[주의] {script} 가 없다. ③ 평판이 초기화되지 않는다.")
        return

    r = subprocess.run([sys.executable, str(script), "--force"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=str(ROOT))
    if r.returncode != 0:
        raise SystemExit(f"벤더 부트스트랩 실패:\n{r.stdout}\n{r.stderr}")
    print("[fresh] ③ 벤더 평판 초기화")


def build_decider(args):
    """판단자를 고른다. loop.py 는 어느 쪽인지 모른다 — 같은 Decider 다."""
    if args.decider == "rule":
        return rule_decider

    from agent.deciders.llm import LlmDecider
    from agent.llm.claude_cli import ClaudeCLI

    llm = ClaudeCLI(exe=args.llm_exe, model=args.llm_model,
                    timeout=args.llm_timeout or 120.0)
    llm.require_login()   # 60스텝 돌다 인증으로 죽는 일이 없게, 시작 전에 확인한다
    print(f"LLM: {llm.exe} · 모델 {llm.model}")
    return LlmDecider(llm)


def main() -> int:
    p = argparse.ArgumentParser(description="MCP 에이전트 실행")
    p.add_argument("--scenario", choices=SCENARIOS, default="normal")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--steps", type=int, default=None, help="스텝 제한 (기본: 시나리오 전체)")
    p.add_argument("--arm", default="proposed", help="비교군 이름. run_id 에 박힌다")
    p.add_argument("--driver", choices=("fixed", "orchestrator"), default="fixed",
                   help="fixed: 파이썬이 순서를 정하고 LLM 은 판단만 (agent/loop.py). "
                        "orchestrator: LLM 이 도구를 직접 들고 스텝의 흐름을 잡는다 "
                        "(agent/orchestrator/). 실서버 + Claude CLI 를 쓴다")
    p.add_argument("--backend", choices=("mock", "mcp"), default="mock")
    p.add_argument("--decider", choices=("rule", "llm"), default="rule")
    p.add_argument("--max-calls", type=int, default=20,
                   help="orchestrator: 스텝당 도구 호출 상한. 넘으면 게이트웨이가 값으로 거부")
    p.add_argument("--step-budget-usd", type=float, default=0.50,
                   help="orchestrator: 스텝 1회의 LLM 비용 상한 (CLI --max-budget-usd)")
    p.add_argument("--intent", default=None,
                   help="사람이 처음 한 번 주는 자연어 상황. llm 판단자만 읽는다")
    p.add_argument("--llm-model", default="sonnet", help="claude CLI 의 --model")
    p.add_argument("--llm-timeout", type=float, default=None,
                   help="LLM 1회 제한(초). 기본: fixed 120 · orchestrator 300 "
                        "(한 스텝에 도구 호출 10회 이상이 오간다)")
    p.add_argument("--llm-exe", default=None, help="claude 실행 파일 경로 (기본: 자동 탐색)")
    p.add_argument("--mock-for", default="",
                   help="mcp 백엔드에서 목으로 대신할 서버. 쉼표 구분 (예: observe,audit)")
    p.add_argument("--desc-mode", choices=("minimal", "advisory"), default="minimal",
                   help="②의 도구 설명 수위")
    p.add_argument("--memory-mode", choices=("warm", "cold"), default="warm",
                   help="③⑤의 상태 유지 위치")
    p.add_argument("--trace", action="store_true",
                   help="도구 호출·LLM 문답을 콘솔에도 쏟는다 "
                        "(파일 runs/<run_id>/trace.log 는 항상 남는다)")
    p.add_argument("--quiet", action="store_true",
                   help="orchestrator: 도구 호출 추적을 콘솔에 쏟지 않는다 (파일에는 남는다)")
    p.add_argument("--fresh", action="store_true",
                   help="같은 run_id 의 이전 기록을 지우고 시작한다 (duplicate_decision 방지)")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    # 레벨은 setup_trace 가 정한다 — agent 로거는 DEBUG, 콘솔 핸들러만 걸러낸다.
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.intent and args.decider != "llm":
        print("[주의] --intent 는 llm 판단자만 읽는다. 규칙 판단자는 무시한다.")

    run_id = f"{args.arm}-{args.scenario}-s{args.seed}"

    # ④의 장부는 runs/<run_id>/ 에 누적된다. 같은 run_id 로 다시 돌리면 그 스텝이
    # 이미 있어 duplicate_decision 으로 거부당한다.
    book = ROOT / "runs" / run_id
    if args.fresh and book.exists():
        shutil.rmtree(book)
        print(f"[fresh] 이전 기록 삭제: {book}")
    elif book.exists():
        print(f"[주의] {book} 에 이전 기록이 있다. 충돌하면 --fresh 를 준다.")

    if args.fresh or args.memory_mode == "cold":
        _reset_vendors()
    else:
        _ensure_vendors()

    # 추적은 항상 파일에 남는다. --trace 는 콘솔에도 쏟을지만 정한다.
    # orchestrator 는 기본으로 콘솔에 쏟는다 — LLM 이 어느 도구를 어떤 값으로 부르고
    # MCP 를 탔는지가 곧 이 드라이버의 관찰 대상이다. 끄려면 --quiet.
    console = args.trace or args.verbose or (args.driver == "orchestrator" and not args.quiet)
    trace_path = setup_trace(run_id, console=console, root=ROOT)
    print(f"기록: {trace_path.parent}")

    if args.driver == "orchestrator":
        return _run_orchestrator(args, run_id)
    # baseline 만 정답 접근이 허용된다 (flow/forbidden.md:15). 그 arm 은
    # arms/baseline.py 가 별도 경로로 실행하므로 여기서는 항상 검사한다.
    # 판단자를 먼저 만든다. 실행파일·인증 문제로 죽을 거면 서버 5개를 띄우기
    # 전에 죽어야 한다 — 뒤에 두면 stdio 프로세스가 고아로 남는다.
    decide = build_decider(args)
    backend = build_backend(args)
    tools = Tools(backend, Guard(enabled=True))

    if args.backend == "mcp":
        print(f"실제 서버: {backend.live}"
              + (f" · 목: {sorted(backend._mock_for)}" if backend._mock_for else ""))

    try:
        results = run_episode(
            tools, decide, run_id,
            scenario=args.scenario, seed=args.seed, max_steps=args.steps,
            intent=args.intent, config=run_config(args),
        )
        _summarize(tools, results, run_id, decide)  # get_metrics 가 서버를 쓴다. 닫기 전에
    except ForbiddenLeak as e:
        print(f"\n[폐기] {e}", file=sys.stderr)
        return 2
    except LLMError as e:
        print(f"\n[LLM 실패] {e}", file=sys.stderr)
        return 3
    except ToolRefused as e:
        print(f"\n[도구 거부] {e}", file=sys.stderr)
        return 4
    finally:
        if hasattr(backend, "close"):
            backend.close()
    return 0


def run_config(args) -> dict:
    """④ 장부의 config 에 남길 실행 조건.

    ④는 scenario · seed · arm 을 환경변수(SLICE_SCENARIO …)에서만 읽는데 아무도 그걸
    넣지 않아 모든 장부에서 None 이었다 (audit/book.py:43 default_config). 에이전트가
    직접 넘긴다 — book.py 주석도 "나머지는 C가 config 인자로 넘긴다" 이다.

    intent 는 주 실험·오라클·블라인드 비교군을 가르는 조건이라 반드시 남긴다.
    """
    cfg = {
        "scenario": args.scenario,
        "seed": args.seed,
        "arm": args.arm,
        "driver": args.driver,
        "intent": args.intent,
        "steps_limit": args.steps,
        "desc_mode": args.desc_mode,
        "memory_mode": args.memory_mode,
    }
    if args.driver == "orchestrator":
        cfg.update(llm_model=args.llm_model, max_calls=args.max_calls,
                   step_budget_usd=args.step_budget_usd)
    else:
        cfg.update(backend=args.backend, decider=args.decider)
        if args.decider == "llm":
            cfg["llm_model"] = args.llm_model
    return cfg


def _run_orchestrator(args, run_id: str) -> int:
    """LLM 오케스트레이터. 서버 5개는 항상 실서버, 판단자는 항상 Claude CLI 다.

    --backend · --decider 는 고정 루프의 주입점이라 여기서는 뜻이 없다.
    """
    from agent.orchestrator.host import OrchestratorHost, print_summary

    if args.backend != "mock" or args.decider != "rule":
        print("[주의] --backend · --decider 는 fixed 드라이버의 옵션이다. orchestrator 는 무시한다.")

    try:
        host = OrchestratorHost(
            run_id, ROOT,
            model=args.llm_model, exe=args.llm_exe,
            step_timeout=args.llm_timeout or 300.0,
            step_budget_usd=args.step_budget_usd,
            desc_mode=args.desc_mode, memory_mode=args.memory_mode,
            max_calls=args.max_calls,
        )
    except LLMError as e:
        print(f"\n[LLM 실패] {e}", file=sys.stderr)
        return 3

    print(f"LLM: {host.cli.exe} · 모델 {host.cli.model} · 드라이버 orchestrator")
    try:
        result = host.run_episode(
            scenario=args.scenario, seed=args.seed,
            max_steps=args.steps, intent=args.intent, config=run_config(args),
        )
        print_summary(result, host)
    except ForbiddenLeak as e:
        print(f"\n[폐기] {e}", file=sys.stderr)
        return 2
    except LLMError as e:
        print(f"\n[LLM 실패] {e}", file=sys.stderr)
        return 3
    finally:
        host.close()
    return 0


def _summarize(tools: Tools, results: list, run_id: str, decide=None) -> None:
    if not results:
        print("스텝이 실행되지 않았다.")
        return

    esc = sum(1 for r in results if r.escalated)
    viol = sum(1 for r in results if r.sla_met is False)
    proc = sum(1 for r in results if r.procurement)
    situations: dict = {}
    policies: dict = {}
    for r in results:
        situations[r.decision.situation] = situations.get(r.decision.situation, 0) + 1
        policies[r.decision.policy] = policies.get(r.decision.policy, 0) + 1

    print(f"\n── {run_id} ──")
    print(f"  스텝        {len(results)}")
    print(f"  개입        {esc}   (자율 처리율 {1 - esc / len(results):.3f})")
    print(f"  SLA 위반    {viol}")
    print(f"  조달        {proc}")
    print(f"  상황 판단   {situations}")
    print(f"  정책 사용   {policies}")

    m = tools.get_metrics()
    print(f"  ④ 지표      steps={m['steps']} interventions={m['interventions']} "
          f"sla_violations={m['sla_violations']} cost={m['procurement_cost_total']}")

    llm = getattr(decide, "_llm", None)
    if llm is not None:
        print(f"  LLM         호출 {llm.calls}회 · {llm.elapsed:.1f}초 "
              f"(스텝당 {llm.elapsed / len(results):.1f}초) · "
              f"형식위반 {decide.malformed} · 정책전환 {decide.policy_switches}")
        print(f"  토큰        입력 {llm.tokens_in:,} · 출력 {llm.tokens_out:,} "
              f"· 비용 ${llm.cost_usd:.4f} "
              f"(스텝당 {(llm.tokens_in + llm.tokens_out) / len(results):,.0f})")

    first = results[0]
    print(f"\n  첫 스텝 도구 호출 {first.tool_calls}회 · "
          f"판단 {first.decision.situation}/{first.decision.policy} · "
          f"combined {first.decision.combined:.3f}")

    # 실서버로 돌린 실행은 장부가 있으니 리포트를 만든다. 목 백엔드는 파일을 남기지 않는다.
    if (ROOT / "runs" / run_id / "decisions.json").exists():
        try:
            from eval.report import build_report
            print(f"  리포트      {build_report(run_id)}   ← 브라우저로 열어 본다")
        except Exception as e:
            print(f"  [주의] 리포트 생성 실패: {e}")


if __name__ == "__main__":
    sys.exit(main())
