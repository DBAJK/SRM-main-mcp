#!/usr/bin/env python3
"""
5G Network Slicing - Simulation Module

This module implements the simulation environment for the 5G network slicing system.
It integrates the orchestrator, slice manager, and other components to simulate
the behavior of the system under different scenarios.
"""

import os
import numpy as np
import logging
import time
import json
import matplotlib.pyplot as plt
from datetime import datetime
import argparse

# Import local modules
from slicesim.orchestrator import SliceOrchestrator
from slicesim.ai.slice_manager import BaseSliceManager, ProportionalSliceManager, EnhancedSliceManager
from slicesim.config import Config, get_config
from slicesim.utils import (
    setup_directories, save_json, load_json, generate_traffic_pattern,
    calculate_utilization, check_qos_violations, visualize_traffic,
    visualize_allocation_comparison, visualize_qos_violations
)

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class SliceSimulation:
    """
    Simulation environment for 5G network slicing.
    
    This class integrates all components and runs the simulation.
    """
    
    def __init__(self, config_path=None):
        """
        Initialize the simulation environment.
        
        Args:
            config_path (str): Path to the configuration file
        """
        # Load configuration
        self.config = Config(config_path)
        
        # Ensure directories exist
        self.config.ensure_directories()
        
        # Initialize components
        self.orchestrator = None
        self.slice_managers = {}
        self.traffic_data = None
        self.results = {}
        
        logger.info("Simulation environment initialized")
    
    def setup(self, model_path=None):
        """
        Set up the simulation environment.
        
        Args:
            model_path (str): Path to the trained model
        
        Returns:
            bool: Whether setup was successful
        """
        try:
            # Create slice managers
            self.slice_managers['static'] = BaseSliceManager()
            self.slice_managers['proportional'] = ProportionalSliceManager()
            
            if model_path:
                self.slice_managers['enhanced'] = EnhancedSliceManager(model_path=model_path)
                logger.info(f"Enhanced slice manager initialized with model from {model_path}")
            
            # Create orchestrator
            if model_path:
                self.orchestrator = SliceOrchestrator(model_path=model_path)
                logger.info(f"Orchestrator initialized with model from {model_path}")
            else:
                self.orchestrator = SliceOrchestrator()
                logger.info("Orchestrator initialized without model")
            
            return True
        except Exception as e:
            logger.error(f"Error setting up simulation: {e}")
            return False
    
    def generate_traffic(self, steps=None, emergency_steps=None):
        """
        Generate traffic pattern for simulation.
        
        Args:
            steps (int): Number of time steps
            emergency_steps (list): List of steps with emergency events
        
        Returns:
            dict: Generated traffic pattern
        """
        if steps is None:
            steps = self.config.get('simulation', 'duration', default=100)
        
        # Generate traffic pattern
        self.traffic_data = generate_traffic_pattern(
            steps=steps,
            emergency_steps=emergency_steps
        )
        
        logger.info(f"Traffic pattern generated for {steps} steps")
        return self.traffic_data
    
    def run_simulation(self, traffic_data=None, manager_types=None):
        """
        Run the simulation.
        
        Args:
            traffic_data (dict): Traffic data to use
            manager_types (list): List of slice manager types to simulate
        
        Returns:
            dict: Simulation results
        """
        if traffic_data is None:
            if self.traffic_data is None:
                self.generate_traffic()
            traffic_data = self.traffic_data
        
        if manager_types is None:
            manager_types = list(self.slice_managers.keys())
        
        steps = traffic_data['steps']
        slice_types = self.config.get('slices', 'types', default=['eMBB', 'URLLC', 'mMTC'])
        
        # Initialize results
        results = {
            'steps': steps,
            'slice_types': slice_types,
            'is_emergency': traffic_data['is_emergency'],
            'emergency_steps': traffic_data['emergency_steps'],
            'managers': {}
        }
        
        # Get QoS thresholds
        thresholds = np.array([
            self.config.get('slices', 'qos_thresholds', 'eMBB', default=0.9),
            self.config.get('slices', 'qos_thresholds', 'URLLC', default=1.2),
            self.config.get('slices', 'qos_thresholds', 'mMTC', default=0.8)
        ])
        
        # Run simulation for each manager type
        for manager_type in manager_types:
            if manager_type not in self.slice_managers:
                logger.warning(f"Slice manager type '{manager_type}' not found, skipping")
                continue
            
            manager = self.slice_managers[manager_type]
            
            # Initialize arrays for recording
            allocations = np.zeros((steps, len(slice_types)))
            utilizations = np.zeros((steps, len(slice_types)))
            violations = np.zeros((steps, len(slice_types)), dtype=bool)
            
            logger.info(f"Running simulation with {manager_type} slice manager")
            
            # Run simulation steps
            for i in range(steps):
                # Check for emergency
                if traffic_data['is_emergency'][i]:
                    manager.set_emergency_mode(True)
                else:
                    manager.set_emergency_mode(False)
                
                # Get traffic for current step
                traffic_values = np.array([
                    traffic_data['traffic'][slice_type][i] for slice_type in slice_types
                ])
                
                # Allocate resources
                if i == 0:
                    # First step, no utilization yet
                    allocation = manager.allocate_resources(
                        traffic_load=np.mean(traffic_values),
                        utilization=np.zeros(len(slice_types))
                    )
                else:
                    # Use previous utilization
                    allocation = manager.allocate_resources(
                        traffic_load=np.mean(traffic_values),
                        utilization=utilizations[i-1]
                    )
                
                # Calculate utilization
                utilization = calculate_utilization(traffic_values, allocation)
                
                # Check for QoS violations
                violation = check_qos_violations(utilization, thresholds)
                
                # Record results
                allocations[i] = allocation
                utilizations[i] = utilization
                violations[i] = violation
            
            # Store results for this manager
            results['managers'][manager_type] = {
                'allocations': allocations.tolist(),
                'utilizations': utilizations.tolist(),
                'violations': violations.tolist(),
                'total_violations': int(np.sum(violations)),
                'violations_by_slice': [int(np.sum(violations[:, j])) for j in range(len(slice_types))]
            }
            
            logger.info(f"Simulation completed for {manager_type} slice manager")
            logger.info(f"Total violations: {results['managers'][manager_type]['total_violations']}")
        
        # Store results
        self.results = results
        
        return results
    
    def save_results(self, output_path=None):
        """
        Save simulation results.
        
        Args:
            output_path (str): Path to save results
        
        Returns:
            bool: Whether results were saved successfully
        """
        if output_path is None:
            # Generate default output path
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = os.path.join(
                self.config.get('system', 'results_dir', default='results'),
                f"simulation_{timestamp}"
            )
        
        # Create directory
        os.makedirs(output_path, exist_ok=True)
        
        try:
            # Save results to JSON
            results_path = os.path.join(output_path, 'simulation_results.json')
            save_json(self.results, results_path)
            
            # Save traffic data
            traffic_path = os.path.join(output_path, 'traffic_data.json')
            save_json(self.traffic_data, traffic_path)
            
            # Generate visualizations
            self.generate_visualizations(output_path)
            
            logger.info(f"Results saved to {output_path}")
            return True
        except Exception as e:
            logger.error(f"Error saving results: {e}")
            return False
    
    def generate_visualizations(self, output_path):
        """
        Generate visualizations of simulation results.
        
        Args:
            output_path (str): Path to save visualizations
        """
        # Visualize traffic
        traffic_viz_path = os.path.join(output_path, 'traffic_pattern.png')
        visualize_traffic(self.traffic_data, traffic_viz_path)
        
        # Compare static vs enhanced if available
        if 'static' in self.results['managers'] and 'enhanced' in self.results['managers']:
            # Get data
            steps = self.results['steps']
            static_data = self.results['managers']['static']
            enhanced_data = self.results['managers']['enhanced']
            
            # Convert to numpy arrays
            static_allocation = np.array(static_data['allocations'])
            enhanced_allocation = np.array(enhanced_data['allocations'])
            static_utilization = np.array(static_data['utilizations'])
            enhanced_utilization = np.array(enhanced_data['utilizations'])
            static_violations = np.array(static_data['violations'])
            enhanced_violations = np.array(enhanced_data['violations'])
            
            # Visualize allocation comparison
            alloc_viz_path = os.path.join(output_path, 'allocation_comparison.png')
            visualize_allocation_comparison(
                steps,
                static_allocation,
                enhanced_allocation,
                static_utilization,
                enhanced_utilization,
                self.results['is_emergency'],
                alloc_viz_path
            )
            
            # Visualize QoS violations
            qos_viz_path = os.path.join(output_path, 'qos_violations.png')
            visualize_qos_violations(
                steps,
                static_violations,
                enhanced_violations,
                self.results['is_emergency'],
                qos_viz_path
            )
        
        # Generate summary visualization
        self._generate_summary_visualization(output_path)
    
    def _generate_summary_visualization(self, output_path):
        """
        Generate summary visualization of simulation results.
        
        Args:
            output_path (str): Path to save visualization
        """
        # Create figure
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
        
        # Get slice types
        slice_types = self.results['slice_types']
        
        # Plot violations by slice type
        manager_types = list(self.results['managers'].keys())
        x = np.arange(len(slice_types))
        width = 0.8 / len(manager_types)
        
        for i, manager_type in enumerate(manager_types):
            violations = self.results['managers'][manager_type]['violations_by_slice']
            ax1.bar(x + i*width - 0.4 + width/2, violations, width, label=manager_type.capitalize())
        
        ax1.set_xlabel('Slice Type')
        ax1.set_ylabel('Number of Violations')
        ax1.set_title('QoS Violations by Slice Type')
        ax1.set_xticks(x)
        ax1.set_xticklabels(slice_types)
        ax1.legend()
        
        # Plot total violations
        total_violations = [self.results['managers'][manager_type]['total_violations'] 
                          for manager_type in manager_types]
        
        ax2.bar(manager_types, total_violations)
        ax2.set_xlabel('Slice Manager')
        ax2.set_ylabel('Number of Violations')
        ax2.set_title('Total QoS Violations')
        ax2.set_xticklabels([m.capitalize() for m in manager_types])
        
        # Add improvement percentage if enhanced is present
        if 'static' in self.results['managers'] and 'enhanced' in self.results['managers']:
            static_violations = self.results['managers']['static']['total_violations']
            enhanced_violations = self.results['managers']['enhanced']['total_violations']
            
            if static_violations > 0:
                improvement = (static_violations - enhanced_violations) / static_violations * 100
                ax2.text(1, enhanced_violations + 5, f"{improvement:.1f}% improvement", 
                        ha='center', va='bottom')
        
        plt.tight_layout()
        
        # Save
        summary_path = os.path.join(output_path, 'summary.png')
        plt.savefig(summary_path)
        plt.close()


def run_simulation(config_path=None, model_path=None, steps=100, output_path=None, emergency_steps=None):
    """
    Run a simulation with the given parameters.
    
    Args:
        config_path (str): Path to the configuration file
        model_path (str): Path to the trained model
        steps (int): Number of time steps
        output_path (str): Path to save results
        emergency_steps (list): List of steps with emergency events
    
    Returns:
        dict: Simulation results
    """
    # Create simulation environment
    sim = SliceSimulation(config_path)
    
    # Set up simulation
    sim.setup(model_path)
    
    # Generate traffic
    sim.generate_traffic(steps, emergency_steps)
    
    # Run simulation
    results = sim.run_simulation()
    
    # Save results
    sim.save_results(output_path)
    
    return results


def main():
    """Main function for running the simulation from command line."""
    parser = argparse.ArgumentParser(description='5G Network Slicing Simulation')
    parser.add_argument('--config', type=str, help='Path to configuration file')
    parser.add_argument('--model', type=str, help='Path to trained model')
    parser.add_argument('--steps', type=int, default=100, help='Number of simulation steps')
    parser.add_argument('--output', type=str, help='Path to save results')
    parser.add_argument('--emergency', type=str, help='Comma-separated list of emergency steps')
    
    args = parser.parse_args()
    
    # Parse emergency steps
    emergency_steps = None
    if args.emergency:
        try:
            emergency_steps = [int(s) for s in args.emergency.split(',')]
        except:
            logger.warning(f"Invalid emergency steps: {args.emergency}, using random events")
    
    # Run simulation
    run_simulation(
        config_path=args.config,
        model_path=args.model,
        steps=args.steps,
        output_path=args.output,
        emergency_steps=emergency_steps
    )


if __name__ == "__main__":
    main() 