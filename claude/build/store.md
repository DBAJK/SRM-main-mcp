<!-- docs/ 에서 이관. claude/ 가 정본이다. -->

# 공유 데이터 스키마

실행 생명주기 · decisions.json · reliability.json · truth.jsonl · vendors.json

# 5. 공유 데이터 스키마

# 5.0 실행 생명주기 — 무엇이 언제 초기화되는가

**`reset()`은 ①만 초기화한다.** ②③④⑤의 상태는 그대로 남는다. 비교군 4 × 시나리오 5 × 시드 3 = **60회를 돌리는데 산출물 경로가 단일 파일**이면 전부 덮어쓰거나 뒤섞인다.

**실행 단위로 경로를 나눈다.**

```
data/                         ← 실행에 걸쳐 유지
  vendors.json                ③ 소유. 레이팅이 누적된다
  reliability.json            ⑤ 소유. warm 모드에서만 사용

runs/{run_id}/                ← 실행마다 새로
  decisions.json              ④ 생성 · ⑤ 추가기입
  truth.jsonl                 ① 기록. 도구 미노출
  reliability.json            ⑤. cold 모드에서만 사용
  context/                    C의 누출 검사용 덤프
```

| 서버 | 상태 | 실행 시작 시 | 근거 |
|---|---|---|---|
| ① | 배분·용량·이력·리스 | **`reset()`이 전부 초기화** | 에피소드가 곧 ①의 수명 |
| ② | 없음 (모델만 상주) | 초기화 불필요 | 무상태 |
| ③ | `vendors.json`의 `rating` | **초기화 안 함** (기본) | 레이팅 누적이 자기 개선의 증거 |
| ④ | `runs/{run_id}/decisions.json` | 첫 `record_decision`이 파일 생성 | 별도 도구 불필요 |
| ⑤ | `reliability.json` | **모드에 따라 다름** | 아래 |

**⑤와 ③의 초기화는 실험 변수다.**

| 모드 | ⑤ `reliability.json` | ③ `vendors.json` | 보이는 것 |
|---|---|---|---|
| `cold` | `runs/{run_id}/` — 실행마다 새로 | 부트스트랩 재실행 | 단일 에피소드 내 적응 |
| `warm` | `data/` — 전체 누적 | 누적 | **장기 자기 개선** (주 결과) |

모드는 ⑤·③ 서버 기동 시 환경변수(`SLICE_MEMORY_MODE`)로 정하고, `decisions.json`의 `config`에 기록한다. **60회 실행을 섞어 돌리면 안 된다** — `warm` 실행들 사이에 `cold` 실행이 끼면 누적 레이팅이 오염된다. 모드별로 묶어서 돌린다.

> **`run_id`를 발급하는 것은 에이전트(C)다.** 형식 `{arm}-{scenario}-s{seed}`. ①의 `reset()`과 ④의 모든 기록에 같은 값이 들어가야 `truth.jsonl`과 `decisions.json`이 `step`으로 조인된다 (§1.5 V3).

# `runs/{run_id}/decisions.json`

④가 생성하고 ⑤가 같은 레코드에 덧붙인다 (분리 설계서 §2.1).

```json
{
  "run_id": "exp-proposed-emergency-s0",
  "config": {"scenario": "emergency", "seed": 0, "arm": "proposed",
             "desc_mode": "minimal", "tau": 0.45},
  "decisions": [
    {
      "decision_id": "exp-proposed-emergency-s0-0012",
      "step": 12,
      "kind": "decision",
      "situation": "emergency",
      "chosen_policy": "rule_based",
      "allocation": {"embb": 0.20, "urllc": 0.70, "mmtc": 0.10},
      "confidence": {"intrinsic": 0.72, "empirical": 0.88, "combined": 0.80},
      "rationale": "URLLC util 1.52 > 1.2, eMBB 동반 상승 없음",
      "observation": { ... },

      "outcome": {                      // ← ⑤가 report_outcome에서 추가
        "sla_met": false,
        "error": 0.18,
        "vendor_id": null,
        "scored_at_step": 13
      }
    },
    { "decision_id": "...-0031", "kind": "escalation",
      "situation": "emergency", "reason": "combined 0.31 < tau 0.45",
      "confidence": {...} }
  ]
}
```

- `kind`로 결정과 에스컬레이션을 한 배열에 둔다. 시간순 재구성이 쉬워진다.
- `config`를 파일에 박는다. 비교군 4 × 시나리오 5 × 시드 N의 산출물이 섞이지 않는다.
- `outcome`이 없는 레코드 = 마지막 스텝 또는 실행 실패. 집계에서 제외 (§3.1 규칙 2).

# `reliability.json` (⑤ 소유)

```json
{
  "rule_based":    {"r": 0.91, "n": 120, "alpha": 0.2},
  "lstm_forecast": {"r": 0.84, "n": 95,  "alpha": 0.2}
}
```

**에피소드 간 유지 여부가 실험 설계 변수다.** §6.2 참조.

# `runs/{run_id}/truth.jsonl` (① 기록, 도구 미노출)

```json
{"step": 12, "is_emergency": true, "is_special_event": false, "is_iot_surge": false}
```

# `data/vendors.json` (③ 소유)

모델 A + `regions`. ⑤는 직접 쓰지 않는다 (분리 설계서 §2.1 승계).

---
