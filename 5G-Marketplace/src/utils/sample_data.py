"""
Sample Data Generator

This script initializes the marketplace with sample data for testing and demonstration purposes.
It creates sample vendors, slice offerings, and simulated slices.
"""

import logging
import random
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any

from src.database.vendors import VendorDatabase
from src.database.slices import SliceDatabase

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def initialize_sample_data():
    """
    Initialize the database with sample data for demonstration purposes
    """
    logger.info("Initializing sample data")
    
    # Initialize vendor database
    vendor_db = VendorDatabase()
    
    # Initialize slice database
    slice_db = SliceDatabase()
    
    # Add sample vendors if none exist
    if not vendor_db.get_all_vendors():
        add_sample_vendors(vendor_db)
    else:
        logger.info("Vendors already exist, skipping sample vendor creation")
    
    # Add sample slices if none exist
    if not slice_db.get_all_slices():
        add_sample_slices(slice_db, vendor_db)
    else:
        logger.info("Slices already exist, skipping sample slice creation")
    
    logger.info("Sample data initialization complete")

def add_sample_vendors(vendor_db: VendorDatabase):
    """
    Add sample vendors to the database
    
    Args:
        vendor_db: The vendor database to add to
    """
    logger.info("Adding sample vendors")
    
    # Sample vendors with their offerings for different slice types
    sample_vendors = [
        {
            "id": "vendor-1",
            "name": "TelcoNet Solutions",
            "location": "New York, USA",
            "rating": 4.8,
            "offerings": {
                "eMBB": {
                    "latency": 15.0,
                    "bandwidth": 1000.0,
                    "reliability": 99.9,
                    "cost": 150.0
                },
                "URLLC": {
                    "latency": 1.0,
                    "bandwidth": 500.0,
                    "reliability": 99.999,
                    "cost": 250.0
                },
                "mMTC": {
                    "latency": 50.0,
                    "bandwidth": 100.0,
                    "reliability": 99.5,
                    "cost": 75.0
                }
            },
            "advanced_attributes": {
                "availability": "high",
                "delayTolerance": "no",
                "deterministic": "no",
                "periodicity": "0.01",
                "maxPacketSize": "1500",
                "groupCommunication": "unicast",
                "missionCritical": "none",
                "maxUsers": 5000,
                "energyEfficiency": True,
                "performanceMonitoring": True,
                "performancePrediction": False,
                "mmtelSupport": True,
                "nbiotSupport": False
            }
        },
        {
            "id": "vendor-2",
            "name": "GlobalConnect 5G",
            "location": "London, UK",
            "rating": 4.5,
            "offerings": {
                "eMBB": {
                    "latency": 20.0,
                    "bandwidth": 1200.0,
                    "reliability": 99.8,
                    "cost": 140.0
                },
                "URLLC": {
                    "latency": 2.0,
                    "bandwidth": 400.0,
                    "reliability": 99.99,
                    "cost": 220.0
                },
                "mMTC": {
                    "latency": 45.0,
                    "bandwidth": 120.0,
                    "reliability": 99.6,
                    "cost": 65.0
                }
            },
            "advanced_attributes": {
                "availability": "high",
                "delayTolerance": "no",
                "deterministic": "no",
                "periodicity": "0.01",
                "maxPacketSize": "1500",
                "groupCommunication": "multicast",
                "missionCritical": "prioritization",
                "maxUsers": 10000,
                "energyEfficiency": True,
                "performanceMonitoring": True,
                "performancePrediction": True,
                "mmtelSupport": True,
                "nbiotSupport": True
            }
        },
        {
            "id": "vendor-3",
            "name": "NextGen Networks",
            "location": "Tokyo, Japan",
            "rating": 4.9,
            "offerings": {
                "eMBB": {
                    "latency": 10.0,
                    "bandwidth": 1500.0,
                    "reliability": 99.95,
                    "cost": 180.0
                },
                "URLLC": {
                    "latency": 0.5,
                    "bandwidth": 600.0,
                    "reliability": 99.9995,
                    "cost": 300.0
                },
                "mMTC": {
                    "latency": 40.0,
                    "bandwidth": 150.0,
                    "reliability": 99.7,
                    "cost": 90.0
                }
            },
            "advanced_attributes": {
                "availability": "very-high",
                "delayTolerance": "yes",
                "deterministic": "yes",
                "periodicity": "0.005",
                "maxPacketSize": "160",
                "groupCommunication": "sc-ptm",
                "missionCritical": "mcptt",
                "maxUsers": 20000,
                "energyEfficiency": True,
                "performanceMonitoring": True,
                "performancePrediction": True,
                "mmtelSupport": True,
                "nbiotSupport": True
            }
        },
        {
            "id": "vendor-4",
            "name": "EuroSlice Providers",
            "location": "Berlin, Germany",
            "rating": 4.6,
            "offerings": {
                "eMBB": {
                    "latency": 18.0,
                    "bandwidth": 950.0,
                    "reliability": 99.85,
                    "cost": 145.0
                },
                "URLLC": {
                    "latency": 1.5,
                    "bandwidth": 450.0,
                    "reliability": 99.995,
                    "cost": 240.0
                },
                "mMTC": {
                    "latency": 48.0,
                    "bandwidth": 110.0,
                    "reliability": 99.55,
                    "cost": 70.0
                }
            },
            "advanced_attributes": {
                "availability": "high",
                "delayTolerance": "no",
                "deterministic": "no",
                "periodicity": "0.02",
                "maxPacketSize": "1500",
                "groupCommunication": "unicast",
                "missionCritical": "none",
                "maxUsers": 8000,
                "energyEfficiency": False,
                "performanceMonitoring": True,
                "performancePrediction": False,
                "mmtelSupport": False,
                "nbiotSupport": True
            }
        },
        {
            "id": "vendor-5",
            "name": "AsiaPacific Telecom",
            "location": "Singapore",
            "rating": 4.7,
            "offerings": {
                "eMBB": {
                    "latency": 12.0,
                    "bandwidth": 1100.0,
                    "reliability": 99.92,
                    "cost": 160.0
                },
                "URLLC": {
                    "latency": 0.8,
                    "bandwidth": 550.0,
                    "reliability": 99.998,
                    "cost": 270.0
                },
                "mMTC": {
                    "latency": 42.0,
                    "bandwidth": 130.0,
                    "reliability": 99.65,
                    "cost": 80.0
                }
            },
            "advanced_attributes": {
                "availability": "high",
                "delayTolerance": "no",
                "deterministic": "no",
                "periodicity": "0.015",
                "maxPacketSize": "1500",
                "groupCommunication": "multicast",
                "missionCritical": "prioritization",
                "maxUsers": 12000,
                "energyEfficiency": True,
                "performanceMonitoring": True,
                "performancePrediction": True,
                "mmtelSupport": True,
                "nbiotSupport": False
            }
        }
    ]
    
    # Add vendors to database
    for vendor in sample_vendors:
        vendor_db.add_vendor(vendor)
    
    logger.info(f"Added {len(sample_vendors)} sample vendors")

def add_sample_slices(slice_db: SliceDatabase, vendor_db: VendorDatabase):
    """
    Add sample slices to the database
    
    Args:
        slice_db: The slice database to add to
        vendor_db: The vendor database to reference
    """
    logger.info("Adding sample slices")
    
    # Get all vendors
    vendors = vendor_db.get_all_vendors()
    
    if not vendors:
        logger.warning("No vendors found, cannot create sample slices")
        return
    
    # Sample slice types
    slice_types = ["eMBB", "URLLC", "mMTC"]
    
    # Generate sample slices
    sample_slices = []
    
    # Create 2 slices for each type
    for slice_type in slice_types:
        for i in range(2):
            # Select random vendor that offers this slice type
            eligible_vendors = [v for v in vendors if slice_type in v["offerings"]]
            if not eligible_vendors:
                continue
            
            vendor = random.choice(eligible_vendors)
            
            # Generate creation time (between 1-30 days ago)
            days_ago = random.randint(1, 30)
            created_at = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M:%S")
            
            # Create slice
            slice_data = {
                "id": f"slice-{str(uuid.uuid4())[:8]}",
                "type": slice_type,
                "vendor_id": vendor["id"],
                "vendor_name": vendor["name"],
                "created_at": created_at,
                "status": random.choice(["active", "active", "active", "degraded", "terminated"]),
                "latency": vendor["offerings"][slice_type]["latency"],
                "bandwidth": vendor["offerings"][slice_type]["bandwidth"],
                "reliability": vendor["offerings"][slice_type]["reliability"],
                "location": vendor["location"],
                "cost": vendor["offerings"][slice_type]["cost"]
            }
            
            sample_slices.append(slice_data)
    
    # Add slices to database
    for slice_data in sample_slices:
        slice_db.add_slice(slice_data)
    
    logger.info(f"Added {len(sample_slices)} sample slices")

if __name__ == "__main__":
    initialize_sample_data() 