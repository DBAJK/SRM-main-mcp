#!/usr/bin/env python3
"""
5G Network Slicing - ML-Based Orchestrator Demo

This script demonstrates the capabilities of the orchestrator
using a trained LSTM model for slice allocation predictions.
"""

import os
import numpy as np
import time
import matplotlib.pyplot as plt
from datetime import datetime
import logging
import tensorflow as tf
import sys
import importlib
import pandas as pd

# Add parent directory to path to import from 5G-Network-Slicing
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '5G-Network-Slicing')))

# Import LSTM predictor
SliceAllocationPredictor = None
try:
    # Try direct import
    from slicesim.ai.lstm_predictor import SliceAllocationPredictor
except ImportError:
    print("Could not import LSTM predictor directly. Trying alternative paths...")
    
    # Try different paths
    possible_paths = [
        'slicesim.ai.lstm_predictor',
        '5G-Network-Slicing.slicesim.ai.lstm_predictor',
    ]
    
    for module_path in possible_paths:
        try:
            module = importlib.import_module(module_path)
            SliceAllocationPredictor = getattr(module, 'SliceAllocationPredictor')
            print(f"Successfully imported SliceAllocationPredictor from {module_path}")
            break
        except (ImportError, AttributeError):
            continue
    
    if SliceAllocationPredictor is None:
        print("Error: Could not import SliceAllocationPredictor from any path.")
        # Create a simple fallback predictor that always returns the same allocation
        class FallbackPredictor:
            def __init__(self, **kwargs):
                print("Using fallback predictor")
            
            def predict(self, input_data):
                return np.array([[0.4, 0.4, 0.2]])
        
        SliceAllocationPredictor = FallbackPredictor

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def load_vendor_data(csv_path, sequence_length=10):
    """
    Load vendor data from CSV file and prepare it for LSTM model.
    
    Args:
        csv_path (str): Path to the CSV file with vendor data
        sequence_length (int): Length of sequence for LSTM input
        
    Returns:
        tuple: (X, y) where X is input sequences and y is target values
    """
    try:
        # Load data from CSV
        data = pd.read_csv(csv_path)
        logger.info(f"Loaded vendor data from {csv_path}, shape: {data.shape}")
        
        # Extract features and targets
        # Assuming the CSV has columns for traffic, time, allocation, and utilization
        # Adapt these column names based on your actual CSV structure
        feature_cols = [
            'traffic_load', 'time_of_day', 'day_of_week', 
            'embb_alloc', 'urllc_alloc', 'mmtc_alloc',
            'embb_util', 'urllc_util', 'mmtc_util',
            'client_count', 'bs_count'
        ]
        
        # If some columns don't exist, try to find alternatives or create synthetic ones
        available_cols = data.columns.tolist()
        
        # Create mapping from expected columns to available columns
        col_map = {}
        for col in feature_cols:
            if col in available_cols:
                col_map[col] = col
            elif col == 'traffic_load' and 'traffic' in available_cols:
                col_map[col] = 'traffic'
            elif col == 'time_of_day' and 'time' in available_cols:
                col_map[col] = 'time'
            elif col == 'embb_alloc' and 'embb' in available_cols:
                col_map[col] = 'embb'
            elif col == 'urllc_alloc' and 'urllc' in available_cols:
                col_map[col] = 'urllc'
            elif col == 'mmtc_alloc' and 'mmtc' in available_cols:
                col_map[col] = 'mmtc'
            # Add other mappings as needed
        
        # Log the column mapping
        logger.info(f"Column mapping: {col_map}")
        
        # Extract features using the mapping
        features = []
        for col in feature_cols:
            if col in col_map:
                features.append(data[col_map[col]].values)
            else:
                # Create synthetic data for missing columns
                logger.warning(f"Column {col} not found, using synthetic data")
                if 'util' in col:
                    # Create synthetic utilization based on allocation
                    alloc_col = col.replace('util', 'alloc')
                    if alloc_col in col_map:
                        synthetic = data[col_map[alloc_col]].values * (0.8 + 0.4 * np.random.random(data.shape[0]))
                        features.append(synthetic)
                    else:
                        features.append(0.5 + 0.2 * np.random.random(data.shape[0]))
                elif 'client_count' in col:
                    features.append(0.4 + 0.3 * np.random.random(data.shape[0]))
                elif 'bs_count' in col:
                    features.append(0.6 + 0.1 * np.random.random(data.shape[0]))
                else:
                    features.append(0.5 + 0.1 * np.random.random(data.shape[0]))
        
        # Combine features
        features = np.column_stack(features)
        
        # Create sequences for LSTM
        X = []
        y = []
        
        for i in range(len(features) - sequence_length):
            X.append(features[i:i+sequence_length])
            # Target is the next allocation after the sequence
            y.append(features[i+sequence_length, 3:6])  # Assuming 3,4,5 are allocation columns
        
        X = np.array(X)
        y = np.array(y)
        
        logger.info(f"Created {len(X)} sequences with shape {X.shape}")
        
        return X, y
    
    except Exception as e:
        logger.error(f"Error loading vendor data: {e}")
        return None, None

class MLOrchestrator:
    """ML-based orchestrator using LSTM for slice allocation predictions."""
    
    def __init__(self, model_path=None, vendor_data_path=None):
        """Initialize the ML orchestrator.
        
        Args:
            model_path (str): Path to the trained LSTM model
            vendor_data_path (str): Path to vendor data CSV
        """
        # Current allocation and utilization
        self.allocation = np.array([0.4, 0.4, 0.2])  # [eMBB, URLLC, mMTC]
        self.utilization = np.array([0.0, 0.0, 0.0])
        
        # Thresholds for QoS violations
        self.thresholds = np.array([0.9, 1.2, 0.8])
        
        # State
        self.is_emergency = False
        self.is_special_event = False
        self.is_iot_surge = False
        
        # Traffic history
        self.traffic_history = []
        self.utilization_history = []
        self.allocation_history = []
        self.feature_history = []
        
        # LSTM forecasting results
        self.forecasts = []
        
        # Sequence length for LSTM input
        self.sequence_length = 10
        
        # Forecast steps
        self.forecast_steps = 5
        
        # Create output directory
        self.output_dir = f"results/ml_orchestrator_demo_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Vendor data for step 5
        self.vendor_data = None
        self.vendor_data_index = 0
        
        # Load vendor data if provided
        if vendor_data_path and os.path.exists(vendor_data_path):
            logger.info(f"Loading vendor data from {vendor_data_path}")
            self.vendor_data = load_vendor_data(vendor_data_path, self.sequence_length)
        
        # Initialize LSTM predictor
        try:
            # Try to load a pre-trained model if available
            if model_path and os.path.exists(model_path):
                logger.info(f"Loading LSTM model from {model_path}")
                
                # Check if it's an autoregressive model
                if 'autoregressive' in model_path or 'enhanced_lstm' in model_path:
                    # Import the AutoregressiveLSTMPredictor
                    try:
                        from slicesim.ai.enhanced_lstm_predictor import AutoregressiveLSTMPredictor
                        self.predictor = AutoregressiveLSTMPredictor(model_path=model_path, skip_training=True)
                        logger.info("Using AutoregressiveLSTMPredictor for multi-step forecasting")
                    except ImportError:
                        # Try alternative paths
                        possible_paths = [
                            '5G-Network-Slicing.slicesim.ai.enhanced_lstm_predictor',
                        ]
                        
                        for module_path in possible_paths:
                            try:
                                module = importlib.import_module(module_path)
                                AutoregressiveLSTMPredictor = getattr(module, 'AutoregressiveLSTMPredictor')
                                self.predictor = AutoregressiveLSTMPredictor(model_path=model_path, skip_training=True)
                                logger.info(f"Using AutoregressiveLSTMPredictor from {module_path}")
                                break
                            except (ImportError, AttributeError):
                                continue
                        
                        if not hasattr(self, 'predictor'):
                            # Fall back to regular predictor
                            logger.warning("Could not import AutoregressiveLSTMPredictor, using regular predictor")
                            self.predictor = SliceAllocationPredictor(model_path=model_path, skip_training=True)
                else:
                    # Regular single-step model
                    self.predictor = SliceAllocationPredictor(model_path=model_path, skip_training=True)
            else:
                # If no model path provided, or model not found, create a new one
                logger.info("Initializing new LSTM predictor with synthetic training")
                self.predictor = SliceAllocationPredictor(skip_training=False)
        except Exception as e:
            logger.error(f"Error initializing LSTM predictor: {e}")
            logger.info("Falling back to rule-based allocation")
            self.predictor = None
        
        logger.info("ML orchestrator initialized")
    
    def set_emergency_mode(self, is_emergency):
        """
        Set emergency mode.
        
        Args:
            is_emergency (bool): Whether there's an emergency
        """
        self.is_emergency = is_emergency
        logger.info(f"Emergency mode set to {is_emergency}")
    
    def set_special_event_mode(self, is_special_event):
        """
        Set special event mode.
        
        Args:
            is_special_event (bool): Whether there's a special event
        """
        self.is_special_event = is_special_event
        logger.info(f"Special event mode set to {is_special_event}")
    
    def set_iot_surge_mode(self, is_iot_surge):
        """
        Set IoT surge mode.
        
        Args:
            is_iot_surge (bool): Whether there's an IoT surge
        """
        self.is_iot_surge = is_iot_surge
        logger.info(f"IoT surge mode set to {is_iot_surge}")
    
    def generate_traffic(self):
        """
        Generate traffic based on current state.
        
        Returns:
            numpy.ndarray: Traffic for each slice
        """
        # Base traffic
        base_traffic = np.array([0.4, 0.3, 0.2])
        
        # Add time-based variation
        hour_of_day = datetime.now().hour / 24.0
        day_of_week = datetime.now().weekday() / 6.0
        
        # Daily pattern (peak during day, low at night)
        daily_factor = 0.3 * np.sin(2 * np.pi * hour_of_day)
        
        # Weekly pattern (higher on weekdays)
        weekly_factor = 0.2 * (1 - day_of_week)
        
        # Apply patterns
        traffic = base_traffic * (1 + daily_factor + weekly_factor)
        
        # Add random variation
        traffic += np.random.normal(0, 0.1, 3)
        
        # Apply event effects
        if self.is_emergency:
            # During emergency, increase URLLC traffic
            traffic[0] *= 0.8  # eMBB reduced
            traffic[1] *= 2.0  # URLLC increased
            traffic[2] *= 0.9  # mMTC slightly reduced
        
        if self.is_special_event:
            # During special event, increase eMBB traffic
            traffic[0] *= 1.5  # eMBB increased
            traffic[1] *= 0.8  # URLLC reduced
            traffic[2] *= 1.0  # mMTC unchanged
        
        if self.is_iot_surge:
            # During IoT surge, increase mMTC traffic
            traffic[0] *= 0.9  # eMBB slightly reduced
            traffic[1] *= 0.9  # URLLC slightly reduced
            traffic[2] *= 1.8  # mMTC increased
        
        # Ensure traffic is positive
        traffic = np.clip(traffic, 0.1, 2.0)
        
        # Add to history
        self.traffic_history.append(traffic)
        if len(self.traffic_history) > 100:
            self.traffic_history = self.traffic_history[-100:]
        
        return traffic
    
    def update_allocation_ml(self, features):
        """
        Update resource allocation using ML model.
        
        Args:
            features (numpy.ndarray): Input features for the ML model
        
        Returns:
            numpy.ndarray: Updated allocation
        """
        try:
            # Check if we have enough history for a sequence
            if len(self.feature_history) >= self.sequence_length:
                # Create sequence from history
                sequence = np.array(self.feature_history[-self.sequence_length:])
                
                # Get prediction from LSTM model
                prediction = self.predictor.predict(sequence)
                
                # Generate forecasts if predictor supports multi-step prediction
                try:
                    # Try to get multi-step forecast - this will only work if your model supports it
                    if hasattr(self.predictor, 'predict') and callable(getattr(self.predictor, 'predict')):
                        # Check if the predict method accepts 'return_all_steps' parameter
                        import inspect
                        params = inspect.signature(self.predictor.predict).parameters
                        if 'return_all_steps' in params:
                            forecasts = self.predictor.predict(sequence, return_all_steps=True)
                            # Store forecasts for visualization
                            self.forecasts.append(forecasts)
                            if len(self.forecasts) > 100:
                                self.forecasts = self.forecasts[-100:]
                            logger.info(f"Generated {len(forecasts)} forecast steps")
                        else:
                            # Single step prediction - create a synthetic forecast by repeating the prediction
                            # This is just for visualization purposes when using a single-step model
                            single_step = prediction if prediction.ndim == 1 else prediction[0]
                            synthetic_forecast = np.array([single_step for _ in range(self.forecast_steps)])
                            self.forecasts.append(synthetic_forecast)
                            if len(self.forecasts) > 100:
                                self.forecasts = self.forecasts[-100:]
                except Exception as e:
                    logger.error(f"Error generating forecasts: {e}")
                    # Create a synthetic forecast as fallback
                    single_step = prediction if prediction.ndim == 1 else prediction[0]
                    synthetic_forecast = np.array([single_step for _ in range(self.forecast_steps)])
                    self.forecasts.append(synthetic_forecast)
                    if len(self.forecasts) > 100:
                        self.forecasts = self.forecasts[-100:]
                
                # Extract allocation from prediction
                # Handle both 1D and 2D predictions (from single-step and autoregressive models)
                if isinstance(prediction, np.ndarray) and prediction.ndim > 1:
                    # For autoregressive model, use first step prediction
                    new_allocation = prediction[0]
                    logger.info(f"ML model predicted allocation: {prediction}")
                else:
                    # For single-step model
                    new_allocation = prediction  # First (and only) prediction
                
                # Apply stability factor to avoid rapid changes
                stability_factor = 0.7
                new_allocation = stability_factor * self.allocation + (1 - stability_factor) * new_allocation
                
                # Ensure allocations are within valid range and sum to 1
                new_allocation = np.clip(new_allocation, 0.1, 0.8)
                new_allocation = new_allocation / np.sum(new_allocation)
                
                logger.info(f"ML model predicted allocation: {new_allocation}")
                
                self.allocation = new_allocation
                return new_allocation
            else:
                # Not enough history, use rule-based allocation
                logger.info("Not enough history for ML prediction, using rule-based allocation")
                return self.update_allocation_rule_based()
        except Exception as e:
            logger.error(f"Error in ML allocation: {e}")
            logger.info("Falling back to rule-based allocation")
            return self.update_allocation_rule_based()
    
    def update_allocation_rule_based(self):
        """
        Update resource allocation based on rules.
        
        Returns:
            numpy.ndarray: Updated allocation
        """
        if self.is_emergency:
            # During emergency, prioritize URLLC
            target_allocation = np.array([0.2, 0.7, 0.1])
        elif self.is_special_event:
            # During special event, prioritize eMBB
            target_allocation = np.array([0.6, 0.3, 0.1])
        elif self.is_iot_surge:
            # During IoT surge, increase mMTC allocation
            target_allocation = np.array([0.3, 0.3, 0.4])
        else:
            # Normal allocation
            target_allocation = np.array([0.4, 0.4, 0.2])
        
        # Apply stability factor to avoid rapid changes
        stability_factor = 0.7
        new_allocation = stability_factor * self.allocation + (1 - stability_factor) * target_allocation
        
        # Check for QoS violations and adjust
        for i in range(3):
            if self.utilization[i] > self.thresholds[i]:
                # Increase allocation for this slice
                increase = min(0.1, (self.utilization[i] - self.thresholds[i]) * 0.2)
                
                # Find least utilized slice
                other_indices = [j for j in range(3) if j != i]
                least_utilized_idx = other_indices[np.argmin(self.utilization[other_indices])]
                
                # Adjust allocations
                new_allocation[i] += increase
                new_allocation[least_utilized_idx] -= increase
        
        # Ensure allocations are within valid range and sum to 1
        new_allocation = np.clip(new_allocation, 0.1, 0.8)
        new_allocation = new_allocation / np.sum(new_allocation)
        
        self.allocation = new_allocation
        return new_allocation
    
    def update_utilization(self, traffic):
        """
        Update utilization based on traffic and allocation.
        
        Args:
            traffic (numpy.ndarray): Traffic for each slice
        
        Returns:
            numpy.ndarray: Updated utilization
        """
        # Calculate utilization (traffic / allocation)
        # Add small constant to avoid division by zero
        utilization = traffic / (self.allocation + 1e-6)
        
        self.utilization = utilization
        
        # Add to history
        self.utilization_history.append(utilization)
        if len(self.utilization_history) > 100:
            self.utilization_history = self.utilization_history[-100:]
        
        return utilization
    
    def create_feature_vector(self, traffic):
        """
        Create feature vector for ML model.
        
        Args:
            traffic (numpy.ndarray): Traffic for each slice
        
        Returns:
            numpy.ndarray: Feature vector
        """
        # Current time features
        hour_of_day = datetime.now().hour / 24.0
        day_of_week = datetime.now().weekday() / 6.0
        
        # Calculate traffic load
        traffic_load = np.sum(traffic) / 3.0
        
        # Client count and base station count (simulated)
        client_count = 0.4 + 0.3 * np.sin(hour_of_day * 2 * np.pi) + 0.05 * np.random.randn()
        bs_count = 0.5 + 0.1 * np.random.randn()
        
        # Create feature vector
        # [traffic_load, time_of_day, day_of_week, embb_alloc, urllc_alloc, mmtc_alloc, 
        #  embb_util, urllc_util, mmtc_util, client_count, bs_count]
        features = np.array([
            traffic_load,
            hour_of_day,
            day_of_week,
            self.allocation[0],  # eMBB allocation
            self.allocation[1],  # URLLC allocation
            self.allocation[2],  # mMTC allocation
            self.utilization[0],  # eMBB utilization
            self.utilization[1],  # URLLC utilization
            self.utilization[2],  # mMTC utilization
            client_count,
            bs_count
        ])
        
        # Add to history
        self.feature_history.append(features)
        if len(self.feature_history) > 100:
            self.feature_history = self.feature_history[-100:]
        
        return features
    
    def run_step(self):
        """
        Run a single step of the orchestration process.
        
        Returns:
            dict: Current state
        """
        # Generate traffic
        traffic = self.generate_traffic()
        
        # Update utilization
        utilization = self.update_utilization(traffic)
        
        # Create feature vector
        features = self.create_feature_vector(traffic)
        
        # Update allocation using ML or rule-based approach
        if self.predictor is not None:
            allocation = self.update_allocation_ml(features)
        else:
            allocation = self.update_allocation_rule_based()
        
        # Add to history
        self.allocation_history.append(allocation)
        if len(self.allocation_history) > 100:
            self.allocation_history = self.allocation_history[-100:]
        
        # Check for QoS violations
        violations = utilization > self.thresholds
        
        # Return current state
        state = {
            'timestamp': datetime.now().isoformat(),
            'traffic': traffic,
            'allocation': allocation,
            'utilization': utilization,
            'violations': violations,
            'is_emergency': self.is_emergency,
            'is_special_event': self.is_special_event,
            'is_iot_surge': self.is_iot_surge,
            'features': features,
            'ml_enabled': self.predictor is not None
        }
        
        # For step 5, use vendor data if available
        step = len(self.history) if hasattr(self, 'history') else 0
        if step == 4 and self.vendor_data is not None and self.vendor_data[0] is not None:
            # We're at step 5 (index 4) and have vendor data
            X_vendor, y_vendor = self.vendor_data
            
            # Use a random sequence from vendor data
            if len(X_vendor) > 0:
                idx = self.vendor_data_index % len(X_vendor)
                vendor_sequence = X_vendor[idx]
                
                # Use the model to predict on vendor data
                try:
                    logger.info(f"Step 5: Using vendor data for LSTM prediction (sequence {idx})")
                    
                    # Get prediction from LSTM model
                    vendor_prediction = self.predictor.predict(np.expand_dims(vendor_sequence, axis=0))
                    
                    # Try to get multi-step forecast
                    try:
                        if hasattr(self.predictor, 'predict') and callable(getattr(self.predictor, 'predict')):
                            import inspect
                            params = inspect.signature(self.predictor.predict).parameters
                            if 'return_all_steps' in params:
                                vendor_forecast = self.predictor.predict(np.expand_dims(vendor_sequence, axis=0), return_all_steps=True)
                                if isinstance(vendor_forecast, np.ndarray) and vendor_forecast.ndim > 1:
                                    vendor_forecast = vendor_forecast[0]  # Remove batch dimension
                                
                                # Store vendor forecast
                                self.forecasts.append(vendor_forecast)
                                logger.info(f"Generated {len(vendor_forecast)} forecast steps from vendor data")
                                
                                # Override current allocation with vendor prediction for step 5
                                if isinstance(vendor_prediction, np.ndarray):
                                    if vendor_prediction.ndim > 1:
                                        # For autoregressive model
                                        self.allocation = vendor_prediction[0]
                                    else:
                                        # For single-step model
                                        self.allocation = vendor_prediction
                                    state['allocation'] = self.allocation
                                    
                                    # Visualize vendor data and prediction
                                    self.visualize_vendor_prediction(vendor_sequence, vendor_forecast, y_vendor[idx] if idx < len(y_vendor) else None)
                            else:
                                # Single step prediction
                                logger.info("Model only supports single-step prediction")
                                if isinstance(vendor_prediction, np.ndarray) and vendor_prediction.ndim > 1:
                                    # For autoregressive model
                                    single_step = vendor_prediction[0]
                                else:
                                    # For single-step model
                                    single_step = vendor_prediction
                                self.allocation = single_step
                                state['allocation'] = self.allocation
                    except Exception as e:
                        logger.error(f"Error generating vendor forecasts: {e}")
                    
                    self.vendor_data_index += 1
                except Exception as e:
                    logger.error(f"Error using vendor data: {e}")
        
        return state
    
    def visualize_state(self, state, output_path=None):
        """
        Visualize current state.
        
        Args:
            state (dict): Current state
            output_path (str): Path to save visualization
        """
        # Create figure with increased size to accommodate LSTM forecasting
        fig = plt.figure(figsize=(18, 12))
        gs = plt.GridSpec(2, 3, figure=fig, height_ratios=[1, 1])
        
        ax1 = fig.add_subplot(gs[0, 0])
        ax2 = fig.add_subplot(gs[0, 1])
        ax3 = fig.add_subplot(gs[0, 2])
        ax4 = fig.add_subplot(gs[1, 0])
        ax5 = fig.add_subplot(gs[1, 1:])  # LSTM forecasting plot spans two columns
        
        # Slice names and colors
        slice_names = ['eMBB', 'URLLC', 'mMTC']
        colors = ['#FF6B6B', '#45B7D1', '#FFBE0B']
        
        # Ensure allocation is 1D for pie chart
        allocation = state['allocation']
        if isinstance(allocation, np.ndarray) and allocation.ndim > 1:
            # For autoregressive model, use first step prediction
            allocation = allocation[0]
        
        # Plot allocation pie chart
        ax1.pie(allocation, labels=slice_names, colors=colors, autopct='%1.1f%%',
               shadow=True, startangle=90)
        ax1.axis('equal')
        ax1.set_title('Current Slice Allocation')
        
        # Plot utilization bar chart
        ax2.bar(slice_names, state['utilization'], color=colors)
        
        # Add threshold lines
        for i, threshold in enumerate(self.thresholds):
            ax2.axhline(y=threshold, xmin=i/3, xmax=(i+1)/3, 
                       color=colors[i], linestyle='--', alpha=0.7)
        
        ax2.set_title('Current Slice Utilization')
        ax2.set_ylabel('Utilization')
        ax2.grid(axis='y', linestyle='--', alpha=0.7)
        
        # Plot traffic history
        if len(self.traffic_history) > 1:
            traffic_history = np.array(self.traffic_history)
            for i, slice_name in enumerate(slice_names):
                ax3.plot(traffic_history[:, i], label=slice_name, color=colors[i])
            
            ax3.set_title('Traffic History')
            ax3.set_xlabel('Time Step')
            ax3.set_ylabel('Traffic')
            ax3.legend()
            ax3.grid(True, linestyle='--', alpha=0.7)
        
        # Plot QoS violations
        violation_counts = np.sum([v['violations'] for v in self.history[-20:]], axis=0)
        ax4.bar(slice_names, violation_counts, color=colors)
        ax4.set_title('QoS Violations (Last 20 Steps)')
        ax4.set_ylabel('Number of Violations')
        ax4.grid(axis='y', linestyle='--', alpha=0.7)
        
        # Plot LSTM forecasting
        if self.predictor is not None and len(self.forecasts) > 0:
            # Get the most recent forecast
            forecast = self.forecasts[-1]
            
            # Create time steps for x-axis
            history_length = min(20, len(self.allocation_history))
            forecast_steps = len(forecast)
            
            # Plot historical allocations
            if history_length > 0:
                # Ensure all elements in allocation_history are 1D arrays
                normalized_history = []
                for alloc in self.allocation_history[-history_length:]:
                    if isinstance(alloc, np.ndarray) and alloc.ndim > 1:
                        # For autoregressive model outputs, use first step
                        normalized_history.append(alloc[0])
                    else:
                        normalized_history.append(alloc)
                
                historical_data = np.array(normalized_history)
                time_history = np.arange(-history_length, 0)
                
                for i, slice_name in enumerate(slice_names):
                    ax5.plot(time_history, historical_data[:, i], 
                            color=colors[i], label=f'{slice_name} (Historical)')
            
            # Plot forecast
            time_forecast = np.arange(0, forecast_steps)
            for i, slice_name in enumerate(slice_names):
                ax5.plot(time_forecast, forecast[:, i], 
                        color=colors[i], linestyle='--', marker='o',
                        label=f'{slice_name} (Forecast)')
            
            # Add vertical line at current time
            ax5.axvline(x=0, color='k', linestyle='-', alpha=0.7)
            ax5.text(0.1, 0.95, 'Now', transform=ax5.transAxes)
            
            ax5.set_title('LSTM Slice Allocation Forecasting')
            ax5.set_xlabel('Time Steps (Relative to Current)')
            ax5.set_ylabel('Allocation Ratio')
            ax5.legend()
            ax5.grid(True, linestyle='--', alpha=0.7)
            
            # Set y-axis limits
            ax5.set_ylim(0, 1)
        else:
            # No forecasting available
            ax5.text(0.5, 0.5, 'LSTM Forecasting Not Available', 
                    horizontalalignment='center', verticalalignment='center',
                    transform=ax5.transAxes)
            ax5.set_title('LSTM Slice Allocation Forecasting')
        
        # Add event indicators and ML status
        events = []
        if state['is_emergency']:
            events.append('Emergency')
        if state['is_special_event']:
            events.append('Special Event')
        if state['is_iot_surge']:
            events.append('IoT Surge')
        
        ml_status = "ML Enabled" if state['ml_enabled'] else "Rule-Based"
        
        if events:
            fig.suptitle(f"Network Status: {', '.join(events)} ({ml_status})", fontsize=16)
        else:
            fig.suptitle(f"Network Status: Normal ({ml_status})", fontsize=16)
        
        plt.tight_layout()
        
        # Save or show
        if output_path:
            plt.savefig(output_path)
            plt.close()
        else:
            plt.show()
    
    def visualize_vendor_prediction(self, input_sequence, forecast, actual=None):
        """
        Visualize vendor data prediction.
        
        Args:
            input_sequence (numpy.ndarray): Input sequence
            forecast (numpy.ndarray): Forecast
            actual (numpy.ndarray): Actual values if available
        """
        try:
            # Create figure
            plt.figure(figsize=(15, 10))
            
            # Slice names and colors
            slice_names = ['eMBB', 'URLLC', 'mMTC']
            colors = ['#FF6B6B', '#45B7D1', '#FFBE0B']
            
            # Plot input sequence - allocation values at indices 3, 4, 5
            input_steps = np.arange(self.sequence_length)
            for i, slice_name in enumerate(slice_names):
                plt.plot(input_steps, input_sequence[:, i+3], color=colors[i], label=f'Input {slice_name}')
            
            # Plot forecast
            forecast_steps = np.arange(self.sequence_length, self.sequence_length + len(forecast))
            for i, slice_name in enumerate(slice_names):
                plt.plot(forecast_steps, forecast[:, i], color=colors[i], linestyle='--', marker='o', 
                        label=f'Forecast {slice_name}')
            
            # Plot actual if available
            if actual is not None:
                actual_step = self.sequence_length
                plt.scatter([actual_step], [actual[0]], color=colors[0], marker='*', s=200, label=f'Actual {slice_names[0]}')
                plt.scatter([actual_step], [actual[1]], color=colors[1], marker='*', s=200, label=f'Actual {slice_names[1]}')
                plt.scatter([actual_step], [actual[2]], color=colors[2], marker='*', s=200, label=f'Actual {slice_names[2]}')
            
            # Add vertical line at the end of input sequence
            plt.axvline(x=self.sequence_length-0.5, color='k', linestyle='-')
            plt.text(self.sequence_length-0.5, 0.5, 'Prediction', rotation=90)
            
            plt.title('LSTM Slice Allocation Prediction using Vendor Data (Step 5)')
            plt.xlabel('Time Step')
            plt.ylabel('Allocation Ratio')
            plt.legend()
            plt.grid(True)
            
            # Save figure
            plt.tight_layout()
            plt.savefig(os.path.join(self.output_dir, 'vendor_prediction_step5.png'))
            plt.close()
            
            logger.info(f"Saved vendor prediction visualization to {os.path.join(self.output_dir, 'vendor_prediction_step5.png')}")
        except Exception as e:
            logger.error(f"Error visualizing vendor prediction: {e}")
    
    def run(self, duration=60, interval=1.0):
        """
        Run the orchestrator for a specified duration.
        
        Args:
            duration (int): Duration in seconds
            interval (float): Update interval in seconds
        """
        logger.info(f"Running ML orchestrator for {duration} seconds")
        
        # Initialize history
        self.history = []
        
        # Run for specified duration
        start_time = time.time()
        step = 0
        
        try:
            while time.time() - start_time < duration:
                # Run step
                state = self.run_step()
                
                # Add to history
                self.history.append(state)
                
                # Log state
                logger.info(f"Step {step}:")
                # Check if allocation is 2D (from autoregressive model) or 1D
                if isinstance(state['allocation'], np.ndarray) and state['allocation'].ndim > 1:
                    # For autoregressive model, use first step prediction
                    logger.info(f"  Allocation: eMBB={state['allocation'][0][0]:.2f}, "
                               f"URLLC={state['allocation'][0][1]:.2f}, "
                               f"mMTC={state['allocation'][0][2]:.2f}")
                else:
                    # For single-step model
                    logger.info(f"  Allocation: eMBB={state['allocation'][0]:.2f}, "
                               f"URLLC={state['allocation'][1]:.2f}, "
                               f"mMTC={state['allocation'][2]:.2f}")
                
                logger.info(f"  Utilization: eMBB={state['utilization'][0]:.2f}, "
                           f"URLLC={state['utilization'][1]:.2f}, "
                           f"mMTC={state['utilization'][2]:.2f}")
                
                # Check for violations
                if np.any(state['violations']):
                    logger.warning(f"  QoS violations: {state['violations']}")
                
                # Visualize state
                viz_path = os.path.join(self.output_dir, f"state_{step:03d}.png")
                self.visualize_state(state, viz_path)
                
                # Increment step
                step += 1
                
                # Sleep
                time.sleep(interval)
        
        except KeyboardInterrupt:
            logger.info("Orchestrator stopped by user")
        
        # Save history
        self.save_history()
        
        logger.info(f"Orchestrator run completed with {step} steps")
    
    def save_history(self):
        """Save history to file."""
        import json
        
        # Convert history to serializable format
        serializable_history = []
        for state in self.history:
            # Handle allocation properly - ensure it's converted to a list correctly
            allocation = state['allocation']
            if isinstance(allocation, np.ndarray):
                if allocation.ndim > 1:
                    # For autoregressive model outputs (2D arrays)
                    allocation_list = allocation.tolist()
                else:
                    # For single-step model outputs (1D arrays)
                    allocation_list = allocation.tolist()
            else:
                allocation_list = allocation
            
            serializable_state = {
                'timestamp': state['timestamp'],
                'traffic': state['traffic'].tolist(),
                'allocation': allocation_list,
                'utilization': state['utilization'].tolist(),
                'violations': state['violations'].tolist(),
                'is_emergency': state['is_emergency'],
                'is_special_event': state['is_special_event'],
                'is_iot_surge': state['is_iot_surge'],
                'features': state['features'].tolist(),
                'ml_enabled': state['ml_enabled']
            }
            serializable_history.append(serializable_state)
        
        # Save to file
        history_path = os.path.join(self.output_dir, 'history.json')
        with open(history_path, 'w') as f:
            json.dump(serializable_history, f, indent=2)
        
        logger.info(f"History saved to {history_path}")
        
        # Save forecasts if available
        if self.predictor is not None and len(self.forecasts) > 0:
            # Convert forecasts to serializable format
            serializable_forecasts = [forecast.tolist() for forecast in self.forecasts]
            
            # Save to file
            forecasts_path = os.path.join(self.output_dir, 'forecasts.json')
            with open(forecasts_path, 'w') as f:
                json.dump(serializable_forecasts, f, indent=2)
            
            logger.info(f"Forecasts saved to {forecasts_path}")


def run_demo():
    """Run the ML orchestrator demo."""
    import argparse
    
    # Parse arguments
    parser = argparse.ArgumentParser(description='5G Network Slicing ML Orchestrator Demo')
    parser.add_argument('--duration', type=int, default=60, help='Duration in seconds')
    parser.add_argument('--interval', type=float, default=1.0, help='Update interval in seconds')
    parser.add_argument('--model-path', type=str, help='Path to trained LSTM model')
    parser.add_argument('--vendor-data', type=str, help='Path to vendor data CSV')
    parser.add_argument('--emergency', action='store_true', help='Simulate emergency')
    parser.add_argument('--special-event', action='store_true', help='Simulate special event')
    parser.add_argument('--iot-surge', action='store_true', help='Simulate IoT surge')
    
    args = parser.parse_args()
    
    # Create orchestrator
    orchestrator = MLOrchestrator(
        model_path=args.model_path,
        vendor_data_path=args.vendor_data
    )
    
    # Set event modes
    if args.emergency:
        orchestrator.set_emergency_mode(True)
    
    if args.special_event:
        orchestrator.set_special_event_mode(True)
    
    if args.iot_surge:
        orchestrator.set_iot_surge_mode(True)
    
    # Run orchestrator
    orchestrator.run(args.duration, args.interval)


if __name__ == "__main__":
    run_demo() 