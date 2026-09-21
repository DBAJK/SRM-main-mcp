# 공통 타입

모든 서버가 공유한다. `mcp/common/schema.py`에 pydantic 모델로 한 번만 정의한다.

## `SliceTriple`

3개 슬라이스에 대한 실수 3개. **배열이 아니라 딕셔너리다.** (배열은 인덱스 순서가 바뀌면 조용히 틀린다)

```json
{"embb": 0.40, "urllc": 0.40, "mmtc": 0.20}
```

## `SliceFlags`

```json
{"embb": true, "urllc": true, "mmtc": false}
```

## 열거형

| 이름 | 값 | 비고 |
|---|---|---|
| `Situation` | `"normal"` · `"emergency"` · `"special_event"` · `"iot_surge"` | **에이전트가 관측으로부터 추론해 만드는 값.** 어떤 도구도 알려주지 않는다 |
| `PolicyName` | `"rule_based"` · `"lstm_forecast"` · `"dqn"` | |
| `SliceType` | `"eMBB"` · `"URLLC"` · `"mMTC"` | ③에서만 쓴다. 대소문자가 `vendors.json`의 키와 정확히 일치해야 한다 |
| `Status` | `"ok"` · `"unavailable"` · `"error"` | |

## 숫자 타입 규약 ⚠️

**JSON은 numpy를 모른다.** 모든 경계에서 파이썬 기본형으로 변환한다.

| 타입 | `json.dumps()` | 비고 |
|---|---|---|
| `np.ndarray` | **실패** | `.tolist()` 필요 |
| `np.bool_` | **실패** | `bool()` 필요 |
| `np.float64` | 통과 | 파이썬 `float` 상속. **우연히 통과하는 것** |
| `float`, `bool`, `int` | 통과 | |

`violations`가 정확히 `np.bool_`이다 (`ml_orchestrator_demo.py:563`). 그대로 반환하면 도구 호출이 예외로 죽는다. `np.float64`는 통과하므로 **한참 잘 돌다가 `violations`에서만 터진다.**
