# 금지 필드 검사

**`baseline` arm을 제외한 모든 실행에서 아래 문자열이 에이전트 컨텍스트에 0건이어야 한다.** 도구 설명·반환값·오류 메시지 전부가 검사 대상이다. 1건이라도 나오면 그 실행은 폐기한다.

```python
FORBIDDEN = ["is_emergency", "is_special_event", "is_iot_surge",
             "ground_truth", "perception_accuracy", "escalation_precision"]
```

| 출처 | 어디로만 나가나 |
|---|---|
| `is_emergency` · `is_special_event` · `is_iot_surge` | ①이 `runs/{run_id}/truth.jsonl`에만 기록. 어떤 도구도 읽지 않는다 |
| `perception_accuracy` · `escalation_precision` | `eval/score.py`가 `truth.jsonl`과 조인해 **오프라인** 계산. ④ `get_metrics`는 반환하지 않는다 |

## `baseline` arm의 예외

`baseline`만 `truth.jsonl`을 읽는다. 기존 시스템(CLI `--emergency`)의 재현이므로 정당하지만, **코드 경로를 물리적으로 분리한다.** 같은 함수에 `if arm == "baseline"`으로 두면 실수로 다른 비교군에 샌다.

## `situation` ↔ `truth` 매핑 규칙

`eval/score.py`가 `perception_accuracy`를 계산하려면 **4값 열거형과 3개 bool 사이의 대응을 사전에 못 박아야 한다.** 채점 후에 정하면 유리한 쪽으로 해석할 수 있다.

| `truth` | 정답 `situation` |
|---|---|
| 전부 `false` | `normal` |
| `is_emergency` 만 `true` | `emergency` |
| `is_special_event` 만 `true` | `special_event` |
| `is_iot_surge` 만 `true` | `iot_surge` |
| 둘 이상 `true` | **발생하지 않음** |

시나리오 정의상 세 플래그는 **상호 배타적**이다. `reset(scenario=...)`은 하나만 켜고, `mixed`의 전환 시점(`test_scenarios.py:92`)도 겹치지 않는다 — 스텝 20~50 `special_event`, 60~90 `emergency`, 100~120 `iot_surge`이며 그 사이는 전부 `normal`이다.

**그래도 ①이 `truth.jsonl`을 쓸 때 상호 배타성을 assert 한다.** 시나리오를 나중에 추가하다 겹치면 채점 기준이 조용히 무너진다.

## 전환 경계 처리

플래그가 바뀐 **그 스텝**의 결정은 정답 판정에서 제외한다. 에이전트는 `obs_t`를 보고 판단하는데 `obs_t`는 전환 **직전**의 트래픽을 반영하므로, 전환 스텝을 미탐으로 세면 원리적으로 맞힐 수 없는 것을 틀렸다고 세는 셈이다. `mixed` 120스텝에서 제외 대상은 5스텝이다.
