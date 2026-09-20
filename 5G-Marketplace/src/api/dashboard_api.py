"""
Dashboard API Module

This module provides endpoints for the marketplace dashboard, displaying system metrics,
active slices, vendor performance, and other analytics.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta

# Configure logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter()

# Import dependencies from main
from src.main import (
    get_vendor_registry,
    get_ndt,
    get_slice_selection_engine,
    get_compliance_monitor,
    get_feedback_loop
)

@router.get("/overview")
async def get_dashboard_overview(
    vendor_registry=Depends(get_vendor_registry),
    ndt=Depends(get_ndt),
    feedback_loop=Depends(get_feedback_loop)
):
    """Get dashboard overview with key metrics
    
    Returns:
        Dict: Dashboard overview data
    """
    try:
        # Get vendor count
        vendors = vendor_registry.list_vendors()
        
        # Get active slices from NDT
        active_slices = await ndt.get_all_telemetry()
        
        # Calculate metrics
        total_vendors = len(vendors)
        total_offerings = sum(len(vendor_registry.get_vendor_offerings(v["vendor_id"])) for v in vendors)
        total_active_slices = len(active_slices)
        
        # Get top vendors by rating
        top_vendors = []
        for vendor in vendors:
            vendor_id = vendor["vendor_id"]
            rating = feedback_loop.get_vendor_rating(vendor_id)
            top_vendors.append({
                "vendor_id": vendor_id,
                "name": vendor["name"],
                "rating": rating
            })
        
        # Sort by rating (descending)
        top_vendors.sort(key=lambda x: x["rating"], reverse=True)
        top_vendors = top_vendors[:5]  # Get top 5
        
        return {
            "marketplace_metrics": {
                "total_vendors": total_vendors,
                "total_offerings": total_offerings,
                "active_slices": total_active_slices,
                "timestamp": datetime.now().isoformat()
            },
            "top_vendors": top_vendors
        }
    except Exception as e:
        logger.error(f"Error getting dashboard overview: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.get("/active-slices")
async def get_active_slices(
    ndt=Depends(get_ndt),
    vendor_registry=Depends(get_vendor_registry)
):
    """Get information about all active slices
    
    Returns:
        List: Active slice information
    """
    try:
        # Get active slices from NDT
        active_slices = await ndt.get_all_telemetry()
        
        # Enrich with vendor information
        result = []
        for slice_id, telemetry in active_slices.items():
            vendor_id = telemetry.get("vendor_id")
            vendor_info = {}
            
            if vendor_id:
                vendor_info = vendor_registry.get_vendor_info(vendor_id) or {}
            
            # Calculate uptime
            start_time = telemetry.get("start_time")
            uptime_seconds = 0
            if start_time:
                try:
                    start_dt = datetime.fromisoformat(start_time)
                    uptime_seconds = (datetime.now() - start_dt).total_seconds()
                except Exception:
                    pass
            
            # Format slice data
            slice_data = {
                "slice_id": slice_id,
                "slice_type": telemetry.get("slice_type", "unknown"),
                "vendor": {
                    "vendor_id": vendor_id,
                    "name": vendor_info.get("name", "Unknown Vendor")
                },
                "status": "active",
                "uptime_seconds": uptime_seconds,
                "qos_actual": telemetry.get("qos_actual", {}),
                "qos_promised": telemetry.get("qos_promised", {}),
                "location": telemetry.get("location", "unknown")
            }
            
            result.append(slice_data)
        
        return result
    except Exception as e:
        logger.error(f"Error getting active slices: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.get("/vendor-performance")
async def get_vendor_performance(
    vendor_registry=Depends(get_vendor_registry),
    feedback_loop=Depends(get_feedback_loop)
):
    """Get vendor performance metrics
    
    Returns:
        List: Vendor performance data
    """
    try:
        # Get all vendors
        vendors = vendor_registry.list_vendors()
        
        # Get performance data for each vendor
        result = []
        for vendor in vendors:
            vendor_id = vendor["vendor_id"]
            
            # Get vendor rating
            rating = feedback_loop.get_vendor_rating(vendor_id)
            
            # Get vendor offerings
            offerings = vendor_registry.get_vendor_offerings(vendor_id)
            
            # Calculate performance metrics
            performance_data = {
                "vendor_id": vendor_id,
                "name": vendor["name"],
                "rating": rating,
                "offerings_count": len(offerings),
                "supported_regions": vendor.get("supported_regions", []),
                "capabilities": vendor_registry.get_vendor_capabilities(vendor_id) or {}
            }
            
            result.append(performance_data)
        
        return result
    except Exception as e:
        logger.error(f"Error getting vendor performance: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.get("/slice-types")
async def get_slice_types_distribution(
    ndt=Depends(get_ndt)
):
    """Get distribution of slice types
    
    Returns:
        Dict: Slice type distribution
    """
    try:
        # Get active slices from NDT
        active_slices = await ndt.get_all_telemetry()
        
        # Count slice types
        slice_types = {
            "eMBB": 0,
            "URLLC": 0,
            "mMTC": 0,
            "other": 0
        }
        
        for slice_id, telemetry in active_slices.items():
            slice_type = telemetry.get("slice_type", "other")
            if slice_type in slice_types:
                slice_types[slice_type] += 1
            else:
                slice_types["other"] += 1
        
        return {
            "distribution": slice_types,
            "total": len(active_slices)
        }
    except Exception as e:
        logger.error(f"Error getting slice types distribution: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.get("/system-health")
async def get_system_health(
    vendor_registry=Depends(get_vendor_registry),
    ndt=Depends(get_ndt),
    slice_selection_engine=Depends(get_slice_selection_engine),
    compliance_monitor=Depends(get_compliance_monitor),
    feedback_loop=Depends(get_feedback_loop)
):
    """Get system health status
    
    Returns:
        Dict: System health information
    """
    try:
        return {
            "components": {
                "vendor_registry": vendor_registry.status(),
                "ndt": ndt.status(),
                "slice_selection_engine": slice_selection_engine.status(),
                "compliance_monitor": compliance_monitor.status(),
                "feedback_loop": feedback_loop.status()
            },
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting system health: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.get("/qos-violations")
async def get_qos_violations(
    compliance_monitor=Depends(get_compliance_monitor),
    vendor_registry=Depends(get_vendor_registry)
):
    """Get QoS violations data
    
    Returns:
        Dict: QoS violations information
    """
    try:
        # Get violation counts from compliance monitor
        violation_counts = compliance_monitor.violation_counts
        
        # Prepare result
        result = []
        for slice_id, count in violation_counts.items():
            # Get vendor information if available
            vendor_id = None
            vendor_name = "Unknown"
            
            # In a real implementation, we would look up the vendor for this slice
            # For now, we'll just include the slice ID and violation count
            
            result.append({
                "slice_id": slice_id,
                "violation_count": count,
                "vendor_id": vendor_id,
                "vendor_name": vendor_name
            })
        
        return result
    except Exception as e:
        logger.error(f"Error getting QoS violations: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}") 