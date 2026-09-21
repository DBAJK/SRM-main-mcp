"""경로 상수 한 곳. (A 소유 · 임시 스텁)"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# 실행에 걸쳐 유지 (설계서 §5.0)
DATA_DIR = ROOT / "data"
VENDORS_JSON = DATA_DIR / "vendors.json"          # ③ 소유. 레이팅 누적
RELIABILITY_WARM = DATA_DIR / "reliability.json"  # ⑤ warm 모드

# 실행마다 새로
RUNS_DIR = ROOT / "runs"

# 원본 자산 (읽기 전용)
SRC_VENDORS_JSON = ROOT / "5G-Marketplace" / "data" / "vendors.json"   # 모델 A (정정 G)
LSTM_MODEL_DIR = ROOT / "5G-Network-Slicing" / "models" / "lstm_model_20250601_011235"
DQN_MODEL_DIR = ROOT / "5G-Network-Slicing" / "models" / "dqn_model_20250601_012010"
DQN_TRAINING_DATA = ROOT / "dqn_training_data"

# ②가 in_distribution 판정에 쓰는 컬럼별 min/max (0단계가 생성)
POLICY_RANGES_JSON = ROOT / "srm_mcp" / "policy" / "ranges.json"


def run_dir(run_id: str) -> Path:
    return RUNS_DIR / run_id


def decisions_json(run_id: str) -> Path:
    return run_dir(run_id) / "decisions.json"


def reliability_json(run_id: str) -> Path:
    """MEMORY_MODE 에 따라 cold = runs/{run_id}/, warm = data/ (설계서 §5.0)."""
    mode = os.environ.get("SLICE_MEMORY_MODE", "warm")
    return RELIABILITY_WARM if mode == "warm" else run_dir(run_id) / "reliability.json"
