import logging
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Dict, Any, List, Optional

from src.ai_agent.agent import AIAgent
from src.ndt.simulator import NetworkDigitalTwin
from src.database.vendors import VendorDatabase
from src.database.slices import SliceDatabase

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

# Define models
class SystemHealth(BaseModel):
    status: str
    components: Dict[str, Dict[str, Any]]
    active_slices: int
    registered_vendors: int
    ai_agent_status: Dict[str, Any]

class SliceInfo(BaseModel):
    id: str
    type: str
    vendor: str
    created_at: str
    status: str
    qos_metrics: Dict[str, Any]

class ActiveSlices(BaseModel):
    slices: List[SliceInfo]

class VendorInfo(BaseModel):
    id: str
    name: str
    location: str
    slice_types: List[str]
    rating: float

class VendorsList(BaseModel):
    vendors: List[VendorInfo]

# Dependencies
def get_ai_agent():
    return AIAgent()

def get_ndt():
    return NetworkDigitalTwin()

def get_vendor_db():
    return VendorDatabase()

def get_slice_db():
    return SliceDatabase()

@router.get("/system-health", response_model=SystemHealth)
async def get_system_health(
    ai_agent: AIAgent = Depends(get_ai_agent),
    ndt: NetworkDigitalTwin = Depends(get_ndt),
    vendor_db: VendorDatabase = Depends(get_vendor_db),
    slice_db: SliceDatabase = Depends(get_slice_db)
):
    """
    Get overall system health and status
    """
    logger.info("Fetching system health information")
    
    # Get AI agent status
    ai_status = ai_agent.status()
    
    # Get NDT status
    ndt_status = ndt.status()
    
    # Get counts
    active_slices = len(slice_db.get_all_slices())
    registered_vendors = len(vendor_db.get_all_vendors())
    
    # Determine overall system status
    if ai_status["status"] == "operational" and ndt_status["status"] == "operational":
        status = "healthy"
    elif ai_status["status"] == "degraded" or ndt_status["status"] == "degraded":
        status = "degraded"
    else:
        status = "error"
    
    return SystemHealth(
        status=status,
        components={
            "ai_agent": {
                "status": ai_status["status"],
                "message": ai_status.get("message", "AI agent is running")
            },
            "ndt": {
                "status": ndt_status["status"],
                "active_simulations": ndt_status["active_simulations"]
            }
        },
        active_slices=active_slices,
        registered_vendors=registered_vendors,
        ai_agent_status=ai_status
    )

@router.get("/active-slices", response_model=ActiveSlices)
async def get_active_slices(
    slice_db: SliceDatabase = Depends(get_slice_db),
    ndt: NetworkDigitalTwin = Depends(get_ndt)
):
    """
    Get information about active network slices
    """
    logger.info("Fetching active slices information")
    
    # Get all slices
    all_slices = slice_db.get_all_slices()
    
    # Get telemetry data for each slice
    slice_info_list = []
    for slice_data in all_slices:
        # Get telemetry data from NDT
        telemetry = ndt.get_slice_telemetry(slice_data["id"])
        
        slice_info = SliceInfo(
            id=slice_data["id"],
            type=slice_data["type"],
            vendor=slice_data["vendor_name"],
            created_at=slice_data["created_at"],
            status=slice_data["status"],
            qos_metrics=telemetry if telemetry else {
                "latency": slice_data["latency"],
                "bandwidth": slice_data["bandwidth"],
                "reliability": slice_data["reliability"]
            }
        )
        slice_info_list.append(slice_info)
    
    return ActiveSlices(slices=slice_info_list)

@router.get("/vendors", response_model=VendorsList)
async def get_vendors(
    vendor_db: VendorDatabase = Depends(get_vendor_db)
):
    """
    Get information about registered vendors
    """
    logger.info("Fetching vendors information")
    
    # Get all vendors
    all_vendors = vendor_db.get_all_vendors()
    
    vendor_info_list = []
    for vendor in all_vendors:
        vendor_info = VendorInfo(
            id=vendor["id"],
            name=vendor["name"],
            location=vendor["location"],
            slice_types=list(vendor["offerings"].keys()),
            rating=vendor["rating"]
        )
        vendor_info_list.append(vendor_info)
    
    return VendorsList(vendors=vendor_info_list) 