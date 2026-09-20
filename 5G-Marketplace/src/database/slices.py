import logging
import json
import os
import uuid
from datetime import datetime
from typing import Dict, List, Any, Optional

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SliceDatabase:
    """
    Database for storing and retrieving network slice information
    Uses a simple JSON file-based storage for demonstration purposes
    """
    
    def __init__(self, data_file: str = "data/slices.json"):
        """
        Initialize the slice database
        
        Args:
            data_file: Path to the JSON file for storing slice data
        """
        self.data_file = data_file
        self.slices = []
        self._load_data()
    
    def _load_data(self) -> None:
        """
        Load slice data from the JSON file
        """
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(self.data_file), exist_ok=True)
            
            # Check if file exists
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r') as file:
                    self.slices = json.load(file)
                logger.info(f"Loaded {len(self.slices)} slices from {self.data_file}")
            else:
                logger.info(f"Slice data file {self.data_file} not found, creating empty database")
                self.slices = []
                self._save_data()
        except Exception as e:
            logger.error(f"Error loading slice data: {str(e)}")
            self.slices = []
    
    def _save_data(self) -> None:
        """
        Save slice data to the JSON file
        """
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(self.data_file), exist_ok=True)
            
            with open(self.data_file, 'w') as file:
                json.dump(self.slices, file, indent=2)
            logger.info(f"Saved {len(self.slices)} slices to {self.data_file}")
        except Exception as e:
            logger.error(f"Error saving slice data: {str(e)}")
    
    def get_all_slices(self) -> List[Dict[str, Any]]:
        """
        Get all slices
        
        Returns:
            List of all slices
        """
        return self.slices
    
    def get_slice_by_id(self, slice_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a slice by ID
        
        Args:
            slice_id: The ID of the slice to retrieve
            
        Returns:
            The slice data if found, None otherwise
        """
        for slice_data in self.slices:
            if slice_data["id"] == slice_id:
                return slice_data
        return None
    
    def add_slice(self, slice_data: Dict[str, Any]) -> str:
        """
        Add a new network slice
        
        Args:
            slice_data: The slice data to add
            
        Returns:
            The ID of the added slice
        """
        # Check if slice already exists
        if "id" in slice_data and self.get_slice_by_id(slice_data["id"]):
            logger.warning(f"Slice with ID {slice_data['id']} already exists, updating")
            return self.update_slice(slice_data["id"], slice_data)
        
        # Generate ID if not provided
        if "id" not in slice_data:
            slice_data["id"] = f"slice-{str(uuid.uuid4())[:8]}"
        
        # Add created_at timestamp if not provided
        if "created_at" not in slice_data:
            slice_data["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Set default status if not provided
        if "status" not in slice_data:
            slice_data["status"] = "active"
        
        # Add slice
        self.slices.append(slice_data)
        self._save_data()
        logger.info(f"Added slice with ID {slice_data['id']}")
        return slice_data["id"]
    
    def update_slice(self, slice_id: str, slice_data: Dict[str, Any]) -> str:
        """
        Update an existing slice
        
        Args:
            slice_id: The ID of the slice to update
            slice_data: The new slice data
            
        Returns:
            The ID of the updated slice
        """
        # Find slice
        for i, existing_slice in enumerate(self.slices):
            if existing_slice["id"] == slice_id:
                # Update slice
                slice_data["id"] = slice_id  # Ensure ID remains the same
                
                # Preserve created_at timestamp
                if "created_at" not in slice_data and "created_at" in existing_slice:
                    slice_data["created_at"] = existing_slice["created_at"]
                
                # Update slice
                self.slices[i] = slice_data
                self._save_data()
                logger.info(f"Updated slice with ID {slice_id}")
                return slice_id
        
        # Slice not found
        logger.warning(f"Slice with ID {slice_id} not found, adding as new")
        return self.add_slice(slice_data)
    
    def delete_slice(self, slice_id: str) -> bool:
        """
        Delete a slice
        
        Args:
            slice_id: The ID of the slice to delete
            
        Returns:
            True if the slice was deleted, False otherwise
        """
        # Find slice
        for i, slice_data in enumerate(self.slices):
            if slice_data["id"] == slice_id:
                # Delete slice
                del self.slices[i]
                self._save_data()
                logger.info(f"Deleted slice with ID {slice_id}")
                return True
        
        # Slice not found
        logger.warning(f"Slice with ID {slice_id} not found, nothing to delete")
        return False
    
    def update_slice_status(self, slice_id: str, new_status: str) -> bool:
        """
        Update a slice's status
        
        Args:
            slice_id: The ID of the slice to update
            new_status: The new status value
            
        Returns:
            True if the status was updated, False otherwise
        """
        # Find slice
        for i, slice_data in enumerate(self.slices):
            if slice_data["id"] == slice_id:
                # Update status
                slice_data["status"] = new_status
                self._save_data()
                logger.info(f"Updated status for slice with ID {slice_id} to {new_status}")
                return True
        
        # Slice not found
        logger.warning(f"Slice with ID {slice_id} not found, cannot update status")
        return False 