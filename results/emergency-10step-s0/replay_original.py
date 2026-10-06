"""원본 ml_orchestrator_demo.py 의 update_allocation_rule_based 를 실행 기록의 관측에 그대로 돌려 대조."""
import sys, json, types
sys.path.insert(0, r"C:\aiagent\SRM-main-mcp")
import numpy as np
try:
    import matplotlib.pyplot  # noqa
except ImportError:
    for m in ("matplotlib", "matplotlib.pyplot", "matplotlib.gridspec"):
        sys.modules[m] = types.ModuleType(m)
import ml_orchestrator_demo as orig
K = ("embb", "urllc", "mmtc")
book = json.load(open(r"runs/original-emergency-s0/decisions.json", encoding="utf-8"))
recs = sorted([r for r in book["decisions"] if r["kind"] == "decision"], key=lambda r: r["step"])
obs = {r["step"]: r["observation"] for r in recs}
worst = 0
for r in recs:
    t = r["step"]; o = obs[t]
    m = orig.MLOrchestrator.__new__(orig.MLOrchestrator)
    m.is_emergency, m.is_special_event, m.is_iot_surge = True, False, False
    m.allocation = np.array([o["allocation"][k] for k in K])
    m.utilization = np.array([o["utilization"][k] for k in K])
    m.thresholds = np.array([o["thresholds"][k] for k in K])
    out = m.update_allocation_rule_based()
    ours = np.array([r["outcome"]["applied_allocation"][k] for k in K])
    d = float(np.abs(out - ours).max()); worst = max(worst, d)
    print(f"s{t}  원본 {np.round(out,4)}  우리 original {np.round(ours,4)}  차이 {d:.1e}")
print("최대 차이", worst)
