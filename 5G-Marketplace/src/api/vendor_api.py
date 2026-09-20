"""
Vendor API Module

This module handles vendor registration, slice offerings, and vendor-specific operations.
"""

import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field, HttpUrl
from typing import Dict, List, Optional, Any
from datetime import datetime
import uuid

# Configure logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter()

# Define models
class VendorRegistration(BaseModel):
    """Vendor registration model"""
    name: str = Field(..., description="Vendor name")
    api_url: HttpUrl = Field(..., description="Vendor API URL")
    api_key: str = Field(..., description="Vendor API key")
    description: str = Field(..., description="Vendor description")
    supported_regions: List[str] = Field(..., description="Supported geographic regions")
    contact_email: str = Field(..., description="Contact email")
    
class VendorInfo(BaseModel):
    """Vendor information model"""
    vendor_id: str = Field(..., description="Vendor identifier")
    name: str = Field(..., description="Vendor name")
    description: str = Field(..., description="Vendor description")
    supported_regions: List[str] = Field(..., description="Supported geographic regions")
    registration_date: datetime = Field(..., description="Registration date")
    status: str = Field(..., description="Vendor status")
    reputation_score: float = Field(..., description="Reputation score (0-1)")
    
class SliceCapabilities(BaseModel):
    """Vendor slice capabilities model"""
    min_latency: float = Field(..., description="Minimum achievable latency in ms")
    max_bandwidth: float = Field(..., description="Maximum achievable bandwidth in Mbps")
    max_availability: float = Field(..., description="Maximum achievable availability percentage")
    max_reliability: float = Field(..., description="Maximum achievable reliability percentage")
    min_jitter: float = Field(..., description="Minimum achievable jitter in ms")
    min_packet_loss: float = Field(..., description="Minimum achievable packet loss percentage")
    security_levels: List[int] = Field(..., description="Supported security levels")
    
class SliceOffering(BaseModel):
    """Slice offering model"""
    offering_id: str = Field(..., description="Offering identifier")
    vendor_id: str = Field(..., description="Vendor identifier")
    slice_type: str = Field(..., description="Slice type (eMBB, URLLC, mMTC)")
    qos: Dict[str, Any] = Field(..., description="QoS parameters")
    price: float = Field(..., description="Price per hour")
    availability_start: datetime = Field(..., description="Availability start time")
    availability_end: Optional[datetime] = Field(None, description="Availability end time")
    provisioning_time: int = Field(..., description="Provisioning time in minutes")
    regions: List[str] = Field(..., description="Available regions")
    
class SliceDeploymentRequest(BaseModel):
    """Slice deployment request model"""
    offering_id: str = Field(..., description="Offering identifier")
    customer_id: str = Field(..., description="Customer identifier")
    slice_id: str = Field(..., description="Slice identifier")
    location: str = Field(..., description="Deployment location")
    qos_requirements: Dict[str, Any] = Field(..., description="QoS requirements")
    
class SliceDeploymentResponse(BaseModel):
    """Slice deployment response model"""
    slice_id: str = Field(..., description="Slice identifier")
    status: str = Field(..., description="Deployment status")
    message: str = Field(..., description="Status message")
    deployment_details: Optional[Dict[str, Any]] = Field(None, description="Deployment details")

# Dependency for getting the vendor registry
async def get_vendor_registry():
    """Get the vendor registry from the main application"""
    from main import vendor_registry
    return vendor_registry

@router.post("/register", response_model=VendorInfo)
async def register_vendor(
    registration: VendorRegistration,
    vendor_registry=Depends(get_vendor_registry)
):
    """Register a new vendor"""
    logger.info(f"Received vendor registration request for {registration.name}")
    
    # Check if vendor API is reachable
    try:
        # In a real implementation, we would verify the vendor API is accessible
        # For now, just assume it's valid
        pass
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Vendor API not reachable: {str(e)}")
    
    # Generate vendor ID
    vendor_id = str(uuid.uuid4())
    
    # Register vendor
    vendor_info = await vendor_registry.register_vendor(
        vendor_id=vendor_id,
        name=registration.name,
        api_url=str(registration.api_url),
        api_key=registration.api_key,
        description=registration.description,
        supported_regions=registration.supported_regions,
        contact_email=registration.contact_email
    )
    
    return vendor_info

@router.get("/info/{vendor_id}", response_model=VendorInfo)
async def get_vendor_info(
    vendor_id: str,
    vendor_registry=Depends(get_vendor_registry)
):
    """Get vendor information"""
    vendor_info = await vendor_registry.get_vendor_info(vendor_id)
    
    if not vendor_info:
        raise HTTPException(status_code=404, detail="Vendor not found")
    
    return vendor_info

@router.get("/list", response_model=List[VendorInfo])
async def list_vendors(
    vendor_registry=Depends(get_vendor_registry)
):
    """List all registered vendors"""
    vendors = await vendor_registry.list_vendors()
    return vendors

@router.post("/capabilities/{vendor_id}", response_model=SliceCapabilities)
async def update_capabilities(
    vendor_id: str,
    capabilities: SliceCapabilities,
    vendor_registry=Depends(get_vendor_registry)
):
    """Update vendor slice capabilities"""
    vendor_info = await vendor_registry.get_vendor_info(vendor_id)
    
    if not vendor_info:
        raise HTTPException(status_code=404, detail="Vendor not found")
    
    # Update capabilities
    await vendor_registry.update_vendor_capabilities(vendor_id, capabilities.dict())
    
    return capabilities

@router.get("/capabilities/{vendor_id}", response_model=SliceCapabilities)
async def get_capabilities(
    vendor_id: str,
    vendor_registry=Depends(get_vendor_registry)
):
    """Get vendor slice capabilities"""
    capabilities = await vendor_registry.get_vendor_capabilities(vendor_id)
    
    if not capabilities:
        raise HTTPException(status_code=404, detail="Vendor capabilities not found")
    
    return SliceCapabilities(**capabilities)

@router.post("/offerings", response_model=SliceOffering)
async def create_offering(
    offering: SliceOffering,
    vendor_registry=Depends(get_vendor_registry)
):
    """Create a new slice offering"""
    # Validate vendor exists
    vendor_info = await vendor_registry.get_vendor_info(offering.vendor_id)
    
    if not vendor_info:
        raise HTTPException(status_code=404, detail="Vendor not found")
    
    # Store offering
    stored_offering = await vendor_registry.add_vendor_offering(offering.dict())
    
    return SliceOffering(**stored_offering)

@router.get("/offerings/{vendor_id}", response_model=List[SliceOffering])
async def list_offerings(
    vendor_id: str,
    vendor_registry=Depends(get_vendor_registry)
):
    """List all offerings from a vendor"""
    # Validate vendor exists
    vendor_info = await vendor_registry.get_vendor_info(vendor_id)
    
    if not vendor_info:
        raise HTTPException(status_code=404, detail="Vendor not found")
    
    # Get offerings
    offerings = await vendor_registry.get_vendor_offerings(vendor_id)
    
    return [SliceOffering(**offering) for offering in offerings]

@router.post("/deploy", response_model=SliceDeploymentResponse)
async def deploy_slice(
    deployment: SliceDeploymentRequest,
    vendor_registry=Depends(get_vendor_registry)
):
    """Request slice deployment from a vendor"""
    # In a real implementation, we would forward this request to the vendor's API
    # For now, just simulate a successful deployment
    
    # Get the offering
    offering = await vendor_registry.get_offering(deployment.offering_id)
    
    if not offering:
        raise HTTPException(status_code=404, detail="Offering not found")
    
    # Simulate deployment
    deployment_response = SliceDeploymentResponse(
        slice_id=deployment.slice_id,
        status="deployed",
        message="Slice deployed successfully",
        deployment_details={
            "vendor_id": offering["vendor_id"],
            "deployment_time": datetime.now().isoformat(),
            "qos_promised": offering["qos"],
            "monitoring_endpoint": f"https://api.example.com/monitoring/{deployment.slice_id}"
        }
    )
    
    return deployment_response

@router.delete("/offerings/{offering_id}")
async def delete_offering(
    offering_id: str,
    vendor_registry=Depends(get_vendor_registry)
):
    """Delete a slice offering"""
    # Get the offering
    offering = await vendor_registry.get_offering(offering_id)
    
    if not offering:
        raise HTTPException(status_code=404, detail="Offering not found")
    
    # Delete offering
    await vendor_registry.delete_offering(offering_id)
    
    return {"message": f"Offering {offering_id} deleted successfully"}

@router.delete("/unregister/{vendor_id}")
async def unregister_vendor(
    vendor_id: str,
    vendor_registry=Depends(get_vendor_registry)
):
    """Unregister a vendor"""
    # Validate vendor exists
    vendor_info = await vendor_registry.get_vendor_info(vendor_id)
    
    if not vendor_info:
        raise HTTPException(status_code=404, detail="Vendor not found")
    
    # Unregister vendor
    await vendor_registry.unregister_vendor(vendor_id)
    
    return {"message": f"Vendor {vendor_id} unregistered successfully"} 