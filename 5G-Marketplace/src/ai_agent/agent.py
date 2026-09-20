"""
AI Agent Module

This module provides an AI agent for slice classification and vendor selection.
It uses pre-trained models for slice classification and vendor offer scoring.
"""

import os
import sys
import logging
import numpy as np
import json
import requests
from typing import Dict, List, Any, Optional, Tuple

# Try to import tensorflow, but make it optional
try:
    import tensorflow as tf
except ImportError:
    tf = None
    logging.warning("TensorFlow not available. Some features may not work.")

# Configure logging
logger = logging.getLogger(__name__)

class AIAgent:
    """AI Agent for slice classification and vendor selection"""
    
    def __init__(self, 
                 model_dir: str = None, 
                 ollama_api_url: str = "http://localhost:11434/api/generate"):
        """Initialize the AI agent
        
        Args:
            model_dir: Directory containing pre-trained models
            ollama_api_url: URL for Ollama API
        """
        # Get the absolute path to the models directory
        if model_dir is None:
            # Get the current file's directory
            current_dir = os.path.dirname(os.path.abspath(__file__))
            # Go up to the workspace root
            workspace_dir = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
            # Set the model directory to the 5G-Network-Slicing/models directory
            self.model_dir = os.path.join(workspace_dir, "5G-Network-Slicing", "models")
        else:
            self.model_dir = model_dir
            
        logger.info(f"Using model directory: {self.model_dir}")
        
        self.ollama_api_url = ollama_api_url
        self.ollama_available = False
        self.slice_classifier = None
        self.allocation_predictor = None
        self.vendor_ratings = {}
        
        # Path to pre-trained models
        self.dqn_model_path = os.path.join(self.model_dir, "dqn_model_20250601_012010")
        self.lstm_model_path = os.path.join(self.model_dir, "lstm_model_20250601_011235")
        
        # Feature names for the models
        self.feature_names = [
            'traffic_load', 'hour_of_day', 'day_of_week',
            'embb_allocation', 'urllc_allocation', 'mmtc_allocation',
            'embb_utilization', 'urllc_utilization', 'mmtc_utilization',
            'client_count', 'bs_count'
        ]
        
        # Slice type mapping
        self.slice_types = {
            0: "eMBB",
            1: "URLLC",
            2: "mMTC"
        }
    
    async def initialize(self):
        """Initialize the AI agent"""
        logger.info("Initializing AI agent")
        
        # Check if Ollama is available
        self.ollama_available = self._check_ollama()
        
        # Load pre-trained models
        self._load_models()
        
        logger.info("AI agent initialization complete")
    
    def _check_ollama(self) -> bool:
        """Check if Ollama is available
        
        Returns:
            bool: True if Ollama is available, False otherwise
        """
        try:
            # Simple test request to Ollama
            response = requests.post(
                self.ollama_api_url,
                json={
                    "model": "llama2",
                    "prompt": "Hello",
                    "stream": False
                },
                timeout=5
            )
            
            if response.status_code == 200:
                logger.info("Ollama is available")
                return True
            else:
                logger.warning(f"Ollama returned status code {response.status_code}")
                return False
        except Exception as e:
            logger.warning(f"Ollama is not available: {str(e)}")
            return False
    
    def _load_models(self):
        """Load pre-trained models"""
        # Check if model directory exists
        if not os.path.exists(self.model_dir):
            logger.error(f"Model directory not found: {self.model_dir}")
            return
            
        # Load DQN classifier model
        try:
            if os.path.exists(self.dqn_model_path):
                logger.info(f"Attempting to load DQN model from {self.dqn_model_path}")
                # List files in the directory to verify content
                files = os.listdir(self.dqn_model_path)
                logger.info(f"DQN model directory contains: {files}")
                
                # Check for saved_model.pb which indicates a valid TF model
                if "saved_model.pb" in files:
                    self.slice_classifier = tf.keras.models.load_model(self.dqn_model_path)
                    logger.info(f"Successfully loaded DQN classifier from {self.dqn_model_path}")
                else:
                    logger.warning(f"DQN model directory exists but doesn't contain saved_model.pb")
            else:
                logger.warning(f"DQN model not found at {self.dqn_model_path}")
        except Exception as e:
            logger.error(f"Error loading DQN model: {str(e)}")
            logger.exception("Detailed error information:")
        
        # Load LSTM predictor model
        try:
            if os.path.exists(self.lstm_model_path):
                logger.info(f"Attempting to load LSTM model from {self.lstm_model_path}")
                # List files in the directory to verify content
                files = os.listdir(self.lstm_model_path)
                logger.info(f"LSTM model directory contains: {files}")
                
                # Check for saved_model.pb which indicates a valid TF model
                if "saved_model.pb" in files:
                    self.allocation_predictor = tf.keras.models.load_model(self.lstm_model_path)
                    logger.info(f"Successfully loaded LSTM predictor from {self.lstm_model_path}")
                else:
                    logger.warning(f"LSTM model directory exists but doesn't contain saved_model.pb")
            else:
                logger.warning(f"LSTM model not found at {self.lstm_model_path}")
        except Exception as e:
            logger.error(f"Error loading LSTM model: {str(e)}")
            logger.exception("Detailed error information:")
    
    async def classify_slice_type(self, qos_requirements: Dict[str, Any]) -> str:
        """Classify slice type based on QoS requirements
        
        Args:
            qos_requirements: QoS requirements
            
        Returns:
            str: Slice type (eMBB, URLLC, mMTC)
        """
        try:
            # Try using the pre-trained classifier if available
            if self.slice_classifier is not None:
                # Extract features from QoS requirements
                features = self._extract_features_from_qos(qos_requirements)
                
                # Make prediction
                prediction = self.slice_classifier.predict(np.array([features]))
                class_idx = np.argmax(prediction, axis=1)[0]
                
                # Map class index to slice type
                slice_type = self.slice_types.get(class_idx, "eMBB")
                
                logger.info(f"Classified slice type using DQN model: {slice_type}")
                return slice_type
            
            # If model not available, try using Ollama
            elif self.ollama_available:
                # Prepare prompt for Ollama
                prompt = self._prepare_classification_prompt(qos_requirements)
                
                # Call Ollama API
                response = requests.post(
                    self.ollama_api_url,
                    json={
                        "model": "llama2",
                        "prompt": prompt,
                        "stream": False
                    }
                )
                
                if response.status_code == 200:
                    # Parse response
                    result = response.json()
                    slice_type = self._parse_ollama_classification(result["response"])
                    logger.info(f"Classified slice type using Ollama: {slice_type}")
                    return slice_type
            
            # Fall back to rule-based classification
            return self._rule_based_classification(qos_requirements)
        except Exception as e:
            logger.error(f"Error in slice classification: {str(e)}")
            # Fall back to rule-based classification
            return self._rule_based_classification(qos_requirements)
    
    def _extract_features_from_qos(self, qos_requirements: Dict[str, Any]) -> np.ndarray:
        """Extract features from QoS requirements for model input
        
        Args:
            qos_requirements: QoS requirements
            
        Returns:
            np.ndarray: Features for model input
        """
        # Extract relevant QoS parameters
        latency_ms = qos_requirements.get("latency_ms", 50)
        bandwidth_mbps = qos_requirements.get("bandwidth_mbps", 100)
        reliability_percent = qos_requirements.get("reliability_percent", 99.9)
        
        # Normalize values
        normalized_latency = min(1.0, latency_ms / 200.0)  # Normalize to [0,1]
        normalized_bandwidth = min(1.0, bandwidth_mbps / 1000.0)  # Normalize to [0,1]
        normalized_reliability = (reliability_percent - 99.0) / 1.0 if reliability_percent >= 99.0 else 0.0  # Normalize to [0,1]
        
        # Create feature vector matching the expected input
        # Default values for features we don't have
        traffic_load = 0.5
        hour_of_day = 12.0 / 24.0  # Normalized hour
        day_of_week = 3.0 / 7.0  # Normalized day (Wednesday)
        
        # Initial allocations (equal)
        embb_allocation = 0.33
        urllc_allocation = 0.33
        mmtc_allocation = 0.34
        
        # Utilization based on QoS requirements
        embb_utilization = normalized_bandwidth
        urllc_utilization = 1.0 - normalized_latency  # Lower latency = higher utilization
        mmtc_utilization = normalized_reliability
        
        # Client and base station counts (defaults)
        client_count = 0.5  # Normalized
        bs_count = 0.5  # Normalized
        
        # Create feature vector
        features = np.array([
            traffic_load, hour_of_day, day_of_week,
            embb_allocation, urllc_allocation, mmtc_allocation,
            embb_utilization, urllc_utilization, mmtc_utilization,
            client_count, bs_count
        ])
        
        return features
    
    def _prepare_classification_prompt(self, qos_requirements: Dict[str, Any]) -> str:
        """Prepare prompt for slice classification using Ollama
        
        Args:
            qos_requirements: QoS requirements
            
        Returns:
            str: Prompt for Ollama
        """
        return f"""
        You are a 5G network slice classifier. Based on the following QoS requirements,
        classify the request as one of these slice types: eMBB, URLLC, or mMTC.
        
        QoS Requirements:
        - Latency: {qos_requirements.get('latency_ms', 'Not specified')} ms
        - Bandwidth: {qos_requirements.get('bandwidth_mbps', 'Not specified')} Mbps
        - Reliability: {qos_requirements.get('reliability_percent', 'Not specified')}%
        - Availability: {qos_requirements.get('availability_percent', 'Not specified')}%
        - Jitter: {qos_requirements.get('jitter_ms', 'Not specified')} ms
        - Packet Loss: {qos_requirements.get('packet_loss_percent', 'Not specified')}%
        
        Respond with only one of: eMBB, URLLC, or mMTC.
        """
    
    def _parse_ollama_classification(self, response: str) -> str:
        """Parse Ollama response for slice classification
        
        Args:
            response: Ollama response
            
        Returns:
            str: Slice type (eMBB, URLLC, mMTC)
        """
        response = response.strip().upper()
        
        if "EMBB" in response:
            return "eMBB"
        elif "URLLC" in response:
            return "URLLC"
        elif "MMTC" in response:
            return "mMTC"
        else:
            # Default to eMBB if response is unclear
            return "eMBB"
    
    def _rule_based_classification(self, qos_requirements: Dict[str, Any]) -> str:
        """Rule-based slice classification
        
        Args:
            qos_requirements: QoS requirements
            
        Returns:
            str: Slice type (eMBB, URLLC, mMTC)
        """
        # Extract QoS parameters with defaults
        latency_ms = qos_requirements.get("latency_ms", 50)
        bandwidth_mbps = qos_requirements.get("bandwidth_mbps", 100)
        reliability_percent = qos_requirements.get("reliability_percent", 99.9)
        device_density = qos_requirements.get("device_density", 1000)  # devices per km²
        
        # URLLC: Low latency, high reliability
        if latency_ms <= 10 and reliability_percent >= 99.999:
            return "URLLC"
        
        # mMTC: High device density, lower bandwidth requirements
        elif device_density >= 10000 and bandwidth_mbps <= 50:
            return "mMTC"
        
        # eMBB: High bandwidth
        elif bandwidth_mbps >= 100:
            return "eMBB"
        
        # Default to eMBB
        else:
            return "eMBB"
    
    async def score_vendor_offer(self, 
                                offer: Dict[str, Any], 
                                qos_requirements: Dict[str, Any],
                                customer_preferences: Dict[str, Any] = None) -> float:
        """Score vendor offer against QoS requirements
        
        Args:
            offer: Vendor offer
            qos_requirements: QoS requirements
            customer_preferences: Customer preferences
            
        Returns:
            float: Score (0-100)
        """
        try:
            # Default customer preferences if not provided
            if customer_preferences is None:
                customer_preferences = {
                    "price_weight": 0.3,
                    "qos_weight": 0.5,
                    "reputation_weight": 0.2
                }
            
            # Calculate QoS match score
            qos_score = self._calculate_qos_match(offer, qos_requirements)
            
            # Calculate price score (lower price is better)
            price_score = self._calculate_price_score(offer)
            
            # Get vendor reputation score
            vendor_id = offer.get("vendor_id")
            reputation_score = self.vendor_ratings.get(vendor_id, 5.0) / 10.0  # Normalize to [0,1]
            
            # Calculate weighted score
            weighted_score = (
                qos_score * customer_preferences.get("qos_weight", 0.5) +
                price_score * customer_preferences.get("price_weight", 0.3) +
                reputation_score * customer_preferences.get("reputation_weight", 0.2)
            )
            
            # Scale to 0-100
            final_score = weighted_score * 100
            
            logger.info(f"Scored vendor offer: {final_score:.2f} (QoS: {qos_score:.2f}, Price: {price_score:.2f}, Reputation: {reputation_score:.2f})")
            return final_score
        except Exception as e:
            logger.error(f"Error scoring vendor offer: {str(e)}")
            return 50.0  # Default middle score
    
    def _calculate_qos_match(self, offer: Dict[str, Any], qos_requirements: Dict[str, Any]) -> float:
        """Calculate QoS match score
        
        Args:
            offer: Vendor offer
            qos_requirements: QoS requirements
            
        Returns:
            float: QoS match score (0-1)
        """
        # Extract QoS parameters from offer
        offer_qos = offer.get("qos_parameters", {})
        
        # Calculate match for each parameter
        scores = []
        
        # Latency (lower is better)
        if "latency_ms" in qos_requirements and "latency_ms" in offer_qos:
            req_latency = qos_requirements["latency_ms"]
            offer_latency = offer_qos["latency_ms"]
            if offer_latency <= req_latency:
                scores.append(1.0)
            else:
                # Score decreases as latency exceeds requirement
                scores.append(max(0.0, 1.0 - (offer_latency - req_latency) / req_latency))
        
        # Bandwidth (higher is better)
        if "bandwidth_mbps" in qos_requirements and "bandwidth_mbps" in offer_qos:
            req_bandwidth = qos_requirements["bandwidth_mbps"]
            offer_bandwidth = offer_qos["bandwidth_mbps"]
            if offer_bandwidth >= req_bandwidth:
                scores.append(1.0)
            else:
                # Score decreases as bandwidth falls below requirement
                scores.append(max(0.0, offer_bandwidth / req_bandwidth))
        
        # Reliability (higher is better)
        if "reliability_percent" in qos_requirements and "reliability_percent" in offer_qos:
            req_reliability = qos_requirements["reliability_percent"]
            offer_reliability = offer_qos["reliability_percent"]
            if offer_reliability >= req_reliability:
                scores.append(1.0)
            else:
                # Score decreases as reliability falls below requirement
                # More sensitive to small differences since reliability is usually >99%
                diff = req_reliability - offer_reliability
                scores.append(max(0.0, 1.0 - (diff / 1.0)))
        
        # Availability (higher is better)
        if "availability_percent" in qos_requirements and "availability_percent" in offer_qos:
            req_availability = qos_requirements["availability_percent"]
            offer_availability = offer_qos["availability_percent"]
            if offer_availability >= req_availability:
                scores.append(1.0)
            else:
                # Score decreases as availability falls below requirement
                # More sensitive to small differences since availability is usually >99%
                diff = req_availability - offer_availability
                scores.append(max(0.0, 1.0 - (diff / 1.0)))
        
        # Jitter (lower is better)
        if "jitter_ms" in qos_requirements and "jitter_ms" in offer_qos:
            req_jitter = qos_requirements["jitter_ms"]
            offer_jitter = offer_qos["jitter_ms"]
            if offer_jitter <= req_jitter:
                scores.append(1.0)
            else:
                # Score decreases as jitter exceeds requirement
                scores.append(max(0.0, 1.0 - (offer_jitter - req_jitter) / req_jitter))
        
        # Packet loss (lower is better)
        if "packet_loss_percent" in qos_requirements and "packet_loss_percent" in offer_qos:
            req_packet_loss = qos_requirements["packet_loss_percent"]
            offer_packet_loss = offer_qos["packet_loss_percent"]
            if offer_packet_loss <= req_packet_loss:
                scores.append(1.0)
            else:
                # Score decreases as packet loss exceeds requirement
                scores.append(max(0.0, 1.0 - (offer_packet_loss - req_packet_loss) / (req_packet_loss + 0.01)))
        
        # Calculate average score
        if scores:
            return sum(scores) / len(scores)
        else:
            return 0.5  # Default middle score
    
    def _calculate_price_score(self, offer: Dict[str, Any]) -> float:
        """Calculate price score
        
        Args:
            offer: Vendor offer
            
        Returns:
            float: Price score (0-1), higher is better (lower price)
        """
        # Extract price from offer
        price = offer.get("price_per_hour", 0)
        
        # Simple price scoring function
        # Assumes price range of 0-100 per hour
        # Lower price is better
        if price <= 0:
            return 1.0
        elif price >= 100:
            return 0.0
        else:
            return 1.0 - (price / 100.0)
    
    async def update_vendor_ratings(self, vendor_ratings: Dict[str, float]):
        """Update vendor ratings
        
        Args:
            vendor_ratings: Vendor ratings
        """
        self.vendor_ratings = vendor_ratings
        logger.info(f"Updated vendor ratings for {len(vendor_ratings)} vendors")
    
    def status(self) -> Dict[str, Any]:
        """
        Get the status of the AI agent.
        
        Returns:
            Dictionary with status information
        """
        # Check if models are loaded
        dqn_status = self.slice_classifier is not None
        lstm_status = self.allocation_predictor is not None
        
        # Determine overall status
        if dqn_status and lstm_status:
            status = "operational"
            message = "All models loaded successfully"
        elif dqn_status or lstm_status:
            status = "degraded"
            message = "Some models loaded, operating in degraded mode"
        else:
            status = "fallback"
            message = "No models loaded, operating in fallback mode"
        
        return {
            "status": status,
            "message": message,
            "models": {
                "dqn_classifier": {
                    "loaded": dqn_status,
                    "path": self.dqn_model_path
                },
                "lstm_predictor": {
                    "loaded": lstm_status,
                    "path": self.lstm_model_path
                }
            },
            "ollama": {
                "available": self.ollama_available,
                "url": self.ollama_api_url
            },
            "model_dir": self.model_dir,
            "model_dir_exists": os.path.exists(self.model_dir),
            "fallback_mode": not (self.ollama_available or self.slice_classifier is not None),
            "vendor_ratings_count": len(self.vendor_ratings)
        } 