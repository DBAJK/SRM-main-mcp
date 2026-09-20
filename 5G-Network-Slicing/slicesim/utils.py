#!/usr/bin/env python3
"""
5G Network Slicing - Utilities Module

This module provides common utility functions for the 5G network slicing system,
including data processing, visualization, and evaluation metrics.
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import json
import logging
from datetime import datetime
from sklearn.preprocessing import MinMaxScaler
from scipy.spatial.distance import euclidean as distance
from scipy.spatial import cKDTree as KDTree
# import tensorflow as tf  # TensorFlow not compatible with Python 3.14

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def format_bps(bits_per_second):
    """
    Format bits per second into a human-readable string.
    
    Args:
        bits_per_second (float): Value in bits per second
    
    Returns:
        str: Formatted string with appropriate unit (bps, Kbps, Mbps, Gbps, Tbps)
    """
    if bits_per_second == 0:
        return "0 bps"
    
    units = ["bps", "Kbps", "Mbps", "Gbps", "Tbps"]
    unit_index = 0
    value = float(bits_per_second)
    
    while value >= 1000 and unit_index < len(units) - 1:
        value /= 1000
        unit_index += 1
    
    return f"{value:.2f} {units[unit_index]}"


def setup_directories(dirs):
    """
    Create directories if they don't exist.
    
    Args:
        dirs (list): List of directory paths to create
    
    Returns:
        bool: Whether all directories were created successfully
    """
    try:
        for directory in dirs:
            os.makedirs(directory, exist_ok=True)
            logger.info(f"Directory created: {directory}")
        return True
    except Exception as e:
        logger.error(f"Error creating directories: {e}")
        return False


def save_json(data, filepath):
    """
    Save data to JSON file.
    
    Args:
        data (dict): Data to save
        filepath (str): Path to save the file
    
    Returns:
        bool: Whether the data was saved successfully
    """
    try:
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=4)
        
        logger.info(f"Data saved to {filepath}")
        return True
    except Exception as e:
        logger.error(f"Error saving data to {filepath}: {e}")
        return False


def load_json(filepath):
    """
    Load data from JSON file.
        
        Args:
        filepath (str): Path to the JSON file
    
    Returns:
        dict: Loaded data or None if error
    """
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        logger.info(f"Data loaded from {filepath}")
        return data
    except Exception as e:
        logger.error(f"Error loading data from {filepath}: {e}")
        return None


def generate_traffic_pattern(steps, slice_types=None, base_levels=None, variances=None, 
                           emergency_factors=None, emergency_steps=None):
    """
    Generate synthetic traffic pattern for network slices.
    
    Args:
        steps (int): Number of time steps
        slice_types (list): List of slice types
        base_levels (dict): Base traffic level for each slice
        variances (dict): Variance of traffic for each slice
        emergency_factors (dict): Traffic multiplier during emergency for each slice
        emergency_steps (list): List of steps with emergency events
    
    Returns:
        dict: Generated traffic pattern
    """
    if slice_types is None:
        slice_types = ['eMBB', 'URLLC', 'mMTC']
    
    if base_levels is None:
        base_levels = {
            'eMBB': 0.4,
            'URLLC': 0.3,
            'mMTC': 0.2
        }
    
    if variances is None:
        variances = {
            'eMBB': 0.2,
            'URLLC': 0.1,
            'mMTC': 0.15
        }
    
    if emergency_factors is None:
        emergency_factors = {
            'eMBB': 0.8,  # Reduced during emergency
            'URLLC': 2.0,  # Increased during emergency
            'mMTC': 0.9   # Slightly reduced during emergency
        }
    
    if emergency_steps is None:
        # Generate random emergency events
        emergency_prob = 0.1
        emergency_steps = [i for i in range(steps) if np.random.random() < emergency_prob]
    
    # Generate traffic pattern
    traffic = {slice_type: np.zeros(steps) for slice_type in slice_types}
    is_emergency = np.zeros(steps, dtype=bool)
    
    # Set emergency steps
    for step in emergency_steps:
        if step < steps:
            is_emergency[step] = True
    
    # Generate base pattern with daily and weekly patterns
    time = np.arange(steps)
    daily_pattern = 0.2 * np.sin(2 * np.pi * time / 24)  # 24-hour cycle
    weekly_pattern = 0.1 * np.sin(2 * np.pi * time / (24 * 7))  # Weekly cycle
    
    for slice_type in slice_types:
        # Base level
        base = base_levels[slice_type]
        variance = variances[slice_type]
        
        # Generate pattern
        pattern = base + daily_pattern + weekly_pattern
        
        # Add random noise
        noise = np.random.normal(0, variance, steps)
        pattern += noise
        
        # Apply emergency factors
        for step in range(steps):
            if is_emergency[step]:
                pattern[step] *= emergency_factors[slice_type]
        
        # Ensure positive values and clip to reasonable range
        pattern = np.clip(pattern, 0.1, 2.0)
        
        # Store in traffic dict
        traffic[slice_type] = pattern
    
    # Create result dictionary
    result = {
        'steps': steps,
        'traffic': traffic,
        'is_emergency': is_emergency.tolist(),
        'emergency_steps': emergency_steps
    }
    
    return result


def calculate_utilization(traffic, allocation):
    """
    Calculate utilization based on traffic and allocation.
    
    Args:
        traffic (numpy.ndarray): Traffic load for each slice
        allocation (numpy.ndarray): Resource allocation for each slice
    
    Returns:
        numpy.ndarray: Utilization for each slice
    """
    # Add small constant to avoid division by zero
    return traffic / (allocation + 1e-6)


def check_qos_violations(utilization, thresholds):
    """
    Check for QoS violations based on utilization and thresholds.
        
        Args:
        utilization (numpy.ndarray): Utilization for each slice
        thresholds (numpy.ndarray): QoS thresholds for each slice
            
        Returns:
        numpy.ndarray: Boolean array indicating violations
    """
    return utilization > thresholds


def prepare_sequence_data(data, sequence_length, features, target_cols=None):
    """
    Prepare sequence data for LSTM model.
    
    Args:
        data (pandas.DataFrame): Input data
        sequence_length (int): Length of input sequence
        features (list): List of feature column names
        target_cols (list): List of target column names
    
    Returns:
        tuple: (X, y) where X is input sequences and y is target values
    """
    X_sequences = []
    y_values = []
    
    # For each possible sequence
    for i in range(len(data) - sequence_length):
        # Extract sequence
        X_sequence = data[features].iloc[i:i+sequence_length].values
        X_sequences.append(X_sequence)
        
        # Extract target (next step after sequence)
        if target_cols:
            y_value = data[target_cols].iloc[i+sequence_length].values
            y_values.append(y_value)
    
    X = np.array(X_sequences)
    
    if target_cols:
        y = np.array(y_values)
        return X, y
    else:
        return X


def prepare_multi_step_data(data, sequence_length, out_steps, features, target_cols):
    """
    Prepare multi-step sequence data for autoregressive LSTM model.
        
        Args:
        data (pandas.DataFrame): Input data
        sequence_length (int): Length of input sequence
        out_steps (int): Number of output steps
        features (list): List of feature column names
        target_cols (list): List of target column names
            
        Returns:
        tuple: (X, y) where X is input sequences and y is target sequences
    """
    X_sequences = []
    y_sequences = []
    
    # For each possible sequence
    for i in range(len(data) - sequence_length - out_steps + 1):
        # Extract input sequence
        X_sequence = data[features].iloc[i:i+sequence_length].values
        X_sequences.append(X_sequence)
        
        # Extract target sequence
        y_sequence = data[target_cols].iloc[i+sequence_length:i+sequence_length+out_steps].values
        y_sequences.append(y_sequence)
    
    X = np.array(X_sequences)
    y = np.array(y_sequences)
    
    return X, y


def visualize_traffic(traffic_data, output_path=None):
    """
    Visualize traffic pattern.
    
    Args:
        traffic_data (dict): Traffic data
        output_path (str): Path to save the visualization
    """
    steps = traffic_data['steps']
    traffic = traffic_data['traffic']
    is_emergency = traffic_data['is_emergency']
    
    # Create figure
    plt.figure(figsize=(12, 6))
    
    # Plot traffic for each slice
    for slice_type, values in traffic.items():
        plt.plot(values, label=slice_type)
    
    # Highlight emergency periods
    emergency_ranges = []
    start = None
    for i, emergency in enumerate(is_emergency):
        if emergency and start is None:
            start = i
        elif not emergency and start is not None:
            emergency_ranges.append((start, i))
            start = None
    
    if start is not None:
        emergency_ranges.append((start, steps))
    
    for start, end in emergency_ranges:
        plt.axvspan(start, end, alpha=0.2, color='red')
    
    plt.xlabel('Time Step')
    plt.ylabel('Traffic Load')
    plt.title('Network Traffic Pattern')
    plt.legend()
    plt.grid(True, linestyle='--', alpha=0.7)
    
    # Save or show
    if output_path:
        plt.savefig(output_path)
        plt.close()
    else:
        plt.show()


def visualize_allocation_comparison(steps, static_allocation, model_allocation, 
                                  static_utilization, model_utilization,
                                  is_emergency=None, output_path=None):
    """
    Visualize comparison between static and model-based allocation.
    
    Args:
        steps (int): Number of time steps
        static_allocation (numpy.ndarray): Static allocation over time
        model_allocation (numpy.ndarray): Model-based allocation over time
        static_utilization (numpy.ndarray): Static utilization over time
        model_utilization (numpy.ndarray): Model-based utilization over time
        is_emergency (list): Boolean list indicating emergency steps
        output_path (str): Path to save the visualization
    """
    slice_types = ['eMBB', 'URLLC', 'mMTC']
    colors = ['#FF6B6B', '#45B7D1', '#FFBE0B']
    
    # Create figure
    fig, axes = plt.subplots(3, 2, figsize=(15, 12))
    
    # Time steps
    x = np.arange(steps)
    
    # Plot allocations
    for i, slice_type in enumerate(slice_types):
        axes[i, 0].plot(x, static_allocation[:, i], label='Static', color='#888888', linestyle='-')
        axes[i, 0].plot(x, model_allocation[:, i], label='Model', color=colors[i], linestyle='-')
        axes[i, 0].set_title(f'{slice_type} Allocation')
        axes[i, 0].set_ylabel('Allocation')
        axes[i, 0].set_xlabel('Time Step')
        axes[i, 0].legend()
        axes[i, 0].grid(True, linestyle='--', alpha=0.7)
    
    # Plot utilizations
    for i, slice_type in enumerate(slice_types):
        axes[i, 1].plot(x, static_utilization[:, i], label='Static', color='#888888', linestyle='-')
        axes[i, 1].plot(x, model_utilization[:, i], label='Model', color=colors[i], linestyle='-')
        axes[i, 1].set_title(f'{slice_type} Utilization')
        axes[i, 1].set_ylabel('Utilization')
        axes[i, 1].set_xlabel('Time Step')
        axes[i, 1].legend()
        axes[i, 1].grid(True, linestyle='--', alpha=0.7)
    
    # Highlight emergency periods if provided
    if is_emergency:
        emergency_ranges = []
        start = None
        for i, emergency in enumerate(is_emergency):
            if emergency and start is None:
                start = i
            elif not emergency and start is not None:
                emergency_ranges.append((start, i))
                start = None
        
        if start is not None:
            emergency_ranges.append((start, steps))
        
        for ax_row in axes:
            for ax in ax_row:
                for start, end in emergency_ranges:
                    ax.axvspan(start, end, alpha=0.2, color='red')
    
    plt.tight_layout()
    
    # Save or show
    if output_path:
        plt.savefig(output_path)
        plt.close()
    else:
        plt.show()


def visualize_qos_violations(steps, static_violations, model_violations, 
                           is_emergency=None, output_path=None):
    """
    Visualize QoS violations comparison.
    
    Args:
        steps (int): Number of time steps
        static_violations (numpy.ndarray): Static violations over time
        model_violations (numpy.ndarray): Model-based violations over time
        is_emergency (list): Boolean list indicating emergency steps
        output_path (str): Path to save the visualization
    """
    slice_types = ['eMBB', 'URLLC', 'mMTC']
    colors = ['#FF6B6B', '#45B7D1', '#FFBE0B']
    
    # Create figure
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
    
    # Time steps
    x = np.arange(steps)
    
    # Calculate cumulative violations
    static_cum_violations = np.cumsum(static_violations, axis=0)
    model_cum_violations = np.cumsum(model_violations, axis=0)
    
    # Plot violations per slice
    for i, slice_type in enumerate(slice_types):
        ax1.plot(x, static_cum_violations[:, i], label=f'Static {slice_type}', 
                color=colors[i], linestyle='--')
        ax1.plot(x, model_cum_violations[:, i], label=f'Model {slice_type}', 
                color=colors[i], linestyle='-')
    
    ax1.set_title('Cumulative QoS Violations by Slice')
    ax1.set_ylabel('Number of Violations')
    ax1.set_xlabel('Time Step')
    ax1.legend()
    ax1.grid(True, linestyle='--', alpha=0.7)
    
    # Plot total violations
    static_total = np.sum(static_violations, axis=1)
    model_total = np.sum(model_violations, axis=1)
    static_cum_total = np.cumsum(static_total)
    model_cum_total = np.cumsum(model_total)
    
    ax2.plot(x, static_cum_total, label='Static Total', color='#888888', linewidth=2)
    ax2.plot(x, model_cum_total, label='Model Total', color='#2ECC71', linewidth=2)
    
    ax2.set_title('Total Cumulative QoS Violations')
    ax2.set_ylabel('Number of Violations')
    ax2.set_xlabel('Time Step')
    ax2.legend()
    ax2.grid(True, linestyle='--', alpha=0.7)
    
    # Highlight emergency periods if provided
    if is_emergency:
        emergency_ranges = []
        start = None
        for i, emergency in enumerate(is_emergency):
            if emergency and start is None:
                start = i
            elif not emergency and start is not None:
                emergency_ranges.append((start, i))
                start = None
        
        if start is not None:
            emergency_ranges.append((start, steps))
        
        for ax in [ax1, ax2]:
            for start, end in emergency_ranges:
                ax.axvspan(start, end, alpha=0.2, color='red')
    
    plt.tight_layout()
    
    # Save or show
    if output_path:
        plt.savefig(output_path)
        plt.close()
    else:
        plt.show()


def evaluate_model(y_true, y_pred):
    """
    Evaluate model performance.
    
    Args:
        y_true (numpy.ndarray): True values
        y_pred (numpy.ndarray): Predicted values
    
    Returns:
        dict: Evaluation metrics
    """
    # Mean Absolute Error
    mae = np.mean(np.abs(y_true - y_pred))
    
    # Mean Squared Error
    mse = np.mean(np.square(y_true - y_pred))
    
    # Root Mean Squared Error
    rmse = np.sqrt(mse)
    
    # Mean Absolute Percentage Error
    # Add small constant to avoid division by zero
    mape = np.mean(np.abs((y_true - y_pred) / (y_true + 1e-6))) * 100
    
    # R-squared
    ss_total = np.sum(np.square(y_true - np.mean(y_true)))
    ss_residual = np.sum(np.square(y_true - y_pred))
    r2 = 1 - (ss_residual / ss_total)
    
    return {
        'mae': float(mae),
        'mse': float(mse),
        'rmse': float(rmse),
        'mape': float(mape),
        'r2': float(r2)
    }


# Example usage
if __name__ == "__main__":
    # Generate traffic pattern
    traffic_data = generate_traffic_pattern(
        steps=100,
        emergency_steps=[20, 21, 22, 23, 24, 60, 61, 62]
    )
    
    # Visualize traffic
    visualize_traffic(traffic_data, "traffic_example.png")
    
    # Create dummy allocation and utilization data
    steps = traffic_data['steps']
    static_allocation = np.tile([0.4, 0.3, 0.3], (steps, 1))
    model_allocation = np.zeros((steps, 3))
    static_utilization = np.zeros((steps, 3))
    model_utilization = np.zeros((steps, 3))
    
    # Calculate utilization
    for i in range(steps):
        traffic_values = np.array([
            traffic_data['traffic']['eMBB'][i],
            traffic_data['traffic']['URLLC'][i],
            traffic_data['traffic']['mMTC'][i]
        ])
        
        # Model allocation changes based on traffic
        if traffic_data['is_emergency'][i]:
            model_allocation[i] = [0.2, 0.7, 0.1]  # Emergency allocation
        else:
            # Simple adaptive allocation
            total = np.sum(traffic_values)
            if total > 0:
                model_allocation[i] = traffic_values / total
            else:
                model_allocation[i] = [0.33, 0.33, 0.34]
        
        # Calculate utilization
        static_utilization[i] = calculate_utilization(traffic_values, static_allocation[i])
        model_utilization[i] = calculate_utilization(traffic_values, model_allocation[i])
    
    # Visualize allocation comparison
    visualize_allocation_comparison(
        steps,
        static_allocation,
        model_allocation,
        static_utilization,
        model_utilization,
        traffic_data['is_emergency'],
        "allocation_comparison_example.png"
    )
    
    # Check QoS violations
    thresholds = np.array([1.5, 1.2, 1.8])
    static_violations = check_qos_violations(static_utilization, thresholds)
    model_violations = check_qos_violations(model_utilization, thresholds)
    
    # Visualize QoS violations
    visualize_qos_violations(
        steps,
        static_violations,
        model_violations,
        traffic_data['is_emergency'],
        "qos_violations_example.png"
    )
    
    print("Example visualizations created!")
