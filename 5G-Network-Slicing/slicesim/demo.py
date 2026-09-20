#!/usr/bin/env python3
"""
5G Network Slicing - Interactive Demo

This module provides an interactive demo for the 5G network slicing system.
It allows users to visualize and interact with the system in real-time.
"""

import os
import sys
import time
import logging
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime
import threading
import queue
import json

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import local modules
from slicesim.orchestrator import SliceOrchestrator
from slicesim.ai.slice_manager import BaseSliceManager, EnhancedSliceManager
from slicesim.config import Config, load_config
from slicesim.utils import setup_directories, save_json

class InteractiveDemo:
    """
    Interactive demo for 5G network slicing system.
    """
    
    def __init__(self, model_path, config_path=None):
        """
        Initialize the interactive demo.
        
        Args:
            model_path (str): Path to the trained model
            config_path (str): Path to the configuration file
        """
        # Load configuration
        self.config = Config(config_path)
        
        # Ensure directories exist
        self.config.ensure_directories()
        
        # Create output directory
        self.output_dir = os.path.join(
            self.config.get('system', 'results_dir', default='results'),
            f"demo_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Initialize components
        self.orchestrator = SliceOrchestrator(model_path=model_path, config_path=config_path)
        self.static_manager = BaseSliceManager(config_path=config_path)
        self.enhanced_manager = EnhancedSliceManager(model_path=model_path, config_path=config_path)
        
        # Initialize state
        self.is_running = False
        self.is_emergency = False
        self.is_special_event = False
        self.is_iot_surge = False
        self.traffic_load = 0.5
        self.client_count = 0.5
        self.bs_count = 0.5
        
        # Initialize history
        self.history = {
            'timestamps': [],
            'traffic_load': [],
            'static_allocation': [],
            'enhanced_allocation': [],
            'static_utilization': [],
            'enhanced_utilization': [],
            'events': []
        }
        
        # Initialize plotting
        plt.ion()  # Enable interactive mode
        self.fig = None
        self.axes = None
        
        # Initialize thread and queue
        self.thread = None
        self.queue = queue.Queue()
        
        logger.info("Interactive demo initialized")
    
    def start(self):
        """
        Start the interactive demo.
        """
        if self.is_running:
            logger.warning("Demo is already running")
            return
        
        # Start orchestrator
        self.orchestrator.start()
        
        # Set running flag
        self.is_running = True
        
        # Start thread
        self.thread = threading.Thread(target=self._run_loop)
        self.thread.daemon = True
        self.thread.start()
        
        logger.info("Interactive demo started")
    
    def stop(self):
        """
        Stop the interactive demo.
        """
        if not self.is_running:
            logger.warning("Demo is not running")
            return
        
        # Set running flag
        self.is_running = False
        
        # Wait for thread to finish
        if self.thread:
            self.thread.join(timeout=5.0)
        
        # Stop orchestrator
        self.orchestrator.stop()
        
        # Save history
        self._save_history()
        
        logger.info("Interactive demo stopped")
    
    def set_emergency(self, is_emergency):
        """
        Set emergency mode.
        
        Args:
            is_emergency (bool): Whether there's an emergency
        """
        self.is_emergency = is_emergency
        self.orchestrator.set_emergency_mode(is_emergency)
        self.static_manager.set_emergency_mode(is_emergency)
        self.enhanced_manager.set_emergency_mode(is_emergency)
        
        # Add event to history
        if is_emergency:
            self.history['events'].append({
                'timestamp': datetime.now().isoformat(),
                'type': 'emergency',
                'status': 'start'
            })
        else:
            self.history['events'].append({
                'timestamp': datetime.now().isoformat(),
                'type': 'emergency',
                'status': 'end'
            })
        
        logger.info(f"Emergency mode set to {is_emergency}")
    
    def set_special_event(self, is_special_event):
        """
        Set special event mode.
        
        Args:
            is_special_event (bool): Whether there's a special event
        """
        self.is_special_event = is_special_event
        self.orchestrator.set_special_event_mode(is_special_event)
        
        # Add event to history
        if is_special_event:
            self.history['events'].append({
                'timestamp': datetime.now().isoformat(),
                'type': 'special_event',
                'status': 'start'
            })
        else:
            self.history['events'].append({
                'timestamp': datetime.now().isoformat(),
                'type': 'special_event',
                'status': 'end'
            })
        
        logger.info(f"Special event mode set to {is_special_event}")
    
    def set_iot_surge(self, is_iot_surge):
        """
        Set IoT surge mode.
        
        Args:
            is_iot_surge (bool): Whether there's an IoT surge
        """
        self.is_iot_surge = is_iot_surge
        self.orchestrator.set_iot_surge_mode(is_iot_surge)
        
        # Add event to history
        if is_iot_surge:
            self.history['events'].append({
                'timestamp': datetime.now().isoformat(),
                'type': 'iot_surge',
                'status': 'start'
            })
        else:
            self.history['events'].append({
                'timestamp': datetime.now().isoformat(),
                'type': 'iot_surge',
                'status': 'end'
            })
        
        logger.info(f"IoT surge mode set to {is_iot_surge}")
    
    def set_traffic_load(self, traffic_load):
        """
        Set traffic load.
        
        Args:
            traffic_load (float): Traffic load (0-1)
        """
        self.traffic_load = max(0.1, min(1.0, traffic_load))
        logger.info(f"Traffic load set to {self.traffic_load}")
    
    def _run_loop(self):
        """Main demo loop."""
        update_interval = 1.0  # seconds
        
        while self.is_running:
            try:
                # Process queue
                self._process_queue()
                
                # Update state
                self._update_state()
                
                # Update visualization
                self._update_visualization()
                
                # Sleep
                time.sleep(update_interval)
            except Exception as e:
                logger.error(f"Error in demo loop: {e}")
                time.sleep(1.0)  # Sleep to avoid tight loop in case of errors
    
    def _process_queue(self):
        """Process commands from queue."""
        try:
            while not self.queue.empty():
                cmd = self.queue.get_nowait()
                
                if cmd['type'] == 'emergency':
                    self.set_emergency(cmd['value'])
                elif cmd['type'] == 'special_event':
                    self.set_special_event(cmd['value'])
                elif cmd['type'] == 'iot_surge':
                    self.set_iot_surge(cmd['value'])
                elif cmd['type'] == 'traffic_load':
                    self.set_traffic_load(cmd['value'])
                elif cmd['type'] == 'stop':
                    self.is_running = False
        except queue.Empty:
            pass
    
    def _update_state(self):
        """Update system state."""
        # Get current time
        now = datetime.now()
        hour_of_day = now.hour / 24.0
        day_of_week = now.weekday() / 6.0
        
        # Add traffic variation
        traffic_variation = 0.1 * np.sin(time.time() / 10.0)
        current_traffic = self.traffic_load + traffic_variation
        
        # Apply event effects
        if self.is_emergency:
            current_traffic += 0.2
        if self.is_special_event:
            current_traffic += 0.3
        if self.is_iot_surge:
            current_traffic += 0.15
        
        # Ensure traffic is within valid range
        current_traffic = max(0.1, min(1.0, current_traffic))
        
        # Calculate slice-specific traffic
        if self.is_emergency:
            # During emergency, increase URLLC traffic
            traffic_values = np.array([
                current_traffic * 0.8,  # eMBB reduced
                current_traffic * 2.0,  # URLLC increased
                current_traffic * 0.9   # mMTC slightly reduced
            ])
        elif self.is_special_event:
            # During special event, increase eMBB traffic
            traffic_values = np.array([
                current_traffic * 1.5,  # eMBB increased
                current_traffic * 0.8,  # URLLC reduced
                current_traffic * 1.0   # mMTC unchanged
            ])
        elif self.is_iot_surge:
            # During IoT surge, increase mMTC traffic
            traffic_values = np.array([
                current_traffic * 0.9,  # eMBB slightly reduced
                current_traffic * 0.9,  # URLLC slightly reduced
                current_traffic * 1.8   # mMTC increased
            ])
        else:
            # Normal traffic distribution
            traffic_values = np.array([
                current_traffic * 1.0,  # eMBB
                current_traffic * 0.8,  # URLLC
                current_traffic * 0.7   # mMTC
            ])
        
        # Get allocations from slice managers
        static_allocation = self.static_manager.allocate_resources(
            traffic_load=current_traffic,
            utilization=np.zeros(3) if len(self.history['static_utilization']) == 0 else self.history['static_utilization'][-1]
        )
        
        enhanced_allocation = self.enhanced_manager.allocate_resources(
            traffic_load=current_traffic,
            utilization=np.zeros(3) if len(self.history['enhanced_utilization']) == 0 else self.history['enhanced_utilization'][-1],
            hour_of_day=hour_of_day,
            day_of_week=day_of_week,
            client_count=self.client_count,
            bs_count=self.bs_count
        )
        
        # Calculate utilizations
        static_utilization = traffic_values / (static_allocation + 1e-6)
        enhanced_utilization = traffic_values / (enhanced_allocation + 1e-6)
        
        # Update history
        self.history['timestamps'].append(now.isoformat())
        self.history['traffic_load'].append(current_traffic)
        self.history['static_allocation'].append(static_allocation.tolist())
        self.history['enhanced_allocation'].append(enhanced_allocation.tolist())
        self.history['static_utilization'].append(static_utilization.tolist())
        self.history['enhanced_utilization'].append(enhanced_utilization.tolist())
    
    def _update_visualization(self):
        """Update visualization."""
        # Create figure if it doesn't exist
        if self.fig is None or not plt.fignum_exists(self.fig.number):
            self.fig, self.axes = plt.subplots(2, 2, figsize=(15, 10))
            plt.subplots_adjust(hspace=0.3, wspace=0.3)
        
        # Clear axes
        for ax_row in self.axes:
            for ax in ax_row:
                ax.clear()
        
        # Get data
        timestamps = self.history['timestamps']
        traffic_load = self.history['traffic_load']
        static_allocation = np.array(self.history['static_allocation'])
        enhanced_allocation = np.array(self.history['enhanced_allocation'])
        static_utilization = np.array(self.history['static_utilization'])
        enhanced_utilization = np.array(self.history['enhanced_utilization'])
        
        # Limit history for visualization
        max_points = 100
        if len(timestamps) > max_points:
            timestamps = timestamps[-max_points:]
            traffic_load = traffic_load[-max_points:]
            static_allocation = static_allocation[-max_points:]
            enhanced_allocation = enhanced_allocation[-max_points:]
            static_utilization = static_utilization[-max_points:]
            enhanced_utilization = enhanced_utilization[-max_points:]
        
        # Convert timestamps to numeric values for plotting
        x = np.arange(len(timestamps))
        
        # Plot traffic load
        self.axes[0, 0].plot(x, traffic_load, 'k-', label='Traffic Load')
        self.axes[0, 0].set_title('Network Traffic Load')
        self.axes[0, 0].set_xlabel('Time')
        self.axes[0, 0].set_ylabel('Load')
        self.axes[0, 0].grid(True, linestyle='--', alpha=0.7)
        
        # Plot allocations
        slice_types = ['eMBB', 'URLLC', 'mMTC']
        colors = ['#FF6B6B', '#45B7D1', '#FFBE0B']
        
        for i, slice_type in enumerate(slice_types):
            self.axes[0, 1].plot(x, static_allocation[:, i], '--', color=colors[i], 
                               label=f'Static {slice_type}')
            self.axes[0, 1].plot(x, enhanced_allocation[:, i], '-', color=colors[i], 
                               label=f'Enhanced {slice_type}')
        
        self.axes[0, 1].set_title('Slice Allocation')
        self.axes[0, 1].set_xlabel('Time')
        self.axes[0, 1].set_ylabel('Allocation')
        self.axes[0, 1].set_ylim(0, 1)
        self.axes[0, 1].grid(True, linestyle='--', alpha=0.7)
        self.axes[0, 1].legend()
        
        # Plot utilizations
        for i, slice_type in enumerate(slice_types):
            self.axes[1, 0].plot(x, static_utilization[:, i], '--', color=colors[i], 
                               label=f'Static {slice_type}')
            self.axes[1, 0].plot(x, enhanced_utilization[:, i], '-', color=colors[i], 
                               label=f'Enhanced {slice_type}')
        
        self.axes[1, 0].set_title('Slice Utilization')
        self.axes[1, 0].set_xlabel('Time')
        self.axes[1, 0].set_ylabel('Utilization')
        self.axes[1, 0].grid(True, linestyle='--', alpha=0.7)
        self.axes[1, 0].legend()
        
        # Plot QoS violations
        # Get QoS thresholds
        thresholds = np.array([
            self.config.get('slices', 'qos_thresholds', 'eMBB', default=0.9),
            self.config.get('slices', 'qos_thresholds', 'URLLC', default=1.2),
            self.config.get('slices', 'qos_thresholds', 'mMTC', default=0.8)
        ])
        
        # Calculate violations
        static_violations = static_utilization > thresholds
        enhanced_violations = enhanced_utilization > thresholds
        
        # Count violations
        static_violation_count = np.sum(static_violations, axis=0)
        enhanced_violation_count = np.sum(enhanced_violations, axis=0)
        
        # Plot violation counts
        x_pos = np.arange(len(slice_types))
        width = 0.35
        
        self.axes[1, 1].bar(x_pos - width/2, static_violation_count, width, 
                          label='Static', color='#888888')
        self.axes[1, 1].bar(x_pos + width/2, enhanced_violation_count, width, 
                          label='Enhanced', color='#2ECC71')
        
        self.axes[1, 1].set_title('QoS Violations')
        self.axes[1, 1].set_xlabel('Slice Type')
        self.axes[1, 1].set_ylabel('Number of Violations')
        self.axes[1, 1].set_xticks(x_pos)
        self.axes[1, 1].set_xticklabels(slice_types)
        self.axes[1, 1].legend()
        
        # Add status text
        status_text = f"Status: "
        if self.is_emergency:
            status_text += "EMERGENCY "
        if self.is_special_event:
            status_text += "SPECIAL EVENT "
        if self.is_iot_surge:
            status_text += "IoT SURGE "
        if not (self.is_emergency or self.is_special_event or self.is_iot_surge):
            status_text += "Normal"
        
        self.fig.suptitle(status_text, fontsize=16)
        
        # Draw
        self.fig.canvas.draw()
        self.fig.canvas.flush_events()
        
        # Save current visualization
        viz_path = os.path.join(self.output_dir, 'current_state.png')
        plt.savefig(viz_path)
    
    def _save_history(self):
        """Save history to file."""
        history_path = os.path.join(self.output_dir, 'demo_history.json')
        save_json(self.history, history_path)
        logger.info(f"History saved to {history_path}")


def run_interactive_demo(model_path, config_path=None):
    """
    Run interactive demo.
    
    Args:
        model_path (str): Path to the trained model
        config_path (str): Path to the configuration file
    """
    # Create demo
    demo = InteractiveDemo(model_path, config_path)
    
    # Start demo
    demo.start()
    
    try:
        # Print instructions
        print("\n5G Network Slicing Interactive Demo")
        print("==================================")
        print("Commands:")
        print("  e - Toggle emergency mode")
        print("  s - Toggle special event mode")
        print("  i - Toggle IoT surge mode")
        print("  t <value> - Set traffic load (0-1)")
        print("  q - Quit")
        print("\nCurrent state is being visualized in a separate window.")
        
        # Main loop
        while True:
            cmd = input("\nEnter command: ").strip().lower()
            
            if cmd == 'q':
                break
            elif cmd == 'e':
                demo.queue.put({'type': 'emergency', 'value': not demo.is_emergency})
            elif cmd == 's':
                demo.queue.put({'type': 'special_event', 'value': not demo.is_special_event})
            elif cmd == 'i':
                demo.queue.put({'type': 'iot_surge', 'value': not demo.is_iot_surge})
            elif cmd.startswith('t '):
                try:
                    value = float(cmd.split(' ')[1])
                    demo.queue.put({'type': 'traffic_load', 'value': value})
                except:
                    print("Invalid traffic load value. Must be a number between 0 and 1.")
            else:
                print("Unknown command.")
    
    finally:
        # Stop demo
        demo.queue.put({'type': 'stop', 'value': None})
        demo.stop()
        
        print("\nDemo stopped. Results saved to:", demo.output_dir)


if __name__ == "__main__":
    # Run demo with default model
    run_interactive_demo("models/lstm_single") 