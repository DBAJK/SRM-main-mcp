import os
import sys
import json
import argparse
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.patches import Circle, Rectangle
from datetime import datetime

class SliceDataVisualizer:
    """Visualizes 5G network slicing data from a data file"""
    
    def __init__(self, data_path, speed=1.0):
        """Initialize the data visualizer"""
        # Load the data
        with open(data_path, 'r') as f:
            self.data = json.load(f)
        
        print(f"Loaded {len(self.data)} time steps from {data_path}")
        
        # Visualization speed (frames per step)
        self.animation_speed = speed
        
        # Setup visualization
        self.fig, self.axs = plt.subplots(2, 2, figsize=(14, 10))
        self.fig.suptitle("5G Network Slicing Real-time Visualization", fontsize=16)
        
        # Flatten axes for easier access
        self.axs = self.axs.flatten()
        
        # Define slice types and colors
        self.slice_types = ["eMBB", "URLLC", "mMTC"]
        self.slice_colors = {
            "eMBB": "#FF6B6B",   # Red - high bandwidth
            "URLLC": "#45B7D1",  # Blue - low latency
            "mMTC": "#FFBE0B"    # Yellow - IoT 
        }
        
        # Current step
        self.current_step = 0
        self.total_steps = len(self.data)
        
        # Traffic history
        self.traffic_history = {slice_type: [] for slice_type in self.slice_types}
        self.time_points = []
        
        # Initialize plots
        self.setup_plots()
        
        # Status text
        self.status_text = self.fig.text(0.5, 0.01, "", ha='center', fontsize=10)
        
    def setup_plots(self):
        """Set up the visualization plots"""
        # 1. Network topology and slice visualization
        self.axs[0].set_title("Network Topology with Slices")
        self.axs[0].set_xlim(0, 1000)
        self.axs[0].set_ylim(0, 1000)
        self.axs[0].set_aspect('equal')
        
        # 2. Slice allocation per base station
        self.axs[1].set_title("Slice Allocation Per Base Station")
        self.axs[1].set_ylim(0, 1.2)
        self.axs[1].set_xlabel("Base Station ID")
        self.axs[1].set_ylabel("Percentage of Resources")
        
        # 3. Traffic load over time
        self.axs[2].set_title("Traffic Load Over Time")
        self.axs[2].set_xlim(0, min(50, self.total_steps))
        self.axs[2].set_ylim(0, 1.0)
        self.axs[2].set_xlabel("Time Step")
        self.axs[2].set_ylabel("Normalized Load")
        
        # 4. QoS parameters by slice
        self.axs[3].set_title("QoS Parameters by Slice")
        self.axs[3].set_ylim(0, 1.2)
        self.axs[3].set_ylabel("Normalized Value")
        self.axs[3].set_xticks(range(3))
        self.axs[3].set_xticklabels(self.slice_types)
        
        # Add legends
        for slice_type, color in self.slice_colors.items():
            self.axs[0].plot([], [], 'o', color=color, label=slice_type)
        self.axs[0].legend(loc='upper right')
        
        # Add bottom text for instructions
        self.fig.text(0.5, 0.04, "Press 'n' to advance, 's' to skip 10 steps, 'r' to restart", 
                      ha='center', fontsize=10, bbox=dict(facecolor='lightgray', alpha=0.5))
        
    def update_network_topology(self, state):
        """Update the network topology visualization"""
        self.axs[0].clear()
        self.axs[0].set_title("Network Topology with Slices")
        self.axs[0].set_xlim(0, 1000)
        self.axs[0].set_ylim(0, 1000)
        
        # Draw base stations
        for bs in state['base_stations']:
            # Draw coverage area
            circle = Circle((bs['x'], bs['y']), bs['radius'], fill=True, 
                           alpha=0.1, facecolor='gray', edgecolor='gray')
            self.axs[0].add_artist(circle)
            
            # Draw base station
            self.axs[0].plot(bs['x'], bs['y'], 'k^', markersize=10)
            self.axs[0].text(bs['x'], bs['y']+20, f"BS {bs['id']}", ha='center')
            
            # Draw slice allocations around base station
            self.draw_slice_indicators(bs)
        
        # Draw clients
        for client in state['clients']:
            if client['active']:
                color = self.slice_colors[client['slice']]
                self.axs[0].plot(client['x'], client['y'], 'o', color=color, 
                                markersize=8, alpha=0.7)
                
                # Draw line to base station if active
                bs = next((b for b in state['base_stations'] if b['id'] == client['base_station']), None)
                if bs:
                    self.axs[0].plot([client['x'], bs['x']], [client['y'], bs['y']], 
                                    color=color, alpha=0.3, linewidth=1)
        
        # Add legend
        for slice_type, color in self.slice_colors.items():
            self.axs[0].plot([], [], 'o', color=color, label=slice_type)
        self.axs[0].legend(loc='upper right')
    
    def draw_slice_indicators(self, bs):
        """Draw slice allocation indicators around base station"""
        x, y = bs['x'], bs['y']
        radius = 40
        
        for i, slice_type in enumerate(self.slice_types):
            angle = 2 * np.pi * (i / len(self.slice_types))
            indicator_x = x + radius * np.cos(angle)
            indicator_y = y + radius * np.sin(angle)
            
            # Get allocation and usage for this slice at this BS
            allocation = bs['slice_allocation'][slice_type]
            usage = bs['slice_usage'][slice_type]
            
            # Draw slice allocation indicator
            size = 100 + 200 * allocation  # Size based on allocation
            color = self.slice_colors[slice_type]
            
            # Draw outer circle (total allocation)
            outer = Circle((indicator_x, indicator_y), np.sqrt(size/np.pi), 
                          fill=True, alpha=0.4, facecolor=color, edgecolor='black')
            self.axs[0].add_artist(outer)
            
            # Draw inner circle (current usage)
            usage_size = size * usage
            inner = Circle((indicator_x, indicator_y), np.sqrt(usage_size/np.pi), 
                          fill=True, alpha=0.8, facecolor=color)
            self.axs[0].add_artist(inner)
            
            # Add label
            label_x = indicator_x + 5
            label_y = indicator_y + 5
            self.axs[0].text(label_x, label_y, slice_type, 
                            fontsize=8, ha='left', va='bottom')
    
    def update_slice_allocation(self, state):
        """Update the slice allocation chart"""
        self.axs[1].clear()
        self.axs[1].set_title("Slice Allocation Per Base Station")
        self.axs[1].set_ylim(0, 1.2)
        self.axs[1].set_xlabel("Base Station ID")
        self.axs[1].set_ylabel("Percentage of Resources")
        
        base_stations = state['base_stations']
        num_bs = len(base_stations)
        x = np.arange(num_bs)
        width = 0.6
        
        # Prepare data arrays
        allocations = {slice_type: [] for slice_type in self.slice_types}
        usages = {slice_type: [] for slice_type in self.slice_types}
        
        # Extract data
        for bs in base_stations:
            for slice_type in self.slice_types:
                allocations[slice_type].append(bs['slice_allocation'][slice_type])
                usages[slice_type].append(bs['slice_usage'][slice_type])
        
        # Plot stacked bars for allocations
        bottom = np.zeros(num_bs)
        for i, slice_type in enumerate(self.slice_types):
            self.axs[1].bar(x, allocations[slice_type], width, bottom=bottom,
                           label=slice_type, color=self.slice_colors[slice_type],
                           alpha=0.6, edgecolor='black')
            
            # Plot usage dots
            for j in range(num_bs):
                usage_height = bottom[j] + usages[slice_type][j]
                self.axs[1].scatter(j, usage_height, color='black', s=30, zorder=3)
            
            bottom += np.array(allocations[slice_type])
        
        # Set labels and legend
        self.axs[1].set_xticks(x)
        self.axs[1].set_xticklabels([f"BS {i}" for i in range(num_bs)])
        self.axs[1].legend(loc='upper right')
        self.axs[1].grid(axis='y', linestyle='--', alpha=0.7)
    
    def update_traffic_history(self, state):
        """Update the traffic history plot"""
        self.axs[2].clear()
        self.axs[2].set_title("Traffic Load Over Time")
        
        # Calculate average usage across base stations for each slice
        base_stations = state['base_stations']
        avg_usage = {slice_type: 0 for slice_type in self.slice_types}
        
        for slice_type in self.slice_types:
            total = sum(bs['slice_usage'][slice_type] for bs in base_stations)
            avg_usage[slice_type] = total / len(base_stations)
            self.traffic_history[slice_type].append(avg_usage[slice_type])
        
        # Add current step to time points
        self.time_points.append(self.current_step)
        
        # Adjust x-axis limits to show recent history
        window_size = 50
        if self.current_step > window_size:
            self.axs[2].set_xlim(self.current_step - window_size, self.current_step + 5)
        else:
            self.axs[2].set_xlim(0, max(window_size, self.current_step + 5))
        
        self.axs[2].set_ylim(0, 1.0)
        self.axs[2].set_xlabel("Time Step")
        self.axs[2].set_ylabel("Normalized Load")
        
        # Plot lines for each slice type
        for slice_type in self.slice_types:
            self.axs[2].plot(self.time_points, self.traffic_history[slice_type],
                            label=slice_type, color=self.slice_colors[slice_type],
                            linewidth=2)
        
        # Add vertical line for current step
        self.axs[2].axvline(x=self.current_step, color='black', linestyle='--', alpha=0.5)
        
        # Add legend
        self.axs[2].legend(loc='upper right')
        self.axs[2].grid(True, linestyle='--', alpha=0.5)
    
    def update_qos_parameters(self, state):
        """Update the QoS parameters visualization"""
        self.axs[3].clear()
        self.axs[3].set_title("QoS Parameters by Slice")
        self.axs[3].set_ylim(0, 1.2)
        self.axs[3].set_ylabel("Normalized Value")
        self.axs[3].set_xticks(range(3))
        self.axs[3].set_xticklabels(self.slice_types)
        
        # Calculate QoS parameters based on current network state
        base_stations = state['base_stations']
        
        # Define QoS parameters per slice type
        qos_params = {
            # baseline parameters: bandwidth, latency, reliability
            "eMBB": [0.9, 0.5, 0.7],
            "URLLC": [0.4, 0.95, 0.95],
            "mMTC": [0.2, 0.4, 0.8]
        }
        
        # Calculate load level for each slice (usage / allocation)
        load_levels = {}
        for slice_type in self.slice_types:
            total_alloc = sum(bs['slice_allocation'][slice_type] for bs in base_stations)
            total_usage = sum(bs['slice_usage'][slice_type] for bs in base_stations)
            
            if total_alloc > 0:
                load_levels[slice_type] = total_usage / total_alloc
            else:
                load_levels[slice_type] = 0
        
        # Adjust QoS based on load levels
        for slice_type in self.slice_types:
            load = load_levels[slice_type]
            
            # Bandwidth decreases with load
            qos_params[slice_type][0] *= max(0.5, 1.0 - 0.5 * load)
            
            # Latency decreases (gets worse) with load for URLLC and eMBB
            if slice_type in ["URLLC", "eMBB"]:
                qos_params[slice_type][1] *= max(0.6, 1.0 - 0.4 * load)
            
            # Reliability decreases with very high load
            if load > 0.8:
                qos_params[slice_type][2] *= max(0.7, 1.0 - 0.3 * (load - 0.8) / 0.2)
        
        # Define labels and colors for QoS parameters
        param_labels = ["Bandwidth", "Low Latency", "Reliability"]
        colors = ['#3498db', '#2ecc71', '#e74c3c']
        
        # Plot parameters as grouped bars
        x = np.arange(len(self.slice_types))
        width = 0.25
        
        for i, param in enumerate(range(3)):
            values = [qos_params[slice_type][param] for slice_type in self.slice_types]
            pos = x + (i - 1) * width
            self.axs[3].bar(pos, values, width, label=param_labels[i], color=colors[i])
        
        # Add horizontal lines for load levels
        for i, slice_type in enumerate(self.slice_types):
            self.axs[3].axhline(y=load_levels[slice_type], 
                                xmin=(i/len(self.slice_types)), 
                                xmax=((i+1)/len(self.slice_types)), 
                                color=self.slice_colors[slice_type], 
                                linestyle='--', linewidth=2, 
                                label=f"{slice_type} Load")
        
        # Add legend
        self.axs[3].legend(fontsize=8)
        self.axs[3].grid(axis='y', linestyle='--', alpha=0.7)
    
    def update_visualization(self, frame=None):
        """Update the entire visualization for the current step"""
        if self.current_step >= self.total_steps:
            print("End of data reached")
            return
        
        # Get current state
        state = self.data[self.current_step]
        
        # Update all visualizations
        self.update_network_topology(state)
        self.update_slice_allocation(state)
        self.update_traffic_history(state)
        self.update_qos_parameters(state)
        
        # Update status text
        timestamp = state['timestamp']
        self.status_text.set_text(f"Step: {self.current_step}/{self.total_steps-1} | Time: {timestamp}")
        
        # Auto-advance to next step if animation is running
        if frame is not None:
            self.current_step = (self.current_step + 1) % self.total_steps
    
    def on_key_press(self, event):
        """Handle key press events"""
        if event.key == 'n':
            # Advance to next step
            self.current_step = min(self.current_step + 1, self.total_steps - 1)
            self.update_visualization()
            plt.draw()
        elif event.key == 's':
            # Skip 10 steps
            self.current_step = min(self.current_step + 10, self.total_steps - 1)
            self.update_visualization()
            plt.draw()
        elif event.key == 'r':
            # Restart from beginning
            self.current_step = 0
            # Clear traffic history
            self.traffic_history = {slice_type: [] for slice_type in self.slice_types}
            self.time_points = []
            self.update_visualization()
            plt.draw()
    
    def run(self, animate=False):
        """Run the visualization"""
        # Connect key press events
        self.fig.canvas.mpl_connect('key_press_event', self.on_key_press)
        
        if animate:
            # Run as animation
            self.animation = animation.FuncAnimation(
                self.fig, self.update_visualization, 
                frames=self.total_steps, interval=1000 / self.animation_speed, 
                repeat=False
            )
        else:
            # Start with first frame
            self.update_visualization()
        
        plt.tight_layout(rect=[0, 0.05, 1, 0.95])  # Adjust for title and bottom text
        plt.show()

def main():
    """Run the visualization"""
    parser = argparse.ArgumentParser(description="Visualize 5G network slicing data")
    parser.add_argument("--data", type=str, default="network_data.json", 
                        help="Path to data file")
    parser.add_argument("--animate", action="store_true", 
                        help="Run as animation")
    parser.add_argument("--speed", type=float, default=1.0, 
                        help="Animation speed multiplier")
    args = parser.parse_args()
    
    # Check if data file exists
    if not os.path.exists(args.data):
        print(f"Data file not found: {args.data}")
        print("Generating data first...")
        
        # Try to import the data generator
        try:
            from generate_data import NetworkDataGenerator
            
            # Generate data
            generator = NetworkDataGenerator(
                base_stations=5, 
                clients=30, 
                steps=100,
                mobility_level=0.3,
                traffic_variance=0.4
            )
            
            # Save to file
            generator.generate_and_save(args.data)
            
        except ImportError:
            print("Could not import data generator. Please run generate_data.py first.")
            return
    
    # Run visualization
    visualizer = SliceDataVisualizer(args.data, args.speed)
    visualizer.run(animate=args.animate)

if __name__ == "__main__":
    main() 