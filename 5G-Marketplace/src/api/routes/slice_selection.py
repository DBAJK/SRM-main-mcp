import logging
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import torch
import sys
import os

from src.slice_selection.engine import SliceSelectionEngine
from src.database.vendors import VendorDatabase
from src.database.slices import SliceDatabase
from src.ndt.simulator import NetworkDigitalTwin
from src.ai_agent.gemini_integration import GeminiAnalyzer
from src.ai_agent.context7_integration import Context7Enhancer

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/slice-selection", tags=["slice-selection"])

# Define models
class QoSRequirements(BaseModel):
    latency: str
    bandwidth: str
    reliability: str
    location: str

class SliceRequest(BaseModel):
    slice_type: str
    qos_requirements: QoSRequirements

class DeployRequest(BaseModel):
    slice_type: str
    qos_requirements: QoSRequirements
    vendor_id: str

class VendorOffer(BaseModel):
    id: str
    name: str
    score: float
    latency: float
    bandwidth: float
    reliability: float
    location: str
    cost: float
    advanced_attributes: Dict[str, Any]

class VendorResponse(BaseModel):
    vendors: List[VendorOffer]

class DeploymentResponse(BaseModel):
    slice_id: str
    vendor_id: str
    vendor_name: str
    deployment_time: str
    status: str

class MonitoringResponse(BaseModel):
    slice_id: str
    telemetry: Dict[str, Any]
    analysis: Optional[Dict[str, Any]] = None
    context7_insights: Optional[Dict[str, Any]] = None

class OptimizationResponse(BaseModel):
    slice_id: str
    recommendations: Dict[str, Any]
    context7_guidance: Optional[Dict[str, Any]] = None

class Context7DocsResponse(BaseModel):
    slice_type: str
    documentation: Dict[str, Any]

class VendorScoreBreakdownRequest(BaseModel):
    vendor_id: str
    slice_type: str
    qos_requirements: QoSRequirements

class VendorScoreBreakdownResponse(BaseModel):
    vendor_id: str
    vendor_name: str
    score_breakdown: Dict[str, Any]

class SliceTypePredictionRequest(BaseModel):
    text: str

class SliceTypePredictionResponse(BaseModel):
    slice_type: str
    confidence: float

# Global variables for model and tokenizer
model = None
tokenizer = None
label_names = ["eMBB", "URLLC", "mMTC"]

# Function to load the model and tokenizer
def load_model():
    global model, tokenizer
    if model is None:
        try:
            # Import necessary libraries
            from transformers import AutoTokenizer, AutoModelForSequenceClassification
            import torch
            
            # Use the Context_Model directory
            model_path = r"G:\5g_sliced\Context_Model"
            
            # Check if model exists
            if not os.path.exists(model_path):
                logger.warning(f"Model not found at {model_path}. Using mock predictions.")
                return False
            
            # Load tokenizer and model
            logger.info(f"Loading model from {model_path}")
            tokenizer = AutoTokenizer.from_pretrained(model_path)
            model = AutoModelForSequenceClassification.from_pretrained(model_path)
            
            return True
        except Exception as e:
            logger.error(f"Error loading model: {str(e)}")
            return False
    return True

# Dependency
def get_selection_engine():
    return SliceSelectionEngine()

def get_vendor_db():
    return VendorDatabase()

def get_slice_db():
    return SliceDatabase()

def get_ndt():
    return NetworkDigitalTwin()

def get_gemini_analyzer():
    return GeminiAnalyzer()

def get_context7_enhancer():
    return Context7Enhancer()

@router.post("/vendors", response_model=VendorResponse)
async def get_vendor_offers(
    request: SliceRequest,
    engine: SliceSelectionEngine = Depends(get_selection_engine),
    vendor_db: VendorDatabase = Depends(get_vendor_db)
):
    """
    Get vendor offers for a specific slice type and QoS requirements
    """
    logger.info(f"Processing vendor selection for slice type: {request.slice_type}")
    
    try:
        # Convert QoS string values to appropriate types
        qos_params = {
            "latency": float(request.qos_requirements.latency),
            "bandwidth": float(request.qos_requirements.bandwidth),
            "reliability": float(request.qos_requirements.reliability),
            "location": request.qos_requirements.location
        }
        
        # Add advanced parameters if they exist
        if hasattr(request.qos_requirements, 'advanced_params'):
            qos_params["advanced_params"] = request.qos_requirements.advanced_params
        
        # Get all vendors
        all_vendors = vendor_db.get_all_vendors()
        
        # Process vendors through selection engine
        scored_vendors = []
        for vendor in all_vendors:
            # Calculate score based on QoS match
            score = engine.score_vendor_offering(
                vendor, 
                request.slice_type, 
                qos_params
            )
            
            # Create vendor offer with score
            vendor_offer = VendorOffer(
                id=vendor["id"],
                name=vendor["name"],
                score=score,
                latency=vendor["offerings"][request.slice_type]["latency"],
                bandwidth=vendor["offerings"][request.slice_type]["bandwidth"],
                reliability=vendor["offerings"][request.slice_type]["reliability"],
                location=vendor["location"],
                cost=vendor["offerings"][request.slice_type]["cost"],
                advanced_attributes=vendor.get("advanced_attributes", {})
            )
            
            scored_vendors.append(vendor_offer)
        
        return VendorResponse(vendors=scored_vendors)
    
    except Exception as e:
        logger.error(f"Error processing vendor selection: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing vendor selection: {str(e)}")

@router.post("/deploy", response_model=DeploymentResponse)
async def deploy_slice(
    request: DeployRequest,
    engine: SliceSelectionEngine = Depends(get_selection_engine),
    vendor_db: VendorDatabase = Depends(get_vendor_db),
    slice_db: SliceDatabase = Depends(get_slice_db),
    ndt: NetworkDigitalTwin = Depends(get_ndt)
):
    """
    Deploy a network slice with the selected vendor
    """
    logger.info(f"Deploying slice with vendor ID: {request.vendor_id}")
    
    try:
        # Get vendor details
        vendor = vendor_db.get_vendor_by_id(request.vendor_id)
        if not vendor:
            raise HTTPException(status_code=404, detail=f"Vendor with ID {request.vendor_id} not found")
        
        # Generate slice ID
        slice_id = f"slice-{str(uuid.uuid4())[:8]}"
        
        # Convert QoS string values to appropriate types
        qos_params = {
            "latency": float(request.qos_requirements.latency),
            "bandwidth": float(request.qos_requirements.bandwidth),
            "reliability": float(request.qos_requirements.reliability),
            "location": request.qos_requirements.location
        }
        
        # Create slice data
        slice_data = {
            "id": slice_id,
            "type": request.slice_type,
            "vendor_id": vendor["id"],
            "vendor_name": vendor["name"],
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": "active",
            "latency": vendor["offerings"][request.slice_type]["latency"],
            "bandwidth": vendor["offerings"][request.slice_type]["bandwidth"],
            "reliability": vendor["offerings"][request.slice_type]["reliability"],
            "location": vendor["location"],
            "cost": vendor["offerings"][request.slice_type]["cost"]
        }
        
        # Add slice to database
        slice_db.add_slice(slice_data)
        
        # Register slice with NDT for monitoring
        qos_promised = {
            "latency_ms": vendor["offerings"][request.slice_type]["latency"],
            "bandwidth_mbps": vendor["offerings"][request.slice_type]["bandwidth"],
            "reliability_percent": vendor["offerings"][request.slice_type]["reliability"]
        }
        
        await ndt.register_slice(
            slice_id=slice_id,
            vendor_id=vendor["id"],
            slice_type=request.slice_type,
            qos_promised=qos_promised,
            location=request.qos_requirements.location
        )
        
        # Return deployment response
        return DeploymentResponse(
            slice_id=slice_id,
            vendor_id=vendor["id"],
            vendor_name=vendor["name"],
            deployment_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            status="Deployed Successfully"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deploying slice: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error deploying slice: {str(e)}")

@router.get("/monitor/{slice_id}", response_model=MonitoringResponse)
async def monitor_slice(
    slice_id: str,
    analyze: bool = False,
    use_context7: bool = True,
    ndt: NetworkDigitalTwin = Depends(get_ndt),
    gemini: GeminiAnalyzer = Depends(get_gemini_analyzer),
    context7: Context7Enhancer = Depends(get_context7_enhancer)
):
    """
    Monitor a deployed slice and optionally analyze with Gemini and Context7
    """
    logger.info(f"Monitoring slice: {slice_id}")
    
    try:
        # Get telemetry data from NDT
        telemetry = await ndt.get_slice_telemetry(slice_id)
        if not telemetry:
            raise HTTPException(status_code=404, detail=f"Slice with ID {slice_id} not found")
        
        # Create response
        response = MonitoringResponse(
            slice_id=slice_id,
            telemetry=telemetry
        )
        
        # If analyze flag is set, use Gemini to analyze telemetry
        if analyze:
            # Get analysis from Gemini
            analysis = await gemini.analyze_telemetry(telemetry)
            response.analysis = analysis
            
            # If Context7 is enabled, enhance the analysis
            if use_context7:
                # Get Context7 insights
                context7_insights = await context7.enhance_telemetry_analysis(telemetry, analysis)
                response.context7_insights = context7_insights.get("context7")
        
        return response
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error monitoring slice: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error monitoring slice: {str(e)}")

@router.get("/optimize/{slice_id}", response_model=OptimizationResponse)
async def optimize_slice(
    slice_id: str,
    use_context7: bool = True,
    ndt: NetworkDigitalTwin = Depends(get_ndt),
    gemini: GeminiAnalyzer = Depends(get_gemini_analyzer),
    context7: Context7Enhancer = Depends(get_context7_enhancer)
):
    """
    Get optimization recommendations for a deployed slice using Gemini and Context7
    """
    logger.info(f"Getting optimization recommendations for slice: {slice_id}")
    
    try:
        # Get telemetry data from NDT
        telemetry = await ndt.get_slice_telemetry(slice_id)
        if not telemetry:
            raise HTTPException(status_code=404, detail=f"Slice with ID {slice_id} not found")
        
        # Get optimization recommendations from Gemini
        recommendations = await gemini.get_optimization_recommendations(telemetry)
        
        # Create response
        response = OptimizationResponse(
            slice_id=slice_id,
            recommendations=recommendations
        )
        
        # If Context7 is enabled, get additional guidance
        if use_context7:
            slice_type = telemetry.get("slice_type", "unknown")
            context7_guidance = await context7.get_optimization_guidance(slice_type)
            response.context7_guidance = context7_guidance
        
        return response
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting optimization recommendations: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting optimization recommendations: {str(e)}")

@router.get("/context7/{slice_type}", response_model=Context7DocsResponse)
async def get_context7_docs(
    slice_type: str,
    topic: Optional[str] = None,
    context7: Context7Enhancer = Depends(get_context7_enhancer)
):
    """
    Get Context7 documentation for a specific slice type
    """
    logger.info(f"Getting Context7 documentation for slice type: {slice_type}")
    
    try:
        # Determine the library name based on slice type
        if slice_type in ["eMBB", "URLLC", "mMTC"]:
            library_name = f"5G-{slice_type}"
            if not topic:
                topic = "optimization"
        else:
            library_name = "5G-Network-Slicing"
            if not topic:
                topic = "general"
        
        # Get documentation from Context7
        docs = await context7.get_library_documentation(library_name, topic)
        
        # Return response
        return Context7DocsResponse(
            slice_type=slice_type,
            documentation=docs
        )
    
    except Exception as e:
        logger.error(f"Error getting Context7 documentation: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting Context7 documentation: {str(e)}")

@router.post("/vendor-score-breakdown", response_model=VendorScoreBreakdownResponse)
async def get_vendor_score_breakdown(
    request: VendorScoreBreakdownRequest,
    engine: SliceSelectionEngine = Depends(get_selection_engine),
    vendor_db: VendorDatabase = Depends(get_vendor_db)
):
    """
    Get detailed breakdown of the ML scoring algorithm for a specific vendor
    """
    logger.info(f"Getting score breakdown for vendor: {request.vendor_id}")
    
    try:
        # Get vendor details
        vendor = vendor_db.get_vendor_by_id(request.vendor_id)
        if not vendor:
            raise HTTPException(status_code=404, detail=f"Vendor with ID {request.vendor_id} not found")
        
        # Convert QoS string values to appropriate types
        qos_params = {
            "latency": float(request.qos_requirements.latency),
            "bandwidth": float(request.qos_requirements.bandwidth),
            "reliability": float(request.qos_requirements.reliability),
            "location": request.qos_requirements.location
        }
        
        # Add advanced parameters if they exist
        if hasattr(request.qos_requirements, 'advanced_params'):
            qos_params["advanced_params"] = request.qos_requirements.advanced_params
        
        # Create vendor offer object for scoring
        offer = {
            "id": vendor["id"],
            "name": vendor["name"],
            "slice_type": request.slice_type,
            "latency": vendor["offerings"][request.slice_type]["latency"],
            "bandwidth": vendor["offerings"][request.slice_type]["bandwidth"],
            "reliability": vendor["offerings"][request.slice_type]["reliability"],
            "location": vendor["location"],
            "cost": vendor["offerings"][request.slice_type]["cost"],
            "advanced_attributes": vendor.get("advanced_attributes", {}),
            "reputation_score": vendor.get("rating", 4.0)
        }
        
        # Get score breakdown
        score_breakdown = engine.get_score_breakdown(offer, qos_params)
        
        # Return response
        return VendorScoreBreakdownResponse(
            vendor_id=vendor["id"],
            vendor_name=vendor["name"],
            score_breakdown=score_breakdown
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting vendor score breakdown: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting vendor score breakdown: {str(e)}")

@router.get("/debug", response_model=Dict[str, str])
async def debug_endpoint():
    """
    Debug endpoint to check if the router is properly registered
    """
    return {"status": "ok", "message": "Slice selection router is working properly"}

@router.post("/predict-slice-type", response_model=SliceTypePredictionResponse)
async def predict_slice_type(request: SliceTypePredictionRequest):
    """
    Predict the slice type based on user input text
    """
    logger.info(f"Predicting slice type for text: {request.text}")
    
    try:
        # Check if model is loaded
        model_loaded = load_model()
        
        if model_loaded and model is not None and tokenizer is not None:
            # Use the model to predict
            device = next(model.parameters()).device
            
            inputs = tokenizer(request.text, return_tensors="pt", padding=True, truncation=True, max_length=128)
            
            # Move inputs to the same device as the model
            inputs = {key: value.to(device) for key, value in inputs.items()}
            
            model.eval()  # Set model to evaluation mode
            with torch.no_grad():
                outputs = model(**inputs)
                predictions = torch.nn.functional.softmax(outputs.logits, dim=-1)
                predicted_class = torch.argmax(predictions, dim=-1).item()
                confidence = predictions[0][predicted_class].item()
            
            predicted_slice_type = label_names[predicted_class]
            
            logger.info(f"Predicted slice type: {predicted_slice_type} with confidence {confidence}")
            
            return SliceTypePredictionResponse(
                slice_type=predicted_slice_type,
                confidence=confidence
            )
        else:
            # If model is not loaded, use mock predictions based on keywords in the text
            text = request.text.lower()
            
            # Simple keyword matching for demo purposes
            if "video" in text or "stream" in text or "gaming" in text or "cloud" in text or "broadband" in text:
                slice_type = "eMBB"
                confidence = 0.85
            elif "latency" in text or "reliable" in text or "real-time" in text or "autonomous" in text:
                slice_type = "URLLC"
                confidence = 0.82
            elif "iot" in text or "sensor" in text or "device" in text or "smart city" in text:
                slice_type = "mMTC"
                confidence = 0.78
            else:
                # Default to eMBB with lower confidence if no keywords match
                slice_type = "eMBB"
                confidence = 0.65
            
            logger.info(f"Using mock prediction: {slice_type} with confidence {confidence}")
            
            return SliceTypePredictionResponse(
                slice_type=slice_type,
                confidence=confidence
            )
    
    except Exception as e:
        logger.error(f"Error predicting slice type: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error predicting slice type: {str(e)}") 