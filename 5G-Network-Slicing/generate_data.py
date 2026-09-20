import os
import sys
import random
import time
import json
import argparse
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

# Add a custom JSON encoder to handle NumPy types
class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        return super(NumpyEncoder, self).default(obj)

class NetworkDataGenerator:
    """Generates realistic 5G network slicing data and saves it to a file"""
    
    def __init__(self, base_stations=5, clients=30, steps=100, 
                 mobility_level=0.3, traffic_variance=0.4):
        """Initialize the data generator"""
        # Configuration
        self.num_base_stations = base_stations
        self.num_clients = clients
        self.num_steps = steps
        self.mobility_level = mobility_level  # How much clients move (0-1)
        self.traffic_variance = traffic_variance  # How much traffic varies (0-1)
        
        # Define slice types and their characteristics
        self.slice_types = ["eMBB", "URLLC", "mMTC"]
        self.slice_colors = {
            "eMBB": "#FF6B6B",   # Red - high bandwidth
            "URLLC": "#45B7D1",  # Blue - low latency
            "mMTC": "#FFBE0B"    # Yellow - IoT 
        }
        
        # Slice profiles - default distribution of resources
        self.slice_profiles = {
            "eMBB": {  # Enhanced Mobile Broadband
                "default_allocation": 0.6,  # Default 60% of resources
                "bandwidth_req": 0.9,      # High bandwidth needs
                "latency_req": 0.4,        # Medium latency needs
                "connection_density": 0.3,  # Low connection density
                "mobility_support": 0.7,    # Good mobility support
                "typical_apps": ["video streaming", "AR/VR", "file download"],
                "priority_weight": 1.0  # Weight for AI-assisted formula
            },
            "URLLC": {  # Ultra-Reliable Low-Latency Communication
                "default_allocation": 0.3,  # Default 30% of resources
                "bandwidth_req": 0.4,      # Medium bandwidth needs
                "latency_req": 0.95,       # Very low latency needs
                "connection_density": 0.2,  # Low connection density
                "mobility_support": 0.5,    # Medium mobility support
                "typical_apps": ["autonomous vehicles", "industrial automation", "remote surgery"],
                "priority_weight": 1.5  # Higher weight for critical services
            },
            "mMTC": {  # Massive Machine-Type Communication
                "default_allocation": 0.1,  # Default 10% of resources
                "bandwidth_req": 0.2,      # Low bandwidth needs
                "latency_req": 0.3,        # High latency tolerance
                "connection_density": 0.9,  # Very high connection density
                "mobility_support": 0.2,    # Low mobility needs
                "typical_apps": ["IoT sensors", "smart meters", "asset tracking"],
                "priority_weight": 0.8  # Lower weight compared to others
            }
        }
        
        # Traffic patterns - how traffic behaves over time for each slice
        self.traffic_patterns = {
            "eMBB": {
                "day_pattern": [0.2, 0.1, 0.05, 0.05, 0.1, 0.2, 0.4, 0.5, 0.6, 0.7, 
                               0.8, 0.9, 0.95, 0.9, 0.85, 0.8, 0.85, 0.9, 0.95, 
                               0.9, 0.8, 0.6, 0.4, 0.3],  # Hourly traffic pattern
                "burst_probability": 0.2,  # Probability of traffic burst
                "burst_magnitude": 0.5     # How significant are bursts
            },
            "URLLC": {
                "day_pattern": [0.3, 0.3, 0.3, 0.3, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8,
                               0.9, 0.9, 0.8, 0.7, 0.7, 0.8, 0.8, 0.7, 0.6, 
                               0.5, 0.4, 0.4, 0.3, 0.3],  # More stable pattern
                "burst_probability": 0.1,  # Lower probability of bursts
                "burst_magnitude": 0.8     # Very significant bursts
            },
            "mMTC": {
                "day_pattern": [0.5, 0.5, 0.5, 0.4, 0.4, 0.4, 0.5, 0.6, 0.6, 0.7,
                               0.7, 0.7, 0.7, 0.7, 0.7, 0.7, 0.6, 0.6, 0.5, 
                               0.5, 0.5, 0.5, 0.5, 0.5],  # Very stable pattern
                "burst_probability": 0.05,  # Very low probability of bursts
                "burst_magnitude": 0.3      # Small bursts
            }
        }
        
        # Initialize data structures
        self.base_stations = []
        self.clients = []
        self.simulation_data = []
        
    def generate_network(self):
        """Generate the base network topology"""
        # Generate base stations with random positions
        for i in range(self.num_base_stations):
            x = random.uniform(100, 900)
            y = random.uniform(100, 900)
            radius = random.uniform(150, 250)
            
            # Generate initial slice allocations
            # These will evolve over time in the simulation
            slice_allocation = {}
            for slice_type in self.slice_types:
                # Add some randomness to the default allocation
                default = self.slice_profiles[slice_type]["default_allocation"]
                slice_allocation[slice_type] = default * random.uniform(0.8, 1.2)
            
            # Normalize allocations to sum to 1
            total = sum(slice_allocation.values())
            for slice_type in slice_allocation:
                slice_allocation[slice_type] /= total
            
            # Initial usage (start with lower than allocation)
            slice_usage = {
                slice_type: allocation * random.uniform(0.3, 0.7) 
                for slice_type, allocation in slice_allocation.items()
            }
            
            # Add base station
            self.base_stations.append({
                'id': i,
                'x': x,
                'y': y,
                'radius': radius,
                'capacity': 1000 * random.uniform(0.8, 1.2),  # Vary capacity a bit
                'slice_allocation': slice_allocation,
                'slice_usage': slice_usage,
                'slice_demands': {slice_type: 0 for slice_type in self.slice_types},
                'total_clients': 0
            })
        
        # Generate client distribution
        # Distribution of clients across slice types
        slice_distribution = {"eMBB": 0.5, "URLLC": 0.3, "mMTC": 0.2}
        
        # Generate clients
        for i in range(self.num_clients):
            # Assign to a random base station based on proximity (weighted)
            bs_weights = []
            for bs in self.base_stations:
                # More clients in central base stations (for realism)
                center_dist = np.sqrt((bs['x'] - 500)**2 + (bs['y'] - 500)**2)
                weight = 1000 / (center_dist + 100)  # Higher weight for central BSs
                bs_weights.append(weight)
                
            # Normalize weights
            total_weight = sum(bs_weights)
            bs_weights = [w/total_weight for w in bs_weights]
            
            # Choose base station
            bs_id = np.random.choice(range(len(self.base_stations)), p=bs_weights)
            bs = self.base_stations[bs_id]
            
            # Place within coverage area
            angle = random.uniform(0, 2 * np.pi)
            distance = random.uniform(30, bs['radius'] * 0.8)
            x = bs['x'] + distance * np.cos(angle)
            y = bs['y'] + distance * np.sin(angle)
            
            # Assign to a slice based on distribution
            slice_type = random.choices(
                list(slice_distribution.keys()),
                weights=list(slice_distribution.values())
            )[0]
            
            # Set mobility pattern - how much this client moves
            mobility = random.random() * self.mobility_level
            
            # Generate data usage pattern - how much data this client uses
            data_intensity = random.uniform(0.2, 1.0)
            
            # Generate client record
            self.clients.append({
                'id': i,
                'x': x,
                'y': y,
                'base_station': bs_id,
                'slice': slice_type,
                'active': random.random() < 0.7,  # 70% active initially
                'data_rate': data_intensity,  # Normalized data rate
                'mobility': mobility,
                'last_position_update': 0,
                'app_type': random.choice(self.slice_profiles[slice_type]["typical_apps"])
            })
            
            # Update base station client count
            self.base_stations[bs_id]['total_clients'] += 1
            self.base_stations[bs_id]['slice_demands'][slice_type] += data_intensity
    
    def simulate_network_dynamics(self):
        """Simulate network changes over time"""
        for step in range(self.num_steps):
            # Simulated timestamp - assuming each step is 5 minutes
            timestamp = datetime.now() + timedelta(minutes=5*step)
            hour = timestamp.hour
            
            # 1. Update client activity and positions
            self.update_clients(step, hour)
            
            # 2. Update base station slice allocations
            self.optimize_slice_allocations(step)
            
            # 3. Update slice usage based on active clients
            self.update_slice_usage(step, hour)
            
            # 4. Capture network state
            self.capture_network_state(step, timestamp)
            
            # Print progress
            if step % 10 == 0:
                print(f"Generated step {step}/{self.num_steps}")
                
        print(f"Generated {self.num_steps} simulation steps")
    
    def update_clients(self, step, hour):
        """Update client activity and positions"""
        for client in self.clients:
            # 1. Update activity state
            # Time-of-day affects probability of being active
            time_factor = self.traffic_patterns[client['slice']]["day_pattern"][hour]
            active_prob = 0.7 * time_factor  # 70% base probability adjusted by time
            
            # Random activity changes
            if random.random() < 0.1:  # 10% chance to consider state change
                client['active'] = random.random() < active_prob
            
            # 2. Update position if active and mobile
            if client['active'] and client['mobility'] > 0 and step - client['last_position_update'] >= 3:
                client['last_position_update'] = step
                
                # Move based on mobility factor
                move_distance = client['mobility'] * 15  # Max 15 units per update
                client['x'] += random.uniform(-move_distance, move_distance)
                client['y'] += random.uniform(-move_distance, move_distance)
                
                # Check if still in range of assigned base station
                bs = self.base_stations[client['base_station']]
                dist = np.sqrt((client['x'] - bs['x'])**2 + (client['y'] - bs['y'])**2)
                
                if dist > bs['radius']:
                    # Find a new base station if out of range
                    new_bs_id = self.find_nearest_base_station(client['x'], client['y'])
                    
                    if new_bs_id != client['base_station']:
                        # Update base station client counts
                        self.base_stations[client['base_station']]['total_clients'] -= 1
                        self.base_stations[client['base_station']]['slice_demands'][client['slice']] -= client['data_rate']
                        
                        self.base_stations[new_bs_id]['total_clients'] += 1
                        self.base_stations[new_bs_id]['slice_demands'][client['slice']] += client['data_rate']
                        
                        # Update client's base station
                        client['base_station'] = new_bs_id
                    else:
                        # Move back toward base station
                        angle = np.arctan2(bs['y'] - client['y'], bs['x'] - client['x'])
                        client['x'] = bs['x'] - (bs['radius'] - 10) * np.cos(angle)
                        client['y'] = bs['y'] - (bs['radius'] - 10) * np.sin(angle)
    
    def find_nearest_base_station(self, x, y):
        """Find the nearest base station to a position"""
        min_dist = float('inf')
        nearest_bs = 0
        
        for bs in self.base_stations:
            dist = np.sqrt((x - bs['x'])**2 + (y - bs['y'])**2)
            
            # Consider only if within range
            if dist <= bs['radius'] and dist < min_dist:
                min_dist = dist
                nearest_bs = bs['id']
                
        return nearest_bs
    
    def ai_slice_advisor(self, current_allocations, base_station_state, client_data):
        """
        AI model to advise on slice allocations.
        Initially, this will be a simple pass-through or a rule-based adjustment.
        
        Args:
            current_allocations (dict): Allocations from the mathematical formula.
            base_station_state (dict): Current state of the base station.
            client_data (list): List of all clients.
            
        Returns:
            dict: AI-advised slice allocations.
        """
        # Placeholder: For now, AI agrees with the formula
        advised_allocations = current_allocations.copy()
        
        # Example of a simple AI rule:
        # If URLLC demand is high and its current allocation is below a threshold, boost it.
        # This is a rudimentary example of how an AI might "fix" the formula's output.
        
        # Calculate current total demand for URLLC at this BS
        urllc_demand_at_bs = 0
        for client in client_data:
            if client['base_station'] == base_station_state['id'] and client['slice'] == 'URLLC' and client['active']:
                urllc_demand_at_bs += client['data_rate'] # Assuming data_rate is a proxy for demand resource units

        # Normalize demand against a typical client data rate to get an idea of "number of demanding clients"
        # This is a heuristic. A more robust metric for "high demand" would be needed.
        # Let's say average data_rate is 0.5 for calculation.
        normalized_urllc_demand_count = urllc_demand_at_bs / 0.5 


        if 'URLLC' in advised_allocations and base_station_state['slice_demands'].get('URLLC', 0) > 0: # Check if URLLC is a slice for this BS and has demand
             # Heuristic: if more than 2 "average" URLLC clients are demanding resources
            if normalized_urllc_demand_count > 2 and advised_allocations['URLLC'] < self.slice_profiles['URLLC']['default_allocation'] * 0.5:
                print(f"AI Advisor: Boosting URLLC for BS {base_station_state['id']} due to high demand and low current formulaic allocation.")
                
                # Calculate how much to boost: aim to bring it up to 70% of its default_allocation as a minimum
                boost_target = self.slice_profiles['URLLC']['default_allocation'] * 0.7
                current_urllc_alloc = advised_allocations['URLLC']
                boost_amount = max(0, boost_target - current_urllc_alloc)

                # How to distribute the "taken" allocation? For simplicity, take proportionally from others.
                # This is a complex part where a real AI would be much smarter.
                # For now, let's just increase URLLC and rely on the later normalization step.
                # This simplistic approach might lead to other slices being starved if not careful.
                # A better AI would re-distribute more intelligently.
                
                if boost_amount > 0:
                    # Check if we can boost without taking others below a minimum (e.g. 5% of their default)
                    # This part needs careful design to avoid issues.
                    # For this example, we'll simplify and assume normalization will handle it,
                    # though in a real system this is where complex AI decision making occurs.
                    advised_allocations['URLLC'] += boost_amount
                    
                    # Reduce other slices proportionally to fund the boost
                    # This is a very basic way to do it.
                    total_other_alloc = sum(alloc for st, alloc in advised_allocations.items() if st != 'URLLC')
                    if total_other_alloc > 0:
                        for slice_type in advised_allocations:
                            if slice_type != 'URLLC':
                                reduction_share = advised_allocations[slice_type] / total_other_alloc
                                advised_allocations[slice_type] -= boost_amount * reduction_share
                                advised_allocations[slice_type] = max(0.01, advised_allocations[slice_type]) # Ensure not zero

        return advised_allocations

    def optimize_slice_allocations(self, step):
        """Update slice allocations based on demand, incorporating AI advice."""
        if step % 5 == 0:  # Perform optimization only periodically
            for bs_state in self.base_stations:
                current_demands = bs_state['slice_demands']
                weighted_demands = {}
                total_weighted_demand = 0

                for slice_type, demand_value in current_demands.items():
                    if demand_value > 0: # Only consider slices with active demand
                        weight = self.slice_profiles.get(slice_type, {}).get("priority_weight", 1.0)
                        weighted_demand = demand_value * weight
                        weighted_demands[slice_type] = weighted_demand
                        total_weighted_demand += weighted_demand
                    else:
                        # Ensure slice_type is in weighted_demands if it was in current_demands but had 0 demand, for advisor awareness
                        if slice_type in self.slice_types:
                             weighted_demands[slice_type] = 0 


                formula_allocations = {}
                if total_weighted_demand > 0:
                    for slice_type, wd in weighted_demands.items():
                        formula_allocations[slice_type] = wd / total_weighted_demand
                else: # No demand for any slice
                    # Fallback to default allocations if no demand at all, or keep existing if some had 0 demand
                    # but we want to preserve their presence for the AI advisor
                    for slice_type in self.slice_types:
                        if slice_type in weighted_demands: # Slices considered (even with 0 demand)
                           formula_allocations[slice_type] = bs_state['slice_allocation'].get(slice_type, self.slice_profiles[slice_type]["default_allocation"])
                        else: # Slices not in current demands at all, use default
                           formula_allocations[slice_type] = self.slice_profiles[slice_type]["default_allocation"]
                    # Normalize these default/existing allocations as they might not sum to 1
                    current_total_formula_alloc = sum(formula_allocations.values())
                    if current_total_formula_alloc > 0:
                        for st in formula_allocations:
                            formula_allocations[st] /= current_total_formula_alloc
                    else: # Should not happen if defaults are > 0
                        # Distribute equally if all defaults were 0
                        num_s = len(self.slice_types)
                        for st in self.slice_types:
                            formula_allocations[st] = 1/num_s if num_s > 0 else 1


                # Get advice from the AI model
                # Pass a copy of client data to avoid unintended modifications if AI model alters it
                ai_advised_allocations = self.ai_slice_advisor(
                    formula_allocations.copy(), 
                    bs_state, 
                    [c.copy() for c in self.clients]
                )

                # Ensure minimum allocation for each slice type that has presence
                # The AI advisor might also enforce this, or do it more intelligently
                final_allocations_before_smoothing = ai_advised_allocations.copy()
                for slice_type in self.slice_types: # Iterate over all possible slice types
                    if slice_type in final_allocations_before_smoothing: # If this slice type is part of current BS allocations
                        min_alloc_threshold = self.slice_profiles[slice_type]["default_allocation"] * 0.1 # At least 10% of its default capacity, if active
                        final_allocations_before_smoothing[slice_type] = max(
                            final_allocations_before_smoothing[slice_type],
                            min_alloc_threshold if current_demands.get(slice_type, 0) > 0 else 0.0 # only enforce min if there was some demand or it was active
                        )
                    # If a slice type is not in final_allocations_before_smoothing, it means it had no demand AND AI didn't add it.
                    # We can add it with 0 allocation to ensure it is present in bs_state['slice_allocation'] for consistency
                    # or rely on the smoothing logic to handle potentially missing keys if that's robust.
                    # For now, let's ensure all slice types configured for the network are present.
                    elif slice_type not in final_allocations_before_smoothing:
                         final_allocations_before_smoothing[slice_type] = 0.0


                # Smooth the transition and normalize
                current_bs_allocations = bs_state['slice_allocation']
                for slice_type in self.slice_types:
                    current_alloc_val = current_bs_allocations.get(slice_type, 0) # Get current or 0 if not set
                    ideal_alloc_val = final_allocations_before_smoothing.get(slice_type, 0) # Get AI advised or 0
                    
                    # Apply smoothing: move 20% toward the ideal AI-advised allocation
                    current_bs_allocations[slice_type] = current_alloc_val * 0.8 + ideal_alloc_val * 0.2
                
                # Normalize to ensure sum = 1 after smoothing and potential minimums
                total_allocation_sum = sum(current_bs_allocations.values())
                if total_allocation_sum > 0:
                    for slice_type in current_bs_allocations:
                        current_bs_allocations[slice_type] /= total_allocation_sum
                else:
                    # Fallback if all allocations became zero (e.g. no demands and no defaults set for some reason)
                    # Distribute equally among available slice types for this BS
                    num_bs_slice_types = len([s for s in self.slice_types if s in current_bs_allocations])
                    if num_bs_slice_types > 0:
                        equal_share = 1 / num_bs_slice_types
                        for slice_type in current_bs_allocations:
                             current_bs_allocations[slice_type] = equal_share
    
    def update_slice_usage(self, step, hour):
        """Update slice usage based on active clients and time patterns"""
        for bs in self.base_stations:
            bs_id = bs['id']
            
            # Calculate base usage for each slice based on active clients
            base_usage = {slice_type: 0 for slice_type in self.slice_types}
            clients_per_slice = {slice_type: 0 for slice_type in self.slice_types}
            
            for client in self.clients:
                if client['base_station'] == bs_id and client['active']:
                    slice_type = client['slice']
                    # Factor in time-of-day pattern
                    time_factor = self.traffic_patterns[slice_type]["day_pattern"][hour]
                    
                    # Calculate usage contribution
                    usage_contribution = client['data_rate'] * time_factor
                    base_usage[slice_type] += usage_contribution
                    clients_per_slice[slice_type] += 1
            
            # Add random bursts/fluctuations in traffic
            for slice_type in self.slice_types:
                # Check for traffic burst
                if random.random() < self.traffic_patterns[slice_type]["burst_probability"]:
                    # Apply a traffic burst
                    burst = self.traffic_patterns[slice_type]["burst_magnitude"] * random.uniform(0.5, 1.0)
                    base_usage[slice_type] += burst * bs['slice_allocation'][slice_type]
                
                # Add random fluctuation proportional to traffic variance
                fluctuation = self.traffic_variance * random.uniform(-0.05, 0.05) * bs['slice_allocation'][slice_type]
                new_usage = base_usage[slice_type] + fluctuation
                
                # Scale to allocation
                max_allocation = bs['slice_allocation'][slice_type]
                new_usage = min(new_usage, max_allocation * 0.95)  # Cap at 95% to avoid saturation
                
                # Smooth change over time (exponential smoothing)
                current = bs['slice_usage'][slice_type]
                bs['slice_usage'][slice_type] = current * 0.7 + new_usage * 0.3
                
                # Ensure usage is within bounds
                bs['slice_usage'][slice_type] = max(0, min(bs['slice_usage'][slice_type], max_allocation))
                
                # Update demands based on actual usage and allocation
                # If usage is high relative to allocation, demand increases
                usage_ratio = bs['slice_usage'][slice_type] / max(0.01, max_allocation)
                if usage_ratio > 0.8:  # High utilization
                    # Increase demand
                    bs['slice_demands'][slice_type] *= 1.05
                elif usage_ratio < 0.3 and clients_per_slice[slice_type] > 0:  # Low utilization
                    # Decrease demand slightly
                    bs['slice_demands'][slice_type] *= 0.95
    
    def capture_network_state(self, step, timestamp):
        """Capture the current network state"""
        # Create a snapshot of the current state
        state = {
            'step': step,
            'timestamp': timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            'base_stations': [],
            'clients': []
        }
        
        # Capture base station state
        for bs in self.base_stations:
            bs_state = {
                'id': bs['id'],
                'x': bs['x'],
                'y': bs['y'],
                'radius': bs['radius'],
                'slice_allocation': bs['slice_allocation'].copy(),
                'slice_usage': bs['slice_usage'].copy(),
                'total_clients': bs['total_clients']
            }
            state['base_stations'].append(bs_state)
        
        # Capture client state
        for client in self.clients:
            client_state = {
                'id': client['id'],
                'x': client['x'],
                'y': client['y'],
                'base_station': client['base_station'],
                'slice': client['slice'],
                'active': client['active'],
                'app_type': client['app_type']
            }
            state['clients'].append(client_state)
        
        # Save state
        self.simulation_data.append(state)
    
    def save_to_json(self, output_path):
        """Save simulation data to a JSON file"""
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        with open(output_path, 'w') as f:
            json.dump(self.simulation_data, f, indent=2, cls=NumpyEncoder)
        
        print(f"Saved simulation data to {output_path}")
    
    def save_to_csv(self, output_dir):
        """Save simulation data to CSV files for easier analysis"""
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # Extract time series data for base stations
        bs_data = []
        for state in self.simulation_data:
            for bs in state['base_stations']:
                row = {
                    'step': state['step'],
                    'timestamp': state['timestamp'],
                    'base_station_id': bs['id'],
                    'total_clients': bs['total_clients']
                }
                
                # Add slice allocation and usage
                for slice_type in self.slice_types:
                    row[f'{slice_type}_allocation'] = bs['slice_allocation'][slice_type]
                    row[f'{slice_type}_usage'] = bs['slice_usage'][slice_type]
                
                bs_data.append(row)
        
        # Save base station data
        bs_df = pd.DataFrame(bs_data)
        bs_df.to_csv(os.path.join(output_dir, 'base_station_data.csv'), index=False)
        
        # Extract time series data for clients
        client_data = []
        for state in self.simulation_data:
            for client in state['clients']:
                row = {
                    'step': state['step'],
                    'timestamp': state['timestamp'],
                    'client_id': client['id'],
                    'base_station_id': client['base_station'],
                    'slice': client['slice'],
                    'active': int(client['active']),
                    'app_type': client['app_type'],
                    'x': client['x'],
                    'y': client['y']
                }
                client_data.append(row)
        
        # Save client data
        client_df = pd.DataFrame(client_data)
        client_df.to_csv(os.path.join(output_dir, 'client_data.csv'), index=False)
        
        print(f"Saved CSV data to {output_dir}")
    
    def generate_and_save(self, json_path, csv_dir=None):
        """Generate network data and save it"""
        self.generate_network()
        self.simulate_network_dynamics()
        self.save_to_json(json_path)
        
        if csv_dir:
            self.save_to_csv(csv_dir)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate realistic 5G network slicing data")
    parser.add_argument("--base-stations", type=int, default=5, help="Number of base stations")
    parser.add_argument("--clients", type=int, default=30, help="Number of clients")
    parser.add_argument("--steps", type=int, default=100, help="Number of simulation steps")
    parser.add_argument("--mobility", type=float, default=0.3, help="Mobility level (0-1)")
    parser.add_argument("--variance", type=float, default=0.4, help="Traffic variance (0-1)")
    parser.add_argument("--output", type=str, default="network_data.json", help="Output JSON file path")
    parser.add_argument("--csv-dir", type=str, default="network_data", help="Directory for CSV output")
    args = parser.parse_args()
    
    print("Generating 5G Network Slicing Data")
    print("---------------------------------")
    print(f"Base Stations: {args.base_stations}")
    print(f"Clients: {args.clients}")
    print(f"Steps: {args.steps}")
    print(f"Mobility Level: {args.mobility}")
    print(f"Traffic Variance: {args.variance}")
    print()
    
    # Generate data
    generator = NetworkDataGenerator(
        base_stations=args.base_stations,
        clients=args.clients,
        steps=args.steps,
        mobility_level=args.mobility,
        traffic_variance=args.variance
    )
    
    # Generate and save data
    generator.generate_and_save(args.output, args.csv_dir) 