#!/usr/bin/env python3
"""
Network Slice Selection

This module implements 3GPP TS 23.501 standards for Network Slice Selection
in 5G networks, including Network Slice Selection Assistance Information (NSSAI)
and Network Slice Selection Function (NSSF).
"""

import os
import json
import numpy as np
from typing import Dict, List, Optional, Tuple, Union
from dataclasses import dataclass

# Import AI models if available
try:
    from slicesim.ai.dqn_classifier import TrafficClassifier
    AI_AVAILABLE = True
except ImportError:
    AI_AVAILABLE = False

@dataclass
class SingleNSSAI:
    """Single Network Slice Selection Assistance Information (S-NSSAI)
    
    As defined in 3GPP TS 23.501 Section 5.15.2
    """
    sst: int  # Slice/Service Type (1-255)
    sd: Optional[str] = None  # Slice Differentiator (optional, 6 hex digits)
    
    def __str__(self):
        if self.sd:
            return f"{self.sst}-{self.sd}"
        return f"{self.sst}"
    
    def to_dict(self):
        """Convert to dictionary"""
        return {"sst": self.sst, "sd": self.sd} if self.sd else {"sst": self.sst}

@dataclass
class NSSAI:
    """Network Slice Selection Assistance Information (NSSAI)
    
    As defined in 3GPP TS 23.501 Section 5.15.2
    """
    s_nssais: List[SingleNSSAI]  # List of S-NSSAIs
    
    def to_dict(self):
        """Convert to dictionary"""
        return {"s_nssais": [s.to_dict() for s in self.s_nssais]}

class NetworkSliceSelectionFunction:
    """Network Slice Selection Function (NSSF)
    
    As defined in 3GPP TS 23.501 Section 6.2.14
    """
    
    def __init__(self, config_path: str = None, use_ai: bool = False):
        """Initialize the Network Slice Selection Function
        
        Args:
            config_path (str): Path to configuration file
            use_ai (bool): Whether to use AI for slice selection
        """
        self.config_path = config_path
        self.use_ai = use_ai and AI_AVAILABLE
        
        # Load configuration
        self.config = self._load_config()
        
        # Initialize AI model if available
        self.ai_model = None
        if self.use_ai:
            print("Initializing AI-based Network Slice Selection...")
            self.ai_model = TrafficClassifier()
            print("AI model loaded successfully")
    
    def _load_config(self) -> Dict:
        """Load configuration from file
        
        Returns:
            Dict: Configuration
        """
        default_config = {
            "allowed_nssais": {
                "00101": [  # PLMN ID
                    {"sst": 1},  # eMBB
                    {"sst": 2},  # URLLC
                    {"sst": 3}   # mMTC
                ]
            },
            "slice_mappings": {
                "default": {"sst": 1},  # Default to eMBB
                "voice": {"sst": 1},
                "video": {"sst": 1},
                "gaming": {"sst": 2},
                "iot": {"sst": 3},
                "ar_vr": {"sst": 1},
                "v2x": {"sst": 2},
                "factory": {"sst": 2},
                "smart_city": {"sst": 3},
                "emergency": {"sst": 2}
            },
            "qos_mappings": {
                "1": {  # eMBB
                    "5qi": [1, 2, 3, 4],
                    "default_5qi": 2,
                    "priority_level": 10,
                    "packet_delay_budget": 100,
                    "packet_error_rate": 1e-6
                },
                "2": {  # URLLC
                    "5qi": [80, 82, 83],
                    "default_5qi": 82,
                    "priority_level": 5,
                    "packet_delay_budget": 10,
                    "packet_error_rate": 1e-5
                },
                "3": {  # mMTC
                    "5qi": [5, 6, 7],
                    "default_5qi": 7,
                    "priority_level": 15,
                    "packet_delay_budget": 200,
                    "packet_error_rate": 1e-4
                }
            }
        }
        
        if self.config_path and os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    config = json.load(f)
                return config
            except Exception as e:
                print(f"Error loading configuration: {e}")
        
        return default_config
    
    def get_allowed_nssai(self, plmn_id: str) -> Optional[NSSAI]:
        """Get allowed NSSAI for a PLMN
        
        Args:
            plmn_id (str): PLMN ID
            
        Returns:
            Optional[NSSAI]: Allowed NSSAI if found, None otherwise
        """
        if plmn_id not in self.config["allowed_nssais"]:
            return None
        
        s_nssais = []
        for s_nssai_dict in self.config["allowed_nssais"][plmn_id]:
            sst = s_nssai_dict["sst"]
            sd = s_nssai_dict.get("sd")
            s_nssais.append(SingleNSSAI(sst=sst, sd=sd))
        
        return NSSAI(s_nssais=s_nssais)
    
    def select_slice(self, service_type: str, qos_requirements: Dict, 
                    plmn_id: str = "00101") -> Optional[SingleNSSAI]:
        """Select a network slice based on service type and QoS requirements
        
        Args:
            service_type (str): Type of service (e.g., "voice", "video")
            qos_requirements (Dict): QoS requirements
            plmn_id (str): PLMN ID
            
        Returns:
            Optional[SingleNSSAI]: Selected S-NSSAI if found, None otherwise
        """
        # Get allowed NSSAI for the PLMN
        allowed_nssai = self.get_allowed_nssai(plmn_id)
        if not allowed_nssai:
            return None
        
        # Check if service type is mapped to a specific slice
        if service_type in self.config["slice_mappings"]:
            s_nssai_dict = self.config["slice_mappings"][service_type]
            sst = s_nssai_dict["sst"]
            sd = s_nssai_dict.get("sd")
            
            # Check if the S-NSSAI is allowed
            for allowed_s_nssai in allowed_nssai.s_nssais:
                if allowed_s_nssai.sst == sst and allowed_s_nssai.sd == sd:
                    return allowed_s_nssai
        
        # If service type is not mapped or the mapped S-NSSAI is not allowed,
        # use AI model if available
        if self.use_ai and self.ai_model:
            return self._select_slice_with_ai(service_type, qos_requirements, allowed_nssai)
        
        # Fallback to default slice
        default_s_nssai_dict = self.config["slice_mappings"]["default"]
        sst = default_s_nssai_dict["sst"]
        sd = default_s_nssai_dict.get("sd")
        
        # Check if the default S-NSSAI is allowed
        for allowed_s_nssai in allowed_nssai.s_nssais:
            if allowed_s_nssai.sst == sst and allowed_s_nssai.sd == sd:
                return allowed_s_nssai
        
        # If default S-NSSAI is not allowed, return the first allowed S-NSSAI
        return allowed_nssai.s_nssais[0]
    
    def _select_slice_with_ai(self, service_type: str, qos_requirements: Dict,
                             allowed_nssai: NSSAI) -> SingleNSSAI:
        """Select a network slice using AI
        
        Args:
            service_type (str): Type of service
            qos_requirements (Dict): QoS requirements
            allowed_nssai (NSSAI): Allowed NSSAI
            
        Returns:
            SingleNSSAI: Selected S-NSSAI
        """
        # Convert service type and QoS requirements to features
        features = self._convert_to_features(service_type, qos_requirements)
        
        # Use AI model to classify traffic
        class_idx, _ = self.ai_model.classify(features)
        
        # Map class index to SST
        sst_map = {0: 1, 1: 2, 2: 3}  # 0->eMBB, 1->URLLC, 2->mMTC
        sst = sst_map.get(class_idx[0], 1)  # Default to eMBB (1) if mapping fails
        
        # Find matching S-NSSAI in allowed NSSAI
        for allowed_s_nssai in allowed_nssai.s_nssais:
            if allowed_s_nssai.sst == sst:
                return allowed_s_nssai
        
        # If no matching S-NSSAI found, return the first allowed S-NSSAI
        return allowed_nssai.s_nssais[0]
    
    def _convert_to_features(self, service_type: str, qos_requirements: Dict) -> np.ndarray:
        """Convert service type and QoS requirements to features for AI model
        
        Args:
            service_type (str): Type of service
            qos_requirements (Dict): QoS requirements
            
        Returns:
            np.ndarray: Features for AI model
        """
        # Initialize features
        features = np.zeros(11)
        
        # Service type mapping to traffic load
        service_load_map = {
            "voice": 0.3,
            "video": 0.7,
            "gaming": 0.5,
            "iot": 0.2,
            "ar_vr": 0.9,
            "v2x": 0.6,
            "factory": 0.8,
            "smart_city": 0.4,
            "emergency": 0.8
        }
        
        # Set traffic load based on service type
        features[0] = service_load_map.get(service_type, 0.5)
        
        # Set time of day and day of week (if available)
        features[1] = qos_requirements.get("time_of_day", 0.5)
        features[2] = qos_requirements.get("day_of_week", 0.5)
        
        # Set current allocation (equal by default)
        features[3:6] = [0.33, 0.33, 0.34]
        
        # Set slice utilization based on QoS requirements
        if "latency" in qos_requirements:
            latency = qos_requirements["latency"]
            if latency < 20:  # Low latency -> URLLC
                features[6:9] = [0.3, 0.9, 0.2]
            elif latency > 100:  # High latency tolerance -> mMTC
                features[6:9] = [0.3, 0.2, 0.9]
            else:  # Medium latency -> eMBB
                features[6:9] = [0.9, 0.3, 0.2]
        else:
            features[6:9] = [0.5, 0.5, 0.5]
        
        # Set client count and base station count
        features[9] = qos_requirements.get("client_density", 0.5)
        features[10] = 0.5  # Default base station count
        
        return features
    
    def get_qos_parameters(self, s_nssai: SingleNSSAI) -> Dict:
        """Get QoS parameters for a network slice
        
        Args:
            s_nssai (SingleNSSAI): S-NSSAI
            
        Returns:
            Dict: QoS parameters
        """
        sst = str(s_nssai.sst)
        if sst not in self.config["qos_mappings"]:
            # Default to eMBB if not found
            sst = "1"
        
        return self.config["qos_mappings"][sst]

# Example usage
if __name__ == "__main__":
    # Create Network Slice Selection Function
    nssf = NetworkSliceSelectionFunction(use_ai=True)
    
    # Get allowed NSSAI for a PLMN
    allowed_nssai = nssf.get_allowed_nssai("00101")
    print("Allowed NSSAI:")
    for s_nssai in allowed_nssai.s_nssais:
        print(f"  SST: {s_nssai.sst}, SD: {s_nssai.sd}")
    
    # Test slice selection for different service types
    service_types = ["voice", "video", "gaming", "iot", "ar_vr", "v2x", "factory", "smart_city", "emergency"]
    
    print("\nSlice Selection:")
    for service_type in service_types:
        # Define QoS requirements
        if service_type in ["gaming", "v2x", "factory", "emergency"]:
            qos_requirements = {"latency": 10, "client_density": 0.3}
        elif service_type in ["iot", "smart_city"]:
            qos_requirements = {"latency": 200, "client_density": 0.9}
        else:
            qos_requirements = {"latency": 50, "client_density": 0.5}
        
        # Select slice
        selected_s_nssai = nssf.select_slice(service_type, qos_requirements)
        
        # Get QoS parameters
        qos_parameters = nssf.get_qos_parameters(selected_s_nssai)
        
        print(f"  Service: {service_type}")
        print(f"    Selected S-NSSAI: SST={selected_s_nssai.sst}, SD={selected_s_nssai.sd}")
        print(f"    5QI: {qos_parameters['default_5qi']}")
        print(f"    Priority Level: {qos_parameters['priority_level']}")
        print(f"    Packet Delay Budget: {qos_parameters['packet_delay_budget']} ms")
        print(f"    Packet Error Rate: {qos_parameters['packet_error_rate']}")
        print() 