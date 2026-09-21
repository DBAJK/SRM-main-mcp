#!/usr/bin/env python3
"""에이전트 실행기.

목 백엔드 + 규칙 판단자로 한 바퀴 돌려 배선을 검증한다.
실제 서버와 LLM 은 각각 --backend mcp, --decider llm 으로 갈아끼운다.

사용 예
  python run.py --scenario emergency --steps 20
  python run.py --scenario mixed --seed 1
"""

import argparse
import logging
import sys

from agent.backends.mock import MockBackend
from agent.deciders.rule import rule_decider
from agent.guard import ForbiddenLeak, Guard
from agent.loop import run_episode
from agent.tools import Tools

SCENARIOS = ("normal", "emergency", "special_event", "iot_surge", "mixed")


def build_tools(backend_name: str, seed: int, guard_enabled: bool) -> Tools:
    if backend_name == "mock":
        backend = MockBackend(seed=seed)
    else:
        raise SystemExit(
            f"백엔드 '{backend_name}' 은 아직 없다. "
            "A·B의 서버가 나오면 agent/backends/mcp.py 를 추가한다."
        )
    return Tools(backend, Guard(enabled=guard_enabled))


def main() -> int:
    p = argparse.ArgumentParser(description="MCP 에이전트 실행")
    p.add_argument("--scenario", choices=SCENARIOS, default="normal")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--steps", type=int, default=None, help="스텝 제한 (기본: 시나리오 전체)")
    p.add_argument("--arm", default="proposed", help="비교군 이름. run_id 에 박힌다")
    p.add_argument("--backend", choices=("mock", "mcp"), default="mock")
    p.add_argument("--decider", choices=("rule", "llm"), default="rule")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(message)s",
    )

    if args.decider == "llm":
        raise SystemExit("llm 판단자는 아직 없다. agent/deciders/llm.py 를 추가한다.")

    run_id = f"{args.arm}-{args.scenario}-s{args.seed}"
    # baseline 만 정답 접근이 허용된다 (flow/forbidden.md:15). 그 arm 은
    # arms/baseline.py 가 별도 경로로 실행하므로 여기서는 항상 검사한다.
    tools = build_tools(args.backend, args.seed, guard_enabled=True)

    try:
        results = run_episode(
            tools, rule_decider, run_id,
            scenario=args.scenario, seed=args.seed, max_steps=args.steps,
        )
    except ForbiddenLeak as e:
        print(f"\n[폐기] {e}", file=sys.stderr)
        return 2

    _summarize(tools, results, run_id)
    return 0


def _summarize(tools: Tools, results: list, run_id: str) -> None:
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

    first = results[0]
    print(f"\n  첫 스텝 도구 호출 {first.tool_calls}회 · "
          f"판단 {first.decision.situation}/{first.decision.policy} · "
          f"combined {first.decision.combined:.3f}")


if __name__ == "__main__":
    sys.exit(main())
