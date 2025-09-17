import sys
from logger import add_log, get_logs, clear_logs
from api_layer.api_server import ApiServer

def main():
    """Main entry point for the application"""
    try:
        # Initialize logger
        # add_log("Starting Data Analysis API Server...")
        
        # # Create API server
        api_server = ApiServer()
        
        # Run the API server - (Debug mode)
        api_server.run(host='0.0.0.0', port=5000, debug=True)
        
    except Exception as e:
        add_log(f"Error starting API server: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
