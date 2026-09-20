import os
import sys
import argparse
import json
from slicesim.Simulator import Simulator
from slicesim.network_graph import NetworkGraphVisualization as NetworkGraph

def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="5G Network Slicing Simulator")
    parser.add_argument('--base-stations', type=int, default=8,
                        help='Number of base stations')
    parser.add_argument('--clients', type=int, default=50,
                        help='Number of clients')
    parser.add_argument('--simulation-time', type=int, default=100,
                        help='Simulation time')
    parser.add_argument('--network-only', action='store_true',
                        help='Run in network visualization only mode')
    parser.add_argument('--data', type=str, default=None,
                        help='Path to JSON data file for visualization (bypasses simulation)')
    parser.add_argument('--mobility', type=int, default=5,
                      help='Client mobility level (0-10)')
    
    return parser.parse_args()

def run_simulation(args):
    """Run the simulation with the specified parameters"""
    # Create simulator instance
    sim = Simulator(
        base_stations=args.base_stations,
        clients=args.clients,
        simulation_time=args.simulation_time,
        mobility=args.mobility
    )
    
    # Run simulation
    print(f"Running simulation with {args.base_stations} base stations and {args.clients} clients...")
    
    if args.network_only:
        # Run only network visualization
        print("Running in network-only mode...")
        sim.run_network_visualization()
    else:
        # Run full simulation
        print("Running full simulation...")
        sim.run()
        
    print("Simulation completed.")

def run_with_data(args):
    """Run visualization using pregenerated data"""
    # Load the data
    print(f"Loading data from {args.data}...")
    try:
        with open(args.data, 'r') as f:
            data = json.load(f)
        
        print(f"Loaded {len(data)} time steps from {args.data}")
        
        # Create network graph instance
        graph = NetworkGraph()
        
        # Run animation with data
        print("Running visualization with loaded data...")
        graph.run_with_data(data)
        
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"Error loading data file: {e}")
        return

def main():
    """Main entry point"""
    args = parse_args()
    
    if args.data:
        # Run with pregenerated data
        run_with_data(args)
    else:
        # Run normal simulation
        run_simulation(args)

if __name__ == "__main__":
    main() 