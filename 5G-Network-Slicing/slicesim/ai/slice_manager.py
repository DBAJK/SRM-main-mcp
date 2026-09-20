#!/usr/bin/env python3
"""
5G Network Slicing - Slice Manager Module

This module implements base and enhanced slice managers for the 5G network slicing system.
The slice managers are responsible for allocating resources to different network slices
based on various strategies, from static allocation to ML-based dynamic allocation.
"""

import os
import numpy as np
import logging
import time
from datetime import datetime
import json
import matplotlib.pyplot as plt
from threading import Lock
import tensorflow as tf
from sklearn.preprocessing import MinMaxScaler

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class BaseSliceManager:
    """
    Base class for slice managers.
    
    This class implements basic slice management functionality and static allocation.
    """
    
    def __init__(self, config_path=None):
        """
        Initialize the slice manager.
        
        Args:
            config_path (str): Path to the configuration file
        """
        # Default configuration
        self.config = {
            'slice_types': ['embb', 'urllc', 'mmtc'],
            'static_allocation': {
                'embb': 0.4,
                'urllc': 0.3,
                'mmtc': 0.3
            },
            'qos_thresholds': {
                'embb': 1.5,
                'urllc': 1.2,
                'mmtc': 1.8
            },
            'emergency_allocation': {
                'embb': 0.3,
                'urllc': 0.6,
                'mmtc': 0.1
            }
        }
        
        # Load configuration if provided
        if config_path and os.path.exists(config_path):
            self._load_config(config_path)
        
        # Initialize state
        self.current_allocation = np.array([
            self.config['static_allocation']['embb'],
            self.config['static_allocation']['urllc'],
            self.config['static_allocation']['mmtc']
        ])
        
        self.current_utilization = np.zeros(3)
        self.is_emergency = False
        self.lock = Lock()
        
        logger.info("Base slice manager initialized")
    
    def _load_config(self, config_path):
        """
        Load configuration from file.
        
        Args:
            config_path (str): Path to the configuration file
        """
        try:
            with open(config_path, 'r') as f:
                loaded_config = json.load(f)
                # Update config with loaded values
                for key, value in loaded_config.items():
                    self.config[key] = value
            logger.info(f"Configuration loaded from {config_path}")
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
    
    def allocate_resources(self, traffic_load, utilization=None):
        """
        Allocate resources based on the current strategy.
        
        Args:
            traffic_load (float): Current traffic load
            utilization (numpy.ndarray): Current utilization of slices
        
        Returns:
            numpy.ndarray: Resource allocation for each slice
        """
        with self.lock:
            # Base implementation uses static allocation
            if self.is_emergency:
                # Use emergency allocation during emergencies
                allocation = np.array([
                    self.config['emergency_allocation']['embb'],
                    self.config['emergency_allocation']['urllc'],
                    self.config['emergency_allocation']['mmtc']
                ])
            else:
                # Use static allocation normally
                allocation = np.array([
                    self.config['static_allocation']['embb'],
                    self.config['static_allocation']['urllc'],
                    self.config['static_allocation']['mmtc']
                ])
            
            # Update current allocation
            self.current_allocation = allocation
            
            # Update utilization if provided
            if utilization is not None:
                self.current_utilization = utilization
            
            return allocation
    
    def set_emergency_mode(self, is_emergency):
        """
        Set emergency mode.
        
        Args:
            is_emergency (bool): Whether there's an emergency
        """
        with self.lock:
            self.is_emergency = is_emergency
        logger.info(f"Emergency mode set to {is_emergency}")
    
    def get_current_allocation(self):
        """
        Get current slice allocation.
        
        Returns:
            numpy.ndarray: Current allocation
        """
        with self.lock:
            return self.current_allocation.copy()
    
    def get_current_utilization(self):
        """
        Get current slice utilization.
        
        Returns:
            numpy.ndarray: Current utilization
        """
        with self.lock:
            return self.current_utilization.copy()
    
    def visualize_allocation(self, output_path=None):
        """
        Visualize current allocation.
        
        Args:
            output_path (str): Path to save visualization
        """
        # Create figure
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
        
        # Plot allocation
        slice_types = ['eMBB', 'URLLC', 'mMTC']
        colors = ['#FF6B6B', '#45B7D1', '#FFBE0B']
        
        # Allocation pie chart
        ax1.pie(self.current_allocation, labels=slice_types, colors=colors, autopct='%1.1f%%',
               shadow=True, startangle=90)
        ax1.axis('equal')
        ax1.set_title('Current Slice Allocation')
        
        # Utilization bar chart
        ax2.bar(slice_types, self.current_utilization, color=colors)
        
        # Add threshold lines
        thresholds = [
            self.config['qos_thresholds']['embb'],
            self.config['qos_thresholds']['urllc'],
            self.config['qos_thresholds']['mmtc']
        ]
        
        for i, threshold in enumerate(thresholds):
            ax2.axhline(y=threshold, xmin=i/3, xmax=(i+1)/3, 
                       color=colors[i], linestyle='--', alpha=0.7)
        
        ax2.set_title('Current Slice Utilization')
        ax2.set_ylabel('Utilization')
        ax2.grid(axis='y', linestyle='--', alpha=0.7)
        
        # Add emergency indicator
        if self.is_emergency:
            fig.suptitle("Network Status: Emergency", fontsize=16)
        else:
            fig.suptitle("Network Status: Normal", fontsize=16)
        
        plt.tight_layout()
        
        # Save or show
        if output_path:
            plt.savefig(output_path)
            plt.close()
        else:
            plt.show()


class ProportionalSliceManager(BaseSliceManager):
    """
    Proportional slice manager that allocates resources based on utilization.
    """
    
    def allocate_resources(self, traffic_load, utilization):
        """
        Allocate resources proportionally to utilization.
        
        Args:
            traffic_load (float): Current traffic load
            utilization (numpy.ndarray): Current utilization of slices
        
        Returns:
            numpy.ndarray: Resource allocation for each slice
        """
        with self.lock:
            # Update utilization
            self.current_utilization = utilization.copy()
            
            if self.is_emergency:
                # Use emergency allocation during emergencies
                allocation = np.array([
                    self.config['emergency_allocation']['embb'],
                    self.config['emergency_allocation']['urllc'],
                    self.config['emergency_allocation']['mmtc']
                ])
            else:
                # Calculate allocation proportional to utilization
                total_util = np.sum(utilization)
                if total_util > 0:
                    # Normalize utilization
                    allocation = utilization / total_util
                else:
                    # If total utilization is 0, use static allocation
                    allocation = np.array([
                        self.config['static_allocation']['embb'],
                        self.config['static_allocation']['urllc'],
                        self.config['static_allocation']['mmtc']
                    ])
            
            # Ensure allocations are within valid range
            allocation = np.clip(allocation, 0.1, 0.8)
            
            # Normalize to sum to 1
            allocation = allocation / np.sum(allocation)
            
            # Update current allocation
            self.current_allocation = allocation
            
            return allocation


class EnhancedSliceManager(BaseSliceManager):
    """
    Enhanced slice manager that uses ML model for allocation decisions.
    """
    
    def __init__(self, model_path=None, config_path=None):
        """
        Initialize the enhanced slice manager.
        
        Args:
            model_path (str): Path to the trained model
            config_path (str): Path to the configuration file
        """
        super().__init__(config_path)
        
        # Additional configuration
        self.config.update({
            'sequence_length': 10,
            'stability_factor': 0.7,
            'feature_names': [
                'traffic_load', 'hour_of_day', 'day_of_week',
                'embb_allocation', 'urllc_allocation', 'mmtc_allocation',
                'embb_utilization', 'urllc_utilization', 'mmtc_utilization',
                'client_count', 'bs_count'
            ]
        })
        
        # Load configuration if provided
        if config_path and os.path.exists(config_path):
            self._load_config(config_path)
        
        # Initialize ML components
        self.model = None
        self.scaler = None
        self.history = []
        self.is_multi_step = False
        self.out_steps = 1
        
        # Load model if provided
        if model_path:
            self.load_model(model_path)
        
        logger.info("Enhanced slice manager initialized")
    
    def load_model(self, model_path):
        """
        Load the trained model and scaler.
        
        Args:
            model_path (str): Path to the model directory
        
        Returns:
            bool: Whether the model was loaded successfully
        """
        try:
            # Load model
            self.model = tf.keras.models.load_model(os.path.join(model_path, 'final_model.h5'))
            logger.info(f"Model loaded from {model_path}")
            
            # Load scaler parameters
            scaler_path = os.path.join(model_path, 'X_scaler.npy')
            if os.path.exists(scaler_path):
                scaler_params = np.load(scaler_path, allow_pickle=True)
                self.scaler = MinMaxScaler()
                self.scaler.data_min_ = scaler_params[0]
                self.scaler.data_max_ = scaler_params[1]
                logger.info(f"Scaler loaded from {scaler_path}")
            else:
                logger.warning(f"Scaler not found at {scaler_path}, using default scaling")
                self.scaler = MinMaxScaler()
            
            # Get model metadata
            self.is_multi_step = len(self.model.output_shape) > 2
            if self.is_multi_step:
                self.out_steps = self.model.output_shape[1]
                logger.info(f"Loaded multi-step model with {self.out_steps} output steps")
            else:
                self.out_steps = 1
                logger.info("Loaded single-step model")
            
            return True
        except Exception as e:
            logger.error(f"Error loading model: {e}")
            return False
    
    def allocate_resources(self, traffic_load, utilization, hour_of_day=None, day_of_week=None, client_count=0.5, bs_count=0.5):
        """
        Allocate resources based on ML model predictions.
        
        Args:
            traffic_load (float): Current traffic load
            utilization (numpy.ndarray): Current utilization of slices
            hour_of_day (float): Hour of day (0-1)
            day_of_week (float): Day of week (0-1)
            client_count (float): Normalized client count
            bs_count (float): Normalized base station count
        
        Returns:
            numpy.ndarray: Resource allocation for each slice
        """
        with self.lock:
            # Update utilization
            self.current_utilization = utilization.copy()
            
            # If model is not loaded or in emergency mode, use base behavior
            if self.model is None:
                logger.warning("Model not loaded, using base allocation strategy")
                return super().allocate_resources(traffic_load, utilization)
            
            # Get current time if not provided
            if hour_of_day is None or day_of_week is None:
                now = datetime.now()
                hour_of_day = now.hour / 24.0
                day_of_week = now.weekday() / 6.0
            
            # Create state dictionary
            state = {
                'timestamp': datetime.now(),
                'traffic_load': traffic_load,
                'hour_of_day': hour_of_day,
                'day_of_week': day_of_week,
                'allocations': self.current_allocation.copy(),
                'utilizations': utilization.copy(),
                'client_count': client_count,
                'bs_count': bs_count,
                'is_emergency': self.is_emergency
            }
            
            # Add to history
            self.history.append(state)
            
            # Keep only the most recent entries needed for the sequence
            if len(self.history) > self.config['sequence_length']:
                self.history = self.history[-self.config['sequence_length']:]
            
            # If we don't have enough history, use base behavior
            if len(self.history) < self.config['sequence_length']:
                logger.info("Not enough history, using base allocation strategy")
                return super().allocate_resources(traffic_load, utilization)
            
            # Prepare input for model
            X = self._prepare_model_input()
            
            # Get model prediction
            prediction = self.model.predict(X, verbose=0)
            
            # Extract the prediction(s)
            if self.is_multi_step:
                # For multi-step models, we have predictions for multiple future steps
                predictions = prediction[0]  # Shape: [out_steps, 3]
                
                # Use a weighted combination of predictions with more weight to near-term
                weights = np.exp(-0.5 * np.arange(self.out_steps))
                weights = weights / np.sum(weights)
                
                # Weighted average of predictions
                model_allocation = np.sum(predictions * weights[:, np.newaxis], axis=0)
            else:
                # For single-step models, we have one prediction
                model_allocation = prediction[0]  # Shape: [3]
            
            # Apply event-specific adjustments
            if self.is_emergency:
                # Increase URLLC allocation during emergencies
                emergency_allocation = np.array([
                    self.config['emergency_allocation']['embb'],
                    self.config['emergency_allocation']['urllc'],
                    self.config['emergency_allocation']['mmtc']
                ])
                
                # Mix model prediction with emergency allocation
                final_allocation = 0.3 * model_allocation + 0.7 * emergency_allocation
            else:
                # Apply stability factor to avoid rapid changes
                stability_factor = self.config['stability_factor']
                final_allocation = stability_factor * self.current_allocation + (1 - stability_factor) * model_allocation
            
            # Check for QoS violations and adjust if needed
            final_allocation = self._adjust_for_qos(final_allocation, utilization)
            
            # Ensure allocations are within valid range and sum to 1
            final_allocation = np.clip(final_allocation, 0.1, 0.8)
            final_allocation = final_allocation / np.sum(final_allocation)
            
            # Update current allocation
            self.current_allocation = final_allocation
            
            return final_allocation
    
    def _prepare_model_input(self):
        """
        Prepare input sequence for the model.
        
        Returns:
            numpy.ndarray: Model input
        """
        # Extract features from history
        sequence = []
        for state in self.history:
            features = [
                state['traffic_load'],
                state['hour_of_day'],
                state['day_of_week'],
                state['allocations'][0],  # eMBB allocation
                state['allocations'][1],  # URLLC allocation
                state['allocations'][2],  # mMTC allocation
                state['utilizations'][0],  # eMBB utilization
                state['utilizations'][1],  # URLLC utilization
                state['utilizations'][2],  # mMTC utilization
                state['client_count'],
                state['bs_count']
            ]
            sequence.append(features)
        
        # Convert to numpy array
        X = np.array(sequence)
        
        # Scale features
        if self.scaler:
            X = self.scaler.transform(X)
        
        # Reshape for model input [batch_size=1, sequence_length, features]
        X = X.reshape(1, X.shape[0], X.shape[1])
        
        return X
    
    def _adjust_for_qos(self, allocation, utilization):
        """
        Adjust allocation to prevent QoS violations.
        
        Args:
            allocation (numpy.ndarray): Current allocation
            utilization (numpy.ndarray): Current utilization
        
        Returns:
            numpy.ndarray: Adjusted allocation
        """
        # Get QoS thresholds
        thresholds = [
            self.config['qos_thresholds']['embb'],
            self.config['qos_thresholds']['urllc'],
            self.config['qos_thresholds']['mmtc']
        ]
        
        # Check for violations and adjust
        for i, threshold in enumerate(thresholds):
            # If utilization is above threshold, increase allocation
            if utilization[i] > threshold:
                # Calculate how much to increase based on violation severity
                violation_factor = (utilization[i] - threshold) / threshold
                increase = min(0.1, violation_factor * 0.2)
                
                # Take from the least utilized slices
                other_indices = [j for j in range(3) if j != i]
                least_utilized_idx = other_indices[np.argmin(utilization[other_indices])]
                
                # Adjust allocations
                allocation[i] += increase
                allocation[least_utilized_idx] -= increase
        
        return allocation


# Example usage
if __name__ == "__main__":
    # Create slice managers
    base_manager = BaseSliceManager()
    proportional_manager = ProportionalSliceManager()
    enhanced_manager = EnhancedSliceManager(model_path="models/lstm_single")
    
    # Test with different traffic loads and utilizations
    traffic_loads = [0.5, 1.0, 1.5]
    utilizations = [
        np.array([0.5, 0.5, 0.5]),  # Equal utilization
        np.array([1.0, 0.5, 0.2]),  # High eMBB
        np.array([0.3, 1.2, 0.5])   # High URLLC
    ]
    
    # Compare allocations
    for i, traffic_load in enumerate(traffic_loads):
        for j, utilization in enumerate(utilizations):
            print(f"\nScenario {i+1}.{j+1}: Traffic={traffic_load}, Utilization={utilization}")
            
            # Base manager
            base_allocation = base_manager.allocate_resources(traffic_load, utilization)
            print(f"Base Manager:        eMBB={base_allocation[0]:.2f}, URLLC={base_allocation[1]:.2f}, mMTC={base_allocation[2]:.2f}")
            
            # Proportional manager
            prop_allocation = proportional_manager.allocate_resources(traffic_load, utilization)
            print(f"Proportional Manager: eMBB={prop_allocation[0]:.2f}, URLLC={prop_allocation[1]:.2f}, mMTC={prop_allocation[2]:.2f}")
            
            # Enhanced manager
            try:
                enhanced_allocation = enhanced_manager.allocate_resources(traffic_load, utilization)
                print(f"Enhanced Manager:    eMBB={enhanced_allocation[0]:.2f}, URLLC={enhanced_allocation[1]:.2f}, mMTC={enhanced_allocation[2]:.2f}")
            except Exception as e:
                print(f"Enhanced Manager: Error - {e}")
    
    # Test emergency mode
    print("\nEmergency Mode Test:")
    base_manager.set_emergency_mode(True)
    proportional_manager.set_emergency_mode(True)
    enhanced_manager.set_emergency_mode(True)
    
    # Get allocations in emergency mode
    base_allocation = base_manager.allocate_resources(1.0, np.array([0.5, 0.5, 0.5]))
    prop_allocation = proportional_manager.allocate_resources(1.0, np.array([0.5, 0.5, 0.5]))
    try:
        enhanced_allocation = enhanced_manager.allocate_resources(1.0, np.array([0.5, 0.5, 0.5]))
        print(f"Enhanced Manager:    eMBB={enhanced_allocation[0]:.2f}, URLLC={enhanced_allocation[1]:.2f}, mMTC={enhanced_allocation[2]:.2f}")
    except Exception as e:
        print(f"Enhanced Manager: Error - {e}")
    
    print(f"Base Manager:        eMBB={base_allocation[0]:.2f}, URLLC={base_allocation[1]:.2f}, mMTC={base_allocation[2]:.2f}")
    print(f"Proportional Manager: eMBB={prop_allocation[0]:.2f}, URLLC={prop_allocation[1]:.2f}, mMTC={prop_allocation[2]:.2f}") 