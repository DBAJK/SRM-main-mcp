import os
import sys
import random
import time
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import numpy as np
from matplotlib.patches import Circle, Rectangle

class SliceVisualizer:
    def __init__(self):
        self.fig, self.axs = plt.subplots(2, 2, figsize=(12, 10))
        self.fig.suptitle("5G Network Slicing Demonstration", fontsize=16)
        
        # Flatten axes for easier access
        self.axs = self.axs.flatten()
        
        # Define slice types and colors
        self.slice_types = ["eMBB", "URLLC", "mMTC"]
        self.slice_colors = {
            "eMBB": "#FF6B6B",   # Red - high bandwidth
            "URLLC": "#45B7D1",  # Blue - low latency
            "mMTC": "#FFBE0B"    # Yellow - IoT 
        }
        
        # Generate base stations with random positions
        self.num_base_stations = 5
        self.base_stations = self.generate_base_stations()
        
        # Generate clients
        self.num_clients = 30
        self.clients = self.generate_clients()
        
        # Current bandwidth allocation per slice
        self.slice_allocation = {
            "eMBB": [0.7, 0.6, 0.5, 0.7, 0.6],   # High bandwidth needs
            "URLLC": [0.2, 0.3, 0.3, 0.2, 0.3],  # Low latency needs
            "mMTC": [0.1, 0.1, 0.2, 0.1, 0.1]    # Many small connections
        }
        
        # Current usage per slice
        self.slice_usage = {
            "eMBB": [0.3, 0.4, 0.2, 0.5, 0.3],
            "URLLC": [0.1, 0.1, 0.1, 0.1, 0.1],
            "mMTC": [0.05, 0.05, 0.1, 0.05, 0.05]
        }
        
        # Initialize subplots
        self.setup_plots()
        self.frame_num = 0
        
    def generate_base_stations(self):
        """Generate base stations with random positions"""
        base_stations = []
        for i in range(self.num_base_stations):
            x = random.uniform(100, 900)
            y = random.uniform(100, 900)
            radius = random.uniform(150, 250)
            base_stations.append({
                'id': i,
                'x': x,
                'y': y,
                'radius': radius,
                'capacity': 1.0  # Total capacity (normalized)
            })
        return base_stations
    
    def generate_clients(self):
        """Generate clients assigned to base stations and slices"""
        clients = []
        slice_distribution = {"eMBB": 0.4, "URLLC": 0.3, "mMTC": 0.3}
        
        for i in range(self.num_clients):
            # Assign to a random base station
            bs = random.choice(self.base_stations)
            bs_x, bs_y = bs['x'], bs['y']
            
            # Place within coverage area
            angle = random.uniform(0, 2 * np.pi)
            distance = random.uniform(30, bs['radius'] * 0.8)
            x = bs_x + distance * np.cos(angle)
            y = bs_y + distance * np.sin(angle)
            
            # Assign to a slice based on distribution
            slice_type = random.choices(
                list(slice_distribution.keys()),
                weights=list(slice_distribution.values())
            )[0]
            
            # Generate a client with random attributes
            clients.append({
                'id': i,
                'x': x,
                'y': y,
                'base_station': bs['id'],
                'slice': slice_type,
                'active': random.random() < 0.7,  # 70% active initially
                'data_rate': random.uniform(0.1, 1.0)  # Normalized data rate
            })
        
        return clients
    
    def setup_plots(self):
        """Initialize all subplots"""
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
        
        # 3. Dynamic Traffic Load
        self.axs[2].set_title("Dynamic Traffic Load")
        self.axs[2].set_xlim(0, 100)
        self.axs[2].set_ylim(0, 1.2)
        self.axs[2].set_xlabel("Time")
        self.axs[2].set_ylabel("Network Load")
        
        # 4. QoS Parameters
        self.axs[3].set_title("QoS Parameters by Slice")
        self.axs[3].set_ylim(0, 1.2)
        self.axs[3].set_ylabel("Normalized Value")
        self.axs[3].set_xticks([0, 1, 2])
        self.axs[3].set_xticklabels(self.slice_types)
        
        # Add legends
        for slice_type, color in self.slice_colors.items():
            self.axs[0].plot([], [], 'o', color=color, label=slice_type)
        self.axs[0].legend(loc='upper right')
        
        # Initialize plot elements
        self.network_elements = {}
        self.bar_plots = {}
        self.traffic_lines = {}
        self.qos_bars = {}
        
        # Add bottom text for instructions
        self.fig.text(0.5, 0.01, "Press 'r' to run simulation steps and see slicing in action", 
                      ha='center', fontsize=12, bbox=dict(facecolor='lightgray', alpha=0.5))
    
    def draw_network(self):
        """Draw the network topology with slices"""
        # Clear existing elements
        self.axs[0].clear()
        self.axs[0].set_title("Network Topology with Slices")
        self.axs[0].set_xlim(0, 1000)
        self.axs[0].set_ylim(0, 1000)
        
        # Draw base stations
        for bs in self.base_stations:
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
        for client in self.clients:
            if client['active']:
                color = self.slice_colors[client['slice']]
                self.axs[0].plot(client['x'], client['y'], 'o', color=color, 
                                markersize=8, alpha=0.7)
                
                # Draw line to base station if active
                bs = self.base_stations[client['base_station']]
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
        
        for i, (slice_type, allocation) in enumerate(self.slice_allocation.items()):
            angle = 2 * np.pi * (i / len(self.slice_types))
            indicator_x = x + radius * np.cos(angle)
            indicator_y = y + radius * np.sin(angle)
            
            # Get current usage for this slice at this BS
            usage = self.slice_usage[slice_type][bs['id']]
            
            # Draw slice allocation indicator
            size = 100 + 200 * allocation[bs['id']]  # Size based on allocation
            color = self.slice_colors[slice_type]
            
            # Draw outer circle (total allocation)
            outer = Circle((indicator_x, indicator_y), np.sqrt(size/np.pi), 
                          fill=True, alpha=0.4, facecolor=color, edgecolor='black')
            self.axs[0].add_artist(outer)
            
            # Draw inner circle (current usage)
            usage_size = size * (usage / allocation[bs['id']])
            inner = Circle((indicator_x, indicator_y), np.sqrt(usage_size/np.pi), 
                          fill=True, alpha=0.8, facecolor=color)
            self.axs[0].add_artist(inner)
            
            # Add label
            label_x = indicator_x + 5
            label_y = indicator_y + 5
            self.axs[0].text(label_x, label_y, slice_type, 
                            fontsize=8, ha='left', va='bottom')
    
    def update_slice_allocation(self):
        """Update slice allocation chart"""
        self.axs[1].clear()
        self.axs[1].set_title("Slice Allocation Per Base Station")
        self.axs[1].set_ylim(0, 1.2)
        self.axs[1].set_xlabel("Base Station ID")
        self.axs[1].set_ylabel("Percentage of Resources")
        
        x = np.arange(self.num_base_stations)
        width = 0.25
        
        # Get data for each slice
        for i, (slice_type, allocation) in enumerate(self.slice_allocation.items()):
            bottom = np.zeros(self.num_base_stations)
            if i > 0:
                for j in range(i):
                    prev_slice = list(self.slice_allocation.keys())[j]
                    bottom += np.array(self.slice_allocation[prev_slice])
            
            # Draw bars
            self.axs[1].bar(x, allocation, width, bottom=bottom, 
                           label=slice_type, color=self.slice_colors[slice_type])
            
            # Add usage indicators (colored dots inside bars)
            for bs_id in range(self.num_base_stations):
                usage = self.slice_usage[slice_type][bs_id]
                usage_y = bottom[bs_id] + usage
                self.axs[1].scatter(bs_id, usage_y, color='black', s=30, zorder=3)
        
        self.axs[1].set_xticks(x)
        self.axs[1].set_xticklabels([f"BS {i}" for i in range(self.num_base_stations)])
        self.axs[1].legend()
        self.axs[1].grid(axis='y', linestyle='--', alpha=0.7)
    
    def update_traffic_plot(self):
        """Update traffic load history plot"""
        self.axs[2].clear()
        self.axs[2].set_title("Dynamic Traffic Load")
        self.axs[2].set_xlim(max(0, self.frame_num - 50), max(100, self.frame_num + 10))
        self.axs[2].set_ylim(0, 1.2)
        self.axs[2].set_xlabel("Time")
        self.axs[2].set_ylabel("Network Load")
        
        # Generate or update traffic data
        if not hasattr(self, 'traffic_data'):
            # Initialize traffic data for each slice
            self.traffic_data = {
                slice_type: [sum(self.slice_usage[slice_type]) / self.num_base_stations] 
                for slice_type in self.slice_types
            }
            self.time_points = [0]
        else:
            # Add the current frame's data
            for slice_type in self.slice_types:
                current_load = sum(self.slice_usage[slice_type]) / self.num_base_stations
                self.traffic_data[slice_type].append(current_load)
            self.time_points.append(self.frame_num)
        
        # Plot traffic data for each slice
        for slice_type in self.slice_types:
            self.axs[2].plot(self.time_points, self.traffic_data[slice_type], 
                            label=slice_type, color=self.slice_colors[slice_type], 
                            linewidth=2)
            
        self.axs[2].legend()
        self.axs[2].grid(True, linestyle='--', alpha=0.7)
    
    def update_qos_parameters(self):
        """Update QoS parameters visualization"""
        self.axs[3].clear()
        self.axs[3].set_title("QoS Parameters by Slice")
        self.axs[3].set_ylim(0, 1.2)
        self.axs[3].set_xticks(np.arange(len(self.slice_types)))
        self.axs[3].set_xticklabels(self.slice_types)
        
        # Define QoS parameters per slice type 
        # These would normally be dynamic but we'll use static values for the demo
        qos_params = {
            # Each has bandwidth, latency, reliability - normalized to 0-1
            "eMBB": [0.9, 0.5, 0.7],   # High bandwidth, medium latency/reliability 
            "URLLC": [0.4, 0.95, 0.95], # Lower bandwidth, very low latency, high reliability
            "mMTC": [0.2, 0.4, 0.8]     # Low bandwidth, tolerant latency, good reliability
        }
        
        # Labels for QoS parameters
        param_labels = ["Bandwidth", "Low Latency", "Reliability"]
        colors = ['#3498db', '#2ecc71', '#e74c3c']
        
        x = np.arange(len(self.slice_types))
        width = 0.25
        
        # Draw grouped bars for each parameter
        for i, param in enumerate(range(3)):
            values = [qos_params[slice_type][param] for slice_type in self.slice_types]
            pos = x + (i - 1) * width
            self.axs[3].bar(pos, values, width, label=param_labels[i], color=colors[i])
        
        # Add current load indicators
        for i, slice_type in enumerate(self.slice_types):
            load = sum(self.slice_usage[slice_type]) / sum(self.slice_allocation[slice_type])
            self.axs[3].axhline(y=load, xmin=(i/len(self.slice_types)), 
                              xmax=((i+1)/len(self.slice_types)), 
                              color=self.slice_colors[slice_type], linestyle='--', 
                              linewidth=2, label=f"{slice_type} Load")
        
        self.axs[3].legend()
        self.axs[3].grid(axis='y', linestyle='--', alpha=0.7)
    
    def update_simulation(self, frame=None):
        """Update simulation state"""
        self.frame_num += 1
        
        # 1. Update client states
        for client in self.clients:
            # Randomly toggle activity
            if random.random() < 0.1:  # 10% chance to change state
                client['active'] = not client['active']
            
            # Move clients slightly
            if client['active']:
                client['x'] += random.uniform(-10, 10)
                client['y'] += random.uniform(-10, 10)
                
                # Keep within boundaries
                bs = self.base_stations[client['base_station']]
                dist = np.sqrt((client['x'] - bs['x'])**2 + (client['y'] - bs['y'])**2)
                if dist > bs['radius']:
                    # Move back toward base station
                    angle = np.arctan2(bs['y'] - client['y'], bs['x'] - client['x'])
                    client['x'] += np.cos(angle) * 5
                    client['y'] += np.sin(angle) * 5
        
        # 2. Update slice allocations (occasionally)
        if self.frame_num % 5 == 0:
            # Pick a random base station to adjust
            bs_id = random.randint(0, self.num_base_stations - 1)
            
            # Count active clients per slice for this BS
            active_clients = {slice_type: 0 for slice_type in self.slice_types}
            for client in self.clients:
                if client['base_station'] == bs_id and client['active']:
                    active_clients[client['slice']] += 1
            
            # Adjust allocation based on active clients
            total_active = sum(active_clients.values())
            
            if total_active > 0:
                # Calculate ideal allocation
                ideal_allocation = {
                    slice_type: max(0.1, count / max(1, total_active))
                    for slice_type, count in active_clients.items()
                }
                
                # Smooth the transition (don't change too abruptly)
                for slice_type in self.slice_types:
                    current = self.slice_allocation[slice_type][bs_id]
                    ideal = ideal_allocation[slice_type]
                    # Move 20% toward ideal
                    self.slice_allocation[slice_type][bs_id] = current * 0.8 + ideal * 0.2
            
            # Normalize to ensure sum = 1
            total = sum(self.slice_allocation[slice_type][bs_id] for slice_type in self.slice_types)
            for slice_type in self.slice_types:
                self.slice_allocation[slice_type][bs_id] /= total
        
        # 3. Update slice usage based on active clients
        for bs_id in range(self.num_base_stations):
            # Calculate usage for each slice based on active clients
            usage = {slice_type: 0 for slice_type in self.slice_types}
            
            for client in self.clients:
                if client['base_station'] == bs_id and client['active']:
                    slice_type = client['slice']
                    usage[slice_type] += client['data_rate'] * 0.1  # Scale down
            
            # Update slice usage (with random fluctuations)
            for slice_type in self.slice_types:
                # Calculate new usage with random fluctuation
                fluctuation = random.uniform(-0.05, 0.05)
                new_usage = usage[slice_type] + fluctuation
                
                # Smooth change over time (exponential smoothing)
                current = self.slice_usage[slice_type][bs_id]
                self.slice_usage[slice_type][bs_id] = current * 0.7 + new_usage * 0.3
                
                # Ensure usage doesn't exceed allocation
                max_usage = self.slice_allocation[slice_type][bs_id]
                self.slice_usage[slice_type][bs_id] = min(max_usage, self.slice_usage[slice_type][bs_id])
                self.slice_usage[slice_type][bs_id] = max(0, self.slice_usage[slice_type][bs_id])
        
        # Update all visualizations
        self.draw_network()
        self.update_slice_allocation()
        self.update_traffic_plot()
        self.update_qos_parameters()
        
        return []
    
    def run(self):
        """Run the visualization"""
        # Start the animation
        self.ani = animation.FuncAnimation(
            self.fig, self.update_simulation, 
            frames=100, interval=200, blit=False
        )
        
        plt.tight_layout(rect=[0, 0.03, 1, 0.95])  # Adjust for title and bottom text
        plt.show()


# Run the simulation when script is executed
if __name__ == "__main__":
    print("5G Network Slicing Visualization")
    print("--------------------------------")
    print("This visualization demonstrates how network slicing dynamically")
    print("allocates resources between different slice types:")
    print("- eMBB (Enhanced Mobile Broadband): High bandwidth")
    print("- URLLC (Ultra-Reliable Low-Latency): Low latency, high reliability")
    print("- mMTC (Massive Machine-Type Communication): Many IoT devices")
    print("\nPress 'r' to run the simulation and see slicing in action.")
    
    visualizer = SliceVisualizer()
    visualizer.run() 