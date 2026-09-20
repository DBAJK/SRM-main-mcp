"""
Customer API Module

This module handles customer slice requests and provides endpoints for
submitting QoS requirements, checking slice status, and managing slices.
"""

import logging
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any
from datetime import datetime
import uuid

# Configure logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter()

# Define models
class QoSRequirements(BaseModel):
    """QoS requirements for a network slice"""
    latency: float = Field(..., description="Maximum latency in milliseconds", gt=0)
    bandwidth: float = Field(..., description="Minimum bandwidth in Mbps", gt=0)
    availability: float = Field(..., description="Minimum availability percentage", ge=99, le=100)
    reliability: Optional[float] = Field(None, description="Minimum reliability percentage", ge=99, le=100)
    jitter: Optional[float] = Field(None, description="Maximum jitter in milliseconds", ge=0)
    packet_loss: Optional[float] = Field(None, description="Maximum packet loss percentage", ge=0, le=100)
    security_level: Optional[int] = Field(None, description="Security level (1-5)", ge=1, le=5)
    
class SliceRequest(BaseModel):
    """Network slice request model"""
    customer_id: str = Field(..., description="Customer identifier")
    name: str = Field(..., description="Slice name")
    location: str = Field(..., description="Geographic location for deployment")
    qos: QoSRequirements = Field(..., description="QoS requirements")
    duration_hours: Optional[int] = Field(None, description="Duration in hours")
    max_price: Optional[float] = Field(None, description="Maximum price willing to pay")
    priority: Optional[int] = Field(1, description="Priority level (1-5)", ge=1, le=5)
    
class SliceResponse(BaseModel):
    """Network slice response model"""
    request_id: str = Field(..., description="Request identifier")
    status: str = Field(..., description="Request status")
    message: str = Field(..., description="Status message")
    timestamp: datetime = Field(..., description="Request timestamp")
    
class SliceDetails(BaseModel):
    """Network slice details model"""
    slice_id: str = Field(..., description="Slice identifier")
    request_id: str = Field(..., description="Original request identifier")
    customer_id: str = Field(..., description="Customer identifier")
    name: str = Field(..., description="Slice name")
    vendor_id: str = Field(..., description="Selected vendor identifier")
    status: str = Field(..., description="Slice status")
    qos_promised: Dict[str, Any] = Field(..., description="Promised QoS parameters")
    qos_actual: Optional[Dict[str, Any]] = Field(None, description="Actual QoS measurements")
    deployment_time: datetime = Field(..., description="Deployment timestamp")
    expiry_time: Optional[datetime] = Field(None, description="Expiry timestamp")
    price: float = Field(..., description="Price per hour")
    
# In-memory storage (replace with database in production)
slice_requests = {}
active_slices = {}

# Dependency for getting the slice selection engine
async def get_slice_selection_engine():
    """Get the slice selection engine from the main application"""
    from main import slice_selection_engine
    return slice_selection_engine

@router.post("/slice/request", response_model=SliceResponse)
async def request_slice(
    request: SliceRequest,
    background_tasks: BackgroundTasks,
    selection_engine=Depends(get_slice_selection_engine)
):
    """Submit a new slice request"""
    logger.info(f"Received slice request from customer {request.customer_id}")
    
    # Generate request ID
    request_id = str(uuid.uuid4())
    
    # Store request
    slice_requests[request_id] = {
        "request": request.dict(),
        "status": "processing",
        "timestamp": datetime.now()
    }
    
    # Process request in background
    background_tasks.add_task(
        process_slice_request,
        request_id=request_id,
        request=request,
        selection_engine=selection_engine
    )
    
    return SliceResponse(
        request_id=request_id,
        status="processing",
        message="Slice request is being processed",
        timestamp=datetime.now()
    )

@router.get("/slice/request/{request_id}", response_model=SliceResponse)
async def get_slice_request_status(request_id: str):
    """Get the status of a slice request"""
    if request_id not in slice_requests:
        raise HTTPException(status_code=404, detail="Slice request not found")
    
    request_data = slice_requests[request_id]
    
    return SliceResponse(
        request_id=request_id,
        status=request_data["status"],
        message=request_data.get("message", ""),
        timestamp=request_data["timestamp"]
    )

@router.get("/slice/{slice_id}", response_model=SliceDetails)
async def get_slice_details(slice_id: str):
    """Get details of a deployed slice"""
    if slice_id not in active_slices:
        raise HTTPException(status_code=404, detail="Slice not found")
    
    return SliceDetails(**active_slices[slice_id])

@router.get("/slices", response_model=List[SliceDetails])
async def list_customer_slices(customer_id: str):
    """List all slices for a customer"""
    customer_slices = [
        SliceDetails(**slice_data)
        for slice_data in active_slices.values()
        if slice_data["customer_id"] == customer_id
    ]
    
    return customer_slices

@router.delete("/slice/{slice_id}")
async def terminate_slice(slice_id: str):
    """Terminate a deployed slice"""
    if slice_id not in active_slices:
        raise HTTPException(status_code=404, detail="Slice not found")
    
    # In a real implementation, we would communicate with the vendor to terminate the slice
    # For now, just mark it as terminated
    active_slices[slice_id]["status"] = "terminated"
    
    return {"message": f"Slice {slice_id} has been terminated"}

async def process_slice_request(request_id: str, request: SliceRequest, selection_engine):
    """Process a slice request in the background"""
    try:
        logger.info(f"Processing slice request {request_id}")
        
        # Step 1: Classify slice type based on QoS requirements
        slice_type = await selection_engine.classify_slice_type(request.qos)
        logger.info(f"Classified as {slice_type} slice")
        
        # Step 2: Query vendors for matching offers
        vendor_offers = await selection_engine.query_vendors(request.qos, slice_type, request.location)
        
        if not vendor_offers:
            logger.warning(f"No vendor offers found for request {request_id}")
            slice_requests[request_id]["status"] = "failed"
            slice_requests[request_id]["message"] = "No matching vendor offers found"
            return
        
        # Step 3: Select best offer
        best_offer = await selection_engine.select_best_offer(vendor_offers, request)
        
        # Step 4: Deploy slice
        slice_id = str(uuid.uuid4())
        deployment_result = await selection_engine.deploy_slice(best_offer, slice_id, request_id)
        
        if deployment_result["success"]:
            # Update request status
            slice_requests[request_id]["status"] = "completed"
            slice_requests[request_id]["message"] = f"Slice deployed successfully with ID {slice_id}"
            
            # Store active slice
            active_slices[slice_id] = {
                "slice_id": slice_id,
                "request_id": request_id,
                "customer_id": request.customer_id,
                "name": request.name,
                "vendor_id": best_offer["vendor_id"],
                "status": "active",
                "qos_promised": best_offer["qos"],
                "qos_actual": None,  # Will be updated by monitoring
                "deployment_time": datetime.now(),
                "expiry_time": None if not request.duration_hours else datetime.now().replace(hour=datetime.now().hour + request.duration_hours),
                "price": best_offer["price"]
            }
            
            logger.info(f"Slice {slice_id} deployed successfully")
        else:
            # Update request status
            slice_requests[request_id]["status"] = "failed"
            slice_requests[request_id]["message"] = deployment_result["error"]
            logger.error(f"Failed to deploy slice for request {request_id}: {deployment_result['error']}")
    
    except Exception as e:
        logger.exception(f"Error processing slice request {request_id}: {str(e)}")
        slice_requests[request_id]["status"] = "failed"
        slice_requests[request_id]["message"] = f"Internal error: {str(e)}" 