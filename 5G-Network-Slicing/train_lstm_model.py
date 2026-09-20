#!/usr/bin/env python3
"""
5G Network Slicing LSTM Model Training

This script trains an autoregressive LSTM model for 5G network slicing
using the generated training data. The model predicts optimal slice
allocations based on current network state and historical data.

The script includes:
- Data loading and preprocessing
- Sequence creation for time-series prediction
- LSTM model architecture with autoregressive capabilities
- Training with validation
- Model evaluation
- Saving the trained model
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import tensorflow as tf
from tensorflow.keras.models import Sequential, Model
from tensorflow.keras.layers import LSTM, Dense, Input, Dropout, Concatenate
from tensorflow.keras.callbacks import EarlyStopping, ModelCheckpoint, ReduceLROnPlateau
from tensorflow.keras.optimizers import Adam
import argparse
import logging
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import MinMaxScaler
import json

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class LSTMModelTrainer:
    """Trainer for 5G network slicing LSTM model"""
    
    def __init__(self, args):
        """Initialize the model trainer
        
        Args:
            args: Command line arguments
        """
        self.args = args
        self.input_dir = args.input_dir
        self.output_dir = args.output_dir
        self.sequence_length = args.sequence_length
        self.batch_size = args.batch_size
        self.epochs = args.epochs
        self.out_steps = args.out_steps
        
        # Create output directory if it doesn't exist
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
        
        # Initialize TensorFlow settings
        self._setup_tensorflow()
        
        # Initialize data structures
        self.X = None
        self.y = None
        self.df = None
        self.scalers = {}
        
        logger.info(f"LSTM model trainer initialized with sequence length {self.sequence_length}")
    
    def _setup_tensorflow(self):
        """Configure TensorFlow settings"""
        # Check for GPU
        gpus = tf.config.list_physical_devices('GPU')
        if gpus:
            logger.info(f"Using GPU: {gpus}")
            # Prevent TensorFlow from allocating all GPU memory
            for gpu in gpus:
                tf.config.experimental.set_memory_growth(gpu, True)
        else:
            logger.info("No GPU found, using CPU")
        
        # Set random seeds for reproducibility
        tf.random.set_seed(42)
        np.random.seed(42)
    
    def load_data(self):
        """Load training data from input directory"""
        logger.info(f"Loading data from {self.input_dir}")
        
        # Check if we have numpy files
        x_path = os.path.join(self.input_dir, 'X_train.npy')
        y_path = os.path.join(self.input_dir, 'y_train.npy')
        
        if os.path.exists(x_path) and os.path.exists(y_path):
            # Load from numpy files
            self.X = np.load(x_path)
            self.y = np.load(y_path)
            logger.info(f"Loaded data from numpy files: X shape {self.X.shape}, y shape {self.y.shape}")
        else:
            # Try loading from CSV
            csv_path = os.path.join(self.input_dir, 'training_data.csv')
            if os.path.exists(csv_path):
                self.df = pd.read_csv(csv_path)
                logger.info(f"Loaded data from CSV: {len(self.df)} samples")
                
                # Extract features and targets
                feature_cols = [
                    'traffic_load', 'hour_of_day', 'day_of_week',
                    'embb_allocation', 'urllc_allocation', 'mmtc_allocation',
                    'embb_utilization', 'urllc_utilization', 'mmtc_utilization',
                    'client_count', 'bs_count'
                ]
                
                target_cols = ['optimal_embb', 'optimal_urllc', 'optimal_mmtc']
                
                self.X = self.df[feature_cols].values
                self.y = self.df[target_cols].values
            else:
                raise FileNotFoundError(f"No training data found in {self.input_dir}")
        
        logger.info(f"Data loaded: X shape {self.X.shape}, y shape {self.y.shape}")
    
    def preprocess_data(self):
        """Preprocess the data for LSTM training"""
        logger.info("Preprocessing data...")
        
        # Scale features
        self.scalers['X'] = MinMaxScaler()
        self.X_scaled = self.scalers['X'].fit_transform(self.X)
        
        # We don't scale y because it's already between 0 and 1 (allocations sum to 1)
        self.y_scaled = self.y
        
        # Create sequences for LSTM
        X_seq, y_seq = self._create_sequences()
        
        # Split into training and validation sets
        self.X_train, self.X_val, self.y_train, self.y_val = train_test_split(
            X_seq, y_seq, test_size=0.2, random_state=42)
        
        logger.info(f"Training data shape: {self.X_train.shape}, {self.y_train.shape}")
        logger.info(f"Validation data shape: {self.X_val.shape}, {self.y_val.shape}")
    
    def _create_sequences(self):
        """Create sequences for LSTM training
        
        Returns:
            tuple: X_seq, y_seq arrays
        """
        X_seq = []
        y_seq = []
        
        # For each possible sequence
        for i in range(len(self.X_scaled) - self.sequence_length - self.out_steps + 1):
            # Input sequence
            X_seq.append(self.X_scaled[i:i+self.sequence_length])
            
            # Output sequence (next out_steps allocations)
            if self.out_steps > 1:
                y_seq.append(self.y_scaled[i+self.sequence_length:i+self.sequence_length+self.out_steps])
            else:
                y_seq.append(self.y_scaled[i+self.sequence_length])
        
        return np.array(X_seq), np.array(y_seq)
    
    def build_model(self):
        """Build the LSTM model architecture
        
        For single-step prediction, use a simple LSTM model.
        For multi-step prediction, use an autoregressive LSTM model.
        """
        input_dim = self.X_train.shape[2]  # Number of features
        output_dim = self.y_train.shape[-1]  # Number of output values (3 slice allocations)
        
        if self.out_steps == 1:
            # Single-step prediction model
            logger.info("Building single-step LSTM model")
            
            model = Sequential([
                LSTM(64, activation='tanh', return_sequences=True, 
                     input_shape=(self.sequence_length, input_dim)),
                Dropout(0.2),
                LSTM(32, activation='tanh'),
                Dropout(0.2),
                Dense(output_dim, activation='softmax')  # Softmax ensures allocations sum to 1
            ])
            
            model.compile(
                optimizer=Adam(learning_rate=0.001),
                loss='mean_squared_error'
            )
        else:
            # Multi-step autoregressive LSTM model
            logger.info(f"Building multi-step autoregressive LSTM model with {self.out_steps} output steps")
            
            # Encoder (processes the input sequence)
            encoder_inputs = Input(shape=(self.sequence_length, input_dim))
            encoder = LSTM(64, activation='tanh', return_sequences=True)(encoder_inputs)
            encoder = Dropout(0.2)(encoder)
            encoder = LSTM(32, activation='tanh')(encoder)
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
                    decoder_output = Dense(output_dim, activation='softmax')(decoder_state)
                else:
                    # For subsequent steps, use the previous output as input
                    # Concatenate with encoder state
                    combined = Concatenate()([decoder_state, decoder_outputs[-1]])
                    decoder_output = Dense(16, activation='relu')(combined)
                    decoder_output = Dense(output_dim, activation='softmax')(decoder_output)
                
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
                loss='mean_squared_error'
            )
        
        # Print model summary
        model.summary()
        self.model = model
        
        # Save model architecture
        with open(os.path.join(self.output_dir, 'model_architecture.json'), 'w') as f:
            f.write(model.to_json())
        
        return model
    
    def train_model(self):
        """Train the LSTM model"""
        logger.info(f"Training model for {self.epochs} epochs with batch size {self.batch_size}")
        
        # Callbacks
        callbacks = [
            EarlyStopping(
                monitor='val_loss',
                patience=10,
                restore_best_weights=True
            ),
            ModelCheckpoint(
                filepath=os.path.join(self.output_dir, 'best_model.h5'),
                monitor='val_loss',
                save_best_only=True
            ),
            ReduceLROnPlateau(
                monitor='val_loss',
                factor=0.5,
                patience=5,
                min_lr=0.0001
            )
        ]
        
        # Train the model
        history = self.model.fit(
            self.X_train,
            self.y_train,
            epochs=self.epochs,
            batch_size=self.batch_size,
            validation_data=(self.X_val, self.y_val),
            callbacks=callbacks,
            verbose=1
        )
        
        # Save training history
        history_dict = history.history
        with open(os.path.join(self.output_dir, 'training_history.json'), 'w') as f:
            # Convert numpy values to Python native types for JSON serialization
            for key in history_dict:
                history_dict[key] = [float(x) for x in history_dict[key]]
            json.dump(history_dict, f)
        
        # Save the final model
        self.model.save(os.path.join(self.output_dir, 'final_model.h5'))
        
        # Save scalers
        np.save(os.path.join(self.output_dir, 'X_scaler.npy'), 
                [self.scalers['X'].data_min_, self.scalers['X'].data_max_])
        
        # Plot training history
        self._plot_training_history(history)
        
        logger.info("Model training completed")
        
        return history
    
    def evaluate_model(self):
        """Evaluate the trained model"""
        logger.info("Evaluating model...")
        
        # Evaluate on validation set
        val_loss = self.model.evaluate(self.X_val, self.y_val)
        logger.info(f"Validation loss: {val_loss}")
        
        # Make predictions on validation set
        y_pred = self.model.predict(self.X_val)
        
        # For multi-step predictions, take the first step for evaluation
        if len(y_pred.shape) > 2:
            y_pred_first = y_pred[:, 0, :]
            y_val_first = self.y_val[:, 0, :]
        else:
            y_pred_first = y_pred
            y_val_first = self.y_val
        
        # Calculate mean absolute error for each slice
        mae = np.mean(np.abs(y_pred_first - y_val_first), axis=0)
        logger.info(f"Mean absolute error: eMBB={mae[0]:.4f}, URLLC={mae[1]:.4f}, mMTC={mae[2]:.4f}")
        
        # Plot predictions vs actual
        self._plot_predictions(y_val_first, y_pred_first)
        
        # Save evaluation metrics
        metrics = {
            'validation_loss': float(val_loss),
            'mae': {
                'embb': float(mae[0]),
                'urllc': float(mae[1]),
                'mmtc': float(mae[2])
            },
            'mean_mae': float(np.mean(mae))
        }
        
        with open(os.path.join(self.output_dir, 'evaluation_metrics.json'), 'w') as f:
            json.dump(metrics, f)
        
        return metrics
    
    def _plot_training_history(self, history):
        """Plot and save training history
        
        Args:
            history: Training history object
        """
        plt.figure(figsize=(12, 4))
        
        # Plot training & validation loss
        plt.subplot(1, 1, 1)
        plt.plot(history.history['loss'], label='Training Loss')
        plt.plot(history.history['val_loss'], label='Validation Loss')
        plt.title('Model Loss')
        plt.ylabel('Loss')
        plt.xlabel('Epoch')
        plt.legend(loc='upper right')
        plt.grid(True)
        
        # Save the plot
        plt.tight_layout()
        plt.savefig(os.path.join(self.output_dir, 'training_history.png'))
        plt.close()
    
    def _plot_predictions(self, y_true, y_pred):
        """Plot and save model predictions vs actual values
        
        Args:
            y_true: True values
            y_pred: Predicted values
        """
        # Create figure with subplots
        fig, axs = plt.subplots(3, 1, figsize=(12, 10))
        fig.suptitle('Model Predictions vs Actual Values', fontsize=16)
        
        slice_types = ['eMBB', 'URLLC', 'mMTC']
        colors = ['#FF6B6B', '#45B7D1', '#FFBE0B']
        
        # Plot each slice type
        for i, (slice_type, color) in enumerate(zip(slice_types, colors)):
            # Get sample indices for plotting (max 100 points)
            indices = np.linspace(0, len(y_true) - 1, min(100, len(y_true))).astype(int)
            
            # Plot actual vs predicted
            axs[i].plot(indices, y_true[indices, i], 'o-', label=f'Actual {slice_type}', color=color)
            axs[i].plot(indices, y_pred[indices, i], 's--', label=f'Predicted {slice_type}', 
                      color=color, alpha=0.7)
            
            axs[i].set_title(f'{slice_type} Allocation')
            axs[i].set_xlabel('Sample Index')
            axs[i].set_ylabel('Allocation')
            axs[i].legend()
            axs[i].grid(True)
        
        # Save the plot
        plt.tight_layout()
        plt.savefig(os.path.join(self.output_dir, 'prediction_comparison.png'))
        plt.close()
        
        # Create a scatter plot of predicted vs actual
        fig, axs = plt.subplots(1, 3, figsize=(15, 5))
        fig.suptitle('Predicted vs Actual Allocations', fontsize=16)
        
        for i, (slice_type, color) in enumerate(zip(slice_types, colors)):
            axs[i].scatter(y_true[:, i], y_pred[:, i], alpha=0.5, color=color)
            
            # Add perfect prediction line
            min_val = min(np.min(y_true[:, i]), np.min(y_pred[:, i]))
            max_val = max(np.max(y_true[:, i]), np.max(y_pred[:, i]))
            axs[i].plot([min_val, max_val], [min_val, max_val], 'k--')
            
            axs[i].set_title(f'{slice_type}')
            axs[i].set_xlabel('Actual')
            axs[i].set_ylabel('Predicted')
            axs[i].grid(True)
        
        # Save the plot
        plt.tight_layout()
        plt.savefig(os.path.join(self.output_dir, 'prediction_scatter.png'))
        plt.close()


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='5G Network Slicing LSTM Model Training')
    
    parser.add_argument('--input_dir', type=str, default='data/training',
                        help='Directory containing training data')
    
    parser.add_argument('--output_dir', type=str, default='models/lstm',
                        help='Directory to save model and results')
    
    parser.add_argument('--sequence_length', type=int, default=10,
                        help='Length of input sequence for LSTM')
    
    parser.add_argument('--batch_size', type=int, default=64,
                        help='Training batch size')
    
    parser.add_argument('--epochs', type=int, default=100,
                        help='Maximum number of training epochs')
    
    parser.add_argument('--out_steps', type=int, default=1,
                        help='Number of future steps to predict (1 for single-step, >1 for multi-step)')
    
    return parser.parse_args()


if __name__ == "__main__":
    # Parse command line arguments
    args = parse_args()
    
    # Print TensorFlow version and GPU availability
    logger.info(f"TensorFlow version: {tf.__version__}")
    logger.info(f"GPU available: {len(tf.config.list_physical_devices('GPU')) > 0}")
    
    # Create and run the trainer
    trainer = LSTMModelTrainer(args)
    trainer.load_data()
    trainer.preprocess_data()
    trainer.build_model()
    trainer.train_model()
    metrics = trainer.evaluate_model()
    
    # Print final results
    print("\nTraining completed!")
    print(f"Validation loss: {metrics['validation_loss']:.6f}")
    print(f"Mean absolute error:")
    print(f"  eMBB: {metrics['mae']['embb']:.6f}")
    print(f"  URLLC: {metrics['mae']['urllc']:.6f}")
    print(f"  mMTC: {metrics['mae']['mmtc']:.6f}")
    print(f"  Average: {metrics['mean_mae']:.6f}")
    print(f"\nModel and results saved to: {args.output_dir}") 