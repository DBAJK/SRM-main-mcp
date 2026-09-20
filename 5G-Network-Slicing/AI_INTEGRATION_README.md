# AI Integration for 5G Network Slicing

This document provides an overview of the AI modules integrated into the 5G Network Slicing Simulation project to optimize resource allocation and traffic classification.

## Overview

The AI integration consists of two main components:

1. **LSTM-based Slice Allocation Predictor**: Predicts the optimal allocation of resources across different slice types (eMBB, URLLC, mMTC) based on historical network state data.

2. **DQN-based Traffic Classifier**: Uses reinforcement learning to classify network traffic into appropriate slice types based on client characteristics and network conditions.

## Directory Structure

```
5G-Network-Slicing/
├── slicesim/
│   ├── ai/
│   │   ├── __init__.py
│   │   ├── lstm_predictor.py     # LSTM model for slice allocation
│   │   └── dqn_classifier.py     # DQN model for traffic classification
│   ├── slice_optimization.py     # Integration of AI with slice allocation
│   └── ...
├── ai_slice_demo.py              # Demo script for AI-enhanced network slicing
├── requirements.txt              # Updated with AI dependencies
└── ...
```

## AI Models

### LSTM Predictor for Slice Allocation

The `SliceAllocationPredictor` class in `lstm_predictor.py` uses a Long Short-Term Memory (LSTM) neural network to predict the optimal allocation of network resources across different slice types. It takes into account:

- Historical slice utilization
- Client distribution
- Network load patterns
- Time-based patterns

The model outputs allocation percentages for each slice type that maximize overall network performance.

### DQN Classifier for Traffic Classification

The `TrafficClassifier` class in `dqn_classifier.py` implements a Deep Q-Network (DQN) to classify network traffic into appropriate slice types. It considers:

- Client data rate requirements
- Base station capacity
- Current slice utilization
- QoS requirements

The model learns over time to optimize slice assignment for better overall network performance.

## Slice Optimization Integration

The `SliceOptimizer` class in `slice_optimization.py` serves as the central integration point, combining:

1. Both AI models for decision-making
2. Fallback heuristic methods when AI is unavailable
3. Data collection for training
4. Model management (saving/loading)

## Running the AI-Enhanced Demo

To run the demo with AI optimization:

```bash
python ai_slice_demo.py --base-stations 5 --clients 50
```

### Command-line Arguments

- `--config <path>`: Path to configuration file
- `--base-stations <num>`: Number of base stations
- `--clients <num>`: Number of clients
- `--simulation-time <time>`: Simulation time
- `--train`: Train AI models before demo
- `--train-data <path>`: Path to training data file
- `--load-models <path>`: Path to load AI models from
- `--save-models <path>`: Path to save AI models to
- `--no-ai`: Disable AI optimization
- `--compare`: Run comparison between AI and non-AI

### Example: Training and Comparing

To train the models and compare AI vs. non-AI performance:

```bash
python ai_slice_demo.py --train --save-models models/ --compare
```

## Performance Metrics

The AI integration tracks and compares several metrics:

1. **Slice Utilization**: How efficiently the network slices are utilized
2. **Client Satisfaction**: Based on QoS parameters appropriate for each slice type
3. **Resource Efficiency**: Overall efficiency of resource allocation
4. **Handovers**: Number of client handovers between base stations/slices
5. **Rejected Clients**: Clients rejected due to capacity constraints

## Requirements

The AI integration requires additional dependencies:
- TensorFlow >= 2.10.0
- TensorBoard >= 2.10.0
- h5py >= 3.7.0
- scikit-learn >= 1.1.0

Install all dependencies with:

```bash
pip install -r requirements.txt
```

## Future Enhancements

Potential improvements to the AI integration:

1. **Federated Learning**: Distribute model training across multiple base stations
2. **Explainable AI**: Add visualization of decision-making process
3. **Online Learning**: Continuously update models during simulation
4. **Multi-objective Optimization**: Explicitly balance multiple competing objectives 