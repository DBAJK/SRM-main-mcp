#!/usr/bin/env python
"""
Test script for the 5G Network Slicing Simulator
This script verifies that all components are working correctly.
"""

import os
import sys
import traceback

def run_test():
    """Run tests to verify simulator functionality"""
    print("Testing 5G Network Slicing Simulator components...")
    
    failures = []
    
    # Test 1: Import modules
    print("\nTest 1: Import modules")
    try:
        from slicesim.Simulator import Simulator
        from slicesim.BaseStation import BaseStation
        from slicesim.Client import Client
        from slicesim.Coverage import Coverage
        from slicesim.Slice import Slice
        from slicesim.Stats import Stats
        from slicesim.utils import KDTree, distance, format_bps
        print("✓ All modules imported successfully")
    except Exception as e:
        failures.append(f"Module import failed: {str(e)}")
        traceback.print_exc()
        print("× Module import test failed")
    
    # Test 2: Create basic objects
    print("\nTest 2: Create basic objects")
    try:
        import simpy
        env = simpy.Environment()
        
        # Create coverage
        coverage = Coverage((100, 100), 200)
        print(f"✓ Created coverage: {coverage}")
        
        # Create base station
        bs = BaseStation(0, coverage)
        print(f"✓ Created base station: {bs}")
        
        # Create slice
        slice_obj = Slice("eMBB", 100e6, env)
        print(f"✓ Created slice: {slice_obj}")
        
        # Add slice to base station
        bs.add_slice(slice_obj)
        print(f"✓ Added slice to base station")
        
        # Create client
        client = Client(0, 150, 150, "eMBB", env)
        print(f"✓ Created client: {client}")
        
        # Connect client to base station
        client.connect_to_base_station(bs)
        print(f"✓ Connected client to base station")
        
        print("✓ Basic objects created successfully")
    except Exception as e:
        failures.append(f"Object creation failed: {str(e)}")
        traceback.print_exc()
        print("× Object creation test failed")
    
    # Test 3: Create simulator
    print("\nTest 3: Create simulator")
    try:
        from slicesim.Simulator import Simulator
        
        # Create simulator with minimal configuration
        sim = Simulator(base_stations=2, clients=5, simulation_time=10)
        print(f"✓ Created simulator with {len(sim.base_stations)} base stations and {len(sim.clients)} clients")
        
        print("✓ Simulator created successfully")
    except Exception as e:
        failures.append(f"Simulator creation failed: {str(e)}")
        traceback.print_exc()
        print("× Simulator creation test failed")
    
    # Print summary
    print("\n=== Test Summary ===")
    if failures:
        print(f"× {len(failures)} tests failed:")
        for i, failure in enumerate(failures):
            print(f"  {i+1}. {failure}")
    else:
        print("✓ All tests passed!")
        print("You can now run the simulator with: python run.py")

if __name__ == "__main__":
    run_test() 