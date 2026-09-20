import os
import sys
import random
import time
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import numpy as np
from matplotlib.patches import Circle, Rectangle
import argparse

# Fix import paths
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)
try:
    from slicesim.Simulator import Simulator
    from slicesim.Distributor import Distributor
    from slicesim.BaseStation import BaseStation
    from slicesim.Client import Client
    from slicesim.slice_optimization import find_optimal_slice
except ImportError:
    print("Could not import simulation modules directly. Trying alternative import paths...")
    try:
        sys.path.append(os.path.join(current_dir, 'slicesim'))
        from Simulator import Simulator
        from Distributor import Distributor
        from BaseStation import BaseStation
        from Client import Client
        from slice_optimization import find_optimal_slice
        print("Successfully imported modules using alternative path.")
    except ImportError as e:
        print(f"Error importing simulation modules: {e}")
        print("Falling back to synthetic data for demonstration.")
        USE_SYNTHETIC_DATA = True
    else:
        USE_SYNTHETIC_DATA = False
else:
    USE_SYNTHETIC_DATA = False

class RealSliceVisualizer:
    def __init__(self, sim_data=None):
        self.fig, self.axs = plt.subplots(2, 2, figsize=(12, 10))
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
        
        # Initialize simulation data
        self.simulator = None
        self.simulation_step = 0
        self.state_history = []
        self.use_synthetic_data = USE_SYNTHETIC_DATA
        
        # Initialize subplots
        self.setup_plots()
        self.frame_num = 0
        
    def connect_simulation(self, base_stations=10, clients=50, simulation_time=100):
        """Connect to an actual simulation instance or create synthetic data"""
        print(f"Initializing with {base_stations} base stations and {clients} clients...")
        
        if self.use_synthetic_data:
            print("Using synthetic data for demonstration")
            # Generate synthetic network data
            self.generate_synthetic_data(base_stations, clients)
            initial_state = self.get_synthetic_state()
        else:
            # Create a simulator instance
            try:
                self.simulator = Simulator(base_stations=base_stations, 
                                          clients=clients, 
                                          simulation_time=simulation_time)
                
                # Initialize simulation
                self.simulator.initialize()
                
                # Get initial state
                initial_state = self.get_simulation_state()
                print("Simulation connected successfully.")
            except Exception as e:
                print(f"Error creating simulator: {e}")
                print("Falling back to synthetic data.")
                self.use_synthetic_data = True
                self.generate_synthetic_data(base_stations, clients)
                initial_state = self.get_synthetic_state()
        
        self.state_history.append(initial_state)
        
        # Update the visualization with the initial state
        self.update_visualization_from_state(initial_state)
        return True
    
    def generate_synthetic_data(self, num_base_stations, num_clients):
        """Generate synthetic data for demonstration"""
        # Generate base stations
        self.synthetic_base_stations = []
        for i in range(num_base_stations):
            x = random.uniform(100, 900)
            y = random.uniform(100, 900)
            radius = random.uniform(150, 250)
            
            # Generate slice allocations
            slice_allocation = {
                "eMBB": random.uniform(0.4, 0.7),
                "URLLC": random.uniform(0.2, 0.4),
                "mMTC": random.uniform(0.1, 0.3)
            }
            
            # Normalize to sum to 1
            total = sum(slice_allocation.values())
            for slice_type in slice_allocation:
                slice_allocation[slice_type] /= total
            
            # Initial usage (lower than allocation)
            slice_usage = {
                slice_type: allocation * random.uniform(0.3, 0.7) 
                for slice_type, allocation in slice_allocation.items()
            }
            
            self.synthetic_base_stations.append({
                'id': i,
                'x': x,
                'y': y,
                'radius': radius,
                'capacity': 1000,
                'slice_allocation': slice_allocation,
                'slice_usage': slice_usage
            })
        
        # Generate clients
        self.synthetic_clients = []
        slice_distribution = {"eMBB": 0.4, "URLLC": 0.3, "mMTC": 0.3}
        
        for i in range(num_clients):
            # Assign to a random base station
            bs = random.choice(self.synthetic_base_stations)
            bs_id = bs['id']
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
            
            # Generate client data
            self.synthetic_clients.append({
                'id': i,
                'x': x,
                'y': y,
                'base_station': bs_id,
                'slice': slice_type,
                'active': random.random() < 0.7,  # 70% active initially
                'data_rate': random.uniform(0.1, 1.0)  # Normalized data rate
            })
    
    def get_synthetic_state(self):
        """Get current synthetic state"""
        # Return current synthetic state
        return {
            'time': self.simulation_step,
            'base_stations': self.synthetic_base_stations,
            'clients': self.synthetic_clients
        }
    
    def update_synthetic_state(self):
        """Update synthetic state to simulate network changes"""
        # 1. Update client states
        for client in self.synthetic_clients:
            # Randomly toggle activity
            if random.random() < 0.1:  # 10% chance to change state
                client['active'] = not client['active']
            
            # Move clients slightly
            if client['active']:
                client['x'] += random.uniform(-10, 10)
                client['y'] += random.uniform(-10, 10)
                
                # Keep within boundaries of base station
                bs = self.synthetic_base_stations[client['base_station']]
                dist = np.sqrt((client['x'] - bs['x'])**2 + (client['y'] - bs['y'])**2)
                if dist > bs['radius']:
                    # Move back toward base station
                    angle = np.arctan2(bs['y'] - client['y'], bs['x'] - client['x'])
                    client['x'] += np.cos(angle) * 5
                    client['y'] += np.sin(angle) * 5
        
        # 2. Update slice allocations (occasionally)
        if self.simulation_step % 5 == 0:
            # Pick a random base station to adjust
            bs_id = random.randint(0, len(self.synthetic_base_stations) - 1)
            bs = self.synthetic_base_stations[bs_id]
            
            # Count active clients per slice for this BS
            active_clients = {slice_type: 0 for slice_type in self.slice_types}
            for client in self.synthetic_clients:
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
                    current = bs['slice_allocation'][slice_type]
                    ideal = ideal_allocation[slice_type]
                    # Move 20% toward ideal
                    bs['slice_allocation'][slice_type] = current * 0.8 + ideal * 0.2
            
            # Normalize to ensure sum = 1
            total = sum(bs['slice_allocation'].values())
            for slice_type in self.slice_types:
                bs['slice_allocation'][slice_type] /= total
        
        # 3. Update slice usage based on active clients
        for bs in self.synthetic_base_stations:
            bs_id = bs['id']
            # Calculate usage for each slice based on active clients
            usage = {slice_type: 0 for slice_type in self.slice_types}
            
            for client in self.synthetic_clients:
                if client['base_station'] == bs_id and client['active']:
                    slice_type = client['slice']
                    usage[slice_type] += client['data_rate'] * 0.1  # Scale down
            
            # Update slice usage (with random fluctuations)
            for slice_type in self.slice_types:
                # Calculate new usage with random fluctuation
                fluctuation = random.uniform(-0.05, 0.05)
                new_usage = usage[slice_type] + fluctuation
                
                # Smooth change over time (exponential smoothing)
                current = bs['slice_usage'][slice_type]
                bs['slice_usage'][slice_type] = current * 0.7 + new_usage * 0.3
                
                # Ensure usage doesn't exceed allocation
                max_usage = bs['slice_allocation'][slice_type]
                bs['slice_usage'][slice_type] = min(max_usage, bs['slice_usage'][slice_type])
                bs['slice_usage'][slice_type] = max(0, bs['slice_usage'][slice_type])
        
        return self.get_synthetic_state()
        
    def get_simulation_state(self):
        """Extract current state from the simulator"""
        if not self.simulator:
            return None
            
        # Get references to simulation components
        bs_list = self.simulator.base_stations
        clients = self.simulator.clients
        env = self.simulator.env
        
        # Extract base station data
        base_stations = []
        for i, bs in enumerate(bs_list):
            # Calculate slice allocations and usage
            slice_allocation = {}
            slice_usage = {}
            
            for slice_type in self.slice_types:
                # Get capacity for this slice
                if slice_type in bs.capacity:
                    total_capacity = bs.capacity[slice_type].capacity
                    current_level = bs.capacity[slice_type].level
                    slice_allocation[slice_type] = total_capacity / bs.total_capacity
                    slice_usage[slice_type] = current_level / total_capacity
                else:
                    slice_allocation[slice_type] = 0
                    slice_usage[slice_type] = 0
            
            # Create base station record
            base_stations.append({
                'id': i,
                'x': bs.x_pos,
                'y': bs.y_pos,
                'radius': bs.coverage_area,
                'capacity': bs.total_capacity,
                'slice_allocation': slice_allocation,
                'slice_usage': slice_usage
            })
        
        # Extract client data
        client_list = []
        for i, client in enumerate(clients):
            # Skip clients without a base station
            if client.base_station is None:
                continue
                
            # Find base station ID
            bs_id = bs_list.index(client.base_station) if client.base_station in bs_list else -1
            if bs_id == -1:
                continue
                
            # Determine slice type based on client subscription
            if client.subscribed_slice in self.slice_types:
                slice_type = client.subscribed_slice
            else:
                # Map subscription to known slice types
                if "eMBB" in client.subscribed_slice:
                    slice_type = "eMBB"
                elif "URLLC" in client.subscribed_slice:
                    slice_type = "URLLC"
                else:
                    slice_type = "mMTC"
            
            # Create client record
            client_list.append({
                'id': i,
                'x': client.x_pos,
                'y': client.y_pos,
                'base_station': bs_id,
                'slice': slice_type,
                'active': client.is_active,
                'data_rate': client.data_usage / 100.0  # Normalize to 0-1 range
            })
        
        # Return state snapshot
        return {
            'time': self.simulation_step,
            'base_stations': base_stations,
            'clients': client_list
        }
    
    def update_visualization_from_state(self, state):
        """Update visualization based on simulation state"""
        if not state:
            return
            
        # Extract data from state
        self.base_stations = state['base_stations']
        self.clients = state['clients']
        self.simulation_step = state['time']
        
        # Format data for visualization
        self.slice_allocation = {slice_type: [] for slice_type in self.slice_types}
        self.slice_usage = {slice_type: [] for slice_type in self.slice_types}
        
        for bs in self.base_stations:
            for slice_type in self.slice_types:
                if slice_type in bs['slice_allocation']:
                    self.slice_allocation[slice_type].append(bs['slice_allocation'][slice_type])
                    self.slice_usage[slice_type].append(bs['slice_usage'][slice_type])
                else:
                    self.slice_allocation[slice_type].append(0)
                    self.slice_usage[slice_type].append(0)
        
        # Update all visualizations
        self.draw_network()
        self.update_slice_allocation()
        self.update_traffic_plot()
        self.update_qos_parameters()
    
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
        self.fig.text(0.5, 0.01, "Displaying real simulation data - Press 'n' to advance simulation step", 
                      ha='center', fontsize=12, bbox=dict(facecolor='lightgray', alpha=0.5))
    
    def draw_network(self):
        """Draw the network topology with slices"""
        if not hasattr(self, 'base_stations') or not self.base_stations:
            return
            
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
        
        for i, slice_type in enumerate(self.slice_types):
            # Skip if slice doesn't exist for this base station
            if slice_type not in bs['slice_allocation']:
                continue
                
            angle = 2 * np.pi * (i / len(self.slice_types))
            indicator_x = x + radius * np.cos(angle)
            indicator_y = y + radius * np.sin(angle)
            
            # Get allocation and usage for this slice at this BS
            allocation = bs['slice_allocation'][slice_type]
            usage = bs['slice_usage'][slice_type]
            
            if allocation <= 0:
                continue  # Skip slices with no allocation
            
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
    
    def update_slice_allocation(self):
        """Update slice allocation chart"""
        if not hasattr(self, 'slice_allocation') or not self.slice_allocation:
            return
            
        self.axs[1].clear()
        self.axs[1].set_title("Slice Allocation Per Base Station")
        self.axs[1].set_ylim(0, 1.2)
        self.axs[1].set_xlabel("Base Station ID")
        self.axs[1].set_ylabel("Percentage of Resources")
        
        num_bs = len(self.base_stations)
        x = np.arange(num_bs)
        width = 0.25
        
        # Get data for each slice
        for i, slice_type in enumerate(self.slice_types):
            allocation = self.slice_allocation[slice_type]
            
            bottom = np.zeros(num_bs)
            if i > 0:
                for j in range(i):
                    prev_slice = self.slice_types[j]
                    bottom += np.array(self.slice_allocation[prev_slice])
            
            # Draw bars
            self.axs[1].bar(x, allocation, width, bottom=bottom, 
                           label=slice_type, color=self.slice_colors[slice_type])
            
            # Add usage indicators (colored dots inside bars)
            for bs_id in range(num_bs):
                usage = self.slice_usage[slice_type][bs_id]
                usage_y = bottom[bs_id] + usage * allocation[bs_id]
                self.axs[1].scatter(bs_id, usage_y, color='black', s=30, zorder=3)
        
        self.axs[1].set_xticks(x)
        self.axs[1].set_xticklabels([f"BS {i}" for i in range(num_bs)])
        self.axs[1].legend()
        self.axs[1].grid(axis='y', linestyle='--', alpha=0.7)
    
    def update_traffic_plot(self):
        """Update traffic load history plot"""
        if not hasattr(self, 'slice_usage') or not self.slice_usage:
            return
            
        self.axs[2].clear()
        self.axs[2].set_title("Dynamic Traffic Load")
        self.axs[2].set_xlim(max(0, self.simulation_step - 50), max(100, self.simulation_step + 10))
        self.axs[2].set_ylim(0, 1.2)
        self.axs[2].set_xlabel("Time")
        self.axs[2].set_ylabel("Network Load")
        
        # Generate or update traffic data
        if not hasattr(self, 'traffic_data'):
            # Initialize traffic data for each slice
            self.traffic_data = {
                slice_type: [sum(self.slice_usage[slice_type]) / max(1, len(self.base_stations))] 
                for slice_type in self.slice_types
            }
            self.time_points = [self.simulation_step]
        else:
            # Add the current frame's data
            for slice_type in self.slice_types:
                current_load = sum(self.slice_usage[slice_type]) / max(1, len(self.base_stations))
                self.traffic_data[slice_type].append(current_load)
            self.time_points.append(self.simulation_step)
        
        # Plot traffic data for each slice
        for slice_type in self.slice_types:
            self.axs[2].plot(self.time_points, self.traffic_data[slice_type], 
                            label=slice_type, color=self.slice_colors[slice_type], 
                            linewidth=2)
            
        self.axs[2].legend()
        self.axs[2].grid(True, linestyle='--', alpha=0.7)
    
    def update_qos_parameters(self):
        """Update QoS parameters visualization"""
        if not hasattr(self, 'slice_usage') or not self.slice_usage:
            return
            
        self.axs[3].clear()
        self.axs[3].set_title("QoS Parameters by Slice")
        self.axs[3].set_ylim(0, 1.2)
        self.axs[3].set_xticks(np.arange(len(self.slice_types)))
        self.axs[3].set_xticklabels(self.slice_types)
        
        # Define QoS parameters per slice type 
        # These would normally be dynamic but we'll use calculated values
        qos_params = {
            # Each has bandwidth, latency, reliability - normalized to 0-1
            "eMBB": [0.9, 0.5, 0.7],   # High bandwidth, medium latency/reliability 
            "URLLC": [0.4, 0.95, 0.95], # Lower bandwidth, very low latency, high reliability
            "mMTC": [0.2, 0.4, 0.8]     # Low bandwidth, tolerant latency, good reliability
        }
        
        # Calculate current QoS based on usage vs allocation
        for slice_type in self.slice_types:
            avg_usage = sum(self.slice_usage[slice_type]) / max(1, len(self.base_stations))
            avg_allocation = sum(self.slice_allocation[slice_type]) / max(1, len(self.base_stations))
            
            # Adjust QoS based on load
            if avg_allocation > 0:
                load_ratio = avg_usage / avg_allocation
                # Bandwidth degrades with high utilization
                qos_params[slice_type][0] *= max(0.5, 1 - 0.5 * load_ratio)
                # Latency increases (gets worse) with high utilization
                qos_params[slice_type][1] *= max(0.5, 1 - 0.3 * load_ratio) 
                # Reliability degrades slightly with high utilization
                qos_params[slice_type][2] *= max(0.7, 1 - 0.2 * load_ratio)
        
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
            avg_usage = sum(self.slice_usage[slice_type]) / max(1, len(self.base_stations))
            avg_allocation = sum(self.slice_allocation[slice_type]) / max(1, len(self.base_stations))
            
            if avg_allocation > 0:
                load = avg_usage / avg_allocation
                self.axs[3].axhline(y=load, xmin=(i/len(self.slice_types)), 
                                  xmax=((i+1)/len(self.slice_types)), 
                                  color=self.slice_colors[slice_type], linestyle='--', 
                                  linewidth=2, label=f"{slice_type} Load")
        
        self.axs[3].legend(fontsize=8)
        self.axs[3].grid(axis='y', linestyle='--', alpha=0.7)
    
    def advance_simulation(self, steps=1):
        """Advance the simulation by the specified number of steps"""
        print(f"Advancing simulation by {steps} steps...")
        
        try:
            # Advance simulation based on mode
            if self.use_synthetic_data:
                for _ in range(steps):
                    self.simulation_step += 1
                    state = self.update_synthetic_state()
                    self.state_history.append(state)
                    self.update_visualization_from_state(state)
                    plt.pause(0.1)  # Give time for display to update
            elif self.simulator:
                # Run the simulation for specified steps
                for _ in range(steps):
                    self.simulator.run_step()
                    self.simulation_step += 1
                    
                    # Capture state
                    state = self.get_simulation_state()
                    self.state_history.append(state)
                    
                    # Update visualization
                    self.update_visualization_from_state(state)
                    plt.pause(0.1)  # Give time for display to update
            else:
                print("No simulation available")
                return False
                
            return True
            
        except Exception as e:
            print(f"Error advancing simulation: {str(e)}")
            # If we encounter an error with the actual simulation, switch to synthetic
            if not self.use_synthetic_data:
                print("Switching to synthetic data mode...")
                self.use_synthetic_data = True
                self.generate_synthetic_data(len(self.base_stations), len(self.clients))
                return self.advance_simulation(steps)
            return False
    
    def on_key_press(self, event):
        """Handle key press events"""
        if event.key == 'n':
            # Advance simulation by 1 step
            self.advance_simulation(1)
        elif event.key == 's':
            # Advance simulation by 10 steps
            self.advance_simulation(10)
    
    def run(self):
        """Run the visualization"""
        # Connect key press events
        self.fig.canvas.mpl_connect('key_press_event', self.on_key_press)
        
        plt.tight_layout(rect=[0, 0.03, 1, 0.95])  # Adjust for title and bottom text
        plt.show()

# Run the simulation when script is executed
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="5G Network Slicing Visualization")
    parser.add_argument("--base-stations", type=int, default=5, help="Number of base stations")
    parser.add_argument("--clients", type=int, default=30, help="Number of clients")
    parser.add_argument("--simulation-time", type=int, default=100, help="Simulation time")
    parser.add_argument("--synthetic", action="store_true", help="Force use of synthetic data")
    args = parser.parse_args()
    
    print("5G Network Slicing Real-time Visualization")
    print("----------------------------------------")
    print("This visualization shows network slicing in action.")
    print("\nPress 'n' to advance simulation by 1 step")
    print("Press 's' to advance simulation by 10 steps")
    
    # If synthetic flag is set, force synthetic data mode
    if args.synthetic:
        USE_SYNTHETIC_DATA = True
    
    # Create visualizer
    visualizer = RealSliceVisualizer()
    
    # Connect to simulation
    visualizer.connect_simulation(
        base_stations=args.base_stations,
        clients=args.clients,
        simulation_time=args.simulation_time
    )
    
    # Run visualization
    visualizer.run() 