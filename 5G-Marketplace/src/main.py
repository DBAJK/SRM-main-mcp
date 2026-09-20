#!/usr/bin/env python3
"""
5G Marketplace Platform - Main Application

This is the main entry point for the 5G Marketplace platform.
It initializes all components and starts the FastAPI server.
"""

import os
import logging
import asyncio
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

# Import components
from src.vendor_registry.registry import VendorRegistry
from src.ai_agent.agent import AIAgent
from src.slice_selection.engine import SliceSelectionEngine
from src.ndt.simulator import NetworkDigitalTwin
from src.compliance_monitor.monitor import SliceComplianceMonitor
from src.feedback_loop.loop import FeedbackLoop

# Get absolute path for logs
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_DIR = os.path.join(BASE_DIR, "logs")
DATA_DIR = os.path.join(BASE_DIR, "data")
FEEDBACK_DIR = os.path.join(DATA_DIR, "feedback")

# Ensure directories exist
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(FEEDBACK_DIR, exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(LOGS_DIR, "marketplace.log"))
    ]
)

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="5G Network Slicing Marketplace",
    description="A marketplace for dynamic 5G network slice selection and vendor negotiation",
    version="0.1.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create component instances
vendor_registry = VendorRegistry()
ai_agent = AIAgent()
ndt = NetworkDigitalTwin()
slice_selection_engine = SliceSelectionEngine()
compliance_monitor = SliceComplianceMonitor()
feedback_loop = FeedbackLoop()

# Component dependency functions
def get_vendor_registry():
    return vendor_registry

def get_ai_agent():
    return ai_agent

def get_ndt():
    return ndt

def get_slice_selection_engine():
    return slice_selection_engine

def get_compliance_monitor():
    return compliance_monitor

def get_feedback_loop():
    return feedback_loop

# Import API routers after component initialization
from src.api.customer_api import router as customer_router
from src.api.vendor_api import router as vendor_router
from src.api.dashboard_api import router as dashboard_router

# Include routers
app.include_router(customer_router, prefix="/api/customer", tags=["Customer API"])
app.include_router(vendor_router, prefix="/api/vendor", tags=["Vendor API"])
app.include_router(dashboard_router, prefix="/api/dashboard", tags=["Dashboard API"])

@app.on_event("startup")
async def startup_event():
    """Initialize components on startup"""
    logger.info("Starting 5G Marketplace platform")
    
    # Register components with each other
    slice_selection_engine.register_vendor_registry(vendor_registry)
    slice_selection_engine.register_ai_agent(ai_agent)
    slice_selection_engine.register_ndt(ndt)
    
    compliance_monitor.register_ndt(ndt)
    compliance_monitor.register_feedback_loop(feedback_loop)
    
    feedback_loop.register_ai_agent(ai_agent)
    feedback_loop.register_vendor_registry(vendor_registry)
    
    # Initialize AI agent
    await ai_agent.initialize()
    
    # Start Network Digital Twin
    await ndt.start()
    
    # Start compliance monitor
    await compliance_monitor.start_monitoring()
    
    # Start feedback loop
    await feedback_loop.start_feedback_loop()
    
    logger.info("All components initialized and started")

@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown components"""
    logger.info("Shutting down 5G Marketplace platform")
    
    # Stop feedback loop
    await feedback_loop.stop_feedback_loop()
    
    # Stop compliance monitor
    await compliance_monitor.stop_monitoring()
    
    # Stop Network Digital Twin
    await ndt.shutdown()
    
    logger.info("All components stopped")

@app.get("/", tags=["Health"])
async def root():
    """Root endpoint for health check"""
    return {"message": "5G Marketplace platform is running"}

@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "components": {
            "vendor_registry": vendor_registry.status(),
            "ai_agent": ai_agent.status(),
            "ndt": ndt.status(),
            "slice_selection_engine": slice_selection_engine.status(),
            "compliance_monitor": compliance_monitor.status(),
            "feedback_loop": feedback_loop.status()
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True) 