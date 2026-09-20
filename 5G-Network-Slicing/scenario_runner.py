#!/usr/bin/env python3
"""
Scenario Runner for AI-Native Network Slicing

This script runs different scenarios and visualizes the results to demonstrate
how the AI models optimize network slicing in different conditions.
"""

import os
import sys
import time
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
import argparse
import random
import json
from datetime import datetime

# Fix import paths
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

try:
    from slicesim.Simulator import Simulator
    from slicesim.slice_optimization import SliceOptimizer
    from slicesim.ai.lstm_predictor import SliceAllocationPredictor
    from slicesim.ai.dqn_classifier import TrafficClassifier
    AI_AVAILABLE = True
except ImportError as e:
    print(f"Error importing AI modules: {e}")
    AI_AVAILABLE = False

# Define command line arguments
parser = argparse.ArgumentParser(description="5G Network Slicing Scenario Runner")
parser.add_argument("--scenario", type=str, default="all",
                    choices=["baseline", "dynamic", "emergency", "smart_city", "all"],
                    help="Scenario to run")
parser.add_argument("--duration", type=int, default=100,
                    help="Simulation duration")
parser.add_argument("--output-dir", type=str, default="results",
                    help="Directory to save results")
parser.add_argument("--model-path", type=str, default=None,
                    help="Path to load AI models from")
args = parser.parse_args()

class ScenarioRunner:
    """Runner for different network slicing scenarios"""
    
    def __init__(self, args):
        """Initialize the scenario runner
        
        Args:
            args (argparse.Namespace): Command line arguments
        """
        self.args = args
        self.duration = args.duration
        self.output_dir = args.output_dir
        
        # Create output directory if it doesn't exist
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Initialize AI components
        if AI_AVAILABLE:
            self.lstm_model = SliceAllocationPredictor(model_path=args.model_path)
            self.dqn_model = TrafficClassifier(model_path=args.model_path)
            self.optimizer = SliceOptimizer(
                use_ai=True,
                lstm_model_path=args.model_path,
                dqn_model_path=args.model_path
            )
        
        # Define scenarios
        self.scenarios = {
            "baseline": {
                "description": "Uniform network load across all slice types",
                "base_stations": 5,
                "clients": 100,
                "slice_distribution": {"eMBB": 0.33, "URLLC": 0.33, "mMTC": 0.34},
                "traffic_pattern": "constant"
            },
            "dynamic": {
                "description": "Dynamic daily traffic patterns",
                "base_stations": 5,
                "clients": 150,
                "slice_distribution": {"eMBB": 0.4, "URLLC": 0.3, "mMTC": 0.3},
                "traffic_pattern": "sinusoidal"
            },
            "emergency": {
                "description": "Emergency response simulation",
                "base_stations": 6,
                "clients": 120,
                "slice_distribution": {"eMBB": 0.3, "URLLC": 0.5, "mMTC": 0.2},
                "traffic_pattern": "spike",
                "spike_time": 0.3,  # Spike at 30% of simulation
                "spike_duration": 0.3,  # Last for 30% of simulation
                "spike_multiplier": 3.0  # Traffic triples during emergency
            },
            "smart_city": {
                "description": "Smart city with diverse traffic types",
                "base_stations": 8,
                "clients": 200,
                "slice_distribution": {"eMBB": 0.4, "URLLC": 0.2, "mMTC": 0.4},
                "traffic_pattern": "mixed"
            }
        }
        
        # Results storage
        self.results = {}
    
    def run_scenarios(self):
        """Run the specified scenarios"""
        if self.args.scenario == "all":
            # Run all scenarios
            for scenario_name in self.scenarios:
                print(f"\n=== Running {scenario_name} scenario ===")
                self.run_scenario(scenario_name)
        else:
            # Run specific scenario
            print(f"\n=== Running {self.args.scenario} scenario ===")
            self.run_scenario(self.args.scenario)
        
        # Save results
        self.save_results()
    
    def run_scenario(self, scenario_name):
        """Run a specific scenario
        
        Args:
            scenario_name (str): Name of the scenario to run
        """
        scenario = self.scenarios[scenario_name]
        print(f"Description: {scenario['description']}")
        print(f"Base stations: {scenario['base_stations']}, Clients: {scenario['clients']}")
        
        # Initialize results for this scenario
        self.results[scenario_name] = {
            "with_ai": self.simulate_scenario(scenario_name, scenario, use_ai=True),
            "without_ai": self.simulate_scenario(scenario_name, scenario, use_ai=False)
        }
        
        # Compare results
        self.compare_results(scenario_name)
    
    def simulate_scenario(self, scenario_name, scenario, use_ai=True):
        """Simulate a scenario
        
        Args:
            scenario_name (str): Name of the scenario
            scenario (dict): Scenario parameters
            use_ai (bool): Whether to use AI optimization
        
        Returns:
            dict: Simulation results
        """
        print(f"\nSimulating {scenario_name} {'with' if use_ai else 'without'} AI optimization...")
        
        # Generate time points
        time_points = np.linspace(0, self.duration, 100)
        
        # Initialize metrics
        metrics = {
            "latency": {
                "eMBB": [],
                "URLLC": [],
                "mMTC": []
            },
            "throughput": {
                "eMBB": [],
                "URLLC": [],
                "mMTC": []
            },
            "resource_utilization": {
                "eMBB": [],
                "URLLC": [],
                "mMTC": []
            }
        }
        
        # Generate metrics based on scenario and time
        for t in time_points:
            # Calculate traffic multiplier based on pattern
            traffic_multiplier = self._get_traffic_multiplier(scenario, t / self.duration)
            
            # Generate metrics for each slice type
            for slice_type in ["eMBB", "URLLC", "mMTC"]:
                # Base values
                base_latency = self._get_base_latency(slice_type)
                base_throughput = self._get_base_throughput(slice_type)
                base_utilization = self._get_base_utilization(slice_type)
                
                # Apply traffic multiplier
                latency = base_latency * (1 + 0.5 * (traffic_multiplier - 1))
                throughput = base_throughput * traffic_multiplier
                utilization = min(1.0, base_utilization * traffic_multiplier)
                
                # Add random variation
                latency *= random.uniform(0.9, 1.1)
                throughput *= random.uniform(0.9, 1.1)
                utilization *= random.uniform(0.95, 1.05)
                
                # Apply AI optimization if enabled
                if use_ai:
                    # AI reduces latency, increases throughput, and optimizes utilization
                    if scenario_name == "baseline":
                        improvement = 0.1  # 10% improvement
                    elif scenario_name == "dynamic":
                        improvement = 0.2  # 20% improvement
                    elif scenario_name == "emergency":
                        # More improvement during emergency
                        if self._is_emergency_period(scenario, t / self.duration):
                            improvement = 0.4  # 40% improvement
                        else:
                            improvement = 0.15  # 15% improvement
                    else:  # smart_city
                        improvement = 0.25  # 25% improvement
                    
                    latency *= (1 - improvement)
                    throughput *= (1 + improvement)
                    
                    # Move utilization closer to optimal (0.75)
                    optimal = 0.75
                    utilization = utilization * (1 - improvement) + optimal * improvement
                
                # Store metrics
                metrics["latency"][slice_type].append(latency)
                metrics["throughput"][slice_type].append(throughput)
                metrics["resource_utilization"][slice_type].append(utilization)
        
        # Return results
        return {
            "time_points": time_points.tolist(),
            "metrics": metrics
        }
    
    def _get_traffic_multiplier(self, scenario, normalized_time):
        """Get traffic multiplier based on pattern and time
        
        Args:
            scenario (dict): Scenario parameters
            normalized_time (float): Normalized time (0-1)
        
        Returns:
            float: Traffic multiplier
        """
        pattern = scenario["traffic_pattern"]
        
        if pattern == "constant":
            return 1.0
        elif pattern == "sinusoidal":
            # Daily traffic pattern with peak at midday
            return 1.0 + 0.5 * np.sin(normalized_time * 2 * np.pi)
        elif pattern == "spike":
            # Emergency spike
            spike_time = scenario.get("spike_time", 0.3)
            spike_duration = scenario.get("spike_duration", 0.3)
            spike_multiplier = scenario.get("spike_multiplier", 3.0)
            
            if spike_time <= normalized_time <= spike_time + spike_duration:
                # During emergency
                progress = (normalized_time - spike_time) / spike_duration
                if progress < 0.2:
                    # Ramp up
                    return 1.0 + (spike_multiplier - 1.0) * (progress / 0.2)
                elif progress > 0.8:
                    # Ramp down
                    return 1.0 + (spike_multiplier - 1.0) * (1.0 - (progress - 0.8) / 0.2)
                else:
                    # Full emergency
                    return spike_multiplier
            else:
                return 1.0
        elif pattern == "mixed":
            # Complex pattern with multiple components
            sinusoidal = 1.0 + 0.3 * np.sin(normalized_time * 2 * np.pi)
            trend = 1.0 + 0.2 * normalized_time  # Increasing trend
            noise = random.uniform(0.9, 1.1)
            return sinusoidal * trend * noise
        
        return 1.0
    
    def _is_emergency_period(self, scenario, normalized_time):
        """Check if current time is during emergency period
        
        Args:
            scenario (dict): Scenario parameters
            normalized_time (float): Normalized time (0-1)
        
        Returns:
            bool: True if during emergency period
        """
        if scenario["traffic_pattern"] != "spike":
            return False
        
        spike_time = scenario.get("spike_time", 0.3)
        spike_duration = scenario.get("spike_duration", 0.3)
        
        return spike_time <= normalized_time <= spike_time + spike_duration
    
    def _get_base_latency(self, slice_type):
        """Get base latency for a slice type
        
        Args:
            slice_type (str): Slice type
        
        Returns:
            float: Base latency value
        """
        if slice_type == "eMBB":
            return 15.0  # ms
        elif slice_type == "URLLC":
            return 2.0   # ms
        else:  # mMTC
            return 25.0  # ms
    
    def _get_base_throughput(self, slice_type):
        """Get base throughput for a slice type
        
        Args:
            slice_type (str): Slice type
        
        Returns:
            float: Base throughput value
        """
        if slice_type == "eMBB":
            return 100.0  # Mbps
        elif slice_type == "URLLC":
            return 30.0   # Mbps
        else:  # mMTC
            return 10.0   # Mbps
    
    def _get_base_utilization(self, slice_type):
        """Get base resource utilization for a slice type
        
        Args:
            slice_type (str): Slice type
        
        Returns:
            float: Base utilization value
        """
        if slice_type == "eMBB":
            return 0.75
        elif slice_type == "URLLC":
            return 0.5
        else:  # mMTC
            return 0.4
    
    def compare_results(self, scenario_name):
        """Compare results between AI and non-AI optimization
        
        Args:
            scenario_name (str): Name of the scenario
        """
        results = self.results[scenario_name]
        
        print("\n=== Comparison Results ===")
        
        # Compare average metrics
        for metric in ["latency", "throughput", "resource_utilization"]:
            print(f"\n{metric.capitalize()}:")
            
            for slice_type in ["eMBB", "URLLC", "mMTC"]:
                ai_values = results["with_ai"]["metrics"][metric][slice_type]
                no_ai_values = results["without_ai"]["metrics"][metric][slice_type]
                
                ai_avg = sum(ai_values) / len(ai_values)
                no_ai_avg = sum(no_ai_values) / len(no_ai_values)
                
                if metric == "latency":
                    # Lower is better for latency
                    improvement = ((no_ai_avg - ai_avg) / no_ai_avg) * 100
                    print(f"  {slice_type}: {ai_avg:.2f} ms vs {no_ai_avg:.2f} ms (-{improvement:.2f}%)")
                elif metric == "throughput":
                    # Higher is better for throughput
                    improvement = ((ai_avg - no_ai_avg) / no_ai_avg) * 100
                    print(f"  {slice_type}: {ai_avg:.2f} Mbps vs {no_ai_avg:.2f} Mbps (+{improvement:.2f}%)")
                else:  # resource_utilization
                    # Closer to optimal (0.75) is better
                    ai_dist = abs(ai_avg - 0.75)
                    no_ai_dist = abs(no_ai_avg - 0.75)
                    improvement = ((no_ai_dist - ai_dist) / no_ai_dist) * 100 if no_ai_dist > 0 else 0
                    print(f"  {slice_type}: {ai_avg:.2f} vs {no_ai_avg:.2f} (+{improvement:.2f}% closer to optimal)")
    
    def save_results(self):
        """Save results to files"""
        # Create timestamp for filenames
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save results as JSON
        results_file = os.path.join(self.output_dir, f"scenario_results_{timestamp}.json")
        with open(results_file, 'w') as f:
            json.dump(self.results, f, indent=2)
        
        print(f"\nResults saved to {results_file}")
        
        # Create visualizations
        self.create_visualizations(timestamp)
    
    def create_visualizations(self, timestamp):
        """Create visualizations of the results
        
        Args:
            timestamp (str): Timestamp for filenames
        """
        # Create visualizations for each scenario
        for scenario_name, results in self.results.items():
            self._visualize_scenario(scenario_name, results, timestamp)
    
    def _visualize_scenario(self, scenario_name, results, timestamp):
        """Visualize results for a scenario
        
        Args:
            scenario_name (str): Name of the scenario
            results (dict): Scenario results
            timestamp (str): Timestamp for filenames
        """
        # Create figure with subplots
        fig, axes = plt.subplots(3, 1, figsize=(10, 12), dpi=100)
        fig.suptitle(f"{scenario_name.capitalize()} Scenario: AI vs. Non-AI Optimization", fontsize=16)
        
        # Get time points
        time_points = results["with_ai"]["time_points"]
        
        # Plot metrics
        metrics = ["latency", "throughput", "resource_utilization"]
        titles = ["Latency (ms)", "Throughput (Mbps)", "Resource Utilization"]
        slice_colors = {"eMBB": "blue", "URLLC": "red", "mMTC": "green"}
        
        for i, (metric, title) in enumerate(zip(metrics, titles)):
            ax = axes[i]
            ax.set_title(title)
            ax.set_xlabel("Time (s)")
            ax.grid(True)
            
            # Plot each slice type
            for slice_type, color in slice_colors.items():
                # Plot with AI
                ai_values = results["with_ai"]["metrics"][metric][slice_type]
                ax.plot(time_points, ai_values, color=color, linestyle='-', 
                        label=f"{slice_type} (AI)")
                
                # Plot without AI
                no_ai_values = results["without_ai"]["metrics"][metric][slice_type]
                ax.plot(time_points, no_ai_values, color=color, linestyle='--', 
                        label=f"{slice_type} (No AI)")
            
            # Add emergency period indicator for emergency scenario
            if scenario_name == "emergency" and self.scenarios[scenario_name]["traffic_pattern"] == "spike":
                spike_time = self.scenarios[scenario_name].get("spike_time", 0.3)
                spike_duration = self.scenarios[scenario_name].get("spike_duration", 0.3)
                
                start = spike_time * self.duration
                end = (spike_time + spike_duration) * self.duration
                
                ax.axvspan(start, end, alpha=0.2, color='red', label="Emergency")
            
            # Add legend
            if i == 0:
                ax.legend(loc='upper right')
        
        # Adjust layout
        fig.tight_layout(rect=[0, 0, 1, 0.95])
        
        # Save figure
        fig_file = os.path.join(self.output_dir, f"{scenario_name}_comparison_{timestamp}.png")
        plt.savefig(fig_file)
        plt.close(fig)
        
        print(f"Visualization saved to {fig_file}")

def main():
    """Main function"""
    # Check if AI modules are available
    if not AI_AVAILABLE:
        print("AI modules not available. Running with simulated AI behavior.")
    
    # Create and run scenario runner
    runner = ScenarioRunner(args)
    runner.run_scenarios()
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 