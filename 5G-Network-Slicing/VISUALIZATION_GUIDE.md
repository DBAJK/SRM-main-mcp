# 5G Network Slicing Visualization Guide

This guide provides an overview of the visualization tools available in this project for demonstrating 5G network slicing concepts and benefits.

## What is Network Slicing?

Network slicing is a key technology in 5G networks that allows a single physical network infrastructure to be partitioned into multiple virtual networks (slices), each tailored to serve specific types of applications with different performance requirements:

- **eMBB (Enhanced Mobile Broadband)**: High data rates for applications like video streaming and web browsing
- **URLLC (Ultra-Reliable Low-Latency Communications)**: Minimal delay for applications like autonomous vehicles and remote surgery
- **mMTC (Massive Machine-Type Communications)**: Efficient connectivity for a massive number of IoT devices

## Available Visualization Tools

### Simple Visualization (`simple_vis.py`)

A static visualization that demonstrates network slicing with synthetic data.

**Features:**
- Base station visualization with slice allocations
- Client distribution across different slices
- Resource allocation per slice type

**How to run:**
```
python simple_vis.py
```

### Data Generator (`generate_data.py`)

Generates realistic 5G network slicing data for visualization.

**Features:**
- Configurable network parameters (base stations, clients)
- Generation of time-series data for slice allocation and utilization
- Output in JSON format for use with other visualization tools

**How to run:**
```
python generate_data.py --steps 100 --base-stations 8 --clients 50 --output network_data.json
```

### Real-Time Visualization (`realtime_vis.py`)

A dynamic visualization that shows network data changing over time.

**Features:**
- Animated slice utilization
- Time-series graphs for resource allocation
- QoS monitoring per slice

**How to run:**
```
python realtime_vis.py --data network_data.json
```

### Simulation Connection (`slice_demo.py`)

Connects to the simulation backend for real-time data or uses synthetic data.

**Features:**
- Real-time data from simulation backend
- Fallback to synthetic data
- Interactive control of simulation parameters

**How to run:**
```
python slice_demo.py --simulation
```

### Network Graph Visualization (`network_graph.py`)

An animated graph-based visualization showing network topology and slice utilization.

**Features:**
- Network topology visualization
- Animated traffic flows between base stations
- Dynamic client connections

**How to run (as part of simulation):**
```
python run.py --base-stations 8 --clients 50 --network-only
```

## Using Generated Data with Visualization Tools

All of our visualization tools can work with either real-time simulation data or pre-generated data:

### Running Network Graph with Pre-generated Data

You can now use the `run.py` script with the `--data` parameter to visualize pre-generated data without running a full simulation:

```
python run.py --data network_data.json
```

This loads the network topology and traffic patterns from the JSON file and displays them using the interactive NetworkGraph visualization.

**Interactive Controls:**
- Press 'n' to advance to the next step
- Press 'p' to go back to the previous step
- Press 's' to skip 10 steps forward
- Press 'r' to restart from the beginning
- Press 'a' to toggle automatic playback

### Full Simulation (`run.py`)

Runs the complete 5G network slicing simulation with visualization.

**Features:**
- Full network simulation
- Multiple base stations with slices
- Client mobility and traffic patterns
- Real-time resource allocation

**How to run:**
```
python run.py --base-stations 8 --clients 50
```

**Options:**
- `--network-only`: Show only network visualization
- `--data`: Use pre-generated data instead of running a simulation
- `--mobility`: Set client mobility level (0-10)

### Demo Launcher (`run_demo.py`)

A unified script to launch any of the visualization tools.

**Features:**
- Single entry point for all demos
- Sequential execution of different visualizations
- Command-line options for customization

**How to run:**
```
python run_demo.py [simple|realtime|network|simulation|full]
```

## Key Insights from Visualizations

Through these visualizations, you can observe several important aspects of network slicing:

1. **Dynamic Resource Allocation**: See how resources are allocated differently across slices based on their requirements
2. **QoS Management**: Observe how different service levels are maintained for different application types
3. **Efficiency Improvements**: Visualize how the same physical infrastructure serves diverse application needs
4. **Resource Utilization**: Monitor how network resources are utilized across different slices
5. **Mobility Handling**: See how client mobility affects resource allocation and network performance

## Complete Demo Workflow

For a comprehensive demonstration of network slicing, run:

```
python run_demo.py full
```

This will sequentially:
1. Generate realistic network data
2. Run the simple visualization
3. Run the real-time visualization
4. Run the network graph visualization
5. Run the full simulation

Alternatively, use individual steps as needed:

```
# Generate data
python generate_data.py --output network_data.json

# Visualize data
python run.py --data network_data.json

# Or run full simulation
python run.py --base-stations 8 --clients 50
```

These visualizations together provide a comprehensive understanding of how 5G network slicing works and its benefits for diverse application requirements. 