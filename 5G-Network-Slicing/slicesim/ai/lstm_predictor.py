#!/usr/bin/env python3
"""
LSTM-based Network Slice Allocation Predictor

This module provides an LSTM-based deep learning model for predicting
optimal slice resource allocation based on network conditions.

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
from tensorflow import keras
from tensorflow.keras.models import Sequential, load_model
from tensorflow.keras.layers import Dense, LSTM, Dropout, BatchNormalization
from tensorflow.keras.optimizers import Adam
from tensorflow.keras.callbacks import EarlyStopping

class SliceAllocationPredictor:
    """Predicts optimal slice resource allocation using LSTM
    
    3GPP Compliance:
    - SST=1: eMBB (Enhanced Mobile Broadband)
    - SST=2: URLLC (Ultra Reliable Low Latency Communications)
    - SST=3: mMTC (Massive Machine Type Communications)
    
    Where SST is Slice/Service Type as defined in 3GPP TS 23.501
    """
    
    def __init__(self, input_dim=11, sequence_length=10, model_path=None, skip_training=False):
        """Initialize the LSTM predictor
        
        Args:
            input_dim (int): Dimension of input features
            sequence_length (int): Length of input sequence
            model_path (str): Path to load the model from
            skip_training (bool): Whether to skip automatic training during initialization
        """
        self.input_dim = input_dim
        self.sequence_length = sequence_length
        self.model_path = model_path
        self.training_history = None
        
        # 3GPP Standard slice types and their SST values
        self.slice_types = {
            'eMBB': 1,   # Enhanced Mobile Broadband (SST=1)
            'URLLC': 2,  # Ultra Reliable Low Latency Communications (SST=2)
            'mMTC': 3    # Massive Machine Type Communications (SST=3)
        }
        
        # 3GPP QoS parameters per slice type (TS 23.501)
        self.qos_parameters = {
            'eMBB': {
                '5qi': [1, 2, 3, 4],  # 5G QoS Identifiers for eMBB
                'priority_level': 10,
                'packet_delay_budget': 100,  # ms
                'packet_error_rate': 10e-6
            },
            'URLLC': {
                '5qi': [80, 82, 83],  # 5G QoS Identifiers for URLLC
                'priority_level': 5,
                'packet_delay_budget': 10,  # ms
                'packet_error_rate': 10e-5
            },
            'mMTC': {
                '5qi': [5, 6, 7],  # 5G QoS Identifiers for mMTC
                'priority_level': 15,
                'packet_delay_budget': 200,  # ms
                'packet_error_rate': 10e-4
            }
        }
        
        # Initialize model
        if model_path and os.path.exists(model_path):
            try:
                self.model = load_model(model_path)
                print(f"Loaded LSTM model from {model_path}")
            except Exception as e:
                print(f"Error loading model: {e}")
                self.model = self._build_model()
        else:
            self.model = self._build_model()
            
            # If no pre-trained model and not skipping training, train on synthetic data
            if not skip_training:
                print("Training LSTM predictor on synthetic data...")
                X_train, y_train, X_val, y_val = self._generate_training_data(15000)  # Increased to 15,000 samples
                self.training_history = self.train(X_train, y_train, epochs=150, batch_size=64, validation_data=(X_val, y_val))
                val_loss = self.training_history.history['val_loss'][-1]
                val_mae = self.training_history.history['val_mae'][-1]
                print(f"Training completed. Validation Loss: {val_loss:.4f}, Validation MAE: {val_mae:.4f}")
    
    def _build_model(self):
        """Build the LSTM model
        
        Returns:
            keras.Model: Compiled LSTM model
        """
        # Print model architecture
        print("LSTM Predictor Model Architecture:")
        
        model = Sequential([
            # First LSTM layer with return sequences for stacking
            LSTM(128, return_sequences=True, 
                 input_shape=(self.sequence_length, self.input_dim),
                 activation='tanh'),
            BatchNormalization(),
            Dropout(0.3),
            
            # Second LSTM layer
            LSTM(64, return_sequences=False, activation='tanh'),
            BatchNormalization(),
            Dropout(0.3),
            
            # Dense hidden layers
            Dense(32, activation='relu'),
            BatchNormalization(),
            Dropout(0.2),
            
            Dense(16, activation='relu'),
            
            # Output layer (3 slices - eMBB, URLLC, mMTC)
            # Softmax ensures outputs sum to 1 (proper allocation)
            Dense(3, activation='softmax')
        ])
        
        # Compile model with better learning rate
        model.compile(
            optimizer=Adam(learning_rate=0.001),
            loss='mean_squared_error',
            metrics=['mae']
        )
        
        # Print model summary
        model.summary()
        
        return model
    
    def _generate_training_data(self, num_samples=15000):
        """Generate synthetic training data
        
        Args:
            num_samples (int): Number of samples to generate
            
        Returns:
            tuple: (X_train, y_train, X_val, y_val)
        """
        # Generate time series data for multiple scenarios
        # Input features: [traffic_load, time_of_day, day_of_week, embb_alloc, urllc_alloc, mmtc_alloc, 
        #                  embb_util, urllc_util, mmtc_util, client_count, bs_count]
        
        # Create empty arrays
        X = np.zeros((num_samples, self.sequence_length, self.input_dim))
        y = np.zeros((num_samples, 3))  # 3 slice types
        
        # Generate different scenarios with varied distributions
        scenarios = ['baseline', 'dynamic', 'emergency', 'smart_city', 'mixed']
        scenario_probs = [0.25, 0.25, 0.2, 0.2, 0.1]  # Probability distribution for scenarios
        
        for i in range(num_samples):
            # Randomly choose scenario type
            scenario_type = np.random.choice(scenarios, p=scenario_probs)
            
            # Create sequence with time correlation
            time_of_day_start = np.random.uniform(0, 1)  # Random starting time
            day_of_week_start = np.random.uniform(0, 1)  # Random starting day
            
            # Initialize allocation with some randomness but sum to 1
            initial_allocation = np.random.dirichlet(np.ones(3) * 2)  # Alpha=2 for less extreme values
            
            # Create sequence with temporal coherence
            for j in range(self.sequence_length):
                # Time progresses through the sequence (with wraparound for day)
                time_progression = j * 0.01  # Small time increment per step
                time_of_day = (time_of_day_start + time_progression) % 1.0
                day_of_week = (day_of_week_start + (time_of_day_start + time_progression) // 1.0) % 1.0
                
                # Evolve allocation slightly from previous timestep (if not first step)
                if j > 0:
                    # Get previous allocation
                    prev_alloc = X[i, j-1, 3:6]
                    # Apply small random change while keeping sum = 1
                    noise = np.random.normal(0, 0.05, 3)
                    current_allocation = prev_alloc + noise
                    current_allocation = np.clip(current_allocation, 0.1, 0.8)  # Avoid extreme values
                    current_allocation = current_allocation / np.sum(current_allocation)  # Normalize
                else:
                    current_allocation = initial_allocation
                
                # Traffic features based on scenario
                if scenario_type == 'baseline':
                    # Regular daily patterns
                    time_factor = np.sin(time_of_day * 2 * np.pi) * 0.3 + 0.5  # Daily cycle
                    traffic_load = 0.5 + time_factor + 0.1 * np.random.randn()
                    
                    # Utilization reflects time of day (higher during day, lower at night)
                    if 0.25 < time_of_day < 0.75:  # Day time (6am-6pm)
                        slice_utilization = np.array([
                            np.random.uniform(0.5, 1.5),  # eMBB higher during day
                            np.random.uniform(0.3, 0.8),  # URLLC moderate
                            np.random.uniform(0.2, 0.6)   # mMTC lower
                        ])
                    else:  # Night time
                        slice_utilization = np.array([
                            np.random.uniform(0.2, 0.6),  # eMBB lower at night
                            np.random.uniform(0.2, 0.7),  # URLLC similar
                            np.random.uniform(0.4, 1.2)   # mMTC higher at night (IoT updates)
                        ])
                    
                    client_count = 0.4 + 0.3 * np.sin(time_of_day * 2 * np.pi) + 0.05 * np.random.randn()
                    bs_count = np.random.uniform(0.4, 0.8)
                
                elif scenario_type == 'dynamic':
                    # More volatile patterns
                    time_factor = np.sin(time_of_day * 2 * np.pi) * 0.4 + 0.5
                    day_factor = np.sin(day_of_week * 2 * np.pi) * 0.2
                    traffic_load = 0.3 + time_factor + day_factor + 0.25 * np.random.randn()
                    
                    # Random spikes in utilization
                    if np.random.random() < 0.2:  # 20% chance of traffic spike
                        spike_slice = np.random.randint(0, 3)  # Random slice gets spike
                        base_util = np.random.uniform(0.2, 0.8, 3)
                        base_util[spike_slice] = np.random.uniform(1.0, 2.0)  # Spike
                        slice_utilization = base_util
                    else:
                        slice_utilization = np.random.uniform(0.2, 1.2, 3)
                    
                    client_count = 0.3 + 0.5 * np.random.random() + 0.1 * np.sin(time_of_day * 4 * np.pi)
                    bs_count = 0.4 + 0.4 * np.random.random()
                
                elif scenario_type == 'emergency':
                    # High URLLC utilization
                    traffic_load = 0.7 + 0.3 * np.random.randn()
                    
                    # Emergency means high URLLC traffic
                    urllc_util = np.random.uniform(1.0, 2.0)  # Very high URLLC
                    slice_utilization = np.array([
                        np.random.uniform(0.1, 0.8),    # eMBB varies
                        urllc_util,                     # URLLC very high
                        np.random.uniform(0.1, 0.5)     # mMTC low
                    ])
                    
                    # More clients during emergency
                    client_count = np.random.uniform(0.6, 1.0)
                    bs_count = np.random.uniform(0.3, 0.7)
                
                elif scenario_type == 'smart_city':
                    # High mMTC utilization for IoT
                    time_factor = np.sin(time_of_day * 2 * np.pi) * 0.2 + 0.6
                    traffic_load = time_factor + 0.2 * np.random.randn()
                    
                    # Smart city means high mMTC traffic
                    mmtc_util = np.random.uniform(1.0, 2.0)  # Very high mMTC
                    slice_utilization = np.array([
                        np.random.uniform(0.2, 0.9),    # eMBB moderate
                        np.random.uniform(0.1, 0.6),    # URLLC low to moderate
                        mmtc_util                       # mMTC very high
                    ])
                    
                    client_count = np.random.uniform(0.7, 1.0)  # Many clients (IoT devices)
                    bs_count = np.random.uniform(0.5, 1.0)  # More base stations for coverage
                
                else:  # mixed scenario
                    # Randomly mix elements from different scenarios
                    traffic_load = 0.5 + 0.4 * np.random.randn()
                    slice_utilization = np.random.uniform(0.3, 1.5, 3)
                    client_count = np.random.uniform(0.3, 0.9)
                    bs_count = np.random.uniform(0.3, 0.9)
                
                # Clip and normalize values
                traffic_load = np.clip(traffic_load, 0, 2)
                slice_utilization = np.clip(slice_utilization, 0, 2)
                client_count = np.clip(client_count, 0, 1)
                bs_count = np.clip(bs_count, 0, 1)
                
                # Create feature vector for this time step
                X[i, j] = np.array([
                    traffic_load,
                    time_of_day,
                    day_of_week,
                    current_allocation[0],  # eMBB
                    current_allocation[1],  # URLLC
                    current_allocation[2],  # mMTC
                    slice_utilization[0],   # eMBB utilization
                    slice_utilization[1],   # URLLC utilization
                    slice_utilization[2],   # mMTC utilization
                    client_count,
                    bs_count
                ])
            
            # Generate optimal allocation (target) based on the final state
            final_state = X[i, -1]  # Last time step
            
            # Extract important features from final state
            final_traffic_load = final_state[0]
            final_time_of_day = final_state[1]
            final_utilization = final_state[6:9]
            
            if scenario_type == 'baseline':
                # Balanced allocation with preference based on time and utilization
                if 0.25 < final_time_of_day < 0.75:  # Day time
                    base_allocation = np.array([0.5, 0.3, 0.2])  # eMBB priority
                else:
                    base_allocation = np.array([0.3, 0.4, 0.3])  # URLLC and mMTC priority at night
                
                # Adjust based on utilization
                util_factor = final_utilization / (np.sum(final_utilization) + 1e-10)
                y[i] = 0.7 * base_allocation + 0.3 * util_factor
                
            elif scenario_type == 'dynamic':
                # More adaptive to utilization
                util_factor = final_utilization / (np.sum(final_utilization) + 1e-10)
                
                # Higher traffic load means more allocation to high utilization slices
                if final_traffic_load > 1.0:
                    # When congested, allocate more to slices with higher utilization
                    y[i] = 0.2 + 0.6 * util_factor
                else:
                    # With lower load, more balanced allocation
                    y[i] = 0.3 + 0.4 * util_factor
                
            elif scenario_type == 'emergency':
                # Priority to URLLC for emergency
                urllc_priority = 0.5 + 0.1 * np.random.randn()
                urllc_priority = np.clip(urllc_priority, 0.45, 0.6)
                
                # Calculate remaining allocation
                remaining = 1.0 - urllc_priority
                
                # Divide remaining based on utilization ratio between eMBB and mMTC
                embb_util = final_utilization[0]
                mmtc_util = final_utilization[2]
                total_remaining_util = embb_util + mmtc_util + 1e-10
                
                embb_alloc = remaining * (embb_util / total_remaining_util)
                mmtc_alloc = remaining - embb_alloc
                
                y[i] = np.array([embb_alloc, urllc_priority, mmtc_alloc])
                
            elif scenario_type == 'smart_city':
                # Priority to mMTC for IoT devices
                mmtc_priority = 0.5 + 0.1 * np.random.randn()
                mmtc_priority = np.clip(mmtc_priority, 0.45, 0.6)
                
                # Calculate remaining allocation
                remaining = 1.0 - mmtc_priority
                
                # Divide remaining based on utilization ratio between eMBB and URLLC
                embb_util = final_utilization[0]
                urllc_util = final_utilization[1]
                total_remaining_util = embb_util + urllc_util + 1e-10
                
                embb_alloc = remaining * (embb_util / total_remaining_util)
                urllc_alloc = remaining - embb_alloc
                
                y[i] = np.array([embb_alloc, urllc_alloc, mmtc_priority])
                
            else:  # mixed
                # Based mostly on utilization with minimum guarantees
                util_factor = final_utilization / (np.sum(final_utilization) + 1e-10)
                min_guarantees = np.array([0.2, 0.2, 0.2])
                remaining = 0.4
                
                y[i] = min_guarantees + remaining * util_factor
            
            # Normalize to ensure sum is exactly 1
            y[i] = y[i] / np.sum(y[i])
            
            # Add small noise to create more diversity in targets
            noise = np.random.normal(0, 0.02, 3)
            y[i] = y[i] + noise
            
            # Clip to ensure allocations are at least 10%
            y[i] = np.clip(y[i], 0.1, 0.8)
            
            # Normalize again to ensure sum is exactly 1
            y[i] = y[i] / np.sum(y[i])
        
        # Split into training and validation sets (80/20)
        split_idx = int(0.8 * num_samples)
        X_train, X_val = X[:split_idx], X[split_idx:]
        y_train, y_val = y[:split_idx], y[split_idx:]
        
        print(f"Generated {len(X_train)} training samples and {len(X_val)} validation samples")
        
        return X_train, y_train, X_val, y_val
    
    def train(self, X, y, epochs=150, batch_size=64, validation_data=None):
        """Train the model
        
        Args:
            X (numpy.ndarray): Input features
            y (numpy.ndarray): Target values
            epochs (int): Number of training epochs
            batch_size (int): Batch size
            validation_data (tuple): Validation data (X_val, y_val)
            
        Returns:
            keras.callbacks.History: Training history
        """
        # Early stopping to prevent overfitting
        early_stopping = EarlyStopping(
            monitor='val_loss' if validation_data else 'loss',
            patience=15,
            restore_best_weights=True
        )
        
        # Train model
        history = self.model.fit(
            X, y,
            epochs=epochs,
            batch_size=batch_size,
            validation_data=validation_data,
            callbacks=[early_stopping],
            verbose=1  # Show progress bar
        )
        
        return history
    
    def predict(self, input_data):
        """Predict optimal slice allocation
        
        Args:
            input_data (numpy.ndarray): Input features
            
        Returns:
            numpy.ndarray: Predicted slice allocation
        """
        # Reshape input if needed
        if len(input_data.shape) == 1:
            # Single feature vector needs to be reshaped as sequence
            # Create a sequence by repeating the same input
            seq_input = np.tile(input_data, (self.sequence_length, 1))
            input_data = seq_input.reshape(1, self.sequence_length, self.input_dim)
        elif len(input_data.shape) == 2:
            # Already a sequence, just add batch dimension
            input_data = input_data.reshape(1, *input_data.shape)
        
        # Make prediction
        prediction = self.model.predict(input_data)
        
        return prediction
    
    def evaluate(self, X_test, y_test):
        """Evaluate the model
        
        Args:
            X_test (numpy.ndarray): Test features
            y_test (numpy.ndarray): Test targets
            
        Returns:
            tuple: (loss, mae)
        """
        return self.model.evaluate(X_test, y_test)
    
    def save(self, path=None):
        """Save the model
        
        Args:
            path (str): Path to save the model
        """
        if path is None:
            path = self.model_path or f"lstm_model_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else '.', exist_ok=True)
        
        self.model.save(path)
        print(f"Model saved to {path}")
    
    def plot_training_history(self, history=None):
        """Plot training history
        
        Args:
            history (keras.callbacks.History): Training history
        """
        if history is None:
            history = self.training_history
            
        if history is None:
            print("No training history available")
            return
            
        plt.figure(figsize=(12, 5))
        
        # Plot loss
        plt.subplot(1, 2, 1)
        plt.plot(history.history['loss'], label='Training Loss')
        if 'val_loss' in history.history:
            plt.plot(history.history['val_loss'], label='Validation Loss')
        plt.title('Loss')
        plt.xlabel('Epoch')
        plt.ylabel('Loss')
        plt.legend()
        
        # Plot MAE
        plt.subplot(1, 2, 2)
        plt.plot(history.history['mae'], label='Training MAE')
        if 'val_mae' in history.history:
            plt.plot(history.history['val_mae'], label='Validation MAE')
        plt.title('Mean Absolute Error')
        plt.xlabel('Epoch')
        plt.ylabel('MAE')
        plt.legend()
        
        plt.tight_layout()
        plt.show()


# Example usage if script is run directly
if __name__ == "__main__":
    # Create predictor
    predictor = SliceAllocationPredictor()
    
    # Generate test data
    X_test, y_test, _, _ = predictor._generate_training_data(100)
    
    # Make predictions
    predictions = predictor.predict(X_test)
    
    # Evaluate model
    loss, mae = predictor.evaluate(X_test, y_test)
    print(f"Test Loss: {loss:.4f}, Test MAE: {mae:.4f}")
    
    # Plot training history
    predictor.plot_training_history()
    
    # Plot some predictions vs actual
    plt.figure(figsize=(16, 8))
    for i in range(4):
        plt.subplot(2, 2, i+1)
        sample_idx = np.random.randint(0, len(predictions))
        
        # Get prediction and actual
        pred = predictions[sample_idx]
        actual = y_test[sample_idx]
        
        # Plot
        labels = ['eMBB', 'URLLC', 'mMTC']
        x = np.arange(len(labels))
        width = 0.35
        
        plt.bar(x - width/2, actual, width, label='Actual', color='blue', alpha=0.7)
        plt.bar(x + width/2, pred, width, label='Predicted', color='red', alpha=0.7)
        
        plt.ylabel('Allocation')
        plt.title(f'Sample {sample_idx}')
        plt.xticks(x, labels)
        plt.ylim(0, 1)
        plt.legend()
        
        # Add values
        for j, v in enumerate(actual):
            plt.text(j - width/2, v + 0.02, f'{v:.2f}', ha='center')
        for j, v in enumerate(pred[0]):
            plt.text(j + width/2, v + 0.02, f'{v:.2f}', ha='center')
    
    plt.tight_layout()
    plt.show() 