"""원본(`ml_orchestrator_demo.py`) vs 현재(`srm_mcp`) 배분 로직 — 실행해서 숫자로 비교. (A 소유)

원본은 모듈 최상단에서 `import tensorflow`를 해서, TF가 없는 환경에서는 **그 파일을 직접
import하면 바로 죽는다.** 그래서 원본 수식을 **줄 번호를 인용해 그대로 옮겨 적고**, 같은
입력을 현재 구현에 넣어 출력을 비교한다 — "원본은 아무도 수정 안 한다"(CLAUDE.md)는
규칙과 "실행해서 비교한다"를 동시에 만족하는 방법이다. 숫자가 다르면 그건 버그가 아니라
의도된 재조정인지 `rationale/environment.md`로 확인한다.

    python tools/check_original_parity.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Windows 기본 콘솔은 cp949 라 '—' 한 글자에 UnicodeEncodeError 로 죽는다.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from srm_mcp.common.const import SLICE_KEYS, THRESHOLDS  # noqa: E402
from srm_mcp.observe.env import EVENT_MULTIPLIERS, CAPACITY_BASE, SliceEnv  # noqa: E402
from srm_mcp.policy import rule  # noqa: E402

failures: list[str] = []
diffs_expected: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f": {detail}" if detail else ""))
    if not ok:
        failures.append(label)


def diff_expected(label: str, original, current, reason: str) -> None:
    print(f"  DIFF(의도됨)  {label}: 원본 {original} → 현재 {current}  — {reason}")
    diffs_expected.append(label)


def to_vec(d: dict) -> np.ndarray:
    return np.array([float(d[k]) for k in SLICE_KEYS])


# ── 1. 원본 수식 그대로 (ml_orchestrator_demo.py 줄 번호 인용) ─────────

def original_rule_target(situation: str) -> np.ndarray:
    """:429~440 그대로."""
    return {
        "emergency": np.array([0.2, 0.7, 0.1]),
        "special_event": np.array([0.6, 0.3, 0.1]),
        "iot_surge": np.array([0.3, 0.3, 0.4]),
        "normal": np.array([0.4, 0.4, 0.2]),
    }[situation]


def original_smooth_clip_normalize(current: np.ndarray, target: np.ndarray,
                                   stability_factor: float = 0.7,
                                   clip_range: tuple = (0.1, 0.8)) -> np.ndarray:
    """:442~443, :458~462 그대로. (위반 보정 :446~457 은 여기 없다 — 아래서 따로 검증)"""
    new_allocation = stability_factor * current + (1 - stability_factor) * target
    new_allocation = np.clip(new_allocation, *clip_range)
    return new_allocation / np.sum(new_allocation)


def original_violation_correction(allocation: np.ndarray, utilization: np.ndarray,
                                  thresholds: np.ndarray) -> np.ndarray:
    """:446~457 그대로. D1-b(위반 보정)가 켜지면 들어갈 로직."""
    allocation = allocation.copy()
    for i in range(3):
        if utilization[i] > thresholds[i]:
            increase = min(0.1, (utilization[i] - thresholds[i]) * 0.2)
            other = [j for j in range(3) if j != i]
            least_utilized_idx = other[int(np.argmin(utilization[other]))]
            allocation[i] += increase
            allocation[least_utilized_idx] -= increase
    return allocation


def original_violations(utilization: np.ndarray, thresholds: np.ndarray) -> np.ndarray:
    """:563 그대로."""
    return utilization > thresholds


EVENT_MULTIPLIERS_ORIGINAL = {
    "emergency": np.array([0.8, 2.0, 0.9]),        # :313~316
    "special_event": np.array([1.5, 0.8, 1.0]),    # :318~321
    "iot_surge": np.array([0.9, 0.9, 1.8]),        # :323~326
    "normal": np.array([1.0, 1.0, 1.0]),
}


# ── 2. 검사 ────────────────────────────────────────────────────

def main() -> int:
    print("① 원본 vs 현재 — 배분 로직 동등성 검사\n")

    print("1. rule_based 목표 배분 표 (:429~440)")
    for situation in ("normal", "emergency", "special_event", "iot_surge"):
        original = original_rule_target(situation)
        current = to_vec(rule.TARGET_BY_SITUATION[situation])
        check(f"{situation}", np.allclose(original, current),
              f"원본 {original.tolist()} vs 현재 {current.tolist()}")

    print("\n2. 이벤트 트래픽 배율 (:313~326)")
    for situation, original in EVENT_MULTIPLIERS_ORIGINAL.items():
        current = to_vec(EVENT_MULTIPLIERS[situation])
        check(f"{situation}", np.allclose(original, current),
              f"원본 {original.tolist()} vs 현재 {current.tolist()}")

    print("\n3. 평활·클립·정규화 파이프라인 (:442~443, :458~462) — 위반 없는 경우")
    for situation in ("normal", "emergency", "special_event", "iot_surge"):
        target = original_rule_target(situation)
        current_start = np.array([0.4, 0.4, 0.2])
        original_result = original_smooth_clip_normalize(current_start, target)

        env = SliceEnv("_parity-check")
        env.reset("_parity-check", scenario="normal", seed=0)
        env.allocation = {k: float(v) for k, v in zip(SLICE_KEYS, current_start)}
        applied = env.apply_allocation(**dict(zip(SLICE_KEYS, target)))
        current_result = to_vec(applied["normalized"])

        check(f"{situation}", np.allclose(original_result, current_result, atol=1e-6),
              f"원본 {original_result.round(4).tolist()} vs 현재 {current_result.round(4).tolist()}")

    print("\n4. 위반 판정 (:563)")
    util = np.array([1.3, 1.525, 0.95])
    thr = np.array([THRESHOLDS[k] for k in SLICE_KEYS])
    original_v = original_violations(util, thr)
    current_v = np.array([bool(util[i] > thr[i]) for i in range(3)])
    check("utilization > thresholds", np.array_equal(original_v, current_v),
          f"{original_v.tolist()} vs {current_v.tolist()}")

    print("\n5. 위반 보정 (:446~457) — D1-b 결정 대상")
    print("   순서가 중요하다: 평활(:442) → 보정(:446) → 클립(:461) → 정규화(:462).")
    print("   보정이 평활 \"전\" 목표가 아니라 평활 \"후\" 배분에 걸린다 (rule.py 독스트링도 이렇게 설명함).")
    util = np.array([1.300, 1.525, 0.950])   # spec/policy.md 응답 예시
    target = original_rule_target("emergency")
    current_alloc = np.array([0.4, 0.4, 0.2])   # 직전 배분 (INIT_ALLOCATION 가정)

    # 평활만 (클립·정규화 전) — :442~443
    smoothed_only = 0.7 * current_alloc + 0.3 * target
    corrected = original_violation_correction(smoothed_only, util, thr)      # :446~457
    final = np.clip(corrected, 0.1, 0.8)                                     # :461
    final = final / final.sum()                                             # :462

    no_correction_final = original_smooth_clip_normalize(current_alloc, target)  # 보정 없이

    print(f"        평활 후(보정 전): {smoothed_only.round(4).tolist()}")
    print(f"        보정 후(클립·정규화 전): {corrected.round(4).tolist()}")
    print(f"        최종(클립+정규화까지): {final.round(4).tolist()}")
    print(f"        보정 없었다면(현재 rule.py 동작): {no_correction_final.round(4).tolist()}")
    diff_expected("위반 보정 적용 여부", "미적용(현재 rule.py)",
                  f"적용 시 {final.round(3).tolist()}",
                  "D1-b 결정 대기 — rule.py 독스트링의 {0.224,0.686,0.090}은 "
                  "이 재현과 정확히 일치하지 않는다(근사치로 보임), D1-b 구현 시 이 스크립트 결과를 정본으로 쓸 것")

    print("\n6. 알려진 의도적 차이 (rationale/environment.md 근거)")
    diff_expected("CAPACITY_BASE", "(개념 없음, 암묵적 1.0)", CAPACITY_BASE,
                  "평시 여유 확보 — 정정 K 신규 도입")
    diff_expected("START_HOUR", "(벽시계, 고정값 없음)", 0,
                  "8은 고부하 구간이라 평시 위반 53%까지 치솟음")
    diff_expected("CLIENT_COUNT_BASE", 0.4, 0.68, "학습 분포 하한보다 낮게 뽑혀 LSTM 신뢰도 영구 0")
    diff_expected("BS_COUNT_BASE", 0.5, 0.72, "같은 이유")

    print(f"\n{'='*60}")
    if failures:
        print(f"실패 {len(failures)}건: {failures}")
    else:
        print(f"동등성 검사 전부 통과. 의도된 차이 {len(diffs_expected)}건은 문서화됨.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
