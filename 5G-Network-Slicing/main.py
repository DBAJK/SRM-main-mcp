#!/usr/bin/env python3
"""
5G Network Slicing - Main Entry Point

This script provides a command-line interface to run different components
of the 5G network slicing system.
"""

import os
import sys
import argparse
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def setup_paths():
    """Add project root to Python path."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if script_dir not in sys.path:
        sys.path.append(script_dir)

def main():
    """Main entry point."""
    # Setup paths
    setup_paths()
    
    # Import local modules (after path setup)
    from slicesim.config import Config, load_config
    from slicesim.simulation import run_simulation
    from slicesim.orchestrator import SliceOrchestrator
    from slicesim.ai.slice_manager import EnhancedSliceManager
    
    # Parse arguments
    parser = argparse.ArgumentParser(description='5G Network Slicing System')
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # Simulation command
    sim_parser = subparsers.add_parser('simulate', help='Run simulation')
    sim_parser.add_argument('--config', type=str, help='Path to configuration file')
    sim_parser.add_argument('--model', type=str, help='Path to trained model')
    sim_parser.add_argument('--steps', type=int, default=100, help='Number of simulation steps')
    sim_parser.add_argument('--output', type=str, help='Path to save results')
    sim_parser.add_argument('--emergency', type=str, help='Comma-separated list of emergency steps')
    
    # Orchestrator command
    orch_parser = subparsers.add_parser('orchestrate', help='Run orchestrator')
    orch_parser.add_argument('--model', type=str, required=True, help='Path to trained model')
    orch_parser.add_argument('--config', type=str, help='Path to configuration file')
    orch_parser.add_argument('--duration', type=int, default=60, help='Duration in seconds')
    orch_parser.add_argument('--emergency', action='store_true', help='Simulate emergency')
    
    # Demo command
    demo_parser = subparsers.add_parser('demo', help='Run interactive demo')
    demo_parser.add_argument('--model', type=str, required=True, help='Path to trained model')
    demo_parser.add_argument('--config', type=str, help='Path to configuration file')
    
    # Parse arguments
    args = parser.parse_args()
    
    # Execute command
    if args.command == 'simulate':
        # Parse emergency steps
        emergency_steps = None
        if args.emergency:
            try:
                emergency_steps = [int(s) for s in args.emergency.split(',')]
            except:
                logger.warning(f"Invalid emergency steps: {args.emergency}, using random events")
        
        # Run simulation
        run_simulation(
            config_path=args.config,
            model_path=args.model,
            steps=args.steps,
            output_path=args.output,
            emergency_steps=emergency_steps
        )
    
    elif args.command == 'orchestrate':
        # Load configuration
        if args.config:
            load_config(args.config)
        
        # Create orchestrator
        orchestrator = SliceOrchestrator(model_path=args.model)
        
        # Start orchestrator
        orchestrator.start()
        
        try:
            # Set emergency mode if requested
            if args.emergency:
                logger.info("Setting emergency mode")
                orchestrator.set_emergency_mode(True)
            
            # Run for specified duration
            import time
            logger.info(f"Running orchestrator for {args.duration} seconds")
            
            start_time = time.time()
            while time.time() - start_time < args.duration:
                # Get current allocation
                allocation = orchestrator.get_current_allocation()
                utilization = orchestrator.get_current_utilization()
                
                # Print status
                logger.info(f"Allocation: eMBB={allocation[0]:.2f}, URLLC={allocation[1]:.2f}, mMTC={allocation[2]:.2f}")
                logger.info(f"Utilization: eMBB={utilization[0]:.2f}, URLLC={utilization[1]:.2f}, mMTC={utilization[2]:.2f}")
                
                # Generate visualization
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                viz_path = f"results/orchestration_{timestamp}.png"
                orchestrator.visualize_allocation(viz_path)
                
                # Sleep
                time.sleep(5)
        
        finally:
            # Stop orchestrator
            orchestrator.stop()
    
    elif args.command == 'demo':
        # Import demo module
        try:
            from slicesim.demo import run_interactive_demo
            
            # Run demo
            run_interactive_demo(args.model, args.config)
        except ImportError:
            logger.error("Demo module not found. Please implement the demo module.")
            return 1
    
    else:
        parser.print_help()
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 