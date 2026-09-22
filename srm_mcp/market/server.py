"""③ slice-market — FastMCP 서버. (B 소유)

계약: `claude/spec/market.md` · 설계서 §4 ③
M1(배선 검증)의 대상이다 — 가장 먼저, 가장 작게 완성한다. ③이 중요해서가 아니라
FastMCP 서버 하나 · stdio 연결 하나 · 도구 호출 하나가 왕복하는지 보는 것이 목적이다.

    python -m srm_mcp.market.server

상태: `data/vendors.json` 의 rating 이 전부다. 실행 간 유지 여부는 부트스트랩이 정한다
(설계서 §5.0) — warm 은 누적, cold 는 시나리오마다 `bootstrap_vendors.py --force`.

⚠️ FastMCP 는 함수 docstring 을 도구 설명으로 써서 LLM 컨텍스트에 그대로 넣는다.
   아래 docstring 은 구현 지침이라 그대로 나가면 §6.3 의 desc_mode 실험이 오염되고
   C의 누출 검사에도 걸린다. 그래서 `@mcp.tool(description=...)` 로 LLM 이 볼 설명을
   분리했다. 설명은 TOOL_DESC 한 곳에서만 고친다.
"""
from __future__ import annotations

from typing import Any, Optional

from fastmcp import FastMCP

from ..common import paths
from ..common.const import (GAIN_SCALE, RATING_DELTA, REFERENCE_BANDWIDTH,
                            cost_per_step)
from ..common.store import read_json, write_json
from . import scoring

mcp = FastMCP("slice-market")

SLICE_TYPES = ("eMBB", "URLLC", "mMTC")

# qos_requirements 가 실제로 읽는 키는 이 셋뿐이다 (engine.py:339, :368, :398).
# ⚠️ 키 이름에 단위를 붙이지 않는다 — latency_ms 가 아니라 latency.
#    틀리면 전부 기본값으로 떨어져 모든 벤더가 같은 점수를 받는다.
QOS_KEYS = ("latency", "bandwidth", "reliability")
QOS_DEFAULTS = {"latency": 50.0, "bandwidth": 100.0, "reliability": 99.0}

DURATION_RANGE = (1, 60)

# LLM 이 보는 설명. 무엇을 하는지와 호출 규약만 말하고, 언제 쓰라는 조언은 넣지 않는다.
TOOL_DESC = {
    "list_offerings": "벤더 오퍼링 목록. slice_type · region 으로 거를 수 있다.",
    "score_offerings": (
        "요구 QoS로 벤더 오퍼링을 채점한다. 점수 내림차순. "
        "qos_requirements 키는 latency(ms) · bandwidth(Mbps) · reliability(%)."
    ),
    "explain_score": "한 벤더의 점수를 기준별로 분해한다.",
    "procure": (
        "벤더에서 슬라이스를 조달한다. duration_steps 는 시간이 아니라 스텝(1~60), "
        "current_step 은 현재 관측의 step. capacity_gain 과 expires_at_step 을 돌려준다."
    ),
    "update_rating": "결정 결과를 벤더 레이팅에 반영한다.",
}

# procure 가 과거 스텝을 거르기 위해 기억하는 값 (flow/errors.md).
# ③은 무상태에 가깝지만 시뮬레이션 시각만은 단조 증가를 확인해야 한다.
_last_step: int = -1

# 에피소드 경계를 넘는 후퇴는 순서 실수가 아니라 **새 에피소드**다.
# ③에는 reset 도구가 없고(spec/tools.md 의 도구 5개가 전부) ①의 reset 을 볼 수도 없으므로
# 후퇴 폭으로 구분한다. 한 번의 step() 이 최대 10스텝(observe/env.py STEP_RANGE)을
# 전진시키므로 에피소드 **안에서** 생길 수 있는 최대 후퇴 폭도 10이다. 그보다 크게 뒤로
# 가면 새 에피소드로 보고 가드를 리베이스한다.
#
# 이게 없으면 warm 모드에서 ③ 프로세스가 실행 경계를 넘어 살아 있을 때(설계서 §5.0 —
# ③은 초기화하지 않는 것이 기본이다) 두 번째 시나리오가 step 0 에서 시작하는 순간
# **그 실행의 모든 조달이 stale_step 으로 거부된다.**
#
# 남는 빈틈: 직전 에피소드가 10스텝 이내에서 끝났고 다음 에피소드의 첫 조달이 그보다
# 앞선 스텝이면 여전히 거부된다. 그때는 다음 스텝에 다시 부르면 통과한다.
MAX_STEP_REWIND = 10
# 조달 원장. 비용 집계는 ④가 하므로 파일로 남기지 않는다 (설계서 §5.0에 경로 없음).
_procurements: list[dict] = []


# ── 벤더 저장소 ────────────────────────────────────────────────
def _load_vendors() -> list[dict]:
    """data/vendors.json (모델 A + regions). 5곳뿐이라 호출마다 읽는다.

    호출마다 읽는 이유: update_rating 이 파일을 갱신하고, cold 모드에서는 실행 사이에
    bootstrap_vendors.py --force 가 파일을 갈아끼운다. 캐시하면 낡은 rating 으로 채점한다.
    """
    vendors = read_json(paths.VENDORS_JSON)
    if vendors is None:
        raise FileNotFoundError(
            f"{paths.VENDORS_JSON} 이 없다. `python tools/bootstrap_vendors.py` 를 먼저 실행할 것."
        )
    return vendors


def _find_vendor(vendors: list[dict], vendor_id: str) -> Optional[dict]:
    return next((v for v in vendors if v["id"] == vendor_id), None)


def _unknown_vendor(vendors: list[dict], vendor_id: str) -> dict:
    """오류 메시지도 프롬프트의 일부다 — 복구에 필요한 정보를 같이 준다."""
    return {"error": "unknown_vendor", "vendor_id": vendor_id,
            "available": [v["id"] for v in vendors]}


def _check_slice_type(slice_type: str) -> None:
    if slice_type not in SLICE_TYPES:
        raise ValueError(f"unknown slice_type: {slice_type!r}. 가능한 값: {list(SLICE_TYPES)}")


def _check_qos(qos_requirements: dict[str, Any]) -> None:
    """키가 하나도 안 맞으면 전 벤더가 동점이 되어 조용히 무의미해진다. 먼저 막는다."""
    if not any(k in qos_requirements for k in QOS_KEYS):
        raise ValueError(
            f"qos_requirements 에 {list(QOS_KEYS)} 중 아무것도 없다: "
            f"{sorted(qos_requirements)}. 키에 단위를 붙이지 말 것 (latency_ms 아님). "
            f"생략 시 기본값 {QOS_DEFAULTS}."
        )


def _offering_row(vendor: dict, slice_type: str, offering: dict) -> dict:
    return {
        "vendor_id": vendor["id"],
        "name": vendor["name"],
        "slice_type": slice_type,
        "latency": float(offering["latency"]),
        "bandwidth": float(offering["bandwidth"]),
        "reliability": float(offering["reliability"]),
        "cost": float(offering["cost"]),
        "regions": list(vendor.get("regions", [])),
        "rating": float(vendor.get("rating", 3.0)),
    }


# ── 도구 ───────────────────────────────────────────────────────
@mcp.tool(description=TOOL_DESC["list_offerings"])
def list_offerings(slice_type: Optional[str] = None,
                   region: Optional[str] = None) -> list[dict]:
    """벤더 5곳 × 슬라이스 3타입을 평탄화해 돌려준다.

    slice_type / region 이 null 이면 거르지 않는다.
    """
    if slice_type is not None:
        _check_slice_type(slice_type)

    rows = []
    for vendor in _load_vendors():
        if region is not None and region not in vendor.get("regions", []):
            continue
        for offered_type, offering in vendor.get("offerings", {}).items():
            if slice_type is not None and offered_type != slice_type:
                continue
            rows.append(_offering_row(vendor, offered_type, offering))
    return rows


@mcp.tool(description=TOOL_DESC["score_offerings"])
def score_offerings(slice_type: str, qos_requirements: dict) -> list[dict]:
    """점수 내림차순, rank 는 1부터.

    rating 이 총점의 10~20%(URLLC 20%)를 차지한다 — ⑤의 피드백이 update_rating 으로
    들어와 순위를 바꾸는 것이 자기 개선의 증거다.
    """
    _check_slice_type(slice_type)
    _check_qos(qos_requirements)

    scored = []
    for vendor in _load_vendors():
        if slice_type not in vendor.get("offerings", {}):
            continue
        scored.append({
            "vendor_id": vendor["id"],
            "name": vendor["name"],
            "score": round(scoring.score_offering(vendor, slice_type, qos_requirements), 2),
            "rating": float(vendor.get("rating", 3.0)),
            "cost": float(vendor["offerings"][slice_type]["cost"]),
        })

    scored.sort(key=lambda row: row["score"], reverse=True)
    return [{"rank": rank, **row} for rank, row in enumerate(scored, start=1)]


@mcp.tool(description=TOOL_DESC["explain_score"])
def explain_score(vendor_id: str, slice_type: str, qos_requirements: dict) -> dict:
    """기준별 원점수 · 가중치 · 기여분.

    total 은 score_offerings 의 score 와 반드시 일치한다 — 같은 `scoring` 경로를 쓰고
    같은 자리에서 반올림한다. engine.py:819 의 get_score_breakdown() 은 쓰지 않는다 (정정 J).
    """
    _check_slice_type(slice_type)
    _check_qos(qos_requirements)

    vendors = _load_vendors()
    vendor = _find_vendor(vendors, vendor_id)
    if vendor is None:
        return _unknown_vendor(vendors, vendor_id)

    result = scoring.breakdown(vendor, slice_type, qos_requirements)
    return {
        "total": round(result["total"], 2),
        "criteria_scores": {k: round(v, 4) for k, v in result["criteria_scores"].items()},
        "weights": {k: round(v, 4) for k, v in result["weights"].items()},
        "contributions": {k: round(v, 2) for k, v in result["contributions"].items()},
        "explanation": result["explanation"],
    }


@mcp.tool(description=TOOL_DESC["procure"])
def procure(vendor_id: str, slice_type: str, qos_requirements: dict,
            duration_steps: int, current_step: int) -> dict:
    """슬라이스를 조달한다. 예산 제약은 없다 — ④가 비용을 집계해 지표로 보고한다.

    current_step — ③은 ①과 별개 프로세스라 시뮬레이션 시각을 모른다. 에이전트가 넘긴다(W2).
        과거 스텝이면 status="rejected" 로 되돌린다 (순서 실수는 복구 가능한 오류다).

        cost_total      = cost × duration_steps × (MINUTES_PER_STEP / 60)   # W3. 4배 주의
        capacity_gain   = (bandwidth / REFERENCE_BANDWIDTH[slice_type]) × GAIN_SCALE
        expires_at_step = current_step + duration_steps

    반환의 vendor_id 는 W4 — ④에 기록되어야 ⑤가 결과 보고 시 되찾는다.
    capacity_gain 은 에이전트가 ①.add_capacity(amount=...) 에 그대로 넣는다.
    add_capacity 는 반드시 step() 전에 호출해야 조달한 그 스텝이 효과를 본다 (W1).
    """
    global _last_step

    _check_slice_type(slice_type)
    _check_qos(qos_requirements)

    vendors = _load_vendors()
    vendor = _find_vendor(vendors, vendor_id)
    if vendor is None:
        return _unknown_vendor(vendors, vendor_id)

    offering = vendor.get("offerings", {}).get(slice_type)
    if offering is None:
        return {"slice_id": None, "status": "rejected", "vendor_id": vendor_id,
                "cost_total": 0.0, "capacity_gain": 0.0, "expires_at_step": None,
                "reason": f"vendor_does_not_offer: {vendor_id} 에 {slice_type} 오퍼링이 없다"}

    low, high = DURATION_RANGE
    if not low <= duration_steps <= high:
        return {"slice_id": None, "status": "rejected", "vendor_id": vendor_id,
                "cost_total": 0.0, "capacity_gain": 0.0, "expires_at_step": None,
                "reason": f"duration_out_of_range: {duration_steps} not in [{low}, {high}]"}

    # 후퇴 폭이 MAX_STEP_REWIND 이내일 때만 순서 실수로 본다. 그보다 크면 새 에피소드라
    # 판단해 가드를 리베이스한다 (아래 _last_step 대입이 곧 리베이스다).
    rewind = _last_step - int(current_step)
    if 0 < rewind <= MAX_STEP_REWIND:
        return {"slice_id": None, "status": "rejected", "vendor_id": vendor_id,
                "cost_total": 0.0, "capacity_gain": 0.0, "expires_at_step": None,
                "reason": f"stale_step: current_step {current_step} < 직전 조달 {_last_step}"}
    _last_step = current_step

    cost_total = cost_per_step(float(offering["cost"])) * duration_steps
    capacity_gain = (float(offering["bandwidth"]) / REFERENCE_BANDWIDTH[slice_type]) * GAIN_SCALE
    slice_id = (f"slice-{slice_type.lower()}-{current_step:04d}-"
                f"{vendor_id.replace('vendor-', 'v')}")

    record = {
        "slice_id": slice_id,
        "status": "active",
        "vendor_id": vendor_id,
        "cost_total": round(cost_total, 2),
        "capacity_gain": round(capacity_gain, 4),
        "expires_at_step": current_step + duration_steps,
        "reason": None,
    }
    _procurements.append({**record, "slice_type": slice_type, "step": current_step})
    return record


@mcp.tool(description=TOOL_DESC["update_rating"])
def update_rating(vendor_id: str, outcome: dict) -> dict:
    """⑤의 report_outcome 결과를 에이전트가 중계해 호출한다.

        rating ← clip(rating + δ, 1.0, 5.0),   δ = +0.05 (sla_met) / −0.20 (위반)

    위반에 4배 가중 — 초기 레이팅이 4.5~4.9로 좁게 몰려 있어 작은 δ로는 순위가 안 바뀐다.
    0.2 하락 = 총점 0.4~0.8점 하락이라 60~120스텝에서 순위 역전이 관측 가능한 크기다.

    ⑤가 vendors.json 에 직접 쓰지 않는 이유가 이 도구다 — 서버 간 직접 호출 금지.
    """
    vendors = _load_vendors()
    vendor = _find_vendor(vendors, vendor_id)
    if vendor is None:
        return _unknown_vendor(vendors, vendor_id)

    if "sla_met" not in outcome:
        return {"error": "missing_field", "field": "sla_met",
                "expected": {"sla_met": "bool", "decision_id": "str"}}

    up, down = RATING_DELTA
    delta = up if outcome["sla_met"] else down

    before = float(vendor.get("rating", 3.0))
    after = min(5.0, max(1.0, before + delta))
    vendor["rating"] = round(after, 4)
    write_json(paths.VENDORS_JSON, vendors)

    return {
        "vendor_id": vendor_id,
        "rating_before": round(before, 4),
        "rating_after": round(after, 4),
        "delta": round(after - before, 4),   # 상·하한에 걸리면 δ와 다르다
    }


if __name__ == "__main__":
    mcp.run()
