#!/usr/bin/env python
"""original 비교군 검사 — 원본 코드와 같은 입력에서 같은 배분이 나오는가. (C · 2026-10-05)

    .venv310\\Scripts\\python.exe tools\\check_original.py

원본 `ml_orchestrator_demo.py` 의 `MLOrchestrator.update_allocation_rule_based()` (:422~465)를 **원본 파일
그대로** 불러와, 우리 쪽 경로(② rule_based 를 원본 설정으로 · ① 액추에이터)와 같은 (직전 배분 · 이용률 · 상황)
에서 비교한다. 원본 파일은 읽기만 한다.

    원본  상황 플래그 → 고정표 → 평활 0.7 → 과부하 보정 → 클립 [0.1, 0.8] → 재정규화
    우리  ② propose(SLICE_TARGET_TABLE=original) + correction(SLICE_RULE_CORRECTION=on · post) → ① actuate

환경 차이(우리 이용률은 traffic/(배분×용량), 원본은 traffic/배분)는 비교군 공통의 환경 쪽 정정 K 라 여기서는
이용률을 같은 값으로 넣어 **배분 규칙만** 대조한다.
"""
from __future__ import annotations

import contextlib
import io
import os
import sys
from pathlib import Path

import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FAILS = 0


def check(label, ok, got=None):
    global FAILS
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + ("" if ok or got is None else f": {got}"))
    FAILS += 0 if ok else 1


def main() -> int:
    from agent import arms
    from srm_mcp.common.actuator import actuate
    from srm_mcp.common.const import SLICE_KEYS as K
    from srm_mcp.policy import rule

    # 원본은 그림용 matplotlib 를 맨 위에서 import 한다. .venv310 에는 없고 배분 규칙과 무관하니 빈 모듈로 대신한다.
    try:
        import matplotlib.pyplot  # noqa: F401
    except ImportError:
        import types
        mpl = types.ModuleType("matplotlib")
        mpl.pyplot = types.ModuleType("matplotlib.pyplot")
        mpl.use = lambda *a, **k: None
        sys.modules.update({"matplotlib": mpl, "matplotlib.pyplot": mpl.pyplot})
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        import ml_orchestrator_demo as orig        # 원본 파일 (읽기 전용)

    flags = {"normal": (False, False, False), "emergency": (True, False, False),
             "special_event": (False, True, False), "iot_surge": (False, False, True)}

    def original(prev, util, situation):
        o = orig.MLOrchestrator.__new__(orig.MLOrchestrator)   # __init__ 은 모델 적재 · 폴더 생성이라 건너뛴다
        o.allocation = np.array([prev[k] for k in K], dtype=float)
        o.utilization = np.array([util[k] for k in K], dtype=float)
        o.thresholds = np.array([0.9, 1.2, 0.8])              # 원본 __init__ :174
        o.is_emergency, o.is_special_event, o.is_iot_surge = flags[situation]
        out = o.update_allocation_rule_based()
        return {k: float(out[i]) for i, k in enumerate(K)}

    def ours(prev, util, situation, exact=False):
        """exact=False 는 실제 경로 — ② 가 보정량을 소수 6자리로 반올림해 낸다(JSON 경계 · rule.correction).
        exact=True 는 반올림 전 보정량(rule.correction_delta)으로, 규칙 자체가 같은지를 본다."""
        obs = {"utilization": util}
        target = rule.propose(obs, situation)
        corr = rule.correction_delta(target, obs) if exact else rule.correction(obs, situation)
        alloc, _, _ = actuate(prev, target, corr)
        return alloc

    saved = {k: os.environ.get(k) for k in arms.ENV_PRESET["original"]}
    os.environ.update(arms.ENV_PRESET["original"])
    try:
        print("1. 무작위 상태 5,000개 — 원본 update_allocation_rule_based 와 배분 일치")
        rng = np.random.default_rng(0)
        worst_exact = worst_wire = 0.0
        n = 0
        for situation in flags:
            for _ in range(1250):
                a = rng.dirichlet([2, 2, 2])
                a = np.clip(a, 0.1, 0.8); a = a / a.sum()
                prev = {k: float(a[i]) for i, k in enumerate(K)}
                util = {k: float(rng.uniform(0.0, 2.5)) for k in K}
                o = original(prev, util, situation)
                e, w = ours(prev, util, situation, exact=True), ours(prev, util, situation)
                worst_exact = max(worst_exact, max(abs(o[k] - e[k]) for k in K))
                worst_wire = max(worst_wire, max(abs(o[k] - w[k]) for k in K)); n += 1
        check(f"{n}개 · 규칙 자체(반올림 전 보정) 최대 차이 {worst_exact:.1e} < 1e-12", worst_exact < 1e-12, worst_exact)
        check(f"{n}개 · 실제 경로(보정 6자리 반올림) 최대 차이 {worst_wire:.1e} < 1e-6", worst_wire < 1e-6, worst_wire)

        print("\n2. 경계 — 보정이 여러 슬라이스에 걸림 · 이용률 동률 · 클립")
        cases = [
            ({"embb": 0.4, "urllc": 0.4, "mmtc": 0.2}, {"embb": 2.0, "urllc": 2.0, "mmtc": 2.0}, "emergency"),
            ({"embb": 0.1, "urllc": 0.8, "mmtc": 0.1}, {"embb": 0.5, "urllc": 0.5, "mmtc": 3.0}, "emergency"),
            ({"embb": 0.8, "urllc": 0.1, "mmtc": 0.1}, {"embb": 0.95, "urllc": 0.2, "mmtc": 0.2}, "special_event"),
            ({"embb": 0.3, "urllc": 0.3, "mmtc": 0.4}, {"embb": 0.0, "urllc": 0.0, "mmtc": 0.0}, "normal"),
        ]
        for prev, util, situation in cases:
            o, w = original(prev, util, situation), ours(prev, util, situation, exact=True)
            d = max(abs(o[k] - w[k]) for k in K)
            check(f"{situation:13} util {list(util.values())} → 차이 {d:.1e}", d < 1e-12, (o, w))

        print("\n3. ②의 근거 문장 — original 판단자가 확인하는 표지")
        r = rule.rationale({"utilization": cases[0][1]}, "emergency", rule.propose({"utilization": cases[0][1]}, "emergency"))
        check("목표표 original · 보정 on · 평활 뒤", "목표표 original" in r and "보정 on · 평활 뒤" in r, r)
    finally:
        for k, v in saved.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)

    print("\n4. 비교군 등록")
    check("kind_of('original') = original", arms.kind_of("original") == "original")
    check("정답 비교군 · 판단자 불필요", "original" in arms.TRUTH_KINDS and not arms.needs_base_decider("original"))

    print("\n5. 설정 없이 돌면 멈춘다 (원본 재현이 아닌데 결과가 나오면 안 된다)")
    from agent.arms.baseline import OriginalDecider
    from agent.schema import StepContext  # noqa: F401  (형만 맞추는 가짜 ctx)

    class FakeCtx:
        run_id, step, demand_class = "_x", 0, None
        def effective(self, p): return 0.5

    class FakeProposer:
        def __init__(self, rationale): self.r = rationale
        def propose(self, policy, situation):
            return {"policy": policy, "allocation": {"embb": 0.4, "urllc": 0.4, "mmtc": 0.2},
                    "correction": None, "confidence": 0.6, "rationale": self.r, "in_distribution": True}

    dec = OriginalDecider(ROOT)
    dec._truth_situation = lambda run_id, step: "emergency"
    try:
        dec(FakeCtx(), FakeProposer("situation=emergency → 목표 [..] (보정 off · 목표표 theta_z)."))
        check("theta_z 설정이면 RuntimeError", False, "통과됨")
    except RuntimeError:
        check("theta_z 설정이면 RuntimeError", True)
    d = dec(FakeCtx(), FakeProposer("situation=emergency → 목표 [..] (보정 on · 평활 뒤 · 목표표 original)."))
    check("원본 설정이면 통과 · 조달 안 함 · 개입 없음", d.procure is False and d.escalation is False
          and d.situation == "emergency", (d.procure, d.escalation, d.situation))

    print("\n" + ("전부 통과" if FAILS == 0 else f"실패 {FAILS}건"))
    return 0 if FAILS == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
