import logging
import json
import os
from typing import Dict, List, Any, Optional

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VendorDatabase:
    """
    Database for storing and retrieving vendor information
    Uses a simple JSON file-based storage for demonstration purposes
    """
    
    def __init__(self, data_file: str = "data/vendors.json"):
        """
        Initialize the vendor database
        
        Args:
            data_file: Path to the JSON file for storing vendor data
        """
        self.data_file = data_file
        self.vendors = []
        self._load_data()
    
    def _load_data(self) -> None:
        """
        Load vendor data from the JSON file
        """
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(self.data_file), exist_ok=True)
            
            # Check if file exists
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r') as file:
                    self.vendors = json.load(file)
                logger.info(f"Loaded {len(self.vendors)} vendors from {self.data_file}")
            else:
                logger.info(f"Vendor data file {self.data_file} not found, creating empty database")
                self.vendors = []
                self._save_data()
        except Exception as e:
            logger.error(f"Error loading vendor data: {str(e)}")
            self.vendors = []
    
    def _save_data(self) -> None:
        """
        Save vendor data to the JSON file
        """
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(self.data_file), exist_ok=True)
            
            with open(self.data_file, 'w') as file:
                json.dump(self.vendors, file, indent=2)
            logger.info(f"Saved {len(self.vendors)} vendors to {self.data_file}")
        except Exception as e:
            logger.error(f"Error saving vendor data: {str(e)}")
    
    def get_all_vendors(self) -> List[Dict[str, Any]]:
        """
        Get all vendors
        
        Returns:
            List of all vendors
        """
        return self.vendors
    
    def get_vendor_by_id(self, vendor_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a vendor by ID
        
        Args:
            vendor_id: The ID of the vendor to retrieve
            
        Returns:
            The vendor data if found, None otherwise
        """
        for vendor in self.vendors:
            if vendor["id"] == vendor_id:
                return vendor
        return None
    
    def add_vendor(self, vendor: Dict[str, Any]) -> str:
        """
        Add a new vendor
        
        Args:
            vendor: The vendor data to add
            
        Returns:
            The ID of the added vendor
        """
        # Check if vendor already exists
        if "id" in vendor and self.get_vendor_by_id(vendor["id"]):
            logger.warning(f"Vendor with ID {vendor['id']} already exists, updating")
            return self.update_vendor(vendor["id"], vendor)
        
        # Generate ID if not provided
        if "id" not in vendor:
            vendor["id"] = f"vendor-{len(self.vendors) + 1}"
        
        # Add vendor
        self.vendors.append(vendor)
        self._save_data()
        logger.info(f"Added vendor {vendor['name']} with ID {vendor['id']}")
        return vendor["id"]
    
    def update_vendor(self, vendor_id: str, vendor_data: Dict[str, Any]) -> str:
        """
        Update an existing vendor
        
        Args:
            vendor_id: The ID of the vendor to update
            vendor_data: The new vendor data
            
        Returns:
            The ID of the updated vendor
        """
        # Find vendor
        for i, vendor in enumerate(self.vendors):
            if vendor["id"] == vendor_id:
                # Update vendor
                vendor_data["id"] = vendor_id  # Ensure ID remains the same
                self.vendors[i] = vendor_data
                self._save_data()
                logger.info(f"Updated vendor with ID {vendor_id}")
                return vendor_id
        
        # Vendor not found
        logger.warning(f"Vendor with ID {vendor_id} not found, adding as new")
        return self.add_vendor(vendor_data)
    
    def delete_vendor(self, vendor_id: str) -> bool:
        """
        Delete a vendor
        
        Args:
            vendor_id: The ID of the vendor to delete
            
        Returns:
            True if the vendor was deleted, False otherwise
        """
        # Find vendor
        for i, vendor in enumerate(self.vendors):
            if vendor["id"] == vendor_id:
                # Delete vendor
                del self.vendors[i]
                self._save_data()
                logger.info(f"Deleted vendor with ID {vendor_id}")
                return True
        
        # Vendor not found
        logger.warning(f"Vendor with ID {vendor_id} not found, nothing to delete")
        return False
    
    def update_vendor_rating(self, vendor_id: str, new_rating: float) -> bool:
        """
        Update a vendor's rating
        
        Args:
            vendor_id: The ID of the vendor to update
            new_rating: The new rating value
            
        Returns:
            True if the rating was updated, False otherwise
        """
        # Find vendor
        for i, vendor in enumerate(self.vendors):
            if vendor["id"] == vendor_id:
                # Update rating
                vendor["rating"] = new_rating
                self._save_data()
                logger.info(f"Updated rating for vendor with ID {vendor_id} to {new_rating}")
                return True
        
        # Vendor not found
        logger.warning(f"Vendor with ID {vendor_id} not found, cannot update rating")
        return False 