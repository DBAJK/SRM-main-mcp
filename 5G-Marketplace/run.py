#!/usr/bin/env python3
"""
Run script for the 5G Marketplace

This script starts both the API server and the frontend server.
"""

import os
import sys
import logging
import subprocess
import argparse
import time
from concurrent.futures import ThreadPoolExecutor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="Run the 5G Marketplace")
    
    parser.add_argument(
        "--api-port",
        type=int,
        default=8001,
        help="Port to run the API server on (default: 8001)"
    )
    
    parser.add_argument(
        "--frontend-port",
        type=int,
        default=8080,
        help="Port to run the frontend server on (default: 8080)"
    )
    
    parser.add_argument(
        "--api-only",
        action="store_true",
        help="Only run the API server"
    )
    
    parser.add_argument(
        "--frontend-only",
        action="store_true",
        help="Only run the frontend server"
    )
    
    return parser.parse_args()

def run_api_server(port):
    """Run the API server"""
    logger.info(f"Starting API server on port {port}")
    
    # Ensure we're in the project root directory
    project_root = os.path.dirname(os.path.abspath(__file__))
    os.chdir(project_root)
    
    # Run the API server
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "src.api.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        str(port),
        "--reload"
    ]
    
    try:
        process = subprocess.Popen(cmd)
        logger.info(f"API server started with PID {process.pid}")
        return process
    except Exception as e:
        logger.error(f"Failed to start API server: {e}")
        return None

def run_frontend_server(port):
    """Run the frontend server"""
    logger.info(f"Starting frontend server on port {port}")
    
    # Ensure we're in the project root directory
    project_root = os.path.dirname(os.path.abspath(__file__))
    os.chdir(project_root)
    
    # Run the frontend server
    cmd = [
        sys.executable,
        "serve_frontend.py",
        "--port",
        str(port)
    ]
    
    try:
        process = subprocess.Popen(cmd)
        logger.info(f"Frontend server started with PID {process.pid}")
        return process
    except Exception as e:
        logger.error(f"Failed to start frontend server: {e}")
        return None

def main():
    """Main function"""
    args = parse_arguments()
    
    api_process = None
    frontend_process = None
    
    try:
        # Start the servers in separate threads
        with ThreadPoolExecutor(max_workers=2) as executor:
            if not args.frontend_only:
                api_future = executor.submit(run_api_server, args.api_port)
                api_process = api_future.result()
                
                if api_process is None:
                    logger.error("Failed to start API server")
                    return 1
                
                logger.info(f"API server is running at http://localhost:{args.api_port}")
            
            if not args.api_only:
                # Wait a bit for the API server to start
                time.sleep(2)
                
                frontend_future = executor.submit(run_frontend_server, args.frontend_port)
                frontend_process = frontend_future.result()
                
                if frontend_process is None:
                    logger.error("Failed to start frontend server")
                    return 1
                
                logger.info(f"Frontend server is running at http://localhost:{args.frontend_port}")
            
            # Print access information
            if not args.frontend_only and not args.api_only:
                logger.info("\n" + "=" * 50)
                logger.info("5G Marketplace is running!")
                logger.info(f"- Frontend: http://localhost:{args.frontend_port}")
                logger.info(f"- API: http://localhost:{args.api_port}/docs")
                logger.info("=" * 50 + "\n")
            
            # Keep the main thread alive
            while True:
                if api_process and api_process.poll() is not None:
                    logger.error("API server has stopped")
                    break
                
                if frontend_process and frontend_process.poll() is not None:
                    logger.error("Frontend server has stopped")
                    break
                
                time.sleep(1)
    
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        # Terminate the processes
        if api_process:
            api_process.terminate()
        
        if frontend_process:
            frontend_process.terminate()
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 