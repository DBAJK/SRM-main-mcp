<!-- docs/ 에서 이관. claude/ 가 정본이다. -->

# 런타임 구조

프로세스 구성 · 저장소 레이아웃 · 기술 스택

# 2. 런타임 구조

# 프로세스 구성

```
orchestrator/run.py  (LLM 에이전트 = MCP 클라이언트)
        │
        │  stdio × 5
        ├──────────────┬──────────────┬──────────────┬──────────────┐
        ▼              ▼              ▼              ▼              ▼
  slice-observe   slice-policy   slice-market   slice-audit   slice-feedback
   (상태 보유)      (무상태)       (읽기 위주)     (로그)        (상태 보유)
        │                                            │              │
        │ truth.jsonl                                │ decisions.json
        ▼ (MCP 도구 아님)                             └──────┬───────┘
   eval/score.py  ◄──────────────────────────────────────────┘
```

- **전송**: stdio. 단일 머신 연구 프로토타입이므로 HTTP 불필요. 서버당 독립 프로세스.
- **①만 에피소드 생명주기를 가진다.** 나머지 넷은 프로세스가 죽어도 파일에서 복구된다.
- **동시 쓰기 없음**: 에이전트가 도구를 순차 호출한다. 락을 두지 않는다 (분리 설계서 §2.1 승계).
- 단, **쓰기는 원자적으로** 한다 — `tmp` 파일에 쓴 뒤 `os.replace()`. 중단 시 JSON 파일이 깨지는 것만 막으면 충분하다.

# 저장소 레이아웃

```
Build-A-Thon-SRM-main/
├── mcp/
│   ├── common/
│   │   ├── paths.py           # 경로 상수 한 곳
│   │   ├── schema.py          # Observation, Decision 등 pydantic 모델
│   │   └── store.py           # 원자적 JSON 읽기/쓰기
│   ├── observe/
│   │   ├── server.py          # ① FastMCP
│   │   └── env.py             # MLOrchestrator에서 추출한 순수 시뮬레이터
│   ├── policy/
│   │   ├── server.py          # ②
│   │   ├── descriptions.py    # 도구 설명 2벌 (§6.3)
│   │   ├── rule.py  lstm.py  dqn.py  classify.py
│   ├── market/
│   │   ├── server.py          # ③
│   │   └── scoring.py         # engine.py에서 추출
│   ├── audit/
│   │   ├── server.py          # ④
│   │   └── metrics.py         # 관측 가능 지표만
│   └── feedback/
│       ├── server.py          # ⑤
│       └── reliability.py     # EMA 갱신 (§6.2)
├── orchestrator/
│   ├── run.py                 # 에이전트 루프 + 비교군 스위치
│   └── prompts/
├── eval/
│   ├── score.py               # 정답 조인 → 정답 의존 지표
│   └── plots.py
├── data/                      # 실행에 걸쳐 유지
│   └── vendors.json           # ③ 소유 (부트스트랩 시 모델 A 복사)
├── runs/{run_id}/             # 실행마다 새로 (§5.0)
│   ├── decisions.json         # ④ 기록 · ⑤ 추가기입
│   ├── truth.jsonl            # ① 기록. 도구 미노출
│   ├── reliability.json       # ⑤ (cold 모드)
│   └── context/               # C의 누출 검사 덤프
└── tools/
    └── step0_verify_models.py # 0단계
```

**기존 코드는 건드리지 않는다.** `mcp/`는 `ml_orchestrator_demo.py`·`engine.py`에서 로직을 **추출(copy-and-adapt)** 하지 저 파일들을 import 하지 않는다. 이유: 두 파일 다 최상단에서 무거운 부작용을 일으킨다 (`MLOrchestrator.__init__`이 `results/` 폴더 생성, 모듈 레벨 TF import). 추출 대상은 §4에 위치를 명시했다.

# 기술 스택

| 항목 | 선택 | 근거 |
|---|---|---|
| MCP 프레임워크 | `fastmcp` | 데코레이터 기반. 서버당 100줄 내외 |
| Python | **3.10** | TF 2.15 호환 상한 |
| TensorFlow | **2.15.1 고정** | Keras 2. SavedModel 직접 적재 (정정 I) |
| 스키마 | `pydantic` v2 | FastMCP가 타입힌트에서 JSON Schema 자동 생성 |
| 가상환경 | **신규 생성** | 동봉된 `venv/`는 Python 3.14 + 타 PC 절대경로. 사용 불가 |

---
