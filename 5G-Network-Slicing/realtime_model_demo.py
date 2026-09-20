#!/usr/bin/env python3
"""
Real-time Network Slicing Demo with Enhanced Autoregressive LSTM Predictor

This script provides a real-time demonstration of the enhanced autoregressive LSTM
predictor for 5G network slicing. It continuously takes input data, processes it
through the trained model, and compares the results with traditional slicing values.

Perfect for hackathon demonstrations showing the benefits of AI-based slicing.
"""

import os
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
import time
import argparse
import logging
import threading
from datetime import datetime
import tensorflow as tf
from queue import Queue
import keyboard

# Import the enhanced slice manager
from slicesim.ai.slice_manager import EnhancedSliceManager, SliceManager

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class RealTimeSlicingDemo:
    """Real-time demonstration of network slicing with AI"""
    
    def __init__(self, args):
        """Initialize the demo
        
        Args:
            args: Command line arguments
        """
        self.args = args
        self.duration = args.duration
        self.scenario = args.scenario
        self.noise_level = args.noise_level
        self.sequence_length = args.sequence_length
        self.out_steps = args.out_steps
        self.output_dir = args.output_dir
        self.show_plots = args.show_plots
        
        # Create output directory if it doesn't exist
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
            
        # Initialize network simulator
        self.simulator = NetworkSimulator(
            scenario=self.scenario,
            duration=self.duration,
            noise_level=self.noise_level
        )
        
        # Initialize slice managers
        self._initialize_slice_managers()
        
        # History for plotting
        self.history = {
            'time': [],
            'traditional_allocation': [],
            'ai_allocation': [],
            'slice_utilization': [],
            'qos_violations': {'traditional': [], 'ai': []}
        }
        
        # Setup visualization
        self._setup_visualization()
        
        # Input queue for manual inputs
        self.input_queue = Queue()
        
        logger.info(f"Real-time slicing demo initialized with {self.scenario} scenario")
    
    def _initialize_slice_managers(self):
        """Initialize traditional and AI-based slice managers"""
        # Traditional slice manager
        self.traditional_manager = SliceManager(
            input_dim=11,
            sequence_length=self.sequence_length,
            skip_training=False  # Train on synthetic data
        )
        
        # Enhanced AI slice manager with autoregressive LSTM
        self.ai_manager = EnhancedSliceManager(
            input_dim=11,
            sequence_length=self.sequence_length,
            out_steps=self.out_steps,
            skip_training=False  # Train on synthetic data
        )
        
        logger.info("Slice managers initialized and trained")
    
    def _setup_visualization(self):
        """Setup visualization for real-time plotting"""
        if self.show_plots:
            self.fig, self.axs = plt.subplots(2, 2, figsize=(14, 8))
            self.fig.suptitle(f"5G Network Slicing Real-time Comparison - {self.scenario.capitalize()} Scenario", fontsize=16)
            
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
        """Run the real-time demo"""
        logger.info(f"Starting real-time slicing demo with {self.scenario} scenario")
        
        # Start input thread
        input_thread = threading.Thread(target=self._input_listener)
        input_thread.daemon = True
        input_thread.start()
        
        # Print instructions
        print("\n=== REAL-TIME 5G NETWORK SLICING DEMO ===")
        print("This demo shows real-time comparison between traditional and AI-based slicing")
        print("Press 'e' to trigger an emergency event")
        print("Press 's' to trigger a traffic spike")
        print("Press 'q' to quit the demo\n")
        
        # Main simulation loop
        try:
            for step in range(self.duration):
                if step % 10 == 0:
                    print(f"\nStep {step}/{self.duration}")
                
                # Check for user input
                self._process_user_input()
                
                # Get current network state
                current_state = self.simulator.get_current_state()
                
                # Get slice allocations
                traditional_allocation = self.traditional_manager.get_optimal_slice_allocation(current_state)
                ai_allocation = self.ai_manager.get_optimal_slice_allocation(current_state)
                
                # Print current allocations
                self._print_allocations(step, traditional_allocation, ai_allocation)
                
                # Apply AI allocation to the network
                self.simulator.apply_slice_allocation(ai_allocation)
                
                # Step the simulation
                self.simulator.step()
                
                # Record history
                self._record_history(step, traditional_allocation, ai_allocation)
                
                # Update visualization
                if self.show_plots and step % 2 == 0:  # Update every 2 steps
                    self._update_visualization()
                
                # Sleep to simulate real-time
                time.sleep(0.5)
            
            # Show final results
            self._show_final_results()
            
            # Save results
            self._save_results()
            
            if self.show_plots:
                plt.tight_layout()
                plt.savefig(os.path.join(self.output_dir, "real_time_comparison.png"))
                if self.args.show_plots:
                    plt.show()
                    
        except KeyboardInterrupt:
            print("\nDemo interrupted by user")
            self._save_results()
    
    def _input_listener(self):
        """Listen for keyboard input"""
        print("Input listener started. Press 'e' for emergency, 's' for spike, 'q' to quit.")
        
        # Monitor for key presses
        keyboard.add_hotkey('e', lambda: self.input_queue.put('emergency'))
        keyboard.add_hotkey('s', lambda: self.input_queue.put('spike'))
        keyboard.add_hotkey('q', lambda: self.input_queue.put('quit'))
        
        # Keep the listener running
        keyboard.wait('q')
    
    def _process_user_input(self):
        """Process user input from the queue"""
        if not self.input_queue.empty():
            user_input = self.input_queue.get()
            
            if user_input == 'emergency':
                print("\n*** EMERGENCY EVENT TRIGGERED ***")
                # Trigger emergency in URLLC slice
                self.simulator.slice_utilization[1] += np.random.uniform(0.6, 1.0)
                
            elif user_input == 'spike':
                print("\n*** TRAFFIC SPIKE TRIGGERED ***")
                # General traffic spike
                self.simulator.traffic_load += np.random.uniform(0.4, 0.8)
                
            elif user_input == 'quit':
                print("\nExiting demo...")
                raise KeyboardInterrupt
    
    def _print_allocations(self, step, traditional_allocation, ai_allocation):
        """Print current allocations"""
        print(f"Step {step}:")
        print(f"  Traditional: eMBB={traditional_allocation[0]:.2f}, URLLC={traditional_allocation[1]:.2f}, mMTC={traditional_allocation[2]:.2f}")
        print(f"  AI-based:    eMBB={ai_allocation[0]:.2f}, URLLC={ai_allocation[1]:.2f}, mMTC={ai_allocation[2]:.2f}")
        
        # Calculate difference
        diff = ai_allocation - traditional_allocation
        print(f"  Difference:  eMBB={diff[0]:+.2f}, URLLC={diff[1]:+.2f}, mMTC={diff[2]:+.2f}")
        
        # Print current utilization
        util = self.simulator.slice_utilization
        print(f"  Utilization: eMBB={util[0]:.2f}, URLLC={util[1]:.2f}, mMTC={util[2]:.2f}")
    
    def _record_history(self, step, traditional_allocation, ai_allocation):
        """Record history for plotting"""
        self.history['time'].append(step)
        self.history['traditional_allocation'].append(traditional_allocation.copy())
        self.history['ai_allocation'].append(ai_allocation.copy())
        self.history['slice_utilization'].append(self.simulator.slice_utilization.copy())
        
        # Record QoS violations
        qos_violations = self.simulator.get_qos_metrics()
        self.history['qos_violations']['traditional'].append(sum(qos_violations.values()))
        self.history['qos_violations']['ai'].append(sum(qos_violations.values()))
    
    def _update_visualization(self):
        """Update the visualization"""
        if not self.show_plots:
            return
        
        # Clear all axes
        for ax in self.axs:
            ax.clear()
        
        # 1. Slice allocation comparison
        self.axs[0].set_title("Slice Allocation Comparison")
        self.axs[0].set_xlabel("Time Step")
        self.axs[0].set_ylabel("Allocation")
        
        time_points = self.history['time']
        
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
        
        # 2. Slice utilization
        self.axs[1].set_title("Slice Utilization")
        self.axs[1].set_xlabel("Time Step")
        self.axs[1].set_ylabel("Utilization")
        
        for i, slice_type in enumerate(self.slice_types):
            util_values = [util[i] for util in self.history['slice_utilization']]
            self.axs[1].plot(time_points, util_values, '-', 
                           color=self.slice_colors[slice_type], 
                           label=slice_type)
            
            # Add threshold lines
            if slice_type == "eMBB":
                threshold = 1.5
            elif slice_type == "URLLC":
                threshold = 1.2
            else:  # mMTC
                threshold = 1.8
                
            self.axs[1].axhline(y=threshold, color=self.slice_colors[slice_type], 
                              linestyle=':', alpha=0.7)
        
        self.axs[1].legend(loc='upper right')
        self.axs[1].grid(True, linestyle='--', alpha=0.7)
        
        # 3. QoS violations
        self.axs[2].set_title("Cumulative QoS Violations")
        self.axs[2].set_xlabel("Time Step")
        self.axs[2].set_ylabel("Violations")
        
        # Calculate cumulative violations
        trad_violations = np.cumsum(self.history['qos_violations']['traditional'])
        ai_violations = np.cumsum(self.history['qos_violations']['ai'])
        
        self.axs[2].plot(time_points, trad_violations, '--', color='gray', 
                       label="Traditional")
        self.axs[2].plot(time_points, ai_violations, '-', color='green', 
                       label="AI-based")
        
        self.axs[2].legend(loc='upper left')
        self.axs[2].grid(True, linestyle='--', alpha=0.7)
        
        # 4. Allocation difference
        self.axs[3].set_title("AI vs Traditional Allocation Difference")
        self.axs[3].set_xlabel("Time Step")
        self.axs[3].set_ylabel("Difference")
        
        for i, slice_type in enumerate(self.slice_types):
            diff_values = [ai[i] - trad[i] for ai, trad in 
                          zip(self.history['ai_allocation'], 
                              self.history['traditional_allocation'])]
            self.axs[3].plot(time_points, diff_values, '-', 
                           color=self.slice_colors[slice_type], 
                           label=slice_type)
        
        self.axs[3].axhline(y=0, color='black', linestyle='-', alpha=0.3)
        self.axs[3].legend(loc='upper right')
        self.axs[3].grid(True, linestyle='--', alpha=0.7)
        
        # Update the figure
        self.fig.tight_layout()
        plt.pause(0.01)
    
    def _show_final_results(self):
        """Show final results of the demo"""
        print("\n=== FINAL RESULTS ===")
        
        # Calculate QoS violations
        trad_violations = sum(self.history['qos_violations']['traditional'])
        ai_violations = sum(self.history['qos_violations']['ai'])
        
        print(f"Traditional QoS violations: {trad_violations}")
        print(f"AI-based QoS violations: {ai_violations}")
        
        if trad_violations > 0:
            improvement = (trad_violations - ai_violations) / trad_violations * 100
            print(f"Improvement: {improvement:.2f}%")
        
        # Calculate average allocation difference
        avg_diff = np.zeros(3)
        for ai, trad in zip(self.history['ai_allocation'], self.history['traditional_allocation']):
            avg_diff += np.abs(ai - trad)
        avg_diff /= len(self.history['time'])
        
        print(f"Average allocation difference:")
        print(f"  eMBB: {avg_diff[0]:.4f}")
        print(f"  URLLC: {avg_diff[1]:.4f}")
        print(f"  mMTC: {avg_diff[2]:.4f}")
    
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
        
        with open(os.path.join(self.output_dir, 'history.json'), 'w') as f:
            json.dump(json_history, f)
        
        # Save final metrics
        trad_violations = sum(self.history['qos_violations']['traditional'])
        ai_violations = sum(self.history['qos_violations']['ai'])
        
        if trad_violations > 0:
            improvement = (trad_violations - ai_violations) / trad_violations * 100
        else:
            improvement = 0
        
        metrics = {
            'traditional_violations': trad_violations,
            'ai_violations': ai_violations,
            'improvement': improvement
        }
        
        with open(os.path.join(self.output_dir, 'metrics.json'), 'w') as f:
            json.dump(metrics, f)
        
        logger.info(f"Results saved to {self.output_dir}")


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
        """Get QoS violation metrics
        
        Returns:
            dict: QoS violation counts
        """
        return self.qos_violations


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Real-time Network Slicing Demo')
    
    parser.add_argument('--scenario', type=str, default='dynamic',
                        choices=['baseline', 'dynamic', 'emergency', 'smart_city', 'mixed'],
                        help='Traffic scenario type')
    
    parser.add_argument('--duration', type=int, default=100,
                        help='Simulation duration in steps')
    
    parser.add_argument('--noise_level', type=float, default=0.1,
                        help='Level of random noise in traffic')
    
    parser.add_argument('--sequence_length', type=int, default=10,
                        help='Length of input sequence for LSTM')
    
    parser.add_argument('--out_steps', type=int, default=5,
                        help='Number of future steps to predict')
    
    parser.add_argument('--output_dir', type=str, default='results/realtime_demo',
                        help='Directory to save results')
    
    parser.add_argument('--show_plots', action='store_true',
                        help='Show real-time plots')
    
    return parser.parse_args()


if __name__ == "__main__":
    # Check TensorFlow version and GPU availability
    logger.info(f"TensorFlow version: {tf.__version__}")
    logger.info(f"GPU available: {len(tf.config.list_physical_devices('GPU')) > 0}")
    
    # Parse command line arguments
    args = parse_args()
    
    # Create and run the demo
    demo = RealTimeSlicingDemo(args)
    demo.run() 