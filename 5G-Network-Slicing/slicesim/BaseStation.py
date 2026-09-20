#!/usr/bin/env python3
"""
5G Network Slicing - Base Station Module

This module implements the base station model for the 5G network slicing system.
"""

import numpy as np

class Coverage:
    """
    Coverage area for a base station.
    """
    
    def __init__(self, center, radius):
        """
        Initialize a coverage area.
        
        Args:
            center (tuple): Center coordinates (x, y)
            radius (float): Coverage radius
        """
        self.center = center
        self.radius = radius

class BaseStation:
    """
    Base station in the 5G network.
    
    This class represents a base station in the 5G network.
    """
    
    def __init__(self, station_id, x, y, coverage_radius=500):
        """
        Initialize a base station.
        
        Args:
            station_id (int): Unique identifier for the base station
            x (float): X coordinate
            y (float): Y coordinate
            coverage_radius (float): Coverage radius
        """
        self.station_id = station_id
        self.id = station_id  # Alias for compatibility
        self.x = x
        self.y = y
        self.coverage = Coverage((x, y), coverage_radius)
        self.clients = []
        
        # Resource allocation for each slice (eMBB, URLLC, mMTC)
        self.allocation = np.array([0.4, 0.4, 0.2])
        
        # Current utilization for each slice
        self.utilization = np.array([0.0, 0.0, 0.0])
        
        # Slices in this base station
        self.slices = {}
    
    def add_slice(self, slice_obj):
        """
        Add a slice to this base station.
        
        Args:
            slice_obj: Slice to add
        """
        if slice_obj.name not in self.slices:
            self.slices[slice_obj.name] = slice_obj
    
    def add_client(self, client):
        """
        Add a client to this base station.
        
        Args:
            client: Client to add
        """
        if client not in self.clients:
            self.clients.append(client)
    
    def remove_client(self, client):
        """
        Remove a client from this base station.
        
        Args:
            client: Client to remove
        """
        if client in self.clients:
            self.clients.remove(client)
    
    def update_allocation(self, allocation):
        """
        Update resource allocation.
        
        Args:
            allocation (numpy.ndarray): New allocation for each slice
        """
        self.allocation = allocation
    
    def update_utilization(self):
        """
        Update utilization based on client traffic.
        """
        # Initialize utilization for each slice
        traffic = np.zeros(3)
        
        # Count clients per slice type
        for client in self.clients:
            if client.slice_type == 'eMBB':
                traffic[0] += client.traffic_load
            elif client.slice_type == 'URLLC':
                traffic[1] += client.traffic_load
            elif client.slice_type == 'mMTC':
                traffic[2] += client.traffic_load
        
        # Calculate utilization (traffic / allocation)
        # Add small constant to avoid division by zero
        self.utilization = traffic / (self.allocation + 1e-6)
        
        return self.utilization
    
    def get_utilization(self):
        """
        Get current utilization.
        
        Returns:
            numpy.ndarray: Current utilization for each slice
        """
        return self.utilization

    def __str__(self):
        """String representation of the base station."""
        return f"BaseStation {self.station_id} at ({self.x}, {self.y}) with {len(self.clients)} clients"

