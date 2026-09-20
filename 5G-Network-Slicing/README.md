# 5G Network Slicing System

A machine learning-based system for dynamic resource allocation in 5G network slicing.

## Overview

This project implements a comprehensive 5G network slicing system that uses machine learning to optimize resource allocation across different network slices (eMBB, URLLC, mMTC). The system can adapt to changing traffic patterns and emergency situations, ensuring that critical services receive the resources they need.

Key features:
- Dynamic resource allocation using LSTM-based machine learning models
- Support for different slice types (eMBB, URLLC, mMTC) with varying QoS requirements
- Handling of emergency scenarios with prioritized resource allocation
- Real-time visualization and monitoring of network performance
- Comparison of traditional static allocation vs. ML-based dynamic allocation

## Architecture

The system consists of the following components:

1. **Orchestrator**: Coordinates the slice management and model predictions, providing a centralized control point.
2. **Slice Manager**: Allocates resources to different network slices based on various strategies.
3. **Models**: LSTM-based neural networks for predicting optimal slice allocations.
4. **Configuration**: Handles system settings and parameters.
5. **Utilities**: Common functions for data processing, visualization, and evaluation.
6. **Simulation**: Simulates network behavior under different scenarios.
7. **Demo**: Interactive demonstration of the system's capabilities.

## Installation

### Prerequisites

- Python 3.8 or higher
- TensorFlow 2.x
- NumPy, Pandas, Matplotlib
- Other dependencies listed in `requirements.txt`

### Setup

1. Clone the repository:
   ```
   git clone https://github.com/yourusername/5G-Network-Slicing.git
   cd 5G-Network-Slicing
   ```

2. Install dependencies:
   ```
    pip install -r requirements.txt
    ```

3. Create necessary directories:
   ```
   mkdir -p results models data
   ```

## Usage

### Training Data Generation

Generate synthetic training data:

```
python -m slicesim.ai.generate_data --samples 1000 --output data/training
```

### Model Training

Train a single-step LSTM model:

```
python -m slicesim.ai.train_model --input data/training --output models/lstm_single --seq_length 10 --out_steps 1 --epochs 50
```

Train a multi-step (autoregressive) LSTM model:

```
python -m slicesim.ai.train_model --input data/training --output models/lstm_multi --seq_length 10 --out_steps 5 --epochs 50
```

### Running Simulations

Run a simulation comparing static and ML-based allocation:

```
python main.py simulate --model models/lstm_single --steps 100 --output results/simulation_1
```

With emergency events at specific steps:

```
python main.py simulate --model models/lstm_single --steps 100 --emergency 20,21,22,60,61,62 --output results/simulation_emergency
```

### Running the Orchestrator

Run the orchestrator in real-time:

```
python main.py orchestrate --model models/lstm_single --duration 60
```

With emergency mode:

```
python main.py orchestrate --model models/lstm_single --duration 60 --emergency
```

### Interactive Demo

Run the interactive demo:

```
python main.py demo --model models/lstm_single
```

## Configuration

The system can be configured through a JSON configuration file. A default configuration is provided, but you can create your own:

```json
{
  "system": {
    "log_level": "INFO",
    "results_dir": "results",
    "models_dir": "models"
  },
  "slices": {
    "types": ["eMBB", "URLLC", "mMTC"],
    "default_allocation": [0.4, 0.4, 0.2],
    "qos_thresholds": {
      "eMBB": 0.9,
      "URLLC": 1.2,
      "mMTC": 0.8
    },
    "emergency_allocation": [0.2, 0.7, 0.1]
  },
  "simulation": {
    "duration": 100,
    "emergency_duration": 20,
    "emergency_probability": 0.1,
    "traffic_patterns": {
      "eMBB": {
        "base_level": 0.4,
        "variance": 0.2,
        "emergency_factor": 0.8
      },
      "URLLC": {
        "base_level": 0.3,
        "variance": 0.1,
        "emergency_factor": 2.0
      },
      "mMTC": {
        "base_level": 0.2,
        "variance": 0.15,
        "emergency_factor": 0.9
      }
    }
  },
  "model": {
    "type": "single_step",
    "input_dim": 11,
    "sequence_length": 10,
    "out_steps": 1,
    "lstm_units": 64,
    "batch_size": 32,
    "epochs": 50,
    "learning_rate": 0.001,
    "train_test_split": 0.8
  }
}
```

To use a custom configuration:

```
python main.py simulate --config my_config.json --model models/lstm_single
```

## Results and Visualization

The system generates various visualizations to help understand the performance:

1. **Traffic Pattern**: Shows the traffic load for each slice type over time.
2. **Allocation Comparison**: Compares static and ML-based allocation strategies.
3. **Utilization**: Shows how efficiently resources are being used.
4. **QoS Violations**: Tracks when utilization exceeds QoS thresholds.
5. **Summary**: Provides an overview of the simulation results.

Results are saved in the specified output directory (default: `results/`).

## Project Structure

```
5G-Network-Slicing/
├── main.py                 # Main entry point
├── README.md               # This file
├── requirements.txt        # Dependencies
├── slicesim/               # Main package
│   ├── __init__.py
│   ├── config.py           # Configuration module
│   ├── demo.py             # Interactive demo
│   ├── orchestrator.py     # Orchestrator module
│   ├── simulation.py       # Simulation module
│   ├── utils.py            # Utility functions
│   └── ai/                 # AI components
│       ├── __init__.py
│       ├── generate_data.py # Data generation
│       ├── models.py       # Model definitions
│       ├── slice_manager.py # Slice manager
│       └── train_model.py  # Model training
├── data/                   # Data directory
│   └── training/           # Training data
├── models/                 # Trained models
└── results/                # Simulation results
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgements

- This project was inspired by research on network slicing in 5G networks.
- Thanks to the TensorFlow team for their excellent machine learning framework.
- Special thanks to all contributors and researchers in the field of network slicing.
