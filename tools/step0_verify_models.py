"""0단계 — 모델 적재 검증. 나머지 전부의 전제다. (B 소유, Day 1 오전)

    py -3.10 -m venv .venv310
    .venv310/Scripts/python -m pip install -r requirements-mcp.txt
    .venv310/Scripts/python tools/step0_verify_models.py

버전 고정이 핵심이다 (정정 I). TF 2.16+ 는 Keras 3 가 기본인데 Keras 3 의 `load_model()` 은
SavedModel 디렉터리를 읽지 못한다. 가중치가 `saved_model.pb` + `variables/` 형식이라
`pip install tensorflow` 만 하면 최신이 깔려 그대로 실패한다. TF 2.15.1 은 cp39~cp311
휠만 있으므로 **Python 3.10(또는 3.11)이 필요하다.**

**적재 성공만으로는 통과가 아니다.** 6개 항목 전부를 본다.

    #  확인                                          실패 시
    1  lstm_model_20250601_011235 적재               TF 버전 재확인 → TFSMLayer → 재학습
    2  입력이 (1, 10, 11) 을 받는가                   피처 차원 재확인
    3  출력 3차원, 합 ≈ 1, 각 항 ∈ [0,1]              스케일러 필요 → 재학습
    4  동일 입력 2회 → 동일 출력                      비결정 레이어 → 신뢰도 식 변경
    5  dqn_model_20250601_012010 적재 + softmax 합≈1  classify_demand 제외
    6  dqn_training_data/*.csv 컬럼별 min/max         in_distribution 판정 불가
       → srm_mcp/policy/ranges.json

정적 모드 — TensorFlow 가 없으면 2·3·5 를 `keras_metadata.pb` 의 모델 config 로 대신 본다.
저장된 구조(입력 shape · 마지막 층의 units 와 activation)는 적재 없이도 읽히므로, 3번 관문을
TF 설치 전에 미리 답할 수 있다. 1·4 는 실제 추론이 필요하므로 SKIP 으로 남는다.

종료 코드: 0 전부 통과 · 1 실패 있음 · 2 실패는 없으나 SKIP 이 남음(= 아직 미완).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Optional

# Windows 기본 콘솔은 cp949 라 '—' 한 글자에 UnicodeEncodeError 로 죽는다.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from srm_mcp.common import paths  # noqa: E402
from srm_mcp.common.const import FEATURE_COLUMNS, FORBIDDEN, SEQUENCE_LENGTH  # noqa: E402
from srm_mcp.common.store import write_json  # noqa: E402

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"

# dqn_training_data.csv 의 컬럼명은 시뮬레이터의 피처 이름과 다르다.
# 순서는 같으므로 이름만 맞춘다. ranges.json 의 키는 FEATURE_COLUMNS 로 통일한다.
CSV_ALIAS = {
    "embb_alloc": "embb_allocation", "urllc_alloc": "urllc_allocation",
    "mmtc_alloc": "mmtc_allocation", "embb_util": "embb_utilization",
    "urllc_util": "urllc_utilization", "mmtc_util": "mmtc_utilization",
}

TRAINING_CSV = paths.DQN_TRAINING_DATA / "dqn_training_data.csv"


# ── 환경 ───────────────────────────────────────────────────────
def load_tensorflow() -> tuple[Optional[Any], Optional[str]]:
    try:
        import tensorflow as tf  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"
    return tf, None


def keras_config(model_dir: Path) -> dict:
    """`keras_metadata.pb` 안에 박혀 있는 모델 config(JSON)를 꺼낸다.

    SavedModel 은 Keras 구조를 JSON 텍스트로 함께 저장한다. protobuf 를 제대로 파싱하지
    않고 중괄호 짝만 맞춰 잘라내도 되는 이유다 — TF 없이 구조를 볼 수 있다.
    """
    raw = (model_dir / "keras_metadata.pb").read_bytes().decode("utf-8", "replace")
    start = raw.index('{"class_name": "Sequential"')
    depth = 0
    for i in range(start, len(raw)):
        if raw[i] == "{":
            depth += 1
        elif raw[i] == "}":
            depth -= 1
            if depth == 0:
                return json.loads(raw[start:i + 1])
    raise ValueError(f"{model_dir}/keras_metadata.pb 에서 모델 config 를 못 찾았다")


def _input_shape(cfg: dict) -> list:
    return cfg["config"]["layers"][0]["config"]["batch_input_shape"]["items"]


def _last_layer(cfg: dict) -> tuple[str, dict]:
    layer = cfg["config"]["layers"][-1]
    return layer["class_name"], layer["config"]


def _sample_window(tf_mod):
    """학습 데이터 첫 SEQUENCE_LENGTH 행 → (1, 10, 11). 분포 안의 실제 입력이다."""
    import pandas as pd  # noqa: PLC0415
    df = pd.read_csv(TRAINING_CSV, nrows=SEQUENCE_LENGTH)
    cols = [CSV_ALIAS.get(c, c) for c in FEATURE_COLUMNS]
    return df[cols].to_numpy(dtype="float32").reshape(1, SEQUENCE_LENGTH, len(FEATURE_COLUMNS))


# ── 검사 6개 ───────────────────────────────────────────────────
def check_1_lstm_loads(ctx: dict) -> tuple[str, str]:
    tf = ctx["tf"]
    if tf is None:
        return SKIP, f"TensorFlow 없음 ({ctx['tf_error']})"
    try:
        ctx["lstm"] = tf.keras.models.load_model(str(paths.LSTM_MODEL_DIR))
    except Exception as exc:  # noqa: BLE001
        return FAIL, (f"{type(exc).__name__}: {exc}\n"
                      f"        → TF 버전 확인({tf.__version__}). Keras 3 면 SavedModel 을 "
                      f"못 읽는다. tensorflow==2.15.1 재설치 → TFSMLayer → 재학습 순.")
    return PASS, f"TF {tf.__version__} 로 적재"


def check_2_input_shape(ctx: dict) -> tuple[str, str]:
    want = [None, SEQUENCE_LENGTH, len(FEATURE_COLUMNS)]
    model = ctx.get("lstm")
    if model is not None:
        got = list(model.input_shape)
        return (PASS if got == want else FAIL), f"model.input_shape = {got} (기대 {want})"
    got = _input_shape(ctx["lstm_cfg"])
    return (PASS if got == want else FAIL), f"[정적] batch_input_shape = {got} (기대 {want})"


def check_3_output_is_normalized(ctx: dict) -> tuple[str, str]:
    """⚠️ 진짜 관문. 출력이 그대로 배분 삼중항이어야 한다."""
    model = ctx.get("lstm")
    if model is not None:
        y = model.predict(_sample_window(ctx["tf"]), verbose=0)
        vec = [float(v) for v in y.reshape(-1)]
        ok = (len(vec) == 3 and abs(sum(vec) - 1.0) < 1e-3
              and all(0.0 <= v <= 1.0 for v in vec))
        detail = f"출력 {[round(v, 4) for v in vec]}, 합 {sum(vec):.6f}"
        if not ok:
            detail += ("\n        → 정규화 전제가 다르다. lstm_model_*/ 에 스케일러가 없어 "
                       "복원 불가 → 재학습.")
        return (PASS if ok else FAIL), detail

    cls, cfg = _last_layer(ctx["lstm_cfg"])
    ok = cls == "Dense" and cfg.get("units") == 3 and cfg.get("activation") == "softmax"
    detail = f"[정적] 마지막 층 {cls}(units={cfg.get('units')}, {cfg.get('activation')})"
    if ok:
        detail += " → 합 = 1, 각 항 ∈ [0,1] 이 구조적으로 보장된다"
    return (PASS if ok else FAIL), detail


def check_4_deterministic(ctx: dict) -> tuple[str, str]:
    model = ctx.get("lstm")
    if model is None:
        layers = [l["class_name"] for l in ctx["lstm_cfg"]["config"]["layers"]]
        risky = [n for n in layers if n in ("Dropout", "GaussianNoise")]
        return SKIP, (f"[정적] 추론 필요. 비결정 후보 레이어: {risky or '없음'} "
                      f"(predict() 는 inference 모드라 통상 결정적)")
    x = _sample_window(ctx["tf"])
    a = model.predict(x, verbose=0)
    b = model.predict(x, verbose=0)
    same = bool((a == b).all())
    return (PASS if same else FAIL), (
        "동일 출력" if same else
        "출력이 달라진다 → 비결정 레이어. lstm_forecast 신뢰도 식을 바꿔야 한다")


def check_5_dqn_classifier(ctx: dict) -> tuple[str, str]:
    tf = ctx["tf"]
    if tf is not None:
        try:
            model = tf.keras.models.load_model(str(paths.DQN_MODEL_DIR))
        except Exception as exc:  # noqa: BLE001
            return FAIL, f"{type(exc).__name__}: {exc} → classify_demand 제외"
        x = _sample_window(tf)[:, -1, :]          # 마지막 스텝 1개 → (1, 11)
        y = model.predict(x, verbose=0).reshape(-1)
        total = float(y.sum())
        ok = len(y) == 3 and abs(total - 1.0) < 1e-3
        return (PASS if ok else FAIL), f"확률 {[round(float(v), 4) for v in y]}, 합 {total:.6f}"

    cfg = ctx["dqn_cfg"]
    cls, last = _last_layer(cfg)
    shape = _input_shape(cfg)
    ok = (shape == [None, len(FEATURE_COLUMNS)] and cls == "Dense"
          and last.get("units") == 3 and last.get("activation") == "softmax")
    return (PASS if ok else FAIL), (
        f"[정적] 입력 {shape}, 마지막 층 {cls}(units={last.get('units')}, "
        f"{last.get('activation')}) → 11 → 3 softmax 분류기")


def check_6_emit_ranges_json(ctx: dict) -> tuple[str, str]:
    """②의 in_distribution 판정 근거. 학습 데이터 통계가 따로 없어 여기서 고정한다."""
    import pandas as pd  # noqa: PLC0415

    if not TRAINING_CSV.exists():
        return FAIL, f"{TRAINING_CSV} 없음 → in_distribution 판정 불가"

    df = pd.read_csv(TRAINING_CSV)
    ranges = {}
    for name in FEATURE_COLUMNS:
        column = CSV_ALIAS.get(name, name)
        if column not in df.columns:
            return FAIL, f"학습 데이터에 {column} 컬럼이 없다 (피처 {name})"
        ranges[name] = {"min": float(df[column].min()), "max": float(df[column].max())}

    # ⚠️ CSV 에는 is_emergency · is_special_event 컬럼이 들어 있다. ranges.json 은 ②가
    #    런타임에 읽으므로 정답 컬럼이 한 개라도 섞이면 그대로 누출이다.
    leaked = [k for k in ranges if any(bad in k for bad in FORBIDDEN)]
    if leaked:
        return FAIL, f"금지 필드가 ranges 에 섞였다: {leaked}"

    write_json(paths.POLICY_RANGES_JSON, {
        "source": str(TRAINING_CSV.relative_to(paths.ROOT)).replace("\\", "/"),
        "rows": int(len(df)),
        "columns": FEATURE_COLUMNS,
        "ranges": ranges,
    })
    return PASS, f"{len(ranges)}개 피처 · {len(df)}행 → {paths.POLICY_RANGES_JSON.name}"


CHECKS = [
    ("1 LSTM 적재", check_1_lstm_loads),
    ("2 입력 (1, 10, 11)", check_2_input_shape),
    ("3 출력 3차원 · 합 ≈ 1 ⚠️", check_3_output_is_normalized),
    ("4 동일 입력 → 동일 출력", check_4_deterministic),
    ("5 분류기 softmax", check_5_dqn_classifier),
    ("6 ranges.json 생성", check_6_emit_ranges_json),
]


def main() -> int:
    tf, tf_error = load_tensorflow()
    ctx: dict[str, Any] = {"tf": tf, "tf_error": tf_error}

    print(f"python {sys.version.split()[0]}")
    if tf is None:
        print(f"tensorflow 없음 — 정적 모드로 2·3·5 만 본다 ({tf_error})")
        print("  TF 2.15.1 은 cp39~cp311 휠만 있다. Python 3.10/3.11 가상환경이 필요하다.")
    else:
        print(f"tensorflow {tf.__version__}")
    print()

    ctx["lstm_cfg"] = keras_config(paths.LSTM_MODEL_DIR)
    ctx["dqn_cfg"] = keras_config(paths.DQN_MODEL_DIR)

    results = []
    for label, check in CHECKS:
        try:
            status, detail = check(ctx)
        except Exception as exc:  # noqa: BLE001
            status, detail = FAIL, f"{type(exc).__name__}: {exc}"
        results.append((label, status))
        print(f"  {status}  {label}\n        {detail}")

    failed = [label for label, status in results if status == FAIL]
    skipped = [label for label, status in results if status == SKIP]

    print()
    gate = next(status for label, status in results if label.startswith("3"))
    if gate == PASS:
        print("3번 통과 → 1차 범위: rule_based + lstm_forecast.")
        print("          C에 '정책 선택' 프롬프트가 필요하다.")
    else:
        print("3번 실패 → 1차 범위: rule_based 단독.")
        print("          정책 선택 축을 빼고 상황 인지 + 에스컬레이션에 집중한다.")
    print("이 결과를 A·C에게 즉시 공유할 것.")

    print(f"\n{len(results) - len(failed) - len(skipped)}/{len(results)} 통과"
          f"{f', 실패 {len(failed)}' if failed else ''}"
          f"{f', SKIP {len(skipped)}' if skipped else ''}")
    if failed:
        return 1
    return 2 if skipped else 0


if __name__ == "__main__":
    sys.exit(main())
