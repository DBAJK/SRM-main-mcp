# ③ `slice-market` — 설계 근거

계약은 `spec/market.md`.

## `qos_requirements` 키에 단위를 붙이지 않는 이유

`engine.py:79`의 `latency_ms`는 **쓰지 않는 다른 경로**(`_rule_based_classification`)의 것이다. 실제 점수 경로(`:339`, `:368`, `:398`)는 `latency`·`bandwidth`·`reliability`만 읽는다. 혼동하면 전부 기본값으로 떨어져 모든 벤더가 같은 점수를 받는다.

## `score_offerings` 실측 결과에서 볼 것

1위와 3위가 흥미롭다. vendor-3이 **모든 QoS 지표에서 우월하고 rating도 최고(4.9)** 인데 3위다. 가격(300 vs 250)이 URLLC 기준가 250을 초과해 `price_score`에서 손해를 본다. 에이전트가 "최고 사양"이 아니라 "요구 대비 최적"을 고르는지 관찰할 수 있는 지점이다.

## ⚠️ 정정 J — `get_score_breakdown()`을 그대로 쓰면 총점이 어긋난다

실행해서 확인한 결과다. **같은 벤더·같은 QoS인데 두 함수가 다른 값을 낸다.**

| 함수 | 결과 |
|---|---|
| `score_vendor_offering()` `:719` | **99.20** |
| `get_score_breakdown()` `:819` | **92.00** |

원인은 **레이팅을 읽는 키가 서로 다르기 때문**이다.

```python
# engine.py:792   (score_offerings가 쓰는 경로)
reputation_score = vendor.get("rating", 3.0) / 5.0          # → 4.8 / 5.0 = 0.96

# engine.py:891   (get_score_breakdown 내부)
reputation_score = offer.get("reputation_score", 3.0) / 5.0  # → 키 없음 → 3.0 / 5.0 = 0.60
```

`vendors.json`에는 `rating`만 있고 `reputation_score`는 없다. 따라서 `get_score_breakdown`은 **항상 기본값 3.0**을 쓴다. URLLC의 평판 가중치 0.2 × (4.8−3.0)/5 × 100 = **7.2점** — 관측된 차이와 정확히 일치한다.

**그대로 노출하면 에이전트가 모순된 두 숫자를 받는다.** `score_offerings`는 99.2라 하고 `explain_score`는 92.0이라 한다. 어느 쪽을 믿어야 할지 알 수 없고, 근거 기록(④)에도 잘못된 값이 남는다.

**추가로 버릴 것**: `get_score_breakdown()`의 반환값에는 `neural_network` 키(601바이트)가 있다. 점수 계산을 신경망처럼 그려 보이는 **UI용 장식**이며 에이전트에게 무의미하다. 매 호출마다 컨텍스트를 먹으므로 반환하지 않는다.

## `procure`가 `duration_hours`가 아니라 `duration_steps`인 이유

①이 가상 시계를 쓴다. 단위를 섞으면 만료 시점 계산이 어긋난다.

`current_step`이 필요한 이유: ③은 ①과 별개 프로세스이고 시뮬레이션 상태에 접근할 수 없다. 그런데 `expires_at_step = current_step + duration_steps`를 반환해야 한다. 에이전트가 `observation.step`을 넘겨준다.

비용 환산을 빠뜨리고 두 단위를 그냥 곱하면(`250 × 10 = 2500`) **비용이 4배 부풀어** 조달 비용 지표가 무의미해진다.

`slice_id`를 ④의 `record_decision`에 함께 기록해야 ⑤가 결과 보고 시 `vendor_id`를 되찾을 수 있다.

## 용량 환산 — `capacity_gain`이 존재하는 이유

원래 ①의 모델에는 총량 개념이 없어 `utilization = traffic / allocation`이었고, `allocation`은 비율이라 **조달해도 분모가 커지지 않았다.** 조달이 SLA에 영향을 주지 못하면 `update_rating`의 δ가 의미 없는 신호가 되고 ⑤ → ③ 피드백 루프 전체가 공회전한다.

**결정: ①에 슬라이스별 용량 배수를 도입한다.**

```
utilization[i] = traffic[i] / (allocation[i] × capacity[i])
```

`capacity`는 `{1.0, 1.0, 1.0}`에서 시작하고 조달로만 오른다. 전체 하나가 아니라 **슬라이스별**인 이유: URLLC를 샀는데 eMBB 이용률이 같이 내려가면 물리적으로 맞지 않는다.

### `REFERENCE_BANDWIDTH`의 근거

벤더의 대역폭이 단위(Mbps)부터 환경의 추상 트래픽 단위와 다르므로 환산이 필요하다. `vendors.json` 벤더 5곳의 **슬라이스별 중앙값 실측치**(`{eMBB: 1100, URLLC: 500, mMTC: 120}`)로 나누면 **"평균적인 offering = 1.0배"** 가 되어 벤더 간 차이만 남는다. URLLC 벤더 3곳의 `capacity_gain`이 0.20 / 0.25 / 0.30으로 50% 폭이라 에이전트의 벤더 선택이 결과로 드러난다.

### `GAIN_SCALE = 0.25`의 튜닝 기준

`const.py`에 두고 조정 가능하다. 두 조건을 동시에 만족해야 한다.

1. **조달 1회가 눈에 보일 것** — 해당 슬라이스 압력이 약 20% 내려간다 (1/1.25)
2. **조달만으로 위기가 해소되지 않을 것** — 해소되면 "항상 사는 것"이 지배 전략이 되어 판단이 사라진다

실측 확인: `emergency` 시나리오의 `demand_pressure` 1.436을 1.0 아래로 내리려면 `GAIN_SCALE=0.25`에서 **조달 5회**가 필요하다. 상한 2.0에 걸리므로 완전 해소는 불가능하다. 두 조건 모두 만족한다.

## 비용이 제약이 아닌 이유

상한과 만료 외에 조달을 억제하는 장치가 없으므로, 에이전트는 원리적으로 계속 살 수 있다. 예산을 도입하는 대신 ④가 `procurement_cost_total`을 집계해 **논문 지표로 보고한다.** *"개입도 줄고 SLA도 유지했지만 비용이 2배"* 라면 그것도 정직한 결과다.

## `update_rating`의 δ가 비대칭(+0.05 / −0.20)인 이유

초기 레이팅이 4.5~4.9로 좁게 몰려 있어 작은 δ로는 순위가 바뀌지 않는다. 0.2 하락 = 총점 0.4~0.8점 하락이며, 60~120스텝에서 순위 역전이 관측 가능한 크기다.

에이전트가 중계하는 이유: 서버 간 직접 호출이 없기 때문이다.
