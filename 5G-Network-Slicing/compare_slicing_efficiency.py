#!/usr/bin/env python3
"""
Network Slicing Efficiency Comparison

This script compares three approaches to network slicing:
1. No-model approach (static allocation)
2. Simple reactive approach
3. Our enhanced model-based approach

The comparison demonstrates the efficiency gains of our model.
"""

import os
import numpy as np
import matplotlib.pyplot as plt
import tensorflow as tf
import argparse
import logging
import time
from datetime import datetime

# Import the slice managers
from slicesim.ai.slice_manager import EnhancedSliceManager, SliceManager

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SlicingEfficiencyComparison:
    """Comparison of different network slicing approaches"""
    
    def __init__(self, args):
        """Initialize the comparison
        
        Args:
            args: Command-line arguments
        """
        self.args = args
        self.sequence_length = 10
        self.out_steps = 5
        self.input_dim = 11
        self.duration = args.duration
        
        # Create output directory
        os.makedirs(args.output_dir, exist_ok=True)
        
        # Initialize slice managers
        self._initialize_slice_managers()
        
        # History buffer for visualization
        self.history = {
            'time': [],
            'traffic': [],
            'static_allocation': [],
            'reactive_allocation': [],
            'enhanced_allocation': [],
            'utilization': [],
            'qos_violations': {
                'static': {'embb': 0, 'urllc': 0, 'mmtc': 0, 'total': 0},
                'reactive': {'embb': 0, 'urllc': 0, 'mmtc': 0, 'total': 0},
                'enhanced': {'embb': 0, 'urllc': 0, 'mmtc': 0, 'total': 0}
            }
        }
        
        logger.info("Slicing efficiency comparison initialized")
    
    def _initialize_slice_managers(self):
        """Initialize slice managers"""
        # Create baseline slice manager
        self.reactive_manager = SliceManager(
            input_dim=self.input_dim,
            sequence_length=self.sequence_length,
            skip_training=True  # Skip training
        )
        
        # Create enhanced slice manager
        self.enhanced_manager = EnhancedSliceManager(
            input_dim=self.input_dim,
            sequence_length=self.sequence_length,
            out_steps=self.out_steps,
            checkpoint_dir=os.path.join(self.args.output_dir, "checkpoints"),
            skip_training=True  # Skip training
        )
        
        logger.info("Slice managers initialized with skip_training=True")
    
    def generate_scenario_data(self):
        """Generate synthetic data for the selected scenario
        
        Returns:
            tuple: (states, traffic)
        """
        # Initialize parameters based on scenario
        if self.args.scenario == 'baseline':
            volatility = 0.1
            emergency_prob = 0.0
            embb_factor = 1.0
            urllc_factor = 1.0
            mmtc_factor = 1.0
        elif self.args.scenario == 'dynamic':
            volatility = 0.3
            emergency_prob = 0.05
            embb_factor = 1.2
            urllc_factor = 0.8
            mmtc_factor = 1.0
        elif self.args.scenario == 'emergency':
            volatility = 0.2
            emergency_prob = 0.8
            embb_factor = 0.7
            urllc_factor = 1.5
            mmtc_factor = 0.8
        elif self.args.scenario == 'smart_city':
            volatility = 0.15
            emergency_prob = 0.0
            embb_factor = 0.9
            urllc_factor = 0.7
            mmtc_factor = 1.4
        else:  # mixed
            volatility = 0.2
            emergency_prob = 0.1
            embb_factor = 1.0
            urllc_factor = 1.0
            mmtc_factor = 1.0
        
        # Generate states
        states = []
        traffic = []
        time_of_day = np.random.uniform(0, 1)
        day_of_week = np.random.uniform(0, 1)
        
        # Initial allocation and utilization
        allocation = np.array([1/3, 1/3, 1/3])
        utilization = np.array([0.5, 0.5, 0.5])
        
        # Track active events
        active_events = []
        
        for i in range(self.duration + self.sequence_length):
            # Update time
            time_of_day = (time_of_day + 0.01) % 1.0
            if time_of_day < 0.01:
                day_of_week = (day_of_week + 0.01) % 1.0
            
            # Time of day effects
            time_factor = np.sin(time_of_day * 2 * np.pi) * 0.3 + 0.5
            
            # Check for emergency events
            if np.random.random() < emergency_prob and 'emergency' not in active_events:
                active_events.append('emergency')
                event_duration = np.random.randint(10, 30)
                active_events.append(('emergency_end', i + event_duration))
                logger.info(f"Emergency event started at step {i}, will last for {event_duration} steps")
            
            # Check for event endings
            events_to_remove = []
            for event in active_events:
                if isinstance(event, tuple) and event[0] == 'emergency_end' and i >= event[1]:
                    events_to_remove.append(event)
                    events_to_remove.append('emergency')
                    logger.info(f"Emergency event ended at step {i}")
            
            for event in events_to_remove:
                if event in active_events:
                    active_events.remove(event)
            
            # Generate traffic pattern
            if 'emergency' in active_events:
                # High baseline with emergency spikes
                traffic_load = 0.7 + 0.2 * np.sin(time_of_day * 2 * np.pi) + volatility * np.random.randn()
                traffic_load += np.random.uniform(0.5, 1.0)  # Emergency spike
                utilization[1] += np.random.uniform(0.5, 1.0)  # URLLC spike during emergency
            else:
                # Regular daily pattern
                traffic_load = 0.5 + time_factor + volatility * np.random.randn()
            
            # Clip traffic load
            traffic_load = np.clip(traffic_load, 0.1, 2.0)
            traffic.append(traffic_load)
            
            # Update utilization based on traffic and allocation
            for j in range(3):
                # Apply slice-specific factors
                slice_factors = [embb_factor, urllc_factor, mmtc_factor]
                target_util = traffic_load * slice_factors[j] / (allocation[j] + 0.1)
                utilization[j] = 0.7 * utilization[j] + 0.3 * (target_util + 0.1 * np.random.randn())
            
            # Clip utilization
            utilization = np.clip(utilization, 0.1, 2.0)
            
            # Create state vector
            state = np.array([
                traffic_load,
                time_of_day,
                day_of_week,
                allocation[0],
                allocation[1],
                allocation[2],
                utilization[0],
                utilization[1],
                utilization[2],
                0.5,  # client_count
                0.6   # bs_count
            ])
            
            states.append(state)
        
        return np.array(states), np.array(traffic)
    
    def generate_static_allocation(self):
        """Generate static slice allocation (no model)
        
        Returns:
            numpy.ndarray: Static allocation
        """
        # Static allocation is always equal distribution
        return np.array([1/3, 1/3, 1/3])
    
    def check_qos_violations(self, utilization, allocation_type):
        """Check for QoS violations
        
        Args:
            utilization (numpy.ndarray): Current utilization
            allocation_type (str): Type of allocation (static, reactive, enhanced)
        """
        # QoS thresholds
        thresholds = {
            'embb': 1.5,  # eMBB threshold
            'urllc': 1.2,  # URLLC threshold
            'mmtc': 1.8   # mMTC threshold
        }
        
        # Check each slice
        if utilization[0] > thresholds['embb']:
            self.history['qos_violations'][allocation_type]['embb'] += 1
            self.history['qos_violations'][allocation_type]['total'] += 1
        
        if utilization[1] > thresholds['urllc']:
            self.history['qos_violations'][allocation_type]['urllc'] += 1
            self.history['qos_violations'][allocation_type]['total'] += 1
        
        if utilization[2] > thresholds['mmtc']:
            self.history['qos_violations'][allocation_type]['mmtc'] += 1
            self.history['qos_violations'][allocation_type]['total'] += 1
    
    def run(self):
        """Run the slicing efficiency comparison"""
        logger.info(f"Starting slicing efficiency comparison with {self.args.scenario} scenario")
        
        # Generate scenario data
        states, traffic = self.generate_scenario_data()
        
        # Initialize history buffers for slice managers
        for i in range(self.sequence_length):
            self.reactive_manager.update_history_buffer(states[i])
            self.enhanced_manager.update_history_buffer(states[i])
        
        # Allocations and utilizations
        static_allocations = []
        reactive_allocations = []
        enhanced_allocations = []
        utilizations = []
        
        # Static allocation (no model)
        static_allocation = self.generate_static_allocation()
        
        # Run simulation
        for i in range(self.sequence_length, len(states)):
            current_state = states[i]
            current_utilization = current_state[6:9]  # eMBB, URLLC, mMTC utilization
            
            try:
                # Get reactive allocation
                reactive_allocation = self.reactive_manager.get_optimal_slice_allocation(current_state)
                
                # Get enhanced allocation
                enhanced_allocation = self.enhanced_manager.get_optimal_slice_allocation(
                    current_state, return_all_steps=False
                )
                
                # Check for QoS violations
                self.check_qos_violations(current_utilization, 'static')
                self.check_qos_violations(current_utilization, 'reactive')
                self.check_qos_violations(current_utilization, 'enhanced')
                
                # Store results
                static_allocations.append(static_allocation)
                reactive_allocations.append(reactive_allocation)
                enhanced_allocations.append(enhanced_allocation)
                utilizations.append(current_utilization)
                
                # Update history buffer for visualization
                self.history['time'].append(i - self.sequence_length)
                self.history['traffic'].append(traffic[i])
                self.history['static_allocation'].append(static_allocation)
                self.history['reactive_allocation'].append(reactive_allocation)
                self.history['enhanced_allocation'].append(enhanced_allocation)
                self.history['utilization'].append(current_utilization)
                
                # Log progress
                if (i - self.sequence_length) % 10 == 0:
                    logger.info(f"Step {i - self.sequence_length}/{self.duration}: "
                               f"Traffic={traffic[i]:.2f}")
            except Exception as e:
                logger.error(f"Error at step {i - self.sequence_length}: {str(e)}")
                logger.error(f"Skipping this step and continuing...")
                continue
        
        # Visualize results
        self._visualize_results()
        
        # Calculate and display efficiency metrics
        self._calculate_efficiency_metrics()
        
        logger.info("Comparison completed")
    
    def _visualize_results(self):
        """Visualize simulation results"""
        # Convert lists to numpy arrays for easier manipulation
        time = np.array(self.history['time'])
        traffic = np.array(self.history['traffic'])
        static_allocation = np.array(self.history['static_allocation'])
        reactive_allocation = np.array(self.history['reactive_allocation'])
        enhanced_allocation = np.array(self.history['enhanced_allocation'])
        utilization = np.array(self.history['utilization'])
        
        # Create figure
        plt.figure(figsize=(15, 12))
        
        # Plot traffic
        plt.subplot(4, 1, 1)
        plt.plot(time, traffic, 'k-', label='Traffic Load')
        plt.title(f'Network Traffic - {self.args.scenario.capitalize()} Scenario')
        plt.ylabel('Load')
        plt.legend()
        plt.grid(True)
        
        # Plot eMBB allocations
        plt.subplot(4, 1, 2)
        plt.plot(time, static_allocation[:, 0], 'b--', alpha=0.7, label='Static eMBB')
        plt.plot(time, reactive_allocation[:, 0], 'g--', alpha=0.7, label='Reactive eMBB')
        plt.plot(time, enhanced_allocation[:, 0], 'r-', label='Enhanced eMBB')
        plt.plot(time, utilization[:, 0], 'k-', label='eMBB Utilization')
        plt.axhline(y=1.5, color='k', linestyle=':', label='QoS Threshold')
        plt.title('eMBB Slice Allocation Comparison')
        plt.ylabel('Allocation / Utilization')
        plt.legend()
        plt.grid(True)
        
        # Plot URLLC allocations
        plt.subplot(4, 1, 3)
        plt.plot(time, static_allocation[:, 1], 'b--', alpha=0.7, label='Static URLLC')
        plt.plot(time, reactive_allocation[:, 1], 'g--', alpha=0.7, label='Reactive URLLC')
        plt.plot(time, enhanced_allocation[:, 1], 'r-', label='Enhanced URLLC')
        plt.plot(time, utilization[:, 1], 'k-', label='URLLC Utilization')
        plt.axhline(y=1.2, color='k', linestyle=':', label='QoS Threshold')
        plt.title('URLLC Slice Allocation Comparison')
        plt.ylabel('Allocation / Utilization')
        plt.legend()
        plt.grid(True)
        
        # Plot mMTC allocations
        plt.subplot(4, 1, 4)
        plt.plot(time, static_allocation[:, 2], 'b--', alpha=0.7, label='Static mMTC')
        plt.plot(time, reactive_allocation[:, 2], 'g--', alpha=0.7, label='Reactive mMTC')
        plt.plot(time, enhanced_allocation[:, 2], 'r-', label='Enhanced mMTC')
        plt.plot(time, utilization[:, 2], 'k-', label='mMTC Utilization')
        plt.axhline(y=1.8, color='k', linestyle=':', label='QoS Threshold')
        plt.title('mMTC Slice Allocation Comparison')
        plt.xlabel('Time Step')
        plt.ylabel('Allocation / Utilization')
        plt.legend()
        plt.grid(True)
        
        plt.tight_layout()
        plt.savefig(os.path.join(self.args.output_dir, f"{self.args.scenario}_slicing_comparison.png"))
        plt.close()
        
        # Create QoS violations bar chart
        plt.figure(figsize=(12, 8))
        
        # Get violation data
        violations = self.history['qos_violations']
        labels = ['eMBB', 'URLLC', 'mMTC', 'Total']
        static_data = [violations['static']['embb'], violations['static']['urllc'], 
                       violations['static']['mmtc'], violations['static']['total']]
        reactive_data = [violations['reactive']['embb'], violations['reactive']['urllc'], 
                        violations['reactive']['mmtc'], violations['reactive']['total']]
        enhanced_data = [violations['enhanced']['embb'], violations['enhanced']['urllc'], 
                        violations['enhanced']['mmtc'], violations['enhanced']['total']]
        
        x = np.arange(len(labels))
        width = 0.25
        
        fig, ax = plt.subplots(figsize=(12, 8))
        rects1 = ax.bar(x - width, static_data, width, label='Static Allocation')
        rects2 = ax.bar(x, reactive_data, width, label='Reactive Allocation')
        rects3 = ax.bar(x + width, enhanced_data, width, label='Enhanced Model')
        
        ax.set_ylabel('Number of Violations')
        ax.set_title('QoS Violations by Allocation Method')
        ax.set_xticks(x)
        ax.set_xticklabels(labels)
        ax.legend()
        
        # Add value labels
        def autolabel(rects):
            for rect in rects:
                height = rect.get_height()
                ax.annotate(f'{height}',
                            xy=(rect.get_x() + rect.get_width() / 2, height),
                            xytext=(0, 3),
                            textcoords="offset points",
                            ha='center', va='bottom')
        
        autolabel(rects1)
        autolabel(rects2)
        autolabel(rects3)
        
        plt.tight_layout()
        plt.savefig(os.path.join(self.args.output_dir, f"{self.args.scenario}_qos_violations.png"))
        plt.close()
    
    def _calculate_efficiency_metrics(self):
        """Calculate and display efficiency metrics"""
        violations = self.history['qos_violations']
        
        # Calculate improvement percentages
        if violations['static']['total'] > 0:
            reactive_improvement = ((violations['static']['total'] - violations['reactive']['total']) / 
                                    violations['static']['total'] * 100)
            enhanced_improvement = ((violations['static']['total'] - violations['enhanced']['total']) / 
                                   violations['static']['total'] * 100)
        else:
            reactive_improvement = 0
            enhanced_improvement = 0
        
        if violations['reactive']['total'] > 0:
            model_vs_reactive = ((violations['reactive']['total'] - violations['enhanced']['total']) / 
                                violations['reactive']['total'] * 100)
        else:
            model_vs_reactive = 0
        
        # Log results
        logger.info("\n" + "="*50)
        logger.info(f"EFFICIENCY METRICS - {self.args.scenario.upper()} SCENARIO")
        logger.info("="*50)
        logger.info(f"QoS Violations:")
        logger.info(f"  Static Allocation: {violations['static']['total']} violations")
        logger.info(f"  Reactive Allocation: {violations['reactive']['total']} violations")
        logger.info(f"  Enhanced Model: {violations['enhanced']['total']} violations")
        logger.info("\nImprovement Percentages:")
        logger.info(f"  Reactive vs Static: {reactive_improvement:.2f}% reduction in violations")
        logger.info(f"  Enhanced vs Static: {enhanced_improvement:.2f}% reduction in violations")
        logger.info(f"  Enhanced vs Reactive: {model_vs_reactive:.2f}% reduction in violations")
        logger.info("="*50)
        
        # Save metrics to file
        metrics = {
            'scenario': self.args.scenario,
            'duration': self.duration,
            'qos_violations': violations,
            'improvements': {
                'reactive_vs_static': reactive_improvement,
                'enhanced_vs_static': enhanced_improvement,
                'enhanced_vs_reactive': model_vs_reactive
            }
        }
        
        # Save to JSON
        import json
        with open(os.path.join(self.args.output_dir, f"{self.args.scenario}_efficiency_metrics.json"), 'w') as f:
            json.dump(metrics, f, indent=2)


def parse_args():
    """Parse command-line arguments"""
    parser = argparse.ArgumentParser(description='Network Slicing Efficiency Comparison')
    parser.add_argument('--scenario', type=str, default='emergency',
                        choices=['baseline', 'dynamic', 'emergency', 'smart_city', 'mixed'],
                        help='Traffic scenario type')
    parser.add_argument('--duration', type=int, default=100,
                        help='Simulation duration in steps')
    parser.add_argument('--output_dir', type=str, default='results/efficiency_comparison',
                        help='Output directory for results')
    
    return parser.parse_args()


if __name__ == '__main__':
    # Parse arguments
    args = parse_args()
    
    # Create output directory
    os.makedirs(args.output_dir, exist_ok=True)
    
    # Print TensorFlow version and GPU availability
    logger.info(f"TensorFlow version: {tf.__version__}")
    logger.info(f"GPU available: {len(tf.config.list_physical_devices('GPU')) > 0}")
    
    # Run comparison
    comparison = SlicingEfficiencyComparison(args)
    comparison.run() 