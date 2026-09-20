#!/usr/bin/env python3
"""
5G Network Slicing - Client Module

This module implements the client model for the 5G network slicing system.
"""

import numpy as np
import math

def distance(a, b):
    """Calculate Euclidean distance between two points"""
    return math.sqrt(sum((i-j)**2 for i, j in zip(a, b)))

class Client:
    """
    Client in the 5G network.
    
    This class represents a client device connected to the 5G network.
    """
    
    def __init__(self, client_id, x, y, slice_type='eMBB', env=None):
        """
        Initialize a client.
        
        Args:
            client_id (int): Unique identifier for the client
            x (float): X coordinate
            y (float): Y coordinate
            slice_type (str): Type of slice ('eMBB', 'URLLC', or 'mMTC')
            env: SimPy environment
        """
        self.client_id = client_id
        self.x = x
        self.y = y
        self.slice_type = slice_type
        self.base_station = None
        self.traffic_load = 0.0
        self.qos_satisfied = True
        self.closest_base_stations = []
        self.env = env
    
    def generate_traffic(self, base_level=0.5, variance=0.2):
        """
        Generate traffic for this client as a SimPy process.
        
        Args:
            base_level (float): Base traffic level
            variance (float): Traffic variance
        """
        while True:
            # Generate random traffic with normal distribution
            traffic = np.random.normal(base_level, variance)
            
            # Ensure traffic is positive
            traffic = max(0.1, traffic)
            
            self.traffic_load = traffic
            
            # Wait before generating traffic again
            if self.env:
                yield self.env.timeout(1)  # Generate traffic every 1 time unit
            else:
                break
    
    def connect_to_base_station(self, base_station):
        """
        Connect to a base station.
        
        Args:
            base_station: Base station to connect to
        """
        self.base_station = base_station
        if base_station:
            base_station.add_client(self)
    
    def check_qos(self, threshold):
        """
        Check if QoS requirements are satisfied.
        
        Args:
            threshold (float): QoS threshold
        
        Returns:
            bool: Whether QoS is satisfied
        """
        if not self.base_station:
            self.qos_satisfied = False
            return False
        
        # Get utilization for this client's slice type
        slice_idx = {'eMBB': 0, 'URLLC': 1, 'mMTC': 2}[self.slice_type]
        utilization = self.base_station.get_utilization()[slice_idx]
        
        # Check if utilization is below threshold
        self.qos_satisfied = utilization <= threshold
        return self.qos_satisfied
    
    def __str__(self):
        """String representation of the client."""
        return f"Client {self.client_id} ({self.slice_type}) at ({self.x}, {self.y})"
