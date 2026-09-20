#!/usr/bin/env python3
"""
Demo for Enhanced Autoregressive LSTM Predictor for Network Slice Allocation

This script demonstrates the capabilities of the enhanced autoregressive LSTM
predictor for multi-step network slice allocation prediction.

The demo:
1. Creates an instance of the AutoregressiveLSTMPredictor
2. Generates synthetic training data
3. Trains the model
4. Visualizes the training history
5. Makes predictions for multiple scenarios
6. Visualizes the predictions

3GPP Standards Compliance:
- Implements slice types according to 3GPP TS 23.501 (SST values)
- Supports QoS parameters defined in 3GPP TS 23.501 Section 5.7
- Aligns with Network Slice Selection Assistance Information (NSSAI) concept
"""

import os
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime
import tensorflow as tf
import argparse
import logging

# Import the enhanced LSTM predictor and slice manager
from slicesim.ai.enhanced_lstm_predictor import AutoregressiveLSTMPredictor
from slicesim.ai.slice_manager import EnhancedSliceManager

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def demo_autoregressive_lstm(args):
    """Run the demo for the autoregressive LSTM predictor
    
    Args:
        args: Command-line arguments
    """
    # Print TensorFlow version and GPU availability
    logger.info(f"TensorFlow version: {tf.__version__}")
    logger.info(f"GPU available: {tf.config.list_physical_devices('GPU')}")
    
    # Create output directory if it doesn't exist
    os.makedirs(args.output_dir, exist_ok=True)
    
    # Create checkpoint directory if it doesn't exist
    checkpoint_dir = os.path.join(args.output_dir, "checkpoints")
    os.makedirs(checkpoint_dir, exist_ok=True)
    
    # Create model path
    model_path = os.path.join(args.output_dir, "autoregressive_lstm_model.h5")
    
    # Create predictor
    logger.info("Creating autoregressive LSTM predictor...")
    predictor = AutoregressiveLSTMPredictor(
        input_dim=args.input_dim,
        sequence_length=args.sequence_length,
        out_steps=args.out_steps,
        model_path=model_path if os.path.exists(model_path) else None
    )
    
    # Generate training data if not loading a pre-trained model
    if not os.path.exists(model_path) or args.retrain:
        logger.info("Generating training data...")
        X_train, y_train, X_val, y_val = predictor._generate_training_data(args.num_samples)
        
        # Train model
        logger.info("Training model...")
        history = predictor.train(
            X_train, y_train,
            epochs=args.epochs,
            batch_size=args.batch_size,
            validation_data=(X_val, y_val),
            checkpoint_dir=checkpoint_dir
        )
        
        # Save model
        predictor.save(model_path)
        logger.info(f"Model saved to {model_path}")
        
        # Plot training history
        plt.figure(figsize=(12, 5))
        
        plt.subplot(1, 2, 1)
        plt.plot(history.history['loss'], label='Training Loss')
        plt.plot(history.history['val_loss'], label='Validation Loss')
        plt.title('Loss')
        plt.xlabel('Epoch')
        plt.ylabel('Loss')
        plt.legend()
        
        plt.subplot(1, 2, 2)
        plt.plot(history.history['mae'], label='Training MAE')
        plt.plot(history.history['val_mae'], label='Validation MAE')
        plt.title('Mean Absolute Error')
        plt.xlabel('Epoch')
        plt.ylabel('MAE')
        plt.legend()
        
        plt.tight_layout()
        plt.savefig(os.path.join(args.output_dir, "training_history.png"))
        if args.show_plots:
            plt.show()
    
    # Generate test scenarios
    logger.info("Generating test scenarios...")
    test_scenarios = generate_test_scenarios(
        predictor.sequence_length,
        predictor.input_dim,
        predictor.out_steps
    )
    
    # Make predictions for each scenario
    for scenario_name, (input_sequence, actual_future) in test_scenarios.items():
        logger.info(f"Making predictions for scenario: {scenario_name}")
        
        # Make prediction
        predictions = predictor.predict(input_sequence, return_all_steps=True)
        
        # Plot predictions
        plt.figure(figsize=(12, 6))
        
        # Create time steps
        input_steps = np.arange(predictor.sequence_length)
        future_steps = np.arange(predictor.sequence_length, predictor.sequence_length + predictor.out_steps)
        
        # Plot input sequence
        plt.plot(input_steps, input_sequence[:, 3], 'b-', label='Input eMBB Allocation')
        plt.plot(input_steps, input_sequence[:, 4], 'r-', label='Input URLLC Allocation')
        plt.plot(input_steps, input_sequence[:, 5], 'g-', label='Input mMTC Allocation')
        
        # Plot predictions
        plt.plot(future_steps, predictions[:, 0], 'b--', label='Predicted eMBB')
        plt.plot(future_steps, predictions[:, 1], 'r--', label='Predicted URLLC')
        plt.plot(future_steps, predictions[:, 2], 'g--', label='Predicted mMTC')
        
        # Plot actual future if provided
        if actual_future is not None:
            plt.plot(future_steps, actual_future[:, 0], 'bo', label='Actual eMBB')
            plt.plot(future_steps, actual_future[:, 1], 'ro', label='Actual URLLC')
            plt.plot(future_steps, actual_future[:, 2], 'go', label='Actual mMTC')
        
        plt.axvline(x=predictor.sequence_length-0.5, color='k', linestyle='-')
        plt.text(predictor.sequence_length-0.5, 0.5, 'Prediction', rotation=90)
        
        plt.title(f'Multi-step Slice Allocation Prediction - {scenario_name}')
        plt.xlabel('Time Step')
        plt.ylabel('Allocation Ratio')
        plt.legend()
        plt.grid(True)
        
        plt.tight_layout()
        plt.savefig(os.path.join(args.output_dir, f"prediction_{scenario_name}.png"))
        if args.show_plots:
            plt.show()
        
        # Calculate prediction error if actual future is provided
        if actual_future is not None:
            mae = np.mean(np.abs(predictions - actual_future))
            logger.info(f"Mean Absolute Error for {scenario_name}: {mae:.4f}")
    
    # Demo the enhanced slice manager
    if args.demo_slice_manager:
        demo_enhanced_slice_manager(args, predictor, test_scenarios)

def demo_enhanced_slice_manager(args, predictor, test_scenarios):
    """Demo the enhanced slice manager
    
    Args:
        args: Command-line arguments
        predictor: Trained predictor
        test_scenarios: Test scenarios
    """
    logger.info("Creating enhanced slice manager...")
    slice_manager = EnhancedSliceManager(
        input_dim=args.input_dim,
        sequence_length=args.sequence_length,
        out_steps=args.out_steps,
        model_path=os.path.join(args.output_dir, "autoregressive_lstm_model.h5"),
        checkpoint_dir=os.path.join(args.output_dir, "checkpoints")
    )
    
    # Simulate real-time slice allocation for a scenario
    scenario_name = "dynamic_traffic"  # Choose a scenario
    input_sequence, actual_future = test_scenarios[scenario_name]
    
    logger.info(f"Simulating real-time slice allocation for scenario: {scenario_name}")
    
    # Initialize history buffer with first few states
    for i in range(args.sequence_length - 1):
        slice_manager.update_history_buffer(input_sequence[i])
    
    # Simulate real-time allocation for the remaining states
    allocations = []
    for i in range(args.sequence_length - 1, args.sequence_length + args.out_steps):
        if i < args.sequence_length + args.out_steps - 1:
            # Get current state
            current_state = input_sequence[i] if i < len(input_sequence) else None
            
            # Get optimal allocation
            if current_state is not None:
                allocation = slice_manager.get_optimal_slice_allocation(current_state)
                allocations.append(allocation)
                logger.info(f"Step {i}: Allocation = {allocation}")
    
    # Plot allocations
    plt.figure(figsize=(12, 6))
    
    # Create time steps
    steps = np.arange(args.sequence_length - 1, args.sequence_length + args.out_steps - 1)
    
    # Plot allocations
    allocations = np.array(allocations)
    plt.plot(steps, allocations[:, 0], 'b-o', label='eMBB Allocation')
    plt.plot(steps, allocations[:, 1], 'r-o', label='URLLC Allocation')
    plt.plot(steps, allocations[:, 2], 'g-o', label='mMTC Allocation')
    
    plt.title(f'Real-time Slice Allocation - {scenario_name}')
    plt.xlabel('Time Step')
    plt.ylabel('Allocation Ratio')
    plt.legend()
    plt.grid(True)
    
    plt.tight_layout()
    plt.savefig(os.path.join(args.output_dir, f"real_time_allocation_{scenario_name}.png"))
    if args.show_plots:
        plt.show()

def generate_test_scenarios(sequence_length, input_dim, out_steps):
    """Generate test scenarios
    
    Args:
        sequence_length (int): Length of input sequence
        input_dim (int): Dimension of input features
        out_steps (int): Number of future steps to predict
        
    Returns:
        dict: Dictionary of test scenarios
    """
    scenarios = {}
    
    # Scenario 1: Baseline with daily pattern
    input_sequence = np.zeros((sequence_length, input_dim))
    actual_future = np.zeros((out_steps, 3))
    
    # Create time progression
    time_of_day = np.linspace(0.2, 0.6, sequence_length)  # Morning to afternoon
    
    # Generate input sequence
    for i in range(sequence_length):
        # Time factors
        time_factor = np.sin(time_of_day[i] * 2 * np.pi) * 0.3 + 0.5
        
        # Traffic load follows time pattern
        traffic_load = 0.5 + time_factor + 0.05 * np.random.randn()
        
        # Allocations start balanced and gradually favor eMBB
        embb_alloc = 0.33 + 0.01 * i
        urllc_alloc = 0.33 - 0.005 * i
        mmtc_alloc = 1.0 - embb_alloc - urllc_alloc
        
        # Utilization reflects time of day
        if time_of_day[i] < 0.5:  # Morning
            embb_util = 0.3 + 0.1 * i  # Increasing
            urllc_util = 0.4
            mmtc_util = 0.6 - 0.05 * i  # Decreasing
        else:  # Afternoon
            embb_util = 0.8
            urllc_util = 0.4 + 0.05 * (i - sequence_length/2)
            mmtc_util = 0.3
        
        # Client count increases during the day
        client_count = 0.3 + 0.5 * time_of_day[i]
        bs_count = 0.6
        
        # Create feature vector
        input_sequence[i] = np.array([
            traffic_load,
            time_of_day[i],
            0.5,  # day_of_week
            embb_alloc,
            urllc_alloc,
            mmtc_alloc,
            embb_util,
            urllc_util,
            mmtc_util,
            client_count,
            bs_count
        ])
    
    # Generate actual future (ground truth)
    future_time = np.linspace(time_of_day[-1], time_of_day[-1] + 0.2, out_steps)
    for i in range(out_steps):
        if future_time[i] < 0.7:  # Still daytime
            actual_future[i] = np.array([0.5, 0.3, 0.2])  # eMBB priority
        else:  # Evening
            actual_future[i] = np.array([0.4, 0.35, 0.25])  # More balanced
    
    scenarios["baseline_daily"] = (input_sequence, actual_future)
    
    # Scenario 2: Emergency scenario with URLLC spike
    input_sequence = np.zeros((sequence_length, input_dim))
    actual_future = np.zeros((out_steps, 3))
    
    # Generate input sequence
    for i in range(sequence_length):
        # Traffic increases as emergency unfolds
        traffic_load = 0.5 + 0.05 * i
        
        # Time factors
        time_of_day = 0.5  # Midday
        day_of_week = 0.5  # Midweek
        
        # Allocations gradually shift to URLLC
        if i < sequence_length // 2:
            # Before emergency
            embb_alloc = 0.5 - 0.02 * i
            urllc_alloc = 0.3 + 0.02 * i
            mmtc_alloc = 0.2
        else:
            # Emergency detected
            embb_alloc = 0.4 - 0.02 * (i - sequence_length // 2)
            urllc_alloc = 0.4 + 0.02 * (i - sequence_length // 2)
            mmtc_alloc = 0.2
        
        # Utilization shows URLLC spike
        if i < sequence_length // 2:
            embb_util = 0.7 - 0.02 * i
            urllc_util = 0.4 + 0.04 * i
            mmtc_util = 0.3
        else:
            embb_util = 0.6 - 0.02 * (i - sequence_length // 2)
            urllc_util = 0.6 + 0.08 * (i - sequence_length // 2)
            mmtc_util = 0.3
        
        # Client count increases during emergency
        client_count = 0.4 + 0.03 * i
        bs_count = 0.6
        
        # Create feature vector
        input_sequence[i] = np.array([
            traffic_load,
            time_of_day,
            day_of_week,
            embb_alloc,
            urllc_alloc,
            mmtc_alloc,
            embb_util,
            urllc_util,
            mmtc_util,
            client_count,
            bs_count
        ])
    
    # Generate actual future (ground truth)
    for i in range(out_steps):
        # Emergency continues, URLLC priority
        actual_future[i] = np.array([0.3 - 0.02 * i, 0.6 + 0.02 * i, 0.1])
    
    scenarios["emergency_urllc"] = (input_sequence, actual_future)
    
    # Scenario 3: Smart city with mMTC dominance
    input_sequence = np.zeros((sequence_length, input_dim))
    actual_future = np.zeros((out_steps, 3))
    
    # Generate input sequence
    for i in range(sequence_length):
        # Traffic is moderate and stable
        traffic_load = 0.6 + 0.02 * np.sin(i / 3)
        
        # Time factors
        time_of_day = 0.7  # Evening
        day_of_week = 0.8  # Weekend
        
        # Allocations favor mMTC for IoT
        embb_alloc = 0.3 - 0.01 * i
        mmtc_alloc = 0.4 + 0.01 * i
        urllc_alloc = 0.3
        
        # Utilization shows high mMTC
        embb_util = 0.4
        urllc_util = 0.3
        mmtc_util = 0.7 + 0.02 * i
        
        # Many IoT clients
        client_count = 0.7 + 0.01 * i
        bs_count = 0.8
        
        # Create feature vector
        input_sequence[i] = np.array([
            traffic_load,
            time_of_day,
            day_of_week,
            embb_alloc,
            urllc_alloc,
            mmtc_alloc,
            embb_util,
            urllc_util,
            mmtc_util,
            client_count,
            bs_count
        ])
    
    # Generate actual future (ground truth)
    for i in range(out_steps):
        # IoT activity continues to increase
        actual_future[i] = np.array([0.2, 0.2, 0.6 + 0.02 * i])
    
    scenarios["smart_city_mmtc"] = (input_sequence, actual_future)
    
    # Scenario 4: Dynamic traffic with spikes
    input_sequence = np.zeros((sequence_length, input_dim))
    actual_future = np.zeros((out_steps, 3))
    
    # Generate input sequence
    for i in range(sequence_length):
        # Traffic has random spikes
        if i % 3 == 0:
            traffic_load = 0.8 + 0.2 * np.random.random()
        else:
            traffic_load = 0.5 + 0.1 * np.random.random()
        
        # Time factors
        time_of_day = (0.3 + 0.05 * i) % 1.0
        day_of_week = 0.5
        
        # Allocations respond to traffic
        if i > 0:
            prev_traffic = input_sequence[i-1, 0]
            if traffic_load > prev_traffic + 0.2:
                # Traffic spike - adjust allocations
                embb_alloc = input_sequence[i-1, 3] - 0.05
                urllc_alloc = input_sequence[i-1, 4] + 0.03
                mmtc_alloc = input_sequence[i-1, 5] + 0.02
            elif traffic_load < prev_traffic - 0.2:
                # Traffic drop - adjust allocations
                embb_alloc = input_sequence[i-1, 3] + 0.05
                urllc_alloc = input_sequence[i-1, 4] - 0.02
                mmtc_alloc = input_sequence[i-1, 5] - 0.03
            else:
                # Stable traffic - small adjustments
                embb_alloc = input_sequence[i-1, 3] + 0.01 * np.random.randn()
                urllc_alloc = input_sequence[i-1, 4] + 0.01 * np.random.randn()
                mmtc_alloc = input_sequence[i-1, 5] + 0.01 * np.random.randn()
                
            # Normalize allocations
            total = embb_alloc + urllc_alloc + mmtc_alloc
            embb_alloc /= total
            urllc_alloc /= total
            mmtc_alloc /= total
        else:
            # Initial allocations
            embb_alloc = 0.4
            urllc_alloc = 0.3
            mmtc_alloc = 0.3
        
        # Utilization varies with traffic
        embb_util = 0.4 + 0.5 * traffic_load + 0.1 * np.random.randn()
        urllc_util = 0.3 + 0.4 * traffic_load + 0.1 * np.random.randn()
        mmtc_util = 0.3 + 0.3 * traffic_load + 0.1 * np.random.randn()
        
        # Client count follows traffic
        client_count = 0.3 + 0.5 * traffic_load
        bs_count = 0.6
        
        # Create feature vector
        input_sequence[i] = np.array([
            traffic_load,
            time_of_day,
            day_of_week,
            embb_alloc,
            urllc_alloc,
            mmtc_alloc,
            embb_util,
            urllc_util,
            mmtc_util,
            client_count,
            bs_count
        ])
    
    # Generate actual future (ground truth) - more traffic spikes
    for i in range(out_steps):
        if i % 2 == 0:
            # Traffic spike
            if i == 0:
                prev_embb = input_sequence[-1, 3]
                prev_urllc = input_sequence[-1, 4]
                prev_mmtc = input_sequence[-1, 5]
            else:
                prev_embb = actual_future[i-1, 0]
                prev_urllc = actual_future[i-1, 1]
                prev_mmtc = actual_future[i-1, 2]
                
            embb = prev_embb - 0.05
            urllc = prev_urllc + 0.03
            mmtc = prev_mmtc + 0.02
        else:
            # Traffic normalizes
            embb = actual_future[i-1, 0] + 0.03
            urllc = actual_future[i-1, 1] - 0.02
            mmtc = actual_future[i-1, 2] - 0.01
        
        # Normalize allocations
        total = embb + urllc + mmtc
        embb /= total
        urllc /= total
        mmtc /= total
        
        actual_future[i] = np.array([embb, urllc, mmtc])
    
    scenarios["dynamic_traffic"] = (input_sequence, actual_future)
    
    return scenarios

def parse_args():
    """Parse command-line arguments
    
    Returns:
        argparse.Namespace: Parsed arguments
    """
    parser = argparse.ArgumentParser(description='Demo for Enhanced Autoregressive LSTM Predictor')
    parser.add_argument('--input_dim', type=int, default=11,
                        help='Input dimension')
    parser.add_argument('--sequence_length', type=int, default=10,
                        help='Input sequence length')
    parser.add_argument('--out_steps', type=int, default=5,
                        help='Number of future steps to predict')
    parser.add_argument('--num_samples', type=int, default=15000,
                        help='Number of samples to generate for training')
    parser.add_argument('--epochs', type=int, default=50,
                        help='Number of training epochs')
    parser.add_argument('--batch_size', type=int, default=64,
                        help='Batch size for training')
    parser.add_argument('--output_dir', type=str, default='models/enhanced_lstm',
                        help='Output directory for models and plots')
    parser.add_argument('--retrain', action='store_true',
                        help='Retrain the model even if a pre-trained model exists')
    parser.add_argument('--show_plots', action='store_true',
                        help='Show plots during training and evaluation')
    parser.add_argument('--demo_slice_manager', action='store_true',
                        help='Demo the enhanced slice manager')
    
    return parser.parse_args()

if __name__ == '__main__':
    # Parse arguments
    args = parse_args()
    
    # Create output directory if it doesn't exist
    os.makedirs(args.output_dir, exist_ok=True)
    
    # Run demo
    demo_autoregressive_lstm(args) 