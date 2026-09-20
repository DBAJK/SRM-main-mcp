#!/usr/bin/env python3
"""
Open5GS Integration Module for AI-Native Network Slicing

This module provides the necessary interfaces to connect the AI-based network slicing
solution with Open5GS for real-world testing and validation.
"""

import os
import sys
import json
import time
import requests
import subprocess
import logging
import numpy as np
from threading import Thread

# Add the project root to the path so we can import our modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import AI modules
from slicesim.ai.lstm_predictor import LSTMPredictor
from slicesim.ai.dqn_classifier import DQNClassifier
from slicesim.slice_optimization import SliceOptimizer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('open5gs_integration')

class Open5GSAdapter:
    """
    Adapter class to interface between the AI slice optimization and Open5GS.
    """
    
    def __init__(self, config_file=None):
        """
        Initialize the Open5GS adapter.
        
        Args:
            config_file: Path to the configuration file for Open5GS integration
        """
        self.config = self._load_config(config_file)
        self.slice_optimizer = SliceOptimizer()
        self.open5gs_api_url = self.config.get('open5gs_api_url', 'http://localhost:3000/api')
        self.api_token = self.config.get('api_token', '')
        self.monitoring_interval = self.config.get('monitoring_interval', 10)  # seconds
        self.is_monitoring = False
        self.monitoring_thread = None
        
        # Check if Open5GS is available
        self._check_open5gs_availability()
    
    def _load_config(self, config_file):
        """Load configuration from file or use defaults."""
        if config_file and os.path.exists(config_file):
            with open(config_file, 'r') as f:
                return json.load(f)
        return {
            'open5gs_api_url': 'http://localhost:3000/api',
            'api_token': '',
            'monitoring_interval': 10,
            'slice_templates': {
                'embb': {
                    'sst': 1,
                    'sd': '000001',
                    'default_qos': {
                        'qci': 9,
                        'arp': 8,
                        'gbr_ul': 0,
                        'gbr_dl': 0,
                        'mbr_ul': 1000000000,
                        'mbr_dl': 1000000000
                    }
                },
                'urllc': {
                    'sst': 2,
                    'sd': '000002',
                    'default_qos': {
                        'qci': 80,
                        'arp': 2,
                        'gbr_ul': 10000000,
                        'gbr_dl': 10000000,
                        'mbr_ul': 100000000,
                        'mbr_dl': 100000000
                    }
                },
                'mmtc': {
                    'sst': 3,
                    'sd': '000003',
                    'default_qos': {
                        'qci': 70,
                        'arp': 6,
                        'gbr_ul': 0,
                        'gbr_dl': 0,
                        'mbr_ul': 10000000,
                        'mbr_dl': 10000000
                    }
                }
            }
        }
    
    def _check_open5gs_availability(self):
        """Check if Open5GS is available and running."""
        try:
            response = requests.get(f"{self.open5gs_api_url}/health", timeout=5)
            if response.status_code == 200:
                logger.info("Open5GS is available")
                return True
            else:
                logger.warning(f"Open5GS API returned status code {response.status_code}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to connect to Open5GS: {e}")
            logger.info("Make sure Open5GS is installed and running")
            logger.info("For installation instructions, visit: https://open5gs.org/open5gs/docs/guide/01-quickstart/")
        return False
    
    def create_network_slice(self, slice_type, custom_params=None):
        """
        Create a new network slice in Open5GS.
        
        Args:
            slice_type: Type of slice ('embb', 'urllc', or 'mmtc')
            custom_params: Optional custom parameters to override defaults
        
        Returns:
            slice_id: ID of the created slice
        """
        if slice_type not in self.config['slice_templates']:
            raise ValueError(f"Unknown slice type: {slice_type}")
        
        # Get slice template
        slice_template = self.config['slice_templates'][slice_type].copy()
        
        # Override with custom params if provided
        if custom_params:
            for key, value in custom_params.items():
                if key in slice_template:
                    if isinstance(slice_template[key], dict) and isinstance(value, dict):
                        slice_template[key].update(value)
                    else:
                        slice_template[key] = value
        
        # Call Open5GS API to create the slice
        headers = {'Content-Type': 'application/json'}
        if self.api_token:
            headers['Authorization'] = f'Bearer {self.api_token}'
        
        try:
            response = requests.post(
                f"{self.open5gs_api_url}/network-slices",
                headers=headers,
                json=slice_template
            )
            
            if response.status_code in (200, 201):
                slice_data = response.json()
                logger.info(f"Created {slice_type} slice with ID: {slice_data.get('id')}")
                return slice_data.get('id')
            else:
                logger.error(f"Failed to create slice: {response.status_code} - {response.text}")
                return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Error creating network slice: {e}")
            return None
    
    def update_slice_resources(self, slice_id, resource_allocation):
        """
        Update the resource allocation for a specific slice.
        
        Args:
            slice_id: ID of the slice to update
            resource_allocation: Dictionary with resource parameters to update
        
        Returns:
            success: Boolean indicating if the update was successful
        """
        headers = {'Content-Type': 'application/json'}
        if self.api_token:
            headers['Authorization'] = f'Bearer {self.api_token}'
        
        try:
            response = requests.patch(
                f"{self.open5gs_api_url}/network-slices/{slice_id}",
                headers=headers,
                json=resource_allocation
            )
            
            if response.status_code == 200:
                logger.info(f"Updated resources for slice {slice_id}")
                return True
            else:
                logger.error(f"Failed to update slice resources: {response.status_code} - {response.text}")
                return False
        except requests.exceptions.RequestException as e:
            logger.error(f"Error updating slice resources: {e}")
            return False
    
    def get_slice_metrics(self, slice_id=None):
        """
        Get performance metrics for slices from Open5GS.
        
        Args:
            slice_id: Optional ID of a specific slice to get metrics for
        
        Returns:
            metrics: Dictionary of slice metrics
        """
        endpoint = f"{self.open5gs_api_url}/metrics"
        if slice_id:
            endpoint = f"{endpoint}/network-slices/{slice_id}"
        
        headers = {}
        if self.api_token:
            headers['Authorization'] = f'Bearer {self.api_token}'
        
        try:
            response = requests.get(endpoint, headers=headers)
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to get slice metrics: {response.status_code} - {response.text}")
                return {}
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting slice metrics: {e}")
            return {}
    
    def _monitoring_loop(self):
        """Background monitoring loop to continuously optimize slices."""
        logger.info("Starting network slice monitoring")
        
        while self.is_monitoring:
            try:
                # Get current metrics
                metrics = self.get_slice_metrics()
                
                if metrics:
                    # Convert metrics to the format expected by the optimizer
                    formatted_metrics = self._format_metrics_for_ai(metrics)
                    
                    # Get optimized allocation from AI
                    optimized_allocation = self.slice_optimizer.optimize_allocation(formatted_metrics)
                    
                    # Apply the optimized allocation to each slice
                    for slice_id, allocation in optimized_allocation.items():
                        self.update_slice_resources(slice_id, allocation)
                
                # Sleep for the monitoring interval
                time.sleep(self.monitoring_interval)
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                time.sleep(self.monitoring_interval)
    
    def _format_metrics_for_ai(self, metrics):
        """
        Format Open5GS metrics to be compatible with the AI models.
        
        Args:
            metrics: Raw metrics from Open5GS
            
        Returns:
            formatted_metrics: Metrics formatted for AI processing
        """
        # This will depend on the exact format of both Open5GS metrics and what your AI expects
        # Here's a placeholder implementation
        formatted_metrics = {
            'network_load': [],
            'slice_metrics': {}
        }
        
        # Extract overall network load
        if 'system' in metrics and 'load' in metrics['system']:
            formatted_metrics['network_load'] = metrics['system']['load']
        
        # Extract per-slice metrics
        if 'slices' in metrics:
            for slice_data in metrics['slices']:
                slice_id = slice_data.get('id')
                if slice_id:
                    formatted_metrics['slice_metrics'][slice_id] = {
                        'throughput': slice_data.get('throughput', 0),
                        'latency': slice_data.get('latency', 0),
                        'packet_loss': slice_data.get('packet_loss', 0),
                        'connected_users': slice_data.get('connected_users', 0),
                        'resource_usage': slice_data.get('resource_usage', 0)
                    }
        
        return formatted_metrics
    
    def start_monitoring(self):
        """Start the background monitoring and optimization thread."""
        if not self.is_monitoring:
            self.is_monitoring = True
            self.monitoring_thread = Thread(target=self._monitoring_loop)
            self.monitoring_thread.daemon = True
            self.monitoring_thread.start()
            logger.info("Monitoring thread started")
    
    def stop_monitoring(self):
        """Stop the background monitoring and optimization thread."""
        if self.is_monitoring:
            self.is_monitoring = False
            if self.monitoring_thread:
                self.monitoring_thread.join(timeout=5)
            logger.info("Monitoring thread stopped")

def main():
    """Main function to demonstrate Open5GS integration."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Open5GS AI Network Slicing Integration')
    parser.add_argument('--config', type=str, help='Path to configuration file')
    parser.add_argument('--create-slices', action='store_true', help='Create initial network slices')
    parser.add_argument('--monitor', action='store_true', help='Start monitoring and optimization')
    parser.add_argument('--duration', type=int, default=3600, help='Duration to run monitoring (seconds)')
    
    args = parser.parse_args()
    
    try:
        # Initialize the adapter
        adapter = Open5GSAdapter(config_file=args.config)
        
        # Create initial slices if requested
        if args.create_slices:
            embb_slice_id = adapter.create_network_slice('embb')
            urllc_slice_id = adapter.create_network_slice('urllc')
            mmtc_slice_id = adapter.create_network_slice('mmtc')
            
            if all([embb_slice_id, urllc_slice_id, mmtc_slice_id]):
                logger.info("Successfully created all network slices")
            else:
                logger.warning("Failed to create some network slices")
        
        # Start monitoring if requested
        if args.monitor:
            adapter.start_monitoring()
            try:
                logger.info(f"Monitoring for {args.duration} seconds...")
                time.sleep(args.duration)
            except KeyboardInterrupt:
                logger.info("Monitoring interrupted by user")
            finally:
                adapter.stop_monitoring()
    
    except Exception as e:
        logger.error(f"Error in main function: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 