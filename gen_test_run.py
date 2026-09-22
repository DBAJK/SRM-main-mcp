"""`eval/score.py` 검증용 합성 실행 생성기. (A 소유 · 개발용 스크립트)

②③⑤ 없이 ①④만으로 가짜 에이전트를 돌려 진짜 `truth.jsonl` + `decisions.json` 쌍을 만든다.
- situation 판단은 `env._label()`(정답)에 15% 확률로 노이즈를 섞는다 — accuracy가 100%가
  아니어야 `eval/score.py`의 분모/분자 로직을 제대로 검증할 수 있다.
- confidence는 난수로 흔들어 TAU=0.45 아래로 종종 떨어지게 해서 에스컬레이션 경로도 태운다.

    python gen_test_run.py
    python -m eval.score test-mixed-s0
"""
import random
import shutil
import sys

sys.path.insert(0, ".")

from srm_mcp.audit import book
from srm_mcp.common import paths
from srm_mcp.common.const import TAU
from srm_mcp.observe.env import SliceEnv

RUN_ID = "test-mixed-s0"

# 실행마다 새로(설계서 §5.0) — 이전 실행이 남긴 decisions.json 이 있으면 모든 스텝이
# duplicate_decision 으로 막혀 esc["fallback_allocation"] 이 KeyError 난다.
shutil.rmtree(paths.run_dir(RUN_ID), ignore_errors=True)
SITUATIONS = ["normal", "emergency", "special_event", "iot_surge"]
ALLOC_PRESETS = {
    "normal": {"embb": 0.4, "urllc": 0.4, "mmtc": 0.2},
    "emergency": {"embb": 0.2, "urllc": 0.7, "mmtc": 0.1},
    "special_event": {"embb": 0.7, "urllc": 0.2, "mmtc": 0.1},
    "iot_surge": {"embb": 0.3, "urllc": 0.2, "mmtc": 0.5},
}

rng = random.Random(0)
env = SliceEnv(RUN_ID)
info = env.reset(RUN_ID, scenario="mixed", seed=0)
total_steps = info["total_steps"]
print(f"total_steps={total_steps}")

n_escalations = 0
for _ in range(total_steps):
    obs = env.get_observation()
    step = obs["step"]
    truth_label = env._label()  # 정답. 여기서만 접근 가능 — 가짜 에이전트를 만드는 스크립트라 예외적으로 씀.

    situation = truth_label if rng.random() < 0.85 else rng.choice(
        [s for s in SITUATIONS if s != truth_label])

    confidence = {
        "situation": rng.uniform(0.3, 0.9),
        "intrinsic": rng.uniform(0.4, 0.9),
        "empirical": rng.uniform(0.4, 0.9),
    }
    combined = (confidence["situation"] * confidence["intrinsic"]
                * confidence["empirical"]) ** (1 / 3)
    confidence["combined"] = round(combined, 6)

    alloc = ALLOC_PRESETS[situation]

    if combined < TAU:
        n_escalations += 1
        esc = book.record_escalation(
            step=step, observation=obs, situation=situation,
            reason=f"combined {combined:.3f} < tau {TAU}",
            confidence=confidence, run_id=RUN_ID)
        env.apply_allocation(**esc["fallback_allocation"])
    else:
        book.record_decision(
            step=step, observation=obs, situation=situation,
            chosen_policy="rule_based", allocation=alloc,
            confidence=confidence, rationale="synthetic test agent",
            run_id=RUN_ID)
        env.apply_allocation(**alloc)

    env.step(1)

print(f"escalations={n_escalations}")
print("done — 이제 `python -m eval.score test-mixed-s0` 를 실행하세요.")