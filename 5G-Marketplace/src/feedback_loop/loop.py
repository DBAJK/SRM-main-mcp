"""
Feedback Loop Module

This module implements a feedback loop that learns from slice performance data
and improves the AI agent's decision making over time.
"""

import logging
import asyncio
import json
import os
from datetime import datetime
from typing import Dict, List, Any, Optional

# Configure logging
logger = logging.getLogger(__name__)

class FeedbackLoop:
    """Feedback loop for learning from slice performance data"""
    
    def __init__(self, data_directory: str = "data/feedback"):
        """Initialize the feedback loop
        
        Args:
            data_directory: Directory for storing feedback data
        """
        self.data_directory = data_directory
        self.ai_agent = None
        self.vendor_registry = None
        self.feedback_running = False
        self.feedback_task = None
        self.processing_interval = 3600  # Process feedback hourly
        self.vendor_ratings = {}
        self.vendor_violations = {}
        self.learning_enabled = True
        
        # Ensure data directory exists
        os.makedirs(self.data_directory, exist_ok=True)
        
        # Load existing vendor ratings if available
        self._load_vendor_ratings()
    
    def register_ai_agent(self, ai_agent):
        """Register the AI agent
        
        Args:
            ai_agent: AI agent instance
        """
        self.ai_agent = ai_agent
        logger.info("AI agent registered with feedback loop")
    
    def register_vendor_registry(self, vendor_registry):
        """Register the vendor registry
        
        Args:
            vendor_registry: Vendor registry instance
        """
        self.vendor_registry = vendor_registry
        logger.info("Vendor registry registered with feedback loop")
    
    async def start_feedback_loop(self):
        """Start the feedback loop"""
        if self.feedback_running:
            logger.warning("Feedback loop already running")
            return
        
        self.feedback_running = True
        self.feedback_task = asyncio.create_task(self._run_feedback_loop())
        logger.info("Feedback loop started")
    
    async def stop_feedback_loop(self):
        """Stop the feedback loop"""
        if not self.feedback_running:
            logger.warning("Feedback loop not running")
            return
        
        self.feedback_running = False
        if self.feedback_task:
            self.feedback_task.cancel()
            try:
                await self.feedback_task
            except asyncio.CancelledError:
                pass
        logger.info("Feedback loop stopped")
    
    async def _run_feedback_loop(self):
        """Run the feedback loop"""
        try:
            while self.feedback_running:
                if self.learning_enabled:
                    # Process accumulated feedback
                    await self._process_feedback()
                    
                    # Update AI agent with new insights
                    await self._update_ai_agent()
                
                # Wait before next processing cycle
                await asyncio.sleep(self.processing_interval)
        except asyncio.CancelledError:
            logger.info("Feedback loop cancelled")
        except Exception as e:
            logger.error(f"Error in feedback loop: {str(e)}")
    
    async def report_violations(self, slice_id: str, vendor_id: str, violations: List[Dict[str, Any]]):
        """Report SLA violations for a slice
        
        Args:
            slice_id: Slice identifier
            vendor_id: Vendor identifier
            violations: List of violations
        """
        try:
            # Log the violation report
            logger.info(f"Received violation report for slice {slice_id} from vendor {vendor_id}")
            
            # Store violation data
            timestamp = datetime.now().isoformat()
            violation_data = {
                "slice_id": slice_id,
                "vendor_id": vendor_id,
                "timestamp": timestamp,
                "violations": violations
            }
            
            # Save to file
            filename = f"{self.data_directory}/violation_{slice_id}_{timestamp.replace(':', '-')}.json"
            with open(filename, 'w') as f:
                json.dump(violation_data, f, indent=2)
            
            # Update vendor violations count
            if vendor_id not in self.vendor_violations:
                self.vendor_violations[vendor_id] = []
            
            self.vendor_violations[vendor_id].append(violation_data)
            
            # Update vendor rating immediately
            await self._update_vendor_rating(vendor_id)
            
            logger.info(f"Violation report saved for slice {slice_id}")
        except Exception as e:
            logger.error(f"Error reporting violations: {str(e)}")
    
    async def report_successful_deployment(self, slice_id: str, vendor_id: str, qos_promised: Dict[str, Any]):
        """Report successful slice deployment
        
        Args:
            slice_id: Slice identifier
            vendor_id: Vendor identifier
            qos_promised: Promised QoS values
        """
        try:
            # Log the success report
            logger.info(f"Received successful deployment report for slice {slice_id} from vendor {vendor_id}")
            
            # Store success data
            timestamp = datetime.now().isoformat()
            success_data = {
                "slice_id": slice_id,
                "vendor_id": vendor_id,
                "timestamp": timestamp,
                "qos_promised": qos_promised,
                "type": "deployment"
            }
            
            # Save to file
            filename = f"{self.data_directory}/success_{slice_id}_{timestamp.replace(':', '-')}.json"
            with open(filename, 'w') as f:
                json.dump(success_data, f, indent=2)
            
            # Update vendor rating (slight positive impact)
            if vendor_id not in self.vendor_ratings:
                self.vendor_ratings[vendor_id] = 5.0  # Default rating
            
            # Small positive adjustment for successful deployment
            self.vendor_ratings[vendor_id] = min(10.0, self.vendor_ratings[vendor_id] + 0.1)
            
            # Save updated ratings
            self._save_vendor_ratings()
            
            logger.info(f"Success report saved for slice {slice_id}")
        except Exception as e:
            logger.error(f"Error reporting successful deployment: {str(e)}")
    
    async def report_slice_termination(self, slice_id: str, vendor_id: str, performance_data: Dict[str, Any]):
        """Report slice termination with performance data
        
        Args:
            slice_id: Slice identifier
            vendor_id: Vendor identifier
            performance_data: Performance data for the slice lifetime
        """
        try:
            # Log the termination report
            logger.info(f"Received termination report for slice {slice_id} from vendor {vendor_id}")
            
            # Store termination data
            timestamp = datetime.now().isoformat()
            termination_data = {
                "slice_id": slice_id,
                "vendor_id": vendor_id,
                "timestamp": timestamp,
                "performance_data": performance_data,
                "type": "termination"
            }
            
            # Save to file
            filename = f"{self.data_directory}/termination_{slice_id}_{timestamp.replace(':', '-')}.json"
            with open(filename, 'w') as f:
                json.dump(termination_data, f, indent=2)
            
            # Update vendor rating based on overall performance
            await self._update_vendor_rating_from_performance(vendor_id, performance_data)
            
            logger.info(f"Termination report saved for slice {slice_id}")
        except Exception as e:
            logger.error(f"Error reporting slice termination: {str(e)}")
    
    async def _update_vendor_rating(self, vendor_id: str):
        """Update vendor rating based on violations
        
        Args:
            vendor_id: Vendor identifier
        """
        if vendor_id not in self.vendor_violations:
            return
        
        if vendor_id not in self.vendor_ratings:
            self.vendor_ratings[vendor_id] = 5.0  # Default rating
        
        # Count recent violations (last 24 hours)
        recent_violations = 0
        now = datetime.now()
        
        for violation_data in self.vendor_violations[vendor_id]:
            try:
                violation_time = datetime.fromisoformat(violation_data["timestamp"])
                time_diff = now - violation_time
                
                # Count violations from last 24 hours
                if time_diff.total_seconds() < 86400:  # 24 hours in seconds
                    recent_violations += len(violation_data["violations"])
            except Exception:
                continue
        
        # Adjust rating based on recent violations
        if recent_violations > 0:
            # Calculate penalty (more violations = bigger penalty)
            penalty = min(0.5, recent_violations * 0.05)
            self.vendor_ratings[vendor_id] = max(1.0, self.vendor_ratings[vendor_id] - penalty)
            
            logger.info(f"Updated vendor {vendor_id} rating to {self.vendor_ratings[vendor_id]} due to {recent_violations} recent violations")
        
        # Save updated ratings
        self._save_vendor_ratings()
    
    async def _update_vendor_rating_from_performance(self, vendor_id: str, performance_data: Dict[str, Any]):
        """Update vendor rating based on overall performance
        
        Args:
            vendor_id: Vendor identifier
            performance_data: Performance data
        """
        if vendor_id not in self.vendor_ratings:
            self.vendor_ratings[vendor_id] = 5.0  # Default rating
        
        # Extract performance metrics
        uptime_percentage = performance_data.get("uptime_percentage", 0)
        qos_compliance = performance_data.get("qos_compliance_percentage", 0)
        
        # Calculate rating adjustment
        adjustment = 0
        
        # Adjust based on uptime
        if uptime_percentage >= 99.9:
            adjustment += 0.3
        elif uptime_percentage >= 99.5:
            adjustment += 0.2
        elif uptime_percentage >= 99.0:
            adjustment += 0.1
        elif uptime_percentage < 98.0:
            adjustment -= 0.2
        
        # Adjust based on QoS compliance
        if qos_compliance >= 99.0:
            adjustment += 0.3
        elif qos_compliance >= 95.0:
            adjustment += 0.2
        elif qos_compliance >= 90.0:
            adjustment += 0.1
        elif qos_compliance < 85.0:
            adjustment -= 0.3
        
        # Apply adjustment
        self.vendor_ratings[vendor_id] = max(1.0, min(10.0, self.vendor_ratings[vendor_id] + adjustment))
        
        logger.info(f"Updated vendor {vendor_id} rating to {self.vendor_ratings[vendor_id]} based on performance data")
        
        # Save updated ratings
        self._save_vendor_ratings()
    
    async def _process_feedback(self):
        """Process accumulated feedback data"""
        try:
            logger.info("Processing feedback data")
            
            # Process all vendor violations
            for vendor_id in self.vendor_violations:
                await self._update_vendor_rating(vendor_id)
            
            # Clean up old violation data
            self._cleanup_old_data()
            
            logger.info("Feedback data processed")
        except Exception as e:
            logger.error(f"Error processing feedback: {str(e)}")
    
    async def _update_ai_agent(self):
        """Update AI agent with new insights"""
        if not self.ai_agent:
            return
        
        try:
            logger.info("Updating AI agent with feedback insights")
            
            # In a real implementation, this would update the AI agent's model
            # with new insights from the feedback loop
            
            # For now, just pass the vendor ratings to the AI agent
            if hasattr(self.ai_agent, 'update_vendor_ratings'):
                await self.ai_agent.update_vendor_ratings(self.vendor_ratings)
                logger.info("AI agent updated with vendor ratings")
        except Exception as e:
            logger.error(f"Error updating AI agent: {str(e)}")
    
    def _cleanup_old_data(self):
        """Clean up old feedback data"""
        try:
            # Clean up files older than 30 days
            now = datetime.now()
            cleanup_count = 0
            
            for filename in os.listdir(self.data_directory):
                file_path = os.path.join(self.data_directory, filename)
                
                # Skip if not a file
                if not os.path.isfile(file_path):
                    continue
                
                # Get file modification time
                file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                time_diff = now - file_time
                
                # Remove if older than 30 days
                if time_diff.days > 30:
                    os.remove(file_path)
                    cleanup_count += 1
            
            if cleanup_count > 0:
                logger.info(f"Cleaned up {cleanup_count} old feedback data files")
        except Exception as e:
            logger.error(f"Error cleaning up old data: {str(e)}")
    
    def _load_vendor_ratings(self):
        """Load vendor ratings from file"""
        try:
            ratings_file = os.path.join(self.data_directory, "vendor_ratings.json")
            
            if os.path.exists(ratings_file):
                with open(ratings_file, 'r') as f:
                    self.vendor_ratings = json.load(f)
                logger.info(f"Loaded ratings for {len(self.vendor_ratings)} vendors")
        except Exception as e:
            logger.error(f"Error loading vendor ratings: {str(e)}")
    
    def _save_vendor_ratings(self):
        """Save vendor ratings to file"""
        try:
            ratings_file = os.path.join(self.data_directory, "vendor_ratings.json")
            
            with open(ratings_file, 'w') as f:
                json.dump(self.vendor_ratings, f, indent=2)
            
            logger.debug(f"Saved ratings for {len(self.vendor_ratings)} vendors")
        except Exception as e:
            logger.error(f"Error saving vendor ratings: {str(e)}")
    
    def get_vendor_rating(self, vendor_id: str) -> float:
        """Get vendor rating
        
        Args:
            vendor_id: Vendor identifier
            
        Returns:
            float: Vendor rating (1-10)
        """
        return self.vendor_ratings.get(vendor_id, 5.0)  # Default rating is 5.0
    
    def status(self) -> Dict[str, Any]:
        """Get feedback loop status
        
        Returns:
            Dict: Status information
        """
        return {
            "status": "operational" if self.feedback_running else "stopped",
            "learning_enabled": self.learning_enabled,
            "processing_interval": self.processing_interval,
            "ai_agent_available": self.ai_agent is not None,
            "vendor_registry_available": self.vendor_registry is not None,
            "vendor_ratings_count": len(self.vendor_ratings)
        } 