#!/usr/bin/env python3
import os
import sys
import argparse
import subprocess

def print_banner(title):
    """Print a banner for the selected demo"""
    width = 60
    print("\n" + "=" * width)
    print(f"{title:^{width}}")
    print("=" * width + "\n")

def run_command(command, cwd="."):
    """Run a command in the specified directory"""
    try:
        subprocess.run(command, shell=True, check=True, cwd=cwd)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {e}")
        return False

def generate_data(args):
    """Generate network slicing data"""
    print_banner("Generating 5G Network Slicing Data")
    
    cmd = "python generate_data.py"
    cmd += f" --steps {args.steps}"
    cmd += f" --clients {args.clients}"
    cmd += f" --base-stations {args.base_stations}"
    cmd += f" --mobility {args.mobility}"
    cmd += f" --variance {args.variance}"
    cmd += f" --output {args.output}"
    
    if args.csv_dir:
        cmd += f" --csv-dir {args.csv_dir}"
    
    print(f"Running: {cmd}")
    return run_command(cmd, ".")

def run_simple_vis(args):
    """Run the simple visualization demo"""
    print_banner("Running Simple Visualization Demo")
    
    cmd = "python simple_vis.py"
    print(f"Running: {cmd}")
    return run_command(cmd, ".")

def run_realtime_vis(args):
    """Run the real-time visualization with generated data"""
    print_banner("Running Real-time Visualization")
    
    cmd = "python realtime_vis.py"
    
    if args.data:
        cmd += f" --data {args.data}"
    
    if args.animate:
        cmd += " --animate"
    
    cmd += f" --speed {args.speed}"
    
    print(f"Running: {cmd}")
    return run_command(cmd, ".")

def run_slice_demo(args):
    """Run the simulation connection demo"""
    print_banner("Running Slice Demo (Simulation Connection)")
    
    cmd = "python slice_demo.py"
    cmd += f" --base-stations {args.base_stations}"
    cmd += f" --clients {args.clients}"
    
    if args.synthetic:
        cmd += " --synthetic"
    
    print(f"Running: {cmd}")
    return run_command(cmd, ".")

def run_network_graph_vis(args):
    """Run the network graph visualization"""
    print_banner("Running Network Graph Visualization")
    
    cmd = "python -c \"from slicesim.network_graph import NetworkGraph; NetworkGraph().run()\""
    
    print(f"Running: {cmd}")
    return run_command(cmd, ".")

def run_simulation(args):
    """Run the main simulation with visualization"""
    print_banner("Running Full Simulation with Visualization")
    
    cmd = "python run.py"
    cmd += f" --base-stations {args.base_stations}"
    cmd += f" --clients {args.clients}"
    
    if args.network_only:
        cmd += " --network-only"
        
    print(f"Running: {cmd}")
    return run_command(cmd, ".")

def run_full_demo(args):
    """Run a full demonstration sequence"""
    print_banner("Running Full 5G Network Slicing Demonstration")
    
    # Step 1: Generate data for visualization
    print("Step 1: Generating network data...")
    gen_args = argparse.Namespace(
        steps=50, 
        clients=40, 
        base_stations=6,
        mobility=0.4,
        variance=0.6,
        output="demo_data.json",
        csv_dir=None
    )
    if not generate_data(gen_args):
        return False
    
    # Step 2: Run simple visualization
    print("\nStep 2: Running simple visualization...")
    if not run_simple_vis(argparse.Namespace()):
        print("Simple visualization was closed. Continuing with demo...")
    
    # Step 3: Run real-time visualization with generated data
    print("\nStep 3: Running real-time visualization with generated data...")
    vis_args = argparse.Namespace(
        data="demo_data.json",
        animate=True,
        speed=1.0
    )
    if not run_realtime_vis(vis_args):
        print("Real-time visualization was closed. Continuing with demo...")
    
    # Step 4: Run network graph visualization
    print("\nStep 4: Running network graph visualization...")
    if not run_network_graph_vis(argparse.Namespace()):
        print("Network graph visualization was closed. Continuing with demo...")
    
    # Step 5: Run simulation with visualization
    print("\nStep 5: Running full simulation with network visualization...")
    sim_args = argparse.Namespace(
        base_stations=6,
        clients=40,
        network_only=True
    )
    return run_simulation(sim_args)

def check_files_exist():
    """Check if all required visualization files exist"""
    required_files = [
        "simple_vis.py",
        "realtime_vis.py",
        "slice_demo.py",
        "generate_data.py",
        "run.py"
    ]
    
    missing_files = []
    for file in required_files:
        if not os.path.exists(file):
            missing_files.append(file)
    
    if missing_files:
        print("Warning: The following required files are missing:")
        for file in missing_files:
            print(f" - {file}")
        print("\nSome demo options may not work correctly.")
    
    # Check for network_graph.py in slicesim directory
    if not os.path.exists("slicesim/network_graph.py"):
        print("Warning: slicesim/network_graph.py is missing.")
        print("The network graph visualization option may not work.")

def main():
    """Main entry point for the demo launcher"""
    parser = argparse.ArgumentParser(description="5G Network Slicing Visualization Demo Launcher")
    
    # Add subparsers for different demos
    subparsers = parser.add_subparsers(dest="demo", help="Demo to run")
    
    # Simple visualization demo
    simple_parser = subparsers.add_parser("simple", help="Run the simple visualization demo")
    
    # Data generator
    gen_parser = subparsers.add_parser("generate", help="Generate network slicing data")
    gen_parser.add_argument("--steps", type=int, default=50, help="Number of simulation steps")
    gen_parser.add_argument("--clients", type=int, default=40, help="Number of clients")
    gen_parser.add_argument("--base-stations", type=int, default=6, help="Number of base stations")
    gen_parser.add_argument("--mobility", type=float, default=0.3, help="Mobility level (0-1)")
    gen_parser.add_argument("--variance", type=float, default=0.4, help="Traffic variance (0-1)")
    gen_parser.add_argument("--output", type=str, default="network_data.json", help="Output file")
    gen_parser.add_argument("--csv-dir", type=str, help="Directory for CSV output")
    
    # Real-time visualization
    rt_parser = subparsers.add_parser("realtime", help="Run the real-time visualization")
    rt_parser.add_argument("--data", type=str, help="Path to data file")
    rt_parser.add_argument("--animate", action="store_true", help="Run as animation")
    rt_parser.add_argument("--speed", type=float, default=1.0, help="Animation speed")
    
    # Slice demo (simulation connection)
    slice_parser = subparsers.add_parser("slice", help="Run the simulation connection demo")
    slice_parser.add_argument("--base-stations", type=int, default=6, help="Number of base stations")
    slice_parser.add_argument("--clients", type=int, default=40, help="Number of clients")
    slice_parser.add_argument("--synthetic", action="store_true", help="Force synthetic data")
    
    # Network graph visualization
    graph_parser = subparsers.add_parser("graph", help="Run the network graph visualization")
    
    # Run simulation with visualization
    sim_parser = subparsers.add_parser("simulation", help="Run the main simulation with visualization")
    sim_parser.add_argument("--base-stations", type=int, default=8, help="Number of base stations")
    sim_parser.add_argument("--clients", type=int, default=50, help="Number of clients")
    sim_parser.add_argument("--network-only", action="store_true", help="Run in network-only mode")
    
    # Full demo mode
    full_parser = subparsers.add_parser("full", help="Run a full demonstration sequence")
    
    # Parse arguments
    args = parser.parse_args()
    
    # Check Python dependencies
    try:
        import numpy
        import matplotlib
        import pandas
    except ImportError as e:
        print(f"Missing dependency: {e}")
        print("Please install required dependencies:")
        print("pip install numpy matplotlib pandas")
        return 1
    
    # Check if required files exist
    check_files_exist()
    
    # Run the selected demo
    if args.demo == "simple":
        run_simple_vis(args)
    elif args.demo == "generate":
        generate_data(args)
    elif args.demo == "realtime":
        run_realtime_vis(args)
    elif args.demo == "slice":
        run_slice_demo(args)
    elif args.demo == "graph":
        run_network_graph_vis(args)
    elif args.demo == "simulation":
        run_simulation(args)
    elif args.demo == "full":
        run_full_demo(args)
    else:
        # If no demo specified, show help
        parser.print_help()
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 