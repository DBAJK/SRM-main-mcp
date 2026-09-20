# 5G Network Slicing Orchestrator Demo

This project demonstrates the capabilities of a 5G network slicing orchestrator, which dynamically allocates resources between different network slices based on traffic patterns and network events.

## Overview

The orchestrator manages three types of network slices:

1. **eMBB (enhanced Mobile Broadband)** - For high-bandwidth applications like video streaming
2. **URLLC (Ultra-Reliable Low-Latency Communications)** - For applications requiring low latency and high reliability
3. **mMTC (massive Machine Type Communications)** - For IoT devices and sensors

The demo simulates different network conditions and shows how the orchestrator adapts resource allocation in real-time.

## Features

- Dynamic resource allocation between network slices
- Simulation of different network events:
  - Emergency situations (prioritizes URLLC)
  - Special events (prioritizes eMBB)
  - IoT surges (prioritizes mMTC)
- Real-time visualization of network state
- QoS violation detection and mitigation
- Historical data tracking and analysis

## Requirements

- Python 3.6+
- NumPy
- Matplotlib

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/5g-network-slicing.git
cd 5g-network-slicing

# Install dependencies
pip install numpy matplotlib
```

## Usage

Run the demo with default settings:

```bash
python orchestrator_demo.py
```

### Command-line Options

- `--duration SECONDS` - Run duration in seconds (default: 60)
- `--interval SECONDS` - Update interval in seconds (default: 1.0)
- `--emergency` - Simulate emergency situation
- `--special-event` - Simulate special event
- `--iot-surge` - Simulate IoT device surge

### Examples

Simulate a 2-minute emergency situation:

```bash
python orchestrator_demo.py --duration 120 --emergency
```

Simulate a special event with faster updates:

```bash
python orchestrator_demo.py --special-event --interval 0.5
```

## Output

The demo creates a directory under `results/` with:

- PNG images showing the network state at each step
- A JSON file with the complete history of the simulation

## License

MIT 