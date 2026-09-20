import random
import simpy
import numpy as np
from .BaseStation import BaseStation
from .Client import Client
from .Coverage import Coverage
from .Distributor import Distributor
from .Graph import Graph
from .Slice import Slice
from .Stats import Stats
from .utils import format_bps, distance, KDTree
try:
    from .network_graph import NetworkGraphVisualization as NetworkGraph
except ImportError:
    NetworkGraph = None

class Simulator:
    """Main simulator class for 5G network slicing"""
    
    def __init__(self, base_stations=5, clients=30, simulation_time=100, mobility=5):
        """Initialize the simulator
        
        Args:
            base_stations (int): Number of base stations
            clients (int): Number of clients
            simulation_time (int): Simulation time in seconds
            mobility (int): Mobility level (0-10)
        """
        self.num_base_stations = base_stations
        self.num_clients = clients
        self.simulation_time = simulation_time
        self.mobility = mobility / 10.0  # Convert 0-10 scale to 0-1
        
        # Initialize simulation environment
        self.env = simpy.Environment()
        
        # Create base stations with slices
        self.base_stations = self._create_base_stations()
        
        # Create clients
        self.clients = self._create_clients()
        
        # Create stats collector
        self.stats = Stats(self.env, self.base_stations, self.clients)
        
        # Create network graph visualization
        self.network_graph = NetworkGraph(self.base_stations, self.clients)
        
        print(f"Initialized simulator with {base_stations} base stations and {clients} clients")
    
    def _create_base_stations(self):
        """Create base stations with coverage areas and slices"""
        base_stations = []
        
        # Define area size based on number of base stations
        area_size = max(1000, self.num_base_stations * 200)
        
        # Create base stations with even distribution
        for i in range(self.num_base_stations):
            # Calculate position to distribute stations evenly
            row = i // int(np.sqrt(self.num_base_stations))
            col = i % int(np.sqrt(self.num_base_stations))
            
            # Add some randomness to position
            x = (col + 0.5) * (area_size / np.sqrt(self.num_base_stations))
            y = (row + 0.5) * (area_size / np.sqrt(self.num_base_stations))
            
            # Add random offset
            x += random.uniform(-50, 50)
            y += random.uniform(-50, 50)
            
            # Create coverage area
            coverage_radius = random.uniform(100, 200)
            coverage = Coverage((x, y), coverage_radius)
            
            # Create base station
            bs = BaseStation(i, coverage.center[0], coverage.center[1], coverage.radius)
            
            # Add slices to base station
            self._add_slices_to_base_station(bs)
            
            base_stations.append(bs)
        
        return base_stations
    
    def _add_slices_to_base_station(self, base_station):
        """Add different slice types to a base station"""
        # eMBB slice (Enhanced Mobile Broadband)
        embb_capacity = random.uniform(80, 120) * 1e6  # 80-120 Mbps
        embb_slice = Slice("eMBB", embb_capacity, self.env)
        base_station.add_slice(embb_slice)
        
        # URLLC slice (Ultra-Reliable Low-Latency Communications)
        urllc_capacity = random.uniform(20, 40) * 1e6  # 20-40 Mbps
        urllc_slice = Slice("URLLC", urllc_capacity, self.env)
        base_station.add_slice(urllc_slice)
        
        # mMTC slice (Massive Machine-Type Communications)
        mmtc_capacity = random.uniform(5, 15) * 1e6  # 5-15 Mbps
        mmtc_slice = Slice("mMTC", mmtc_capacity, self.env)
        base_station.add_slice(mmtc_slice)
        
        # Voice slice
        voice_capacity = random.uniform(10, 20) * 1e6  # 10-20 Mbps
        voice_slice = Slice("voice", voice_capacity, self.env)
        base_station.add_slice(voice_slice)
    
    def _create_clients(self):
        """Create clients with different service requirements"""
        clients = []
        
        # Get maximum coordinates from base stations
        max_x = max(bs.coverage.center[0] + bs.coverage.radius for bs in self.base_stations)
        max_y = max(bs.coverage.center[1] + bs.coverage.radius for bs in self.base_stations)
        
        # Build KD-Tree for faster nearest neighbor search
        bs_positions = [(bs.coverage.center[0], bs.coverage.center[1]) for bs in self.base_stations]
        kdtree = KDTree(bs_positions)
        
        # Distribution of client types
        client_types = {
            "eMBB": 0.4,    # 40% of clients are eMBB
            "URLLC": 0.2,   # 20% of clients are URLLC
            "mMTC": 0.3,    # 30% of clients are mMTC
            "voice": 0.1    # 10% of clients are voice
        }
        
        # Create clients
        for i in range(self.num_clients):
            # Randomly place client within area
            x = random.uniform(0, max_x)
            y = random.uniform(0, max_y)
            
            # Determine client type based on distribution
            client_type = np.random.choice(
                list(client_types.keys()),
                p=list(client_types.values())
            )
            
            # Create client
            client = Client(
                client_id=i,
                x=x,
                y=y,
                slice_type=client_type,
                env=self.env
            )
            
            # Find nearest base station using KD-Tree
            dist, nearest_idx = kdtree.query((x, y), k=1)
            nearest_bs = self.base_stations[nearest_idx]
            
            # Connect client to nearest base station
            client.connect_to_base_station(nearest_bs)
            
            clients.append(client)
        
        return clients
    
    def run(self):
        """Run the full simulation"""
        # Start client processes
        for client in self.clients:
            self.env.process(client.generate_traffic())
        
        # Start statistics collection
        self.env.process(self.stats.collect_stats())
        
        # Start network visualization
        self.network_graph.show()
        
        # Start applying random traffic changes
        self.env.process(self._apply_random_traffic_changes())
        
        # Run simulation
        try:
            self.env.run(until=self.simulation_time)
        except Exception as e:
            print(f"Simulation error: {e}")
        
        # Display statistics
        self.stats.display_stats()
    
    def run_network_visualization(self):
        """Run only the network visualization"""
        # Start network visualization
        self.network_graph.run()
    
    def _apply_random_traffic_changes(self):
        """Apply random traffic changes to simulate varying network conditions"""
        while True:
            # Wait some time
            yield self.env.timeout(1)
            
            # 50% chance of applying traffic changes
            if random.random() < 0.5:
                # Select 1-2 random base stations
                num_bs_to_modify = random.randint(1, min(2, len(self.base_stations)))
                selected_bs = random.sample(self.base_stations, num_bs_to_modify)
                
                for bs in selected_bs:
                    # Select 1-2 random slices to modify
                    num_slices_to_modify = random.randint(1, min(2, len(bs.slices)))
                    selected_slices = random.sample(bs.slices, num_slices_to_modify)
                    
                    for s in selected_slices:
                        # Generate random traffic spike or drop between -60% and +80%
                        change_factor = random.uniform(-0.6, 0.8)
                        
                        # Calculate the amount of capacity to modify
                        current_level = s.capacity.level
                        total_capacity = s.capacity.capacity
                        
                        # Calculate how much to change the usage by
                        change_amount = abs(change_factor * total_capacity) 
                        
                        try:
                            if change_factor > 0:
                                # Traffic increase (get from container)
                                amount_to_get = min(change_amount, current_level)
                                if amount_to_get > 0:
                                    s.capacity.get(amount_to_get)
                            else:
                                # Traffic decrease (put into container)
                                amount_to_put = min(change_amount, total_capacity - current_level)
                                if amount_to_put > 0:
                                    s.capacity.put(amount_to_put)
                        except Exception as e:
                            # Handle any errors with capacity get/put
                            print(f"Error modifying traffic for {s.name}: {e}") 