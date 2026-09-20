#!/usr/bin/env python3
"""
5G Network Slice Training and Analysis

This script trains the AI models on large datasets and performs comprehensive
slice allocation analysis across different scenarios.
"""

import os
import sys
import argparse
import time
import numpy as np
from datetime import datetime
import matplotlib.pyplot as plt

# Add the parent directory to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import required modules
from slicesim.ai.lstm_predictor import SliceAllocationPredictor
from slicesim.ai.dqn_classifier import TrafficClassifier
from slice_analyzer import SliceAnalyzer

def train_models(args):
    """Train the AI models on large datasets
    
    Args:
        args: Command line arguments
        
    Returns:
        tuple: (lstm_model, dqn_model)
    """
    print("="*80)
    print(f"TRAINING AI MODELS ON {args.samples} SAMPLES")
    print("="*80)
    
    # Create models directory if it doesn't exist
    os.makedirs(args.models_dir, exist_ok=True)
    
    # Train LSTM predictor
    print("\nTraining LSTM Slice Allocation Predictor...")
    start_time = time.time()
    
    lstm_model_path = os.path.join(args.models_dir, f"lstm_model_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    lstm_model = SliceAllocationPredictor(input_dim=11, sequence_length=10, model_path=None)
    
    # Generate training data
    print(f"Generating {args.samples} samples for LSTM training...")
    X_train, y_train, X_val, y_val = lstm_model._generate_training_data(args.samples)
    
    # Train the model
    print("Training LSTM model...")
    history = lstm_model.train(X_train, y_train, epochs=args.epochs, 
                              batch_size=args.batch_size, validation_data=(X_val, y_val))
    
    # Save the model
    lstm_model.save(lstm_model_path)
    
    lstm_train_time = time.time() - start_time
    print(f"LSTM training completed in {lstm_train_time:.1f} seconds")
    print(f"LSTM model saved to {lstm_model_path}")
    
    # Evaluate LSTM model
    print("\nEvaluating LSTM model...")
    X_test, y_test, _, _ = lstm_model._generate_training_data(1000)  # Generate test data
    loss, mae = lstm_model.evaluate(X_test, y_test)
    print(f"Test Loss: {loss:.4f}, Test MAE: {mae:.4f}")
    
    # Train DQN classifier
    print("\nTraining DQN Traffic Classifier...")
    start_time = time.time()
    
    dqn_model_path = os.path.join(args.models_dir, f"dqn_model_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    dqn_model = TrafficClassifier(input_dim=11, output_dim=3, model_path=None)
    
    # Generate training data
    print(f"Generating {args.samples} samples for DQN training...")
    X_train, y_train, X_val, y_val = dqn_model._generate_training_data(args.samples)
    
    # Train the model
    print("Training DQN model...")
    history = dqn_model.train(X_train, y_train, epochs=args.epochs, 
                             batch_size=args.batch_size, validation_data=(X_val, y_val))
    
    # Save the model
    dqn_model.save(dqn_model_path)
    
    dqn_train_time = time.time() - start_time
    print(f"DQN training completed in {dqn_train_time:.1f} seconds")
    print(f"DQN model saved to {dqn_model_path}")
    
    # Evaluate DQN model
    print("\nEvaluating DQN model...")
    X_test, y_test, _, _ = dqn_model._generate_training_data(1000)  # Generate test data
    loss, accuracy = dqn_model.evaluate(X_test, y_test)
    print(f"Test Loss: {loss:.4f}, Test Accuracy: {accuracy:.4f}")
    
    # Plot training history
    if args.plot:
        print("\nPlotting training history...")
        
        # Create plots directory
        plots_dir = os.path.join(args.save_dir, "training_plots")
        os.makedirs(plots_dir, exist_ok=True)
        
        # LSTM training history
        plt.figure(figsize=(12, 5))
        
        plt.subplot(1, 2, 1)
        plt.plot(history.history['loss'], label='Training Loss')
        plt.plot(history.history['val_loss'], label='Validation Loss')
        plt.title('LSTM Loss')
        plt.xlabel('Epoch')
        plt.ylabel('Loss')
        plt.legend()
        
        plt.subplot(1, 2, 2)
        plt.plot(history.history['mae'], label='Training MAE')
        plt.plot(history.history['val_mae'], label='Validation MAE')
        plt.title('LSTM Mean Absolute Error')
        plt.xlabel('Epoch')
        plt.ylabel('MAE')
        plt.legend()
        
        plt.tight_layout()
        lstm_plot_path = os.path.join(plots_dir, f"lstm_training_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
        plt.savefig(lstm_plot_path)
        print(f"LSTM training plot saved to {lstm_plot_path}")
        
        # DQN training history
        plt.figure(figsize=(12, 5))
        
        plt.subplot(1, 2, 1)
        plt.plot(history.history['loss'], label='Training Loss')
        plt.plot(history.history['val_loss'], label='Validation Loss')
        plt.title('DQN Loss')
        plt.xlabel('Epoch')
        plt.ylabel('Loss')
        plt.legend()
        
        plt.subplot(1, 2, 2)
        plt.plot(history.history['accuracy'], label='Training Accuracy')
        plt.plot(history.history['val_accuracy'], label='Validation Accuracy')
        plt.title('DQN Accuracy')
        plt.xlabel('Epoch')
        plt.ylabel('Accuracy')
        plt.legend()
        
        plt.tight_layout()
        dqn_plot_path = os.path.join(plots_dir, f"dqn_training_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
        plt.savefig(dqn_plot_path)
        print(f"DQN training plot saved to {dqn_plot_path}")
    
    return lstm_model, dqn_model

def analyze_slices(args, lstm_model=None, dqn_model=None):
    """Analyze slice allocations using the trained models
    
    Args:
        args: Command line arguments
        lstm_model: Trained LSTM model (optional)
        dqn_model: Trained DQN model (optional)
    """
    print("\n" + "="*80)
    print("ANALYZING SLICE ALLOCATIONS")
    print("="*80)
    
    # Create analyzer
    analyzer = SliceAnalyzer(results_dir=args.results_dir)
    
    # Create results directory if it doesn't exist
    os.makedirs(args.save_dir, exist_ok=True)
    
    # Analyze scenarios
    if args.scenario == 'all':
        print("\nAnalyzing all scenarios...")
        scenarios = ['baseline', 'dynamic', 'emergency', 'smart_city']
        
        # Analyze each scenario
        for scenario in scenarios:
            print(f"\nAnalyzing {scenario} scenario...")
            analysis = analyzer.analyze_slice_allocation(scenario, args.time)
            
            # Save visualization
            save_path = os.path.join(args.save_dir, f"{scenario}_analysis.png")
            analyzer.visualize_analysis(analysis, save_path)
            print(f"Analysis visualization saved to {save_path}")
        
        # Create comparison visualization
        print("\nCreating scenario comparison...")
        analyzer.compare_scenarios(save_dir=args.save_dir)
        print(f"Scenario comparison saved to {args.save_dir}")
    else:
        print(f"\nAnalyzing {args.scenario} scenario at time point {args.time}...")
        analysis = analyzer.analyze_slice_allocation(args.scenario, args.time)
        
        # Save visualization
        save_path = os.path.join(args.save_dir, f"{args.scenario}_analysis.png")
        analyzer.visualize_analysis(analysis, save_path)
        print(f"Analysis visualization saved to {save_path}")
        
        # Print detailed analysis if requested
        if args.detailed:
            print("\n" + "="*80)
            print(f"DETAILED SLICE ALLOCATION ANALYSIS FOR {args.scenario.upper()} SCENARIO")
            print("="*80)
            
            print(f"\nScenario Context: {analysis['explanations']['scenario']}")
            print(f"Traffic Analysis: {analysis['explanations']['traffic']}")
            print(f"Time Pattern: {analysis['explanations']['time']}")
            
            print("\nSlice Utilization:")
            for slice_type, explanation in analysis['explanations']['slices'].items():
                print(f"  - {explanation}")
            
            print(f"\nClient Distribution: {analysis['explanations']['clients']}")
            
            print("\nAI vs Traditional Allocation:")
            for slice_type in ['eMBB', 'URLLC', 'mMTC']:
                trad = analysis['traditional_allocation'][slice_type]
                ai = analysis['ai_allocation'][slice_type]
                diff = (ai - trad) * 100  # percentage points
                direction = "increase" if diff > 0 else "decrease"
                print(f"  - {slice_type}: {trad:.2f} → {ai:.2f} ({abs(diff):.1f}% {direction})")
            
            print("\nAI Decision Summary:")
            print(f"  {analysis['explanations']['decision']}")
            
            print("\nTraffic Classification Results:")
            dominant_class = analysis['dqn_classification']['class']
            probs = analysis['dqn_classification']['probabilities']
            print(f"  - Dominant traffic pattern: {dominant_class}")
            print(f"  - Classification confidence: {probs[dominant_class]:.2f}")
    
    print("\nSlice allocation analysis completed successfully!")

def main():
    """Main function"""
    parser = argparse.ArgumentParser(description="5G Network Slice Training and Analysis")
    parser.add_argument('--train', action='store_true',
                      help='Train AI models on large datasets')
    parser.add_argument('--analyze', action='store_true',
                      help='Analyze slice allocations')
    parser.add_argument('--samples', type=int, default=15000,
                      help='Number of samples for training')
    parser.add_argument('--epochs', type=int, default=150,
                      help='Number of training epochs')
    parser.add_argument('--batch-size', type=int, default=64,
                      help='Batch size for training')
    parser.add_argument('--scenario', type=str, default='all',
                      choices=['all', 'baseline', 'dynamic', 'emergency', 'smart_city'],
                      help='Scenario to analyze')
    parser.add_argument('--time', type=int, default=15,
                      help='Time point to analyze')
    parser.add_argument('--results-dir', type=str, default='results',
                      help='Directory containing simulation results')
    parser.add_argument('--models-dir', type=str, default='models',
                      help='Directory to save trained models')
    parser.add_argument('--save-dir', type=str, default='analysis_results',
                      help='Directory to save analysis results')
    parser.add_argument('--plot', action='store_true',
                      help='Plot training history')
    parser.add_argument('--detailed', action='store_true',
                      help='Show detailed metrics and explanations')
    
    args = parser.parse_args()
    
    # Default behavior if no action specified
    if not (args.train or args.analyze):
        args.train = True
        args.analyze = True
    
    # Train models if requested
    lstm_model = None
    dqn_model = None
    if args.train:
        lstm_model, dqn_model = train_models(args)
    
    # Analyze slice allocations if requested
    if args.analyze:
        analyze_slices(args, lstm_model, dqn_model)

if __name__ == "__main__":
    main() 