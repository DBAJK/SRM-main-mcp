#!/usr/bin/env python3
"""
Run Network Slicing Efficiency Comparison

This script runs the efficiency comparison across multiple scenarios
and generates a summary report.
"""

import os
import sys
import argparse
import json
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime
import logging

# Import the comparison class
from compare_slicing_efficiency import SlicingEfficiencyComparison

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def run_all_scenarios(args):
    """Run efficiency comparison for all scenarios
    
    Args:
        args: Command-line arguments
    
    Returns:
        dict: Results for all scenarios
    """
    scenarios = ['baseline', 'dynamic', 'emergency', 'smart_city']
    results = {}
    
    for scenario in scenarios:
        logger.info(f"Running comparison for {scenario} scenario")
        
        # Update scenario in args
        args.scenario = scenario
        
        # Create scenario output directory
        scenario_dir = os.path.join(args.output_dir, scenario)
        os.makedirs(scenario_dir, exist_ok=True)
        
        # Update output directory in args
        args.output_dir = scenario_dir
        
        # Run comparison
        comparison = SlicingEfficiencyComparison(args)
        comparison.run()
        
        # Load results
        result_file = os.path.join(scenario_dir, f"{scenario}_efficiency_metrics.json")
        with open(result_file, 'r') as f:
            results[scenario] = json.load(f)
        
        logger.info(f"Completed {scenario} scenario")
    
    return results

def generate_summary_report(results, output_dir):
    """Generate summary report for all scenarios
    
    Args:
        results (dict): Results for all scenarios
        output_dir (str): Output directory
    """
    logger.info("Generating summary report")
    
    # Extract data for plotting
    scenarios = list(results.keys())
    
    # QoS violations
    static_violations = [results[s]['qos_violations']['static']['total'] for s in scenarios]
    reactive_violations = [results[s]['qos_violations']['reactive']['total'] for s in scenarios]
    enhanced_violations = [results[s]['qos_violations']['enhanced']['total'] for s in scenarios]
    
    # Improvements
    reactive_vs_static = [results[s]['improvements']['reactive_vs_static'] for s in scenarios]
    enhanced_vs_static = [results[s]['improvements']['enhanced_vs_static'] for s in scenarios]
    enhanced_vs_reactive = [results[s]['improvements']['enhanced_vs_reactive'] for s in scenarios]
    
    # Create QoS violations plot
    plt.figure(figsize=(15, 10))
    
    # Plot QoS violations
    plt.subplot(2, 1, 1)
    x = np.arange(len(scenarios))
    width = 0.25
    
    plt.bar(x - width, static_violations, width, label='Static Allocation')
    plt.bar(x, reactive_violations, width, label='Reactive Allocation')
    plt.bar(x + width, enhanced_violations, width, label='Enhanced Model')
    
    plt.xlabel('Scenario')
    plt.ylabel('Number of QoS Violations')
    plt.title('QoS Violations by Scenario and Allocation Method')
    plt.xticks(x, [s.capitalize() for s in scenarios])
    plt.legend()
    plt.grid(True, axis='y')
    
    # Add value labels
    for i, v in enumerate(static_violations):
        plt.text(i - width, v + 0.5, str(v), ha='center')
    for i, v in enumerate(reactive_violations):
        plt.text(i, v + 0.5, str(v), ha='center')
    for i, v in enumerate(enhanced_violations):
        plt.text(i + width, v + 0.5, str(v), ha='center')
    
    # Plot improvements
    plt.subplot(2, 1, 2)
    plt.bar(x - width, reactive_vs_static, width, label='Reactive vs Static')
    plt.bar(x, enhanced_vs_static, width, label='Enhanced vs Static')
    plt.bar(x + width, enhanced_vs_reactive, width, label='Enhanced vs Reactive')
    
    plt.xlabel('Scenario')
    plt.ylabel('Improvement (%)')
    plt.title('Improvement Percentages by Scenario')
    plt.xticks(x, [s.capitalize() for s in scenarios])
    plt.legend()
    plt.grid(True, axis='y')
    
    # Add value labels
    for i, v in enumerate(reactive_vs_static):
        plt.text(i - width, v + 1, f"{v:.1f}%", ha='center')
    for i, v in enumerate(enhanced_vs_static):
        plt.text(i, v + 1, f"{v:.1f}%", ha='center')
    for i, v in enumerate(enhanced_vs_reactive):
        plt.text(i + width, v + 1, f"{v:.1f}%", ha='center')
    
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, "summary_comparison.png"))
    plt.close()
    
    # Create summary table
    with open(os.path.join(output_dir, "summary_report.md"), 'w') as f:
        f.write("# Network Slicing Efficiency Comparison Summary\n\n")
        f.write(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        f.write("## QoS Violations by Scenario\n\n")
        f.write("| Scenario | Static Allocation | Reactive Allocation | Enhanced Model | Improvement (Enhanced vs Static) |\n")
        f.write("|----------|------------------|---------------------|----------------|----------------------------------|\n")
        
        for scenario in scenarios:
            static = results[scenario]['qos_violations']['static']['total']
            reactive = results[scenario]['qos_violations']['reactive']['total']
            enhanced = results[scenario]['qos_violations']['enhanced']['total']
            improvement = results[scenario]['improvements']['enhanced_vs_static']
            
            f.write(f"| {scenario.capitalize()} | {static} | {reactive} | {enhanced} | {improvement:.2f}% |\n")
        
        # Calculate averages
        avg_static = sum(static_violations) / len(static_violations)
        avg_reactive = sum(reactive_violations) / len(reactive_violations)
        avg_enhanced = sum(enhanced_violations) / len(enhanced_violations)
        avg_improvement = sum(enhanced_vs_static) / len(enhanced_vs_static)
        
        f.write(f"| **Average** | {avg_static:.1f} | {avg_reactive:.1f} | {avg_enhanced:.1f} | {avg_improvement:.2f}% |\n\n")
        
        f.write("## Detailed Improvement Percentages\n\n")
        f.write("| Scenario | Reactive vs Static | Enhanced vs Static | Enhanced vs Reactive |\n")
        f.write("|----------|---------------------|---------------------|---------------------|\n")
        
        for scenario in scenarios:
            r_vs_s = results[scenario]['improvements']['reactive_vs_static']
            e_vs_s = results[scenario]['improvements']['enhanced_vs_static']
            e_vs_r = results[scenario]['improvements']['enhanced_vs_reactive']
            
            f.write(f"| {scenario.capitalize()} | {r_vs_s:.2f}% | {e_vs_s:.2f}% | {e_vs_r:.2f}% |\n")
        
        # Calculate averages
        avg_r_vs_s = sum(reactive_vs_static) / len(reactive_vs_static)
        avg_e_vs_s = sum(enhanced_vs_static) / len(enhanced_vs_static)
        avg_e_vs_r = sum(enhanced_vs_reactive) / len(enhanced_vs_reactive)
        
        f.write(f"| **Average** | {avg_r_vs_s:.2f}% | {avg_e_vs_s:.2f}% | {avg_e_vs_r:.2f}% |\n\n")
        
        # Add conclusion
        f.write("## Conclusion\n\n")
        f.write(f"The enhanced model-based approach shows significant improvement over both static and reactive allocation methods:\n\n")
        f.write(f"- **{avg_e_vs_s:.2f}%** average reduction in QoS violations compared to static allocation\n")
        f.write(f"- **{avg_e_vs_r:.2f}%** average reduction in QoS violations compared to reactive allocation\n\n")
        f.write("This demonstrates the efficiency of our model-based approach in optimizing network slice allocation.")
    
    logger.info(f"Summary report generated at {os.path.join(output_dir, 'summary_report.md')}")

def parse_args():
    """Parse command-line arguments"""
    parser = argparse.ArgumentParser(description='Run Network Slicing Efficiency Comparison')
    parser.add_argument('--duration', type=int, default=100,
                        help='Simulation duration in steps')
    parser.add_argument('--output_dir', type=str, default='results/efficiency_comparison',
                        help='Output directory for results')
    
    return parser.parse_args()

if __name__ == '__main__':
    # Parse arguments
    args = parse_args()
    
    # Create output directory
    main_output_dir = args.output_dir
    os.makedirs(main_output_dir, exist_ok=True)
    
    # Run all scenarios
    results = run_all_scenarios(args)
    
    # Generate summary report
    generate_summary_report(results, main_output_dir) 