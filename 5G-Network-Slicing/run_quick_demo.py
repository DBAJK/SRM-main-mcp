#!/usr/bin/env python3
"""
Quick Network Slicing Demo with Enhanced Autoregressive LSTM Predictor

This script demonstrates network slice allocation using pre-trained models
without retraining, comparing baseline and enhanced approaches.
"""

import os
import numpy as np
import matplotlib.pyplot as plt
import tensorflow as tf
import argparse
import logging

# Import the slice managers
from slicesim.ai.slice_manager import EnhancedSliceManager, SliceManager

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class QuickSlicingDemo:
    """Quick network slicing demonstration using pre-trained models"""
    
    def __init__(self, args):
        """Initialize the demo
        
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
        
        # Initialize slice managers with skip_training=True
        self._initialize_slice_managers()
        
        # History buffer for visualization
        self.history = {
            'time': [],
            'traffic': [],
            'baseline_allocation': [],
            'enhanced_allocation': [],
            'utilization': []
        }
        
        logger.info("Quick slicing demo initialized")
    
    def _initialize_slice_managers(self):
        """Initialize baseline and enhanced slice managers with skip_training=True"""
        # Create baseline slice manager
        self.baseline_manager = SliceManager(
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
            tuple: (states, traffic_pattern)
        """
        # Initialize parameters based on scenario
        if self.args.scenario == 'baseline':
            volatility = 0.1
            emergency_prob = 0.0
        elif self.args.scenario == 'dynamic':
            volatility = 0.3
            emergency_prob = 0.05
        elif self.args.scenario == 'emergency':
            volatility = 0.2
            emergency_prob = 0.8
        elif self.args.scenario == 'smart_city':
            volatility = 0.15
            emergency_prob = 0.0
        else:  # mixed
            volatility = 0.2
            emergency_prob = 0.1
        
        # Generate states
        states = []
        traffic = []
        time_of_day = np.random.uniform(0, 1)
        day_of_week = np.random.uniform(0, 1)
        
        # Initial allocation and utilization
        allocation = np.array([1/3, 1/3, 1/3])
        utilization = np.array([0.5, 0.5, 0.5])
        
        for i in range(self.duration + self.sequence_length):
            # Update time
            time_of_day = (time_of_day + 0.01) % 1.0
            if time_of_day < 0.01:
                day_of_week = (day_of_week + 0.01) % 1.0
            
            # Generate traffic pattern
            if self.args.scenario == 'emergency':
                # High baseline with emergency spikes
                traffic_load = 0.7 + 0.2 * np.sin(time_of_day * 2 * np.pi) + volatility * np.random.randn()
                
                # Emergency events
                if np.random.random() < emergency_prob:
                    traffic_load += np.random.uniform(0.5, 1.0)
                    utilization[1] += np.random.uniform(0.5, 1.0)  # URLLC spike
            else:
                # Regular daily pattern
                time_factor = np.sin(time_of_day * 2 * np.pi) * 0.3 + 0.5
                traffic_load = 0.5 + time_factor + volatility * np.random.randn()
            
            # Clip traffic load
            traffic_load = np.clip(traffic_load, 0.1, 2.0)
            traffic.append(traffic_load)
            
            # Update utilization based on traffic and allocation
            for j in range(3):
                target_util = traffic_load / (allocation[j] + 0.1)
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
    
    def run(self):
        """Run the quick slicing demo"""
        logger.info(f"Starting quick slicing demo with {self.args.scenario} scenario")
        
        # Generate scenario data
        states, traffic = self.generate_scenario_data()
        
        # Initialize history buffers
        for i in range(self.sequence_length):
            self.baseline_manager.update_history_buffer(states[i])
            self.enhanced_manager.update_history_buffer(states[i])
        
        # Allocations and utilizations
        baseline_allocations = []
        enhanced_allocations = []
        enhanced_predictions = []
        utilizations = []
        
        # Run simulation
        for i in range(self.sequence_length, len(states)):
            current_state = states[i]
            
            # Get baseline allocation
            baseline_allocation = self.baseline_manager.get_optimal_slice_allocation(current_state)
            
            # Get enhanced allocation with multi-step prediction
            enhanced_allocation = self.enhanced_manager.get_optimal_slice_allocation(
                current_state, return_all_steps=True
            )
            
            # Store results
            baseline_allocations.append(baseline_allocation)
            enhanced_allocations.append(enhanced_allocation[0])  # First step
            enhanced_predictions.append(enhanced_allocation)  # All steps
            utilizations.append(current_state[6:9])  # eMBB, URLLC, mMTC utilization
            
            # Update history buffer for visualization
            self.history['time'].append(i - self.sequence_length)
            self.history['traffic'].append(traffic[i])
            self.history['baseline_allocation'].append(baseline_allocation)
            self.history['enhanced_allocation'].append(enhanced_allocation[0])
            self.history['utilization'].append(current_state[6:9])
            
            # Log progress
            if (i - self.sequence_length) % 10 == 0:
                logger.info(f"Step {i - self.sequence_length}/{self.duration}: "
                           f"Traffic={traffic[i]:.2f}")
        
        # Visualize results
        self._visualize_results()
        
        # Visualize predictions
        self._visualize_predictions(enhanced_predictions)
        
        logger.info("Demo completed")
    
    def _visualize_results(self):
        """Visualize simulation results"""
        # Convert lists to numpy arrays for easier manipulation
        time = np.array(self.history['time'])
        traffic = np.array(self.history['traffic'])
        baseline_allocation = np.array(self.history['baseline_allocation'])
        enhanced_allocation = np.array(self.history['enhanced_allocation'])
        utilization = np.array(self.history['utilization'])
        
        # Create figure
        plt.figure(figsize=(15, 10))
        
        # Plot traffic
        plt.subplot(3, 1, 1)
        plt.plot(time, traffic, 'k-', label='Traffic Load')
        plt.title(f'Network Traffic - {self.args.scenario.capitalize()} Scenario')
        plt.ylabel('Load')
        plt.legend()
        plt.grid(True)
        
        # Plot slice allocations
        plt.subplot(3, 1, 2)
        
        # Baseline allocations
        plt.plot(time, baseline_allocation[:, 0], 'b--', alpha=0.7, label='Baseline eMBB')
        plt.plot(time, baseline_allocation[:, 1], 'r--', alpha=0.7, label='Baseline URLLC')
        plt.plot(time, baseline_allocation[:, 2], 'g--', alpha=0.7, label='Baseline mMTC')
        
        # Enhanced allocations
        plt.plot(time, enhanced_allocation[:, 0], 'b-', label='Enhanced eMBB')
        plt.plot(time, enhanced_allocation[:, 1], 'r-', label='Enhanced URLLC')
        plt.plot(time, enhanced_allocation[:, 2], 'g-', label='Enhanced mMTC')
        
        plt.title('Slice Allocation Comparison')
        plt.ylabel('Allocation Ratio')
        plt.legend()
        plt.grid(True)
        
        # Plot utilization
        plt.subplot(3, 1, 3)
        plt.plot(time, utilization[:, 0], 'b-', label='eMBB Utilization')
        plt.plot(time, utilization[:, 1], 'r-', label='URLLC Utilization')
        plt.plot(time, utilization[:, 2], 'g-', label='mMTC Utilization')
        
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
        plt.savefig(os.path.join(self.args.output_dir, f"{self.args.scenario}_results.png"))
        plt.show()
    
    def _visualize_predictions(self, predictions):
        """Visualize multi-step predictions"""
        # Get sample predictions at different time points
        sample_indices = [10, int(len(predictions)/3), int(2*len(predictions)/3), len(predictions)-10]
        
        plt.figure(figsize=(15, 10))
        
        for i, idx in enumerate(sample_indices):
            plt.subplot(2, 2, i+1)
            
            # Get prediction
            prediction = predictions[idx]
            
            # Create time steps
            steps = np.arange(self.out_steps)
            
            # Plot prediction
            plt.plot(steps, prediction[:, 0], 'b-o', label='eMBB')
            plt.plot(steps, prediction[:, 1], 'r-o', label='URLLC')
            plt.plot(steps, prediction[:, 2], 'g-o', label='mMTC')
            
            plt.title(f'Multi-step Prediction at t={self.history["time"][idx]}')
            plt.xlabel('Future Step')
            plt.ylabel('Allocation Ratio')
            plt.legend()
            plt.grid(True)
        
        plt.tight_layout()
        plt.savefig(os.path.join(self.args.output_dir, f"{self.args.scenario}_predictions.png"))
        plt.show()


def parse_args():
    """Parse command-line arguments"""
    parser = argparse.ArgumentParser(description='Quick Network Slicing Demo')
    parser.add_argument('--scenario', type=str, default='emergency',
                        choices=['baseline', 'dynamic', 'emergency', 'smart_city', 'mixed'],
                        help='Traffic scenario type')
    parser.add_argument('--duration', type=int, default=100,
                        help='Simulation duration in steps')
    parser.add_argument('--output_dir', type=str, default='results/quick_demo',
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
    
    # Run demo
    demo = QuickSlicingDemo(args)
    demo.run() 