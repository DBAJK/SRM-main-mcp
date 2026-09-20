#!/usr/bin/env python3
"""
5G Network Slice Analysis Tool

This script analyzes and visualizes how AI models allocate 5G network slices,
providing detailed explanations of the reasoning behind each allocation decision.
"""

import os
import sys
import argparse
import numpy as np
from datetime import datetime

# Add the parent directory to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import slice analyzer
from slice_analyzer import SliceAnalyzer

def run_analysis(args):
    """Run slice allocation analysis
    
    Args:
        args: Command line arguments
    """
    # Create analyzer
    analyzer = SliceAnalyzer(results_dir=args.results_dir)
    
    # Create results directory if it doesn't exist
    os.makedirs(args.save_dir, exist_ok=True)
    
    if args.scenario == 'all':
        print("Analyzing all scenarios...")
        analyzer.compare_scenarios(save_dir=args.save_dir)
        print(f"Scenario comparison saved to {args.save_dir}")
    else:
        print(f"Analyzing {args.scenario} scenario at time point {args.time}...")
        analysis = analyzer.analyze_slice_allocation(args.scenario, args.time)
        
        # Save path
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        save_path = os.path.join(args.save_dir, f"{args.scenario}_analysis_{timestamp}.png")
        
        # Visualize analysis
        analyzer.visualize_analysis(analysis, save_path)
        print(f"Analysis visualization saved to {save_path}")
        
        # Print textual analysis
        print("\n" + "="*80)
        print(f"SLICE ALLOCATION ANALYSIS FOR {args.scenario.upper()} SCENARIO")
        print("="*80)
        
        print(f"\nScenario Context: {analysis['explanations']['scenario']}")
        print(f"Traffic Analysis: {analysis['explanations']['traffic']}")
        print(f"Time Pattern: {analysis['explanations']['time']}")
        
        print("\nSlice Utilization:")
        for slice_type, explanation in analysis['explanations']['slices'].items():
            print(f"  - {explanation}")
        
        print(f"\nClient Distribution: {analysis['explanations']['clients']}")
        
        print("\nAI vs Traditional Allocation:")
        for slice_type in ['eMBB', 'URLLC', 'mMTC']:
            trad = analysis['traditional_allocation'][slice_type]
            ai = analysis['ai_allocation'][slice_type]
            diff = (ai - trad) * 100  # percentage points
            direction = "increase" if diff > 0 else "decrease"
            print(f"  - {slice_type}: {trad:.2f} → {ai:.2f} ({abs(diff):.1f}% {direction})")
        
        print("\nAI Decision Summary:")
        print(f"  {analysis['explanations']['decision']}")
        
        print("\nTraffic Classification Results:")
        dominant_class = analysis['dqn_classification']['class']
        probs = analysis['dqn_classification']['probabilities']
        print(f"  - Dominant traffic pattern: {dominant_class}")
        print(f"  - Classification confidence: {probs[dominant_class]:.2f}")
        
        print("\nNote: The AI model allocates resources based on:")
        print("  1. Current network utilization patterns")
        print("  2. Time of day traffic trends")
        print("  3. Client distribution across slices")
        print("  4. Historical traffic patterns")
        print("  5. Predicted future demands\n")

def main():
    """Main function"""
    parser = argparse.ArgumentParser(description="5G Network Slice Analysis Tool")
    parser.add_argument('--scenario', type=str, default='dynamic',
                      choices=['all', 'baseline', 'dynamic', 'emergency', 'smart_city'],
                      help='Scenario to analyze')
    parser.add_argument('--time', type=int, default=15,
                      help='Time point to analyze')
    parser.add_argument('--results-dir', type=str, default='results',
                      help='Directory containing simulation results')
    parser.add_argument('--save-dir', type=str, default='analysis_results',
                      help='Directory to save analysis results')
    parser.add_argument('--detailed', action='store_true',
                      help='Show detailed metrics and explanations')
    
    args = parser.parse_args()
    
    run_analysis(args)

if __name__ == "__main__":
    main() 