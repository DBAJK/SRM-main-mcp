#!/usr/bin/env python3
"""
Interactive Demo for 5G Network Slicing with AI

This script provides an interactive demonstration of AI-based network slicing
optimization, showing real-time metrics and comparisons between AI and traditional
optimization approaches.
"""

import os
import sys
import time
import json
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
import matplotlib.gridspec as gridspec
import argparse
from datetime import datetime

# Add the parent directory to the path to import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from slicesim.slice_optimization import SliceOptimizer

class NetworkSimulator:
    """Simulates a 5G network with changing traffic patterns"""
    
    def __init__(self, scenario='baseline', duration=300):
        """Initialize the network simulator
        
        Args:
            scenario (str): Simulation scenario ('baseline', 'dynamic', 'emergency', 'smart_city')
            duration (int): Simulation duration in seconds
        """
        self.scenario = scenario
        self.duration = duration
        self.current_time = 0
        self.step = 0
        self.traffic_patterns = self._generate_traffic_patterns()
        
        # Initialize base stations and clients
        self.base_stations = self._initialize_base_stations()
        self.clients = self._initialize_clients()
        
        # Initialize metrics history
        self.metrics_history = {
            'traditional': {
                'latency': [],
                'throughput': [],
                'resource_utilization': [],
                'qoe': [],
                'time': []
            },
            'ai': {
                'latency': [],
                'throughput': [],
                'resource_utilization': [],
                'qoe': [],
                'time': []
            }
        }
        
        # Initialize optimizers
        self.traditional_optimizer = SliceOptimizer(use_ai=False)
        self.ai_optimizer = SliceOptimizer(use_ai=True)
        
        print(f"Initialized {scenario} scenario for {duration} seconds")
    
    def _generate_traffic_patterns(self):
        """Generate traffic patterns based on the scenario
        
        Returns:
            dict: Traffic patterns for each time step
        """
        patterns = {}
        time_steps = np.linspace(0, self.duration, 300)  # 300 time steps
        
        if self.scenario == 'baseline':
            # Baseline: Steady traffic with slight variations
            for t in time_steps:
                patterns[t] = {
                    'eMBB': 0.5 + 0.1 * np.sin(t/30),
                    'URLLC': 0.3 + 0.05 * np.cos(t/20),
                    'mMTC': 0.2 + 0.05 * np.sin(t/40)
                }
        
        elif self.scenario == 'dynamic':
            # Dynamic: Rapidly changing traffic patterns
            for t in time_steps:
                patterns[t] = {
                    'eMBB': 0.4 + 0.3 * np.sin(t/10),
                    'URLLC': 0.3 + 0.3 * np.cos(t/15),
                    'mMTC': 0.3 + 0.2 * np.sin(t/5)
                }
        
        elif self.scenario == 'emergency':
            # Emergency: Sudden spike in URLLC traffic
            for t in time_steps:
                if 100 <= t <= 200:  # Emergency period
                    patterns[t] = {
                        'eMBB': 0.3,
                        'URLLC': 0.6 + 0.1 * np.sin(t/10),
                        'mMTC': 0.1
                    }
                else:
                    patterns[t] = {
                        'eMBB': 0.5 + 0.1 * np.sin(t/30),
                        'URLLC': 0.3 + 0.05 * np.cos(t/20),
                        'mMTC': 0.2 + 0.05 * np.sin(t/40)
                    }
        
        elif self.scenario == 'smart_city':
            # Smart City: High mMTC traffic, periodic eMBB spikes
            for t in time_steps:
                embb_spike = 0.5 if (t % 50 < 10) else 0.3
                patterns[t] = {
                    'eMBB': embb_spike + 0.1 * np.sin(t/20),
                    'URLLC': 0.2 + 0.05 * np.cos(t/30),
                    'mMTC': 0.5 + 0.1 * np.sin(t/40)
                }
        
        return patterns
    
    def _initialize_base_stations(self):
        """Initialize base stations
        
        Returns:
            list: Base stations
        """
        return [
            {
                'id': 'bs1',
                'capacity': 10,
                'location': [0, 0],
                'slice_usage': {'eMBB': 0, 'URLLC': 0, 'mMTC': 0},
                'slice_allocation': {'eMBB': 0.33, 'URLLC': 0.33, 'mMTC': 0.34}
            },
            {
                'id': 'bs2',
                'capacity': 8,
                'location': [5, 5],
                'slice_usage': {'eMBB': 0, 'URLLC': 0, 'mMTC': 0},
                'slice_allocation': {'eMBB': 0.33, 'URLLC': 0.33, 'mMTC': 0.34}
            }
        ]
    
    def _initialize_clients(self):
        """Initialize clients
        
        Returns:
            list: Clients
        """
        clients = []
        client_id = 1
        
        # Add eMBB clients
        for i in range(10):
            clients.append({
                'id': client_id,
                'slice': 'eMBB',
                'base_station': 'bs1' if i < 5 else 'bs2',
                'data_rate': 1.0,
                'active': True
            })
            client_id += 1
        
        # Add URLLC clients
        for i in range(8):
            clients.append({
                'id': client_id,
                'slice': 'URLLC',
                'base_station': 'bs1' if i < 4 else 'bs2',
                'data_rate': 0.5,
                'active': True
            })
            client_id += 1
        
        # Add mMTC clients
        for i in range(15):
            clients.append({
                'id': client_id,
                'slice': 'mMTC',
                'base_station': 'bs1' if i < 8 else 'bs2',
                'data_rate': 0.2,
                'active': True
            })
            client_id += 1
        
        return clients
    
    def get_network_state(self):
        """Get the current network state
        
        Returns:
            dict: Current network state
        """
        # Update slice usage based on traffic patterns
        current_pattern = self._get_current_traffic_pattern()
        
        for bs in self.base_stations:
            bs_clients = [c for c in self.clients if c['base_station'] == bs['id']]
            for slice_type in ['eMBB', 'URLLC', 'mMTC']:
                slice_clients = [c for c in bs_clients if c['slice'] == slice_type]
                # Calculate usage based on client count and traffic pattern
                client_count = len(slice_clients)
                traffic_factor = current_pattern[slice_type]
                bs['slice_usage'][slice_type] = client_count * traffic_factor
        
        return {
            'time': self.current_time,
            'base_stations': self.base_stations,
            'clients': self.clients
        }
    
    def _get_current_traffic_pattern(self):
        """Get the traffic pattern for the current time
        
        Returns:
            dict: Current traffic pattern
        """
        # Find closest time point in patterns
        time_points = sorted(self.traffic_patterns.keys())
        closest_point = min(time_points, key=lambda x: abs(x - self.current_time))
        return self.traffic_patterns[closest_point]
    
    def step_simulation(self):
        """Advance the simulation by one step
        
        Returns:
            bool: Whether the simulation is complete
        """
        if self.current_time >= self.duration:
            return True  # Simulation complete
        
        # Get network state
        network_state = self.get_network_state()
        
        # Run traditional optimization
        traditional_allocation = self.traditional_optimizer.optimize_slices(network_state)
        
        # Run AI optimization
        ai_allocation = self.ai_optimizer.optimize_slices(network_state)
        
        # Calculate and record metrics
        self._calculate_and_record_metrics(network_state, traditional_allocation, ai_allocation)
        
        # Update time
        self.current_time += 1
        self.step += 1
        
        return False  # Simulation not complete
    
    def _calculate_and_record_metrics(self, network_state, traditional_allocation, ai_allocation):
        """Calculate and record metrics for both optimization approaches
        
        Args:
            network_state (dict): Current network state
            traditional_allocation (dict): Traditional optimization allocation
            ai_allocation (dict): AI optimization allocation
        """
        # Calculate metrics for traditional approach
        trad_metrics = self._calculate_metrics(network_state, traditional_allocation)
        
        # Calculate metrics for AI approach
        ai_metrics = self._calculate_metrics(network_state, ai_allocation)
        
        # Record metrics
        for metric in ['latency', 'throughput', 'resource_utilization', 'qoe']:
            self.metrics_history['traditional'][metric].append(trad_metrics[metric])
            self.metrics_history['ai'][metric].append(ai_metrics[metric])
        
        self.metrics_history['traditional']['time'].append(self.current_time)
        self.metrics_history['ai']['time'].append(self.current_time)
    
    def _calculate_metrics(self, network_state, slice_allocation):
        """Calculate metrics for a given allocation
        
        Args:
            network_state (dict): Current network state
            slice_allocation (dict): Slice allocation
            
        Returns:
            dict: Calculated metrics
        """
        # Initialize metrics
        metrics = {
            'latency': 0,
            'throughput': 0,
            'resource_utilization': 0,
            'qoe': 0
        }
        
        total_bs = len(network_state['base_stations'])
        if total_bs == 0:
            return metrics
        
        # Calculate metrics for each base station
        for bs in network_state['base_stations']:
            bs_id = bs['id']
            bs_clients = [c for c in network_state['clients'] if c['base_station'] == bs_id]
            bs_capacity = bs['capacity']
            
            if bs_id not in slice_allocation:
                continue
            
            bs_allocation = slice_allocation[bs_id]
            bs_usage = bs['slice_usage']
            
            # Calculate latency (lower is better)
            # Higher congestion (usage/allocation) increases latency
            latency_factors = []
            for slice_type in ['eMBB', 'URLLC', 'mMTC']:
                allocation = bs_allocation.get(slice_type, 0.33)
                usage = bs_usage.get(slice_type, 0)
                # Avoid division by zero
                congestion = usage / max(0.001, allocation * bs_capacity)
                
                # Weight by slice requirements (URLLC is most sensitive)
                weight = 3 if slice_type == 'URLLC' else (1 if slice_type == 'eMBB' else 0.5)
                latency_factor = congestion * weight
                
                if len(bs_clients) > 0:
                    latency_factors.append(latency_factor)
            
            if latency_factors:
                bs_latency = sum(latency_factors) / len(latency_factors)
                metrics['latency'] += bs_latency
            
            # Calculate throughput (higher is better)
            bs_throughput = 0
            for slice_type in ['eMBB', 'URLLC', 'mMTC']:
                allocation = bs_allocation.get(slice_type, 0.33)
                usage = bs_usage.get(slice_type, 0)
                
                # Calculate throughput based on allocation and usage
                # If allocation matches usage well, throughput is higher
                efficiency = 1 - min(1, abs(usage - allocation * bs_capacity) / max(0.001, allocation * bs_capacity))
                slice_throughput = usage * efficiency
                
                # Weight by slice requirements (eMBB cares most about throughput)
                weight = 3 if slice_type == 'eMBB' else (1 if slice_type == 'URLLC' else 0.5)
                bs_throughput += slice_throughput * weight
            
            metrics['throughput'] += bs_throughput
            
            # Calculate resource utilization (higher is better, but not over 1)
            total_usage = sum(bs_usage.values())
            utilization = min(1, total_usage / bs_capacity)
            metrics['resource_utilization'] += utilization
        
        # Average across base stations
        metrics['latency'] /= total_bs
        metrics['throughput'] /= total_bs
        metrics['resource_utilization'] /= total_bs
        
        # Calculate QoE based on other metrics
        # QoE increases with throughput and utilization, decreases with latency
        metrics['qoe'] = (metrics['throughput'] * 0.4 + 
                          metrics['resource_utilization'] * 0.3 -
                          metrics['latency'] * 0.3)
        
        # Normalize QoE to 0-1 range
        metrics['qoe'] = max(0, min(1, metrics['qoe']))
        
        return metrics
    
    def get_current_metrics(self):
        """Get the current metrics
        
        Returns:
            dict: Current metrics for both optimization approaches
        """
        result = {}
        
        for approach in ['traditional', 'ai']:
            if not self.metrics_history[approach]['time']:
                result[approach] = {
                    'latency': 0,
                    'throughput': 0,
                    'resource_utilization': 0,
                    'qoe': 0
                }
            else:
                result[approach] = {
                    'latency': self.metrics_history[approach]['latency'][-1],
                    'throughput': self.metrics_history[approach]['throughput'][-1],
                    'resource_utilization': self.metrics_history[approach]['resource_utilization'][-1],
                    'qoe': self.metrics_history[approach]['qoe'][-1]
                }
        
        return result
    
    def get_metrics_history(self):
        """Get the metrics history
        
        Returns:
            dict: Metrics history for both optimization approaches
        """
        return self.metrics_history
    
    def save_results(self, filename=None):
        """Save simulation results to file
        
        Args:
            filename (str): Filename to save results
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"results/{self.scenario}_results_{timestamp}.json"
        
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        # Save metrics history to file
        with open(filename, 'w') as f:
            json.dump(self.metrics_history, f, indent=2)
        
        print(f"Results saved to {filename}")
        
        # Also save plots
        self.plot_results(os.path.splitext(filename)[0] + '.png')
    
    def plot_results(self, save_path=None):
        """Plot the simulation results
        
        Args:
            save_path (str): Path to save the plot
        """
        # Create figure
        plt.figure(figsize=(15, 10))
        
        # Create subplots
        metrics = ['latency', 'throughput', 'resource_utilization', 'qoe']
        for i, metric in enumerate(metrics):
            plt.subplot(2, 2, i+1)
            
            for approach, color in [('traditional', 'blue'), ('ai', 'red')]:
                if not self.metrics_history[approach]['time']:
                    continue
                    
                plt.plot(
                    self.metrics_history[approach]['time'],
                    self.metrics_history[approach][metric],
                    label=f"{approach.capitalize()}",
                    color=color
                )
            
            plt.title(f"{metric.replace('_', ' ').title()}")
            plt.xlabel("Time (s)")
            plt.ylabel("Value")
            plt.legend()
            plt.grid(True)
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path)
            print(f"Plot saved to {save_path}")
        
        plt.show()

class InteractiveDemo:
    """Interactive demo for 5G network slicing with AI"""
    
    def __init__(self, scenario='baseline', duration=300, compare=True):
        """Initialize the interactive demo
        
        Args:
            scenario (str): Simulation scenario
            duration (int): Simulation duration in seconds
            compare (bool): Whether to compare AI and traditional approaches
        """
        self.simulator = NetworkSimulator(scenario, duration)
        self.compare = compare
        self.running = False
        self.speed = 1  # simulation steps per second
        
        # Create the figure and axes
        self.setup_plot()
        
        # Initialize the animation
        self.ani = FuncAnimation(self.fig, self.update, interval=1000/self.speed, blit=False)
    
    def setup_plot(self):
        """Set up the plot layout"""
        self.fig = plt.figure(figsize=(15, 8))
        gs = gridspec.GridSpec(2, 4, height_ratios=[1, 3])
        
        # Create subplots
        self.ax_control = plt.subplot(gs[0, :])
        self.ax_latency = plt.subplot(gs[1, 0])
        self.ax_throughput = plt.subplot(gs[1, 1])
        self.ax_utilization = plt.subplot(gs[1, 2])
        self.ax_qoe = plt.subplot(gs[1, 3])
        
        # Set titles
        self.ax_control.set_title(f"Scenario: {self.simulator.scenario.title()} - Control Panel")
        self.ax_latency.set_title("Latency (lower is better)")
        self.ax_throughput.set_title("Throughput (higher is better)")
        self.ax_utilization.set_title("Resource Utilization")
        self.ax_qoe.set_title("Quality of Experience")
        
        # Set up axes
        for ax in [self.ax_latency, self.ax_throughput, self.ax_utilization, self.ax_qoe]:
            ax.set_xlim(0, self.simulator.duration)
            ax.set_xlabel("Time (s)")
            ax.grid(True)
        
        self.ax_latency.set_ylim(0, 2)
        self.ax_throughput.set_ylim(0, 5)
        self.ax_utilization.set_ylim(0, 1)
        self.ax_qoe.set_ylim(0, 1)
        
        # Initialize plot lines
        self.lines = {}
        for approach, color in [('traditional', 'blue'), ('ai', 'red')]:
            self.lines[approach] = {
                'latency': self.ax_latency.plot([], [], label=f"{approach.capitalize()}", color=color)[0],
                'throughput': self.ax_throughput.plot([], [], label=f"{approach.capitalize()}", color=color)[0],
                'resource_utilization': self.ax_utilization.plot([], [], label=f"{approach.capitalize()}", color=color)[0],
                'qoe': self.ax_qoe.plot([], [], label=f"{approach.capitalize()}", color=color)[0]
            }
        
        # Add legends
        for ax in [self.ax_latency, self.ax_throughput, self.ax_utilization, self.ax_qoe]:
            ax.legend()
        
        # Add control panel elements using annotations
        self.control_elements = {}
        self.control_elements['time'] = self.ax_control.annotate(
            f"Time: 0/{self.simulator.duration} s",
            xy=(0.1, 0.5), xycoords='axes fraction',
            fontsize=12
        )
        
        self.control_elements['ai_metrics'] = self.ax_control.annotate(
            "AI Metrics: Latency=0.00, Throughput=0.00, Utilization=0.00, QoE=0.00",
            xy=(0.1, 0.3), xycoords='axes fraction',
            fontsize=10, color='red'
        )
        
        self.control_elements['trad_metrics'] = self.ax_control.annotate(
            "Traditional Metrics: Latency=0.00, Throughput=0.00, Utilization=0.00, QoE=0.00",
            xy=(0.1, 0.1), xycoords='axes fraction',
            fontsize=10, color='blue'
        )
        
        # Hide axes ticks for control panel
        self.ax_control.set_xticks([])
        self.ax_control.set_yticks([])
        
        plt.tight_layout()
    
    def start(self):
        """Start the simulation"""
        self.running = True
        plt.show()
    
    def update(self, frame):
        """Update the plot
        
        Args:
            frame: Animation frame
        """
        if not self.running:
            return
        
        # Step the simulation
        simulation_complete = self.simulator.step_simulation()
        if simulation_complete:
            self.running = False
            self.simulator.save_results()
            return
        
        # Update plot data
        metrics_history = self.simulator.get_metrics_history()
        current_metrics = self.simulator.get_current_metrics()
        
        for approach in ['traditional', 'ai']:
            for metric in ['latency', 'throughput', 'resource_utilization', 'qoe']:
                self.lines[approach][metric].set_data(
                    metrics_history[approach]['time'],
                    metrics_history[approach][metric]
                )
        
        # Update control panel
        self.control_elements['time'].set_text(f"Time: {self.simulator.current_time}/{self.simulator.duration} s")
        
        self.control_elements['ai_metrics'].set_text(
            f"AI Metrics: Latency={current_metrics['ai']['latency']:.2f}, "
            f"Throughput={current_metrics['ai']['throughput']:.2f}, "
            f"Utilization={current_metrics['ai']['resource_utilization']:.2f}, "
            f"QoE={current_metrics['ai']['qoe']:.2f}"
        )
        
        self.control_elements['trad_metrics'].set_text(
            f"Traditional Metrics: Latency={current_metrics['traditional']['latency']:.2f}, "
            f"Throughput={current_metrics['traditional']['throughput']:.2f}, "
            f"Utilization={current_metrics['traditional']['resource_utilization']:.2f}, "
            f"QoE={current_metrics['traditional']['qoe']:.2f}"
        )
        
        # Auto-adjust y-limits if needed
        for approach in ['traditional', 'ai']:
            if metrics_history[approach]['latency']:
                max_latency = max(metrics_history[approach]['latency'])
                if max_latency > self.ax_latency.get_ylim()[1]:
                    self.ax_latency.set_ylim(0, max_latency * 1.1)
            
            if metrics_history[approach]['throughput']:
                max_throughput = max(metrics_history[approach]['throughput'])
                if max_throughput > self.ax_throughput.get_ylim()[1]:
                    self.ax_throughput.set_ylim(0, max_throughput * 1.1)
        
        return self.lines

def main():
    """Main function to run the interactive demo"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Interactive Demo for 5G Network Slicing with AI')
    parser.add_argument('--scenario', type=str, default='baseline',
                        choices=['baseline', 'dynamic', 'emergency', 'smart_city'],
                        help='Simulation scenario')
    parser.add_argument('--duration', type=int, default=300,
                        help='Simulation duration in seconds')
    parser.add_argument('--compare', action='store_true',
                        help='Compare AI and traditional approaches')
    parser.add_argument('--headless', action='store_true',
                        help='Run in headless mode (no visualization)')
    
    args = parser.parse_args()
    
    if args.headless:
        # Run in headless mode
        simulator = NetworkSimulator(args.scenario, args.duration)
        print(f"Running headless simulation for {args.scenario} scenario ({args.duration} seconds)...")
        
        # Run simulation steps
        while not simulator.step_simulation():
            if simulator.step % 10 == 0:
                print(f"Simulation progress: {simulator.current_time}/{simulator.duration} seconds")
        
        # Save results
        simulator.save_results()
    else:
        # Run interactive demo
        demo = InteractiveDemo(args.scenario, args.duration, args.compare)
        demo.start()

if __name__ == "__main__":
    main() 