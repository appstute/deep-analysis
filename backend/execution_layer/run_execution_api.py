#!/usr/bin/env python3

import sys
import os
from execution_api import ExecutionApi

def main():
    """Main entry point for the execution API"""
    try:
        print("Starting Data Analysis Execution API...")
        
        # Create and run the execution API
        api = ExecutionApi()
        api.run(host='0.0.0.0', port=5001)
        
    except Exception as e:
        print(f"Error starting Execution API: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main() 