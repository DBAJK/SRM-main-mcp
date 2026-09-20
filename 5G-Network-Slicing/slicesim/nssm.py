#!/usr/bin/env python3
"""
Network Slice Subnet Management (NSSM)

This module implements 3GPP TS 28.530 and TS 28.531 standards for
Network Slice Subnet Management in 5G networks.
"""

import os
import uuid
import json
import time
from enum import Enum
from typing import Dict, List, Optional, Tuple, Union
from dataclasses import dataclass, field, asdict

class SliceState(Enum):
    """Network Slice states as defined in 3GPP TS 28.530"""
    NOT_INSTANTIATED = "NOT_INSTANTIATED"
    INSTANTIATING = "INSTANTIATING"
    INSTANTIATED = "INSTANTIATED"
    ACTIVATING = "ACTIVATING" 
    ACTIVE = "ACTIVE"
    DEACTIVATING = "DEACTIVATING"
    DEACTIVATED = "DEACTIVATED"
    TERMINATING = "TERMINATING"
    TERMINATED = "TERMINATED"

class SliceType(Enum):
    """Standardized Slice/Service Types (SST) as defined in 3GPP TS 23.501"""
    EMBB = 1  # Enhanced Mobile Broadband
    URLLC = 2  # Ultra Reliable Low Latency Communications
    MMTC = 3  # Massive Machine Type Communications
    # Values 4-127 are reserved for standard use
    # Values 128-255 are for operator-specific use

@dataclass
class SliceProfile:
    """Network Slice Profile as defined in 3GPP TS 28.531"""
    sNSSAI: Dict[str, Union[int, str]]  # S-NSSAI (SST and optional SD)
    pLMNIdList: List[str]  # PLMN IDs where this slice is available
    perfReq: Dict[str, Union[int, float]]  # Performance requirements
    maxNumberOfUEs: int
    coverageAreaTAList: List[str]  # Tracking Areas
    latency: int  # in milliseconds
    uEMobilityLevel: str  # "STATIONARY", "NOMADIC", "RESTRICTED_MOBILITY", "FULLY_MOBILITY"
    resourceSharingLevel: str  # "SHARED", "NON_SHARED"
    
    # QoS parameters according to 3GPP TS 23.501
    fiveQIValue: int = 0  # 5G QoS Identifier
    priorityLevel: int = 0
    packetDelayBudget: int = 0  # in milliseconds
    packetErrorRate: float = 0.0
    
    def to_dict(self):
        """Convert to dictionary"""
        return asdict(self)

@dataclass
class NetworkSliceSubnet:
    """Network Slice Subnet Instance (NSSI) as defined in 3GPP TS 28.530"""
    id: str  # UUID for this slice subnet
    name: str
    description: str
    state: SliceState
    sliceType: SliceType
    profile: SliceProfile
    managedFunctions: List[str] = field(default_factory=list)  # Network functions in this slice
    administrativeDomain: str = ""
    userPlaneResources: Dict = field(default_factory=dict)
    controlPlaneResources: Dict = field(default_factory=dict)
    creationTime: float = field(default_factory=time.time)
    modificationTime: float = field(default_factory=time.time)
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "state": self.state.value,
            "sliceType": self.sliceType.value,
            "profile": self.profile.to_dict(),
            "managedFunctions": self.managedFunctions,
            "administrativeDomain": self.administrativeDomain,
            "userPlaneResources": self.userPlaneResources,
            "controlPlaneResources": self.controlPlaneResources,
            "creationTime": self.creationTime,
            "modificationTime": self.modificationTime
        }

class NetworkSliceSubnetManager:
    """Manager for Network Slice Subnet Instances (NSSI) according to 3GPP TS 28.531"""
    
    def __init__(self, storage_path: str = None):
        """Initialize the Network Slice Subnet Manager
        
        Args:
            storage_path (str): Path to store slice data
        """
        self.storage_path = storage_path
        self.slice_subnets: Dict[str, NetworkSliceSubnet] = {}
        
        # Load existing slice subnets if storage path is provided
        if storage_path and os.path.exists(storage_path):
            self._load_slice_subnets()
    
    def create_slice_subnet(self, name: str, description: str, slice_type: SliceType, 
                           profile: SliceProfile) -> NetworkSliceSubnet:
        """Create a new Network Slice Subnet Instance
        
        Args:
            name (str): Name of the slice subnet
            description (str): Description of the slice subnet
            slice_type (SliceType): Type of slice (eMBB, URLLC, mMTC)
            profile (SliceProfile): Slice profile with requirements
            
        Returns:
            NetworkSliceSubnet: Created slice subnet
        """
        # Generate unique ID
        slice_id = str(uuid.uuid4())
        
        # Create slice subnet
        slice_subnet = NetworkSliceSubnet(
            id=slice_id,
            name=name,
            description=description,
            state=SliceState.NOT_INSTANTIATED,
            sliceType=slice_type,
            profile=profile
        )
        
        # Store slice subnet
        self.slice_subnets[slice_id] = slice_subnet
        
        # Save to storage
        if self.storage_path:
            self._save_slice_subnets()
        
        return slice_subnet
    
    def get_slice_subnet(self, slice_id: str) -> Optional[NetworkSliceSubnet]:
        """Get a Network Slice Subnet Instance by ID
        
        Args:
            slice_id (str): ID of the slice subnet
            
        Returns:
            Optional[NetworkSliceSubnet]: Slice subnet if found, None otherwise
        """
        return self.slice_subnets.get(slice_id)
    
    def update_slice_subnet_state(self, slice_id: str, state: SliceState) -> bool:
        """Update the state of a Network Slice Subnet Instance
        
        Args:
            slice_id (str): ID of the slice subnet
            state (SliceState): New state
            
        Returns:
            bool: True if successful, False otherwise
        """
        if slice_id not in self.slice_subnets:
            return False
        
        # Update state
        self.slice_subnets[slice_id].state = state
        self.slice_subnets[slice_id].modificationTime = time.time()
        
        # Save to storage
        if self.storage_path:
            self._save_slice_subnets()
        
        return True
    
    def delete_slice_subnet(self, slice_id: str) -> bool:
        """Delete a Network Slice Subnet Instance
        
        Args:
            slice_id (str): ID of the slice subnet
            
        Returns:
            bool: True if successful, False otherwise
        """
        if slice_id not in self.slice_subnets:
            return False
        
        # Delete slice subnet
        del self.slice_subnets[slice_id]
        
        # Save to storage
        if self.storage_path:
            self._save_slice_subnets()
        
        return True
    
    def get_all_slice_subnets(self) -> List[NetworkSliceSubnet]:
        """Get all Network Slice Subnet Instances
        
        Returns:
            List[NetworkSliceSubnet]: List of all slice subnets
        """
        return list(self.slice_subnets.values())
    
    def _save_slice_subnets(self):
        """Save slice subnets to storage"""
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        
        # Convert to dictionary
        slice_subnets_dict = {
            slice_id: slice_subnet.to_dict()
            for slice_id, slice_subnet in self.slice_subnets.items()
        }
        
        # Save to file
        with open(self.storage_path, 'w') as f:
            json.dump(slice_subnets_dict, f, indent=2)
    
    def _load_slice_subnets(self):
        """Load slice subnets from storage"""
        try:
            with open(self.storage_path, 'r') as f:
                slice_subnets_dict = json.load(f)
            
            # Convert to NetworkSliceSubnet objects
            for slice_id, slice_dict in slice_subnets_dict.items():
                profile_dict = slice_dict.pop('profile')
                profile = SliceProfile(**profile_dict)
                
                # Convert string state to enum
                state_str = slice_dict.pop('state')
                state = SliceState(state_str)
                
                # Convert int slice type to enum
                slice_type_int = slice_dict.pop('sliceType')
                slice_type = SliceType(slice_type_int)
                
                # Create NetworkSliceSubnet
                self.slice_subnets[slice_id] = NetworkSliceSubnet(
                    **slice_dict,
                    state=state,
                    sliceType=slice_type,
                    profile=profile
                )
        except Exception as e:
            print(f"Error loading slice subnets: {e}")
            self.slice_subnets = {}

def create_standard_slice_profile(slice_type: SliceType) -> SliceProfile:
    """Create a standard slice profile based on slice type
    
    Args:
        slice_type (SliceType): Type of slice
        
    Returns:
        SliceProfile: Standard slice profile
    """
    if slice_type == SliceType.EMBB:
        return SliceProfile(
            sNSSAI={"sst": 1, "sd": "000001"},
            pLMNIdList=["00101"],
            perfReq={"throughput": 100, "latency": 100},
            maxNumberOfUEs=1000,
            coverageAreaTAList=["TA1", "TA2"],
            latency=100,
            uEMobilityLevel="FULLY_MOBILITY",
            resourceSharingLevel="SHARED",
            fiveQIValue=2,
            priorityLevel=10,
            packetDelayBudget=100,
            packetErrorRate=1e-6
        )
    elif slice_type == SliceType.URLLC:
        return SliceProfile(
            sNSSAI={"sst": 2, "sd": "000001"},
            pLMNIdList=["00101"],
            perfReq={"throughput": 10, "latency": 10},
            maxNumberOfUEs=100,
            coverageAreaTAList=["TA1"],
            latency=10,
            uEMobilityLevel="RESTRICTED_MOBILITY",
            resourceSharingLevel="NON_SHARED",
            fiveQIValue=82,
            priorityLevel=5,
            packetDelayBudget=10,
            packetErrorRate=1e-5
        )
    elif slice_type == SliceType.MMTC:
        return SliceProfile(
            sNSSAI={"sst": 3, "sd": "000001"},
            pLMNIdList=["00101"],
            perfReq={"throughput": 1, "latency": 200},
            maxNumberOfUEs=10000,
            coverageAreaTAList=["TA1", "TA2", "TA3"],
            latency=200,
            uEMobilityLevel="STATIONARY",
            resourceSharingLevel="SHARED",
            fiveQIValue=7,
            priorityLevel=15,
            packetDelayBudget=200,
            packetErrorRate=1e-4
        )
    else:
        raise ValueError(f"Unsupported slice type: {slice_type}")

# Example usage
if __name__ == "__main__":
    # Create manager
    manager = NetworkSliceSubnetManager(storage_path="data/slice_subnets.json")
    
    # Create standard slice profiles
    embb_profile = create_standard_slice_profile(SliceType.EMBB)
    urllc_profile = create_standard_slice_profile(SliceType.URLLC)
    mmtc_profile = create_standard_slice_profile(SliceType.MMTC)
    
    # Create slice subnets
    embb_slice = manager.create_slice_subnet(
        name="eMBB Slice",
        description="Enhanced Mobile Broadband Slice",
        slice_type=SliceType.EMBB,
        profile=embb_profile
    )
    
    urllc_slice = manager.create_slice_subnet(
        name="URLLC Slice",
        description="Ultra Reliable Low Latency Communications Slice",
        slice_type=SliceType.URLLC,
        profile=urllc_profile
    )
    
    mmtc_slice = manager.create_slice_subnet(
        name="mMTC Slice",
        description="Massive Machine Type Communications Slice",
        slice_type=SliceType.MMTC,
        profile=mmtc_profile
    )
    
    # Print slice subnets
    for slice_subnet in manager.get_all_slice_subnets():
        print(f"Slice Subnet: {slice_subnet.name} ({slice_subnet.id})")
        print(f"  Type: {slice_subnet.sliceType.name}")
        print(f"  State: {slice_subnet.state.name}")
        print(f"  Profile: {slice_subnet.profile.to_dict()}")
        print() 