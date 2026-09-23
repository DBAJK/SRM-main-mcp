"""오케스트레이터 배선 검사 — LLM 없이 게이트웨이와 심판을 확인한다.

    .venv/Scripts/python tools/check_orchestrator.py

1. 게이트웨이가 서버 5개를 띄우고 HTTP 로 도구를 재노출한다 (reset 은 숨김)
2. 도구 설명이 서버가 낸 원문 그대로다
3. HTTP 클라이언트(= CLI 자리)로 한 스텝을 손으로 밟는다 → 호출 기록 · Guard · 상한
4. 심판이 올바른 순서에 위반 0, 어긋난 순서에 정확한 코드를 낸다

`fastmcp` 가 필요하다. 끝나면 vendors.json 과 runs/_check-orchestrator/ 를 되돌린다.
"""
from __future__ import annotations

import asyncio
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from agent.orchestrator.gateway import Gateway  # noqa: E402
from agent.orchestrator.referee import judge  # noqa: E402

RUN_ID = "_check-orchestrator"
FAILS = 0


def check(label: str, ok: bool, got=None) -> None:
    global FAILS
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f": {got}" if got is not None else ""))
    if not ok:
        FAILS += 1


def calls(*names: str) -> list[dict]:
    return [{"tool": n, "ok": True} for n in names]


def main() -> int:
    run_dir = ROOT / "runs" / RUN_ID
    if run_dir.exists():
        shutil.rmtree(run_dir)
    vendors = ROOT / "data" / "vendors.json"
    vendors_backup = vendors.read_bytes() if vendors.exists() else None

    print("1. 게이트웨이 기동")
    gw = Gateway(RUN_ID, run_dir / "orchestrator", memory_mode="cold",
                 server_log_dir=run_dir / "servers", max_calls=6)
    try:
        url = gw.start()
        check("HTTP 열림", url.startswith("http://127.0.0.1:"), url)
        check("서버 5개 모두 실서버", gw.backend.live == ["audit", "feedback", "market", "observe", "policy"],
              gw.backend.live)
        check("도구 21개 = 20개 재노출 + compute_confidence", len(gw.exposed) == 21, len(gw.exposed))
        check("reset 은 숨김", "reset" not in gw.exposed)
        cfg = json.loads(gw.write_mcp_config().read_text(encoding="utf-8"))
        check("servers.json 에 게이트웨이 하나", list(cfg["mcpServers"]) == ["slice"], cfg)

        print("\n2. 도구 설명 원문 유지")
        upstream = {t.name: t.description for t in gw.backend.list_tools("observe")}

        async def _list():
            from fastmcp import Client
            async with Client(url) as c:
                return {t.name: (t.description, t.input_schema) for t in await c.list_tools()}

        seen = asyncio.run(_list())
        check("HTTP 로 보이는 도구 수", len(seen) == 21, len(seen))
        check("get_observation 설명 동일", seen["get_observation"][0] == upstream["get_observation"])
        check("apply_allocation 스키마에 embb·urllc·mmtc",
              set(seen["apply_allocation"][1].get("properties", {})) >= {"embb", "urllc", "mmtc"},
              sorted(seen["apply_allocation"][1].get("properties", {})))

        print("\n3. HTTP 클라이언트로 한 스텝 (CLI 자리)")
        gw.call("observe", "reset", run_id=RUN_ID, scenario="emergency", seed=0)
        gw.begin_step(0)

        async def _step():
            from fastmcp import Client
            out = {}
            async with Client(url) as c:
                obs = (await c.call_tool("get_observation", {})).data
                out["obs"] = obs
                out["rel"] = (await c.call_tool("get_reliability_table", {})).data
                prop = (await c.call_tool("propose_allocation", {
                    "policy": "rule_based", "observation": obs, "situation": "emergency"})).data
                out["prop"] = prop
                conf = (await c.call_tool("compute_confidence", {
                    "intrinsic": prop["confidence"],
                    "empirical": out["rel"]["rule_based"]["effective"]})).data
                out["conf"] = conf
                rec = (await c.call_tool("record_decision", {
                    "step": obs["step"], "observation": obs, "situation": "emergency",
                    "chosen_policy": "rule_based", "allocation": prop["allocation"],
                    "confidence": {"situation": 0.8, "intrinsic": prop["confidence"],
                                   "empirical": out["rel"]["rule_based"]["effective"],
                                   "combined": conf["combined"]},
                    "rationale": "check"})).data
                out["rec"] = rec
                await c.call_tool("apply_allocation", prop["allocation"])
                # 6회 상한 — 7번째부터 거부돼야 한다
                out["refused"] = (await c.call_tool("step", {"n": 1})).data
            return out

        got = asyncio.run(_step())
        check("관측에 step 필드", "step" in got["obs"], got["obs"].get("step"))
        check("② 제안 status ok", got["prop"].get("status") == "ok", got["prop"].get("status"))
        check("compute_confidence 공식 √(i×e)",
              abs(got["conf"]["combined"] - (got["prop"]["confidence"] * got["rel"]["rule_based"]["effective"]) ** 0.5) < 1e-3,
              got["conf"])
        check("④ decision_id 형식 {run_id}-{step:04d}", got["rec"].get("decision_id") == f"{RUN_ID}-0000",
              got["rec"].get("decision_id"))
        check("7번째 호출은 상한으로 거부", got["refused"].get("error") == "call_budget_exceeded",
              got["refused"].get("error"))

        log = gw.log.for_step(0)
        check("호출 기록 7건", len(log) == 7, len(log))
        check("기록에 서버 표기", [e["server"] for e in log][:3] == ["observe", "feedback", "policy"],
              [e["server"] for e in log])
        check("Guard 통과 횟수 ≥ 6", gw.guard.checked >= 6, gw.guard.checked)
        check("누출 없음", gw.leak is None)

        print("\n4. 심판")
        good = judge(0, calls("get_observation", "get_reliability_table", "propose_allocation",
                              "compute_confidence", "record_decision", "apply_allocation",
                              "step", "report_outcome"))
        check("표준 순서 → 위반 0", good.violations == [], good.violations)

        proc_good = judge(1, calls("get_observation", "score_offerings", "procure", "add_capacity",
                                   "record_decision", "apply_allocation", "step",
                                   "report_outcome", "update_rating"))
        check("조달 포함 표준 순서 → 위반 0", proc_good.violations == [], proc_good.violations)

        v = judge(2, calls("get_observation", "record_decision", "apply_allocation", "step"))
        check("report 누락 → no_report", [x["code"] for x in v.violations] == ["no_report"],
              [x["code"] for x in v.violations])

        v = judge(3, calls("get_observation", "record_decision", "apply_allocation",
                           "report_outcome", "step"))
        check("step 전 report → report_before_step",
              "report_before_step" in [x["code"] for x in v.violations],
              [x["code"] for x in v.violations])

        v = judge(4, calls("get_observation", "record_decision", "apply_allocation", "step",
                           "add_capacity", "report_outcome"))
        check("step 뒤 add_capacity → add_capacity_after_step (warn)",
              any(x["code"] == "add_capacity_after_step" and x["severity"] == "warn"
                  for x in v.violations), [x["code"] for x in v.violations])

        v = judge(5, calls("get_observation", "record_decision", "record_escalation",
                           "apply_allocation", "step", "report_outcome"))
        check("결정 레코드 둘 → duplicate_decision_record",
              "duplicate_decision_record" in [x["code"] for x in v.violations])

        v = judge(6, calls("get_observation", "apply_allocation", "step", "report_outcome",
                           "record_decision"))
        check("기록이 적용 뒤 → record_after_apply (warn)",
              any(x["code"] == "record_after_apply" for x in v.violations))

        v = judge(7, calls("get_observation", "record_decision", "apply_allocation",
                           "step", "step", "report_outcome"))
        check("step 2회 → multiple_step (error)",
              any(x["code"] == "multiple_step" and x["severity"] == "error" for x in v.violations))

        v = judge(9, [{"tool": "get_observation", "ok": True},
                      {"tool": "record_decision", "ok": True, "value_error": "missing_confidence"},
                      {"tool": "record_decision", "ok": True, "decision_id": "x-0009"},
                      {"tool": "apply_allocation", "ok": True}, {"tool": "step", "ok": True},
                      {"tool": "report_outcome", "ok": False, "error": "ToolError: 'embb'"},
                      {"tool": "report_outcome", "ok": True, "sla_met": True}])
        check("값으로 거부된 호출은 세지 않음 → 위반 0 · failed_calls 2",
              v.violations == [] and v.failed_calls == 2,
              ([x["code"] for x in v.violations], v.failed_calls))

        v = judge(8, [{"tool": "get_observation", "ok": True},
                      {"tool": "record_escalation", "ok": True, "decision_id": "x-0008"},
                      {"tool": "apply_allocation", "ok": True}, {"tool": "step", "ok": True,
                                                                 "episode_done": True},
                      {"tool": "report_outcome", "ok": True, "sla_met": False}])
        check("사실 추출: escalated · episode_done · sla_met",
              v.escalated and v.episode_done and v.sla_met is False and v.decision_id == "x-0008",
              (v.escalated, v.episode_done, v.sla_met, v.decision_id))
    finally:
        gw.stop()
        if vendors_backup is not None:
            vendors.write_bytes(vendors_backup)
        if run_dir.exists():
            shutil.rmtree(run_dir, ignore_errors=True)

    print("\n" + ("전부 통과" if FAILS == 0 else f"실패 {FAILS}건"))
    return 0 if FAILS == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
