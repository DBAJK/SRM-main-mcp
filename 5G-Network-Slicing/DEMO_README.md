# AI-Native Network Slicing Demo Tools

This directory contains demo tools for visualizing and testing the AI-based network slicing optimization system. These tools demonstrate how the AI models improve network slice allocation and traffic classification in different scenarios.

## Available Demo Tools

### 1. Interactive Demo (`interactive_demo.py`)

A real-time interactive GUI application that visualizes network metrics with and without AI optimization.

**Features:**
- Live visualization of latency, throughput, and resource utilization for each slice type
- Toggle between AI and non-AI optimization to see the difference
- Choose between different scenarios (baseline, dynamic, emergency, smart city)
- Adjust simulation speed
- Visualize emergency events in real-time

**Usage:**
```bash
python interactive_demo.py [--scenario SCENARIO] [--duration DURATION]
```

**Arguments:**
- `--scenario`: Initial scenario to load (baseline, dynamic, emergency, smart_city)
- `--duration`: Simulation duration in seconds (default: 300)

**Example:**
```bash
python interactive_demo.py --scenario emergency
```

### 2. Scenario Runner (`scenario_runner.py`)

Batch runs different scenarios and generates detailed comparison reports and visualizations.

**Features:**
- Runs all or specific scenarios with both AI and non-AI optimization
- Generates detailed metrics and comparison statistics
- Creates visualization plots showing the performance differences
- Saves results as JSON files for further analysis

**Usage:**
```bash
python scenario_runner.py [--scenario SCENARIO] [--duration DURATION] [--output-dir OUTPUT_DIR] [--model-path MODEL_PATH]
```

**Arguments:**
- `--scenario`: Scenario to run (baseline, dynamic, emergency, smart_city, all)
- `--duration`: Simulation duration (default: 100)
- `--output-dir`: Directory to save results (default: results)
- `--model-path`: Path to load AI models from (optional)

**Example:**
```bash
python scenario_runner.py --scenario all --duration 200
```

## Scenarios

The demo tools include the following pre-configured scenarios:

1. **Baseline**: Uniform network load across all slice types
   - Constant traffic pattern
   - Even distribution of eMBB, URLLC, and mMTC traffic

2. **Dynamic**: Daily traffic patterns with varying loads
   - Sinusoidal traffic pattern simulating daily usage cycles
   - Higher eMBB traffic proportion

3. **Emergency**: Sudden spike in critical communications
   - Traffic spike during emergency period
   - Higher URLLC traffic proportion
   - Shows how AI adapts to sudden changes in demand

4. **Smart City**: Diverse IoT and multimedia traffic
   - Mixed traffic pattern with increasing trend
   - Higher proportion of mMTC and eMBB traffic
   - Complex traffic patterns with multiple components

## Metrics

The demos track the following key metrics:

- **Latency (ms)**: End-to-end delay for each slice type
  - Lower is better, especially critical for URLLC

- **Throughput (Mbps)**: Data transfer rate for each slice type
  - Higher is better, especially important for eMBB

- **Resource Utilization**: Efficiency of resource usage
  - Optimal value is around 0.75 (75%)
  - Shows how well resources are allocated to each slice

## AI Optimization Benefits

The demos highlight the following benefits of AI optimization:

1. **Adaptive Resource Allocation**: The LSTM predictor dynamically adjusts resource allocation based on traffic patterns and demand.

2. **Traffic Classification**: The DQN classifier identifies traffic types to apply appropriate QoS policies.

3. **Improved QoS**: AI optimization reduces latency, increases throughput, and optimizes resource utilization.

4. **Emergency Response**: AI models show significant improvement during emergency scenarios by prioritizing critical communications.

## Requirements

To run the demo tools, you need:

- Python 3.6+
- TensorFlow 2.x
- NumPy
- Matplotlib
- tkinter (for interactive demo)

These dependencies are included in the project's requirements.txt file.

## Troubleshooting

If you encounter issues with the AI modules, the demos will fall back to simulated AI behavior. Check the console output for any error messages related to importing the AI modules. 