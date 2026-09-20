#!/usr/bin/env python3
"""
Open5GS AI Integration Demo

This script demonstrates the integration between the AI-based network slicing solution
and Open5GS for real-world testing and validation.
"""

import os
import sys
import time
import json
import argparse
import logging
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime

# Add the project root to the path so we can import our modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import our modules
from open5gs_integration import Open5GSAdapter
from slicesim.ai.lstm_predictor import LSTMPredictor
from slicesim.ai.dqn_classifier import DQNClassifier

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('open5gs_ai_demo')

class Open5GSAIDemo:
    """
    Demo class to showcase the integration between AI-based network slicing and Open5GS.
    """
    
    def __init__(self, config_file=None):
        """
        Initialize the demo.
        
        Args:
            config_file: Path to the configuration file
        """
        self.config_file = config_file or 'open5gs_config.json'
        self.adapter = Open5GSAdapter(config_file=self.config_file)
        self.metrics_history = {
            'timestamps': [],
            'slices': {}
        }
        self.slice_ids = {}
    
    def setup_slices(self):
        """Set up the network slices for the demo."""
        logger.info("Setting up network slices...")
        
        # Create eMBB slice
        embb_slice_id = self.adapter.create_network_slice('embb')
        if embb_slice_id:
            self.slice_ids['embb'] = embb_slice_id
            logger.info(f"Created eMBB slice with ID: {embb_slice_id}")
        else:
            logger.error("Failed to create eMBB slice")
        
        # Create URLLC slice
        urllc_slice_id = self.adapter.create_network_slice('urllc')
        if urllc_slice_id:
            self.slice_ids['urllc'] = urllc_slice_id
            logger.info(f"Created URLLC slice with ID: {urllc_slice_id}")
        else:
            logger.error("Failed to create URLLC slice")
        
        # Create mMTC slice
        mmtc_slice_id = self.adapter.create_network_slice('mmtc')
        if mmtc_slice_id:
            self.slice_ids['mmtc'] = mmtc_slice_id
            logger.info(f"Created mMTC slice with ID: {mmtc_slice_id}")
        else:
            logger.error("Failed to create mMTC slice")
        
        return len(self.slice_ids) == 3
    
    def collect_metrics(self, duration=300, interval=10):
        """
        Collect metrics from the network slices for a specified duration.
        
        Args:
            duration: Duration to collect metrics for (seconds)
            interval: Interval between metric collections (seconds)
        """
        logger.info(f"Collecting metrics for {duration} seconds...")
        
        start_time = time.time()
        end_time = start_time + duration
        
        while time.time() < end_time:
            current_time = time.time()
            self.metrics_history['timestamps'].append(current_time)
            
            # Get metrics for each slice
            for slice_type, slice_id in self.slice_ids.items():
                metrics = self.adapter.get_slice_metrics(slice_id)
                
                if slice_type not in self.metrics_history['slices']:
                    self.metrics_history['slices'][slice_type] = {
                        'throughput': [],
                        'latency': [],
                        'packet_loss': [],
                        'connected_users': [],
                        'resource_usage': []
                    }
                
                # Extract and store metrics
                slice_metrics = metrics.get('metrics', {})
                self.metrics_history['slices'][slice_type]['throughput'].append(
                    slice_metrics.get('throughput', 0)
                )
                self.metrics_history['slices'][slice_type]['latency'].append(
                    slice_metrics.get('latency', 0)
                )
                self.metrics_history['slices'][slice_type]['packet_loss'].append(
                    slice_metrics.get('packet_loss', 0)
                )
                self.metrics_history['slices'][slice_type]['connected_users'].append(
                    slice_metrics.get('connected_users', 0)
                )
                self.metrics_history['slices'][slice_type]['resource_usage'].append(
                    slice_metrics.get('resource_usage', 0)
                )
            
            # Sleep for the specified interval
            time_to_sleep = interval - (time.time() - current_time)
            if time_to_sleep > 0:
                time.sleep(time_to_sleep)
    
    def run_ai_optimization(self, duration=300, interval=30):
        """
        Run the AI optimization for a specified duration.
        
        Args:
            duration: Duration to run optimization for (seconds)
            interval: Interval between optimization runs (seconds)
        """
        logger.info(f"Running AI optimization for {duration} seconds...")
        
        # Start monitoring (which includes optimization)
        self.adapter.start_monitoring()
        
        try:
            # Wait for the specified duration
            time.sleep(duration)
        finally:
            # Stop monitoring
            self.adapter.stop_monitoring()
    
    def visualize_results(self, output_dir='results'):
        """
        Visualize the collected metrics.
        
        Args:
            output_dir: Directory to save visualization results
        """
        logger.info("Visualizing results...")
        
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        
        # Convert timestamps to relative time (seconds since start)
        if not self.metrics_history['timestamps']:
            logger.error("No metrics collected")
            return
        
        start_time = self.metrics_history['timestamps'][0]
        relative_times = [t - start_time for t in self.metrics_history['timestamps']]
        
        # Plot metrics for each slice
        metrics_to_plot = ['throughput', 'latency', 'packet_loss', 'resource_usage']
        slice_colors = {'embb': 'blue', 'urllc': 'red', 'mmtc': 'green'}
        
        for metric in metrics_to_plot:
            plt.figure(figsize=(10, 6))
            
            for slice_type, color in slice_colors.items():
                if slice_type in self.metrics_history['slices']:
                    values = self.metrics_history['slices'][slice_type][metric]
                    plt.plot(relative_times, values, color=color, label=f"{slice_type}")
            
            plt.xlabel('Time (seconds)')
            plt.ylabel(metric.replace('_', ' ').title())
            plt.title(f"{metric.replace('_', ' ').title()} over Time")
            plt.legend()
            plt.grid(True)
            
            # Save the plot
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{output_dir}/{metric}_{timestamp}.png"
            plt.savefig(filename)
            logger.info(f"Saved {metric} plot to {filename}")
            
            plt.close()
        
        # Save raw metrics to JSON
        metrics_file = f"{output_dir}/metrics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(metrics_file, 'w') as f:
            json.dump(self.metrics_history, f, indent=2)
        logger.info(f"Saved raw metrics to {metrics_file}")
    
    def compare_ai_vs_non_ai(self, duration=300, interval=10):
        """
        Compare performance with and without AI optimization.
        
        Args:
            duration: Duration for each test (seconds)
            interval: Interval between metric collections (seconds)
        """
        logger.info("Starting comparison: AI vs. Non-AI optimization")
        
        # First, collect metrics without AI optimization
        logger.info("Phase 1: Collecting metrics without AI optimization...")
        self.metrics_history = {
            'timestamps': [],
            'slices': {}
        }
        self.collect_metrics(duration=duration, interval=interval)
        
        # Save non-AI metrics
        non_ai_metrics = self.metrics_history.copy()
        
        # Then, run with AI optimization
        logger.info("Phase 2: Running with AI optimization...")
        self.metrics_history = {
            'timestamps': [],
            'slices': {}
        }
        self.run_ai_optimization(duration=duration)
        self.collect_metrics(duration=duration, interval=interval)
        
        # Save AI metrics
        ai_metrics = self.metrics_history.copy()
        
        # Compare and visualize results
        self._visualize_comparison(non_ai_metrics, ai_metrics)
    
    def _visualize_comparison(self, non_ai_metrics, ai_metrics, output_dir='results'):
        """
        Visualize comparison between AI and non-AI optimization.
        
        Args:
            non_ai_metrics: Metrics collected without AI optimization
            ai_metrics: Metrics collected with AI optimization
            output_dir: Directory to save visualization results
        """
        logger.info("Visualizing comparison results...")
        
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        
        # Metrics to compare
        metrics_to_compare = ['throughput', 'latency', 'packet_loss', 'resource_usage']
        slice_types = ['embb', 'urllc', 'mmtc']
        
        # Calculate averages for each metric and slice type
        ai_averages = {}
        non_ai_averages = {}
        
        for slice_type in slice_types:
            ai_averages[slice_type] = {}
            non_ai_averages[slice_type] = {}
            
            for metric in metrics_to_compare:
                if (slice_type in ai_metrics['slices'] and 
                    metric in ai_metrics['slices'][slice_type] and 
                    ai_metrics['slices'][slice_type][metric]):
                    ai_averages[slice_type][metric] = np.mean(ai_metrics['slices'][slice_type][metric])
                else:
                    ai_averages[slice_type][metric] = 0
                
                if (slice_type in non_ai_metrics['slices'] and 
                    metric in non_ai_metrics['slices'][slice_type] and 
                    non_ai_metrics['slices'][slice_type][metric]):
                    non_ai_averages[slice_type][metric] = np.mean(non_ai_metrics['slices'][slice_type][metric])
                else:
                    non_ai_averages[slice_type][metric] = 0
        
        # Create bar charts comparing AI vs. non-AI for each metric
        for metric in metrics_to_compare:
            plt.figure(figsize=(12, 6))
            
            x = np.arange(len(slice_types))
            width = 0.35
            
            ai_values = [ai_averages[st][metric] for st in slice_types]
            non_ai_values = [non_ai_averages[st][metric] for st in slice_types]
            
            plt.bar(x - width/2, non_ai_values, width, label='Without AI')
            plt.bar(x + width/2, ai_values, width, label='With AI')
            
            plt.xlabel('Slice Type')
            plt.ylabel(metric.replace('_', ' ').title())
            plt.title(f'Average {metric.replace("_", " ").title()}: AI vs. Non-AI')
            plt.xticks(x, slice_types)
            plt.legend()
            
            # Add percentage improvement/degradation
            for i, (non_ai, ai) in enumerate(zip(non_ai_values, ai_values)):
                if non_ai > 0:  # Avoid division by zero
                    pct_change = ((ai - non_ai) / non_ai) * 100
                    color = 'green' if (metric == 'throughput' and pct_change > 0) or \
                                      (metric in ['latency', 'packet_loss'] and pct_change < 0) else 'red'
                    plt.annotate(f"{pct_change:.1f}%", 
                                xy=(i, max(ai, non_ai) + 0.05 * max(ai, non_ai)),
                                ha='center', va='bottom', color=color)
            
            # Save the plot
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{output_dir}/comparison_{metric}_{timestamp}.png"
            plt.savefig(filename)
            logger.info(f"Saved comparison plot for {metric} to {filename}")
            
            plt.close()
        
        # Save comparison data to JSON
        comparison_file = f"{output_dir}/comparison_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        comparison_data = {
            'ai': ai_averages,
            'non_ai': non_ai_averages
        }
        with open(comparison_file, 'w') as f:
            json.dump(comparison_data, f, indent=2)
        logger.info(f"Saved comparison data to {comparison_file}")

def main():
    """Main function to run the Open5GS AI demo."""
    parser = argparse.ArgumentParser(description='Open5GS AI Network Slicing Demo')
    parser.add_argument('--config', type=str, default='open5gs_config.json', 
                        help='Path to configuration file')
    parser.add_argument('--duration', type=int, default=300, 
                        help='Duration for tests (seconds)')
    parser.add_argument('--interval', type=int, default=10, 
                        help='Interval between metric collections (seconds)')
    parser.add_argument('--compare', action='store_true', 
                        help='Run comparison between AI and non-AI optimization')
    parser.add_argument('--output-dir', type=str, default='results', 
                        help='Directory to save results')
    
    args = parser.parse_args()
    
    try:
        # Initialize the demo
        demo = Open5GSAIDemo(config_file=args.config)
        
        # Set up network slices
        if not demo.setup_slices():
            logger.error("Failed to set up all required network slices")
            return 1
        
        # Run the demo
        if args.compare:
            demo.compare_ai_vs_non_ai(duration=args.duration, interval=args.interval)
        else:
            # Collect initial metrics
            demo.collect_metrics(duration=args.duration / 2, interval=args.interval)
            
            # Run AI optimization
            demo.run_ai_optimization(duration=args.duration)
            
            # Collect final metrics
            demo.collect_metrics(duration=args.duration / 2, interval=args.interval)
        
        # Visualize results
        demo.visualize_results(output_dir=args.output_dir)
        
        logger.info("Demo completed successfully")
    
    except Exception as e:
        logger.error(f"Error in demo: {e}", exc_info=True)
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 