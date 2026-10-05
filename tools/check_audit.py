"""④ slice-audit 자체 검사 — 계약과 집계 불변식을 대조한다. (A 소유)

    python tools/check_audit.py

`build/order.md` 3단계 완료 판정이 여기 §2 다 — **`get_metrics()` 반환 필드에 정답 의존
지표가 부재**할 것.

①을 실제로 돌려 60스텝 에피소드 하나를 기록하고, ⑤의 채점을 `feedback.scoring` 으로
흉내 내어 `decisions.json` 공유 계약(§5)까지 확인한다. `fastmcp` 없이 돈다.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# Windows 기본 콘솔은 cp949 라 '—' 한 글자에 UnicodeEncodeError 로 죽는다.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

RUN = "_check-audit"
os.environ["SLICE_RUN_ID"] = RUN

from srm_mcp.audit import book, metrics  # noqa: E402
from srm_mcp.common import paths  # noqa: E402
from srm_mcp.common.const import FORBIDDEN, INIT_ALLOCATION  # noqa: E402
from srm_mcp.common.store import read_json, write_json  # noqa: E402
from srm_mcp.observe.env import SliceEnv  # noqa: E402

# ⑤가 decision_id 에서 run_id 를 되파는 정규식 (feedback/server.py:44).
DECISION_ID_RE = re.compile(r"^(?P<run_id>.+)-(?P<step>\d{4})$")

# spec/audit.md 의 Metrics 필드. 이 목록이 곧 3단계 완료 판정이다.
EXPECTED_METRIC_KEYS = {
    "steps", "interventions", "autonomous_rate", "sla_violations", "mean_utilization",
    "policy_usage", "mttr", "unresolved", "procurements", "procurement_cost_total",
    "mean_capacity", "pressure_exceeded",
}

CONF = {"situation": 0.70, "intrinsic": 0.521, "empirical": 0.880, "combined": 0.685}

failures: list[str] = []


def check(label: str, got, want, tol: float = 0.005) -> None:
    if isinstance(want, float) and isinstance(got, (int, float)):
        ok = abs(got - want) <= tol
    else:
        ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {label}: {got!r}" + ("" if ok else f"  (기대 {want!r})"))
    if not ok:
        failures.append(label)


def check_true(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f": {detail}" if detail else ""))
    if not ok:
        failures.append(label)


def fresh() -> None:
    """이전 실행의 책을 지운다. 남아 있으면 duplicate_decision 으로 전부 막힌다."""
    path = paths.decisions_json(RUN)
    if path.exists():
        path.unlink()


def score_like_feedback(decision_id: str, observed: dict) -> None:
    """⑤ `report_outcome` 이 같은 파일에 덧쓰는 부분만 흉내 낸다.

    ⑤ 본체는 `fastmcp` 를 import 하므로 여기서는 `feedback.scoring` 만 쓴다.
    키 이름이 어긋나면 ④의 집계가 조용히 0이 된다 — 그걸 잡는 것이 목적이다.
    """
    from srm_mcp.feedback import scoring

    run_id = DECISION_ID_RE.match(decision_id).group("run_id")
    page = read_json(paths.decisions_json(run_id))
    record = next(r for r in page["decisions"] if r["decision_id"] == decision_id)
    applied = {k: float(v) for k, v in observed["allocation"].items()}
    ideal = scoring.ideal_allocation(observed)
    record["outcome"] = {
        "sla_met": scoring.sla_met(observed["violations"]),
        "error": round(scoring.distance(applied, ideal), 4),
        "scored_at_step": int(observed["step"]),
        "applied_allocation": applied,
        "requested_allocation": record.get("allocation"),
        "actuator_delta": 0.0,
        "observed_violations": scoring.violations_view(observed["violations"]),
    }
    write_json(paths.decisions_json(run_id), page)


def main() -> int:
    print("④ slice-audit 검사\n")

    # ── 1. 기록 계약 ───────────────────────────────────────────
    print("1. record_decision")
    fresh()
    env = SliceEnv(RUN)
    env.reset(RUN, "emergency", 0)
    for _ in range(12):
        env.step(1)
    obs = env.get_observation()

    result = book.record_decision(
        step=12, observation=obs, situation="emergency", chosen_policy="rule_based",
        allocation={"embb": 0.20, "urllc": 0.70, "mmtc": 0.10}, confidence=CONF,
        rationale="URLLC 구성비가 평시보다 높다")
    check("decision_id 형식", result["decision_id"], f"{RUN}-0012")
    check("recorded_at_step", result["recorded_at_step"], 12)
    check_true("⑤의 정규식이 run_id 를 되판다",
               DECISION_ID_RE.match(result["decision_id"]).group("run_id") == RUN)
    check_true("첫 호출이 파일을 만든다", paths.decisions_json(RUN).exists())

    page = read_json(paths.decisions_json(RUN))
    check("book.run_id", page["run_id"], RUN)
    check_true("config 가 파일에 박힌다", "tau" in page["config"], str(page["config"]))
    record = page["decisions"][0]
    for key in ("decision_id", "step", "kind", "chosen_policy", "allocation",
                "vendor_id", "observation", "outcome"):
        check_true(f"⑤가 읽는 키 존재: {key}", key in record)

    dup = book.record_decision(
        step=12, observation=obs, situation="normal", chosen_policy="rule_based",
        allocation=dict(INIT_ALLOCATION), confidence=CONF, rationale="중복")
    check("같은 스텝 두 번 → 거부", dup.get("error"), "duplicate_decision")

    bad = book.record_decision(
        step=13, observation=obs, situation="normal", chosen_policy="rule_based",
        allocation=dict(INIT_ALLOCATION),
        confidence={"intrinsic": 0.5, "empirical": 0.8, "combined": 0.63},
        rationale="situation 확신 누락")
    check("confidence.situation 누락 → 거부", bad.get("error"), "missing_confidence")
    check("무엇이 없는지 알려준다", bad.get("missing"), ["situation"])

    saved = os.environ.pop("SLICE_RUN_ID")
    check("run_id 없음 → 복구 가능한 오류",
          book.get_metrics().get("error"), "missing_run_id")
    os.environ["SLICE_RUN_ID"] = saved

    # ── 2. 정답 비노출 — build/order.md 3단계 완료 판정 ────────
    print("\n2. 정답 비노출 (3단계 완료 판정)")
    got_keys = set(book.get_metrics().keys())
    check("get_metrics 반환 필드", got_keys, EXPECTED_METRIC_KEYS)
    leaked = [word for word in FORBIDDEN if word in str(sorted(got_keys))]
    check_true("정답 의존 지표 부재", not leaked, str(leaked))

    for name in ("server.py", "book.py", "metrics.py"):
        src = (ROOT / "srm_mcp" / "audit" / name).read_text(encoding="utf-8")
        hits = [word for word in FORBIDDEN if word in src]
        check_true(f"{name} 에 FORBIDDEN 0건", not hits, str(hits))

    # ── 3. record_escalation ──────────────────────────────────
    print("\n3. record_escalation")
    escalated = book.record_escalation(
        step=13, observation=obs, situation="emergency",
        reason="combined 0.31 < tau 0.45",
        confidence={"situation": 0.4, "intrinsic": 0.5, "empirical": 0.48,
                    "combined": 0.31})
    check("escalation_id", escalated["escalation_id"], f"{RUN}-esc-0013")
    check("decision_id 도 함께 발급", escalated["decision_id"], f"{RUN}-0013")
    check("fallback_policy", escalated["fallback_policy"], "rule_based")
    check("fallback_situation", escalated["fallback_situation"], "normal")
    # D4 — 기본은 결정 시점 관측의 최적 배분(expert). ⑤ ideal_allocation 과 같은 식이다.
    from srm_mcp.feedback.scoring import ideal_allocation
    expert = {k: round(v, 6) for k, v in ideal_allocation(obs).items()}
    check("fallback_allocation = a*(obs_t) (D4 expert)", escalated["fallback_allocation"], expert)
    check("fallback_mode", escalated.get("fallback_mode"), "expert")
    check_true("instruction 이 다음 행동을 지정",
               "apply_allocation" in escalated["instruction"])

    page = read_json(paths.decisions_json(RUN))
    same_step = [r for r in page["decisions"] if r["step"] == 13]
    check("한 호출이 레코드 둘", len(same_step), 2)
    check("kind 구성", sorted(r["kind"] for r in same_step), ["decision", "escalation"])
    fallback_record = next(r for r in same_step if r["kind"] == "decision")
    check_true("폴백 결정에 에이전트의 상황 판단이 남는다",
               fallback_record["situation"] == "emergency",
               f"situation={fallback_record['situation']}, "
               f"fallback_situation={fallback_record['fallback_situation']}")
    check("⑤가 읽는 allocation = 폴백",
          fallback_record["allocation"], expert)


    after = book.record_decision(
        step=13, observation=obs, situation="emergency", chosen_policy="lstm_forecast",
        allocation=dict(INIT_ALLOCATION), confidence=CONF, rationale="또 기록")
    check("에스컬레이션 뒤 record_decision → 거부", after.get("error"), "duplicate_decision")

    # 조달 3필드 중계 — 에스컬레이션한 스텝에 조달했을 때. 이게 없으면 그 조달이
    # 아무 레코드에도 안 남고(위의 duplicate_decision 때문에 복구 경로도 없다)
    # get_metrics 가 적게 세며 ⑤→③ 레이팅 되먹임이 끊긴다.
    book.record_escalation(
        step=14, observation=obs, situation="emergency", reason="조달했는데 확신이 낮다",
        confidence=CONF, slice_id="slice-urllc-0014-v1", vendor_id="vendor-1",
        cost_total=625.0)
    page = read_json(paths.decisions_json(RUN))
    escalated_decision = next(r for r in page["decisions"]
                              if r["step"] == 14 and r["kind"] == "decision")
    check("에스컬레이션 스텝의 slice_id", escalated_decision["slice_id"],
          "slice-urllc-0014-v1")
    check("에스컬레이션 스텝의 vendor_id", escalated_decision["vendor_id"], "vendor-1")
    check("에스컬레이션 스텝의 cost_total", escalated_decision["cost_total"], 625.0)
    metrics_14 = book.get_metrics(window=1)
    check("조달이 집계에 잡힌다", metrics_14["procurements"], 1)
    check("비용이 집계에 잡힌다", metrics_14["procurement_cost_total"], 625.0)

    # ── 4. 에피소드 전체 — 집계 불변식 ────────────────────────
    print("\n4. 60스텝 에피소드 집계 불변식")
    fresh()
    env = SliceEnv(RUN)
    env.reset(RUN, "emergency", 0)
    ids: list[str] = []
    for _ in range(60):
        obs = env.get_observation()
        step = obs["step"]
        if step % 15 == 7:                       # 4회 에스컬레이션
            out = book.record_escalation(step, obs, "emergency", "낮은 확신", CONF)
            allocation = out["fallback_allocation"]
        else:
            allocation = {"embb": 0.20, "urllc": 0.70, "mmtc": 0.10}
            out = book.record_decision(step, obs, "emergency", "rule_based", allocation,
                                       CONF, "임계 초과",
                                       slice_id=("s-1" if step == 20 else None),
                                       vendor_id=("vendor-1" if step == 20 else None),
                                       cost_total=(625.0 if step == 20 else None))
        ids.append(out["decision_id"])
        env.apply_allocation(**allocation)
        env.step(1)
        score_like_feedback(out["decision_id"], env.get_observation())

    # 마지막 결정은 채점될 다음 스텝이 없다 — 그 한 건을 되돌린다.
    page = read_json(paths.decisions_json(RUN))
    next(r for r in page["decisions"] if r["decision_id"] == ids[-1])["outcome"] = None
    write_json(paths.decisions_json(RUN), page)

    result = book.get_metrics()
    records = read_json(paths.decisions_json(RUN))["decisions"]
    decisions = [r for r in records if r["kind"] == "decision"]

    check("기록된 결정 수", len(decisions), 60)
    check("steps = 채점된 결정 수", result["steps"], 59)
    check("sum(policy_usage) = 기록된 결정 수", sum(result["policy_usage"].values()), 60)
    check_true("둘의 차이가 1 (정상)",
               sum(result["policy_usage"].values()) - result["steps"] == 1)
    check("interventions", result["interventions"], 4)
    check("autonomous_rate", result["autonomous_rate"], round(1 - 4 / 59, 6), tol=1e-6)
    check("procurements", result["procurements"], 1)
    check("procurement_cost_total", result["procurement_cost_total"], 625.0)
    check_true("sla_violations 는 outcome 에서 온다",
               result["sla_violations"] == sum(
                   1 for r in decisions
                   if isinstance(r.get("outcome"), dict)
                   and r["outcome"]["sla_met"] is False),
               str(result["sla_violations"]))
    check_true("mean_capacity 는 기본 용량 이상",
               result["mean_capacity"]["urllc"] >= 1.6, str(result["mean_capacity"]))
    check_true("mttr · unresolved 가 계산된다",
               result["mttr"] is not None or result["unresolved"] > 0,
               f"mttr={result['mttr']} unresolved={result['unresolved']}")

    windowed = book.get_metrics(window=10)
    check_true("window 가 최근 스텝만 본다",
               sum(windowed["policy_usage"].values()) == 10,
               str(windowed["policy_usage"]))

    # ── 5. mttr · unresolved 산출 ─────────────────────────────
    print("\n5. mttr · unresolved")
    def make(step: int, violated: bool) -> dict:
        return {"step": step, "kind": "decision",
                "observation": {"violations": {"embb": violated, "urllc": False,
                                               "mmtc": False}},
                "outcome": None}

    # 2~4 위반(길이 3) · 7~8 위반(길이 2) → 평균 2.5
    timeline = [make(s, s in (2, 3, 4, 7, 8)) for s in range(12)]
    mean, unresolved = metrics.mttr(timeline)
    check("mttr", mean, 2.5)
    check("unresolved (전부 복구)", unresolved, 0)

    never = [make(s, s >= 5) for s in range(10)]
    mean, unresolved = metrics.mttr(never)
    check("복구 못 한 구간은 평균에서 뺀다", mean, None)
    check("unresolved", unresolved, 1)

    # ── 6. get_decisions 컨텍스트 ─────────────────────────────
    print("\n6. get_decisions")
    brief = book.get_decisions(n=5)
    check("기본 n=5 요약 5건", len(brief), 5)
    check_true("요약에는 observation 이 없다", "observation" not in brief[0],
               str(sorted(brief[0])))
    full = book.get_decisions(n=2, full=True)
    check_true("full=True 면 observation 이 딸려온다", "observation" in full[0])
    only = book.get_decisions(n=10, kind="escalation")
    check_true("kind 필터", all(r["kind"] == "escalation" for r in only), str(len(only)))

    # ── 7. confidence 값 정리 (workplan-2 A-2b) ────────────────
    # 맨 끝에 둔다 — 앞 검사의 get_metrics(window=…) · get_decisions(n=…) 를 가로채지 않게.
    print("\n7. confidence 값 정리 (A-2b)")
    s900 = book.record_decision(
        step=900, observation=obs, situation="normal", chosen_policy="rule_based",
        allocation=dict(INIT_ALLOCATION),
        confidence={"situation": "0.9", "intrinsic": 0.5, "empirical": 0.8, "combined": 0.63},
        rationale="문자열 확신")
    stored = next(r for r in book.get_decisions(n=5, full=True)
                  if r.get("decision_id") == s900.get("decision_id"))
    check_true("숫자 문자열 confidence → float 로 저장",
               isinstance(stored["confidence"]["situation"], float),
               repr(stored["confidence"]["situation"]))
    nan = book.record_decision(
        step=901, observation=obs, situation="normal", chosen_policy="rule_based",
        allocation=dict(INIT_ALLOCATION),
        confidence={"situation": float("nan"), "intrinsic": 0.5, "empirical": 0.8, "combined": 0.63},
        rationale="NaN 확신")
    check("NaN confidence → 거부", nan.get("error"), "malformed_confidence")

    # 옛 동작 스위치 — SLICE_FALLBACK=init 이면 상수 (M-0 · after-B1 과 비교할 때)
    os.environ["SLICE_FALLBACK"] = "init"
    old_fb = book.record_escalation(
        step=902, observation=obs, situation="emergency", reason="init 모드",
        confidence=CONF, agent_allocation={"embb": 0.2, "urllc": 0.7, "mmtc": 0.1})
    os.environ.pop("SLICE_FALLBACK")
    check("SLICE_FALLBACK=init → INIT 상수", old_fb["fallback_allocation"], dict(INIT_ALLOCATION))
    rec902 = next(r for r in read_json(paths.decisions_json(RUN))["decisions"]
                 if r["step"] == 902 and r["kind"] == "decision")
    check("agent_allocation 저장 (D5)", rec902.get("agent_allocation"),
          {"embb": 0.2, "urllc": 0.7, "mmtc": 0.1})

    print("\n8. 개입 재설계 — 사람이 답한 상황 라벨의 배분 (2026-10-05)")
    # 2026-10-05 개입 재설계 — 사람이 답한 상황 라벨의 배분을 넘기면 폴백 대신 그것을 적용 · 기록한다
    human = book.record_escalation(
        step=950, observation=obs, situation="normal", reason="low_situation_confidence",
        confidence=CONF, human_situation="emergency",
        human_allocation={"embb": 0.3, "urllc": 0.5, "mmtc": 0.2})
    check("human_allocation → fallback_mode human_label", human.get("fallback_mode"), "human_label")
    check("human_allocation → 적용 배분 = 사람 라벨의 배분", human.get("fallback_allocation"),
          {"embb": 0.3, "urllc": 0.5, "mmtc": 0.2})
    check("human_situation → fallback_situation", human.get("fallback_situation"), "emergency")
    rec30 = next(r for r in read_json(paths.decisions_json(RUN))["decisions"]
                 if r["step"] == 950 and r["kind"] == "decision")
    check("장부의 에이전트 판단(situation)은 그대로", rec30["situation"], "normal")
    bad_h = book.record_escalation(
        step=951, observation=obs, situation="normal", reason="x", confidence=CONF,
        human_allocation={"embb": -1, "urllc": 0.5, "mmtc": 0.2})
    check("음수 human_allocation → 거부", bad_h.get("error"), "malformed_human_allocation")

    print(f"\n{'실패 ' + str(len(failures)) + '건: ' + ', '.join(failures) if failures else '전부 통과'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
