#!/usr/bin/env python3
"""
AI vs Traditional Optimization Comparison Tool

This script runs comparisons between AI-based and traditional
network slicing optimization approaches across different scenarios.
"""

import os
import sys
import argparse
import json
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime

# Add the parent directory to the path to import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the simulator from the interactive demo
from interactive_demo import NetworkSimulator

def run_comparison(scenario, duration=300, save_dir='results'):
    """Run a comparison between AI and traditional optimization
    
    Args:
        scenario (str): Scenario to run
        duration (int): Duration of the simulation in seconds
        save_dir (str): Directory to save results
    
    Returns:
        dict: Comparison results
    """
    print(f"Running comparison for scenario: {scenario}")
    
    # Create simulator
    simulator = NetworkSimulator(scenario, duration)
    
    # Run simulation
    step = 0
    while not simulator.step_simulation():
        step += 1
        if step % 10 == 0:
            print(f"Progress: {simulator.current_time}/{duration} seconds")
    
    # Get results
    metrics = simulator.get_metrics_history()
    
    # Calculate improvement percentages
    improvements = calculate_improvements(metrics)
    
    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    result_file = os.path.join(save_dir, f"{scenario}_results_{timestamp}.json")
    
    os.makedirs(save_dir, exist_ok=True)
    
    with open(result_file, 'w') as f:
        json.dump({
            'scenario': scenario,
            'duration': duration,
            'metrics': metrics,
            'improvements': improvements
        }, f, indent=2)
    
    print(f"Results saved to {result_file}")
    
    # Generate plots
    plot_file = os.path.join(save_dir, f"{scenario}_comparison_{timestamp}.png")
    plot_comparison(metrics, improvements, scenario, plot_file)
    
    return {
        'scenario': scenario,
        'metrics': metrics,
        'improvements': improvements,
        'result_file': result_file,
        'plot_file': plot_file
    }

def calculate_improvements(metrics):
    """Calculate improvement percentages of AI over traditional
    
    Args:
        metrics (dict): Metrics history
    
    Returns:
        dict: Improvement percentages
    """
    improvements = {
        'latency': 0,
        'throughput': 0,
        'resource_utilization': 0,
        'qoe': 0
    }
    
    # Skip if data is insufficient
    if (not metrics['traditional']['latency'] or 
        not metrics['ai']['latency']):
        return improvements
    
    # Calculate average values
    trad_latency = np.mean(metrics['traditional']['latency'])
    ai_latency = np.mean(metrics['ai']['latency'])
    
    trad_throughput = np.mean(metrics['traditional']['throughput'])
    ai_throughput = np.mean(metrics['ai']['throughput'])
    
    trad_utilization = np.mean(metrics['traditional']['resource_utilization'])
    ai_utilization = np.mean(metrics['ai']['resource_utilization'])
    
    trad_qoe = np.mean(metrics['traditional']['qoe'])
    ai_qoe = np.mean(metrics['ai']['qoe'])
    
    # Calculate improvements
    # For latency, lower is better, so improvement is negative percentage
    if trad_latency > 0:
        improvements['latency'] = -100 * (ai_latency - trad_latency) / trad_latency
    
    # For others, higher is better
    if trad_throughput > 0:
        improvements['throughput'] = 100 * (ai_throughput - trad_throughput) / trad_throughput
    
    if trad_utilization > 0:
        improvements['resource_utilization'] = 100 * (ai_utilization - trad_utilization) / trad_utilization
    
    if trad_qoe > 0:
        improvements['qoe'] = 100 * (ai_qoe - trad_qoe) / trad_qoe
    
    return improvements

def plot_comparison(metrics, improvements, scenario, save_path=None):
    """Plot comparison between AI and traditional optimization
    
    Args:
        metrics (dict): Metrics history
        improvements (dict): Improvement percentages
        scenario (str): Scenario name
        save_path (str): Path to save the plot
    """
    plt.figure(figsize=(15, 10))
    
    # Plot metrics over time
    metrics_list = ['latency', 'throughput', 'resource_utilization', 'qoe']
    for i, metric in enumerate(metrics_list):
        plt.subplot(2, 2, i+1)
        
        plt.plot(
            metrics['traditional']['time'],
            metrics['traditional'][metric],
            label='Traditional',
            color='blue'
        )
        
        plt.plot(
            metrics['ai']['time'],
            metrics['ai'][metric],
            label='AI-based',
            color='red'
        )
        
        # Add improvement text
        improvement = improvements[metric]
        color = 'green' if (
            (metric != 'latency' and improvement > 0) or
            (metric == 'latency' and improvement < 0)
        ) else 'red'
        
        if metric == 'latency':
            # For latency, lower is better
            label = f"AI is {abs(improvement):.1f}% {'better' if improvement > 0 else 'worse'}"
        else:
            # For others, higher is better
            label = f"AI is {abs(improvement):.1f}% {'better' if improvement > 0 else 'worse'}"
        
        plt.annotate(
            label,
            xy=(0.5, 0.95),
            xycoords='axes fraction',
            horizontalalignment='center',
            verticalalignment='top',
            fontsize=10,
            color=color
        )
        
        plt.title(f"{metric.replace('_', ' ').title()}")
        plt.xlabel("Time (s)")
        plt.ylabel("Value")
        plt.legend()
        plt.grid(True)
    
    plt.suptitle(f"AI vs Traditional Optimization: {scenario.title()} Scenario", fontsize=16)
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    
    if save_path:
        plt.savefig(save_path)
        print(f"Plot saved to {save_path}")
    
    plt.close()

def run_all_scenarios(duration=300, save_dir='results'):
    """Run comparisons for all scenarios
    
    Args:
        duration (int): Duration of the simulation in seconds
        save_dir (str): Directory to save results
    
    Returns:
        dict: Results for all scenarios
    """
    scenarios = ['baseline', 'dynamic', 'emergency', 'smart_city']
    results = {}
    
    for scenario in scenarios:
        results[scenario] = run_comparison(scenario, duration, save_dir)
    
    # Generate summary plot
    summary_file = os.path.join(save_dir, f"summary_comparison_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
    plot_summary(results, summary_file)
    
    return results

def plot_summary(results, save_path=None):
    """Plot summary of all scenario comparisons
    
    Args:
        results (dict): Results for all scenarios
        save_path (str): Path to save the plot
    """
    plt.figure(figsize=(15, 10))
    
    scenarios = list(results.keys())
    metrics = ['latency', 'throughput', 'resource_utilization', 'qoe']
    
    for i, metric in enumerate(metrics):
        plt.subplot(2, 2, i+1)
        
        # Collect improvement values
        improvements = [results[scenario]['improvements'][metric] for scenario in scenarios]
        
        # For latency, flip the sign for plotting since lower is better but we want positive bars to be good
        if metric == 'latency':
            improvements = [-imp for imp in improvements]
            ylabel = "Improvement (%) - Lower is better for latency"
        else:
            ylabel = "Improvement (%)"
        
        # Create bars
        bars = plt.bar(scenarios, improvements)
        
        # Color bars based on value
        for j, bar in enumerate(bars):
            bar.set_color('green' if improvements[j] > 0 else 'red')
        
        # Add value labels
        for j, v in enumerate(improvements):
            plt.text(
                j,
                v + (5 if v >= 0 else -5),
                f"{v:.1f}%",
                ha='center',
                va='bottom' if v >= 0 else 'top',
                fontsize=10
            )
        
        plt.title(f"{metric.replace('_', ' ').title()} Improvement")
        plt.xlabel("Scenario")
        plt.ylabel(ylabel)
        plt.grid(True, axis='y')
        
        # Make scenario names more readable
        plt.xticks(range(len(scenarios)), [s.title() for s in scenarios])
    
    plt.suptitle("AI vs Traditional Optimization: Summary Across Scenarios", fontsize=16)
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    
    if save_path:
        plt.savefig(save_path)
        print(f"Summary plot saved to {save_path}")
    
    plt.close()

def main():
    """Main function to run the comparison tool"""
    parser = argparse.ArgumentParser(description='AI vs Traditional Optimization Comparison Tool')
    parser.add_argument('--scenario', type=str, default='all',
                       choices=['all', 'baseline', 'dynamic', 'emergency', 'smart_city'],
                       help='Scenario to run (default: all)')
    parser.add_argument('--duration', type=int, default=300,
                       help='Duration of the simulation in seconds (default: 300)')
    parser.add_argument('--save-dir', type=str, default='results',
                       help='Directory to save results (default: results)')
    
    args = parser.parse_args()
    
    if args.scenario == 'all':
        results = run_all_scenarios(args.duration, args.save_dir)
        print("\nSummary of AI improvements across scenarios:")
        for scenario, result in results.items():
            print(f"\n{scenario.title()} scenario:")
            for metric, value in result['improvements'].items():
                if metric == 'latency':
                    # For latency, lower is better
                    print(f"  {metric.title()}: {'Improved' if value > 0 else 'Worsened'} by {abs(value):.2f}%")
                else:
                    # For others, higher is better
                    print(f"  {metric.title()}: {'Improved' if value > 0 else 'Worsened'} by {abs(value):.2f}%")
    else:
        result = run_comparison(args.scenario, args.duration, args.save_dir)
        print("\nAI improvement summary:")
        for metric, value in result['improvements'].items():
            if metric == 'latency':
                # For latency, lower is better
                print(f"  {metric.title()}: {'Improved' if value > 0 else 'Worsened'} by {abs(value):.2f}%")
            else:
                # For others, higher is better
                print(f"  {metric.title()}: {'Improved' if value > 0 else 'Worsened'} by {abs(value):.2f}%")




if __name__ == "__main__":
    main() 