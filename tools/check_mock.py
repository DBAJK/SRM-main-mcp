"""목 백엔드 계약 검사 — 목이 실서버 계약(B-1 · B-2 · B-3 · A-1 · A-2)대로 움직이는가.

    .venv310/Scripts/python tools/check_mock.py

서버를 띄우지 않는다. 목(`agent/backends/mock.py`)은 계약이 바뀌는 식을 서버 모듈에서
그대로 가져다 쓴다(workplan-2 C-14). 서버 쪽 계약이 또 바뀌었는데 목이 따라가지 못하면
여기서 걸린다. 수치(용량 · 트래픽)는 목이 가짜이므로 검사하지 않는다.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from agent.backends.mock import MockBackend          # noqa: E402
from agent.deciders.rule import rule_decider          # noqa: E402
from agent.guard import Guard                         # noqa: E402
from agent.loop import run_episode                    # noqa: E402
from agent.tools import Tools                         # noqa: E402

FAILS = 0


def check(label, ok, got=None):
    global FAILS
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f": {got}" if got is not None else ""))
    FAILS += 0 if ok else 1


print("1. n=0 사전값 (B-3)")
mb = MockBackend(seed=0)
t0 = mb.call("feedback", "get_reliability_table", {})
check("lstm recent_error 0.2 · dqn 0.6 · rule 0.1",
      (t0["lstm_forecast"]["recent_error"], t0["dqn"]["recent_error"], t0["rule_based"]["recent_error"])
      == (0.2, 0.6, 0.1), {k: v["recent_error"] for k, v in t0.items()})
check("effective 0.5 · fallback 은 표에 없음",
      all(v["effective"] == 0.5 for v in t0.values()) and "fallback" not in t0, sorted(t0))

print("2. 에피소드 — emergency 30스텝 · 규칙 판단자")
mb = MockBackend(seed=0)
tools = Tools(mb, Guard(enabled=True))
results = run_episode(tools, rule_decider, "mockc14-emergency-s0", scenario="emergency", seed=0, max_steps=30)
esc_recs = [d for d in mb.decisions.values() if d.get("escalated")]
auto_recs = [d for d in mb.decisions.values() if not d.get("escalated")]
scored_auto = [d for d in auto_recs if "outcome" in d]
scored_esc = [d for d in esc_recs if "outcome" in d]
rel = mb.reliability
print(f"  개입 {len(esc_recs)} · 자율 {len(auto_recs)} · rule_based n {rel['rule_based']['n']} · "
      f"fallback n {rel.get('fallback', {}).get('n')}")
check("B-2 — 정책 n = 채점된 자율 스텝 수", rel["rule_based"]["n"] == len(scored_auto),
      (rel["rule_based"]["n"], len(scored_auto)))
check("B-2 — fallback n = 채점된 개입 스텝 수",
      (rel.get("fallback", {}).get("n", 0)) == len(scored_esc), (rel.get("fallback", {}).get("n"), len(scored_esc)))
check("B-2 — counted_in_reliability 가 개입이면 False",
      all(d["outcome"]["counted_in_reliability"] is False for d in scored_esc)
      and all(d["outcome"]["counted_in_reliability"] is True for d in scored_auto))
check("A-1 — 개입 레코드에 agent_policy (고정 루프가 넘김)",
      bool(esc_recs) and all(d.get("agent_policy") == "rule_based" for d in esc_recs),
      sorted({d.get("agent_policy") for d in esc_recs}) if esc_recs else "개입 없음")
check("폴백 = INIT 상수 {0.4, 0.4, 0.2}",
      all(d["allocation"] == {"embb": 0.4, "urllc": 0.4, "mmtc": 0.2} for d in esc_recs))
rats = [d.get("rationale", "") for d in auto_recs]
check("B-1 — rule_based 근거에 (보정 on)", any("(보정 on)" in r for r in rats), rats[0][-40:] if rats else None)
allocs = {tuple(sorted(d["allocation"].items())) for d in auto_recs}
check("B-1 — 자율 스텝 요청 배분이 하나로 고정되지 않음", len(allocs) > 1, len(allocs))

print("3. A-2 — confidence 검사")
mb = MockBackend(seed=0)
obs = mb.call("observe", "reset", {"run_id": "x", "scenario": "normal", "seed": 0})["observation"]
base = dict(step=0, observation=obs, situation="normal", chosen_policy="rule_based",
            allocation={"embb": 0.4, "urllc": 0.4, "mmtc": 0.2}, rationale="t")
r = mb.call("audit", "record_decision",
            {**base, "confidence": {"situation": "iot_surge", "intrinsic": 0.5, "empirical": 0.5, "combined": 0.5}})
check("문자열 situation → malformed_confidence", r.get("error") == "malformed_confidence", r.get("error"))
r = mb.call("audit", "record_decision", {**base, "confidence": {"intrinsic": 0.5}})
check("키 누락 → missing_confidence", r.get("error") == "missing_confidence", r.get("error"))
r = mb.call("audit", "record_decision",
            {**base, "confidence": {"situation": 0.9, "intrinsic": 0.5, "empirical": 0.5, "combined": 0.5}})
check("정상 → decision_id", "decision_id" in r, r.get("decision_id"))

print("\n" + ("전부 통과" if FAILS == 0 else f"실패 {FAILS}건"))
sys.exit(1 if FAILS else 0)
