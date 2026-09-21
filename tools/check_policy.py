"""② slice-policy 자체 검사 — 설계서의 완료 판정과 실측치를 대조한다. (B 소유)

    python tools/check_policy.py

`claude/spec/policy.md` 의 예시 응답과 ROLES.md §3.2 의 B-2 완료 판정 2개를 그대로 건다.

    · 같은 관측에 situation 만 바꾸면 배분이 달라진다
    · recent_error=null 과 =0.3 이 다른 confidence 를 낸다

TensorFlow 없이 돌아간다 — `lstm_forecast` 는 적재 실패 경로(status=error)까지 검증하고,
신뢰도 식은 순수 함수라 모델 없이도 확인된다. fastmcp 가 없으면 최소 스텁으로 대신한다
(도구 함수 자체를 부르기 위한 것이며, 실제 서버 기동과는 무관하다).
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:  # noqa: SIM105
    import fastmcp  # noqa: F401
except ImportError:
    stub = types.ModuleType("fastmcp")

    class _FastMCP:
        def __init__(self, name): self.name = name
        def tool(self, *_a, **_kw): return lambda fn: fn
        def run(self): raise RuntimeError("스텁이다 — 실제 기동에는 fastmcp 가 필요하다")

    stub.FastMCP = _FastMCP
    sys.modules["fastmcp"] = stub
    print("fastmcp 없음 — 스텁으로 도구 함수만 검사한다\n")

from srm_mcp.common.const import FORBIDDEN, SEQUENCE_LENGTH  # noqa: E402
from srm_mcp.policy import features, lstm, rule  # noqa: E402
from srm_mcp.policy import server as s  # noqa: E402

# spec/policy.md 예시 1 의 관측
OBS = {"step": 12,
       "utilization": {"embb": 1.300, "urllc": 1.525, "mmtc": 0.950},
       "traffic": {"embb": 0.55, "urllc": 0.72, "mmtc": 0.18},
       "allocation": {"embb": 0.4, "urllc": 0.4, "mmtc": 0.2}}

failures: list[str] = []


def check(label: str, got, want, tol: float = 0.0005) -> None:
    ok = abs(got - want) <= tol if isinstance(want, float) and isinstance(got, float) else got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {label}: {got!r}" + ("" if ok else f"  (기대 {want!r})"))
    if not ok:
        failures.append(label)


def main() -> int:
    print("1. rule_based — spec/policy.md 예시 1 (emergency)")
    p = s.propose_allocation("rule_based", OBS, "emergency")
    check("policy", p["policy"], "rule_based")
    check("allocation", p["allocation"], {"embb": 0.2, "urllc": 0.7, "mmtc": 0.1})
    check("confidence", round(p["confidence"], 3), 0.556)
    check("status", p["status"], "ok")
    check("in_distribution", p["in_distribution"], True)
    print(f"        rationale: {p['rationale']}")

    print("\n2. 완료 판정 — situation 만 바꾸면 배분이 달라진다")
    seen = {}
    for situation in ("normal", "emergency", "special_event", "iot_surge"):
        alloc = s.propose_allocation("rule_based", OBS, situation)["allocation"]
        seen[situation] = tuple(round(v, 3) for v in alloc.values())
        print(f"        {situation:14} → {seen[situation]}")
    check("4개 상황이 모두 다른 배분", len(set(seen.values())), 4)
    check("confidence 는 situation 과 무관",
          len({round(s.propose_allocation("rule_based", OBS, x)["confidence"], 6)
               for x in seen}), 1)

    print("\n3. situation 기본값 없음 (정정 E)")
    try:
        s.propose_allocation("rule_based", OBS)  # type: ignore[call-arg]
        check("situation 생략", "허용됨", "TypeError")
    except TypeError:
        print("  PASS  situation 생략 → TypeError (필수 인자)")
    try:
        s.propose_allocation("rule_based", OBS, "Emergency")
        check("잘못된 situation", "허용됨", "ValueError")
    except ValueError as exc:
        print(f"  PASS  잘못된 situation → ValueError: {str(exc)[:70]}")

    print("\n4. 조용한 폴백 금지 (정정 H)")
    short = {"n": 4, "columns": [], "features": []}
    q = s.propose_allocation("lstm_forecast", OBS, "emergency", history=short)
    check("policy 필드가 바뀌지 않는다", q["policy"], "lstm_forecast")
    check("allocation 은 null", q["allocation"], None)
    check("status != ok", q["status"] in ("unavailable", "error"), True)
    check("rule_based 결과가 새지 않는다", q["allocation"] is None, True)
    print(f"        reason: {q['reason']}")

    print("\n5. 완료 판정 — recent_error 가 confidence 를 바꾼다 (V4)")
    none_conf = lstm.confidence(None, True)
    conf_03 = lstm.confidence(0.3, True)
    check("recent_error=null → exp(−3×0.5)", round(none_conf, 4), 0.2231)
    check("recent_error=0.3 → exp(−0.9)", round(conf_03, 4), 0.4066)
    check("recent_error=0.1 → 0.74 (설계서 §6.1)", round(lstm.confidence(0.1, True), 2), 0.74)
    check("두 값이 다르다", none_conf != conf_03, True)
    check("분포 밖이면 0", lstm.confidence(0.1, False), 0.0)

    print("\n6. rule_based confidence 범위 [0.50, 0.80] — 하한이 τ(0.45) 위")
    tight = {"utilization": {"embb": 0.9, "urllc": 1.2, "mmtc": 0.8}}       # 여유 0
    loose = {"utilization": {"embb": 1.8, "urllc": 2.4, "mmtc": 1.6}}       # 여유 임계의 100%
    mid = {"utilization": {"embb": 0.1, "urllc": 0.1, "mmtc": 0.1}}         # 최소 여유 87.5%
    check("임계에 딱 붙으면 0.50", round(rule.confidence(tight), 4), 0.50)
    check("여유가 임계 이상이면 상한 0.80", round(rule.confidence(loose), 4), 0.80)
    check("여유 87.5% → 0.7625", round(rule.confidence(mid), 4), 0.7625)
    check("하한 > τ(0.45)", rule.confidence(tight) > 0.45, True)

    print("\n7. list_policies")
    for info in s.list_policies():
        print(f"        {info['name']:14} available={str(info['available']):5} "
              f"requires={info['requires']}  {info['description']}")
    names = [i["name"] for i in s.list_policies()]
    check("정책 3개", names, ["rule_based", "lstm_forecast", "dqn"])
    check("rule_based 는 항상 가용", s.list_policies()[0]["available"], True)
    check("dqn 은 1차 범위 제외", s.list_policies()[2]["available"], False)

    print("\n8. compare_policies — 가용 여부와 무관하게 전부 반환 (W6)")
    table = {"rule_based": {"recent_error": 0.094}, "lstm_forecast": {"recent_error": 0.112}}
    rows = s.compare_policies(OBS, "emergency", history=short, recent_errors=table)
    check("3개 전부", len(rows), 3)
    check("정책 이름 유지", [r["policy"] for r in rows], ["rule_based", "lstm_forecast", "dqn"])

    print("\n9. 금지 필드 — 도구 설명과 반환값 (flow/forbidden.md)")
    blob = repr(s.TOOL_DESC) + repr(s.list_policies()) + repr(rows) + repr(p)
    hits = [w for w in FORBIDDEN if w in blob]
    check("FORBIDDEN 0건", hits, [])

    print("\n10. in_distribution — ranges.json 경계")
    if features.ranges_available():
        ranges = features.load_ranges()
        inside = [[ranges[c]["min"] for c in ranges] for _ in range(SEQUENCE_LENGTH)]
        outside = [row[:] for row in inside]
        outside[0][0] = ranges["traffic_load"]["max"] + 1.0
        check("범위 안", features.out_of_range(inside), [])
        check("범위 밖 traffic_load 감지", features.out_of_range(outside), ["traffic_load"])
    else:
        print("  SKIP  ranges.json 없음 — tools/step0_verify_models.py 먼저")

    print(f"\n{'실패 ' + str(len(failures)) + '건: ' + ', '.join(failures) if failures else '전부 통과'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
