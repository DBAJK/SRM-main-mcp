#!/usr/bin/env python3
"""
5G Network Slicing Orchestrator

This module implements the orchestrator for the 5G network slicing system.
The orchestrator coordinates the slice management and model predictions,
providing a centralized control point for the entire system.

Key responsibilities:
- Load and manage ML models
- Process network telemetry data
- Make slice allocation decisions
- Coordinate between different system components
- Handle emergency and special event scenarios
- Maintain system stability and performance
"""

import os
import numpy as np
import tensorflow as tf
import logging
import time
from datetime import datetime
from threading import Thread, Lock
from sklearn.preprocessing import MinMaxScaler
import json
import matplotlib.pyplot as plt

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SliceOrchestrator:
    """
    Orchestrator for 5G network slicing system.
    
    This class coordinates the slice management and model predictions,
    providing a centralized control point for the entire system.
    """
    
    def __init__(self, model_path=None, config_path=None, look_ahead=3):
        """
        Initialize the orchestrator.
        
        Args:
            model_path (str): Path to the trained model
            config_path (str): Path to the configuration file
            look_ahead (int): Number of steps to look ahead for predictions
        """
        self.model_path = model_path
        self.config_path = config_path
        self.look_ahead = look_ahead
        
        # Default configuration
        self.config = {
            'slice_types': ['embb', 'urllc', 'mmtc'],
            'qos_thresholds': {
                'embb': 1.5,
                'urllc': 1.2,
                'mmtc': 1.8
            },
            'emergency_weights': {
                'embb': 0.3,
                'urllc': 0.6,
                'mmtc': 0.1
            },
            'normal_weights': {
                'embb': 0.4,
                'urllc': 0.3,
                'mmtc': 0.3
            },
            'update_interval': 1.0,  # seconds
            'stability_factor': 0.7,  # how much to consider previous allocation
            'proactive_factor': 0.5,  # how much to consider future predictions
            'sequence_length': 10,    # input sequence length for model
            'feature_names': [
                'traffic_load', 'hour_of_day', 'day_of_week',
                'embb_allocation', 'urllc_allocation', 'mmtc_allocation',
                'embb_utilization', 'urllc_utilization', 'mmtc_utilization',
                'client_count', 'bs_count'
            ]
        }
        
        # Load configuration if provided
        if config_path and os.path.exists(config_path):
            self._load_config()
        
        # Initialize components
        self.model = None
        self.scaler = None
        self.history = []
        self.current_allocation = np.array([1/3, 1/3, 1/3])  # Start with equal allocation
        self.current_utilization = np.array([0.0, 0.0, 0.0])
        self.is_emergency = False
        self.is_special_event = False
        self.is_iot_surge = False
        
        # Thread safety
        self.lock = Lock()
        self._running = False
        self._thread = None
        
        # Load model if provided
        if model_path:
            self.load_model(model_path)
    
    def _load_config(self):
        """Load configuration from file"""
        try:
            with open(self.config_path, 'r') as f:
                loaded_config = json.load(f)
                # Update config with loaded values
                for key, value in loaded_config.items():
                    self.config[key] = value
            logger.info(f"Configuration loaded from {self.config_path}")
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
    
    def load_model(self, model_path):
        """
        Load the trained model and scaler.
        
        Args:
            model_path (str): Path to the model directory
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
                
                # Handle different scaler formats
                if len(scaler_params) == 2:
                    # Old format: [data_min, data_max]
                    self.scaler.data_min_ = scaler_params[0]
                    self.scaler.data_max_ = scaler_params[1]
                    # Compute scale_ and min_
                    self.scaler.scale_ = 1.0 / (scaler_params[1] - scaler_params[0])
                    self.scaler.min_ = -scaler_params[0] * self.scaler.scale_
                elif len(scaler_params) >= 4:
                    # New format: [data_min, data_max, scale_, min_]
                    self.scaler.data_min_ = scaler_params[0]
                    self.scaler.data_max_ = scaler_params[1]
                    self.scaler.scale_ = scaler_params[2]
                    self.scaler.min_ = scaler_params[3]
                
                logger.info(f"Scaler loaded from {scaler_path}")
            else:
                logger.warning(f"Scaler not found at {scaler_path}, using default scaling")
                self.scaler = MinMaxScaler()
                # Fit with dummy data to initialize attributes
                self.scaler.fit(np.random.random((10, 11)))
            
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
    
    def start(self):
        """Start the orchestrator in a separate thread"""
        if self._running:
            logger.warning("Orchestrator is already running")
            return False
        
        if not self.model:
            logger.error("No model loaded, cannot start orchestrator")
            return False
        
        self._running = True
        self._thread = Thread(target=self._run_loop)
        self._thread.daemon = True
        self._thread.start()
        logger.info("Orchestrator started")
        return True
    
    def stop(self):
        """Stop the orchestrator"""
        if not self._running:
            logger.warning("Orchestrator is not running")
            return
        
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)
        logger.info("Orchestrator stopped")
    
    def _run_loop(self):
        """Main orchestrator loop"""
        while self._running:
            try:
                # Get current network state
                network_state = self._get_network_state()
                
                # Make allocation decision
                new_allocation = self.make_allocation_decision(network_state)
                
                # Apply allocation
                with self.lock:
                    self.current_allocation = new_allocation
                
                # Sleep for update interval
                time.sleep(self.config['update_interval'])
            except Exception as e:
                logger.error(f"Error in orchestrator loop: {e}")
                time.sleep(1.0)  # Sleep to avoid tight loop in case of errors
    
    def _get_network_state(self):
        """
        Get current network state (to be implemented by specific system).
        This is a placeholder that would be replaced with actual telemetry collection.
        
        Returns:
            dict: Current network state
        """
        # In a real system, this would collect telemetry data from the network
        # For now, we'll use a placeholder implementation
        now = datetime.now()
        
        # Placeholder for telemetry data
        state = {
            'timestamp': now,
            'traffic_load': 0.5 + 0.2 * np.sin(now.hour / 24.0 * 2 * np.pi),
            'hour_of_day': now.hour / 24.0,
            'day_of_week': now.weekday() / 6.0,
            'client_count': 0.5,
            'bs_count': 0.5,
            'allocations': self.current_allocation.copy(),
            'utilizations': self.current_utilization.copy(),
            'is_emergency': self.is_emergency,
            'is_special_event': self.is_special_event,
            'is_iot_surge': self.is_iot_surge
        }
        
        # Update utilizations based on traffic and allocations
        for i in range(3):
            # Add small constant to avoid division by zero
            state['utilizations'][i] = state['traffic_load'] / (state['allocations'][i] + 0.01)
        
        # Apply event effects to utilization
        if state['is_emergency']:
            state['utilizations'][1] += np.random.uniform(0.5, 1.0)  # URLLC
            state['utilizations'][0] += np.random.uniform(0.2, 0.5)  # eMBB
        
        if state['is_special_event']:
            state['utilizations'][0] += np.random.uniform(0.4, 0.8)  # eMBB
        
        if state['is_iot_surge']:
            state['utilizations'][2] += np.random.uniform(0.3, 0.7)  # mMTC
        
        # Clip utilization to valid range
        state['utilizations'] = np.clip(state['utilizations'], 0.1, 2.0)
        
        # Update current utilization
        self.current_utilization = state['utilizations'].copy()
        
        return state
    
    def make_allocation_decision(self, network_state):
        """
        Make slice allocation decision based on current state and model predictions.
        
        Args:
            network_state (dict): Current network state
        
        Returns:
            numpy.ndarray: New slice allocation
        """
        # Add current state to history
        self.history.append(network_state)
        
        # Keep only the most recent entries needed for the sequence
        if len(self.history) > self.config['sequence_length']:
            self.history = self.history[-self.config['sequence_length']:]
        
        # If we don't have enough history, use equal allocation
        if len(self.history) < self.config['sequence_length']:
            return self.current_allocation
        
        # Prepare input sequence for the model
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
        if network_state['is_emergency']:
            # Increase URLLC allocation during emergencies
            weights = self.config['emergency_weights']
            event_allocation = np.array([weights['embb'], weights['urllc'], weights['mmtc']])
            
            # Mix model prediction with emergency allocation
            final_allocation = 0.3 * model_allocation + 0.7 * event_allocation
        else:
            # Apply stability factor to avoid rapid changes
            stability_factor = self.config['stability_factor']
            final_allocation = stability_factor * self.current_allocation + (1 - stability_factor) * model_allocation
        
        # Check for QoS violations and adjust if needed
        final_allocation = self._adjust_for_qos(final_allocation, network_state['utilizations'])
        
        # Ensure allocations are within valid range and sum to 1
        final_allocation = np.clip(final_allocation, 0.1, 0.8)
        final_allocation = final_allocation / np.sum(final_allocation)
        
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
    
    def set_emergency_mode(self, is_emergency):
        """
        Set emergency mode.
        
        Args:
            is_emergency (bool): Whether there's an emergency
        """
        with self.lock:
            self.is_emergency = is_emergency
        logger.info(f"Emergency mode set to {is_emergency}")
    
    def set_special_event_mode(self, is_special_event):
        """
        Set special event mode.
        
        Args:
            is_special_event (bool): Whether there's a special event
        """
        with self.lock:
            self.is_special_event = is_special_event
        logger.info(f"Special event mode set to {is_special_event}")
    
    def set_iot_surge_mode(self, is_iot_surge):
        """
        Set IoT surge mode.
        
        Args:
            is_iot_surge (bool): Whether there's an IoT surge
        """
        with self.lock:
            self.is_iot_surge = is_iot_surge
        logger.info(f"IoT surge mode set to {is_iot_surge}")
    
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
    
    def save_state(self, output_path):
        """
        Save current orchestrator state.
        
        Args:
            output_path (str): Path to save state
        """
        state = {
            'timestamp': datetime.now().isoformat(),
            'current_allocation': self.current_allocation.tolist(),
            'current_utilization': self.current_utilization.tolist(),
            'is_emergency': self.is_emergency,
            'is_special_event': self.is_special_event,
            'is_iot_surge': self.is_iot_surge,
            'config': self.config
        }
        
        try:
            with open(output_path, 'w') as f:
                json.dump(state, f, indent=2)
            logger.info(f"State saved to {output_path}")
            return True
        except Exception as e:
            logger.error(f"Error saving state: {e}")
            return False
    
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
        
        # Add event indicators
        events = []
        if self.is_emergency:
            events.append('Emergency')
        if self.is_special_event:
            events.append('Special Event')
        if self.is_iot_surge:
            events.append('IoT Surge')
        
        if events:
            fig.suptitle(f"Network Status: {', '.join(events)}", fontsize=16)
        else:
            fig.suptitle("Network Status: Normal", fontsize=16)
        
        plt.tight_layout()
        
        # Save or show
        if output_path:
            plt.savefig(output_path)
            plt.close()
        else:
            plt.show()


# Example usage
if __name__ == "__main__":
    # Create orchestrator
    orchestrator = SliceOrchestrator(model_path="models/lstm_single")
    
    # Start orchestrator
    orchestrator.start()
    
    try:
        # Run for a while
        for i in range(10):
            # Get current allocation
            allocation = orchestrator.get_current_allocation()
            utilization = orchestrator.get_current_utilization()
            
            # Print status
            print(f"Step {i}:")
            print(f"  Allocation: eMBB={allocation[0]:.2f}, URLLC={allocation[1]:.2f}, mMTC={allocation[2]:.2f}")
            print(f"  Utilization: eMBB={utilization[0]:.2f}, URLLC={utilization[1]:.2f}, mMTC={utilization[2]:.2f}")
            
            # Simulate events
            if i == 3:
                orchestrator.set_emergency_mode(True)
                print("  Emergency mode activated")
            
            if i == 6:
                orchestrator.set_emergency_mode(False)
                print("  Emergency mode deactivated")
            
            # Visualize
            orchestrator.visualize_allocation(f"results/allocation_{i}.png")
            
            # Sleep
            time.sleep(1)
    
    finally:
        # Stop orchestrator
        orchestrator.stop() 