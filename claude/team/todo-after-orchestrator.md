# 남은 수정 목록 — 오케스트레이터 도입 후

작성 2026-09-23 · C(에이전트) · 대상 A·B·C 전원

`--driver orchestrator`(LLM 이 도구를 직접 들고 스텝의 흐름을 잡는 구조)를 붙여 실서버 5개로
돌려 본 뒤 정리한 것이다. 팀 보고서 `issue-B-policy-feedback.md` 의 4건을 포함하고, 오케스트레이터
실행에서 새로 드러난 것을 더했다. 순서는 **정책 선택 실험이 성립하는 데 필요한 것**부터다.

실측 근거: `runs/proposed-mixed-s0/report.html`(sonnet 10스텝 · 9스텝) · `runs/orch-check-*/`(haiku).

---

## 지금 상태 한 줄

판단은 살아 있다 — LLM 이 상황을 읽고, 정책을 고르고, 벤더를 골라 사고, 절차를 스스로 지킨다
(절차 준수 1.0). 그런데 **배분 숫자는 새 데이터로 보정되지 않는다.** 실제로 배분을 내는 정책이
`rule_based` 하나이고 그것은 상황 라벨 4개에 배분 4개가 박힌 표다. 관측을 읽지 않는다.
관측으로 배분을 고칠 장치 둘(위반 보정 · LSTM)이 모두 꺼져 있어 SLA 위반이 매 스텝 같은 방향으로 난다.

---

## 1순위 — 이게 안 되면 정책 축이 죽어 있다

| # | 수정 | 위치 | 담당 | 크기 |
|---|---|---|---|---|
| 1 | **`lstm_forecast` 흡수 상태 해소.** 표본이 없을 때 ⑤가 `recent_error=null` 대신 사전값에서 유도한 오차(lstm 0.8 → 0.15)를 준다. `null` 을 ②가 최악 오차와 같게 취급해 고르는 순간 개입되고, 개입 스텝 성적은 폴백에 붙어 표본이 영영 안 쌓인다. (보고서 1번 · A안) | `srm_mcp/feedback/reliability.py` | B | 小 |
| 2 | **개입 스텝의 원래 정책을 장부에 남긴다.** `record_escalation` 이 `chosen_policy` 를 `FALLBACK_POLICY` 로 덮는다. `agent_policy` 필드를 추가하고 시그니처에 `chosen_policy` 를 받는다. 에이전트(고정 루프 · 오케스트레이터 프롬프트)는 그 값을 중계만 한다. (보고서 4번) | `srm_mcp/audit/book.py` · `agent/loop.py` · `agent/orchestrator/prompt.md` | A + C | 小 |
| 3 | **위반 보정을 환경변수로 되살린다.** `SLICE_RULE_CORRECTION=on/off`. 원본 `:446~457` 의 "임계 넘은 슬라이스에 배분을 더 주고 가장 여유 있는 곳에서 뺀다" 를 옮긴다. 켜면 배분이 관측에 반응하고 SLA 위반 63% 가 내려갈 것. 양쪽을 다 측정해 Day 0 결정을 데이터로 대신한다. (보고서 3번) | `srm_mcp/policy/rule.py` | B | 中 |
| 4 | **오케스트레이터 프롬프트에 이력 규칙.** "`lstm_forecast` 를 쓰려면 `get_history` 의 결과를 `history` 인자로 넘긴다" 한 줄. 9스텝 실측에서 `get_history` 는 4번만 불렸다 — 이력 없이는 LSTM 이 모델이 있어도 `unavailable` 이다 (CLAUDE.md 규칙 8의 책임이 LLM 으로 넘어간 것). | `agent/orchestrator/prompt.md` | C | 小 |
| 5 | **TensorFlow 환경에서 실행.** 지금 개발 머신은 Python 3.14 + `.venv` 라 `lstm_forecast` · `classify_demand` 가 `model_not_loaded`. `.venv310`(TF 2.15.1) 머신에서 `tools/step0_verify_models.py` 통과 후 본실험. | 환경 | A | 환경 |

## 2순위 — 측정의 정직성

| # | 수정 | 위치 | 담당 | 크기 |
|---|---|---|---|---|
| 6 | **오류 스텝 제외 채점.** 심판(`referee.jsonl`)이 오류 등급 위반(`no_step` `no_report` `no_decision_record` `multiple_step` `report_before_step` `apply_after_step`)을 낸 스텝을 지표에서 빼고, 제외 수를 같이 보고한다. 지금 `eval/score.py` 는 위반을 모른다. | `eval/score.py` | C | 小 |
| 7 | **에스컬레이션 불이행 심판 규칙.** `compute_confidence` 가 `escalate: true` 를 냈는데 `record_decision` 을 부른 경우를 위반으로 센다. 지금은 잡지 못한다. | `agent/orchestrator/referee.py` | C | 小 |
| 8 | **④의 `confidence` 타입 검사.** `bad_confidence` 가 키 존재만 본다. LLM 이 `confidence.situation` 에 `"iot_surge"` 문자열을 넣어도 받아들였다 (haiku 실측). 네 값이 float 인지 확인하고 `malformed_confidence` 로 거부. | `srm_mcp/audit/book.py` | A | 小 |
| 9 | **조달 기준 명시 여부 결정.** 프롬프트의 "압력 1.0 이상이면 모자란다" 는 설명일 뿐 강제가 아니라, LLM 이 압력 0.73~0.88 에서도 사고 같은 슬라이스를 연속으로 산다. 스텝당 비용이 고정 루프(120스텝 3137.5)의 약 5배. **선택지**: (a) "압력 1.0 이상일 때만" 을 프롬프트에 넣어 고정 루프와 공정 비교 (b) 자율 판단으로 두고 비용을 측정치로 보고. 본실험 전에 셋이 정한다. | `agent/orchestrator/prompt.md` | C + 팀 | 결정 |
| 10 | **`rule_based` 안전 하한 문서 정정.** 독스트링 "하한 0.50 이라 항상 임계 위" 는 거짓 — `combined = √(intrinsic × empirical)` 이라 empirical 이 함께 떨어지면 뚫린다. 보고서 셋째 안("안전 기본값은 없다")으로 문구를 고친다. (보고서 2번) | `srm_mcp/policy/rule.py` | B | 小 |

## 3순위 — 운영 정리

| # | 수정 | 위치 | 담당 | 크기 |
|---|---|---|---|---|
| 11 | **`data/vendors.json` 추적 해제.** `.gitignore` 에 있지만 커밋 `5b96cdc` 에서 추적에 들어가 실행마다 워킹트리가 더러워진다. `git rm --cached data/vendors.json` 한 번. 부트스트랩이 원본에서 결정적으로 재생성한다. | git | 아무나 | 小 |
| 12 | **본실험 시작 상태 규약.** ⑤ warm 누적(`data/reliability.json`)이 이전 실행을 이어받아 스텝 0 신뢰도표가 `n=5` 로 시작한 실측이 있다. 실험 시작 전 `--memory-mode cold` 또는 파일 삭제를 절차에 명시. `--fresh` 는 ④ 장부와 ③ 평판만 지운다. | `agent/README.md` · 실험 스크립트 | C | 小 |
| 13 | **본실험 배치 스크립트.** 시나리오 5 × 시드 3 × (고정 루프 규칙 · 고정 루프 LLM · 오케스트레이터) 를 순서대로 돌리고 `report.html` 과 `summary.json` 을 한 폴더에 모은다. 60회 이상을 손으로 못 돌린다. 비용 상한과 재시작 지점을 갖는다. | `tools/run_matrix.py` 신규 | C | 中 |
| 14 | **문서 정합.** `build/store.md` 의 confidence 예시(`situation` 누락) · `flow/loop.md` 의 reset 용량 `[1,1,1]` → `[1.6,1.6,1.6]` · `spec/tools.md` 의 조달 순서 표기. | `claude/` | 각 담당 | 小 |

---

## 순서 제안

1. **C 가 지금 바로**: 4 · 6 · 7 · 11 · 12. 반나절. 다른 팀원 코드를 건드리지 않는다.
2. **B · A 에게**: 1 · 2 · 3 · 8 · 10. 1~3 은 `issue-B-policy-feedback.md` 에 실측·제안까지 있으므로 8 · 10 만 덧붙이면 된다.
3. **1~3 이 들어오고 5 의 환경이 준비되면** 13 으로 본실험. 그 전에 돌리는 60회는 정책 선택 축이 죽은 데이터라 다시 돌려야 한다.
4. **9 는 본실험 전에** 셋이 같이 정한다.

## 비용 · 시간 참고 (실측)

| 구성 | 스텝당 | 120스텝 |
|---|---|---|
| 오케스트레이터 · haiku | 호출 10~12 · 47초 · $0.055 | 약 1시간 35분 · 약 $7 |
| 오케스트레이터 · sonnet | 호출 8~19 · 25~87초 · $0.05~0.18 (평균 $0.09) | 약 1시간 25분 · 약 $11 |
| 고정 루프 · LLM(sonnet) | 17초 · $0.048 (보고서 실측) | 35분 · $5.78 |

조달 스텝(16~19회 호출)이 비조달 스텝(8~9회)의 2배 이상이다. 9번 결정이 비용을 크게 좌우한다.
