#!/usr/bin/env python3
"""
5G Network Slicing Model Pipeline

This script runs the full pipeline for 5G network slicing model development:
1. Generate synthetic training data
2. Train the LSTM model (both single-step and multi-step)
3. Evaluate model performance
4. Compare models

This provides a complete workflow for developing and testing 5G network
slicing models with different configurations.
"""

import os
import argparse
import logging
import subprocess
import json
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ModelPipeline:
    """Pipeline for 5G network slicing model development"""
    
    def __init__(self, args):
        """Initialize the pipeline
        
        Args:
            args: Command line arguments
        """
        self.args = args
        self.base_dir = args.base_dir
        self.num_samples = args.num_samples
        self.visualize = args.visualize
        self.skip_data_gen = args.skip_data_gen
        self.skip_training = args.skip_training
        
        # Set up directories
        self.data_dir = os.path.join(self.base_dir, 'data')
        self.models_dir = os.path.join(self.base_dir, 'models')
        self.results_dir = os.path.join(self.base_dir, 'results')
        
        # Create directories if they don't exist
        for directory in [self.data_dir, self.models_dir, self.results_dir]:
            if not os.path.exists(directory):
                os.makedirs(directory)
        
        # Set up model configurations
        self.model_configs = [
            {
                'name': 'single_step',
                'sequence_length': 10,
                'out_steps': 1,
                'batch_size': 64,
                'epochs': 50
            },
            {
                'name': 'multi_step_3',
                'sequence_length': 10,
                'out_steps': 3,
                'batch_size': 64,
                'epochs': 50
            },
            {
                'name': 'multi_step_5',
                'sequence_length': 10,
                'out_steps': 5,
                'batch_size': 64,
                'epochs': 50
            }
        ]
        
        logger.info(f"Pipeline initialized with base directory: {self.base_dir}")
    
    def run_pipeline(self):
        """Run the full pipeline"""
        # Step 1: Generate training data
        if not self.skip_data_gen:
            self.generate_training_data()
        else:
            logger.info("Skipping data generation step")
        
        # Step 2: Train models
        if not self.skip_training:
            self.train_models()
        else:
            logger.info("Skipping model training step")
        
        # Step 3: Compare models
        self.compare_models()
        
        logger.info("Pipeline completed successfully")
    
    def generate_training_data(self):
        """Generate synthetic training data"""
        logger.info("Generating training data...")
        
        # Build command
        cmd = [
            'python', 'generate_training_data.py',
            '--num_samples', str(self.num_samples),
            '--output_dir', self.data_dir
        ]
        
        if self.visualize:
            cmd.append('--visualize')
        
        # Run command
        logger.info(f"Running command: {' '.join(cmd)}")
        process = subprocess.run(cmd, check=True, capture_output=True, text=True)
        
        # Log output
        logger.info(process.stdout)
        if process.stderr:
            logger.warning(process.stderr)
        
        logger.info(f"Training data generated and saved to {self.data_dir}")
    
    def train_models(self):
        """Train all model configurations"""
        logger.info("Training models...")
        
        for config in self.model_configs:
            logger.info(f"Training {config['name']} model...")
            
            # Create model directory
            model_dir = os.path.join(self.models_dir, config['name'])
            if not os.path.exists(model_dir):
                os.makedirs(model_dir)
            
            # Build command
            cmd = [
                'python', 'train_lstm_model.py',
                '--input_dir', self.data_dir,
                '--output_dir', model_dir,
                '--sequence_length', str(config['sequence_length']),
                '--batch_size', str(config['batch_size']),
                '--epochs', str(config['epochs']),
                '--out_steps', str(config['out_steps'])
            ]
            
            # Run command
            logger.info(f"Running command: {' '.join(cmd)}")
            process = subprocess.run(cmd, check=True, capture_output=True, text=True)
            
            # Log output
            logger.info(f"Model training completed for {config['name']}")
            
            # Save stdout and stderr to log files
            with open(os.path.join(model_dir, 'training_log.txt'), 'w') as f:
                f.write(process.stdout)
            
            if process.stderr:
                with open(os.path.join(model_dir, 'training_errors.txt'), 'w') as f:
                    f.write(process.stderr)
    
    def compare_models(self):
        """Compare the performance of all trained models"""
        logger.info("Comparing model performance...")
        
        # Create comparison directory
        comparison_dir = os.path.join(self.results_dir, 'model_comparison')
        if not os.path.exists(comparison_dir):
            os.makedirs(comparison_dir)
        
        # Collect metrics for all models
        metrics = {}
        for config in self.model_configs:
            model_name = config['name']
            metrics_file = os.path.join(self.models_dir, model_name, 'evaluation_metrics.json')
            
            if os.path.exists(metrics_file):
                with open(metrics_file, 'r') as f:
                    model_metrics = json.load(f)
                metrics[model_name] = model_metrics
            else:
                logger.warning(f"Metrics file not found for {model_name}")
        
        # Create comparison plots
        if metrics:
            self._create_comparison_plots(metrics, comparison_dir)
            
            # Save comparison metrics to file
            with open(os.path.join(comparison_dir, 'comparison_metrics.json'), 'w') as f:
                json.dump(metrics, f)
            
            logger.info(f"Model comparison completed and saved to {comparison_dir}")
        else:
            logger.warning("No metrics found for comparison")
    
    def _create_comparison_plots(self, metrics, output_dir):
        """Create comparison plots for model metrics
        
        Args:
            metrics: Dictionary of model metrics
            output_dir: Directory to save plots
        """
        # Extract model names and MAE values
        model_names = list(metrics.keys())
        
        # Create bar chart for overall MAE
        plt.figure(figsize=(10, 6))
        mean_mae = [metrics[model]['mean_mae'] for model in model_names]
        plt.bar(model_names, mean_mae)
        plt.title('Mean Absolute Error by Model')
        plt.ylabel('MAE')
        plt.grid(axis='y', linestyle='--', alpha=0.7)
        
        # Add values on top of bars
        for i, v in enumerate(mean_mae):
            plt.text(i, v + 0.001, f'{v:.4f}', ha='center')
        
        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, 'overall_mae_comparison.png'))
        plt.close()
        
        # Create bar chart for slice-specific MAE
        plt.figure(figsize=(12, 7))
        slice_types = ['embb', 'urllc', 'mmtc']
        x = np.arange(len(model_names))
        width = 0.25
        
        # Plot bars for each slice type
        for i, slice_type in enumerate(slice_types):
            mae_values = [metrics[model]['mae'][slice_type] for model in model_names]
            plt.bar(x + (i - 1) * width, mae_values, width, 
                   label=slice_type.upper())
        
        plt.title('Mean Absolute Error by Slice Type')
        plt.ylabel('MAE')
        plt.xlabel('Model')
        plt.xticks(x, model_names)
        plt.legend()
        plt.grid(axis='y', linestyle='--', alpha=0.7)
        
        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, 'slice_mae_comparison.png'))
        plt.close()
        
        # Create table with all metrics
        plt.figure(figsize=(10, 6))
        plt.axis('off')
        
        table_data = []
        table_data.append(['Model', 'Val Loss', 'eMBB MAE', 'URLLC MAE', 'mMTC MAE', 'Mean MAE'])
        
        for model in model_names:
            model_metrics = metrics[model]
            table_data.append([
                model,
                f"{model_metrics['validation_loss']:.6f}",
                f"{model_metrics['mae']['embb']:.6f}",
                f"{model_metrics['mae']['urllc']:.6f}",
                f"{model_metrics['mae']['mmtc']:.6f}",
                f"{model_metrics['mean_mae']:.6f}"
            ])
        
        table = plt.table(cellText=table_data, loc='center', cellLoc='center')
        table.auto_set_font_size(False)
        table.set_fontsize(12)
        table.scale(1.2, 1.5)
        
        plt.title('Model Performance Comparison', fontsize=16, pad=20)
        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, 'metrics_table.png'))
        plt.close()
        
        # Create summary text file
        with open(os.path.join(output_dir, 'comparison_summary.txt'), 'w') as f:
            f.write("5G Network Slicing Model Comparison\n")
            f.write("=================================\n\n")
            f.write(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            # Find best model
            best_model = min(model_names, key=lambda x: metrics[x]['mean_mae'])
            f.write(f"Best overall model: {best_model} (Mean MAE: {metrics[best_model]['mean_mae']:.6f})\n\n")
            
            # Best model for each slice type
            for slice_type in slice_types:
                best_for_slice = min(model_names, key=lambda x: metrics[x]['mae'][slice_type])
                f.write(f"Best model for {slice_type.upper()}: {best_for_slice} ")
                f.write(f"(MAE: {metrics[best_for_slice]['mae'][slice_type]:.6f})\n")
            
            f.write("\nDetailed Metrics:\n")
            f.write("----------------\n\n")
            
            for model in model_names:
                f.write(f"Model: {model}\n")
                f.write(f"  Validation Loss: {metrics[model]['validation_loss']:.6f}\n")
                f.write(f"  MAE:\n")
                f.write(f"    eMBB: {metrics[model]['mae']['embb']:.6f}\n")
                f.write(f"    URLLC: {metrics[model]['mae']['urllc']:.6f}\n")
                f.write(f"    mMTC: {metrics[model]['mae']['mmtc']:.6f}\n")
                f.write(f"    Mean: {metrics[model]['mean_mae']:.6f}\n\n")


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='5G Network Slicing Model Pipeline')
    
    parser.add_argument('--base_dir', type=str, default='.',
                        help='Base directory for data, models, and results')
    
    parser.add_argument('--num_samples', type=int, default=8760,
                        help='Number of samples to generate (default: 8760, one year hourly)')
    
    parser.add_argument('--visualize', action='store_true',
                        help='Generate visualizations')
    
    parser.add_argument('--skip_data_gen', action='store_true',
                        help='Skip data generation step')
    
    parser.add_argument('--skip_training', action='store_true',
                        help='Skip model training step')
    
    return parser.parse_args()


if __name__ == "__main__":
    # Parse command line arguments
    args = parse_args()
    
    # Create and run the pipeline
    pipeline = ModelPipeline(args)
    pipeline.run_pipeline()
    
    print("\nPipeline completed successfully!")
    print(f"- Data directory: {os.path.join(args.base_dir, 'data')}")
    print(f"- Models directory: {os.path.join(args.base_dir, 'models')}")
    print(f"- Results directory: {os.path.join(args.base_dir, 'results')}")
    
    if not args.skip_training:
        comparison_dir = os.path.join(args.base_dir, 'results', 'model_comparison')
        summary_file = os.path.join(comparison_dir, 'comparison_summary.txt')
        
        if os.path.exists(summary_file):
            print("\nModel Comparison Summary:")
            with open(summary_file, 'r') as f:
                for i, line in enumerate(f):
                    if i < 15:  # Print only the first few lines
                        print(line.rstrip())
            print("...")
            print(f"\nFull summary available at: {summary_file}") 