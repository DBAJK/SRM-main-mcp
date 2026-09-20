"""
Network Digital Twin (NDT) Simulator Module

This module provides a Network Digital Twin (NDT) simulator for validating
slice performance and providing feedback to the AI agent.
"""

import os
import logging
import json
import asyncio
import random
from datetime import datetime
from typing import Dict, List, Any, Optional
from prometheus_client import Counter, Gauge, start_http_server, CollectorRegistry

# Configure logging
logger = logging.getLogger(__name__)

class NetworkDigitalTwin:
    """Network Digital Twin simulator"""
    
    def __init__(self, metrics_port: int = 8001):
        """Initialize the Network Digital Twin simulator
        
        Args:
            metrics_port: Port for Prometheus metrics
        """
        self.logger = logging.getLogger(__name__)
        self.metrics_port = metrics_port
        self.active_slices = {}
        self.telemetry_data = {}
        self.running = False
        self.simulation_task = None
        self.simulation_interval = 5  # seconds
        
        # Create a custom registry for this instance
        self.registry = CollectorRegistry()
        
        # Initialize metrics
        self.slice_count = Gauge('ndt_active_slices', 'Number of active slices', registry=self.registry)
        self.qos_violations = Gauge('ndt_qos_violations', 'Number of QoS violations detected', registry=self.registry)
        self.slice_latency = Gauge('ndt_slice_latency', 'Slice latency (ms)', ['slice_id', 'vendor_id'], registry=self.registry)
        self.slice_bandwidth = Gauge('ndt_slice_bandwidth', 'Slice bandwidth (Mbps)', ['slice_id', 'vendor_id'], registry=self.registry)
        self.slice_availability = Gauge('ndt_slice_availability', 'Slice availability (%)', ['slice_id', 'vendor_id'], registry=self.registry)
    
    async def start(self):
        """Start the Network Digital Twin"""
        logger.info("Starting Network Digital Twin")
        
        # Set running flag
        self.running = True
        
        # Start simulation loop
        self.simulation_task = asyncio.create_task(self._run_simulation())
        
        logger.info("Network Digital Twin started")
    
    async def initialize(self):
        """Initialize the Network Digital Twin (legacy method)"""
        await self.start()
    
    async def shutdown(self):
        """Shutdown the Network Digital Twin"""
        logger.info("Shutting down Network Digital Twin")
        
        # Clear running flag
        self.running = False
        
        # Cancel simulation task
        if self.simulation_task:
            self.simulation_task.cancel()
            try:
                await self.simulation_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Network Digital Twin shutdown complete")
    
    async def register_slice(
        self,
        slice_id: str,
        vendor_id: str,
        slice_type: str,
        qos_promised: Dict[str, Any],
        location: str,
        start_time: Optional[str] = None
    ) -> bool:
        """Register a slice for simulation
        
        Args:
            slice_id: Slice identifier
            vendor_id: Vendor identifier
            slice_type: Slice type
            qos_promised: QoS parameters
            location: Location of the slice
            start_time: Start time of the slice
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Set start time if not provided
            if not start_time:
                start_time = datetime.now().isoformat()
                
            # Store slice information
            self.active_slices[slice_id] = {
                "slice_id": slice_id,
                "vendor_id": vendor_id,
                "slice_type": slice_type,
                "qos_promised": qos_promised,
                "location": location,
                "start_time": start_time,
                "status": "active"
            }
            
            # Initialize telemetry data
            self.telemetry_data[slice_id] = {
                "slice_id": slice_id,
                "vendor_id": vendor_id,
                "slice_type": slice_type,
                "qos_promised": qos_promised,
                "qos_actual": self._generate_initial_qos(qos_promised, slice_type),
                "location": location,
                "start_time": start_time,
                "qos_history": [],
                "violations": []
            }
            
            # Update metrics
            self.slice_count.set(len(self.active_slices))
            
            logger.info(f"Registered slice {slice_id} for simulation")
            return True
        except Exception as e:
            logger.error(f"Error registering slice {slice_id}: {str(e)}")
            return False
    
    async def unregister_slice(self, slice_id: str) -> bool:
        """Unregister a slice from simulation
        
        Args:
            slice_id: Slice identifier
            
        Returns:
            bool: True if successful, False otherwise
        """
        if slice_id in self.active_slices:
            # Remove slice
            del self.active_slices[slice_id]
            
            # Remove telemetry data
            if slice_id in self.telemetry_data:
                del self.telemetry_data[slice_id]
            
            # Update metrics
            self.slice_count.set(len(self.active_slices))
            
            logger.info(f"Unregistered slice {slice_id} from simulation")
            return True
        else:
            logger.warning(f"Slice {slice_id} not found for unregistration")
            return False
    
    async def get_slice_telemetry(self, slice_id: str) -> Optional[Dict[str, Any]]:
        """Get telemetry data for a slice
        
        Args:
            slice_id: Slice identifier
            
        Returns:
            Dict: Telemetry data
        """
        if slice_id in self.telemetry_data:
            return self.telemetry_data[slice_id]
        else:
            return None
    
    async def get_all_telemetry(self) -> Dict[str, Dict[str, Any]]:
        """Get telemetry data for all slices
        
        Returns:
            Dict: Telemetry data for all slices
        """
        return self.telemetry_data
    
    def _generate_initial_qos(self, promised_qos: Dict[str, Any], slice_type: str) -> Dict[str, Any]:
        """Generate initial QoS values based on promised QoS
        
        Args:
            promised_qos: Promised QoS parameters
            slice_type: Slice type
            
        Returns:
            Dict: Initial QoS values
        """
        # Start with slightly better than promised values
        actual_qos = {}
        
        for key, value in promised_qos.items():
            if key in ["latency_ms", "jitter_ms", "packet_loss_percent"]:
                # Lower is better, so start with slightly lower value
                actual_qos[key] = value * random.uniform(0.8, 0.95)
            elif key in ["bandwidth_mbps", "availability_percent", "reliability_percent"]:
                # Higher is better, so start with slightly higher value
                actual_qos[key] = value * random.uniform(1.01, 1.05)
            else:
                # For other parameters, just use the promised value
                actual_qos[key] = value
        
        return actual_qos
    
    async def _run_simulation(self):
        """Run the simulation loop"""
        try:
            while self.running:
                # Update telemetry for each active slice
                for slice_id, slice_info in list(self.active_slices.items()):
                    await self._update_slice_telemetry(slice_id, slice_info)
                
                # Wait before next update
                await asyncio.sleep(self.simulation_interval)
        except asyncio.CancelledError:
            logger.info("Simulation loop cancelled")
        except Exception as e:
            logger.error(f"Error in simulation loop: {str(e)}")
    
    async def _update_slice_telemetry(self, slice_id: str, slice_info: Dict[str, Any]):
        """Update telemetry for a slice
        
        Args:
            slice_id: Slice identifier
            slice_info: Slice information
        """
        try:
            if slice_id not in self.telemetry_data:
                return
            
            telemetry = self.telemetry_data[slice_id]
            promised_qos = slice_info["qos_promised"]
            actual_qos = telemetry["qos_actual"]
            slice_type = slice_info["slice_type"]
            vendor_id = slice_info["vendor_id"]
            
            # Store current QoS in history
            telemetry["qos_history"].append({
                "timestamp": datetime.now().isoformat(),
                "qos": actual_qos.copy()
            })
            
            # Limit history size
            if len(telemetry["qos_history"]) > 100:
                telemetry["qos_history"] = telemetry["qos_history"][-100:]
            
            # Update QoS values with some randomness
            new_qos = {}
            violations = []
            
            for key, promised_value in promised_qos.items():
                current_value = actual_qos.get(key, promised_value)
                
                # Add some randomness based on slice type
                if slice_type == "URLLC":
                    # URLLC should be more stable
                    variation = 0.05
                elif slice_type == "eMBB":
                    # eMBB can have more variation
                    variation = 0.1
                else:  # mMTC
                    # mMTC can have even more variation
                    variation = 0.15
                
                # Calculate new value with random variation
                if key in ["latency_ms", "jitter_ms", "packet_loss_percent"]:
                    # Lower is better
                    # 90% of the time, stay below promised value
                    if random.random() < 0.9:
                        new_value = promised_value * random.uniform(0.8, 1.0)
                    else:
                        # Occasionally exceed promised value
                        new_value = promised_value * random.uniform(1.0, 1.2)
                    
                    # Check for violation
                    if new_value > promised_value:
                        violations.append({
                            "parameter": key,
                            "promised": promised_value,
                            "actual": new_value,
                            "timestamp": datetime.now().isoformat()
                        })
                        # Increment QoS violation counter
                        self.qos_violations.labels(slice_id=slice_id, vendor_id=vendor_id, parameter=key).inc()
                
                elif key in ["bandwidth_mbps", "availability_percent", "reliability_percent"]:
                    # Higher is better
                    # 90% of the time, stay above promised value
                    if random.random() < 0.9:
                        new_value = promised_value * random.uniform(1.0, 1.1)
                    else:
                        # Occasionally fall below promised value
                        new_value = promised_value * random.uniform(0.9, 1.0)
                    
                    # Check for violation
                    if new_value < promised_value:
                        violations.append({
                            "parameter": key,
                            "promised": promised_value,
                            "actual": new_value,
                            "timestamp": datetime.now().isoformat()
                        })
                        # Increment QoS violation counter
                        self.qos_violations.labels(slice_id=slice_id, vendor_id=vendor_id, parameter=key).inc()
                
                else:
                    # For other parameters, just use the promised value
                    new_value = promised_value
                
                new_qos[key] = new_value
            
            # Update actual QoS
            telemetry["qos_actual"] = new_qos
            
            # Add violations
            if violations:
                telemetry["violations"].extend(violations)
                
                # Limit violations history
                if len(telemetry["violations"]) > 100:
                    telemetry["violations"] = telemetry["violations"][-100:]
            
            # Update metrics
            if "latency_ms" in new_qos:
                self.slice_latency.labels(slice_id=slice_id, vendor_id=vendor_id).set(new_qos["latency_ms"])
            if "bandwidth_mbps" in new_qos:
                self.slice_bandwidth.labels(slice_id=slice_id, vendor_id=vendor_id).set(new_qos["bandwidth_mbps"])
            if "availability_percent" in new_qos:
                self.slice_availability.labels(slice_id=slice_id, vendor_id=vendor_id).set(new_qos["availability_percent"])
            
            logger.debug(f"Updated telemetry for slice {slice_id}")
        except Exception as e:
            logger.error(f"Error updating telemetry for slice {slice_id}: {str(e)}")
    
    def status(self) -> Dict[str, Any]:
        """
        Get the status of the Network Digital Twin.
        
        Returns:
            Dictionary with status information
        """
        return {
            "status": "operational" if self.running else "idle",
            "active_simulations": len(self.active_slices),
            "metrics_port": self.metrics_port
        } 