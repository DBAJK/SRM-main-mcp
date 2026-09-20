#!/usr/bin/env python3
"""
Test Scenarios for 5G Network Slicing Orchestrator

This script tests the orchestrator under different network scenarios
to evaluate its performance with both ML and DQN components.
"""

import os
import numpy as np
import matplotlib.pyplot as plt
import time
from datetime import datetime
import argparse
import logging
import json
import sys

# Configure logging
logging.basicConfig(level=logging.INFO,
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Try to import the orchestrator modules
try:
    from ml_orchestrator_demo import MLOrchestrator
except ImportError:
    logger.error("Could not import MLOrchestrator. Make sure ml_orchestrator_demo.py is available.")
    sys.exit(1)

class ScenarioTester:
    """Test different scenarios for the network slicing orchestrator."""
    
    def __init__(self, output_dir=None, lstm_model_path=None, dqn_model_path=None):
        """Initialize the scenario tester.
        
        Args:
            output_dir (str): Directory to save results
            lstm_model_path (str): Path to LSTM model
            dqn_model_path (str): Path to DQN model
        """
        self.output_dir = output_dir or f"results/scenario_tests_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Create orchestrator
        try:
            self.orchestrator = MLOrchestrator(model_path=lstm_model_path)
            logger.info("Created orchestrator with LSTM model")
        except Exception as e:
            logger.error(f"Error creating orchestrator: {e}")
            sys.exit(1)
        
        # Define scenarios
        self.scenarios = {
            "normal": {
                "description": "Normal network operation",
                "duration": 30,
                "interval": 0.5,
                "emergency": False,
                "special_event": False,
                "iot_surge": False
            },
            "emergency": {
                "description": "Emergency situation with high URLLC demand",
                "duration": 30,
                "interval": 0.5,
                "emergency": True,
                "special_event": False,
                "iot_surge": False
            },
            "special_event": {
                "description": "Special event with high eMBB demand",
                "duration": 30,
                "interval": 0.5,
                "emergency": False,
                "special_event": True,
                "iot_surge": False
            },
            "iot_surge": {
                "description": "IoT device surge with high mMTC demand",
                "duration": 30,
                "interval": 0.5,
                "emergency": False,
                "special_event": False,
                "iot_surge": True
            },
            "mixed": {
                "description": "Mixed scenario with changing conditions",
                "duration": 60,
                "interval": 0.5,
                "emergency": False,
                "special_event": False,
                "iot_surge": False,
                "dynamic_changes": [
                    {"time": 10, "event": "special_event", "value": True},
                    {"time": 25, "event": "special_event", "value": False},
                    {"time": 30, "event": "emergency", "value": True},
                    {"time": 45, "event": "emergency", "value": False},
                    {"time": 50, "event": "iot_surge", "value": True}
                ]
            }
        }
        
        # Results storage
        self.results = {}
    
    def run_scenario(self, scenario_name):
        """Run a specific scenario.
        
        Args:
            scenario_name (str): Name of the scenario to run
        
        Returns:
            dict: Results of the scenario
        """
        if scenario_name not in self.scenarios:
            logger.error(f"Unknown scenario: {scenario_name}")
            return None
        
        scenario = self.scenarios[scenario_name]
        logger.info(f"Running scenario: {scenario_name} - {scenario['description']}")
        
        # Reset orchestrator
        self.orchestrator = MLOrchestrator(model_path=None)
        
        # Set initial conditions
        self.orchestrator.set_emergency_mode(scenario.get("emergency", False))
        self.orchestrator.set_special_event_mode(scenario.get("special_event", False))
        self.orchestrator.set_iot_surge_mode(scenario.get("iot_surge", False))
        
        # Create scenario output directory
        scenario_dir = os.path.join(self.output_dir, scenario_name)
        os.makedirs(scenario_dir, exist_ok=True)
        self.orchestrator.output_dir = scenario_dir
        
        # Run scenario
        if "dynamic_changes" in scenario:
            # Run with dynamic changes
            self._run_dynamic_scenario(scenario)
        else:
            # Run normal scenario
            self.orchestrator.run(scenario["duration"], scenario["interval"])
        
        # Collect results
        self.results[scenario_name] = self._analyze_results(scenario_name)
        
        return self.results[scenario_name]
    
    def _run_dynamic_scenario(self, scenario):
        """Run a scenario with dynamic changes.
        
        Args:
            scenario (dict): Scenario configuration
        """
        logger.info("Running dynamic scenario with changing conditions")
        
        # Initialize history
        self.orchestrator.history = []
        
        # Sort changes by time
        changes = sorted(scenario["dynamic_changes"], key=lambda x: x["time"])
        next_change_idx = 0
        
        # Run for specified duration
        start_time = time.time()
        step = 0
        
        try:
            while time.time() - start_time < scenario["duration"]:
                # Check if it's time for a condition change
                elapsed = time.time() - start_time
                if next_change_idx < len(changes) and elapsed >= changes[next_change_idx]["time"]:
                    change = changes[next_change_idx]
                    event_type = change["event"]
                    value = change["value"]
                    
                    logger.info(f"Dynamic change at {elapsed:.1f}s: {event_type} = {value}")
                    
                    # Apply change
                    if event_type == "emergency":
                        self.orchestrator.set_emergency_mode(value)
                    elif event_type == "special_event":
                        self.orchestrator.set_special_event_mode(value)
                    elif event_type == "iot_surge":
                        self.orchestrator.set_iot_surge_mode(value)
                    
                    next_change_idx += 1
                
                # Run step
                state = self.orchestrator.run_step()
                
                # Add to history
                self.orchestrator.history.append(state)
                
                # Log state
                logger.info(f"Step {step}:")
                logger.info(f"  Allocation: eMBB={state['allocation'][0]:.2f}, "
                           f"URLLC={state['allocation'][1]:.2f}, "
                           f"mMTC={state['allocation'][2]:.2f}")
                logger.info(f"  Utilization: eMBB={state['utilization'][0]:.2f}, "
                           f"URLLC={state['utilization'][1]:.2f}, "
                           f"mMTC={state['utilization'][2]:.2f}")
                
                # Check for violations
                if np.any(state['violations']):
                    logger.warning(f"  QoS violations: {state['violations']}")
                
                # Visualize state
                viz_path = os.path.join(self.orchestrator.output_dir, f"state_{step:03d}.png")
                self.orchestrator.visualize_state(state, viz_path)
                
                # Increment step
                step += 1
                
                # Sleep
                time.sleep(scenario["interval"])
        
        except KeyboardInterrupt:
            logger.info("Scenario stopped by user")
        
        # Save history
        self.orchestrator.save_history()
        
        logger.info(f"Dynamic scenario completed with {step} steps")
    
    def _analyze_results(self, scenario_name):
        """Analyze results from a scenario run.
        
        Args:
            scenario_name (str): Name of the scenario
        
        Returns:
            dict: Analysis results
        """
        logger.info(f"Analyzing results for scenario: {scenario_name}")
        
        # Get history
        history = self.orchestrator.history
        
        # Calculate metrics
        total_steps = len(history)
        
        # QoS violations
        violations = np.zeros(3)
        for state in history:
            violations += state["violations"].astype(int)
        
        violation_rate = violations / total_steps
        
        # Average utilization
        avg_utilization = np.zeros(3)
        for state in history:
            avg_utilization += state["utilization"]
        avg_utilization /= total_steps
        
        # Average allocation
        avg_allocation = np.zeros(3)
        for state in history:
            avg_allocation += state["allocation"]
        avg_allocation /= total_steps
        
        # Create analysis results
        analysis = {
            "scenario": scenario_name,
            "description": self.scenarios[scenario_name]["description"],
            "total_steps": total_steps,
            "qos_violations": violations.tolist(),
            "violation_rate": violation_rate.tolist(),
            "avg_utilization": avg_utilization.tolist(),
            "avg_allocation": avg_allocation.tolist()
        }
        
        # Save analysis to file
        analysis_path = os.path.join(self.orchestrator.output_dir, "analysis.json")
        with open(analysis_path, "w") as f:
            json.dump(analysis, f, indent=2)
        
        return analysis
    
    def run_all_scenarios(self):
        """Run all defined scenarios.
        
        Returns:
            dict: Results for all scenarios
        """
        logger.info("Running all scenarios")
        
        for scenario_name in self.scenarios:
            self.run_scenario(scenario_name)
        
        # Create comparison visualizations
        self._create_comparison_visualizations()
        
        return self.results
    
    def _create_comparison_visualizations(self):
        """Create visualizations comparing results across scenarios."""
        if not self.results:
            logger.warning("No results to visualize")
            return
        
        logger.info("Creating comparison visualizations")
        
        # Create comparison directory
        comparison_dir = os.path.join(self.output_dir, "comparison")
        os.makedirs(comparison_dir, exist_ok=True)
        
        # QoS violation comparison
        plt.figure(figsize=(12, 6))
        scenario_names = list(self.results.keys())
        x = np.arange(len(scenario_names))
        width = 0.25
        
        slice_names = ['eMBB', 'URLLC', 'mMTC']
        colors = ['#FF6B6B', '#45B7D1', '#FFBE0B']
        
        for i, slice_name in enumerate(slice_names):
            violations = [self.results[s]["violation_rate"][i] for s in scenario_names]
            plt.bar(x + (i - 1) * width, violations, width, label=slice_name, color=colors[i])
        
        plt.xlabel('Scenario')
        plt.ylabel('QoS Violation Rate')
        plt.title('QoS Violation Rate by Scenario and Slice Type')
        plt.xticks(x, scenario_names)
        plt.legend()
        plt.grid(axis='y', linestyle='--', alpha=0.7)
        plt.tight_layout()
        plt.savefig(os.path.join(comparison_dir, "qos_violations.png"))
        plt.close()
        
        # Average utilization comparison
        plt.figure(figsize=(12, 6))
        
        for i, slice_name in enumerate(slice_names):
            utilization = [self.results[s]["avg_utilization"][i] for s in scenario_names]
            plt.bar(x + (i - 1) * width, utilization, width, label=slice_name, color=colors[i])
        
        plt.xlabel('Scenario')
        plt.ylabel('Average Utilization')
        plt.title('Average Utilization by Scenario and Slice Type')
        plt.xticks(x, scenario_names)
        plt.legend()
        plt.grid(axis='y', linestyle='--', alpha=0.7)
        plt.tight_layout()
        plt.savefig(os.path.join(comparison_dir, "avg_utilization.png"))
        plt.close()
        
        # Average allocation comparison
        plt.figure(figsize=(12, 6))
        
        for i, slice_name in enumerate(slice_names):
            allocation = [self.results[s]["avg_allocation"][i] for s in scenario_names]
            plt.bar(x + (i - 1) * width, allocation, width, label=slice_name, color=colors[i])
        
        plt.xlabel('Scenario')
        plt.ylabel('Average Allocation')
        plt.title('Average Resource Allocation by Scenario and Slice Type')
        plt.xticks(x, scenario_names)
        plt.legend()
        plt.grid(axis='y', linestyle='--', alpha=0.7)
        plt.tight_layout()
        plt.savefig(os.path.join(comparison_dir, "avg_allocation.png"))
        plt.close()
        
        # Save overall results
        overall_path = os.path.join(comparison_dir, "overall_results.json")
        with open(overall_path, "w") as f:
            json.dump(self.results, f, indent=2)
        
        logger.info(f"Comparison visualizations saved to {comparison_dir}")


def main():
    """Main function to run scenario tests."""
    parser = argparse.ArgumentParser(description='Test scenarios for 5G Network Slicing Orchestrator')
    parser.add_argument('--scenario', type=str, choices=['normal', 'emergency', 'special_event', 'iot_surge', 'mixed', 'all'],
                       default='all', help='Scenario to run')
    parser.add_argument('--output-dir', type=str, help='Directory to save results')
    parser.add_argument('--lstm-model', type=str, help='Path to LSTM model')
    parser.add_argument('--dqn-model', type=str, help='Path to DQN model')
    
    args = parser.parse_args()
    
    # Create tester
    tester = ScenarioTester(
        output_dir=args.output_dir,
        lstm_model_path=args.lstm_model,
        dqn_model_path=args.dqn_model
    )
    
    # Run scenarios
    if args.scenario == 'all':
        results = tester.run_all_scenarios()
    else:
        results = tester.run_scenario(args.scenario)
    
    logger.info("Scenario testing completed")
    
    return results


if __name__ == "__main__":
    main() 