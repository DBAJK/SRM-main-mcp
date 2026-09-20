#!/usr/bin/env python3
"""
Real-time Network Slicing Demo with Enhanced Autoregressive LSTM Predictor

This script demonstrates real-time network slice allocation using the enhanced
autoregressive LSTM predictor in a simulated 5G network environment.

Features:
- Real-time traffic simulation with different scenarios
- Multi-step prediction and proactive slice allocation
- Dynamic visualization of slice allocations
- Performance comparison with baseline methods
- Metrics tracking for QoS evaluation
"""

import os
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
import tensorflow as tf
import time
import argparse
import logging
from datetime import datetime

# Import the enhanced slice manager
from slicesim.ai.slice_manager import EnhancedSliceManager, SliceManager

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class NetworkSimulator:
    """Simulates a 5G network with dynamic traffic patterns"""
    
    def __init__(self, scenario='mixed', duration=100, noise_level=0.1):
        """Initialize the network simulator
        
        Args:
            scenario (str): Traffic scenario type
            duration (int): Simulation duration in steps
            noise_level (float): Level of random noise in traffic
        """
        self.scenario = scenario
        self.duration = duration
        self.noise_level = noise_level
        self.current_step = 0
        
        # Network state variables
        self.traffic_load = 0.5
        self.time_of_day = np.random.uniform(0, 1)
        self.day_of_week = np.random.uniform(0, 1)
        self.slice_allocation = np.array([1/3, 1/3, 1/3])  # Initial equal allocation
        self.slice_utilization = np.array([0.5, 0.5, 0.5])  # Initial utilization
        self.client_count = 0.5
        self.bs_count = 0.6
        
        # History of network states
        self.history = []
        
        # QoS metrics
        self.qos_violations = {
            'embb': 0,
            'urllc': 0,
            'mmtc': 0
        }
        
        # Initialize scenario parameters
        self._initialize_scenario()
        
        logger.info(f"Network simulator initialized with {scenario} scenario")
    
    def _initialize_scenario(self):
        """Initialize scenario-specific parameters"""
        if self.scenario == 'baseline':
            self.traffic_pattern = 'daily'
            self.volatility = 0.1
            self.emergency_prob = 0.0
            self.spike_prob = 0.05
        elif self.scenario == 'dynamic':
            self.traffic_pattern = 'volatile'
            self.volatility = 0.3
            self.emergency_prob = 0.05
            self.spike_prob = 0.2
        elif self.scenario == 'emergency':
            self.traffic_pattern = 'emergency'
            self.volatility = 0.2
            self.emergency_prob = 0.8
            self.spike_prob = 0.3
        elif self.scenario == 'smart_city':
            self.traffic_pattern = 'iot'
            self.volatility = 0.15
            self.emergency_prob = 0.0
            self.spike_prob = 0.1
        else:  # mixed
            self.traffic_pattern = 'mixed'
            self.volatility = 0.2
            self.emergency_prob = 0.1
            self.spike_prob = 0.15
    
    def get_current_state(self):
        """Get the current network state
        
        Returns:
            numpy.ndarray: Current state vector
        """
        return np.array([
            self.traffic_load,
            self.time_of_day,
            self.day_of_week,
            self.slice_allocation[0],  # eMBB
            self.slice_allocation[1],  # URLLC
            self.slice_allocation[2],  # mMTC
            self.slice_utilization[0],  # eMBB utilization
            self.slice_utilization[1],  # URLLC utilization
            self.slice_utilization[2],  # mMTC utilization
            self.client_count,
            self.bs_count
        ])
    
    def step(self):
        """Simulate one time step
        
        Returns:
            numpy.ndarray: New network state
        """
        # Store current state in history
        self.history.append(self.get_current_state())
        
        # Update time
        self.time_of_day = (self.time_of_day + 0.01) % 1.0
        if self.time_of_day < 0.01:  # New day
            self.day_of_week = (self.day_of_week + 0.01) % 1.0
        
        # Update traffic based on scenario
        self._update_traffic()
        
        # Update utilization based on allocation and traffic
        self._update_utilization()
        
        # Check for QoS violations
        self._check_qos_violations()
        
        # Increment step counter
        self.current_step += 1
        
        return self.get_current_state()
    
    def _update_traffic(self):
        """Update traffic patterns based on scenario"""
        # Base traffic follows daily pattern
        if self.traffic_pattern == 'daily':
            # Daily cycle with peak during day
            time_factor = np.sin(self.time_of_day * 2 * np.pi) * 0.3 + 0.5
            self.traffic_load = 0.5 + time_factor + self.noise_level * np.random.randn()
        
        elif self.traffic_pattern == 'volatile':
            # More random variations
            time_factor = np.sin(self.time_of_day * 2 * np.pi) * 0.2 + 0.5
            day_factor = np.sin(self.day_of_week * 2 * np.pi) * 0.1
            self.traffic_load = 0.4 + time_factor + day_factor + self.volatility * np.random.randn()
            
            # Random traffic spikes
            if np.random.random() < self.spike_prob:
                self.traffic_load += np.random.uniform(0.3, 0.8)
        
        elif self.traffic_pattern == 'emergency':
            # High baseline with spikes
            self.traffic_load = 0.7 + 0.2 * np.sin(self.time_of_day * 2 * np.pi) + self.volatility * np.random.randn()
            
            # Emergency events
            if np.random.random() < self.emergency_prob:
                self.traffic_load += np.random.uniform(0.5, 1.0)
                
                # During emergency, URLLC utilization spikes
                self.slice_utilization[1] += np.random.uniform(0.5, 1.0)
        
        elif self.traffic_pattern == 'iot':
            # IoT traffic patterns (higher at night)
            time_factor = 0.3 - 0.2 * np.sin(self.time_of_day * 2 * np.pi)
            self.traffic_load = 0.6 + time_factor + self.volatility * np.random.randn()
            
            # IoT devices active at night
            if self.time_of_day < 0.25 or self.time_of_day > 0.75:
                self.slice_utilization[2] += np.random.uniform(0.2, 0.5)  # mMTC spike
        
        else:  # mixed
            # Combination of patterns
            time_factor = np.sin(self.time_of_day * 2 * np.pi) * 0.3 + 0.5
            self.traffic_load = 0.5 + time_factor + self.volatility * np.random.randn()
            
            # Random events
            if np.random.random() < self.spike_prob:
                event_type = np.random.choice(['embb', 'urllc', 'mmtc'])
                if event_type == 'embb':
                    self.slice_utilization[0] += np.random.uniform(0.3, 0.7)
                elif event_type == 'urllc':
                    self.slice_utilization[1] += np.random.uniform(0.3, 0.7)
                else:
                    self.slice_utilization[2] += np.random.uniform(0.3, 0.7)
        
        # Update client count based on traffic
        self.client_count = 0.3 + 0.5 * self.traffic_load + 0.1 * np.random.randn()
        
        # Clip values to valid ranges
        self.traffic_load = np.clip(self.traffic_load, 0.1, 2.0)
        self.client_count = np.clip(self.client_count, 0.1, 1.0)
    
    def _update_utilization(self):
        """Update slice utilization based on allocation and traffic"""
        # Calculate utilization based on allocation and traffic
        # If allocation is insufficient for the traffic, utilization will be high
        for i in range(3):
            # Base utilization depends on traffic and allocation
            target_util = self.traffic_load / (self.slice_allocation[i] + 0.1)
            
            # Add some randomness
            noise = self.noise_level * np.random.randn()
            
            # Smooth transition from previous utilization (70% previous, 30% new)
            self.slice_utilization[i] = 0.7 * self.slice_utilization[i] + 0.3 * (target_util + noise)
        
        # Clip utilization to valid range
        self.slice_utilization = np.clip(self.slice_utilization, 0.1, 2.0)
    
    def _check_qos_violations(self):
        """Check for QoS violations based on utilization"""
        # eMBB: High throughput, moderate latency
        if self.slice_utilization[0] > 1.5:
            self.qos_violations['embb'] += 1
        
        # URLLC: Ultra-low latency, high reliability
        if self.slice_utilization[1] > 1.2:
            self.qos_violations['urllc'] += 1
        
        # mMTC: Massive connectivity
        if self.slice_utilization[2] > 1.8:
            self.qos_violations['mmtc'] += 1
    
    def apply_slice_allocation(self, allocation):
        """Apply a new slice allocation
        
        Args:
            allocation (numpy.ndarray): New slice allocation
        """
        # Ensure allocation sums to 1
        allocation = allocation / np.sum(allocation)
        
        # Apply new allocation
        self.slice_allocation = allocation
    
    def get_qos_metrics(self):
        """Get QoS metrics
        
        Returns:
            dict: QoS metrics
        """
        total_steps = max(1, self.current_step)
        return {
            'embb_violation_rate': self.qos_violations['embb'] / total_steps,
            'urllc_violation_rate': self.qos_violations['urllc'] / total_steps,
            'mmtc_violation_rate': self.qos_violations['mmtc'] / total_steps,
            'total_violations': sum(self.qos_violations.values()),
            'avg_embb_util': np.mean([s[6] for s in self.history]) if self.history else 0,
            'avg_urllc_util': np.mean([s[7] for s in self.history]) if self.history else 0,
            'avg_mmtc_util': np.mean([s[8] for s in self.history]) if self.history else 0
        }


class RealTimeSlicingDemo:
    """Real-time network slicing demonstration"""
    
    def __init__(self, args):
        """Initialize the demo
        
        Args:
            args: Command-line arguments
        """
        self.args = args
        self.sequence_length = args.sequence_length
        self.out_steps = args.out_steps
        self.input_dim = 11
        
        # Create output directory
        os.makedirs(args.output_dir, exist_ok=True)
        
        # Initialize network simulator
        self.simulator = NetworkSimulator(
            scenario=args.scenario,
            duration=args.duration,
            noise_level=args.noise_level
        )
        
        # Initialize slice managers
        self._initialize_slice_managers()
        
        # Metrics for comparison
        self.metrics = {
            'baseline': {
                'allocations': [],
                'utilizations': [],
                'qos_violations': 0
            },
            'enhanced': {
                'allocations': [],
                'utilizations': [],
                'qos_violations': 0,
                'predictions': []
            }
        }
        
        # History buffer for visualization
        self.history_buffer = {
            'time': [],
            'traffic': [],
            'baseline_allocation': [],
            'enhanced_allocation': [],
            'utilization': []
        }
        
        logger.info("Real-time slicing demo initialized")
    
    def _initialize_slice_managers(self):
        """Initialize baseline and enhanced slice managers"""
        # Model paths
        baseline_model_path = os.path.join(self.args.output_dir, "baseline_lstm_model.h5")
        enhanced_model_path = os.path.join(self.args.output_dir, "autoregressive_lstm_model.h5")
        
        # Create baseline slice manager
        self.baseline_manager = SliceManager(
            input_dim=self.input_dim,
            sequence_length=self.sequence_length,
            model_path=baseline_model_path if os.path.exists(baseline_model_path) else None
        )
        
        # Create enhanced slice manager
        self.enhanced_manager = EnhancedSliceManager(
            input_dim=self.input_dim,
            sequence_length=self.sequence_length,
            out_steps=self.out_steps,
            model_path=enhanced_model_path if os.path.exists(enhanced_model_path) else None,
            checkpoint_dir=os.path.join(self.args.output_dir, "checkpoints")
        )
        
        logger.info("Slice managers initialized")
    
    def run(self):
        """Run the real-time slicing demo"""
        logger.info(f"Starting real-time slicing demo with {self.args.scenario} scenario")
        
        # Initialize simulator
        simulator_baseline = NetworkSimulator(
            scenario=self.args.scenario,
            duration=self.args.duration,
            noise_level=self.args.noise_level
        )
        
        simulator_enhanced = NetworkSimulator(
            scenario=self.args.scenario,
            duration=self.args.duration,
            noise_level=self.args.noise_level
        )
        
        # Initialize history buffers
        history_baseline = []
        history_enhanced = []
        
        # Warm up history buffer
        for _ in range(self.sequence_length - 1):
            state_baseline = simulator_baseline.step()
            state_enhanced = simulator_enhanced.step()
            
            history_baseline.append(state_baseline)
            history_enhanced.append(state_enhanced)
            
            # Update history buffers in slice managers
            self.baseline_manager.update_history_buffer(state_baseline)
            self.enhanced_manager.update_history_buffer(state_enhanced)
        
        # Run simulation
        for step in range(self.args.duration):
            # Get current state
            state_baseline = simulator_baseline.step()
            state_enhanced = simulator_enhanced.step()
            
            # Get optimal slice allocation from baseline manager
            baseline_allocation = self.baseline_manager.get_optimal_slice_allocation(state_baseline)
            
            # Get optimal slice allocation from enhanced manager (with multi-step prediction)
            enhanced_allocation = self.enhanced_manager.get_optimal_slice_allocation(
                state_enhanced, return_all_steps=self.args.show_predictions
            )
            
            # If showing predictions, use first step for allocation
            if self.args.show_predictions:
                # Store predictions for visualization
                self.metrics['enhanced']['predictions'].append(enhanced_allocation)
                # Use first step for actual allocation
                actual_enhanced_allocation = enhanced_allocation[0]
            else:
                actual_enhanced_allocation = enhanced_allocation
            
            # Apply allocations to simulators
            simulator_baseline.apply_slice_allocation(baseline_allocation)
            simulator_enhanced.apply_slice_allocation(actual_enhanced_allocation)
            
            # Store metrics
            self.metrics['baseline']['allocations'].append(baseline_allocation)
            self.metrics['baseline']['utilizations'].append(simulator_baseline.slice_utilization.copy())
            
            self.metrics['enhanced']['allocations'].append(
                actual_enhanced_allocation if not self.args.show_predictions else enhanced_allocation[0]
            )
            self.metrics['enhanced']['utilizations'].append(simulator_enhanced.slice_utilization.copy())
            
            # Update history buffer for visualization
            self.history_buffer['time'].append(step)
            self.history_buffer['traffic'].append(simulator_enhanced.traffic_load)
            self.history_buffer['baseline_allocation'].append(baseline_allocation)
            self.history_buffer['enhanced_allocation'].append(
                actual_enhanced_allocation if not self.args.show_predictions else enhanced_allocation[0]
            )
            self.history_buffer['utilization'].append(simulator_enhanced.slice_utilization.copy())
            
            # Log progress
            if step % 10 == 0:
                logger.info(f"Step {step}/{self.args.duration}: "
                           f"Traffic={simulator_enhanced.traffic_load:.2f}, "
                           f"Enhanced allocation=[{actual_enhanced_allocation[0]:.2f}, "
                           f"{actual_enhanced_allocation[1]:.2f}, {actual_enhanced_allocation[2]:.2f}]")
        
        # Get final QoS metrics
        baseline_qos = simulator_baseline.get_qos_metrics()
        enhanced_qos = simulator_enhanced.get_qos_metrics()
        
        self.metrics['baseline']['qos_violations'] = baseline_qos['total_violations']
        self.metrics['enhanced']['qos_violations'] = enhanced_qos['total_violations']
        
        # Print results
        logger.info("Simulation completed")
        logger.info(f"Baseline QoS violations: {baseline_qos['total_violations']}")
        logger.info(f"Enhanced QoS violations: {enhanced_qos['total_violations']}")
        logger.info(f"QoS improvement: {(baseline_qos['total_violations'] - enhanced_qos['total_violations']) / max(1, baseline_qos['total_violations']) * 100:.2f}%")
        
        # Visualize results
        if self.args.show_plots:
            self._visualize_results()
        
        return self.metrics
    
    def _visualize_results(self):
        """Visualize simulation results"""
        # Convert lists to numpy arrays for easier manipulation
        time = np.array(self.history_buffer['time'])
        traffic = np.array(self.history_buffer['traffic'])
        baseline_allocation = np.array(self.history_buffer['baseline_allocation'])
        enhanced_allocation = np.array(self.history_buffer['enhanced_allocation'])
        utilization = np.array(self.history_buffer['utilization'])
        
        # Create figure
        plt.figure(figsize=(15, 10))
        
        # Plot traffic
        plt.subplot(3, 1, 1)
        plt.plot(time, traffic, 'k-', label='Traffic Load')
        plt.title('Network Traffic')
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
        
        plt.title('Slice Allocation')
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
        plt.savefig(os.path.join(self.args.output_dir, f"{self.args.scenario}_simulation.png"))
        plt.show()
        
        # If showing predictions, visualize them
        if self.args.show_predictions and self.metrics['enhanced']['predictions']:
            self._visualize_predictions()
    
    def _visualize_predictions(self):
        """Visualize multi-step predictions"""
        # Get a sample of predictions for visualization
        sample_indices = np.linspace(0, len(self.metrics['enhanced']['predictions'])-1, 4, dtype=int)
        
        plt.figure(figsize=(15, 10))
        
        for i, idx in enumerate(sample_indices):
            plt.subplot(2, 2, i+1)
            
            # Get prediction
            prediction = self.metrics['enhanced']['predictions'][idx]
            
            # Create time steps
            steps = np.arange(self.out_steps)
            
            # Plot prediction
            plt.plot(steps, prediction[:, 0], 'b-o', label='eMBB')
            plt.plot(steps, prediction[:, 1], 'r-o', label='URLLC')
            plt.plot(steps, prediction[:, 2], 'g-o', label='mMTC')
            
            plt.title(f'Multi-step Prediction at t={idx}')
            plt.xlabel('Future Step')
            plt.ylabel('Allocation Ratio')
            plt.legend()
            plt.grid(True)
        
        plt.tight_layout()
        plt.savefig(os.path.join(self.args.output_dir, f"{self.args.scenario}_predictions.png"))
        plt.show()
        
        # Create animated visualization of predictions over time
        if self.args.animate and len(self.metrics['enhanced']['predictions']) > 10:
            self._create_prediction_animation()
    
    def _create_prediction_animation(self):
        """Create animated visualization of predictions over time"""
        # Create figure
        fig, ax = plt.subplots(figsize=(10, 6))
        
        # Initialize lines
        lines = [
            ax.plot([], [], 'b-o', label='eMBB')[0],
            ax.plot([], [], 'r-o', label='URLLC')[0],
            ax.plot([], [], 'g-o', label='mMTC')[0]
        ]
        
        # Set up plot
        ax.set_xlim(0, self.out_steps - 1)
        ax.set_ylim(0, 1)
        ax.set_xlabel('Future Step')
        ax.set_ylabel('Allocation Ratio')
        ax.set_title('Multi-step Prediction Animation')
        ax.legend()
        ax.grid(True)
        
        # Time step text
        time_text = ax.text(0.02, 0.95, '', transform=ax.transAxes)
        
        # Animation update function
        def update(frame):
            # Get prediction for this frame
            prediction = self.metrics['enhanced']['predictions'][frame]
            
            # Update lines
            for i, line in enumerate(lines):
                line.set_data(np.arange(self.out_steps), prediction[:, i])
            
            # Update time text
            time_text.set_text(f'Time Step: {frame}')
            
            return lines + [time_text]
        
        # Create animation
        anim = FuncAnimation(
            fig, update, frames=range(0, len(self.metrics['enhanced']['predictions']), 2),
            interval=200, blit=True
        )
        
        # Save animation
        anim.save(os.path.join(self.args.output_dir, f"{self.args.scenario}_prediction_animation.gif"), 
                 writer='pillow', fps=5)
        
        plt.close()


def parse_args():
    """Parse command-line arguments"""
    parser = argparse.ArgumentParser(description='Real-time Network Slicing Demo')
    parser.add_argument('--scenario', type=str, default='mixed',
                        choices=['baseline', 'dynamic', 'emergency', 'smart_city', 'mixed'],
                        help='Traffic scenario type')
    parser.add_argument('--duration', type=int, default=100,
                        help='Simulation duration in steps')
    parser.add_argument('--noise_level', type=float, default=0.1,
                        help='Level of random noise in traffic')
    parser.add_argument('--sequence_length', type=int, default=10,
                        help='Input sequence length for LSTM')
    parser.add_argument('--out_steps', type=int, default=5,
                        help='Number of future steps to predict')
    parser.add_argument('--output_dir', type=str, default='results/realtime_demo',
                        help='Output directory for results')
    parser.add_argument('--show_plots', action='store_true',
                        help='Show plots during execution')
    parser.add_argument('--show_predictions', action='store_true',
                        help='Show multi-step predictions')
    parser.add_argument('--animate', action='store_true',
                        help='Create animated visualization of predictions')
    
    return parser.parse_args()


if __name__ == '__main__':
    # Parse arguments
    args = parse_args()
    
    # Create output directory
    os.makedirs(args.output_dir, exist_ok=True)
    
    # Print TensorFlow version and GPU availability
    logger.info(f"TensorFlow version: {tf.__version__}")
    logger.info(f"GPU available: {tf.config.list_physical_devices('GPU')}")
    
    # Run demo
    demo = RealTimeSlicingDemo(args)
    metrics = demo.run()
    
    # Save metrics
    np.save(os.path.join(args.output_dir, f"{args.scenario}_metrics.npy"), metrics)
    
    logger.info(f"Demo completed. Results saved to {args.output_dir}") 