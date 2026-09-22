"""서버 3개를 **별도 프로세스로 stdio 기동**해 1스텝을 왕복시킨다. (B 소유)

    .venv310/Scripts/python tools/smoke_servers.py

`check_*.py` 는 도구 함수를 파이썬으로 직접 부르지만 이 스크립트는 실제 MCP 전송을 탄다 —
프로세스 분리 · 핸드셰이크 · JSON 직렬화 · 스키마 검증까지 걸린다. ①④가 아직 없으므로
합성 관측을 쓰고, ②③⑤ 사이의 값 중계(에이전트 역할)를 파이썬이 대신한다.

M1(배선 검증)의 증거로 쓸 수 있다. `fastmcp` 가 필요하다.

⚠️ `update_rating` 이 `data/vendors.json` 을 실제로 갱신하므로 끝나면 되돌린다.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
from pathlib import Path

# Windows 기본 콘솔은 cp949 라 '—' 한 글자에 UnicodeEncodeError 로 죽는다.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from fastmcp import Client
    from fastmcp.client.transports import StdioTransport
except ImportError:
    sys.exit("fastmcp 가 없다. pip install -r requirements-mcp.txt")

from srm_mcp.common import paths  # noqa: E402
from srm_mcp.common.store import read_json, write_json  # noqa: E402

RUN_ID = "_smoke-s0"
ENV = {**os.environ, "PYTHONPATH": str(ROOT), "PYTHONIOENCODING": "utf-8",
       "SLICE_MEMORY_MODE": "cold", "SLICE_RUN_ID": RUN_ID, "SLICE_DESC_MODE": "minimal"}

QOS = {"latency": 1.0, "bandwidth": 400, "reliability": 99.99}
OBS = {"step": 12, "utilization": {"embb": 1.3, "urllc": 1.525, "mmtc": 0.95},
       "traffic": {"embb": 0.55, "urllc": 0.72, "mmtc": 0.18},
       "allocation": {"embb": 0.4, "urllc": 0.4, "mmtc": 0.2},
       "capacity": {"embb": 1.0, "urllc": 1.0, "mmtc": 1.0},
       "demand_pressure": 1.436}
OBSERVED = {**OBS, "step": 13,
            "allocation": {"embb": 0.34, "urllc": 0.49, "mmtc": 0.17},
            "utilization": {"embb": 1.618, "urllc": 1.469, "mmtc": 1.059},
            "violations": {"embb": True, "urllc": True, "mmtc": True}}


def transport(module: str) -> "StdioTransport":
    return StdioTransport(command=sys.executable, args=["-m", module],
                          cwd=str(ROOT), env=ENV)


def build_history(n: int = 10):
    """①의 get_history() 자리. 학습 데이터 앞 n행을 그대로 쓴다 — 분포 안이 보장된다.

    컬럼 이름을 CSV 쪽(`embb_allocation` …)으로 넘겨서 `features.ALIASES` 변환 경로까지
    같이 태운다. A가 어느 이름을 쓰든 받아야 하는 자리다.
    """
    try:
        import pandas as pd
    except ImportError:
        return None
    csv = paths.DQN_TRAINING_DATA / "dqn_training_data.csv"
    if not csv.exists():
        return None
    columns = ["traffic_load", "time_of_day", "day_of_week",
               "embb_allocation", "urllc_allocation", "mmtc_allocation",
               "embb_utilization", "urllc_utilization", "mmtc_utilization",
               "client_count", "bs_count"]
    df = pd.read_csv(csv, nrows=n)[columns]
    return {"n": n, "columns": columns,
            "features": [[float(v) for v in row] for row in df.to_numpy()]}


def seed_decisions() -> None:
    """④가 아직 없으므로 decisions.json 을 직접 깔아 둔다 (설계서 §5.0 형식)."""
    write_json(paths.decisions_json(RUN_ID), {
        "run_id": RUN_ID,
        "config": {"scenario": "emergency", "seed": 0, "arm": "proposed", "tau": 0.45},
        "decisions": [
            {"decision_id": f"{RUN_ID}-0012", "step": 12, "kind": "decision",
             "situation": "emergency", "chosen_policy": "rule_based",
             "allocation": {"embb": 0.2, "urllc": 0.7, "mmtc": 0.1},
             "vendor_id": "vendor-1"},
            {"decision_id": f"{RUN_ID}-0020", "step": 20, "kind": "decision",
             "situation": "normal", "chosen_policy": "lstm_forecast",
             "allocation": {"embb": 0.4, "urllc": 0.4, "mmtc": 0.2}},
        ]})


async def main() -> int:
    shutil.rmtree(paths.run_dir(RUN_ID), ignore_errors=True)
    seed_decisions()
    ratings_before = {v["id"]: v["rating"] for v in read_json(paths.VENDORS_JSON)}

    async with Client(transport("srm_mcp.policy.server")) as pol, \
               Client(transport("srm_mcp.market.server")) as mkt, \
               Client(transport("srm_mcp.feedback.server")) as fb:

        print(f"연결: policy {len(await pol.list_tools())} · market {len(await mkt.list_tools())}"
              f" · feedback {len(await fb.list_tools())} 도구\n")
        print("── 1스텝 표준 호출 순서 (spec/tools.md) ──")

        table = (await fb.call_tool("get_reliability_table", {})).data
        print(f"2.  ⑤ get_reliability_table → rule_based {table['rule_based']}")

        history = build_history()
        if history is None:
            print("    (학습 데이터가 없어 history 없이 간다 — lstm 은 unavailable)")

        obs = dict(OBS)
        if history:
            # ①이 관측에 11차원 피처를 싣는 형태 (Day 0 확정 대상).
            obs["features"] = history["features"][-1]
            obs["feature_columns"] = history["columns"]

        demand = (await pol.call_tool("classify_demand", {"observation": obs})).data
        print(f"2b. ② classify_demand → dominant={demand['dominant']} "
              f"margin={round(demand['margin'], 4) if demand['available'] else '-'} "
              f"available={demand['available']}")
        if demand["available"]:
            print(f"    probabilities={ {k: round(v, 4) for k, v in demand['probabilities'].items()} }")

        rows = (await pol.call_tool("compare_policies",
                                    {"observation": obs, "situation": "emergency",
                                     "history": history,
                                     "recent_errors": table})).data
        for row in rows:
            print(f"3.  ② {row['policy']:14} status={row['status']:12} "
                  f"conf={row['confidence']:<7} alloc={row['allocation']}")
            if row["status"] != "ok":
                print(f"    {' ' * 14} reason={row['reason']}")
        chosen = next(r for r in rows if r["status"] == "ok")

        if history:
            print("\n3b. ② recent_error 가 신뢰도를 바꾸는가 (V4)")
            for err in (None, 0.1, 0.3):
                r = (await pol.call_tool("propose_allocation",
                                         {"policy": "lstm_forecast", "observation": obs,
                                          "situation": "emergency", "history": history,
                                          "recent_error": err})).data
                print(f"    recent_error={str(err):5} → conf={r['confidence']:<7} "
                      f"in_dist={r['in_distribution']} status={r['status']}")

        top = (await mkt.call_tool("score_offerings",
                                   {"slice_type": "URLLC", "qos_requirements": QOS})).data[0]
        print(f"\n5a. ③ score_offerings 1위 → {top['vendor_id']} {top['score']}")

        proc = (await mkt.call_tool("procure", {
            "vendor_id": top["vendor_id"], "slice_type": "URLLC", "qos_requirements": QOS,
            "duration_steps": 10, "current_step": OBS["step"]})).data
        print(f"5b. ③ procure → {proc['slice_id']} gain={proc['capacity_gain']} "
              f"cost={proc['cost_total']} expires={proc['expires_at_step']}")
        print(f"5c. ① add_capacity(amount={proc['capacity_gain']}) ← 에이전트가 중계 (① 미구현)")
        print(f"6~7. ① apply_allocation({chosen['allocation']}) → step()  (① 미구현)")

        out = (await fb.call_tool("report_outcome",
                                  {"decision_id": f"{RUN_ID}-0012",
                                   "observed": OBSERVED})).data
        print(f"\n8.  ⑤ report_outcome → sla_met={out['sla_met']} error={out['error']} "
              f"actuator_delta={out['actuator_delta']} vendor={out['vendor_id']}")

        if out["vendor_id"]:
            rating = (await mkt.call_tool("update_rating", {
                "vendor_id": out["vendor_id"],
                "outcome": {"sla_met": out["sla_met"],
                            "decision_id": f"{RUN_ID}-0012"}})).data
            print(f"9.  ③ update_rating → {rating['rating_before']} → {rating['rating_after']}")
            after = (await mkt.call_tool("score_offerings",
                                         {"slice_type": "URLLC",
                                          "qos_requirements": QOS})).data[0]
            print(f"    레이팅이 점수에 반영됨: {top['score']} → {after['score']}")

        print("\n── 오류를 값으로 (flow/errors.md) ──")
        probes = [
            ("procure 과거 스텝", mkt, "procure",
             {"vendor_id": "vendor-1", "slice_type": "URLLC", "qos_requirements": QOS,
              "duration_steps": 10, "current_step": 5}),
            ("procure 기간 초과", mkt, "procure",
             {"vendor_id": "vendor-1", "slice_type": "URLLC", "qos_requirements": QOS,
              "duration_steps": 99, "current_step": 13}),
            ("explain 없는 벤더", mkt, "explain_score",
             {"vendor_id": "vendor-9", "slice_type": "URLLC", "qos_requirements": QOS}),
            ("report 재채점", fb, "report_outcome",
             {"decision_id": f"{RUN_ID}-0012", "observed": OBSERVED}),
            ("report step() 전", fb, "report_outcome",
             {"decision_id": f"{RUN_ID}-0020", "observed": {**OBSERVED, "step": 20}}),
        ]
        for label, client, tool, args in probes:
            data = (await client.call_tool(tool, args)).data
            print(f"  {label:18} → {data.get('error') or data.get('reason')}")

        print("\n── 계약 위반은 예외로 ──")
        for label, client, tool, args in [
            ("잘못된 situation", pol, "propose_allocation",
             {"policy": "rule_based", "observation": OBS, "situation": "Emergency"}),
            ("없는 policy", pol, "propose_allocation",
             {"policy": "ppo", "observation": OBS, "situation": "normal"}),
            ("단위 붙은 qos 키", mkt, "score_offerings",
             {"slice_type": "URLLC", "qos_requirements": {"latency_ms": 1.0}}),
        ]:
            try:
                await client.call_tool(tool, args)
                print(f"  {label:18} → !! 통과했다")
            except Exception as exc:  # noqa: BLE001
                print(f"  {label:18} → 도구 오류 ({str(exc).splitlines()[0][-60:]})")

        print("\n── 금지 필드 — 도구 표면 전수 (flow/forbidden.md) ──")
        from srm_mcp.common.const import FORBIDDEN  # noqa: PLC0415
        surface = ""
        for client in (pol, mkt, fb):
            for tool in await client.list_tools():
                surface += tool.name + (tool.description or "") + json.dumps(tool.input_schema)
        hits = [w for w in FORBIDDEN if w in surface]
        print(f"  {hits or '0건'}")

    # 되돌리기
    vendors = read_json(paths.VENDORS_JSON)
    for vendor in vendors:
        vendor["rating"] = ratings_before[vendor["id"]]
    write_json(paths.VENDORS_JSON, vendors)
    shutil.rmtree(paths.run_dir(RUN_ID), ignore_errors=True)

    print("\n3개 프로세스 정상 종료 · vendors.json 복원됨")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
