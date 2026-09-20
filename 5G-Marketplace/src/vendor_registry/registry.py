"""
Vendor Registry Module

This module manages the registry of vendors, their capabilities, and offerings.
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional

# Configure logging
logger = logging.getLogger(__name__)

class VendorRegistry:
    """Registry for managing vendors and their offerings"""
    
    def __init__(self, storage_path: str = None):
        """Initialize the vendor registry
        
        Args:
            storage_path: Path to storage directory
        """
        self.storage_path = storage_path or os.path.join("data", "vendor_registry")
        self.vendors = {}
        self.capabilities = {}
        self.offerings = {}
        self._ensure_storage_path()
    
    def _ensure_storage_path(self):
        """Ensure storage path exists"""
        os.makedirs(self.storage_path, exist_ok=True)
        
        # Create storage files if they don't exist
        vendors_file = os.path.join(self.storage_path, "vendors.json")
        capabilities_file = os.path.join(self.storage_path, "capabilities.json")
        offerings_file = os.path.join(self.storage_path, "offerings.json")
        
        for file_path, default_content in [
            (vendors_file, {}),
            (capabilities_file, {}),
            (offerings_file, {})
        ]:
            if not os.path.exists(file_path):
                with open(file_path, "w") as f:
                    json.dump(default_content, f, indent=2)
    
    async def load_vendors(self):
        """Load vendors from storage"""
        try:
            vendors_file = os.path.join(self.storage_path, "vendors.json")
            capabilities_file = os.path.join(self.storage_path, "capabilities.json")
            offerings_file = os.path.join(self.storage_path, "offerings.json")
            
            # Load vendors
            if os.path.exists(vendors_file):
                with open(vendors_file, "r") as f:
                    self.vendors = json.load(f)
            
            # Load capabilities
            if os.path.exists(capabilities_file):
                with open(capabilities_file, "r") as f:
                    self.capabilities = json.load(f)
            
            # Load offerings
            if os.path.exists(offerings_file):
                with open(offerings_file, "r") as f:
                    self.offerings = json.load(f)
            
            logger.info(f"Loaded {len(self.vendors)} vendors, {len(self.capabilities)} capabilities, {len(self.offerings)} offerings")
        except Exception as e:
            logger.error(f"Error loading vendors: {str(e)}")
    
    async def save_vendors(self):
        """Save vendors to storage"""
        try:
            vendors_file = os.path.join(self.storage_path, "vendors.json")
            capabilities_file = os.path.join(self.storage_path, "capabilities.json")
            offerings_file = os.path.join(self.storage_path, "offerings.json")
            
            # Save vendors
            with open(vendors_file, "w") as f:
                json.dump(self.vendors, f, indent=2, default=str)
            
            # Save capabilities
            with open(capabilities_file, "w") as f:
                json.dump(self.capabilities, f, indent=2, default=str)
            
            # Save offerings
            with open(offerings_file, "w") as f:
                json.dump(self.offerings, f, indent=2, default=str)
            
            logger.info(f"Saved {len(self.vendors)} vendors, {len(self.capabilities)} capabilities, {len(self.offerings)} offerings")
        except Exception as e:
            logger.error(f"Error saving vendors: {str(e)}")
    
    async def register_vendor(
        self,
        vendor_id: str,
        name: str,
        api_url: str,
        api_key: str,
        description: str,
        supported_regions: List[str],
        contact_email: str,
        advanced_attributes: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Register a new vendor
        
        Args:
            vendor_id: Vendor identifier
            name: Vendor name
            api_url: Vendor API URL
            api_key: Vendor API key
            description: Vendor description
            supported_regions: Supported geographic regions
            contact_email: Contact email
            advanced_attributes: Advanced network slice template attributes
            
        Returns:
            Dict: Vendor information
        """
        # Create vendor information
        vendor_info = {
            "vendor_id": vendor_id,
            "name": name,
            "description": description,
            "supported_regions": supported_regions,
            "registration_date": datetime.now().isoformat(),
            "status": "active",
            "reputation_score": 0.5,  # Initial reputation score
            "api_url": api_url,
            "api_key": api_key,
            "contact_email": contact_email,
            "advanced_attributes": advanced_attributes or {}
        }
        
        # Store vendor
        self.vendors[vendor_id] = vendor_info
        
        # Save vendors
        await self.save_vendors()
        
        # Return vendor information (excluding sensitive data)
        return {
            "vendor_id": vendor_id,
            "name": name,
            "description": description,
            "supported_regions": supported_regions,
            "registration_date": datetime.now(),
            "status": "active",
            "reputation_score": 0.5,
            "advanced_attributes": advanced_attributes or {}
        }
    
    async def unregister_vendor(self, vendor_id: str) -> bool:
        """Unregister a vendor
        
        Args:
            vendor_id: Vendor identifier
            
        Returns:
            bool: True if successful, False otherwise
        """
        if vendor_id not in self.vendors:
            return False
        
        # Remove vendor
        del self.vendors[vendor_id]
        
        # Remove capabilities
        if vendor_id in self.capabilities:
            del self.capabilities[vendor_id]
        
        # Remove offerings
        offerings_to_remove = []
        for offering_id, offering in self.offerings.items():
            if offering["vendor_id"] == vendor_id:
                offerings_to_remove.append(offering_id)
        
        for offering_id in offerings_to_remove:
            del self.offerings[offering_id]
        
        # Save vendors
        await self.save_vendors()
        
        return True
    
    async def get_vendor_info(self, vendor_id: str) -> Optional[Dict[str, Any]]:
        """Get vendor information
        
        Args:
            vendor_id: Vendor identifier
            
        Returns:
            Dict: Vendor information
        """
        if vendor_id not in self.vendors:
            return None
        
        vendor_info = self.vendors[vendor_id]
        
        # Return vendor information (excluding sensitive data)
        return {
            "vendor_id": vendor_id,
            "name": vendor_info["name"],
            "description": vendor_info["description"],
            "supported_regions": vendor_info["supported_regions"],
            "registration_date": vendor_info["registration_date"],
            "status": vendor_info["status"],
            "reputation_score": vendor_info["reputation_score"],
            "advanced_attributes": vendor_info.get("advanced_attributes", {})
        }
    
    async def list_vendors(self) -> List[Dict[str, Any]]:
        """List all vendors
        
        Returns:
            List: List of vendor information
        """
        vendor_list = []
        
        for vendor_id, vendor_info in self.vendors.items():
            # Add vendor information (excluding sensitive data)
            vendor_list.append({
                "vendor_id": vendor_id,
                "name": vendor_info["name"],
                "description": vendor_info["description"],
                "supported_regions": vendor_info["supported_regions"],
                "registration_date": vendor_info["registration_date"],
                "status": vendor_info["status"],
                "reputation_score": vendor_info["reputation_score"],
                "advanced_attributes": vendor_info.get("advanced_attributes", {})
            })
        
        return vendor_list
    
    async def update_vendor_capabilities(self, vendor_id: str, capabilities: Dict[str, Any], advanced_attributes: Dict[str, Any] = None) -> bool:
        """Update vendor capabilities
        
        Args:
            vendor_id: Vendor identifier
            capabilities: Vendor capabilities
            advanced_attributes: Advanced network slice template attributes
            
        Returns:
            bool: True if successful, False otherwise
        """
        if vendor_id not in self.vendors:
            return False
        
        # Store capabilities
        self.capabilities[vendor_id] = capabilities
        
        # Update advanced attributes if provided
        if advanced_attributes is not None and vendor_id in self.vendors:
            self.vendors[vendor_id]["advanced_attributes"] = advanced_attributes
        
        # Save vendors
        await self.save_vendors()
        
        return True
    
    async def get_vendor_capabilities(self, vendor_id: str) -> Optional[Dict[str, Any]]:
        """Get vendor capabilities
        
        Args:
            vendor_id: Vendor identifier
            
        Returns:
            Dict: Vendor capabilities
        """
        if vendor_id not in self.capabilities:
            return None
        
        return self.capabilities[vendor_id]
    
    async def add_vendor_offering(self, offering: Dict[str, Any]) -> Dict[str, Any]:
        """Add a vendor offering
        
        Args:
            offering: Vendor offering
            
        Returns:
            Dict: Stored offering
        """
        offering_id = offering.get("offering_id")
        
        # Store offering
        self.offerings[offering_id] = offering
        
        # Save vendors
        await self.save_vendors()
        
        return offering
    
    async def get_offering(self, offering_id: str) -> Optional[Dict[str, Any]]:
        """Get an offering
        
        Args:
            offering_id: Offering identifier
            
        Returns:
            Dict: Offering
        """
        if offering_id not in self.offerings:
            return None
        
        return self.offerings[offering_id]
    
    async def get_vendor_offerings(self, vendor_id: str) -> List[Dict[str, Any]]:
        """Get all offerings from a vendor
        
        Args:
            vendor_id: Vendor identifier
            
        Returns:
            List: List of offerings
        """
        vendor_offerings = []
        
        for offering_id, offering in self.offerings.items():
            if offering["vendor_id"] == vendor_id:
                vendor_offerings.append(offering)
        
        return vendor_offerings
    
    async def delete_offering(self, offering_id: str) -> bool:
        """Delete an offering
        
        Args:
            offering_id: Offering identifier
            
        Returns:
            bool: True if successful, False otherwise
        """
        if offering_id not in self.offerings:
            return False
        
        # Remove offering
        del self.offerings[offering_id]
        
        # Save vendors
        await self.save_vendors()
        
        return True
    
    async def find_matching_offerings(
        self,
        qos_requirements: Dict[str, Any],
        slice_type: str,
        location: str
    ) -> List[Dict[str, Any]]:
        """Find offerings that match QoS requirements
        
        Args:
            qos_requirements: QoS requirements
            slice_type: Slice type
            location: Geographic location
            
        Returns:
            List: List of matching offerings
        """
        matching_offerings = []
        
        for offering_id, offering in self.offerings.items():
            # Check if slice type matches
            if offering["slice_type"] != slice_type:
                continue
            
            # Check if location is supported
            if location not in offering["regions"]:
                continue
            
            # Check if QoS requirements are met
            qos_match = True
            for key, value in qos_requirements.items():
                if key in offering["qos"]:
                    # For latency, jitter, and packet_loss, lower is better
                    if key in ["latency", "jitter", "packet_loss"]:
                        if offering["qos"][key] > value:
                            qos_match = False
                            break
                    # For bandwidth, availability, and reliability, higher is better
                    elif key in ["bandwidth", "availability", "reliability"]:
                        if offering["qos"][key] < value:
                            qos_match = False
                            break
            
            if qos_match:
                # Get the full vendor info to include advanced attributes
                vendor_info = self.vendors.get(offering["vendor_id"], {})
                
                # Combine offering with vendor's advanced attributes
                full_offering_details = {
                    **offering,
                    "advanced_attributes": vendor_info.get("advanced_attributes", {})
                }
                matching_offerings.append(full_offering_details)
        
        return matching_offerings
    
    def status(self) -> Dict[str, Any]:
        """Get vendor registry status
        
        Returns:
            Dict: Status information
        """
        return {
            "status": "operational",
            "vendor_count": len(self.vendors),
            "offering_count": len(self.offerings)
        } 