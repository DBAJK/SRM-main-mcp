"""
Slice Compliance Monitor Module

This module monitors slice compliance with SLAs and triggers actions when violations occur.
"""

import logging
import asyncio
from datetime import datetime
from typing import Dict, List, Any, Optional

# Configure logging
logger = logging.getLogger(__name__)

class SliceComplianceMonitor:
    """Monitor for slice compliance with SLAs"""
    
    def __init__(self, monitoring_interval: int = 30):
        """Initialize the slice compliance monitor
        
        Args:
            monitoring_interval: Monitoring interval in seconds
        """
        self.monitoring_interval = monitoring_interval
        self.ndt = None
        self.feedback_loop = None
        self.monitoring_running = False
        self.monitoring_task = None
        self.violation_thresholds = {
            "latency": 1.1,  # 10% above promised
            "bandwidth": 0.9,  # 10% below promised
            "availability": 0.99,  # 1% below promised
            "reliability": 0.99,  # 1% below promised
            "jitter": 1.2,  # 20% above promised
            "packet_loss": 1.5  # 50% above promised
        }
        self.violation_counts = {}
    
    def register_ndt(self, ndt):
        """Register the Network Digital Twin
        
        Args:
            ndt: Network Digital Twin instance
        """
        self.ndt = ndt
        logger.info("Network Digital Twin registered with compliance monitor")
    
    def register_feedback_loop(self, feedback_loop):
        """Register the feedback loop
        
        Args:
            feedback_loop: Feedback loop instance
        """
        self.feedback_loop = feedback_loop
        logger.info("Feedback loop registered with compliance monitor")
    
    async def start_monitoring(self):
        """Start monitoring slices"""
        if self.monitoring_running:
            logger.warning("Monitoring already running")
            return
        
        self.monitoring_running = True
        self.monitoring_task = asyncio.create_task(self._run_monitoring())
        logger.info("Slice compliance monitoring started")
    
    async def stop_monitoring(self):
        """Stop monitoring slices"""
        if not self.monitoring_running:
            logger.warning("Monitoring not running")
            return
        
        self.monitoring_running = False
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
        logger.info("Slice compliance monitoring stopped")
    
    async def _run_monitoring(self):
        """Run the monitoring loop"""
        try:
            while self.monitoring_running:
                # Check if NDT is available
                if self.ndt:
                    # Get telemetry data for all slices
                    telemetry_data = await self.ndt.get_all_telemetry()
                    
                    # Check compliance for each slice
                    for slice_id, telemetry in telemetry_data.items():
                        await self._check_slice_compliance(slice_id, telemetry)
                
                # Wait before next check
                await asyncio.sleep(self.monitoring_interval)
        except asyncio.CancelledError:
            logger.info("Monitoring loop cancelled")
        except Exception as e:
            logger.error(f"Error in monitoring loop: {str(e)}")
    
    async def _check_slice_compliance(self, slice_id: str, telemetry: Dict[str, Any]):
        """Check compliance for a slice
        
        Args:
            slice_id: Slice identifier
            telemetry: Telemetry data
        """
        try:
            # Get actual QoS values
            actual_qos = telemetry.get("qos_actual", {})
            if not actual_qos:
                return
            
            # Get slice information from NDT
            slice_info = self.ndt.active_slices.get(slice_id)
            if not slice_info:
                return
            
            # Get promised QoS values
            promised_qos = slice_info.get("qos_promised", {})
            if not promised_qos:
                return
            
            # Check for violations
            violations = []
            
            for key, promised_value in promised_qos.items():
                if key not in actual_qos:
                    continue
                
                actual_value = actual_qos[key]
                threshold = self.violation_thresholds.get(key, 1.0)
                
                # Check if violation occurred
                if key in ["latency", "jitter", "packet_loss"]:
                    # Lower is better
                    if actual_value > promised_value * threshold:
                        violations.append({
                            "parameter": key,
                            "promised": promised_value,
                            "actual": actual_value,
                            "timestamp": datetime.now().isoformat()
                        })
                elif key in ["bandwidth", "availability", "reliability"]:
                    # Higher is better
                    if actual_value < promised_value * threshold:
                        violations.append({
                            "parameter": key,
                            "promised": promised_value,
                            "actual": actual_value,
                            "timestamp": datetime.now().isoformat()
                        })
            
            # If violations found, take action
            if violations:
                # Increment violation count
                if slice_id not in self.violation_counts:
                    self.violation_counts[slice_id] = 0
                self.violation_counts[slice_id] += len(violations)
                
                # Log violations
                logger.warning(f"Slice {slice_id} has {len(violations)} QoS violations")
                
                # Send violations to feedback loop
                if self.feedback_loop:
                    await self.feedback_loop.report_violations(
                        slice_id=slice_id,
                        vendor_id=telemetry.get("vendor_id"),
                        violations=violations
                    )
                
                # Check if severe violations
                if self._is_severe_violation(violations) or self.violation_counts[slice_id] >= 10:
                    logger.error(f"Severe violations detected for slice {slice_id}")
                    
                    # Trigger fallback action
                    await self._trigger_fallback_action(slice_id, violations)
            else:
                # Reset violation count if no violations
                if slice_id in self.violation_counts:
                    self.violation_counts[slice_id] = 0
        except Exception as e:
            logger.error(f"Error checking compliance for slice {slice_id}: {str(e)}")
    
    def _is_severe_violation(self, violations: List[Dict[str, Any]]) -> bool:
        """Check if violations are severe
        
        Args:
            violations: List of violations
            
        Returns:
            bool: True if severe violations, False otherwise
        """
        for violation in violations:
            parameter = violation["parameter"]
            promised = violation["promised"]
            actual = violation["actual"]
            
            # Define severe violation thresholds
            if parameter in ["latency", "jitter"]:
                # More than 50% above promised
                if actual > promised * 1.5:
                    return True
            elif parameter in ["availability", "reliability"]:
                # More than 5% below promised
                if actual < promised * 0.95:
                    return True
            elif parameter == "bandwidth":
                # More than 30% below promised
                if actual < promised * 0.7:
                    return True
            elif parameter == "packet_loss":
                # More than 3x promised
                if actual > promised * 3:
                    return True
        
        return False
    
    async def _trigger_fallback_action(self, slice_id: str, violations: List[Dict[str, Any]]):
        """Trigger fallback action for severe violations
        
        Args:
            slice_id: Slice identifier
            violations: List of violations
        """
        # In a real implementation, this would trigger actions like:
        # - Switching to a backup vendor
        # - Scaling up resources
        # - Notifying the customer
        # - Applying penalties to the vendor
        
        # For now, just log the action
        logger.warning(f"Triggering fallback action for slice {slice_id} due to severe violations")
        
        # Reset violation count
        self.violation_counts[slice_id] = 0
    
    def status(self) -> Dict[str, Any]:
        """Get compliance monitor status
        
        Returns:
            Dict: Status information
        """
        return {
            "status": "operational" if self.monitoring_running else "stopped",
            "monitoring_interval": self.monitoring_interval,
            "ndt_available": self.ndt is not None,
            "feedback_loop_available": self.feedback_loop is not None,
            "violation_counts": self.violation_counts
        } 