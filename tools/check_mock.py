"""목 백엔드 계약 검사 — 목이 실서버 계약(B-1 · B-2 · B-3 · A-1 · A-2)대로 움직이는가.

    .venv310/Scripts/python tools/check_mock.py

서버를 띄우지 않는다. 목(`agent/backends/mock.py`)은 계약이 바뀌는 식을 서버 모듈에서
그대로 가져다 쓴다(workplan-2 C-14). 서버 쪽 계약이 또 바뀌었는데 목이 따라가지 못하면
여기서 걸린다. 수치(용량 · 트래픽)는 목이 가짜이므로 검사하지 않는다.
"""
import os
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
# 보정 기본은 2026-10-03 부터 off 다(rule.py CORRECTION_DEFAULT). 아래 B-1 판정은 보정 배선을 보는 것이라 켠다.
os.environ["SLICE_RULE_CORRECTION"] = "on"
# 개입 판정 기본은 2026-10-05 부터 상황 확신(situation)이다. 아래 B-2 · D5 · A-1 · D4 는 예전 신뢰도 판정의 개입 경로
# 계약을 보는 것이라 그 방식으로 돌린다. 새 경로(사람이 상황 라벨로 답한다)는 5절.
os.environ["AGENT_ESCALATION"] = "confidence"
mb = MockBackend(seed=0)
# ①에 실제로 넘어간 보정량을 엿본다 (B-1 판정용 — 아래)
_sent_corrections: list = []
_orig_apply = mb._apply_allocation
def _spy_apply(embb, urllc, mmtc, correction=None):
    _sent_corrections.append(correction)
    return _orig_apply(embb, urllc, mmtc, correction)
mb._apply_allocation = _spy_apply
tools = Tools(mb, Guard(enabled=True))
results = run_episode(tools, rule_decider, "mockc14-emergency-s0", scenario="emergency", seed=0, max_steps=30)
esc_recs = [d for d in mb.decisions.values() if d.get("escalated")]
auto_recs = [d for d in mb.decisions.values() if not d.get("escalated")]
scored_auto = [d for d in auto_recs if "outcome" in d]
scored_esc = [d for d in esc_recs if "outcome" in d]
rel = mb.reliability
print(f"  개입 {len(esc_recs)} · 자율 {len(auto_recs)} · rule_based n {rel['rule_based']['n']} · "
      f"fallback n {rel.get('fallback', {}).get('n')}")
# D5 가상 채점이 켜져 있으면(기본) 개입 스텝도 agent_policy 로 한 번씩 쌓인다 — 실제 성적은 여전히 폴백 칸.
shadowed = [d for d in scored_esc if (d["outcome"].get("shadow") or {}).get("policy") == "rule_based"]
check("B-2 · D5 — 정책 n = 채점된 자율 스텝 + 가상 채점된 개입 스텝",
      rel["rule_based"]["n"] == len(scored_auto) + len(shadowed),
      (rel["rule_based"]["n"], len(scored_auto), len(shadowed)))
check("D5 — 개입 레코드에 agent_allocation (고정 루프가 넘김) · 전부 가상 채점됨",
      bool(esc_recs) and all(d.get("agent_allocation") for d in esc_recs) and len(shadowed) == len(scored_esc),
      (len(esc_recs), len(shadowed)))
check("B-2 — fallback n = 채점된 개입 스텝 수",
      (rel.get("fallback", {}).get("n", 0)) == len(scored_esc), (rel.get("fallback", {}).get("n"), len(scored_esc)))
check("B-2 — counted_in_reliability 가 개입이면 False",
      all(d["outcome"]["counted_in_reliability"] is False for d in scored_esc)
      and all(d["outcome"]["counted_in_reliability"] is True for d in scored_auto))
check("A-1 — 개입 레코드에 agent_policy (고정 루프가 넘김)",
      bool(esc_recs) and all(d.get("agent_policy") == "rule_based" for d in esc_recs),
      sorted({d.get("agent_policy") for d in esc_recs}) if esc_recs else "개입 없음")
from srm_mcp.audit.book import fallback_allocation  # noqa: E402
check("D4 — 폴백 = ④ 와 같은 a*(obs_t) (expert)",
      bool(esc_recs) and all(d["allocation"] == fallback_allocation(d["observation"])[0]
                             and d.get("fallback_mode") == "expert" for d in esc_recs))

# 옛 동작 스위치 — 둘 다 끄면 B-2 까지의 동작(상수 폴백 · 개입 중 성적 멈춤)
os.environ["SLICE_FALLBACK"], os.environ["SLICE_SHADOW_SCORING"] = "init", "off"
mb0 = MockBackend(seed=0)
run_episode(Tools(mb0, Guard(enabled=True)), rule_decider, "mockold-emergency-s0",
            scenario="emergency", seed=0, max_steps=30)
del os.environ["SLICE_FALLBACK"], os.environ["SLICE_SHADOW_SCORING"]
esc0 = [d for d in mb0.decisions.values() if d.get("escalated")]
auto0 = [d for d in mb0.decisions.values() if not d.get("escalated") and "outcome" in d]
check("스위치 off — 폴백 = INIT 상수 · 정책 n = 자율 스텝만",
      all(d["allocation"] == {"embb": 0.4, "urllc": 0.4, "mmtc": 0.2} for d in esc0)
      and mb0.reliability["rule_based"]["n"] == len(auto0), (len(esc0), mb0.reliability["rule_based"]["n"], len(auto0)))
rats = [d.get("rationale", "") for d in auto_recs]
# 근거 끝은 ②가 정한다 — B-7 이후 "(보정 on · 목표표 original)". 목은 ② 를 그대로 부르므로 형식이
# 바뀌어도 따라가고, 여기서는 보정 설정이 남는지만 본다.
check("B-1 — rule_based 근거에 보정 설정(보정 on)", any("보정 on" in r for r in rats), rats[0][-50:] if rats else None)
# D1-b post 이후 요청 배분은 상황별 목표표 그대로다 — 상황 라벨이 안정되면(C-23) 한 가지로 고정되는 게
# 맞다. 보정은 correction 으로 ①에 따로 간다. 그래서 "보정이 실제로 ①에 넘어가는가"를 본다.
nonzero = [c for c in _sent_corrections if c and any(abs(v) > 1e-9 for v in c.values())]
check("B-1 · D1-b — 자율 스텝에서 0 아닌 보정량이 ①에 넘어간다", len(nonzero) > 0,
      (len(nonzero), len(_sent_corrections)))

os.environ.pop("AGENT_ESCALATION", None)

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
r = mb.call("audit", "record_decision",
            {**base, "step": 1, "confidence": {"situation": "0.9", "intrinsic": 0.5, "empirical": 0.5, "combined": 0.5}})
stored = mb.decisions.get(r.get("decision_id"), {}).get("confidence", {}).get("situation")
check("A-2b — 숫자 문자열은 float 로 저장", isinstance(stored, float) and stored == 0.9, repr(stored))
r = mb.call("audit", "record_decision",
            {**base, "step": 2, "confidence": {"situation": float("nan"), "intrinsic": 0.5, "empirical": 0.5, "combined": 0.5}})
check("A-2b — NaN → malformed_confidence", r.get("error") == "malformed_confidence", r.get("error"))

print("4. 규칙 판단자의 상황 추론 — 우도 HMM (반복 2) · 실제 ① 궤적")
# 목의 트래픽은 가짜라 여기서는 실제 ① 시뮬레이터(SliceEnv)로 궤적만 뽑는다. 트래픽은 배분과 무관하다.
import shutil                                         # noqa: E402
from agent.deciders import rule as rule_mod           # noqa: E402
from agent.schema import StepContext                  # noqa: E402
from srm_mcp.observe.env import SliceEnv              # noqa: E402


def _accuracy(signal: str) -> float:
    os.environ["AGENT_SITUATION_SIGNAL"] = signal
    ok = n = 0
    for scenario in ("normal", "emergency", "special_event", "iot_surge", "mixed"):
        rid = f"_check-mock-sit-{scenario}"
        env = SliceEnv(rid)
        env.reset(rid, scenario, 0)
        rule_mod.reset_run(rid)
        prev = None
        for _ in range(env.total_steps):
            obs = env.get_observation()
            label = env._label()
            ctx = StepContext(run_id=rid, step=obs["step"], observation=obs, history=None,
                              reliability={}, demand_class=None)
            guess, _conf = rule_mod.infer_situation(ctx)
            if prev is None or prev == label:          # 전환 스텝은 뺀다 (eval/score.py)
                n += 1
                ok += guess == label
            prev = label
            env.step()
        shutil.rmtree(ROOT / "runs" / rid, ignore_errors=True)
    os.environ.pop("AGENT_SITUATION_SIGNAL", None)
    return ok / n


acc_lik, acc_c23 = _accuracy("likelihood"), _accuracy("traffic")
check("기본 신호는 likelihood", rule_mod.situation_signal() == "likelihood", rule_mod.situation_signal())
check("시드 0 다섯 시나리오 정확도 ≥ 0.95 이고 C-23 보다 높다", acc_lik >= 0.95 and acc_lik > acc_c23,
      (round(acc_lik, 3), round(acc_c23, 3)))
env = SliceEnv("_check-mock-sit-x")
env.reset("_check-mock-sit-x", "emergency", 0)
ctx = StepContext(run_id="_check-mock-sit-x", step=0, observation=env.get_observation(), history=None,
                  reliability={}, demand_class=None)
rule_mod.reset_run("_check-mock-sit-x")
first = rule_mod.infer_situation(ctx)
check("같은 스텝을 다시 판단해도 같은 답 (재시도에 상태가 두 번 쌓이지 않는다)",
      rule_mod.infer_situation(ctx) == first, first)
check("확신은 사후확률 (0.25 ~ 1)", 0.25 <= first[1] <= 1.0, first[1])
shutil.rmtree(ROOT / "runs" / "_check-mock-sit-x", ignore_errors=True)

print("5. 개입 재설계 — 상황 확신 < 0.9 면 사람을 부르고, 사람은 상황 라벨로 답한다 (2026-10-05)")
from dataclasses import replace as _replace  # noqa: E402
from agent.schema import Decision, SITUATION_ESCALATION_THRESHOLD, escalation_mode  # noqa: E402
check("기본 판정은 situation", escalation_mode() == "situation", escalation_mode())
base_d = dict(situation="emergency", policy="rule_based", allocation={"embb": 0.3, "urllc": 0.5, "mmtc": 0.2},
              conf_intrinsic=0.9, conf_empirical=0.9, rationale="t")
check("확신 0.85 < 0.9 → 부른다 · 0.95 → 안 부른다",
      (Decision(conf_situation=0.85, **base_d).escalate, Decision(conf_situation=0.95, **base_d).escalate)
      == (True, False), SITUATION_ESCALATION_THRESHOLD)
os.environ["AGENT_ESCALATION"] = "confidence"
check("AGENT_ESCALATION=confidence 면 예전 공식 (combined 0.9 ≥ τ → 안 부른다)",
      Decision(conf_situation=0.1, **base_d).escalate is False)
os.environ.pop("AGENT_ESCALATION")
asked = []


def _human(run_id, step):
    asked.append(step)
    return "emergency"


def always_unsure(ctx, prop):
    return _replace(rule_decider(ctx, prop), conf_situation=0.5)


always_unsure.on_human_label = lambda run_id, step, label: asked.append(("absorb", step, label))
mbh = MockBackend(seed=0)
run_episode(Tools(mbh, Guard(enabled=True)), always_unsure, "mockhuman-emergency-s0",
            scenario="emergency", seed=0, max_steps=5, human=_human)
recs = [d for d in mbh.decisions.values() if d.get("escalated")]
check("확신이 낮은 스텝마다 사람을 불렀다",
      len(recs) == 5 and [a for a in asked if isinstance(a, int)] == [0, 1, 2, 3, 4], (len(recs), asked[:6]))
check("폴백 대신 사람 라벨의 배분이 기록된다 (human_label · emergency)",
      all(d.get("fallback_mode") == "human_label" and d.get("fallback_situation") == "emergency" for d in recs),
      sorted({(d.get("fallback_mode"), d.get("fallback_situation")) for d in recs}))
check("판단자에게 사람의 답이 전달된다 (on_human_label)", ("absorb", 0, "emergency") in asked, asked[:4])
import math as _m  # noqa: E402
from agent.deciders import rule as rule_mod2  # noqa: E402
rule_mod2.reset_run("_absorb")
rule_mod2.absorb_label("_absorb", 3, "iot_surge")
check("absorb_label — 그 스텝 믿음이 답한 라벨 0.99",
      round(_m.exp(rule_mod2._belief["_absorb"][3]["iot_surge"]), 2) == 0.99)
rule_mod2.reset_run("_absorb")

print("\n6. SLICE_POLICIES — 기본은 rule_based 고정 (2026-10-05 결정)")
import types as _types  # noqa: E402
from agent.deciders.rule import pick_policy  # noqa: E402
os.environ.pop("SLICE_POLICIES", None)
_mb = MockBackend(seed=0)
_mb._reset("mockpolicy-emergency-s0", "emergency", 0)
_obs = _mb._get_observation()
_hist10 = {"n_available": 10}
_q = _mb._propose_allocation("lstm_forecast", _obs, "emergency", history=_hist10)
check("기본: mock lstm 은 unavailable · disabled_by_config",
      _q["status"] == "unavailable" and str(_q["reason"]).startswith("disabled_by_config"), _q.get("reason"))
check("기본: mock list_policies 의 lstm available=false",
      [r["available"] for r in _mb._list_policies()] == [True, False, False])
# lstm 이 성적을 쌓아 rule 보다 높아도 기본에서는 고르지 않는다
_ctx = _types.SimpleNamespace(history=_hist10, samples=lambda p: 5,
                              effective=lambda p: {"rule_based": 0.4, "lstm_forecast": 0.9}[p])
check("기본: pick_policy 는 rule_based", pick_policy(_ctx) == "rule_based", pick_policy(_ctx))
os.environ["SLICE_POLICIES"] = "all"
check("all: pick_policy 는 성적 높은 lstm", pick_policy(_ctx) == "lstm_forecast", pick_policy(_ctx))
check("all: mock lstm 은 ok", _mb._propose_allocation("lstm_forecast", _obs, "emergency", history=_hist10)["status"] == "ok")
os.environ.pop("SLICE_POLICIES")

print("\n" + ("전부 통과" if FAILS == 0 else f"실패 {FAILS}건"))
sys.exit(1 if FAILS else 0)
