#!/usr/bin/env python3
"""
5G Network Slicing - Orchestrator Demo

This script demonstrates the capabilities of the orchestrator
without relying on a trained model or scaler.
"""

import os
import numpy as np
import time
import matplotlib.pyplot as plt
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SimpleOrchestrator:
    """Simple orchestrator for demonstration purposes."""
    
    def __init__(self):
        """Initialize the orchestrator."""
        # Current allocation and utilization
        self.allocation = np.array([0.4, 0.4, 0.2])  # [eMBB, URLLC, mMTC]
        self.utilization = np.array([0.0, 0.0, 0.0])
        
        # Thresholds for QoS violations
        self.thresholds = np.array([0.9, 1.2, 0.8])
        
        # State
        self.is_emergency = False
        self.is_special_event = False
        self.is_iot_surge = False
        
        # Traffic history
        self.traffic_history = []
        
        # Create output directory
        self.output_dir = f"results/orchestrator_demo_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        os.makedirs(self.output_dir, exist_ok=True)
        
        logger.info("Simple orchestrator initialized")
    
    def set_emergency_mode(self, is_emergency):
        """
        Set emergency mode.
        
        Args:
            is_emergency (bool): Whether there's an emergency
        """
        self.is_emergency = is_emergency
        logger.info(f"Emergency mode set to {is_emergency}")
    
    def set_special_event_mode(self, is_special_event):
        """
        Set special event mode.
        
        Args:
            is_special_event (bool): Whether there's a special event
        """
        self.is_special_event = is_special_event
        logger.info(f"Special event mode set to {is_special_event}")
    
    def set_iot_surge_mode(self, is_iot_surge):
        """
        Set IoT surge mode.
        
        Args:
            is_iot_surge (bool): Whether there's an IoT surge
        """
        self.is_iot_surge = is_iot_surge
        logger.info(f"IoT surge mode set to {is_iot_surge}")
    
    def generate_traffic(self):
        """
        Generate traffic based on current state.
        
        Returns:
            numpy.ndarray: Traffic for each slice
        """
        # Base traffic
        base_traffic = np.array([0.4, 0.3, 0.2])
        
        # Add time-based variation
        hour_of_day = datetime.now().hour / 24.0
        day_of_week = datetime.now().weekday() / 6.0
        
        # Daily pattern (peak during day, low at night)
        daily_factor = 0.3 * np.sin(2 * np.pi * hour_of_day)
        
        # Weekly pattern (higher on weekdays)
        weekly_factor = 0.2 * (1 - day_of_week)
        
        # Apply patterns
        traffic = base_traffic * (1 + daily_factor + weekly_factor)
        
        # Add random variation
        traffic += np.random.normal(0, 0.1, 3)
        
        # Apply event effects
        if self.is_emergency:
            # During emergency, increase URLLC traffic
            traffic[0] *= 0.8  # eMBB reduced
            traffic[1] *= 2.0  # URLLC increased
            traffic[2] *= 0.9  # mMTC slightly reduced
        
        if self.is_special_event:
            # During special event, increase eMBB traffic
            traffic[0] *= 1.5  # eMBB increased
            traffic[1] *= 0.8  # URLLC reduced
            traffic[2] *= 1.0  # mMTC unchanged
        
        if self.is_iot_surge:
            # During IoT surge, increase mMTC traffic
            traffic[0] *= 0.9  # eMBB slightly reduced
            traffic[1] *= 0.9  # URLLC slightly reduced
            traffic[2] *= 1.8  # mMTC increased
        
        # Ensure traffic is positive
        traffic = np.clip(traffic, 0.1, 2.0)
        
        # Add to history
        self.traffic_history.append(traffic)
        if len(self.traffic_history) > 100:
            self.traffic_history = self.traffic_history[-100:]
        
        return traffic
    
    def update_allocation(self):
        """
        Update resource allocation based on current state.
        
        Returns:
            numpy.ndarray: Updated allocation
        """
        if self.is_emergency:
            # During emergency, prioritize URLLC
            target_allocation = np.array([0.2, 0.7, 0.1])
        elif self.is_special_event:
            # During special event, prioritize eMBB
            target_allocation = np.array([0.6, 0.3, 0.1])
        elif self.is_iot_surge:
            # During IoT surge, increase mMTC allocation
            target_allocation = np.array([0.3, 0.3, 0.4])
        else:
            # Normal allocation
            target_allocation = np.array([0.4, 0.4, 0.2])
        
        # Apply stability factor to avoid rapid changes
        stability_factor = 0.7
        new_allocation = stability_factor * self.allocation + (1 - stability_factor) * target_allocation
        
        # Check for QoS violations and adjust
        for i in range(3):
            if self.utilization[i] > self.thresholds[i]:
                # Increase allocation for this slice
                increase = min(0.1, (self.utilization[i] - self.thresholds[i]) * 0.2)
                
                # Find least utilized slice
                other_indices = [j for j in range(3) if j != i]
                least_utilized_idx = other_indices[np.argmin(self.utilization[other_indices])]
                
                # Adjust allocations
                new_allocation[i] += increase
                new_allocation[least_utilized_idx] -= increase
        
        # Ensure allocations are within valid range and sum to 1
        new_allocation = np.clip(new_allocation, 0.1, 0.8)
        new_allocation = new_allocation / np.sum(new_allocation)
        
        self.allocation = new_allocation
        return new_allocation
    
    def update_utilization(self, traffic):
        """
        Update utilization based on traffic and allocation.
        
        Args:
            traffic (numpy.ndarray): Traffic for each slice
        
        Returns:
            numpy.ndarray: Updated utilization
        """
        # Calculate utilization (traffic / allocation)
        # Add small constant to avoid division by zero
        utilization = traffic / (self.allocation + 1e-6)
        
        self.utilization = utilization
        return utilization
    
    def run_step(self):
        """
        Run a single step of the orchestration process.
        
        Returns:
            dict: Current state
        """
        # Generate traffic
        traffic = self.generate_traffic()
        
        # Update utilization
        utilization = self.update_utilization(traffic)
        
        # Update allocation
        allocation = self.update_allocation()
        
        # Check for QoS violations
        violations = utilization > self.thresholds
        
        # Return current state
        return {
            'timestamp': datetime.now().isoformat(),
            'traffic': traffic,
            'allocation': allocation,
            'utilization': utilization,
            'violations': violations,
            'is_emergency': self.is_emergency,
            'is_special_event': self.is_special_event,
            'is_iot_surge': self.is_iot_surge
        }
    
    def visualize_state(self, state, output_path=None):
        """
        Visualize current state.
        
        Args:
            state (dict): Current state
            output_path (str): Path to save visualization
        """
        # Create figure
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 10))
        
        # Slice names and colors
        slice_names = ['eMBB', 'URLLC', 'mMTC']
        colors = ['#FF6B6B', '#45B7D1', '#FFBE0B']
        
        # Plot allocation pie chart
        ax1.pie(state['allocation'], labels=slice_names, colors=colors, autopct='%1.1f%%',
               shadow=True, startangle=90)
        ax1.axis('equal')
        ax1.set_title('Current Slice Allocation')
        
        # Plot utilization bar chart
        ax2.bar(slice_names, state['utilization'], color=colors)
        
        # Add threshold lines
        for i, threshold in enumerate(self.thresholds):
            ax2.axhline(y=threshold, xmin=i/3, xmax=(i+1)/3, 
                       color=colors[i], linestyle='--', alpha=0.7)
        
        ax2.set_title('Current Slice Utilization')
        ax2.set_ylabel('Utilization')
        ax2.grid(axis='y', linestyle='--', alpha=0.7)
        
        # Plot traffic history
        if len(self.traffic_history) > 1:
            traffic_history = np.array(self.traffic_history)
            for i, slice_name in enumerate(slice_names):
                ax3.plot(traffic_history[:, i], label=slice_name, color=colors[i])
            
            ax3.set_title('Traffic History')
            ax3.set_xlabel('Time Step')
            ax3.set_ylabel('Traffic')
            ax3.legend()
            ax3.grid(True, linestyle='--', alpha=0.7)
        
        # Plot QoS violations
        violation_counts = np.sum([v['violations'] for v in self.history[-20:]], axis=0)
        ax4.bar(slice_names, violation_counts, color=colors)
        ax4.set_title('QoS Violations (Last 20 Steps)')
        ax4.set_ylabel('Number of Violations')
        ax4.grid(axis='y', linestyle='--', alpha=0.7)
        
        # Add event indicators
        events = []
        if state['is_emergency']:
            events.append('Emergency')
        if state['is_special_event']:
            events.append('Special Event')
        if state['is_iot_surge']:
            events.append('IoT Surge')
        
        if events:
            fig.suptitle(f"Network Status: {', '.join(events)}", fontsize=16)
        else:
            fig.suptitle("Network Status: Normal", fontsize=16)
        
        plt.tight_layout()
        
        # Save or show
        if output_path:
            plt.savefig(output_path)
            plt.close()
        else:
            plt.show()
    
    def run(self, duration=60, interval=1.0):
        """
        Run the orchestrator for a specified duration.
        
        Args:
            duration (int): Duration in seconds
            interval (float): Update interval in seconds
        """
        logger.info(f"Running orchestrator for {duration} seconds")
        
        # Initialize history
        self.history = []
        
        # Run for specified duration
        start_time = time.time()
        step = 0
        
        try:
            while time.time() - start_time < duration:
                # Run step
                state = self.run_step()
                
                # Add to history
                self.history.append(state)
                
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
                viz_path = os.path.join(self.output_dir, f"state_{step:03d}.png")
                self.visualize_state(state, viz_path)
                
                # Increment step
                step += 1
                
                # Sleep
                time.sleep(interval)
        
        except KeyboardInterrupt:
            logger.info("Orchestrator stopped by user")
        
        # Save history
        self.save_history()
        
        logger.info(f"Orchestrator run completed with {step} steps")
    
    def save_history(self):
        """Save history to file."""
        import json
        
        # Convert history to serializable format
        serializable_history = []
        for state in self.history:
            serializable_state = {
                'timestamp': state['timestamp'],
                'traffic': state['traffic'].tolist(),
                'allocation': state['allocation'].tolist(),
                'utilization': state['utilization'].tolist(),
                'violations': state['violations'].tolist(),
                'is_emergency': state['is_emergency'],
                'is_special_event': state['is_special_event'],
                'is_iot_surge': state['is_iot_surge']
            }
            serializable_history.append(serializable_state)
        
        # Save to file
        history_path = os.path.join(self.output_dir, 'history.json')
        with open(history_path, 'w') as f:
            json.dump(serializable_history, f, indent=2)
        
        logger.info(f"History saved to {history_path}")


def run_demo():
    """Run the orchestrator demo."""
    import argparse
    
    # Parse arguments
    parser = argparse.ArgumentParser(description='5G Network Slicing Orchestrator Demo')
    parser.add_argument('--duration', type=int, default=60, help='Duration in seconds')
    parser.add_argument('--interval', type=float, default=1.0, help='Update interval in seconds')
    parser.add_argument('--emergency', action='store_true', help='Simulate emergency')
    parser.add_argument('--special-event', action='store_true', help='Simulate special event')
    parser.add_argument('--iot-surge', action='store_true', help='Simulate IoT surge')
    
    args = parser.parse_args()
    
    # Create orchestrator
    orchestrator = SimpleOrchestrator()
    
    # Set event modes
    if args.emergency:
        orchestrator.set_emergency_mode(True)
    
    if args.special_event:
        orchestrator.set_special_event_mode(True)
    
    if args.iot_surge:
        orchestrator.set_iot_surge_mode(True)
    
    # Run orchestrator
    orchestrator.run(args.duration, args.interval)


if __name__ == "__main__":
    run_demo() 