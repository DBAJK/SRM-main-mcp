"""
Gemini API Integration Module

This module provides integration with Google's Gemini API for analyzing network slice telemetry data
and providing insights and recommendations.
"""

import os
import logging
import json
from typing import Dict, List, Any, Optional
from datetime import datetime

# Try to import google.generativeai, but make it optional
try:
    import google.generativeai as genai
except ImportError:
    genai = None
    logging.warning("Google Generative AI not available. Some features may not work.")

# Configure logging
logger = logging.getLogger(__name__)

class GeminiAnalyzer:
    """Gemini API integration for analyzing network slice telemetry data"""
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize the Gemini Analyzer
        
        Args:
            api_key: Gemini API key (if None, will try to get from environment variable)
        """
        # Use the provided API key as default
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY") or "AIzaSyBMNwnCU_B9xcmpAOSHuzyasUxn4G7JxOo"
        
        if genai is None:
            logger.warning("Gemini API not available. GeminiAnalyzer will not function properly.")
            self.model = None
            return
        
        try:
            genai.configure(api_key=self.api_key)
            logger.info("Gemini API configured successfully")
        except Exception as e:
            logger.error(f"Error configuring Gemini API: {str(e)}")
        
        # Set default model
        self.model_name = "gemini-1.5-pro"
        try:
            self.model = genai.GenerativeModel(
                self.model_name,
                generation_config={
                    "temperature": 0.2,
                    "top_p": 0.95,
                    "top_k": 40
                }
            )
        except Exception as e:
            logger.error(f"Error creating Gemini model: {str(e)}")
            self.model = None
    
    async def analyze_telemetry(self, telemetry_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze telemetry data using Gemini API
        
        Args:
            telemetry_data: Telemetry data from the Network Digital Twin
            
        Returns:
            Dict: Analysis results
        """
        try:
            # Extract relevant information from telemetry data
            slice_id = telemetry_data.get("slice_id", "unknown")
            slice_type = telemetry_data.get("slice_type", "unknown")
            vendor_id = telemetry_data.get("vendor_id", "unknown")
            qos_promised = telemetry_data.get("qos_promised", {})
            qos_actual = telemetry_data.get("qos_actual", {})
            violations = telemetry_data.get("violations", [])
            
            # Create context-aware prompt for Gemini
            prompt = f"""
            You are an expert 5G network slice monitoring system powered by AI. Your task is to analyze telemetry data from a 5G network slice and provide actionable insights.

            # NETWORK SLICE DETAILS
            Slice ID: {slice_id}
            Slice Type: {slice_type}
            Vendor ID: {vendor_id}
            
            # PROMISED QoS PARAMETERS
            ```json
            {json.dumps(qos_promised, indent=2)}
            ```
            
            # ACTUAL QoS PARAMETERS
            ```json
            {json.dumps(qos_actual, indent=2)}
            ```
            
            # RECENT QoS VIOLATIONS
            ```json
            {json.dumps(violations[-5:] if violations else [], indent=2)}
            ```
            
            # ANALYSIS REQUIREMENTS
            1. Provide a concise assessment of the slice performance (2-3 sentences)
            2. Identify specific QoS violations or concerning trends with precise metrics
            3. Provide 3-4 concrete recommendations for optimizing the slice configuration
            4. Calculate a health score from 0-100 based on how well actual parameters match promised ones
               - For parameters where lower is better (latency, jitter), score = min(100, 100 * (promised / actual))
               - For parameters where higher is better (bandwidth, reliability), score = min(100, 100 * (actual / promised))
               - Overall health score should be the average of individual parameter scores
            
            # REQUIRED OUTPUT FORMAT
            Your analysis must include:
            1. Performance Assessment: [your assessment]
            2. QoS Violations: [list specific violations]
            3. Optimization Recommendations: [numbered list]
            4. Health Score: [numerical score]/100
            """
            
            # Call Gemini API
            response = await self.model.generate_content_async(prompt)
            
            # Process response
            analysis_text = response.text
            
            # Extract health score - assuming Gemini includes it in the response
            health_score = 0
            try:
                # Try to find a health score in the text
                for line in analysis_text.split('\n'):
                    if "health score" in line.lower():
                        # Extract number from string
                        import re
                        numbers = re.findall(r'\d+', line)
                        if numbers:
                            health_score = int(numbers[0])
                            # Ensure it's in range 0-100
                            health_score = max(0, min(100, health_score))
                            break
            except Exception as e:
                logger.error(f"Error extracting health score: {str(e)}")
                health_score = 0
            
            # Return analysis results
            return {
                "slice_id": slice_id,
                "timestamp": datetime.now().isoformat(),
                "analysis": analysis_text,
                "health_score": health_score,
                "model_used": self.model_name
            }
            
        except Exception as e:
            logger.error(f"Error analyzing telemetry with Gemini: {str(e)}")
            return {
                "error": f"Error analyzing telemetry: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }
    
    async def get_optimization_recommendations(self, telemetry_data: Dict[str, Any]) -> Dict[str, Any]:
        """Get optimization recommendations for a slice using Gemini API
        
        Args:
            telemetry_data: Telemetry data from the Network Digital Twin
            
        Returns:
            Dict: Optimization recommendations
        """
        try:
            # Extract relevant information from telemetry data
            slice_id = telemetry_data.get("slice_id", "unknown")
            slice_type = telemetry_data.get("slice_type", "unknown")
            qos_promised = telemetry_data.get("qos_promised", {})
            qos_actual = telemetry_data.get("qos_actual", {})
            qos_history = telemetry_data.get("qos_history", [])
            violations = telemetry_data.get("violations", [])
            
            # Create context-aware prompt for Gemini with 5G domain knowledge
            prompt = f"""
            You are an expert 5G network optimization AI assistant. Your task is to analyze network slice telemetry data and provide detailed optimization recommendations.

            # NETWORK SLICE DETAILS
            Slice ID: {slice_id}
            Slice Type: {slice_type}
            
            # PROMISED QoS PARAMETERS
            ```json
            {json.dumps(qos_promised, indent=2)}
            ```
            
            # CURRENT QoS PARAMETERS
            ```json
            {json.dumps(qos_actual, indent=2)}
            ```
            
            # RECENT QoS VIOLATIONS
            ```json
            {json.dumps(violations[-5:] if violations else [], indent=2)}
            ```
            
            # QoS HISTORY (RECENT MEASUREMENTS)
            ```json
            {json.dumps(qos_history[-5:] if qos_history else [], indent=2)}
            ```
            
            # SLICE TYPE CONTEXT
            {self._get_slice_type_context(slice_type)}
            
            # OPTIMIZATION REQUIREMENTS
            Based on the telemetry data and the specific characteristics of this {slice_type} slice, provide:
            1. Specific optimization recommendations with technical justification
            2. Parameter adjustments with precise target values
            3. Resource allocation changes with expected impact
            4. Priority level for each recommendation (High, Medium, Low)
            
            # REQUIRED OUTPUT FORMAT
            Format your recommendations as follows:
            
            ## Summary
            [1-2 sentence overview of current performance]
            
            ## Recommendations
            1. [First recommendation]
               - Target values: [specific parameter values]
               - Expected impact: [expected improvement]
               - Priority: [High/Medium/Low]
               - Technical justification: [brief explanation]
            
            2. [Second recommendation]
               ...
            
            ## Implementation Plan
            [Brief implementation sequence]
            """
            
            # Call Gemini API
            response = await self.model.generate_content_async(prompt)
            
            # Process response
            recommendations_text = response.text
            
            # Return recommendations
            return {
                "slice_id": slice_id,
                "timestamp": datetime.now().isoformat(),
                "recommendations": recommendations_text,
                "model_used": self.model_name
            }
            
        except Exception as e:
            logger.error(f"Error getting optimization recommendations with Gemini: {str(e)}")
            return {
                "error": f"Error getting optimization recommendations: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }
    
    def _get_slice_type_context(self, slice_type: str) -> str:
        """Get context information for different slice types
        
        Args:
            slice_type: The type of network slice
            
        Returns:
            str: Context information
        """
        contexts = {
            "eMBB": """
                Enhanced Mobile Broadband (eMBB) slices prioritize high data rates and traffic capacity.
                Key optimization areas:
                - Bandwidth efficiency and spectrum utilization
                - Maintaining consistent throughput under varying load conditions
                - Balancing coverage vs. capacity trade-offs
                - Video streaming and large file transfer optimization
                
                Typical KPIs:
                - Throughput: 100+ Mbps (downlink), 50+ Mbps (uplink)
                - Latency: 10-100ms acceptable
                - Connection density: Moderate
            """,
            
            "URLLC": """
                Ultra-Reliable Low-Latency Communication (URLLC) slices prioritize minimal latency and maximum reliability.
                Key optimization areas:
                - End-to-end latency minimization
                - Packet error rate reduction
                - Redundancy mechanisms without excessive overhead
                - Predictable performance under all conditions
                
                Typical KPIs:
                - Latency: 1-10ms (critical)
                - Reliability: 99.999%+ (critical)
                - Availability: 99.999%+
                - Packet error rate: <10^-5
            """,
            
            "mMTC": """
                Massive Machine-Type Communication (mMTC) slices prioritize connection density and energy efficiency.
                Key optimization areas:
                - Massive device connectivity management
                - Energy consumption minimization
                - Efficient small data transmission
                - Scalable access mechanisms
                
                Typical KPIs:
                - Connection density: Up to 1 million devices per km²
                - Energy efficiency: 10+ years battery life for IoT devices
                - Bandwidth: Low to moderate (often <100 Kbps per device)
                - Latency: Non-critical (seconds to minutes acceptable)
            """
        }
        
        return contexts.get(slice_type, "No specific context available for this slice type.") 