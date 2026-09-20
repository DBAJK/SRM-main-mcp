#!/usr/bin/env python3
"""
URLLC Slice Optimization

This script demonstrates how our model-based approach significantly improves
the QoS for URLLC (Ultra-Reliable Low-Latency Communications) slices,
which are critical for emergency services and require strict QoS guarantees.
"""

import numpy as np
import matplotlib.pyplot as plt
import os
import json

# Create output directory
output_dir = "results/urllc_optimization"
os.makedirs(output_dir, exist_ok=True)

# Simulation parameters
duration = 100
thresholds = {
    "eMBB": 1.5,   # eMBB can handle higher utilization
    "URLLC": 1.2,  # URLLC needs strict guarantees (most critical)
    "mMTC": 1.8    # mMTC can handle very high utilization
}

# Generate traffic pattern with emergency events that impact URLLC
def generate_traffic():
    # Base traffic pattern
    time = np.linspace(0, 2*np.pi, duration)
    base_traffic = 0.5 + 0.3 * np.sin(time)
    
    # Add random variations
    noise = 0.05 * np.random.randn(duration)
    traffic = base_traffic + noise
    
    # Add emergency events (specifically impacting URLLC)
    emergency_events = [
        {"start": 15, "duration": 10, "magnitude": 2.0},  # Major emergency
        {"start": 40, "duration": 5, "magnitude": 1.8},   # Medium emergency
        {"start": 60, "duration": 15, "magnitude": 2.2},  # Critical emergency
        {"start": 85, "duration": 8, "magnitude": 1.5}    # Minor emergency
    ]
    
    # Apply emergency events
    urllc_impact = np.zeros(duration)
    for event in emergency_events:
        start = event["start"]
        end = min(start + event["duration"], duration)
        magnitude = event["magnitude"]
        
        # Ramp up
        for i in range(start, start + 2):
            if i < duration:
                urllc_impact[i] = magnitude * 0.5
        
        # Full impact
        for i in range(start + 2, end - 1):
            if i < duration:
                urllc_impact[i] = magnitude
        
        # Ramp down
        for i in range(end - 1, end + 1):
            if i < duration:
                urllc_impact[i] = magnitude * 0.5
    
    # Create traffic for each slice type
    traffic_embb = traffic.copy()
    traffic_urllc = traffic.copy() + urllc_impact  # URLLC gets emergency impact
    traffic_mmtc = traffic.copy() * 0.8  # mMTC has lower baseline
    
    # Clip to reasonable range
    traffic_embb = np.clip(traffic_embb, 0.1, 2.5)
    traffic_urllc = np.clip(traffic_urllc, 0.1, 3.0)
    traffic_mmtc = np.clip(traffic_mmtc, 0.1, 2.0)
    
    return traffic_embb, traffic_urllc, traffic_mmtc, urllc_impact

# Static allocation is always equal distribution
def static_allocation():
    return np.array([1/3, 1/3, 1/3])

# Model-based allocation that prioritizes URLLC during emergencies
def model_allocation(time_idx, urllc_traffic_history):
    # Default allocation
    allocation = np.array([1/3, 1/3, 1/3])
    
    # If we have enough history, detect trends and emergencies
    if len(urllc_traffic_history) >= 5:
        # Get recent URLLC traffic
        recent_traffic = urllc_traffic_history[-5:]
        current_traffic = recent_traffic[-1]
        
        # Detect emergency (high URLLC traffic)
        if current_traffic > 1.5:
            # High emergency - prioritize URLLC heavily
            allocation = np.array([0.2, 0.6, 0.2])
        elif current_traffic > 1.0:
            # Moderate load - adjust allocation moderately
            allocation = np.array([0.25, 0.5, 0.25])
        
        # Detect rising trend
        if len(urllc_traffic_history) >= 10:
            trend = np.polyfit(range(10), urllc_traffic_history[-10:], 1)[0]
            if trend > 0.1:
                # Proactively increase URLLC allocation
                allocation[1] += 0.1
                allocation[0] -= 0.05
                allocation[2] -= 0.05
                
                # Normalize
                allocation = allocation / np.sum(allocation)
    
    return allocation

# Calculate utilization based on traffic and allocation
def calculate_utilization(traffic, allocation):
    # Calculate utilization - higher allocation means lower utilization
    utilization = traffic / (allocation + 0.01)
    
    # Add small random variations
    noise = 0.05 * np.random.randn()
    utilization += noise
    
    # Clip to reasonable range
    utilization = np.clip(utilization, 0.1, 3.0)
    
    return utilization

# Check for QoS violations
def check_violation(utilization, threshold):
    return utilization > threshold

# Run simulation
print("Generating traffic pattern...")
traffic_embb, traffic_urllc, traffic_mmtc, urllc_impact = generate_traffic()

# Initialize arrays
static_allocations = []
model_allocations = []
static_utilizations = {
    "eMBB": [],
    "URLLC": [],
    "mMTC": []
}
model_utilizations = {
    "eMBB": [],
    "URLLC": [],
    "mMTC": []
}
static_violations = {
    "eMBB": 0,
    "URLLC": 0,
    "mMTC": 0,
    "total": 0
}
model_violations = {
    "eMBB": 0,
    "URLLC": 0,
    "mMTC": 0,
    "total": 0
}

# Run simulation
print("Running simulation...")
for i in range(duration):
    # Get current traffic
    current_embb = traffic_embb[i]
    current_urllc = traffic_urllc[i]
    current_mmtc = traffic_mmtc[i]
    
    # Get allocations
    static_alloc = static_allocation()
    
    # For model allocation, use URLLC traffic history
    urllc_history = traffic_urllc[:i+1].tolist()
    model_alloc = model_allocation(i, urllc_history)
    
    # Calculate utilizations
    static_util_embb = calculate_utilization(current_embb, static_alloc[0])
    static_util_urllc = calculate_utilization(current_urllc, static_alloc[1])
    static_util_mmtc = calculate_utilization(current_mmtc, static_alloc[2])
    
    model_util_embb = calculate_utilization(current_embb, model_alloc[0])
    model_util_urllc = calculate_utilization(current_urllc, model_alloc[1])
    model_util_mmtc = calculate_utilization(current_mmtc, model_alloc[2])
    
    # Check for violations
    if check_violation(static_util_embb, thresholds["eMBB"]):
        static_violations["eMBB"] += 1
        static_violations["total"] += 1
    
    if check_violation(static_util_urllc, thresholds["URLLC"]):
        static_violations["URLLC"] += 1
        static_violations["total"] += 1
    
    if check_violation(static_util_mmtc, thresholds["mMTC"]):
        static_violations["mMTC"] += 1
        static_violations["total"] += 1
    
    if check_violation(model_util_embb, thresholds["eMBB"]):
        model_violations["eMBB"] += 1
        model_violations["total"] += 1
    
    if check_violation(model_util_urllc, thresholds["URLLC"]):
        model_violations["URLLC"] += 1
        model_violations["total"] += 1
    
    if check_violation(model_util_mmtc, thresholds["mMTC"]):
        model_violations["mMTC"] += 1
        model_violations["total"] += 1
    
    # Store results
    static_allocations.append(static_alloc)
    model_allocations.append(model_alloc)
    
    static_utilizations["eMBB"].append(static_util_embb)
    static_utilizations["URLLC"].append(static_util_urllc)
    static_utilizations["mMTC"].append(static_util_mmtc)
    
    model_utilizations["eMBB"].append(model_util_embb)
    model_utilizations["URLLC"].append(model_util_urllc)
    model_utilizations["mMTC"].append(model_util_mmtc)

# Convert to numpy arrays
static_allocations = np.array(static_allocations)
model_allocations = np.array(model_allocations)

for slice_type in ["eMBB", "URLLC", "mMTC"]:
    static_utilizations[slice_type] = np.array(static_utilizations[slice_type])
    model_utilizations[slice_type] = np.array(model_utilizations[slice_type])

# Calculate improvement
if static_violations["total"] > 0:
    total_improvement = ((static_violations["total"] - model_violations["total"]) / 
                        static_violations["total"] * 100)
else:
    total_improvement = 0

# Calculate URLLC-specific improvement
if static_violations["URLLC"] > 0:
    urllc_improvement = ((static_violations["URLLC"] - model_violations["URLLC"]) / 
                        static_violations["URLLC"] * 100)
else:
    urllc_improvement = 0

# Save results
results = {
    "static_violations": static_violations,
    "model_violations": model_violations,
    "total_improvement": total_improvement,
    "urllc_improvement": urllc_improvement
}

with open(os.path.join(output_dir, "urllc_optimization.json"), "w") as f:
    json.dump(results, f, indent=2)

print(f"Static violations: {static_violations['total']} (URLLC: {static_violations['URLLC']})")
print(f"Model violations: {model_violations['total']} (URLLC: {model_violations['URLLC']})")
print(f"Total improvement: {total_improvement:.2f}%")
print(f"URLLC improvement: {urllc_improvement:.2f}%")

# Visualize results
print("Generating visualizations...")
time = np.arange(duration)

# Create figure for URLLC focus
plt.figure(figsize=(15, 12))

# Plot URLLC traffic and emergency impact
plt.subplot(4, 1, 1)
plt.plot(time, traffic_urllc, "r-", label="URLLC Traffic")
plt.plot(time, urllc_impact, "r--", alpha=0.5, label="Emergency Impact")
plt.title("URLLC Traffic with Emergency Events")
plt.ylabel("Traffic Load")
plt.legend()
plt.grid(True)

# Plot allocations
plt.subplot(4, 1, 2)
plt.plot(time, static_allocations[:, 1], "b--", label="Static URLLC Allocation")
plt.plot(time, model_allocations[:, 1], "r-", label="Model URLLC Allocation")
plt.title("URLLC Slice Allocation Comparison")
plt.ylabel("Allocation")
plt.legend()
plt.grid(True)

# Plot utilizations
plt.subplot(4, 1, 3)
plt.plot(time, static_utilizations["URLLC"], "b-", label="Static URLLC Utilization")
plt.plot(time, model_utilizations["URLLC"], "r-", label="Model URLLC Utilization")
plt.axhline(y=thresholds["URLLC"], color="k", linestyle=":", label="QoS Threshold")
plt.title("URLLC Slice Utilization Comparison")
plt.ylabel("Utilization")
plt.legend()
plt.grid(True)

# Plot cumulative violations
static_cumulative = np.cumsum(np.array([check_violation(u, thresholds["URLLC"]) for u in static_utilizations["URLLC"]]))
model_cumulative = np.cumsum(np.array([check_violation(u, thresholds["URLLC"]) for u in model_utilizations["URLLC"]]))

plt.subplot(4, 1, 4)
plt.plot(time, static_cumulative, "b-", label="Static URLLC Violations")
plt.plot(time, model_cumulative, "r-", label="Model URLLC Violations")
plt.title("Cumulative URLLC QoS Violations")
plt.xlabel("Time Step")
plt.ylabel("Violations")
plt.legend()
plt.grid(True)

plt.tight_layout()
plt.savefig(os.path.join(output_dir, "urllc_comparison.png"))
plt.close()

# Create QoS violations bar chart
plt.figure(figsize=(12, 8))

# Get violation data
slice_types = ["eMBB", "URLLC", "mMTC", "total"]
static_data = [static_violations[s] for s in slice_types]
model_data = [model_violations[s] for s in slice_types]

x = np.arange(len(slice_types))
width = 0.35

fig, ax = plt.subplots(figsize=(12, 8))
rects1 = ax.bar(x - width/2, static_data, width, label="Static Allocation")
rects2 = ax.bar(x + width/2, model_data, width, label="Model-based Allocation")

ax.set_ylabel("Number of Violations")
ax.set_title("QoS Violations by Allocation Method")
ax.set_xticks(x)
ax.set_xticklabels([s.upper() if s == "total" else s for s in slice_types])
ax.legend()

# Add value labels
def autolabel(rects):
    for rect in rects:
        height = rect.get_height()
        ax.annotate(f"{height}",
                    xy=(rect.get_x() + rect.get_width() / 2, height),
                    xytext=(0, 3),
                    textcoords="offset points",
                    ha="center", va="bottom")

autolabel(rects1)
autolabel(rects2)

# Add improvement percentage
plt.figtext(0.5, 0.01, 
          f"URLLC improvement: {urllc_improvement:.2f}% reduction in QoS violations\n"
          f"Total improvement: {total_improvement:.2f}% reduction in QoS violations", 
          ha="center", fontsize=12, bbox={"facecolor":"orange", "alpha":0.5, "pad":5})

plt.tight_layout(rect=[0, 0.05, 1, 1])
plt.savefig(os.path.join(output_dir, "qos_violations.png"))
plt.close()

print(f"Results saved to {output_dir}")
print("Done!") 