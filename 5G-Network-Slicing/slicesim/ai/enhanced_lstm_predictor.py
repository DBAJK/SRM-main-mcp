#!/usr/bin/env python3
"""
Enhanced LSTM-based Network Slice Allocation Predictor with Autoregressive Capabilities

This module provides an improved LSTM-based deep learning model for predicting
optimal slice resource allocation based on network conditions, with multi-step
autoregressive forecasting capabilities.

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
from tensorflow.keras.models import Sequential, Model, load_model
from tensorflow.keras.layers import Dense, LSTM, Dropout, BatchNormalization, Input, LSTMCell
from tensorflow.keras.optimizers import Adam
from tensorflow.keras.callbacks import EarlyStopping, ModelCheckpoint

# Import the original LSTM predictor as the base class
from slicesim.ai.lstm_predictor import SliceAllocationPredictor

class AutoregressiveLSTMPredictor(SliceAllocationPredictor):
    """Enhanced LSTM predictor with autoregressive capabilities for multi-step forecasting
    
    3GPP Compliance:
    - SST=1: eMBB (Enhanced Mobile Broadband)
    - SST=2: URLLC (Ultra Reliable Low Latency Communications)
    - SST=3: mMTC (Massive Machine Type Communications)
    
    Where SST is Slice/Service Type as defined in 3GPP TS 23.501
    """
    
    def __init__(self, input_dim=11, sequence_length=10, out_steps=3, model_path=None, skip_training=False):
        """Initialize the enhanced LSTM predictor
        
        Args:
            input_dim (int): Dimension of input features
            sequence_length (int): Length of input sequence
            out_steps (int): Number of future steps to predict
            model_path (str): Path to load the model from
            skip_training (bool): Whether to skip training during initialization
        """
        # Set out_steps before calling parent __init__
        self.out_steps = out_steps
        self.input_dim = input_dim
        self.sequence_length = sequence_length
        self.model_path = model_path
        self.training_history = None
        
        # Initialize the 3GPP standard slice types and QoS parameters from parent class
        # but skip the automatic training
        SliceAllocationPredictor.__init__(self, input_dim, sequence_length, model_path, skip_training=True)
        
        # Override the model with our autoregressive model
        if model_path and os.path.exists(model_path):
            try:
                self.model = load_model(model_path)
                print(f"Loaded autoregressive LSTM model from {model_path}")
            except Exception as e:
                print(f"Error loading model: {e}")
                self.model = self._build_autoregressive_model()
        else:
            self.model = self._build_autoregressive_model()
            
            # If no pre-trained model and not skipping training, train on synthetic data
            if not skip_training:
                print("Training autoregressive LSTM predictor on synthetic data...")
                X_train, y_train, X_val, y_val = self._generate_training_data(15000)
                self.training_history = self.train(X_train, y_train, epochs=150, batch_size=64, validation_data=(X_val, y_val))
                val_loss = self.training_history.history['val_loss'][-1]
                val_mae = self.training_history.history['val_mae'][-1]
                print(f"Training completed. Validation Loss: {val_loss:.4f}, Validation MAE: {val_mae:.4f}")
    
    def _build_autoregressive_model(self):
        """Build an autoregressive LSTM model for multi-step prediction
        
        Returns:
            keras.Model: Compiled autoregressive LSTM model
        """
        # Print model architecture
        print("Autoregressive LSTM Predictor Model Architecture:")
        
        # Create input layer
        inputs = Input(shape=(self.sequence_length, self.input_dim))
        
        # LSTM encoder
        x = LSTM(128, return_sequences=True, activation='tanh')(inputs)
        x = BatchNormalization()(x)
        x = Dropout(0.3)(x)
        
        # Second LSTM layer to extract features
        x = LSTM(64, return_sequences=False, activation='tanh')(x)
        x = BatchNormalization()(x)
        x = Dropout(0.3)(x)
        
        # Dense hidden layer - Match the dimension with the LSTM cell (64)
        features = Dense(64, activation='relu')(x)
        
        # Create LSTM cell for autoregressive prediction
        lstm_cell = LSTMCell(64)
        
        # Output layer for a single step
        dense = Dense(3, activation='softmax')
        
        # Implement the autoregressive prediction loop
        # This is based on the Context7 example
        
        # Initialize state and first prediction
        states = [tf.zeros([tf.shape(features)[0], 64]), tf.zeros([tf.shape(features)[0], 64])]
        next_input = features
        predictions = []
        
        # Autoregressive loop for multi-step prediction
        for _ in range(self.out_steps):
            # Get next prediction and state
            next_input, states = lstm_cell(next_input, states)
            prediction = dense(next_input)
            predictions.append(prediction)
        
        # Stack predictions along time axis
        outputs = tf.stack(predictions, axis=1)
        
        # Create model
        model = Model(inputs=inputs, outputs=outputs)
        
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
        """Generate synthetic training data for autoregressive model
        
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
        # For autoregressive model, we need multi-step outputs
        y = np.zeros((num_samples, self.out_steps, 3))  # 3 slice types for each step
        
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
            
            # Create input sequence with temporal coherence
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
                
                # Generate features based on scenario type (same as original)
                # This is simplified - in the real implementation, copy the full logic from the original
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
            
            # Generate optimal allocations for future steps (target)
            # For autoregressive model, we need multi-step outputs
            for step in range(self.out_steps):
                # Calculate future time based on last input step
                future_time_progression = (self.sequence_length + step) * 0.01
                future_time_of_day = (time_of_day_start + future_time_progression) % 1.0
                future_day_of_week = (day_of_week_start + (time_of_day_start + future_time_progression) // 1.0) % 1.0
                
                # Extract important features from last sequence step
                final_state = X[i, -1]
                final_traffic_load = final_state[0]
                final_utilization = final_state[6:9]
                
                # Generate target allocation based on scenario type and future time
                if scenario_type == 'baseline':
                    # Balanced allocation with preference based on time and utilization
                    if 0.25 < future_time_of_day < 0.75:  # Day time
                        base_allocation = np.array([0.5, 0.3, 0.2])  # eMBB priority
                    else:
                        base_allocation = np.array([0.3, 0.4, 0.3])  # URLLC and mMTC priority at night
                    
                    # Adjust based on utilization
                    util_factor = final_utilization / (np.sum(final_utilization) + 1e-10)
                    y[i, step] = 0.7 * base_allocation + 0.3 * util_factor
                    
                elif scenario_type == 'dynamic':
                    # More adaptive to utilization
                    util_factor = final_utilization / (np.sum(final_utilization) + 1e-10)
                    
                    # Higher traffic load means more allocation to high utilization slices
                    if final_traffic_load > 1.0:
                        # When congested, allocate more to slices with higher utilization
                        y[i, step] = 0.2 + 0.6 * util_factor
                    else:
                        # With lower load, more balanced allocation
                        y[i, step] = 0.3 + 0.4 * util_factor
                    
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
                    
                    y[i, step] = np.array([embb_alloc, urllc_priority, mmtc_alloc])
                    
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
                    
                    y[i, step] = np.array([embb_alloc, urllc_alloc, mmtc_priority])
                    
                else:  # mixed
                    # Based mostly on utilization with minimum guarantees
                    util_factor = final_utilization / (np.sum(final_utilization) + 1e-10)
                    min_guarantees = np.array([0.2, 0.2, 0.2])
                    remaining = 0.4
                    
                    y[i, step] = min_guarantees + remaining * util_factor
                
                # Normalize to ensure sum is exactly 1
                y[i, step] = y[i, step] / np.sum(y[i, step])
                
                # Add small noise to create more diversity in targets
                noise = np.random.normal(0, 0.02, 3)
                y[i, step] = y[i, step] + noise
                
                # Clip to ensure allocations are at least 10%
                y[i, step] = np.clip(y[i, step], 0.1, 0.8)
                
                # Normalize again to ensure sum is exactly 1
                y[i, step] = y[i, step] / np.sum(y[i, step])
        
        # Split into training and validation sets (80/20)
        split_idx = int(0.8 * num_samples)
        X_train, X_val = X[:split_idx], X[split_idx:]
        y_train, y_val = y[:split_idx], y[split_idx:]
        
        print(f"Generated {len(X_train)} training samples and {len(X_val)} validation samples")
        print(f"Input shape: {X_train.shape}, Output shape: {y_train.shape}")
        
        return X_train, y_train, X_val, y_val
    
    def train(self, X, y, epochs=150, batch_size=64, validation_data=None, checkpoint_dir=None):
        """Train the autoregressive LSTM model
        
        Args:
            X (numpy.ndarray): Input data with shape (num_samples, sequence_length, input_dim)
            y (numpy.ndarray): Target data with shape (num_samples, out_steps, 3)
            epochs (int): Number of training epochs
            batch_size (int): Batch size
            validation_data (tuple): Validation data (X_val, y_val)
            checkpoint_dir (str): Directory to save model checkpoints
            
        Returns:
            keras.callbacks.History: Training history
        """
        # Print shapes for debugging
        print(f"Input shape: {X.shape}, Output shape: {y.shape}")
        
        # Create callbacks
        callbacks = [
            EarlyStopping(
                monitor='val_loss',
                patience=15,
                restore_best_weights=True
            )
        ]
        
        # Add ModelCheckpoint callback if checkpoint_dir is provided
        if checkpoint_dir:
            os.makedirs(checkpoint_dir, exist_ok=True)
            checkpoint_path = os.path.join(
                checkpoint_dir,
                f"autoregressive_lstm_model_{datetime.now().strftime('%Y%m%d_%H%M%S')}.h5"
            )
            callbacks.append(
                ModelCheckpoint(
                    filepath=checkpoint_path,
                    monitor='val_loss',
                    save_best_only=True,
                    save_weights_only=False,
                    verbose=1
                )
            )
        
        # Train model
        history = self.model.fit(
            X, y,
            epochs=epochs,
            batch_size=batch_size,
            validation_data=validation_data,
            callbacks=callbacks,
            verbose=1
        )
        
        return history
    
    def predict(self, input_data, return_all_steps=False):
        """Make predictions using the autoregressive LSTM model
        
        Args:
            input_data (numpy.ndarray): Input data with shape (sequence_length, input_dim)
                                       or (batch_size, sequence_length, input_dim)
            return_all_steps (bool): Whether to return all predicted steps
            
        Returns:
            numpy.ndarray: Predicted slice allocation(s)
        """
        # Ensure input has batch dimension
        if input_data.ndim == 2:
            input_data = np.expand_dims(input_data, axis=0)
        
        # Make prediction
        prediction = self.model.predict(input_data, verbose=0)
        
        # Return either all steps or just the first step
        if return_all_steps:
            return prediction[0]  # Shape: (out_steps, 3)
        else:
            return prediction[0, 0]  # Shape: (3,)
    
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
            path = self.model_path or f"autoregressive_lstm_model_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
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
        
        plt.subplot(1, 2, 1)
        plt.plot(history.history['loss'], label='Training Loss')
        if 'val_loss' in history.history:
            plt.plot(history.history['val_loss'], label='Validation Loss')
        plt.title('Loss')
        plt.xlabel('Epoch')
        plt.ylabel('Loss')
        plt.legend()
        
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
    
    def plot_predictions(self, input_sequence, actual_future=None):
        """Plot predictions against actual future values
        
        Args:
            input_sequence (numpy.ndarray): Input sequence
            actual_future (numpy.ndarray, optional): Actual future values
        """
        # Get predictions
        predictions = self.predict(input_sequence, return_all_steps=True)
        
        # Create time steps
        input_steps = np.arange(self.sequence_length)
        future_steps = np.arange(self.sequence_length, self.sequence_length + self.out_steps)
        
        # Plot
        plt.figure(figsize=(12, 6))
        
        # Plot input sequence
        if len(input_sequence.shape) == 3:
            # Batch of sequences, take the first one
            input_sequence = input_sequence[0]
        
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
        
        plt.axvline(x=self.sequence_length-0.5, color='k', linestyle='-')
        plt.text(self.sequence_length-0.5, 0.5, 'Prediction', rotation=90)
        
        plt.title('Multi-step Slice Allocation Prediction')
        plt.xlabel('Time Step')
        plt.ylabel('Allocation Ratio')
        plt.legend()
        plt.grid(True)
        
        plt.tight_layout()
        plt.show()


# Example usage
if __name__ == "__main__":
    # Create autoregressive LSTM predictor
    predictor = AutoregressiveLSTMPredictor(input_dim=11, sequence_length=10, out_steps=5)
    
    # Generate sample data
    X_train, y_train, X_val, y_val = predictor._generate_training_data(1000)
    
    # Train model
    history = predictor.train(X_train, y_train, epochs=50, batch_size=32, validation_data=(X_val, y_val))
    
    # Plot training history
    predictor.plot_training_history(history)
    
    # Make predictions
    sample_input = X_val[0]
    sample_output = y_val[0]
    predictor.plot_predictions(sample_input, sample_output)
    
    # Save model
    predictor.save("models/autoregressive_lstm_model.h5") 