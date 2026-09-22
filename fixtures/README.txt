# AI 돌려서 폴더에 있는 json 내용 정리햇으

fixtures/ 안내 — ①(observe) 없이 개발·테스트용 샘플 데이터
생성 스크립트: tools/record_fixtures.py (seed=0 고정 — 재실행해도 항상 같은 값이 나옴)
================================================================
obs_normal.jsonl / obs_emergency.jsonl / obs_mixed.jsonl
================================================================
각 파일은 해당 시나리오를 30스텝 돌리며, 매 스텝 진행 "직전"의 관측값을 한 줄씩 기록한
것이다. ①의 get_observation() 이 실제로 돌려주는 것과 형식이 완전히 같다.
한 줄 = 관측 1개 (JSON 객체). 필드 설명:
  step             현재 스텝 번호 (0부터 시작)
  sim_time         가상 시계 (벽시계 아님)
                     hour_of_day  0~23
                     day_of_week  0=월요일 ~ 6=일요일
                     is_weekend   day_of_week >= 5
  traffic          슬라이스별 수요. eMBB / URLLC / mMTC, 범위 0.1~2.0
  allocation       현재 적용된 배분 (embb+urllc+mmtc 의 합 = 1.0)
  utilization      이용률 = traffic / (allocation x capacity)
  capacity         슬라이스별 용량 배수. 기본 1.6, 조달하면 올라감, 상한 2.6
  thresholds       임계값 (고정값). embb 0.9 / urllc 1.2 / mmtc 0.8
  violations       이용률이 임계값을 넘었는지 (true/false), 슬라이스별
  client_count     정규화된 단말 수 (0~1)
  bs_count         정규화된 기지국 수 (0~1)
  demand_pressure  수요 압력. 1.0 을 넘으면 재배분만으로는 전 슬라이스 SLA 를 못 지킨다
                   (= 외부 조달이 필요하다는 신호)
  features         분류기 / LSTM 이 쓰는 11차원 피처 (traffic_load, time_of_day 등).
                   history_emergency.jsonl 의 columns 와 같은 항목이다.
* 파일 안에 "정답"(지금 비상 상황인지 등)은 없다. 일부러 뺀 것이다 — 에이전트는 이
  값들만 보고 situation 을 직접 추론해야 한다 (이 프로젝트의 핵심 규칙).
================================================================
history_emergency.jsonl
================================================================
emergency 시나리오를 30스텝 돌린 뒤 get_history(30) 결과를 한 줄에 한 스텝씩 풀어놓은
것이다. ②의 lstm_forecast 정책이 받는 입력 형태(11차원 x n스텝 시퀀스) 그대로다.
  columns   피처 이름 11개, 순서 고정
            [traffic_load, time_of_day, day_of_week,
             embb_alloc, urllc_alloc, mmtc_alloc,
             embb_util, urllc_util, mmtc_util,
             client_count, bs_count]
  values    columns 순서에 대응하는 실제 숫자 11개
================================================================
쓰는 법 (파이썬 예시)
================================================================
  import json
  with open("fixtures/obs_emergency.jsonl", encoding="utf-8") as f:
      observations = [json.loads(line) for line in f]
  # observations[0] 이 첫 스텝의 관측값. ①을 안 켜고도 진짜 응답인 것처럼 바로 쓴다.
  result = propose_allocation(policy="rule_based",
                               observation=observations[0],
                               situation="emergency")
================================================================
주의
================================================================
- 이 파일들은 개발·테스트용 샘플이지 실제 실험 결과가 아니다. 논문 수치로 쓰지 말 것.
- seed=0 고정이라 재생성해도 항상 같은 값이 나온다. 다른 조건으로 테스트하려면
  tools/record_fixtures.py 를 고쳐서 다시 생성한다.

