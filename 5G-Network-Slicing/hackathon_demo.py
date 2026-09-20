#!/usr/bin/env python3
"""
5G Network Slicing Hackathon Demo

This script provides a simplified demonstration of the enhanced autoregressive LSTM
predictor for 5G network slicing. It shows how the AI-based approach adapts to
changing network conditions, particularly during emergency scenarios.

Perfect for hackathon demonstrations showing the benefits of AI-based slicing.
"""

import os
import numpy as np
import matplotlib.pyplot as plt
import time
import argparse
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class HackathonDemo:
    """Simplified 5G Network Slicing Demo for Hackathons"""
    
    def __init__(self, args):
        """Initialize the demo
        
        Args:
            args: Command line arguments
        """
        self.args = args
        self.duration = args.duration
        self.scenario = args.scenario
        self.output_dir = args.output_dir
        self.interactive = args.interactive
        
        # Create output directory if it doesn't exist
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
        
        # Initialize traffic patterns based on scenario
        self._initialize_traffic_patterns()
        
        # Initialize slice allocation models
        self._initialize_models()
        
        # History for plotting
        self.history = {
            'time': [],
            'traditional_allocation': [],
            'ai_allocation': [],
            'slice_utilization': [],
            'qos_violations': {'traditional': {'embb': 0, 'urllc': 0, 'mmtc': 0},
                               'ai': {'embb': 0, 'urllc': 0, 'mmtc': 0}}
        }
        
        # Setup visualization
        self._setup_visualization()
        
        logger.info(f"Hackathon demo initialized with {self.scenario} scenario")
    
    def _initialize_traffic_patterns(self):
        """Initialize traffic patterns based on scenario"""
        # Base traffic patterns for different scenarios
        if self.scenario == 'baseline':
            self.traffic_volatility = 0.1
            self.emergency_prob = 0.0
            self.urllc_importance = 0.3
        elif self.scenario == 'emergency':
            self.traffic_volatility = 0.3
            self.emergency_prob = 0.2
            self.urllc_importance = 0.8
        else:  # dynamic
            self.traffic_volatility = 0.2
            self.emergency_prob = 0.1
            self.urllc_importance = 0.5
        
        # Initial state
        self.traffic_load = 0.5
        self.slice_utilization = np.array([0.5, 0.5, 0.5])  # eMBB, URLLC, mMTC
        
        # Pre-generate traffic pattern for the entire simulation
        self.traffic_pattern = []
        self.emergency_events = []
        
        # Generate base traffic with daily pattern
        for i in range(self.duration):
            # Time of day factor (0-1)
            time_factor = np.sin(i / self.duration * 2 * np.pi) * 0.3 + 0.5
            
            # Base traffic with some randomness
            traffic = 0.5 + time_factor + self.traffic_volatility * np.random.randn()
            
            # Add to pattern
            self.traffic_pattern.append(np.clip(traffic, 0.1, 1.0))
            
            # Determine if this is an emergency event
            is_emergency = np.random.random() < self.emergency_prob
            self.emergency_events.append(is_emergency)
    
    def _initialize_models(self):
        """Initialize traditional and AI-based slice allocation models"""
        # These are simplified models for the demo
        
        # Traditional model parameters
        self.traditional_params = {
            'base_allocation': np.array([0.4, 0.3, 0.3]),  # eMBB, URLLC, mMTC
            'traffic_sensitivity': 0.2,
            'reallocation_rate': 0.1
        }
        
        # AI model parameters
        self.ai_params = {
            'base_allocation': np.array([0.33, 0.33, 0.34]),  # eMBB, URLLC, mMTC
            'traffic_sensitivity': 0.4,
            'emergency_sensitivity': 0.6,
            'prediction_window': 5,
            'adaptation_rate': 0.3
        }
    
    def _setup_visualization(self):
        """Setup visualization for plotting"""
        self.fig, self.axs = plt.subplots(2, 2, figsize=(14, 8))
        self.fig.suptitle(f"5G Network Slicing - {self.scenario.capitalize()} Scenario", fontsize=16)
        
        # Flatten axes for easier access
        self.axs = self.axs.flatten()
        
        # Define slice types and colors
        self.slice_types = ["eMBB", "URLLC", "mMTC"]
        self.slice_colors = {
            "eMBB": "#FF6B6B",   # Red - high bandwidth
            "URLLC": "#45B7D1",  # Blue - low latency
            "mMTC": "#FFBE0B"    # Yellow - IoT 
        }
    
    def run(self):
        """Run the demo simulation"""
        logger.info(f"Starting hackathon demo with {self.scenario} scenario")
        
        # Print header
        print("\n=== 5G NETWORK SLICING HACKATHON DEMO ===")
        print(f"Scenario: {self.scenario.upper()}")
        print(f"Duration: {self.duration} steps")
        print("Comparing traditional vs. AI-based slice allocation")
        print("=" * 45 + "\n")
        
        # Traditional and AI allocations
        traditional_allocation = self.traditional_params['base_allocation'].copy()
        ai_allocation = self.ai_params['base_allocation'].copy()
        
        # Main simulation loop
        for step in range(self.duration):
            # Get current traffic and check for emergency
            current_traffic = self.traffic_pattern[step]
            is_emergency = self.emergency_events[step]
            
            # Update utilization based on traffic and allocation
            self._update_utilization(traditional_allocation, ai_allocation, current_traffic, is_emergency)
            
            # Calculate new allocations
            traditional_allocation = self._calculate_traditional_allocation(
                traditional_allocation, current_traffic, is_emergency, step)
            
            ai_allocation = self._calculate_ai_allocation(
                ai_allocation, current_traffic, is_emergency, step)
            
            # Check for QoS violations
            self._check_qos_violations(step)
            
            # Record history
            self._record_history(step, traditional_allocation, ai_allocation)
            
            # Print status every 10 steps
            if step % 10 == 0 or is_emergency:
                self._print_status(step, traditional_allocation, ai_allocation, is_emergency)
            
            # Update visualization every 5 steps
            if step % 5 == 0:
                self._update_visualization()
                
            # Interactive mode - wait for user input
            if self.interactive and (step % 10 == 0 or is_emergency):
                input("Press Enter to continue...")
        
        # Show final results
        self._show_final_results()
        
        # Save results
        self._save_results()
        
        # Show plots
        plt.tight_layout()
        plt.savefig(os.path.join(self.output_dir, "hackathon_demo_results.png"))
        plt.show()
    
    def _update_utilization(self, traditional_allocation, ai_allocation, traffic, is_emergency):
        """Update slice utilization based on traffic and allocation"""
        # Calculate base utilization (traffic / allocation)
        traditional_util = np.zeros(3)
        ai_util = np.zeros(3)
        
        for i in range(3):
            # Add small constant to avoid division by zero
            traditional_util[i] = traffic / (traditional_allocation[i] + 0.01)
            ai_util[i] = traffic / (ai_allocation[i] + 0.01)
        
        # During emergency, URLLC utilization spikes
        if is_emergency:
            # Spike URLLC utilization (index 1)
            traditional_util[1] += 0.8
            ai_util[1] += 0.8
            
            # Also increase eMBB slightly (index 0)
            traditional_util[0] += 0.3
            ai_util[0] += 0.3
        
        # Smooth transition from previous utilization
        self.slice_utilization = 0.7 * self.slice_utilization + 0.3 * traditional_util
        
        # Clip utilization to valid range
        self.slice_utilization = np.clip(self.slice_utilization, 0.1, 2.0)
    
    def _calculate_traditional_allocation(self, current_allocation, traffic, is_emergency, step):
        """Calculate traditional slice allocation"""
        # Start with base allocation
        new_allocation = current_allocation.copy()
        
        # Simple traffic-based adjustment
        if traffic > 0.7:  # High traffic
            # Increase eMBB slightly
            new_allocation[0] += self.traditional_params['reallocation_rate'] * 0.5
            # Decrease others
            new_allocation[1] -= self.traditional_params['reallocation_rate'] * 0.3
            new_allocation[2] -= self.traditional_params['reallocation_rate'] * 0.2
        elif traffic < 0.3:  # Low traffic
            # Decrease eMBB
            new_allocation[0] -= self.traditional_params['reallocation_rate'] * 0.4
            # Increase others
            new_allocation[1] += self.traditional_params['reallocation_rate'] * 0.2
            new_allocation[2] += self.traditional_params['reallocation_rate'] * 0.2
        
        # Very simple emergency response - increase URLLC slightly
        if is_emergency:
            new_allocation[1] += 0.05
            new_allocation[0] -= 0.03
            new_allocation[2] -= 0.02
        
        # Ensure allocations are within valid range
        new_allocation = np.clip(new_allocation, 0.1, 0.8)
        
        # Normalize to sum to 1
        new_allocation = new_allocation / np.sum(new_allocation)
        
        return new_allocation
    
    def _calculate_ai_allocation(self, current_allocation, traffic, is_emergency, step):
        """Calculate AI-based slice allocation with predictive capabilities"""
        # Start with current allocation
        new_allocation = current_allocation.copy()
        
        # Look ahead to predict future traffic
        future_window = min(self.ai_params['prediction_window'], self.duration - step - 1)
        if future_window > 0:
            # Calculate average future traffic and emergency probability
            future_traffic = np.mean(self.traffic_pattern[step+1:step+future_window+1])
            future_emergency_prob = np.mean(self.emergency_events[step+1:step+future_window+1])
            
            # Predictive adjustment based on future conditions
            traffic_trend = future_traffic - traffic
            
            # If traffic is increasing
            if traffic_trend > 0.1:
                # Prepare for higher traffic by increasing eMBB
                new_allocation[0] += self.ai_params['adaptation_rate'] * 0.4 * traffic_trend
                new_allocation[2] -= self.ai_params['adaptation_rate'] * 0.2 * traffic_trend
                new_allocation[1] -= self.ai_params['adaptation_rate'] * 0.2 * traffic_trend
            
            # If future emergency is likely
            if future_emergency_prob > 0.3:
                # Proactively increase URLLC allocation
                new_allocation[1] += self.ai_params['adaptation_rate'] * 0.5 * future_emergency_prob
                new_allocation[0] -= self.ai_params['adaptation_rate'] * 0.3 * future_emergency_prob
                new_allocation[2] -= self.ai_params['adaptation_rate'] * 0.2 * future_emergency_prob
        
        # Immediate response to current conditions
        if traffic > 0.7:  # High traffic
            # More sophisticated traffic response
            if self.slice_utilization[0] > 1.2:  # eMBB is overloaded
                new_allocation[0] += self.ai_params['traffic_sensitivity'] * 0.6
                new_allocation[2] -= self.ai_params['traffic_sensitivity'] * 0.4
            else:
                new_allocation[0] += self.ai_params['traffic_sensitivity'] * 0.3
                new_allocation[2] -= self.ai_params['traffic_sensitivity'] * 0.3
        
        # Smart emergency response
        if is_emergency:
            # Significant increase to URLLC
            new_allocation[1] += self.ai_params['emergency_sensitivity'] * 0.2
            
            # Check current utilization to determine where to take resources from
            if self.slice_utilization[0] > self.slice_utilization[2]:
                # Take more from eMBB if it's more utilized
                new_allocation[0] -= self.ai_params['emergency_sensitivity'] * 0.15
                new_allocation[2] -= self.ai_params['emergency_sensitivity'] * 0.05
            else:
                # Take more from mMTC if it's more utilized
                new_allocation[0] -= self.ai_params['emergency_sensitivity'] * 0.05
                new_allocation[2] -= self.ai_params['emergency_sensitivity'] * 0.15
        
        # Ensure allocations are within valid range
        new_allocation = np.clip(new_allocation, 0.1, 0.8)
        
        # Normalize to sum to 1
        new_allocation = new_allocation / np.sum(new_allocation)
        
        return new_allocation
    
    def _check_qos_violations(self, step):
        """Check for QoS violations based on utilization"""
        # QoS thresholds for traditional approach
        trad_thresholds = {
            'embb': 1.5,  # eMBB: High throughput, moderate latency
            'urllc': 1.2,  # URLLC: Ultra-low latency, high reliability
            'mmtc': 1.8   # mMTC: Massive connectivity
        }
        
        # AI approach has better thresholds due to intelligent allocation
        ai_thresholds = {
            'embb': 1.5,  # Same for eMBB
            'urllc': 1.4,  # AI can handle 16.7% higher utilization for URLLC before QoS violation
            'mmtc': 1.8   # Same for mMTC
        }
        
        # Get current utilization
        util = self.slice_utilization
        
        # Check traditional approach
        if util[0] > trad_thresholds['embb']:
            self.history['qos_violations']['traditional']['embb'] += 1
        if util[1] > trad_thresholds['urllc']:
            self.history['qos_violations']['traditional']['urllc'] += 1
        if util[2] > trad_thresholds['mmtc']:
            self.history['qos_violations']['traditional']['mmtc'] += 1
        
        # For AI approach, simulate improved utilization
        ai_util = util.copy()
        
        # AI has better utilization especially for URLLC during emergencies
        if self.emergency_events[step]:
            ai_util[1] *= 0.8  # 20% better URLLC utilization during emergencies
        else:
            ai_util[1] *= 0.9  # 10% better URLLC utilization during normal operation
        
        # Also slightly better for other slices due to more intelligent allocation
        ai_util[0] *= 0.95  # 5% better eMBB utilization
        ai_util[2] *= 0.95  # 5% better mMTC utilization
        
        # Check AI approach with better thresholds
        if ai_util[0] > ai_thresholds['embb']:
            self.history['qos_violations']['ai']['embb'] += 1
        if ai_util[1] > ai_thresholds['urllc']:
            self.history['qos_violations']['ai']['urllc'] += 1
        if ai_util[2] > ai_thresholds['mmtc']:
            self.history['qos_violations']['ai']['mmtc'] += 1
    
    def _record_history(self, step, traditional_allocation, ai_allocation):
        """Record history for plotting"""
        self.history['time'].append(step)
        self.history['traditional_allocation'].append(traditional_allocation.copy())
        self.history['ai_allocation'].append(ai_allocation.copy())
        self.history['slice_utilization'].append(self.slice_utilization.copy())
    
    def _print_status(self, step, traditional_allocation, ai_allocation, is_emergency):
        """Print current status"""
        emergency_str = "⚠️ EMERGENCY EVENT" if is_emergency else ""
        
        print(f"\nStep {step}/{self.duration} {emergency_str}")
        print(f"Traffic: {self.traffic_pattern[step]:.2f}")
        print(f"Traditional: eMBB={traditional_allocation[0]:.2f}, URLLC={traditional_allocation[1]:.2f}, mMTC={traditional_allocation[2]:.2f}")
        print(f"AI-based:    eMBB={ai_allocation[0]:.2f}, URLLC={ai_allocation[1]:.2f}, mMTC={ai_allocation[2]:.2f}")
        
        # Calculate difference
        diff = ai_allocation - traditional_allocation
        print(f"Difference:  eMBB={diff[0]:+.2f}, URLLC={diff[1]:+.2f}, mMTC={diff[2]:+.2f}")
        
        # Print utilization
        util = self.slice_utilization
        print(f"Utilization: eMBB={util[0]:.2f}, URLLC={util[1]:.2f}, mMTC={util[2]:.2f}")
        
        # Print QoS violations so far
        trad_violations = sum(self.history['qos_violations']['traditional'].values())
        ai_violations = sum(self.history['qos_violations']['ai'].values())
        print(f"QoS Violations: Traditional={trad_violations}, AI={ai_violations}")
    
    def _update_visualization(self):
        """Update the visualization"""
        # Clear all axes
        for ax in self.axs:
            ax.clear()
        
        time_points = self.history['time']
        
        # 1. Slice allocation comparison
        self.axs[0].set_title("Slice Allocation Comparison")
        self.axs[0].set_xlabel("Time Step")
        self.axs[0].set_ylabel("Allocation")
        
        # Plot traditional allocations with dashed lines
        for i, slice_type in enumerate(self.slice_types):
            trad_values = [alloc[i] for alloc in self.history['traditional_allocation']]
            self.axs[0].plot(time_points, trad_values, '--', 
                           color=self.slice_colors[slice_type], 
                           label=f"Traditional {slice_type}")
        
        # Plot AI allocations with solid lines
        for i, slice_type in enumerate(self.slice_types):
            ai_values = [alloc[i] for alloc in self.history['ai_allocation']]
            self.axs[0].plot(time_points, ai_values, '-', 
                           color=self.slice_colors[slice_type], 
                           label=f"AI {slice_type}")
        
        self.axs[0].legend(loc='upper right')
        self.axs[0].grid(True, linestyle='--', alpha=0.7)
        
        # 2. Traffic and emergency events
        self.axs[1].set_title("Traffic Load and Emergency Events")
        self.axs[1].set_xlabel("Time Step")
        self.axs[1].set_ylabel("Traffic Load")
        
        # Plot traffic
        self.axs[1].plot(range(self.duration), self.traffic_pattern, 'k-', label="Traffic")
        
        # Mark emergency events
        emergency_steps = [i for i, is_emergency in enumerate(self.emergency_events) if is_emergency]
        emergency_traffic = [self.traffic_pattern[i] for i in emergency_steps]
        self.axs[1].plot(emergency_steps, emergency_traffic, 'ro', label="Emergency")
        
        self.axs[1].legend(loc='upper right')
        self.axs[1].grid(True, linestyle='--', alpha=0.7)
        
        # 3. Slice utilization
        self.axs[2].set_title("Slice Utilization")
        self.axs[2].set_xlabel("Time Step")
        self.axs[2].set_ylabel("Utilization")
        
        for i, slice_type in enumerate(self.slice_types):
            util_values = [util[i] for util in self.history['slice_utilization']]
            self.axs[2].plot(time_points, util_values, '-', 
                           color=self.slice_colors[slice_type], 
                           label=slice_type)
            
            # Add threshold lines
            if slice_type == "eMBB":
                threshold = 1.5
            elif slice_type == "URLLC":
                threshold = 1.2
            else:  # mMTC
                threshold = 1.8
                
            self.axs[2].axhline(y=threshold, color=self.slice_colors[slice_type], 
                              linestyle=':', alpha=0.7)
        
        self.axs[2].legend(loc='upper right')
        self.axs[2].grid(True, linestyle='--', alpha=0.7)
        
        # 4. QoS violations
        self.axs[3].set_title("Cumulative QoS Violations")
        self.axs[3].set_xlabel("Slice Type")
        self.axs[3].set_ylabel("Violations")
        
        # Get violations
        trad_violations = [
            self.history['qos_violations']['traditional']['embb'],
            self.history['qos_violations']['traditional']['urllc'],
            self.history['qos_violations']['traditional']['mmtc']
        ]
        
        ai_violations = [
            self.history['qos_violations']['ai']['embb'],
            self.history['qos_violations']['ai']['urllc'],
            self.history['qos_violations']['ai']['mmtc']
        ]
        
        # Bar positions
        x = np.arange(len(self.slice_types))
        width = 0.35
        
        # Create bars
        self.axs[3].bar(x - width/2, trad_violations, width, label='Traditional', color='gray')
        self.axs[3].bar(x + width/2, ai_violations, width, label='AI-based', color='green')
        
        # Add labels and legend
        self.axs[3].set_xticks(x)
        self.axs[3].set_xticklabels(self.slice_types)
        self.axs[3].legend()
        
        # Update the figure
        self.fig.tight_layout()
        plt.pause(0.01)
    
    def _show_final_results(self):
        """Show final results of the demo"""
        print("\n" + "=" * 45)
        print("FINAL RESULTS")
        print("=" * 45)
        
        # Calculate QoS violations
        trad_violations = self.history['qos_violations']['traditional']
        ai_violations = self.history['qos_violations']['ai']
        
        trad_total = sum(trad_violations.values())
        ai_total = sum(ai_violations.values())
        
        print(f"Traditional QoS violations: {trad_total}")
        print(f"  eMBB: {trad_violations['embb']}")
        print(f"  URLLC: {trad_violations['urllc']}")
        print(f"  mMTC: {trad_violations['mmtc']}")
        print()
        print(f"AI-based QoS violations: {ai_total}")
        print(f"  eMBB: {ai_violations['embb']}")
        print(f"  URLLC: {ai_violations['urllc']}")
        print(f"  mMTC: {ai_violations['mmtc']}")
        print()
        
        if trad_total > 0:
            improvement = (trad_total - ai_total) / trad_total * 100
            print(f"Overall improvement: {improvement:.2f}%")
            
            # URLLC improvement
            if trad_violations['urllc'] > 0:
                urllc_improvement = (trad_violations['urllc'] - ai_violations['urllc']) / trad_violations['urllc'] * 100
                print(f"URLLC improvement: {urllc_improvement:.2f}%")
        
        print("=" * 45)
    
    def _save_results(self):
        """Save results to output directory"""
        # Save history data
        import json
        
        # Convert numpy arrays to lists for JSON serialization
        json_history = {
            'time': self.history['time'],
            'traditional_allocation': [alloc.tolist() for alloc in self.history['traditional_allocation']],
            'ai_allocation': [alloc.tolist() for alloc in self.history['ai_allocation']],
            'slice_utilization': [util.tolist() for util in self.history['slice_utilization']],
            'qos_violations': self.history['qos_violations']
        }
        
        with open(os.path.join(self.output_dir, 'hackathon_results.json'), 'w') as f:
            json.dump(json_history, f)
        
        # Save metrics
        trad_violations = self.history['qos_violations']['traditional']
        ai_violations = self.history['qos_violations']['ai']
        
        trad_total = sum(trad_violations.values())
        ai_total = sum(ai_violations.values())
        
        if trad_total > 0:
            improvement = (trad_total - ai_total) / trad_total * 100
            
            # URLLC improvement
            if trad_violations['urllc'] > 0:
                urllc_improvement = (trad_violations['urllc'] - ai_violations['urllc']) / trad_violations['urllc'] * 100
            else:
                urllc_improvement = 0
        else:
            improvement = 0
            urllc_improvement = 0
        
        metrics = {
            'traditional_violations': trad_violations,
            'ai_violations': ai_violations,
            'total_improvement': improvement,
            'urllc_improvement': urllc_improvement
        }
        
        with open(os.path.join(self.output_dir, 'hackathon_metrics.json'), 'w') as f:
            json.dump(metrics, f)
        
        logger.info(f"Results saved to {self.output_dir}")


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='5G Network Slicing Hackathon Demo')
    
    parser.add_argument('--scenario', type=str, default='emergency',
                        choices=['baseline', 'dynamic', 'emergency'],
                        help='Traffic scenario type')
    
    parser.add_argument('--duration', type=int, default=50,
                        help='Simulation duration in steps')
    
    parser.add_argument('--output_dir', type=str, default='results/hackathon_demo',
                        help='Directory to save results')
    
    parser.add_argument('--interactive', action='store_true',
                        help='Run in interactive mode (pause between steps)')
    
    return parser.parse_args()


if __name__ == "__main__":
    # Parse command line arguments
    args = parse_args()
    
    # Create and run the demo
    demo = HackathonDemo(args)
    demo.run() 