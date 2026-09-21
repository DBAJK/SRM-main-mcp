"""LLM 에이전트 — MCP 서버 5개를 조합해 자원 배분을 판단한다.

구조
  schema.py    에이전트가 만들어내는 값 (Decision 등)
  guard.py     정답 누출 검사 (flow/forbidden.md)
  tools.py     도구 21개 호출 창구. 백엔드 주입
  loop.py      9스텝 골격. 판단자 주입
  backends/    mock(임시) · mcp(실제 서버)
  deciders/    rule(LLM 없음) · llm(본체)
  arms/        비교군 4종
"""
