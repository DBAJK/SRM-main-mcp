#!/usr/bin/env python3
"""
5G Network Slicing - Model Definitions

This module defines the LSTM model architectures used in the 5G network slicing system.
It includes both single-step and multi-step (autoregressive) models.
"""

import tensorflow as tf
from tensorflow.keras.models import Sequential, Model
from tensorflow.keras.layers import LSTM, Dense, Input, Dropout, Concatenate
from tensorflow.keras.optimizers import Adam
import numpy as np
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SingleStepLSTM:
    """
    Single-step LSTM model for slice allocation prediction.
    
    This model predicts the optimal slice allocation for the next time step
    based on a sequence of past observations.
    """
    
    def __init__(self, input_dim=11, sequence_length=10, lstm_units=64):
        """
        Initialize the single-step LSTM model.
        
        Args:
            input_dim (int): Dimension of input features
            sequence_length (int): Length of input sequence
            lstm_units (int): Number of LSTM units
        """
        self.input_dim = input_dim
        self.sequence_length = sequence_length
        self.lstm_units = lstm_units
        
        # Build model
        self.model = self._build_model()
        logger.info("Single-step LSTM model initialized")
    
    def _build_model(self):
        """
        Build the single-step LSTM model.
        
        Returns:
            tensorflow.keras.Model: Compiled LSTM model
        """
        model = Sequential([
            LSTM(self.lstm_units, activation='tanh', return_sequences=True, 
                 input_shape=(self.sequence_length, self.input_dim)),
            Dropout(0.2),
            LSTM(self.lstm_units // 2, activation='tanh'),
            Dropout(0.2),
            Dense(3, activation='softmax')  # 3 slice types (eMBB, URLLC, mMTC)
        ])
        
        model.compile(
            optimizer=Adam(learning_rate=0.001),
            loss='mean_squared_error',
            metrics=['mae']
        )
        
        model.summary()
        return model
    
    def train(self, X_train, y_train, epochs=50, batch_size=32, validation_data=None, callbacks=None):
        """
        Train the model.
        
        Args:
            X_train (numpy.ndarray): Training input data
            y_train (numpy.ndarray): Training target data
            epochs (int): Number of training epochs
            batch_size (int): Batch size
            validation_data (tuple): Validation data (X_val, y_val)
            callbacks (list): Keras callbacks
        
        Returns:
            keras.callbacks.History: Training history
        """
        logger.info(f"Training single-step LSTM model for {epochs} epochs with batch size {batch_size}")
        history = self.model.fit(
            X_train, y_train,
            epochs=epochs,
            batch_size=batch_size,
            validation_data=validation_data,
            callbacks=callbacks,
            verbose=1
        )
        return history
    
    def predict(self, X):
        """
        Make predictions using the model.
        
        Args:
            X (numpy.ndarray): Input data
        
        Returns:
            numpy.ndarray: Predicted slice allocations
        """
        # Ensure input has correct shape
        if len(X.shape) == 2:
            # Single sample, add batch dimension
            X = np.expand_dims(X, axis=0)
        
        # Make prediction
        prediction = self.model.predict(X, verbose=0)
        
        # Return first prediction if batch size is 1
        if prediction.shape[0] == 1:
            return prediction[0]
        
        return prediction
    
    def evaluate(self, X_test, y_test):
        """
        Evaluate the model.
        
        Args:
            X_test (numpy.ndarray): Test input data
            y_test (numpy.ndarray): Test target data
        
        Returns:
            tuple: (loss, mae)
        """
        loss, mae = self.model.evaluate(X_test, y_test, verbose=0)
        return loss, mae
    
    def save(self, path):
        """
        Save the model.
        
        Args:
            path (str): Path to save the model
        """
        self.model.save(path)
        logger.info(f"Model saved to {path}")
    
    def load(self, path):
        """
        Load the model.
        
        Args:
            path (str): Path to load the model from
        
        Returns:
            bool: Whether the model was loaded successfully
        """
        try:
            self.model = tf.keras.models.load_model(path)
            logger.info(f"Model loaded from {path}")
            return True
        except Exception as e:
            logger.error(f"Error loading model: {e}")
            return False


class AutoregressiveLSTM:
    """
    Autoregressive LSTM model for multi-step slice allocation prediction.
    
    This model predicts the optimal slice allocation for multiple future time steps
    based on a sequence of past observations, using an autoregressive approach.
    """
    
    def __init__(self, input_dim=11, sequence_length=10, out_steps=5, lstm_units=64):
        """
        Initialize the autoregressive LSTM model.
        
        Args:
            input_dim (int): Dimension of input features
            sequence_length (int): Length of input sequence
            out_steps (int): Number of future steps to predict
            lstm_units (int): Number of LSTM units
        """
        self.input_dim = input_dim
        self.sequence_length = sequence_length
        self.out_steps = out_steps
        self.lstm_units = lstm_units
        
        # Build model
        self.model = self._build_model()
        logger.info(f"Autoregressive LSTM model initialized with {out_steps} output steps")
    
    def _build_model(self):
        """
        Build the autoregressive LSTM model.
        
        Returns:
            tensorflow.keras.Model: Compiled LSTM model
        """
        # Encoder (processes the input sequence)
        encoder_inputs = Input(shape=(self.sequence_length, self.input_dim))
        encoder = LSTM(self.lstm_units, activation='tanh', return_sequences=True)(encoder_inputs)
        encoder = Dropout(0.2)(encoder)
        encoder = LSTM(self.lstm_units // 2, activation='tanh')(encoder)
        encoder = Dropout(0.2)(encoder)
        
        # Initialize decoder's output
        decoder_outputs = []
        
        # Initial state for decoder
        decoder_state = encoder
        
        # Autoregressive decoder for each output step
        for i in range(self.out_steps):
            # For the first step, we don't have a previous output
            if i == 0:
                # Use the encoder output directly
                decoder_output = Dense(3, activation='softmax')(decoder_state)
            else:
                # For subsequent steps, use the previous output as input
                # Concatenate with encoder state
                combined = Concatenate()([decoder_state, decoder_outputs[-1]])
                decoder_output = Dense(16, activation='relu')(combined)
                decoder_output = Dense(3, activation='softmax')(decoder_output)
            
            decoder_outputs.append(decoder_output)
        
        # Combine all outputs
        if self.out_steps > 1:
            model_output = tf.stack(decoder_outputs, axis=1)
        else:
            model_output = decoder_outputs[0]
        
        # Create model
        model = Model(inputs=encoder_inputs, outputs=model_output)
        
        model.compile(
            optimizer=Adam(learning_rate=0.001),
            loss='mean_squared_error',
            metrics=['mae']
        )
        
        model.summary()
        return model
    
    def train(self, X_train, y_train, epochs=50, batch_size=32, validation_data=None, callbacks=None):
        """
        Train the model.
        
        Args:
            X_train (numpy.ndarray): Training input data
            y_train (numpy.ndarray): Training target data
            epochs (int): Number of training epochs
            batch_size (int): Batch size
            validation_data (tuple): Validation data (X_val, y_val)
            callbacks (list): Keras callbacks
        
        Returns:
            keras.callbacks.History: Training history
        """
        logger.info(f"Training autoregressive LSTM model for {epochs} epochs with batch size {batch_size}")
        history = self.model.fit(
            X_train, y_train,
            epochs=epochs,
            batch_size=batch_size,
            validation_data=validation_data,
            callbacks=callbacks,
            verbose=1
        )
        return history
    
    def predict(self, X, return_all_steps=False):
        """
        Make predictions using the model.
        
        Args:
            X (numpy.ndarray): Input data
            return_all_steps (bool): Whether to return all predicted steps
        
        Returns:
            numpy.ndarray: Predicted slice allocations
        """
        # Ensure input has correct shape
        if len(X.shape) == 2:
            # Single sample, add batch dimension
            X = np.expand_dims(X, axis=0)
        
        # Make prediction
        prediction = self.model.predict(X, verbose=0)
        
        # Return first prediction if batch size is 1
        if prediction.shape[0] == 1:
            if return_all_steps:
                return prediction[0]  # Return all steps for first sample
            else:
                return prediction[0, 0]  # Return first step for first sample
        
        return prediction
    
    def evaluate(self, X_test, y_test):
        """
        Evaluate the model.
        
        Args:
            X_test (numpy.ndarray): Test input data
            y_test (numpy.ndarray): Test target data
        
        Returns:
            tuple: (loss, mae)
        """
        loss, mae = self.model.evaluate(X_test, y_test, verbose=0)
        return loss, mae
    
    def save(self, path):
        """
        Save the model.
        
        Args:
            path (str): Path to save the model
        """
        self.model.save(path)
        logger.info(f"Model saved to {path}")
    
    def load(self, path):
        """
        Load the model.
        
        Args:
            path (str): Path to load the model from
        
        Returns:
            bool: Whether the model was loaded successfully
        """
        try:
            self.model = tf.keras.models.load_model(path)
            logger.info(f"Model loaded from {path}")
            return True
        except Exception as e:
            logger.error(f"Error loading model: {e}")
            return False


# Factory function to create the appropriate model
def create_model(model_type='single_step', **kwargs):
    """
    Create a model of the specified type.
    
    Args:
        model_type (str): Type of model to create ('single_step' or 'autoregressive')
        **kwargs: Additional arguments to pass to the model constructor
    
    Returns:
        object: Model instance
    """
    if model_type.lower() == 'single_step':
        return SingleStepLSTM(**kwargs)
    elif model_type.lower() in ['autoregressive', 'multi_step']:
        return AutoregressiveLSTM(**kwargs)
    else:
        raise ValueError(f"Unknown model type: {model_type}")


# Example usage
if __name__ == "__main__":
    # Create single-step model
    single_step_model = create_model('single_step', input_dim=11, sequence_length=10)
    
    # Create autoregressive model
    autoregressive_model = create_model('autoregressive', input_dim=11, sequence_length=10, out_steps=5)
    
    # Generate sample data
    X_sample = np.random.random((32, 10, 11))  # (batch_size, sequence_length, input_dim)
    y_single = np.random.random((32, 3))  # (batch_size, 3)
    y_multi = np.random.random((32, 5, 3))  # (batch_size, out_steps, 3)
    
    # Test single-step model
    print("\nTesting single-step model:")
    history_single = single_step_model.train(X_sample, y_single, epochs=2, batch_size=8)
    prediction_single = single_step_model.predict(X_sample[0])
    print(f"Prediction shape: {prediction_single.shape}")
    print(f"Prediction: {prediction_single}")
    
    # Test autoregressive model
    print("\nTesting autoregressive model:")
    history_multi = autoregressive_model.train(X_sample, y_multi, epochs=2, batch_size=8)
    prediction_multi = autoregressive_model.predict(X_sample[0], return_all_steps=True)
    print(f"Prediction shape: {prediction_multi.shape}")
    print(f"First step prediction: {prediction_multi[0]}")
    print(f"Last step prediction: {prediction_multi[-1]}") 