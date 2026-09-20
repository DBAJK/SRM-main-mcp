"""
Slice Selection Engine Module

This module provides the slice selection engine for the marketplace platform.
It selects the optimal vendor slice based on customer requirements.
"""

import logging
import asyncio
from typing import Dict, List, Any, Optional
import math

# Configure logging
logger = logging.getLogger(__name__)

class SliceSelectionEngine:
    """Slice selection engine for the marketplace platform"""
    
    def __init__(self):
        """Initialize the slice selection engine"""
        self.vendor_registry = None
        self.ai_agent = None
        self.ndt = None
        self.logger = logging.getLogger(__name__)
    
    def register_vendor_registry(self, vendor_registry):
        """Register the vendor registry
        
        Args:
            vendor_registry: Vendor registry instance
        """
        self.vendor_registry = vendor_registry
        logger.info("Vendor registry registered with slice selection engine")
    
    def register_ai_agent(self, ai_agent):
        """Register the AI agent
        
        Args:
            ai_agent: AI agent instance
        """
        self.ai_agent = ai_agent
        logger.info("AI agent registered with slice selection engine")
    
    def register_ndt(self, ndt):
        """Register the Network Digital Twin
        
        Args:
            ndt: Network Digital Twin instance
        """
        self.ndt = ndt
        logger.info("Network Digital Twin registered with slice selection engine")
    
    async def classify_slice_type(self, qos_requirements: Dict[str, Any]) -> str:
        """Classify slice type based on QoS requirements
        
        Args:
            qos_requirements: QoS requirements
            
        Returns:
            str: Slice type (eMBB, URLLC, mMTC)
        """
        if self.ai_agent:
            # Use AI agent for classification
            return await self.ai_agent.classify_slice_type(qos_requirements)
        else:
            # Fallback to rule-based classification
            return self._rule_based_classification(qos_requirements)
    
    def _rule_based_classification(self, qos_requirements: Dict[str, Any]) -> str:
        """Rule-based slice classification
        
        Args:
            qos_requirements: QoS requirements
            
        Returns:
            str: Slice type (eMBB, URLLC, mMTC)
        """
        # Extract QoS parameters with defaults
        latency_ms = qos_requirements.get("latency_ms", 50)
        bandwidth_mbps = qos_requirements.get("bandwidth_mbps", 100)
        reliability_percent = qos_requirements.get("reliability_percent", 99.9)
        
        # URLLC: Low latency, high reliability
        if latency_ms <= 10 and reliability_percent >= 99.999:
            return "URLLC"
        
        # eMBB: High bandwidth
        elif bandwidth_mbps >= 100:
            return "eMBB"
        
        # mMTC: Default for IoT-like requirements
        else:
            return "mMTC"
    
    async def query_vendors(self, 
                           qos_requirements: Dict[str, Any], 
                           slice_type: str, 
                           location: str) -> List[Dict[str, Any]]:
        """Query vendors for matching offers
        
        Args:
            qos_requirements: QoS requirements
            slice_type: Slice type (eMBB, URLLC, mMTC)
            location: Location for the slice
            
        Returns:
            List[Dict]: List of matching offers
        """
        if not self.vendor_registry:
            logger.error("Vendor registry not registered")
            return []
        
        # Find matching offerings
        try:
            matching_offers = self.vendor_registry.find_matching_offerings(
                qos_requirements=qos_requirements,
                slice_type=slice_type,
                location=location
            )
            
            logger.info(f"Found {len(matching_offers)} matching offers for {slice_type} slice in {location}")
            return matching_offers
        except Exception as e:
            logger.error(f"Error querying vendors: {str(e)}")
            return []
    
    async def select_best_offer(self, 
                               offers: List[Dict[str, Any]], 
                               qos_requirements: Dict[str, Any],
                               customer_preferences: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
        """Select the best offer from a list of offers
        
        Args:
            offers: List of offers
            qos_requirements: QoS requirements
            customer_preferences: Customer preferences
            
        Returns:
            Dict: Best offer, or None if no offers
        """
        if not offers:
            logger.warning("No offers to select from")
            return None
        
        # Default customer preferences if not provided
        if customer_preferences is None:
            customer_preferences = {
                "price_weight": 0.3,
                "qos_weight": 0.5,
                "reputation_weight": 0.2
            }
        
        try:
            # Score each offer using advanced AI scoring
            scored_offers = []
            
            for offer in offers:
                if self.ai_agent and hasattr(self.ai_agent, 'score_vendor_offer'):
                    # Use AI agent for scoring if available
                    score = await self.ai_agent.score_vendor_offer(
                        offer=offer,
                        qos_requirements=qos_requirements,
                        customer_preferences=customer_preferences
                    )
                else:
                    # Use enhanced ML-based scoring
                    score = self._advanced_score_offer(offer, qos_requirements)
                
                scored_offers.append((score, offer))
            
            # Sort by score (descending)
            scored_offers.sort(key=lambda x: x[0], reverse=True)
            
            # Return the best offer
            if scored_offers:
                best_score, best_offer = scored_offers[0]
                logger.info(f"Selected best offer with score {best_score:.2f}")
                return best_offer
            else:
                return None
        except Exception as e:
            logger.error(f"Error selecting best offer: {str(e)}")
            return offers[0] if offers else None
    
    def _advanced_score_offer(self, offer: Dict[str, Any], qos_requirements: Dict[str, Any]) -> float:
        """Advanced AI-based scoring function for network slice offers
        
        This function uses a weighted scoring approach that considers:
        1. Basic QoS parameters (latency, bandwidth, reliability)
        2. Advanced network slice template attributes
        3. Slice type-specific optimizations
        4. Cost efficiency
        5. Vendor reputation
        
        Args:
            offer: Vendor offer
            qos_requirements: QoS requirements
            
        Returns:
            float: Score (0-100)
        """
        # Get slice type from offer or default to eMBB
        slice_type = offer.get("slice_type", "eMBB")
        
        # Extract advanced parameters if available
        advanced_params = qos_requirements.get("advanced_attributes", {})
        
        # Get vendor's advanced attributes
        vendor_advanced_attrs = offer.get("advanced_attributes", {})
        
        # Calculate weights based on slice type and advanced parameters
        weights = self._calculate_criteria_weights(slice_type, advanced_params)
        
        # Score different aspects of the offering
        scores = {
            "latency": self._score_latency(offer, qos_requirements, slice_type),
            "bandwidth": self._score_bandwidth(offer, qos_requirements, slice_type),
            "reliability": self._score_reliability(offer, qos_requirements, slice_type),
            "price": self._calculate_price_score(offer, slice_type),
            "reputation": min(1.0, offer.get("reputation_score", 0.5) / 5.0)
        }
        
        # Score advanced attributes if available
        if advanced_params and vendor_advanced_attrs:
            advanced_scores = {
                "availability": self._score_availability(offer, advanced_params),
                "deterministic": self._score_deterministic_communication(offer, advanced_params),
                "packet_size": self._score_packet_size(offer, advanced_params),
                "group_comm": self._score_group_communication(offer, advanced_params),
                "mission_critical": self._score_mission_critical(offer, advanced_params)
            }
            
            # Add advanced scores to the main scores dictionary
            scores.update(advanced_scores)
        
        # Calculate final weighted score
        final_score = 0.0
        total_weight = sum(weights.values())
        
        for criterion, score in scores.items():
            if criterion in weights:
                # Normalize the weight
                normalized_weight = weights[criterion] / total_weight
                final_score += score * normalized_weight
        
        # Scale to 0-100
        final_score = final_score * 100
        
        logger.debug(f"Offer {offer.get('offering_id', 'unknown')} scored {final_score:.2f}/100")
        return final_score
    
    def _calculate_criteria_weights(self, slice_type: str, advanced_params: Dict[str, Any]) -> Dict[str, float]:
        """Calculate weights for different criteria based on slice type and advanced parameters
        
        Args:
            slice_type: Type of network slice (eMBB, URLLC, mMTC)
            advanced_params: Advanced parameters from the request
            
        Returns:
            Dict: Weights for different criteria
        """
        # Base weights for different slice types
        if slice_type == "URLLC":
            weights = {
                "latency": 0.35,
                "reliability": 0.25,
                "bandwidth": 0.10,
                "price": 0.10,
                "reputation": 0.05,
                "availability": 0.05,
                "deterministic": 0.05,
                "packet_size": 0.02,
                "group_comm": 0.01,
                "mission_critical": 0.02
            }
        elif slice_type == "mMTC":
            weights = {
                "latency": 0.10,
                "reliability": 0.15,
                "bandwidth": 0.10,
                "price": 0.25,
                "reputation": 0.05,
                "availability": 0.10,
                "deterministic": 0.05,
                "packet_size": 0.10,
                "group_comm": 0.05,
                "mission_critical": 0.05
            }
        else:  # eMBB
            weights = {
                "latency": 0.15,
                "reliability": 0.15,
                "bandwidth": 0.30,
                "price": 0.15,
                "reputation": 0.05,
                "availability": 0.05,
                "deterministic": 0.02,
                "packet_size": 0.05,
                "group_comm": 0.05,
                "mission_critical": 0.03
            }
        
        # Adjust weights based on advanced parameters
        if advanced_params:
            # If mission critical is specified, increase its weight
            if advanced_params.get("missionCritical") and advanced_params["missionCritical"] != "none":
                weights["mission_critical"] *= 2.0
                weights["reliability"] *= 1.5
                weights["latency"] *= 1.2
                
                # Normalize other weights
                total = sum(weights.values())
                for key in weights:
                    weights[key] = weights[key] / total
            
            # If deterministic communication is required, increase its weight
            if advanced_params.get("deterministic") == "yes":
                weights["deterministic"] *= 3.0
                weights["latency"] *= 1.5
                
                # Normalize other weights
                total = sum(weights.values())
                for key in weights:
                    weights[key] = weights[key] / total
        
        return weights
    
    def _score_latency(self, offering: Dict[str, Any], qos_params: Dict[str, Any], slice_type: str) -> float:
        """Score latency based on requirements
        
        Args:
            offering: Vendor offering
            qos_params: QoS parameters
            slice_type: Slice type
            
        Returns:
            float: Score (0-1)
        """
        required_latency = float(qos_params.get("latency", 50))
        offered_latency = float(offering.get("latency", 100))
        
        # For URLLC, use a stricter scoring function
        if slice_type == "URLLC":
            if offered_latency <= required_latency:
                return 1.0
            else:
                # Exponential penalty for exceeding required latency in URLLC
                return max(0.0, math.exp(-0.5 * (offered_latency - required_latency) / required_latency))
        else:
            # For other slice types, use a more lenient scoring
            if offered_latency <= required_latency:
                return 1.0
            else:
                # Linear penalty for exceeding required latency
                return max(0.0, 1.0 - (offered_latency - required_latency) / required_latency)
    
    def _score_bandwidth(self, offering: Dict[str, Any], qos_params: Dict[str, Any], slice_type: str) -> float:
        """Score bandwidth based on requirements
        
        Args:
            offering: Vendor offering
            qos_params: QoS parameters
            slice_type: Slice type
            
        Returns:
            float: Score (0-1)
        """
        required_bandwidth = float(qos_params.get("bandwidth", 100))
        offered_bandwidth = float(offering.get("bandwidth", 100))
        
        # For eMBB, use a stricter scoring function
        if slice_type == "eMBB":
            if offered_bandwidth >= required_bandwidth:
                # Bonus for exceeding bandwidth requirements for eMBB
                return min(1.0, 1.0 + 0.2 * (offered_bandwidth - required_bandwidth) / required_bandwidth)
            else:
                # Steep penalty for not meeting bandwidth in eMBB
                return max(0.0, (offered_bandwidth / required_bandwidth) ** 2)
        else:
            # For other slice types, use a more lenient scoring
            if offered_bandwidth >= required_bandwidth:
                return 1.0
            else:
                # Linear penalty for not meeting bandwidth
                return max(0.0, offered_bandwidth / required_bandwidth)
    
    def _score_reliability(self, offering: Dict[str, Any], qos_params: Dict[str, Any], slice_type: str) -> float:
        """Score reliability based on requirements
        
        Args:
            offering: Vendor offering
            qos_params: QoS parameters
            slice_type: Slice type
            
        Returns:
            float: Score (0-1)
        """
        required_reliability = float(qos_params.get("reliability", 99.0))
        offered_reliability = float(offering.get("reliability", 99.0))
        
        # Convert to failure rates for more meaningful comparison (e.g., 99.9% -> 0.1% failure)
        required_failure = 100 - required_reliability
        offered_failure = 100 - offered_reliability
        
        # For URLLC, use a stricter scoring function
        if slice_type == "URLLC" or slice_type == "mMTC":
            if offered_failure <= required_failure:
                return 1.0
            # Exponential penalty for higher failure rates
            return max(0.0, math.exp(-2.0 * (offered_failure / required_failure - 1.0)))
        
        # For other slice types, use a more lenient scoring
        if offered_failure <= required_failure:
            return 1.0
        
        # Linear penalty for higher failure rates
        return max(0.0, 1.0 - (offered_failure - required_failure) / required_failure)
    
    def _score_availability(self, offering: Dict[str, Any], advanced_params: Dict[str, Any]) -> float:
        """Score availability based on requirements
        
        Args:
            offering: Vendor offering
            advanced_params: Advanced parameters
            
        Returns:
            float: Score (0-1)
        """
        # Get vendor's advanced attributes
        vendor_attrs = offering.get("advanced_attributes", {})
        
        # Get required and offered availability levels
        required_availability = advanced_params.get("availability", "medium")
        offered_availability = vendor_attrs.get("availability", "medium")
        
        # Define availability levels and their numeric values
        availability_levels = {
            "low": 1,
            "medium": 2,
            "high": 3,
            "very-high": 4
        }
        
        # Convert to numeric values
        required_level = availability_levels.get(required_availability, 2)
        offered_level = availability_levels.get(offered_availability, 2)
        
        # Score based on difference between required and offered
        if offered_level >= required_level:
            # Bonus for exceeding requirements
            return min(1.0, 1.0 + 0.1 * (offered_level - required_level))
        else:
            # Penalty for not meeting requirements
            return max(0.0, offered_level / required_level)
    
    def _score_deterministic_communication(self, offering: Dict[str, Any], advanced_params: Dict[str, Any]) -> float:
        """Score deterministic communication based on requirements
        
        Args:
            offering: Vendor offering
            advanced_params: Advanced parameters
            
        Returns:
            float: Score (0-1)
        """
        # Get vendor's advanced attributes
        vendor_attrs = offering.get("advanced_attributes", {})
        
        # Check if deterministic communication is required
        required_deterministic = advanced_params.get("deterministic", "no")
        offered_deterministic = vendor_attrs.get("deterministic", "no")
        
        # If deterministic is required but not offered, severe penalty
        if required_deterministic == "yes" and offered_deterministic != "yes":
            return 0.0
        
        # If deterministic is required and offered, check periodicity
        if required_deterministic == "yes" and offered_deterministic == "yes":
            required_periodicity = float(advanced_params.get("periodicity", 0.01))
            offered_periodicity = float(vendor_attrs.get("periodicity", 0.01))
            
            # Lower periodicity is better (more frequent updates)
            if offered_periodicity <= required_periodicity:
                return 1.0
            else:
                # Penalty for higher periodicity
                return max(0.0, required_periodicity / offered_periodicity)
        
        # If deterministic is not required, no penalty
        return 1.0
    
    def _score_packet_size(self, offering: Dict[str, Any], advanced_params: Dict[str, Any]) -> float:
        """Score packet size support based on requirements
        
        Args:
            offering: Vendor offering
            advanced_params: Advanced parameters
            
        Returns:
            float: Score (0-1)
        """
        # Get vendor's advanced attributes
        vendor_attrs = offering.get("advanced_attributes", {})
        
        # Get required and offered packet sizes
        required_size = advanced_params.get("maxPacketSize", "1500")
        offered_size = vendor_attrs.get("maxPacketSize", "1500")
        
        # Convert to numeric values
        required_size = int(required_size)
        offered_size = int(offered_size)
        
        # If offered size is sufficient, full score
        if offered_size >= required_size:
            return 1.0
        else:
            # Penalty for smaller packet size
            return max(0.0, offered_size / required_size)
    
    def _score_group_communication(self, offering: Dict[str, Any], advanced_params: Dict[str, Any]) -> float:
        """Score group communication support based on requirements
        
        Args:
            offering: Vendor offering
            advanced_params: Advanced parameters
            
        Returns:
            float: Score (0-1)
        """
        # Get vendor's advanced attributes
        vendor_attrs = offering.get("advanced_attributes", {})
        
        # Get required and offered group communication support
        required_group = advanced_params.get("groupCommunication", "none")
        offered_group = vendor_attrs.get("groupCommunication", "none")
        
        # Define group communication levels and their numeric values
        group_levels = {
            "none": 1,
            "unicast": 2,
            "multicast": 3,
            "sc-ptm": 4
        }
        
        # Convert to numeric values
        required_level = group_levels.get(required_group, 1)
        offered_level = group_levels.get(offered_group, 1)
        
        # Score based on difference between required and offered
        if offered_level >= required_level:
            return 1.0
        else:
            # Penalty for not meeting requirements
            return max(0.0, offered_level / required_level)
    
    def _score_mission_critical(self, offering: Dict[str, Any], advanced_params: Dict[str, Any]) -> float:
        """Score mission critical support based on requirements
        
        Args:
            offering: Vendor offering
            advanced_params: Advanced parameters
            
        Returns:
            float: Score (0-1)
        """
        # Get vendor's advanced attributes
        vendor_attrs = offering.get("advanced_attributes", {})
        
        # Get required and offered mission critical support
        required_mc = advanced_params.get("missionCritical", "none")
        offered_mc = vendor_attrs.get("missionCritical", "none")
        
        # Define mission critical levels and their numeric values
        mc_levels = {
            "none": 1,
            "prioritization": 2,
            "preemption": 3,
            "mcptt": 4
        }
        
        # Convert to numeric values
        required_level = mc_levels.get(required_mc, 1)
        offered_level = mc_levels.get(offered_mc, 1)
        
        # Score based on difference between required and offered
        if offered_level >= required_level:
            return 1.0
        else:
            # Severe penalty for not meeting mission critical requirements
            return max(0.0, (offered_level / required_level) ** 2)
    
    def _calculate_qos_match(self, offering: Dict[str, Any], qos_params: Dict[str, Any], slice_type: str) -> float:
        """Calculate overall QoS match score
        
        Args:
            offering: Vendor offering
            qos_params: QoS parameters
            slice_type: Slice type
            
        Returns:
            float: Score (0-1)
        """
        # Calculate scores for each QoS parameter
        latency_score = self._score_latency(offering, qos_params, slice_type)
        bandwidth_score = self._score_bandwidth(offering, qos_params, slice_type)
        reliability_score = self._score_reliability(offering, qos_params, slice_type)
        
        # Weight the scores based on slice type
        if slice_type == "URLLC":
            # URLLC prioritizes latency and reliability
            weights = {"latency": 0.5, "reliability": 0.4, "bandwidth": 0.1}
        elif slice_type == "eMBB":
            # eMBB prioritizes bandwidth
            weights = {"latency": 0.2, "reliability": 0.2, "bandwidth": 0.6}
        else:  # mMTC
            # mMTC has more balanced requirements
            weights = {"latency": 0.3, "reliability": 0.4, "bandwidth": 0.3}
        
        # Calculate weighted score
        qos_score = (
            latency_score * weights["latency"] +
            bandwidth_score * weights["bandwidth"] +
            reliability_score * weights["reliability"]
        )
        
        return qos_score
    
    def _calculate_price_score(self, offering: Dict[str, Any], slice_type: str) -> float:
        """Calculate price score
        
        Args:
            offering: Vendor offering
            slice_type: Slice type
            
        Returns:
            float: Score (0-1)
        """
        price = offering.get("cost", 100)
        
        # Define reference prices for different slice types
        if slice_type == "URLLC":
            # URLLC is expected to be more expensive
            reference_price = 250
        elif slice_type == "eMBB":
            # eMBB is mid-range
            reference_price = 150
        else:  # mMTC
            # mMTC is expected to be cheaper
            reference_price = 75
        
        # Calculate price score (lower price is better)
        if price <= reference_price:
            # Bonus for prices below reference
            return min(1.0, 1.0 + 0.2 * (reference_price - price) / reference_price)
        else:
            # Penalty for prices above reference
            return max(0.0, 1.0 - 0.5 * (price - reference_price) / reference_price)
    
    async def deploy_slice(self, offer: Dict[str, Any], customer_id: str) -> Dict[str, Any]:
        """Deploy a slice with a vendor
        
        Args:
            offer: Vendor offer
            customer_id: Customer ID
            
        Returns:
            Dict: Deployment result
        """
        try:
            # In a real implementation, this would call the vendor's API
            # to deploy the slice. For now, we'll simulate a successful deployment.
            
            slice_id = f"slice-{customer_id}-{offer['offering_id'][:8]}"
            vendor_id = offer["vendor_id"]
            slice_type = offer["slice_type"]
            qos_promised = offer["qos_parameters"]
            location = offer["locations"][0] if offer["locations"] else "unknown"
            
            # Register slice with NDT
            if self.ndt:
                await self.ndt.register_slice(
                    slice_id=slice_id,
                    vendor_id=vendor_id,
                    slice_type=slice_type,
                    qos_promised=qos_promised,
                    location=location
                )
                logger.info(f"Registered slice {slice_id} with NDT")
            
            # Return deployment result
            return {
                "slice_id": slice_id,
                "vendor_id": vendor_id,
                "slice_type": slice_type,
                "qos_promised": qos_promised,
                "location": location,
                "status": "deployed"
            }
        except Exception as e:
            logger.error(f"Error deploying slice: {str(e)}")
            return {
                "status": "failed",
                "error": str(e)
            }
    
    def status(self) -> Dict[str, Any]:
        """Get slice selection engine status
        
        Returns:
            Dict: Status information
        """
        return {
            "status": "operational",
            "vendor_registry_available": self.vendor_registry is not None,
            "ai_agent_available": self.ai_agent is not None,
            "ndt_available": self.ndt is not None
        }
    
    def score_vendor_offering(self, vendor: Dict[str, Any], slice_type: str, qos_params: Dict[str, Any]) -> float:
        """
        Score a vendor offering based on QoS requirements and slice type using advanced decision techniques
        
        Args:
            vendor: Vendor data
            slice_type: Type of slice (eMBB, URLLC, mMTC)
            qos_params: QoS parameters requested by the customer
            
        Returns:
            float: Score between 0 and 100
        """
        logger.info(f"Scoring vendor {vendor['name']} for {slice_type} slice")
        
        try:
            # Check if vendor supports this slice type
            if slice_type not in vendor.get("offerings", {}):
                logger.warning(f"Vendor {vendor['name']} does not offer {slice_type} slice type")
                return 0.0
            
            # Get vendor's offering for this slice type
            offering = vendor["offerings"][slice_type]
            
            # Get advanced QoS parameters if provided (from Step 2 form)
            advanced_params = qos_params.get("advanced_params", {})
            
            # Determine weights based on slice type and advanced parameters
            weights = self._calculate_criteria_weights(slice_type, advanced_params)
            
            # Calculate individual criterion scores
            scores = {}
            
            # Core QoS metrics (always evaluated)
            scores["latency"] = self._score_latency(offering, qos_params, slice_type)
            scores["bandwidth"] = self._score_bandwidth(offering, qos_params, slice_type)
            scores["reliability"] = self._score_reliability(offering, qos_params, slice_type)
            
            # Advanced metrics (if provided)
            if "availability" in advanced_params:
                scores["availability"] = self._score_availability(offering, advanced_params)
            
            if "deterministic" in advanced_params and advanced_params["deterministic"] == "yes":
                scores["deterministic"] = self._score_deterministic_communication(offering, advanced_params)
            
            if "maxPacketSize" in advanced_params:
                scores["packet_size"] = self._score_packet_size(offering, advanced_params)
            
            if "groupCommunication" in advanced_params and advanced_params["groupCommunication"] != "none":
                scores["group_comm"] = self._score_group_communication(offering, advanced_params)
            
            if "missionCritical" in advanced_params and advanced_params["missionCritical"] != "none":
                scores["mission_critical"] = self._score_mission_critical(offering, advanced_params)
            
            # Calculate weighted QoS score
            qos_score = 0.0
            total_weight = 0.0
            
            for criterion, score in scores.items():
                if criterion in weights:
                    qos_score += score * weights[criterion]
                    total_weight += weights[criterion]
            
            if total_weight > 0:
                qos_score = qos_score / total_weight
            else:
                qos_score = 0.5  # Default middle score
            
            # Get vendor reputation score (10-20% of total based on slice type)
            reputation_weight = 0.1
            if slice_type == "URLLC":
                # For critical applications, reputation is more important
                reputation_weight = 0.2
                
            reputation_score = vendor.get("rating", 3.0) / 5.0
            
            # Calculate price score (10-20% of total)
            price_weight = 0.2
            if "price_sensitivity" in advanced_params:
                # Adjust price weight based on customer's price sensitivity
                sensitivity = advanced_params["price_sensitivity"]
                if sensitivity == "high":
                    price_weight = 0.3
                elif sensitivity == "low":
                    price_weight = 0.1
            
            price_score = self._calculate_price_score(offering, slice_type)
            
            # Calculate total score (0-100)
            qos_weight = 1.0 - (reputation_weight + price_weight)
            total_score = (qos_score * qos_weight + 
                          reputation_score * reputation_weight + 
                          price_score * price_weight) * 100
            
            logger.info(f"Vendor {vendor['name']} scored {total_score:.2f} for {slice_type} slice")
            return total_score
            
        except Exception as e:
            logger.error(f"Error scoring vendor offering: {str(e)}")
            return 0.0
    
    def get_score_breakdown(self, offer: Dict[str, Any], qos_requirements: Dict[str, Any]) -> Dict[str, Any]:
        """Get detailed breakdown of the scoring calculation for a vendor offer
        
        This function returns the detailed scoring process, including:
        - Individual criterion scores
        - Weights for each criterion
        - Calculation steps
        - Neural network-like representation of the scoring process
        
        Args:
            offer: Vendor offer
            qos_requirements: QoS requirements
            
        Returns:
            Dict: Detailed scoring breakdown
        """
        # Get slice type from offer or default to eMBB
        slice_type = offer.get("slice_type", "eMBB")
        
        # Extract advanced parameters if available
        advanced_params = qos_requirements.get("advanced_params", {})
        
        # Get vendor's advanced attributes
        vendor_advanced_attrs = offer.get("advanced_attributes", {})
        
        # Calculate weights based on slice type and advanced parameters
        weights = self._calculate_criteria_weights(slice_type, advanced_params)
        
        # Score different aspects of the offering
        scores = {
            "latency": self._score_latency(offer, qos_requirements, slice_type),
            "bandwidth": self._score_bandwidth(offer, qos_requirements, slice_type),
            "reliability": self._score_reliability(offer, qos_requirements, slice_type),
        }
        
        # Score advanced attributes if available
        if advanced_params and vendor_advanced_attrs:
            if "availability" in advanced_params:
                scores["availability"] = self._score_availability(offer, advanced_params)
            
            if "deterministic" in advanced_params and advanced_params["deterministic"] == "yes":
                scores["deterministic"] = self._score_deterministic_communication(offer, advanced_params)
            
            if "maxPacketSize" in advanced_params:
                scores["packet_size"] = self._score_packet_size(offer, advanced_params)
            
            if "groupCommunication" in advanced_params and advanced_params["groupCommunication"] != "none":
                scores["group_comm"] = self._score_group_communication(offer, advanced_params)
            
            if "missionCritical" in advanced_params and advanced_params["missionCritical"] != "none":
                scores["mission_critical"] = self._score_mission_critical(offer, advanced_params)
        
        # Calculate weighted QoS score
        qos_score = 0.0
        total_weight = 0.0
        
        for criterion, score in scores.items():
            if criterion in weights:
                qos_score += score * weights[criterion]
                total_weight += weights[criterion]
        
        if total_weight > 0:
            qos_score = qos_score / total_weight
        else:
            qos_score = 0.5  # Default middle score
        
        # Get vendor reputation score (10-20% of total based on slice type)
        reputation_weight = 0.1
        if slice_type == "URLLC":
            # For critical applications, reputation is more important
            reputation_weight = 0.2
            
        reputation_score = offer.get("reputation_score", 3.0) / 5.0
        scores["reputation"] = reputation_score
        
        # Calculate price score (10-20% of total)
        price_weight = 0.2
        if "price_sensitivity" in advanced_params:
            # Adjust price weight based on customer's price sensitivity
            sensitivity = advanced_params["price_sensitivity"]
            if sensitivity == "high":
                price_weight = 0.3
            elif sensitivity == "low":
                price_weight = 0.1
        
        price_score = self._calculate_price_score(offer, slice_type)
        scores["price"] = price_score
        
        # Calculate total score (0-100)
        qos_weight = 1.0 - (reputation_weight + price_weight)
        total_score = (qos_score * qos_weight + 
                      reputation_score * reputation_weight + 
                      price_score * price_weight) * 100
        
        # Calculate weighted scores for visualization
        weighted_scores = {}
        for criterion, score in scores.items():
            if criterion in weights:
                weighted_scores[criterion] = score * (weights[criterion] / total_weight) * qos_weight
        
        # Add reputation and price weighted scores
        weighted_scores["reputation"] = reputation_score * reputation_weight
        weighted_scores["price"] = price_score * price_weight
        
        # Create calculation steps for visualization
        calculation_steps = []
        
        # Add QoS criteria
        for criterion, score in scores.items():
            if criterion in weights:
                weight = weights[criterion] / total_weight * qos_weight
                weighted_score = score * weight
                contribution = (weighted_score / (total_score / 100)) * 100
                
                step = {
                    "criterion": criterion,
                    "raw_score": score,
                    "weight": weight,
                    "weighted_score": weighted_score,
                    "contribution": contribution
                }
                calculation_steps.append(step)
        
        # Add reputation and price
        calculation_steps.append({
            "criterion": "reputation",
            "raw_score": reputation_score,
            "weight": reputation_weight,
            "weighted_score": reputation_score * reputation_weight,
            "contribution": (reputation_score * reputation_weight / (total_score / 100)) * 100
        })
        
        calculation_steps.append({
            "criterion": "price",
            "raw_score": price_score,
            "weight": price_weight,
            "weighted_score": price_score * price_weight,
            "contribution": (price_score * price_weight / (total_score / 100)) * 100
        })
        
        # Sort calculation steps by contribution (highest first)
        calculation_steps.sort(key=lambda x: x["contribution"], reverse=True)
        
        # Create neural network representation
        nn_layers = [
            {
                "name": "input",
                "nodes": [
                    {"name": "latency", "value": offer.get("latency", 0)},
                    {"name": "bandwidth", "value": offer.get("bandwidth", 0)},
                    {"name": "reliability", "value": offer.get("reliability", 0)},
                    {"name": "cost", "value": offer.get("cost", 0)},
                ]
            },
            {
                "name": "scoring",
                "nodes": [
                    {"name": criterion, "value": score} for criterion, score in scores.items()
                ]
            },
            {
                "name": "weighting",
                "nodes": [
                    {"name": "qos", "value": qos_weight},
                    {"name": "reputation", "value": reputation_weight},
                    {"name": "price", "value": price_weight}
                ]
            },
            {
                "name": "output",
                "nodes": [
                    {"name": "final_score", "value": total_score}
                ]
            }
        ]
        
        # Generate explanation based on top contributors
        top_contributors = calculation_steps[:3]
        explanation = f"This vendor scored {total_score:.2f}/100 primarily due to "
        
        if len(top_contributors) > 0:
            explanation += f"strong {top_contributors[0]['criterion']} ({top_contributors[0]['raw_score']:.2f})"
            
            if len(top_contributors) > 1:
                explanation += f" and {top_contributors[1]['criterion']} ({top_contributors[1]['raw_score']:.2f})"
                
            if len(top_contributors) > 2:
                explanation += f", with good {top_contributors[2]['criterion']} ({top_contributors[2]['raw_score']:.2f})"
        
        explanation += f". The vendor's offering aligns well with the {slice_type} slice type requirements."
        
        # Return complete breakdown
        return {
            "final_score": total_score,
            "slice_type": slice_type,
            "individual_scores": scores,
            "weights": weights,
            "weighted_scores": weighted_scores,
            "calculation_steps": calculation_steps,
            "neural_network": nn_layers,
            "explanation": explanation
        }