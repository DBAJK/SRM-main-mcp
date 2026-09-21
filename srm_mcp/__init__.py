"""SRM MCP 서버 묶음.

설계서 §2 "저장소 레이아웃". 각 서버는 독립 프로세스로 stdio 전송을 쓴다.
기존 코드(`ml_orchestrator_demo.py`, `engine.py`)를 import 하지 않고 추출(copy-and-adapt)한다.
"""
