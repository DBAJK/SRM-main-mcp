#!/usr/bin/env python3
"""
Slice Optimization Module

This module provides optimization algorithms for 5G network slicing,
including both traditional and AI-based approaches.

3GPP Standards Compliance:
- Implements slice types according to 3GPP TS 23.501
- Follows QoS framework defined in 3GPP TS 23.501 Section 5.7
- Supports Network Slice Selection Function (NSSF) as per 3GPP TS 23.501 Section 6.2.14
"""

import os
import numpy as np
import time
from datetime import datetime
import json
import matplotlib.pyplot as plt

# Import AI models if available
try:
    from slicesim.ai.lstm_predictor import SliceAllocationPredictor
    from slicesim.ai.dqn_classifier import TrafficClassifier
    from slicesim.nssm import NetworkSliceSubnetManager, SliceType, SliceState
    from slicesim.slice_selection import NetworkSliceSelectionFunction
    AI_AVAILABLE = True
except ImportError as e:
    print(f"Warning: {e}")
    AI_AVAILABLE = False

class SliceOptimizer:
    """Optimizer for network slice resource allocation"""
    
    def __init__(self, use_ai=False, lstm_model_path=None, dqn_model_path=None):
        """Initialize the slice optimizer
        
        Args:
            use_ai (bool): Whether to use AI-based optimization
            lstm_model_path (str): Path to LSTM model
            dqn_model_path (str): Path to DQN model
        """
        self.use_ai = use_ai and AI_AVAILABLE
        self.lstm_model = None
        self.dqn_model = None
        self.optimization_history = []
        
        # 3GPP-compliant components
        self.nssm = None
        self.nssf = None
        
        # Load AI models if available and requested
        if self.use_ai:
            print("Initializing AI-based slice optimizer...")
            self.lstm_model = SliceAllocationPredictor(model_path=lstm_model_path)
            self.dqn_model = TrafficClassifier(model_path=dqn_model_path)
            
            # Initialize 3GPP-compliant components
            try:
                self.nssm = NetworkSliceSubnetManager(storage_path="data/slice_subnets.json")
                self.nssf = NetworkSliceSelectionFunction(use_ai=True)
                print("3GPP-compliant components initialized")
            except Exception as e:
                print(f"Error initializing 3GPP components: {e}")
            
            print("AI models loaded successfully")
        else:
            print("Using traditional slice optimization (AI not available or disabled)")
    
    def optimize_slices(self, network_state):
        """Optimize slice allocation based on current network state
        
        Args:
            network_state (dict): Current network state
            
        Returns:
            dict: Optimized slice allocation
        """
        start_time = time.time()
        
        # Extract relevant features
        features = self._extract_features(network_state)
        
        # Perform optimization (AI or traditional)
        if self.use_ai:
            optimized_allocation = self._ai_optimization(features, network_state)
        else:
            optimized_allocation = self._traditional_optimization(features, network_state)
        
        # Record optimization
        optimization_record = {
            'timestamp': datetime.now().isoformat(),
            'network_state': {
                'time': network_state.get('time', 0),
                'clients': len(network_state.get('clients', [])),
                'base_stations': len(network_state.get('base_stations', []))
            },
            'optimization_time': time.time() - start_time,
            'optimized_allocation': optimized_allocation
        }
        self.optimization_history.append(optimization_record)
        
        return optimized_allocation
    
    def _extract_features(self, network_state):
        """Extract features from the network state
        
        Args:
            network_state (dict): Current network state
            
        Returns:
            dict: Extracted features
        """
        # Initialize feature collections
        features = {
            'global': {},
            'base_stations': [],
            'slices': {
                'eMBB': {},
                'URLLC': {},
                'mMTC': {}
            }
        }
        
        # Extract global features
        total_clients = len(network_state.get('clients', []))
        active_clients = len([c for c in network_state.get('clients', []) if c.get('active', False)])
        
        # Add 3GPP-specific global features
        features['global'] = {
            'time': network_state.get('time', 0),
            'total_clients': total_clients,
            'active_clients': active_clients,
            'total_base_stations': len(network_state.get('base_stations', [])),
            # 3GPP-specific features
            'plmn_id': network_state.get('plmn_id', '00101'),
            'nssai': network_state.get('nssai', {'eMBB': 1, 'URLLC': 2, 'mMTC': 3})
        }
        
        # Extract base station features
        for bs in network_state.get('base_stations', []):
            bs_clients = [c for c in network_state.get('clients', []) if c.get('base_station') == bs.get('id')]
            
            bs_features = {
                'id': bs.get('id'),
                'capacity': bs.get('capacity', 0),
                'location': bs.get('location', [0, 0]),
                'client_count': len(bs_clients),
                'active_client_count': len([c for c in bs_clients if c.get('active', False)]),
                'slice_usage': bs.get('slice_usage', {'eMBB': 0, 'URLLC': 0, 'mMTC': 0}),
                'slice_allocation': bs.get('slice_allocation', {'eMBB': 0.33, 'URLLC': 0.33, 'mMTC': 0.34}),
                # 3GPP-specific features
                'slice_qos': {
                    'eMBB': {'5qi': 2, 'priority_level': 10, 'packet_delay_budget': 100},
                    'URLLC': {'5qi': 82, 'priority_level': 5, 'packet_delay_budget': 10},
                    'mMTC': {'5qi': 7, 'priority_level': 15, 'packet_delay_budget': 200}
                }
            }
            
            features['base_stations'].append(bs_features)
        
        # Extract slice-specific features
        for slice_type in ['eMBB', 'URLLC', 'mMTC']:
            slice_clients = [c for c in network_state.get('clients', []) if c.get('slice') == slice_type]
            
            # Calculate average data rate for slice
            data_rates = [c.get('data_rate', 0) for c in slice_clients]
            avg_data_rate = sum(data_rates) / max(1, len(data_rates))
            
            # Calculate total slice usage across base stations
            total_usage = sum(bs.get('slice_usage', {}).get(slice_type, 0) for bs in network_state.get('base_stations', []))
            total_allocation = sum(bs.get('slice_allocation', {}).get(slice_type, 0) for bs in network_state.get('base_stations', []))
            
            # Get 3GPP SST value for this slice type
            sst_map = {'eMBB': 1, 'URLLC': 2, 'mMTC': 3}
            sst = sst_map.get(slice_type, 1)
            
            features['slices'][slice_type] = {
                'client_count': len(slice_clients),
                'active_client_count': len([c for c in slice_clients if c.get('active', False)]),
                'avg_data_rate': avg_data_rate,
                'total_usage': total_usage,
                'total_allocation': total_allocation,
                # 3GPP-specific features
                'sst': sst,
                '5qi': 2 if slice_type == 'eMBB' else (82 if slice_type == 'URLLC' else 7)
            }
        
        return features
    
    def _traditional_optimization(self, features, network_state):
        """Perform traditional optimization based on simple rules
        
        Args:
            features (dict): Extracted features
            network_state (dict): Current network state
            
        Returns:
            dict: Optimized slice allocation
        """
        # Simple brute force approach - static allocation based on slice type
        # This approach doesn't adapt well to changing conditions
        optimized_allocation = {}
        
        # Static allocation rules regardless of actual usage
        # eMBB gets most bandwidth during day, URLLC at night, and mMTC gets fixed small portion
        time_of_day = features['global']['time'] % 24
        
        for bs_features in features['base_stations']:
            bs_id = bs_features['id']
            
            # Very simplistic time-based allocation that doesn't consider actual usage
            if 8 <= time_of_day <= 20:  # Daytime: prioritize eMBB
                new_allocation = {
                    'eMBB': 0.6,
                    'URLLC': 0.25,
                    'mMTC': 0.15
                }
            else:  # Nighttime: prioritize URLLC
                new_allocation = {
                    'eMBB': 0.3,
                    'URLLC': 0.5,
                    'mMTC': 0.2
                }
            
            # Store optimized allocation for this base station
            optimized_allocation[bs_id] = new_allocation
        
        return optimized_allocation
    
    def _ai_optimization(self, features, network_state):
        """Perform AI-based optimization
        
        Args:
            features (dict): Extracted features
            network_state (dict): Current network state
            
        Returns:
            dict: Optimized slice allocation
        """
        # Initialize optimized allocation
        optimized_allocation = {}
        
        # Create input features for AI models
        time_of_day = features['global']['time'] % 24 / 24  # Normalize time to 0-1
        day_of_week = (features['global']['time'] // 24) % 7 / 6  # Normalize day to 0-1
        
        # Process each base station
        for bs_features in features['base_stations']:
            bs_id = bs_features['id']
            current_allocation = bs_features['slice_allocation']
            slice_usage = bs_features['slice_usage']
            
            # Calculate traffic load (0-2 range)
            total_capacity = bs_features['capacity']
            total_usage = sum(slice_usage.values())
            traffic_load = min(2.0, total_usage / max(0.001, total_capacity))
            
            # Calculate individual slice utilization ratios
            slice_utilization = {}
            for slice_type in ['eMBB', 'URLLC', 'mMTC']:
                usage = slice_usage.get(slice_type, 0)
                allocation = current_allocation.get(slice_type, 0.33) * total_capacity
                if allocation > 0:
                    slice_utilization[slice_type] = min(2.0, usage / allocation)
                else:
                    slice_utilization[slice_type] = 0
            
            # Prepare richer input for LSTM model
            lstm_input = np.array([
                traffic_load,  
                time_of_day,
                day_of_week,
                current_allocation.get('eMBB', 0.33),
                current_allocation.get('URLLC', 0.33),
                current_allocation.get('mMTC', 0.34),
                slice_utilization.get('eMBB', 0),
                slice_utilization.get('URLLC', 0),
                slice_utilization.get('mMTC', 0),
                bs_features['client_count'] / 20,  # Normalize client count
                len(features['base_stations']) / 5  # Normalize base station count
            ])
            
            # Get optimized allocation from LSTM
            predicted_allocation = self.lstm_model.predict(lstm_input)[0]
            
            # Classify traffic using DQN with the same rich features
            _, traffic_probabilities = self.dqn_model.classify(lstm_input)
            
            # Fine-tune allocation based on traffic classification
            final_allocation = self._fine_tune_allocation(predicted_allocation, traffic_probabilities[0])
            
            # Apply 3GPP QoS constraints if NSSF is available
            if self.nssf:
                final_allocation = self._apply_3gpp_qos_constraints(final_allocation, bs_features)
            
            # Convert to dictionary
            new_allocation = {
                'eMBB': final_allocation[0],
                'URLLC': final_allocation[1],
                'mMTC': final_allocation[2]
            }
            
            # Store optimized allocation for this base station
            optimized_allocation[bs_id] = new_allocation
        
        return optimized_allocation
    
    def _apply_3gpp_qos_constraints(self, allocation, bs_features):
        """Apply 3GPP QoS constraints to allocation
        
        Args:
            allocation (numpy.ndarray): Allocation percentages [eMBB, URLLC, mMTC]
            bs_features (dict): Base station features
            
        Returns:
            numpy.ndarray: Adjusted allocation
        """
        # Get QoS parameters for each slice
        slice_qos = bs_features.get('slice_qos', {})
        
        # Ensure minimum allocation for URLLC based on priority level
        urllc_qos = slice_qos.get('URLLC', {})
        urllc_priority = urllc_qos.get('priority_level', 5)
        
        # Higher priority (lower number) means more guaranteed resources
        # Priority 5 (URLLC) should have at least 20% resources
        min_urllc = 0.2
        
        # If URLLC allocation is below minimum, adjust
        if allocation[1] < min_urllc:
            # Calculate how much to take from other slices
            shortfall = min_urllc - allocation[1]
            
            # Take proportionally from eMBB and mMTC
            total_other = allocation[0] + allocation[2]
            if total_other > 0:
                embb_reduction = shortfall * (allocation[0] / total_other)
                mmtc_reduction = shortfall * (allocation[2] / total_other)
                
                # Apply adjustments
                allocation[0] -= embb_reduction
                allocation[1] = min_urllc
                allocation[2] -= mmtc_reduction
        
        # Ensure minimum allocation for each slice type (at least 10%)
        allocation = np.clip(allocation, 0.1, 0.8)
        
        # Normalize to ensure sum is 1
        allocation = allocation / np.sum(allocation)
        
        return allocation
    
    def _fine_tune_allocation(self, base_allocation, traffic_class_probs):
        """Fine-tune allocation based on traffic classification
        
        Args:
            base_allocation (numpy.ndarray): Base allocation from LSTM
            traffic_class_probs (numpy.ndarray): Traffic class probabilities
            
        Returns:
            numpy.ndarray: Fine-tuned allocation
        """
        # Convert to numpy arrays
        base_allocation = np.array(base_allocation)
        traffic_class_probs = np.array(traffic_class_probs)
        
        # Calculate weighted adjustment
        adjustment = traffic_class_probs * 0.2  # 20% influence from traffic class
        
        # Apply adjustment
        adjusted_allocation = base_allocation * 0.8 + adjustment
        
        # Normalize to ensure sum is 1
        adjusted_allocation = adjusted_allocation / np.sum(adjusted_allocation)
        
        return adjusted_allocation
    
    def train_models(self, data=None, save_path=None):
        """Train AI models for slice optimization
        
        Args:
            data (list): Training data (optional)
            save_path (str): Path to save trained models
            
        Returns:
            dict: Training metrics
        """
        if not self.use_ai:
            print("AI optimization is disabled, cannot train models")
            return {}
        
        metrics = {}
        
        # Train LSTM model
        print("Training LSTM model...")
        if data:
            # TODO: Convert data to LSTM training format
            pass
        else:
            # Generate synthetic data
            X_train, y_train, X_val, y_val = self.lstm_model._generate_training_data(10000)
            history = self.lstm_model.train(X_train, y_train, epochs=100, batch_size=64, validation_data=(X_val, y_val))
            metrics['lstm'] = {
                'loss': history.history['loss'],
                'val_loss': history.history['val_loss'],
                'mae': history.history['mae'],
                'val_mae': history.history['val_mae']
            }
        
        # Train DQN model
        print("Training DQN model...")
        if data:
            # TODO: Convert data to DQN training format
            pass
        else:
            # Generate synthetic data
            X_train, y_train, X_val, y_val = self.dqn_model._generate_training_data(10000)
            history = self.dqn_model.train(X_train, y_train, epochs=100, batch_size=64, validation_data=(X_val, y_val))
            metrics['dqn'] = {
                'loss': history.history['loss'],
                'val_loss': history.history['val_loss'],
                'accuracy': history.history['accuracy'],
                'val_accuracy': history.history['val_accuracy']
            }
        
        # Save models if path is provided
        if save_path:
            os.makedirs(save_path, exist_ok=True)
            lstm_path = os.path.join(save_path, "lstm_model")
            dqn_path = os.path.join(save_path, "dqn_model")
            
            self.lstm_model.save(lstm_path)
            self.dqn_model.save(dqn_path)
            
            print(f"Models saved to {save_path}")
        
        return metrics
    
    def save_optimization_history(self, file_path):
        """Save optimization history to file
        
        Args:
            file_path (str): Path to save the file
        """
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        # Save to JSON file
        with open(file_path, 'w') as f:
            json.dump(self.optimization_history, f, indent=2)
        
        print(f"Optimization history saved to {file_path}")
    
    def plot_optimization_results(self, save_path=None):
        """Plot optimization results
        
        Args:
            save_path (str): Path to save the plot
        """
        if not self.optimization_history:
            print("No optimization history available")
            return
        
        # Extract data for plotting
        timestamps = []
        optimization_times = []
        allocations = {
            'eMBB': [],
            'URLLC': [],
            'mMTC': []
        }
        
        for record in self.optimization_history:
            timestamps.append(record['network_state']['time'])
            optimization_times.append(record['optimization_time'])
            
            # Average allocation across all base stations
            avg_allocation = {
                'eMBB': 0,
                'URLLC': 0,
                'mMTC': 0
            }
            
            for bs_id, allocation in record['optimized_allocation'].items():
                for slice_type in avg_allocation:
                    avg_allocation[slice_type] += allocation.get(slice_type, 0)
            
            # Normalize by number of base stations
            num_bs = len(record['optimized_allocation'])
            for slice_type in avg_allocation:
                avg_allocation[slice_type] /= max(1, num_bs)
                allocations[slice_type].append(avg_allocation[slice_type])
        
        # Create plots
        plt.figure(figsize=(15, 10))
        
        # Plot optimization time
        plt.subplot(2, 1, 1)
        plt.plot(timestamps, optimization_times)
        plt.title('Optimization Time')
        plt.xlabel('Network Time')
        plt.ylabel('Execution Time (s)')
        plt.grid(True)
        
        # Plot slice allocations
        plt.subplot(2, 1, 2)
        for slice_type, values in allocations.items():
            plt.plot(timestamps, values, label=slice_type)
        
        plt.title('Average Slice Allocation')
        plt.xlabel('Network Time')
        plt.ylabel('Allocation Ratio')
        plt.legend()
        plt.grid(True)
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path)
            print(f"Optimization results plot saved to {save_path}")
        
        plt.show()


def find_optimal_slice(client_features, slice_optimizer=None):
    """Find optimal slice for a client based on features
    
    Args:
        client_features (dict): Client features
        slice_optimizer (SliceOptimizer): Slice optimizer (optional)
        
    Returns:
        str: Optimal slice type
    """
    # If no optimizer provided, create one
    if not slice_optimizer:
        slice_optimizer = SliceOptimizer(use_ai=AI_AVAILABLE)
    
    # If AI is available, use DQN classifier
    if slice_optimizer.use_ai and slice_optimizer.dqn_model:
        # Convert client features to model input
        features = np.array([
            client_features.get('data_rate', 0.5) / 2.0,  # Normalize data rate
            client_features.get('time_of_day', 0.5),
            client_features.get('day_of_week', 0.5),
            0.33, 0.33, 0.34,  # Default allocation
            client_features.get('embb_util', 0.5),
            client_features.get('urllc_util', 0.5),
            client_features.get('mmtc_util', 0.5),
            client_features.get('client_density', 0.5),
            client_features.get('bs_count', 0.5)
        ])
        
        # Use DQN to classify
        class_idx, _ = slice_optimizer.dqn_model.classify(features)
        
        # Map class index to slice type
        slice_map = {0: 'eMBB', 1: 'URLLC', 2: 'mMTC'}
        return slice_map.get(class_idx[0], 'eMBB')
    
    # If 3GPP NSSF is available, use it
    elif slice_optimizer.nssf:
        # Extract service type and QoS requirements
        service_type = client_features.get('service_type', 'default')
        
        qos_requirements = {
            'latency': client_features.get('latency', 50),
            'client_density': client_features.get('client_density', 0.5),
            'time_of_day': client_features.get('time_of_day', 0.5),
            'day_of_week': client_features.get('day_of_week', 0.5)
        }
        
        # Use NSSF to select slice
        s_nssai = slice_optimizer.nssf.select_slice(service_type, qos_requirements)
        
        # Map SST to slice type
        sst_map = {1: 'eMBB', 2: 'URLLC', 3: 'mMTC'}
        return sst_map.get(s_nssai.sst, 'eMBB')
    
    # Fallback to simple rule-based selection
    else:
        data_rate = client_features.get('data_rate', 0)
        latency = client_features.get('latency', 100)
        connection_density = client_features.get('client_density', 0)
        
        if latency < 20:
            return 'URLLC'  # Low latency requirement
        elif connection_density > 0.7:
            return 'mMTC'  # High connection density
        elif data_rate > 1.0:
            return 'eMBB'  # High data rate
        else:
            return 'eMBB'  # Default to eMBB


# Example usage if script is run directly
if __name__ == "__main__":
    # Create optimizer
    optimizer = SliceOptimizer(use_ai=True)
    
    # Create sample network state
    network_state = {
        'time': 12,  # Noon
        'clients': [
            {'id': 1, 'active': True, 'data_rate': 1.5, 'base_station': 'bs1', 'slice': 'eMBB'},
            {'id': 2, 'active': True, 'data_rate': 0.5, 'base_station': 'bs1', 'slice': 'URLLC'},
            {'id': 3, 'active': True, 'data_rate': 0.2, 'base_station': 'bs1', 'slice': 'mMTC'},
            {'id': 4, 'active': False, 'data_rate': 0, 'base_station': 'bs1', 'slice': 'eMBB'},
        ],
        'base_stations': [
            {
                'id': 'bs1',
                'capacity': 10,
                'location': [0, 0],
                'slice_usage': {'eMBB': 1.5, 'URLLC': 0.5, 'mMTC': 0.2},
                'slice_allocation': {'eMBB': 0.33, 'URLLC': 0.33, 'mMTC': 0.34}
            }
        ]
    }
    
    # Optimize slices
    optimized_allocation = optimizer.optimize_slices(network_state)
    print("Optimized allocation:", optimized_allocation)
    
    # Test find_optimal_slice function
    client_features = {
        'data_rate': 1.5,
        'latency': 10,
        'client_density': 0.3,
        'service_type': 'gaming',
        'time_of_day': 0.5,
        'day_of_week': 0.3
    }
    
    optimal_slice = find_optimal_slice(client_features, optimizer)
    print(f"Optimal slice for client: {optimal_slice}") 