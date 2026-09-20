#!/usr/bin/env python3
"""
Simple Network Slicing Demo

This script demonstrates the difference between baseline and enhanced
network slicing models using pre-generated data.
"""

import os
import numpy as np
import matplotlib.pyplot as plt
import tensorflow as tf
import argparse
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def generate_scenario_data(scenario, duration=100):
    """Generate synthetic data for the selected scenario
    
    Args:
        scenario (str): Scenario type
        duration (int): Duration in steps
        
    Returns:
        tuple: (traffic, utilization)
    """
    # Initialize parameters based on scenario
    if scenario == 'baseline':
        volatility = 0.1
        emergency_prob = 0.0
    elif scenario == 'dynamic':
        volatility = 0.3
        emergency_prob = 0.05
    elif scenario == 'emergency':
        volatility = 0.2
        emergency_prob = 0.8
    elif scenario == 'smart_city':
        volatility = 0.15
        emergency_prob = 0.0
    else:  # mixed
        volatility = 0.2
        emergency_prob = 0.1
    
    # Generate traffic pattern
    traffic = []
    time_of_day = np.random.uniform(0, 1)
    
    for i in range(duration):
        # Update time
        time_of_day = (time_of_day + 0.01) % 1.0
        
        # Generate traffic pattern
        if scenario == 'emergency':
            # High baseline with emergency spikes
            traffic_load = 0.7 + 0.2 * np.sin(time_of_day * 2 * np.pi) + volatility * np.random.randn()
            
            # Emergency events
            if np.random.random() < emergency_prob:
                traffic_load += np.random.uniform(0.5, 1.0)
        else:
            # Regular daily pattern
            time_factor = np.sin(time_of_day * 2 * np.pi) * 0.3 + 0.5
            traffic_load = 0.5 + time_factor + volatility * np.random.randn()
        
        # Clip traffic load
        traffic_load = np.clip(traffic_load, 0.1, 2.0)
        traffic.append(traffic_load)
    
    # Generate slice utilization based on traffic
    utilization = []
    for t in traffic:
        # Different utilization patterns for different slices
        embb_util = 0.6 * t + 0.1 * np.random.randn()  # eMBB follows traffic closely
        urllc_util = 0.4 * t + 0.3 * np.random.randn()  # URLLC less dependent on traffic
        mmtc_util = 0.3 * t + 0.2 * np.sin(time_of_day * 2 * np.pi) + 0.1 * np.random.randn()  # mMTC has daily pattern
        
        # Clip utilization
        embb_util = np.clip(embb_util, 0.1, 2.0)
        urllc_util = np.clip(urllc_util, 0.1, 2.0)
        mmtc_util = np.clip(mmtc_util, 0.1, 2.0)
        
        utilization.append([embb_util, urllc_util, mmtc_util])
    
    return np.array(traffic), np.array(utilization)

def generate_baseline_allocation(traffic, utilization):
    """Generate baseline slice allocation
    
    This simulates a simple reactive allocation strategy
    
    Args:
        traffic (numpy.ndarray): Traffic pattern
        utilization (numpy.ndarray): Slice utilization
        
    Returns:
        numpy.ndarray: Baseline allocation
    """
    allocations = []
    
    for i in range(len(traffic)):
        # Simple allocation based on current utilization
        total_util = np.sum(utilization[i])
        if total_util > 0:
            allocation = utilization[i] / total_util
        else:
            allocation = np.array([1/3, 1/3, 1/3])
        
        # Ensure allocation sums to 1
        allocation = allocation / np.sum(allocation)
        allocations.append(allocation)
    
    return np.array(allocations)

def generate_enhanced_allocation(traffic, utilization):
    """Generate enhanced slice allocation
    
    This simulates a proactive allocation strategy with multi-step prediction
    
    Args:
        traffic (numpy.ndarray): Traffic pattern
        utilization (numpy.ndarray): Slice utilization
        
    Returns:
        numpy.ndarray: Enhanced allocation
    """
    allocations = []
    
    # Look-ahead window
    window = 5
    
    # Memory of recent traffic trends
    trend_memory = []
    trend_memory_size = 3
    
    # Thresholds for QoS violations
    thresholds = {
        'embb': 1.5,  # eMBB threshold
        'urllc': 1.2,  # URLLC threshold
        'mmtc': 1.8   # mMTC threshold
    }
    
    for i in range(len(traffic)):
        # For enhanced allocation, we look ahead to anticipate future needs
        future_idx = min(i + window, len(traffic) - 1)
        future_traffic = traffic[future_idx]
        current_util = utilization[i]
        
        # Calculate traffic trend
        if i > 0:
            traffic_trend = traffic[i] - traffic[i-1]
            trend_memory.append(traffic_trend)
            if len(trend_memory) > trend_memory_size:
                trend_memory.pop(0)
        else:
            traffic_trend = 0
            trend_memory = [0]
        
        # Calculate average trend
        avg_trend = sum(trend_memory) / len(trend_memory)
        
        # Predict future utilization based on trend
        predicted_util = current_util.copy()
        for j in range(3):  # For each slice
            predicted_util[j] += avg_trend * window * 0.5  # Assume half of traffic trend affects utilization
        
        # Check for potential QoS violations
        potential_violations = [
            predicted_util[0] > thresholds['embb'],
            predicted_util[1] > thresholds['urllc'],
            predicted_util[2] > thresholds['mmtc']
        ]
        
        # Adjust allocation based on predictions and potential violations
        if any(potential_violations):
            # Proactive allocation to prevent violations
            if potential_violations[0]:  # eMBB violation
                allocation = np.array([0.5, 0.3, 0.2])
            elif potential_violations[1]:  # URLLC violation (higher priority)
                allocation = np.array([0.2, 0.6, 0.2])
            elif potential_violations[2]:  # mMTC violation
                allocation = np.array([0.3, 0.3, 0.4])
        else:
            # No violations predicted, allocate based on trend
            if avg_trend > 0.05:  # Traffic increasing trend
                # Prepare for higher demand, prioritize URLLC for responsiveness
                allocation = np.array([0.3, 0.5, 0.2])
            elif avg_trend < -0.05:  # Traffic decreasing trend
                # Balance allocation as load reduces
                allocation = np.array([0.4, 0.3, 0.3])
            else:  # Stable traffic
                # Allocate based on current utilization with smoothing
                total_util = np.sum(current_util)
                if total_util > 0:
                    base_allocation = current_util / total_util
                else:
                    base_allocation = np.array([1/3, 1/3, 1/3])
                
                # Apply smoothing
                allocation = 0.7 * base_allocation + 0.3 * np.array([1/3, 1/3, 1/3])
        
        # Apply additional adjustments based on specific utilization patterns
        for j in range(3):
            if current_util[j] > 0.9 * thresholds[list(thresholds.keys())[j]]:
                # Approaching threshold, increase allocation for this slice
                allocation[j] += 0.1
        
        # Ensure allocation sums to 1
        allocation = allocation / np.sum(allocation)
        allocations.append(allocation)
    
    return np.array(allocations)

def visualize_results(traffic, utilization, baseline_allocation, enhanced_allocation, scenario, output_dir):
    """Visualize simulation results
    
    Args:
        traffic (numpy.ndarray): Traffic pattern
        utilization (numpy.ndarray): Slice utilization
        baseline_allocation (numpy.ndarray): Baseline allocation
        enhanced_allocation (numpy.ndarray): Enhanced allocation
        scenario (str): Scenario type
        output_dir (str): Output directory
    """
    # Create figure
    plt.figure(figsize=(15, 10))
    
    # Plot traffic
    plt.subplot(3, 1, 1)
    plt.plot(traffic, 'k-', label='Traffic Load')
    plt.title(f'Network Traffic - {scenario.capitalize()} Scenario')
    plt.ylabel('Load')
    plt.legend()
    plt.grid(True)
    
    # Plot slice allocations
    plt.subplot(3, 1, 2)
    
    # Baseline allocations
    plt.plot(baseline_allocation[:, 0], 'b--', alpha=0.7, label='Baseline eMBB')
    plt.plot(baseline_allocation[:, 1], 'r--', alpha=0.7, label='Baseline URLLC')
    plt.plot(baseline_allocation[:, 2], 'g--', alpha=0.7, label='Baseline mMTC')
    
    # Enhanced allocations
    plt.plot(enhanced_allocation[:, 0], 'b-', label='Enhanced eMBB')
    plt.plot(enhanced_allocation[:, 1], 'r-', label='Enhanced URLLC')
    plt.plot(enhanced_allocation[:, 2], 'g-', label='Enhanced mMTC')
    
    plt.title('Slice Allocation Comparison')
    plt.ylabel('Allocation Ratio')
    plt.legend()
    plt.grid(True)
    
    # Plot utilization
    plt.subplot(3, 1, 3)
    plt.plot(utilization[:, 0], 'b-', label='eMBB Utilization')
    plt.plot(utilization[:, 1], 'r-', label='URLLC Utilization')
    plt.plot(utilization[:, 2], 'g-', label='mMTC Utilization')
    
    # Add threshold lines
    plt.axhline(y=1.5, color='b', linestyle=':', label='eMBB QoS Threshold')
    plt.axhline(y=1.2, color='r', linestyle=':', label='URLLC QoS Threshold')
    plt.axhline(y=1.8, color='g', linestyle=':', label='mMTC QoS Threshold')
    
    plt.title('Slice Utilization')
    plt.xlabel('Time Step')
    plt.ylabel('Utilization')
    plt.legend()
    plt.grid(True)
    
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, f"{scenario}_comparison.png"))
    plt.show()

def calculate_qos_violations(utilization, allocation):
    """Calculate QoS violations
    
    Args:
        utilization (numpy.ndarray): Slice utilization
        allocation (numpy.ndarray): Slice allocation
        
    Returns:
        dict: QoS violations
    """
    # QoS thresholds
    thresholds = {
        'embb': 1.5,  # eMBB threshold
        'urllc': 1.2,  # URLLC threshold
        'mmtc': 1.8   # mMTC threshold
    }
    
    # Count violations
    violations = {
        'embb': np.sum(utilization[:, 0] > thresholds['embb']),
        'urllc': np.sum(utilization[:, 1] > thresholds['urllc']),
        'mmtc': np.sum(utilization[:, 2] > thresholds['mmtc'])
    }
    
    # Calculate total violations
    violations['total'] = violations['embb'] + violations['urllc'] + violations['mmtc']
    
    # Calculate violation rates
    duration = len(utilization)
    violations['embb_rate'] = violations['embb'] / duration
    violations['urllc_rate'] = violations['urllc'] / duration
    violations['mmtc_rate'] = violations['mmtc'] / duration
    violations['total_rate'] = violations['total'] / duration
    
    return violations

def run_demo(args):
    """Run the simple demo
    
    Args:
        args: Command-line arguments
    """
    logger.info(f"Starting simple demo with {args.scenario} scenario")
    
    # Create output directory
    os.makedirs(args.output_dir, exist_ok=True)
    
    # Generate scenario data
    traffic, utilization = generate_scenario_data(args.scenario, args.duration)
    
    # Generate baseline allocation
    baseline_allocation = generate_baseline_allocation(traffic, utilization)
    
    # Generate enhanced allocation
    enhanced_allocation = generate_enhanced_allocation(traffic, utilization)
    
    # Calculate QoS violations
    baseline_violations = calculate_qos_violations(utilization, baseline_allocation)
    enhanced_violations = calculate_qos_violations(utilization, enhanced_allocation)
    
    # Print results
    logger.info("QoS Violations Comparison:")
    logger.info(f"Baseline - Total: {baseline_violations['total']}, eMBB: {baseline_violations['embb']}, URLLC: {baseline_violations['urllc']}, mMTC: {baseline_violations['mmtc']}")
    logger.info(f"Enhanced - Total: {enhanced_violations['total']}, eMBB: {enhanced_violations['embb']}, URLLC: {enhanced_violations['urllc']}, mMTC: {enhanced_violations['mmtc']}")
    
    # Calculate improvement
    if baseline_violations['total'] > 0:
        improvement = (baseline_violations['total'] - enhanced_violations['total']) / baseline_violations['total'] * 100
        logger.info(f"QoS Improvement: {improvement:.2f}%")
    
    # Visualize results
    visualize_results(traffic, utilization, baseline_allocation, enhanced_allocation, args.scenario, args.output_dir)
    
    logger.info("Demo completed")

def parse_args():
    """Parse command-line arguments"""
    parser = argparse.ArgumentParser(description='Simple Network Slicing Demo')
    parser.add_argument('--scenario', type=str, default='emergency',
                        choices=['baseline', 'dynamic', 'emergency', 'smart_city', 'mixed'],
                        help='Traffic scenario type')
    parser.add_argument('--duration', type=int, default=100,
                        help='Simulation duration in steps')
    parser.add_argument('--output_dir', type=str, default='results/simple_demo',
                        help='Output directory for results')
    
    return parser.parse_args()

if __name__ == '__main__':
    # Parse arguments
    args = parse_args()
    
    # Run demo
    run_demo(args) 