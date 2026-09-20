#!/usr/bin/env python3
"""
Simple HTTP Server for 5G Marketplace Frontend

This script serves the frontend files for the 5G Marketplace platform.
"""

import os
import sys
import logging
import argparse
from http.server import HTTPServer, SimpleHTTPRequestHandler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class CORSRequestHandler(SimpleHTTPRequestHandler):
    """Custom request handler with CORS support"""
    
    def end_headers(self):
        """Add CORS headers"""
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        return super().end_headers()
    
    def log_message(self, format, *args):
        """Log to our logger instead of stderr"""
        logger.info("%s - %s", self.address_string(), format % args)

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="Run the 5G Marketplace frontend server")
    
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port to run the frontend server on (default: 8080)"
    )
    
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host to bind the frontend server to (default: 0.0.0.0)"
    )
    
    return parser.parse_args()

def main():
    """Main function"""
    args = parse_arguments()
    
    # Change to frontend directory
    frontend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")
    if os.path.exists(frontend_dir):
        os.chdir(frontend_dir)
    else:
        logger.error(f"Frontend directory not found: {frontend_dir}")
        logger.info("Creating frontend directory")
        os.makedirs(frontend_dir, exist_ok=True)
        os.chdir(frontend_dir)
    
    # Start server
    server_address = (args.host, args.port)
    httpd = HTTPServer(server_address, CORSRequestHandler)
    
    logger.info(f"Starting frontend server at http://{args.host}:{args.port}")
    logger.info("Press Ctrl+C to stop the server")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Server stopped")
    finally:
        httpd.server_close()

if __name__ == "__main__":
    main() 