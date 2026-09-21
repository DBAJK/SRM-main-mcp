# 오류 규약

**원칙: 에이전트가 판단으로 대응할 수 있는 것은 값으로, 코드 버그는 예외로.**

## 값으로 돌려줄 것 vs 예외를 던질 것

| 상황 | 처리 | 이유 |
|---|---|---|
| 정책 사용 불가 (이력 부족, 모델 없음) | **`status` 필드로 반환** | 에이전트의 판단 재료 |
| 배분 입력이 비정상 | **`accepted: false`로 반환** | 에이전트가 재시도 가능 |
| 존재하지 않는 `vendor_id` | **`error` 필드로 반환** | 오타 복구 가능 |
| 존재하지 않는 `decision_id` | **`error` 필드로 반환** | |
| 용량 상한 초과 (`add_capacity`) | **`accepted: false`로 반환** | 에이전트가 다른 슬라이스를 택할 수 있음 |
| `current_step`이 과거 (`procure`) | **`status: "rejected"`로 반환** | 순서 실수. 복구 가능 |
| 잘못된 열거형 값 | 예외 (FastMCP가 스키마 검증) | 계약 위반 |
| 파일 I/O 실패 | 예외 | 복구 불가 |

**오류 메시지도 프롬프트의 일부다.** 복구에 필요한 정보를 같이 준다.

```json
// 존재하지 않는 벤더 — available을 같이 주면 에이전트가 한 번에 복구한다
{"error": "unknown_vendor", "vendor_id": "vendor-9",
 "available": ["vendor-1", "vendor-2", "vendor-3", "vendor-4", "vendor-5"]}
```

## 호출 순서 위반

| 위반 | 반환 |
|---|---|
| `report_outcome`을 `step()` 전에 호출 | `{"error": "premature_scoring", "reason": "decision at step 12, observed step 12; expected >= 13"}` |
| `add_capacity`를 `step()` 후에 호출 | 허용되지만 **한 스텝 늦게 반영**된다. 조달한 스텝은 효과를 못 본다 |
| `procure` 없이 `add_capacity` 호출 | 허용. 용량은 늘지만 **비용이 기록되지 않아** 지표가 왜곡된다. 검사기가 경고 |
| `apply_allocation` 없이 `step()` 두 번 | 허용. 직전 배분이 유지됨 |
| `reset()` 없이 시작 | 허용. `seed=0`, `scenario="normal"`로 자동 초기화 |
