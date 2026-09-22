<!-- docs/ 에서 이관. claude/ 가 정본이다. -->

# 구현 순서와 미결 사항

단계별 완료 판정 · ③ 서버 골격 · 남은 결정

# 8. 구현 순서와 체크포인트

분리 설계서 §7을 유지하되, 각 단계의 **완료 판정 기준**을 붙인다.

| 순서 | 대상 | 완료 판정 | 작업량 |
|---|---|---|---|
| **0** | 모델 적재 검증 | §7의 6개 항목 통과. `ranges.json` 생성 | 小 |
| **1** | ③ `slice-market` | 에이전트가 `score_offerings` 호출 → 5개 벤더 점수 수신. **MCP 배선 검증** | 小 |
| **2** | ① `slice-observe` | 동일 시드 2회 실행 → `truth.jsonl` **바이트 단위 동일** (정정 F 검증) | 中 |
| **3** | ④ `slice-audit` | `get_metrics()` 반환 필드에 정답 의존 지표 **부재** 확인 (정정 D) | 小~中 |
| **4** | ② `slice-policy` | `situation` 인자로 배분이 바뀜(정정 E). LSTM 실패 시 `status="unavailable"` 반환(정정 H) | 中 |
| **5** | ⑤ `slice-feedback` | `warm` 모드 120스텝에서 `reliability.json`의 값이 실제로 움직임 | 中 |
| **6** | `eval/score.py` | `truth.jsonl` × `decisions.json` 조인 → `perception_accuracy` 산출 | 小 |
| **7** | 베이스라인 실행 | 비교군 4개 × 시나리오 5개 × 시드 3개 = 60회 | 中 |
| **8** | ② `dqn` 추가 | 선택. 데이터 재생성 선행 | 大 |

**2단계의 완료 판정이 가장 중요하다.** 동일 시드 재현이 안 되면 이후 모든 비교가 무의미하다. 여기서 반드시 멈추고 확인한다.

1단계(③)를 먼저 하는 이유는 분리 설계서와 같다 — **MCP 배선 자체를 검증**하는 것이 목적이지 ③이 중요해서가 아니다. FastMCP 서버 하나, stdio 연결 하나, 도구 호출 하나가 왕복하면 나머지는 같은 패턴의 반복이다.

# ③ 서버 골격 (1단계 산출물 예시)

```python
# mcp/market/server.py
from fastmcp import FastMCP
from mcp.common.store import read_json, write_json_atomic
from mcp.common.paths import VENDORS
from mcp.market.scoring import score_vendor_offering, get_score_breakdown

mcp = FastMCP("slice-market")

@mcp.tool()
def score_offerings(slice_type: str, qos_requirements: dict) -> list[dict]:
    """주어진 slice_type과 QoS 요구에 대해 등록된 모든 벤더를 점수화한다."""
    vendors = read_json(VENDORS)
    out = [{"vendor_id": v["id"], "name": v["name"],
            "score": score_vendor_offering(v, slice_type, qos_requirements),
            "rating": v["rating"]}
           for v in vendors if slice_type in v.get("offerings", {})]
    return sorted(out, key=lambda x: x["score"], reverse=True)

@mcp.tool()
def update_rating(vendor_id: str, outcome: dict) -> dict:
    """결과 보고를 반영해 벤더 레이팅을 갱신한다. ⑤의 보고를 에이전트가 중계한다."""
    vendors = read_json(VENDORS)
    delta = 0.05 if outcome.get("sla_met") else -0.20
    for v in vendors:
        if v["id"] == vendor_id:
            v["rating"] = max(1.0, min(5.0, v["rating"] + delta))
            write_json_atomic(VENDORS, vendors)
            return {"vendor_id": vendor_id, "rating": v["rating"], "delta": delta}
    return {"error": f"unknown vendor: {vendor_id}"}

if __name__ == "__main__":
    mcp.run()
```

도구 **docstring이 곧 LLM 프롬프트**라는 점을 여기서부터 의식한다 (§6.3).

---

# 9. 남은 미결 사항

분리 설계서 §9 중 이 문서에서 해소되지 않은 것.

| # | 항목 | 상태 |
|---|---|---|
| 0 | TF 적재 검증 | **§7로 절차 확정. 실행 대기** |
| 1 | DQN 1차 포함 여부 | **해소 — 포함하지 않음** (§7) |
| 2 | DQN 상태의 `is_emergency` 차원 | 2차로 이월. 에이전트 추론값 주입이 기본안 |
| 3 | 내재적 신뢰도 산출식 | **해소** (§6.1) |
| 4 | 경험적 신뢰도 갱신식 | **해소** (§6.2) |
| 5 | 오케스트레이터 LLM 선택·비용 | **미해소.** 스텝당 3~5회 도구 호출 × 120스텝 × 60회 실행 ≈ 2~3만 호출. 모델 선정 전 토큰 예산 산정 필요 |
| 6 | 문헌 조사 | 미해소 (3단계) |
| 7 | Dashboard API 재활용 | 미해소 (6단계) |
| 8 | 도구 설명 수위 | **해소 — 실험 변수로 승격** (§6.3) |
| 9 | 에이전트 프롬프트 배경 지식 범위 | **미해소.** §6.3과 같은 문제가 프롬프트에도 있음. `decisions.json`에 프롬프트 해시를 기록해 사후 추적 가능하게 할 것 |
| 10 | 조달의 환경 반영 방식 | **해소 — ①에 용량 배수 도입** (정정 K) |
| 11 | 조달 비용 억제 장치 | **해소 — 예산 대신 상한·만료 + 비용을 논문 지표로 보고** |

**5번이 다음 병목이다.** 2~3만 회의 도구 호출은 비용과 시간 모두에서 무시할 수 없다. 2단계 개발계획서에서 다음을 정해야 한다.

- 모델 선정 (로컬 Ollama vs API)
- 시드 3개가 맞는지, 시나리오 5개를 다 돌릴지
- 스텝당 호출 횟수 상한 (도구 호출 루프가 발산하지 않도록)

**9번은 8번과 같은 위험**이다. 도구 설명을 최소판으로 만들어도 시스템 프롬프트에 *"URLLC 이용률이 높으면 비상 상황일 수 있다"* 라고 적으면 같은 문제가 된다. 프롬프트도 최소판/조언판 두 벌을 준비하고 `config`에 기록한다.

---
