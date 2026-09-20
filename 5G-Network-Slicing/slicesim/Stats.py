import numpy as np
import matplotlib.pyplot as plt

class Stats:
    """Statistics collector for simulation"""
    
    def __init__(self, env, base_stations, clients):
        """Initialize statistics collector
        
        Args:
            env (simpy.Environment): Simulation environment
            base_stations (list): List of base stations
            clients (list): List of clients
        """
        self.env = env
        self.base_stations = base_stations
        self.clients = clients
        
        # Initialize stats containers
        self.time_points = []
        
        # Slice utilization over time
        self.slice_utilization = {}  # {slice_name: [utilization_values]}
        
        # Connected clients over time
        self.connected_clients = []
        
        # Per-slice client counts
        self.slice_client_counts = {}  # {slice_name: [client_counts]}
        
        # Initialize slice stats
        all_slice_names = set()
        for bs in base_stations:
            for s in bs.slices.values():
                all_slice_names.add(s.name)
        
        for slice_name in all_slice_names:
            self.slice_utilization[slice_name] = []
            self.slice_client_counts[slice_name] = []
    
    def collect_stats(self):
        """Collect statistics at regular intervals"""
        while True:
            # Wait for next collection point
            yield self.env.timeout(1)  # Collect every 1 time unit
            
            # Record time
            current_time = self.env.now
            self.time_points.append(current_time)
            
            # Collect base station and slice stats
            slice_utils = {name: [] for name in self.slice_utilization.keys()}
            slice_clients = {name: 0 for name in self.slice_client_counts.keys()}
            
            for bs in self.base_stations:
                for s in bs.slices.values():
                    # Record slice utilization
                    utilization = 1.0 - (s.capacity.level / s.capacity.capacity)
                    slice_utils[s.name].append(utilization)
            
            # Count connected clients per slice
            connected_count = 0
            for client in self.clients:
                if client.base_station:
                    connected_count += 1
                    slice_clients[client.slice_type] += 1
            
            # Store stats
            self.connected_clients.append(connected_count)
            
            # Store average utilization per slice
            for slice_name, utils in slice_utils.items():
                if utils:  # Only if we have values
                    avg_util = sum(utils) / len(utils)
                    self.slice_utilization[slice_name].append(avg_util)
                else:
                    self.slice_utilization[slice_name].append(0)
            
            # Store client counts per slice
            for slice_name, count in slice_clients.items():
                self.slice_client_counts[slice_name].append(count)
    
    def display_stats(self):
        """Display collected statistics"""
        if not self.time_points or len(self.time_points) < 2:
            print("Not enough statistics collected to display")
            return
        
        # Create figure with subplots
        fig, axs = plt.subplots(2, 2, figsize=(12, 8))
        
        # 1. Slice Utilization Over Time
        ax = axs[0, 0]
        for slice_name, utils in self.slice_utilization.items():
            if len(utils) == len(self.time_points):  # Ensure same length
                ax.plot(self.time_points, utils, label=slice_name)
        
        ax.set_xlabel('Time')
        ax.set_ylabel('Utilization')
        ax.set_title('Slice Utilization Over Time')
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        # 2. Connected Clients Over Time
        ax = axs[0, 1]
        if len(self.connected_clients) == len(self.time_points):
            ax.plot(self.time_points, self.connected_clients)
        ax.set_xlabel('Time')
        ax.set_ylabel('Connected Clients')
        ax.set_title('Connected Clients Over Time')
        ax.grid(True, alpha=0.3)
        
        # 3. Clients Per Slice Over Time
        ax = axs[1, 0]
        for slice_name, counts in self.slice_client_counts.items():
            ax.plot(self.time_points, counts, label=slice_name)
        
        ax.set_xlabel('Time')
        ax.set_ylabel('Client Count')
        ax.set_title('Clients Per Slice Over Time')
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        # 4. Average Slice Utilization (Bar Chart)
        ax = axs[1, 1]
        slice_names = list(self.slice_utilization.keys())
        avg_utils = [sum(utils)/len(utils) if utils else 0 for utils in self.slice_utilization.values()]
        
        ax.bar(slice_names, avg_utils)
        ax.set_xlabel('Slice Type')
        ax.set_ylabel('Average Utilization')
        ax.set_title('Average Slice Utilization')
        ax.grid(True, alpha=0.3, axis='y')
        
        # Adjust layout and show
        plt.tight_layout()
        plt.show()
        
        # Print summary statistics
        print("\n=== Simulation Statistics ===")
        print(f"Simulation time: {self.time_points[-1]} units")
        print(f"Average connected clients: {sum(self.connected_clients)/len(self.connected_clients):.2f}")
        
        print("\nSlice Utilization:")
        for slice_name, utils in self.slice_utilization.items():
            if utils:
                avg_util = sum(utils)/len(utils)
                print(f"  {slice_name}: {avg_util*100:.2f}%")
        
        print("\nAverage Clients per Slice:")
        for slice_name, counts in self.slice_client_counts.items():
            if counts:
                avg_count = sum(counts)/len(counts)
                print(f"  {slice_name}: {avg_count:.2f} clients")
        