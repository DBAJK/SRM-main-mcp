"""심판 — 스텝이 끝난 뒤 절차 위반을 판정한다. **막지 않는다.**

고정 루프(`agent/loop.py`)에서는 파이썬이 순서를 보장하므로 위반이 정의상 0이다.
오케스트레이터에서는 LLM 이 순서를 정하므로 위반이 **날 수 있고**, 그 빈도가
"LLM 이 절차를 얼마나 스스로 지키는가"라는 측정치가 된다. 그래서 게이트웨이는
거부하지 않고 심판은 사후에 세기만 한다.

규칙은 `claude/spec/tools.md` 의 "부작용 있는 도구 8개는 한 스텝에 정해진 횟수만"
과 `claude/flow/loop.md` §3.1 의 시간 규약에서 그대로 가져왔다. 각 규칙에 붙은
severity 는 채점 데이터에 미치는 영향이다.

    error  그 스텝의 채점이 불가능하거나 왜곡된다 (기록 없음 · 채점 없음 · 시간 건너뜀)
    warn   결과는 남지만 의미가 어긋난다 (조달이 다음 스텝에 반영 · vendor_id 유실)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Verdict:
    step: int
    calls: int
    violations: list[dict] = field(default_factory=list)

    # 스텝 요약에 쓰는 사실. 호출 기록에서 읽은 것이라 LLM 의 자기 보고와 다를 수 있다.
    escalated: bool = False
    procured: bool = False
    sla_met: Optional[bool] = None
    decision_id: Optional[str] = None
    episode_done: bool = False
    tools_in_order: list[str] = field(default_factory=list)

    # 완료되지 않은 호출 — 서버가 값으로 거부(flow/errors.md) 했거나 예외를 냈거나
    # 상한에 걸린 것. 순서·횟수 판정에서 빼고, 그 수 자체를 "되풀이 비용"으로 센다.
    failed_calls: int = 0

    @property
    def errors(self) -> int:
        return sum(1 for v in self.violations if v["severity"] == "error")

    @property
    def warns(self) -> int:
        return sum(1 for v in self.violations if v["severity"] == "warn")

    def as_row(self) -> dict:
        return {
            "step": self.step,
            "calls": self.calls,
            "failed_calls": self.failed_calls,
            "escalated": self.escalated,
            "procured": self.procured,
            "sla_met": self.sla_met,
            "decision_id": self.decision_id,
            "violations": self.violations,
            "order": self.tools_in_order,
        }


def judge(step: int, calls: list[dict], budget_hit: bool = False) -> Verdict:
    """한 스텝의 호출 기록(게이트웨이 `CallLog.for_step`)을 판정한다."""
    # 완료된 호출만 본다. ④가 missing_confidence 로 거부한 record_decision 을 세면
    # 재시도가 duplicate_decision_record 로 잡힌다 (2026-09-23 실측).
    ok_calls = [c for c in calls
                if c.get("ok") and not c.get("refused") and not c.get("value_error")]
    order = [c["tool"] for c in ok_calls]
    v = Verdict(step=step, calls=len(calls), tools_in_order=order,
                failed_calls=len(calls) - len(ok_calls))

    idx = {name: [i for i, t in enumerate(order) if t == name] for name in set(order)}
    first = lambda name: idx.get(name, [None])[0]          # noqa: E731
    count = lambda name: len(idx.get(name, []))            # noqa: E731

    def flag(code: str, severity: str, detail: str) -> None:
        v.violations.append({"code": code, "severity": severity, "detail": detail})

    # ── 사실 추출 ────────────────────────────────────────────────────
    for c in ok_calls:
        if c["tool"] == "record_escalation":
            v.escalated = True
        if c["tool"] in ("record_decision", "record_escalation") and c.get("decision_id"):
            v.decision_id = c["decision_id"]
        if c["tool"] == "procure" and c.get("vendor_id"):
            v.procured = True
        if c["tool"] == "report_outcome" and c.get("sla_met") is not None:
            v.sla_met = bool(c["sla_met"])
        if c["tool"] == "step" and c.get("episode_done"):
            v.episode_done = True

    # ── 관측 ─────────────────────────────────────────────────────────
    if count("get_observation") == 0:
        flag("no_observation", "warn", "관측 없이 판단했다")

    # ── 기록: decision 또는 escalation 정확히 하나 ────────────────────
    records = count("record_decision") + count("record_escalation")
    if records == 0:
        flag("no_decision_record", "error", "④에 판단이 남지 않았다 — 이 스텝은 채점되지 않는다")
    elif records > 1:
        flag("duplicate_decision_record", "error",
             f"record_decision {count('record_decision')} · record_escalation "
             f"{count('record_escalation')} — 한 스텝에 결정 레코드가 둘 이상")

    # ── 실행 · 전진 · 채점 ───────────────────────────────────────────
    if count("apply_allocation") == 0:
        flag("no_apply", "error", "배분을 적용하지 않았다")
    elif count("apply_allocation") > 1:
        flag("multiple_apply", "warn", f"apply_allocation {count('apply_allocation')}회")

    if count("step") == 0:
        flag("no_step", "error", "시뮬레이션을 전진시키지 않았다 — 다음 스텝 관측이 같다")
    elif count("step") > 1:
        flag("multiple_step", "error",
             f"step {count('step')}회 — 판단 없이 시간이 흘렀다")

    if count("report_outcome") == 0:
        flag("no_report", "error", "⑤에 결과를 보고하지 않았다 — 신뢰도가 갱신되지 않는다")

    # ── 순서 ─────────────────────────────────────────────────────────
    i_rec = min([i for n in ("record_decision", "record_escalation") for i in idx.get(n, [])],
                default=None)
    i_apply, i_step, i_report = first("apply_allocation"), first("step"), first("report_outcome")

    if i_step is not None and i_report is not None and i_report < i_step:
        flag("report_before_step", "error",
             "report_outcome 이 step 앞이다 — 직전 관측으로 채점됐다 (premature)")
    if i_rec is not None and i_apply is not None and i_rec > i_apply:
        flag("record_after_apply", "warn",
             "기록이 적용 뒤다 — 실행 실패 사례가 장부에서 사라진다")
    if i_apply is not None and i_step is not None and i_apply > i_step:
        flag("apply_after_step", "error",
             "배분 적용이 step 뒤다 — 이 스텝의 배분이 다음 스텝에 적용됐다")
    for i in idx.get("add_capacity", []):
        if i_step is not None and i > i_step:
            flag("add_capacity_after_step", "warn",
                 "조달 용량이 step 뒤에 들어갔다 — 이 스텝은 효과를 못 본다")
    for i in idx.get("procure", []):
        if i_rec is not None and i > i_rec:
            flag("procure_after_record", "warn",
                 "조달이 기록 뒤다 — 레코드에 vendor_id 가 없어 ⑤→③ 되먹임이 끊긴다")

    # ── 상한 ─────────────────────────────────────────────────────────
    if budget_hit:
        flag("call_budget_exceeded", "warn", "스텝당 호출 상한에 닿아 뒤 호출이 거부됐다")

    return v


class RefereeLog:
    """판정을 `referee.jsonl` 에 누적하고 합계를 낸다."""

    def __init__(self, path: Path):
        self._fh = open(path, "a", encoding="utf-8")
        self.verdicts: list[Verdict] = []

    def add(self, v: Verdict) -> Verdict:
        self.verdicts.append(v)
        self._fh.write(json.dumps(v.as_row(), ensure_ascii=False) + "\n")
        self._fh.flush()
        return v

    def summary(self) -> dict:
        n = len(self.verdicts)
        codes: dict[str, int] = {}
        for v in self.verdicts:
            for x in v.violations:
                codes[x["code"]] = codes.get(x["code"], 0) + 1
        clean = sum(1 for v in self.verdicts if not v.violations)
        return {
            "steps": n,
            "clean_steps": clean,
            "procedure_adherence": round(clean / n, 3) if n else None,
            "error_steps": sum(1 for v in self.verdicts if v.errors),
            "violations_by_code": dict(sorted(codes.items(), key=lambda kv: -kv[1])),
            "mean_calls_per_step": round(sum(v.calls for v in self.verdicts) / n, 1) if n else None,
            "mean_failed_calls_per_step":
                round(sum(v.failed_calls for v in self.verdicts) / n, 2) if n else None,
        }

    def close(self) -> None:
        try:
            self._fh.close()
        except OSError:
            pass
