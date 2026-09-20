#!/usr/bin/env python3
"""
5G Network Slicing - LSTM Web Server

This script creates a web server that serves LSTM predictions from vendor data.
It provides API endpoints to be used by the web interface at
http://localhost:8080/slice-demo.html
"""

import os
import numpy as np
import json
import logging
import tensorflow as tf
from flask import Flask, jsonify, request, send_from_directory, render_template
from flask_cors import CORS
import sys
import importlib
import pandas as pd
from datetime import datetime

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

# Load vendor data
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
        
        return X, y, data.columns.tolist()
    
    except Exception as e:
        logger.error(f"Error loading vendor data: {e}")
        return None, None, None

# Initialize Flask app
app = Flask(__name__, static_folder='web', static_url_path='')
CORS(app)  # Enable CORS for all routes

# Global variables
lstm_predictor = None
vendor_data = None
vendor_data_index = 0
output_dir = f"results/lstm_web_server_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

# Initialize LSTM predictor and load vendor data
def initialize(model_path, vendor_data_path):
    global lstm_predictor, vendor_data, output_dir
    
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    try:
        # Load LSTM model
        if model_path and os.path.exists(model_path):
            logger.info(f"Loading LSTM model from {model_path}")
            lstm_predictor = SliceAllocationPredictor(model_path=model_path, skip_training=True)
        else:
            logger.warning("No valid model path provided, using synthetic model")
            lstm_predictor = SliceAllocationPredictor(skip_training=False)
        
        # Load vendor data
        if vendor_data_path and os.path.exists(vendor_data_path):
            logger.info(f"Loading vendor data from {vendor_data_path}")
            vendor_data = load_vendor_data(vendor_data_path)
        else:
            logger.warning("No valid vendor data path provided")
    
    except Exception as e:
        logger.error(f"Error initializing: {e}")

# API Routes
@app.route('/')
def index():
    return send_from_directory('web', 'index.html')

@app.route('/api/lstm-prediction')
def get_lstm_prediction():
    """API endpoint to get LSTM prediction from vendor data"""
    global vendor_data_index
    
    if lstm_predictor is None or vendor_data is None or vendor_data[0] is None:
        return jsonify({
            'error': 'LSTM predictor or vendor data not initialized',
            'success': False
        })
    
    try:
        # Get vendor data
        X_vendor, y_vendor, columns = vendor_data
        
        # Get sequence from vendor data
        if len(X_vendor) == 0:
            return jsonify({
                'error': 'No vendor data sequences available',
                'success': False
            })
        
        # Use the next sequence
        idx = vendor_data_index % len(X_vendor)
        vendor_sequence = X_vendor[idx]
        
        # Make prediction
        prediction = lstm_predictor.predict(np.expand_dims(vendor_sequence, axis=0))
        
        # Get multi-step forecast if available
        forecast = None
        try:
            if hasattr(lstm_predictor, 'predict') and callable(getattr(lstm_predictor, 'predict')):
                import inspect
                params = inspect.signature(lstm_predictor.predict).parameters
                if 'return_all_steps' in params:
                    forecast = lstm_predictor.predict(np.expand_dims(vendor_sequence, axis=0), return_all_steps=True)
                    if isinstance(forecast, np.ndarray) and forecast.ndim > 1:
                        forecast = forecast[0].tolist()  # Remove batch dimension and convert to list
                else:
                    # Single step prediction - create a synthetic forecast
                    single_step = prediction[0]
                    forecast = [single_step.tolist() for _ in range(5)]  # 5-step forecast
        except Exception as e:
            logger.error(f"Error generating forecast: {e}")
            # Create synthetic forecast
            single_step = prediction[0]
            forecast = [single_step.tolist() for _ in range(5)]  # 5-step forecast
        
        # Get actual future value if available
        actual = None
        if idx < len(y_vendor):
            actual = y_vendor[idx].tolist()
        
        # Increment index for next request
        vendor_data_index += 1
        
        # Prepare response
        response = {
            'sequence': vendor_sequence.tolist(),
            'prediction': prediction[0].tolist(),
            'forecast': forecast,
            'actual': actual,
            'sequence_id': idx,
            'success': True,
            'slice_names': ['eMBB', 'URLLC', 'mMTC']
        }
        
        return jsonify(response)
    
    except Exception as e:
        logger.error(f"Error generating prediction: {e}")
        return jsonify({
            'error': str(e),
            'success': False
        })

@app.route('/api/reset-index')
def reset_index():
    """Reset the vendor data index"""
    global vendor_data_index
    vendor_data_index = 0
    return jsonify({'success': True})

# Web Server
if __name__ == '__main__':
    import argparse
    
    # Parse arguments
    parser = argparse.ArgumentParser(description='5G Network Slicing LSTM Web Server')
    parser.add_argument('--port', type=int, default=8081, help='Port to run the server on')
    parser.add_argument('--model-path', type=str, default='models/lstm_single/best_model.h5',
                        help='Path to trained LSTM model')
    parser.add_argument('--vendor-data', type=str, default='data/training/training_data.csv',
                        help='Path to vendor data CSV')
    
    args = parser.parse_args()
    
    # Initialize
    initialize(args.model_path, args.vendor_data)
    
    # Run server
    logger.info(f"Starting server on port {args.port}")
    app.run(host='0.0.0.0', port=args.port, debug=True) 