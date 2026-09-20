import math
import os
import random
import sys
import time
from threading import Event

import simpy
import yaml

from slicesim.BaseStation import BaseStation
from slicesim.Client import Client
from slicesim.Coverage import Coverage
from slicesim.Distributor import Distributor
from slicesim.Graph import Graph
from slicesim.Slice import Slice
from slicesim.Stats import Stats
from slicesim.utils import KDTree
from slicesim.network_graph import NetworkGraphVisualization

# Global control flags
simulation_running = Event()
simulation_paused = Event()
current_time = 0

def get_dist(d):
    return {
        'randrange': random.randrange, # start, stop, step
        'randint': random.randint, # a, b
        'random': random.random,
        'uniform': random, # a, b
        'triangular': random.triangular, # low, high, mode
        'beta': random.betavariate, # alpha, beta
        'expo': random.expovariate, # lambda
        'gamma': random.gammavariate, # alpha, beta
        'gauss': random.gauss, # mu, sigma
        'lognorm': random.lognormvariate, # mu, sigma
        'normal': random.normalvariate, # mu, sigma
        'vonmises': random.vonmisesvariate, # mu, kappa
        'pareto': random.paretovariate, # alpha
        'weibull': random.weibullvariate # alpha, beta
    }.get(d)


def get_random_mobility_pattern(vals, mobility_patterns):
    i = 0
    r = random.random()
    while vals[i] < r:
        i += 1
    return mobility_patterns[i]


def get_random_slice_index(vals):
    i = 0
    r = random.random()
    while vals[i] < r:
        i += 1
    return i


def wait_for_user_input():
    """Wait for user input to control simulation"""
    global current_time
    while True:
        cmd = input(f"\nTime: {current_time} - Enter command (r: run 10 steps, p: pause, q: quit): ")
        if cmd.lower() == 'r':
            simulation_paused.clear()  # Unpause
            simulation_running.set()    # Start/Continue running
            return True
        elif cmd.lower() == 'p':
            simulation_paused.set()     # Pause
            simulation_running.clear()   # Stop running
            return True
        elif cmd.lower() == 'q':
            simulation_running.clear()   # Stop running
            return False
        else:
            print("Invalid command. Use 'r' to run, 'p' to pause, or 'q' to quit.")


def run_simulation(config_file, base_stations=None, clients=None, simulation_time=None, network_only=False):
    """Run the 5G network slicing simulation with the given config file and optional overrides"""
    global current_time
    
    # Read YAML file
    try:
        with open(config_file, 'r') as stream:
            data = yaml.load(stream, Loader=yaml.FullLoader)
    except FileNotFoundError:
        print('File Not Found:', config_file)
        return

    # Use a fixed seed for reproducibility, but allow it to be dynamic
    random.seed()
    env = simpy.Environment()

    SETTINGS = data['settings']
    SLICES_INFO = data['slices']
    NUM_CLIENTS = clients if clients is not None else SETTINGS['num_clients']
    MOBILITY_PATTERNS = data['mobility_patterns']
    BASE_STATIONS_DATA = data['base_stations']
    CLIENTS = data['clients']

    # Make clients more mobile
    for mobility in MOBILITY_PATTERNS.values():
        if 'params' in mobility and len(mobility['params']) >= 2:
            # Increase mobility parameters by multiplying by 2-3
            mobility['params'] = [p * random.uniform(2, 3) for p in mobility['params']]

    # Make slice usage more dynamic
    for slice_info in SLICES_INFO.values():
        if 'usage_pattern' in slice_info and 'params' in slice_info['usage_pattern']:
            # Increase usage variation
            slice_info['usage_pattern']['params'] = [
                p * random.uniform(0.8, 1.5) for p in slice_info['usage_pattern']['params']
            ]

    # Override simulation time if provided
    if simulation_time is not None:
        SETTINGS['simulation_time'] = simulation_time
    else:
        # Default to short simulation for better control
        SETTINGS['simulation_time'] = 200

    # Enable console output and real-time plotting
    sys.stdout = sys.__stdout__
    SETTINGS['plotting_params']['plot_show'] = True
    SETTINGS['plotting_params']['plotting'] = True

    # Randomize client and base station distributions for more interesting visuals
    if base_stations is not None or clients is not None:
        # Apply random variations to client locations
        if 'location' in CLIENTS:
            for coord in ['x', 'y']:
                if coord in CLIENTS['location']:
                    # Widen the distribution
                    if 'params' in CLIENTS['location'][coord] and len(CLIENTS['location'][coord]['params']) >= 2:
                        range_width = CLIENTS['location'][coord]['params'][1] - CLIENTS['location'][coord]['params'][0]
                        CLIENTS['location'][coord]['params'][0] -= range_width * 0.2
                        CLIENTS['location'][coord]['params'][1] += range_width * 0.2

    # Adjust base station count if provided
    if base_stations is not None and base_stations != len(BASE_STATIONS_DATA):
        # Sample or create additional base stations as needed
        if base_stations > len(BASE_STATIONS_DATA):
            # Create more base stations by placing them in random positions
            x_vals = SETTINGS['statistics_params']['x']
            y_vals = SETTINGS['statistics_params']['y']
            
            # Get the ratios from the first base station as a template
            template_ratios = BASE_STATIONS_DATA[0]['ratios']
            template_capacity = BASE_STATIONS_DATA[0]['capacity_bandwidth']
            template_coverage = BASE_STATIONS_DATA[0]['coverage']
            
            # Randomize slice allocations more for dynamic visualization
            slice_names = list(template_ratios.keys())
            
            # Generate additional base stations
            for i in range(len(BASE_STATIONS_DATA), base_stations):
                # Create randomized ratios that still sum to 1
                new_ratios = {}
                remaining = 1.0
                
                # Assign random ratios to each slice
                for name in slice_names[:-1]:
                    max_ratio = remaining * 0.8  # Leave some for the last slice
                    ratio = random.uniform(0.05, max_ratio)
                    new_ratios[name] = ratio
                    remaining -= ratio
                
                # Assign the remainder to the last slice
                new_ratios[slice_names[-1]] = remaining
                
                # Create new base station with random position
                new_bs = {
                    'x': random.uniform(x_vals['min'], x_vals['max']),
                    'y': random.uniform(y_vals['min'], y_vals['max']),
                    'coverage': template_coverage + random.uniform(-50, 50),  # Randomize coverage
                    'capacity_bandwidth': template_capacity * random.uniform(0.8, 1.2),  # Randomize capacity
                    'ratios': new_ratios
                }
                BASE_STATIONS_DATA.append(new_bs)
        else:
            # Reduce the number of base stations
            BASE_STATIONS_DATA = BASE_STATIONS_DATA[:base_stations]

    # Initialize components (same as before)
    collected, slice_weights = 0, []
    for __, s in SLICES_INFO.items():
        collected += s['client_weight']
        slice_weights.append(collected)

    collected, mb_weights = 0, []
    for __, mb in MOBILITY_PATTERNS.items():
        collected += mb['client_weight']
        mb_weights.append(collected)

    mobility_patterns = []
    for name, mb in MOBILITY_PATTERNS.items():
        mobility_pattern = Distributor(name, get_dist(mb['distribution']), *mb['params'])
        mobility_patterns.append(mobility_pattern)

    usage_patterns = {}
    for name, s in SLICES_INFO.items():
        usage_patterns[name] = Distributor(name, get_dist(s['usage_pattern']['distribution']), *s['usage_pattern']['params'])

    base_stations = []
    for i, b in enumerate(BASE_STATIONS_DATA):
        slices = []
        ratios = b['ratios']
        capacity = b['capacity_bandwidth']
        for name, s in SLICES_INFO.items():
            s_cap = capacity * ratios[name]
            s = Slice(name, ratios[name], 0, s['client_weight'],
                    s['delay_tolerance'],
                    s['qos_class'], s['bandwidth_guaranteed'],
                    s['bandwidth_max'], s_cap, usage_patterns[name])
            s.capacity = simpy.Container(env, init=s_cap, capacity=s_cap)
            slices.append(s)
        base_station = BaseStation(i, Coverage((b['x'], b['y']), b['coverage']), capacity, slices)
        base_stations.append(base_station)

    ufp = CLIENTS['usage_frequency']
    usage_freq_pattern = Distributor(f'ufp', get_dist(ufp['distribution']), *ufp['params'], divide_scale=ufp['divide_scale'])

    x_vals = SETTINGS['statistics_params']['x']
    y_vals = SETTINGS['statistics_params']['y']
    stats = Stats(env, base_stations, None, ((x_vals['min'], x_vals['max']), (y_vals['min'], y_vals['max'])))

    clients = []
    for i in range(NUM_CLIENTS):
        loc_x = CLIENTS['location']['x']
        loc_y = CLIENTS['location']['y']
        location_x = get_dist(loc_x['distribution'])(*loc_x['params'])
        location_y = get_dist(loc_y['distribution'])(*loc_y['params'])

        mobility_pattern = get_random_mobility_pattern(mb_weights, mobility_patterns)
        connected_slice_index = get_random_slice_index(slice_weights)
        
        c = Client(i, env, location_x, location_y,
                mobility_pattern, usage_freq_pattern.generate_scaled(), 
                connected_slice_index, stats)
        clients.append(c)

    # Initialize simulation
    KDTree.limit = SETTINGS['limit_closest_base_stations']
    KDTree.run(clients, base_stations, 0)
    stats.clients = clients
    env.process(stats.collect())

    # Create visualization
    xlim_left = 0
    xlim_right = 100  # Show last 100 time steps
    
    # Create regular visualization if not network_only mode
    if not network_only:
        graph = Graph(base_stations, clients, (xlim_left, xlim_right),
                    ((x_vals['min'], x_vals['max']), (y_vals['min'], y_vals['max'])),
                    output_dpi=SETTINGS['plotting_params']['plot_file_dpi'],
                    scatter_size=SETTINGS['plotting_params']['scatter_size'],
                    output_filename=SETTINGS['plotting_params']['plot_file'])

    # Create network graph visualization
    network_graph = NetworkGraphVisualization(base_stations, clients)

    # Initial setup
    print("\n5G Network Slicing Simulation")
    print("-----------------------------")
    print(f"Base Stations: {len(base_stations)}")
    print(f"Clients: {len(clients)}")
    print(f"Simulation Time: {SETTINGS['simulation_time']}")
    print("\nControls:")
    print("r - Run simulation for 10 time steps")
    print("p - Pause simulation")
    print("q - Quit simulation")

    # Start visualizations
    if not network_only:
        graph.draw_live(*stats.get_stats())
    network_graph.show()
    
    # Interactive simulation loop
    simulation_running.clear()  # Start paused
    simulation_paused.set()
    
    # Create a function to add random traffic changes
    def apply_random_traffic_changes():
        # Randomly select more base stations to modify (for more visible changes)
        for bs in random.sample(base_stations, k=min(4, len(base_stations))):
            # Select 1-2 random slices to modify
            if bs.slices:
                slices_to_modify = random.sample(bs.slices, k=min(2, len(bs.slices)))
                for slice_to_modify in slices_to_modify:
                    # Apply more dramatic random traffic spike or drop
                    usage_change = slice_to_modify.capacity.capacity * random.uniform(-0.6, 0.8)
                    
                    # Calculate new level ensuring it stays within bounds
                    current_level = slice_to_modify.capacity.level
                    
                    # Determine action based on level change
                    if usage_change > 0:  # Increasing traffic (reducing available capacity)
                        # Don't try to use more than what's available
                        amount_to_get = min(current_level, usage_change)
                        if amount_to_get > 0:
                            try:
                                slice_to_modify.capacity.get(amount_to_get)
                                action = "increased"
                                percent = (amount_to_get / slice_to_modify.capacity.capacity) * 100
                                print(f"Traffic {action} by {percent:.1f}% on {slice_to_modify.name} at BS_{bs.id}")
                            except Exception as e:
                                print(f"Could not increase traffic on {slice_to_modify.name}: {str(e)}")
                    else:  # Decreasing traffic (increasing available capacity)
                        # Don't exceed capacity
                        amount_to_put = min(slice_to_modify.capacity.capacity - current_level, -usage_change)
                        if amount_to_put > 0:
                            try:
                                slice_to_modify.capacity.put(amount_to_put)
                                action = "decreased"
                                percent = (amount_to_put / slice_to_modify.capacity.capacity) * 100
                                print(f"Traffic {action} by {percent:.1f}% on {slice_to_modify.name} at BS_{bs.id}")
                            except Exception as e:
                                print(f"Could not decrease traffic on {slice_to_modify.name}: {str(e)}")
    
    while True:
        if not wait_for_user_input():  # User wants to quit
            break
            
        if simulation_running.is_set():
            # Run for 10 time steps
            for _ in range(10):
                # Apply traffic changes more frequently
                if random.random() < 0.5:  # 50% chance each step instead of 30%
                    apply_random_traffic_changes()
                
                env.run(until=env.now + 1)
                current_time = int(env.now)
                time.sleep(0.05)  # Smaller delay for faster visualization
                
                # Update visualizations
                if not network_only:
                    # Regular graph is already being updated via the animation function
                    pass
                
                # Update the network graph visualization
                network_graph.update()
                
                if simulation_paused.is_set():
                    break
    
    print("\nSimulation ended.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print('Please type an input file.')
        print('python -m slicesim <input-file>')
        exit(1)
    
    config_file = os.path.join(os.path.dirname(__file__), sys.argv[1])
    run_simulation(config_file)
