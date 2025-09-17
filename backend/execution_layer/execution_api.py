from flask import Flask, request, jsonify
import asyncio
from flask_cors import CORS
import socketio  # SocketIO client to connect to API layer
import json
import time
import os
import sys
import threading
import traceback
import uuid
import shutil
import queue

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import analysis components
from execution_layer.agents.data_analysis_agent import DataAnalysisAgent
from typing import TypedDict, Dict, Any

class MetricsState(TypedDict):
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int
    successful_requests: int

class ProgressEvent:
    def __init__(self, job_id: str, stage: str, message: str, percentage: int, emoji: str = ""):
        self.job_id = job_id
        self.stage = stage
        self.message = message
        self.percentage = percentage
        self.emoji = emoji
        self.timestamp = time.time()
        self.iso_timestamp = time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime())

    def to_dict(self):
        return {
            'job_id': self.job_id,
            'stage': self.stage,
            'message': self.message,
            'percentage': self.percentage,
            'emoji': self.emoji,
            'timestamp': self.timestamp,
            'iso_timestamp': self.iso_timestamp
        }

class ExecutionApi:
    def __init__(self):
        self.app = Flask(__name__)
        CORS(self.app)
        
        # RESTORED: SocketIO client to connect to API layer for progress streaming
        # This creates a client connection (not server) to avoid conflicts
        self.sio_client = socketio.SimpleClient()
        self.api_layer_connected = False
                
        # Use session-level output directory (already unique per container via Docker mount)
        self.output_dir = os.path.join('execution_layer', 'output_data')
        os.makedirs(self.output_dir, exist_ok=True)
        # File-based run lock path (per container) - keep OUTSIDE output_dir so cleanup doesn't remove it
        self.run_lock_path = os.path.join('execution_layer', '.analysis_running.lock')
        
        # Progress tracking for jobs - restored streaming capability
        self.active_jobs = set()
        self.progress_lock = threading.Lock()
        
        # Register routes 
        self.register_routes()
    
    def connect_to_api_layer(self, api_host='host.docker.internal', api_port=5000):
        """Connect to API layer's SocketIO server for progress streaming"""
        try:
            if not self.api_layer_connected:
                api_url = f'http://{api_host}:{api_port}'
                print(f"[EXECUTION LAYER] 🔗 Connecting to API layer at {api_url}")
                self.sio_client.connect(api_url)
                self.api_layer_connected = True
                print(f"[EXECUTION LAYER] ✅ Connected to API layer SocketIO")
        except Exception as e:
            print(f"[EXECUTION LAYER] ❌ Failed to connect to API layer: {e}")
            self.api_layer_connected = False

    def _emit_progress(self, job_id: str, stage: str, message: str, emoji: str = ""):
        """Emit progress event for a job - RESTORED streaming through SocketIO client"""
        progress_event = ProgressEvent(job_id, stage, message, 0, emoji)  # Set percentage to 0 since we don't need it
        
        # Emit progress to API layer via SocketIO client
        try:
            if self.api_layer_connected:
                # Emit to API layer which will forward to frontend
                self.sio_client.emit('execution_progress', progress_event.to_dict())
                print(f"[EXECUTION LAYER] 📡 Progress streamed: {emoji} {stage}: {message}")
            else:
                # Try to reconnect if not connected
                self.connect_to_api_layer()
                if self.api_layer_connected:
                    self.sio_client.emit('execution_progress', progress_event.to_dict())
                    print(f"[EXECUTION LAYER] 📡 Progress streamed: {emoji} {stage}: {message}")
                else:
                    print(f"[EXECUTION LAYER] ⚠️  Progress (no connection): {emoji} {stage}: {message}")
        except Exception as e:
            print(f"[EXECUTION LAYER] ❌ Error emitting progress: {e}")
            print(f"[EXECUTION LAYER] 📝 Progress (fallback): {emoji} {stage}: {message}")
    
    # REMOVED: register_socketio_events() - no longer needed since we removed the SocketIO instance
    # All WebSocket communication now handled by main API layer
    
    def register_routes(self):
        """Register all API routes"""
        
        @self.app.route('/health')
        def health():
            return jsonify({
                'status': 'healthy', 
                'service': 'analysis-execution-api',
                'output_dir': self.output_dir
            })
        

        
        @self.app.route('/analyze_job', methods=['POST'])
        def analyze_job():
            """Handle job-based analysis with job-specific folders"""
            # Get analysis request from JSON body
            data = request.get_json()
            if not data or 'query' not in data or 'job_id' not in data:
                return jsonify({'error': 'Missing analysis query or job_id'}), 400
            
            job_id = data['job_id']
            
            # Create job-specific lock path
            job_lock_path = os.path.join('execution_layer', f'.analysis_running_{job_id}.lock')
            
            # File-based guard: if lock exists, reject as busy
            if os.path.exists(job_lock_path):
                return jsonify({'status': 'busy', 'error': f'Analysis already in progress for job {job_id}'}), 409
            
            try:
                # Run analysis for the specific job
                analysis_result = self.run_job_analysis(data, job_lock_path)
                
                # Return the result
                return jsonify(analysis_result)
                
            except Exception as e:
                error_msg = f"Job analysis failed: {str(e)}"
                print(error_msg)
                traceback.print_exc()
                return jsonify({
                    'status': 'error',
                    'error': f'Analysis failed: {str(e)}',
                    'error_type': 'analysis_failure',
                    'error_code': 'ANALYSIS_FAILED',
                    'job_id': data.get('job_id', 'unknown'),
                    'message': 'An unexpected error occurred during analysis execution.'
                }), 500
        
        # Keep legacy analyze endpoint for backward compatibility
        @self.app.route('/analyze', methods=['POST'])
        def analyze():
            # Get analysis request from JSON body
            data = request.get_json()
            if not data or 'query' not in data:
                return jsonify({'error': 'Missing analysis query'}), 400
            
            # File-based guard: if lock exists, reject as busy
            if os.path.exists(self.run_lock_path):
                return jsonify({'status': 'busy', 'error': 'Analysis already in progress'}), 409
            
            # Ensure output directory exists
            # os.makedirs(self.output_dir, exist_ok=True)
            
            try:
                # Run analysis in a separate thread
                analysis_result = self.run_analysis(data)
                
                # Return the result
                return jsonify(analysis_result)
                
            except Exception as e:
                error_msg = f"Analysis failed: {str(e)}"
                print(error_msg)
                traceback.print_exc()
                return jsonify({
                    'status': 'error',
                    'error': f'Legacy analysis failed: {str(e)}',
                    'error_type': 'legacy_analysis_failure',
                    'error_code': 'LEGACY_ANALYSIS_FAILED',
                    'message': 'An unexpected error occurred during legacy analysis execution.'
                }), 500
            
    
    def calculate_costs(self, metrics: MetricsState, model_name) -> Dict[str, Any]:
        """Calculate costs based on metrics and model pricing"""
        # Default pricing per 1K tokens
        model_pricing = {
            "gpt-4.1": {"input": 0.002, "output": 0.008},
            "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},  
            "gpt-4.1-mini": {"input": 0.0004, "output": 0.0016},
        }
        
        # Get pricing for model or use default
        pricing = model_pricing.get(model_name, {"input": 0.002, "output": 0.008})
        
        try:
            # Convert to cost per 1000 tokens
            prompt_cost = (metrics["prompt_tokens"] / 1000) * pricing["input"]
            completion_cost = (metrics["completion_tokens"] / 1000) * pricing["output"]
            total_cost = prompt_cost + completion_cost
            
            print(f"Calculated costs for {model_name}: prompt=${prompt_cost:.4f}, completion=${completion_cost:.4f}, total=${total_cost:.4f}")
            
            return {
                "prompt_cost": float(prompt_cost),
                "completion_cost": float(completion_cost),
                "total_cost": float(total_cost),
                "model": model_name,
                "prompt_tokens": metrics["prompt_tokens"],
                "completion_tokens": metrics["completion_tokens"],
                "total_tokens": metrics["total_tokens"]
            }
        except Exception as e:
            print(f"Error calculating costs: {str(e)}")
            return {
                "prompt_cost": 0.0,
                "completion_cost": 0.0,
                "total_cost": 0.0,
                "model": model_name,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0
            }

    def create_graph(self):
        """
        Build a graph with Data Analysis Agent as the main coordinator.
        Data Analysis Agent uses EDA Agent and Code Agent internally.
        """
        from langgraph.graph import Graph
        
        g = Graph()
        
        # Create main data analysis agent
        data_analysis_agent = DataAnalysisAgent(output_dir=self.output_dir)
        
        # Add node
        g.add_node("data_analysis_agent", data_analysis_agent)
        
        # Set entry and exit points
        g.set_entry_point("data_analysis_agent")
        g.set_finish_point("data_analysis_agent")
        
        return g.compile()

    def run_job_analysis(self, data, job_lock_path):
        """Run analysis for a specific job with JOB-SPECIFIC directories (FIXED VERSION)"""
        try:
            # Create file-based run lock to prevent re-entry
            try:
                with open(job_lock_path, 'x') as _f:
                    _f.write('running')
            except FileExistsError:
                return {
                    'status': 'busy',
                    'error': f'Analysis already in progress for job {data.get("job_id")}'
                }

            # Get job parameters
            job_id = data['job_id']
            user_query = data['query']
            model_name = data.get('model', 'gpt-4.1-mini')
            container_id = data.get('container_id', '')
            
            # CORRECTED: Container has session mount, create job subdirectories within session
            # Container mount: /app/execution_layer/output_data → host session directory
            
            # Get paths from job manager
            host_input_dir = data.get('input_dir', '')   # Host session input dir
            host_output_dir = data.get('output_dir', '')  # Host job output path (for reference)
            
            # Container paths: job directories WITHIN the session mount
            job_input_dir = os.path.join('execution_layer', 'input_data')  # Use session input (shared)
            job_output_dir = os.path.join('execution_layer', 'output_data', job_id)  # Job subdir in session mount
            
            print(f"🔧 [CONTAINER] Setting up job {job_id} directories:")
            print(f"📥 Container input dir: {job_input_dir} (session shared)")
            print(f"📤 Container output dir: {job_output_dir} (job-specific)")
            print(f"🏠 Host output will be at: {host_output_dir}")
            
            # Create job-specific output directory WITHIN the session mount
            # No need to create input dir - using shared session input
            os.makedirs(job_output_dir, exist_ok=True)
            
            print(f"✅ [CONTAINER] Starting job analysis {job_id} with JOB-SPECIFIC directories")
            print(f"🔍 Job input dir (container): {job_input_dir}")
            print(f"💾 Job output dir (container): {job_output_dir}")
            print(f"🗂️ Host output dir: {host_output_dir}")
            print(f"📝 Query: {user_query}")
            print(f"🤖 Model: {model_name}")
            
            # RESTORED: Connect to API layer for real-time progress streaming
            self.connect_to_api_layer()
            
            # VERIFICATION: Check job directory within session mount
            try:
                session_mount_path = os.path.join('execution_layer', 'output_data')
                if os.path.exists(session_mount_path):
                    existing_items = [d for d in os.listdir(session_mount_path) if os.path.isdir(os.path.join(session_mount_path, d))]
                    print(f"📂 [CONTAINER] Existing job directories in session mount: {existing_items}")
                    print(f"📊 [CONTAINER] Total job directories in this session: {len(existing_items)}")
                    
                    # Check if our job directory was created
                    if os.path.exists(job_output_dir):
                        print(f"✅ [CONTAINER] Job directory created successfully: {job_output_dir}")
                    else:
                        print(f"❌ [CONTAINER] ERROR: Job directory NOT created: {job_output_dir}")
                else:
                    print(f"❌ [CONTAINER] ERROR: Session mount directory doesn't exist: {session_mount_path}")
                    
            except Exception as e:
                print(f"❌ [CONTAINER] Error checking job directories: {str(e)}")
            
            # Track active job
            with self.progress_lock:
                self.active_jobs.add(job_id)
            
            # Initialize metrics state
            metrics: MetricsState = {
                "total_tokens": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "successful_requests": 0
            }
            
            # Initialize analysis state with JOB-SPECIFIC paths and progress callback  
            state = {
                "original_query": user_query,
                "query_analysis":{
                    "user_intent": "",
                    "sub_queries": [],
                    "plan": [],
                    "expected_output":[]
                    },
                "command": "",
                "eda_outputs": [],
                "image_paths": [],
                "eda_summary": "",
                "eda_vision_analysis": "",
                "hypothesis_findings": [],
                "hypothesis_summary":"",
                "patterns_found": [],
                "final_html_report": "",
                "narrator_frame_text": "",
                "narrator_file_analyses": [],
                "error": None,
                "history": [],
                "last_code": "",
                "last_output": "",
                "last_error": None,
                "metrics": metrics,  
                "model_name": model_name,
                "output_dir": job_output_dir,  # ✅ FIXED: Use JOB-SPECIFIC output dir
                "input_dir": job_input_dir,    # ✅ FIXED: Use JOB-SPECIFIC input dir
                "job_id": job_id,
                "container_id": container_id,
                "user_email": data.get('user_email'),
                "user_token_info": data.get('user_token_info'),
                "progress_callback": lambda stage, message, emoji="": self._emit_progress(job_id, stage, message, emoji)
            }

            # Create data analysis agent with JOB-SPECIFIC output directory  
            data_analysis_agent = DataAnalysisAgent(output_dir=job_output_dir)
            
            from langgraph.graph import Graph
            g = Graph()
            g.add_node("data_analysis_agent", data_analysis_agent)
            g.set_entry_point("data_analysis_agent")
            g.set_finish_point("data_analysis_agent")
            compiled = g.compile()
            
            print("Running job analysis")
            
            # Run the analysis
            state = asyncio.run(compiled.ainvoke(state))
            
            # Calculate final costs
            costs = self.calculate_costs(state["metrics"], state["model_name"])
            print(f"Job {job_id} analysis completed with costs: {json.dumps(costs)}")
            
            # Path to the report file in JOB-SPECIFIC output directory
            report_file = os.path.join(job_output_dir, 'analysis_report.html')
            
            try:
                if os.path.exists(report_file):
                    with open(report_file, 'r', encoding='utf-8') as f:
                        report_str = f.read()
                else:
                    report_str = state.get("final_html_report", "<p>No report generated</p>")
                    # Save report to file for future reference
                    if report_str and report_str != "<p>No report generated</p>":
                        with open(report_file, 'w', encoding='utf-8') as f:
                            f.write(report_str)
                        print(f"HTML report saved to: {report_file}")
                    else:
                        print("Warning: No final_html_report found in state")
                        print(f"State keys: {list(state.keys())}")
            except Exception as e:
                print(f"Error reading/writing report file: {str(e)}")
                report_str = f"<p>Error with report: {str(e)}</p>"
            
            print(f"✅ [CONTAINER] Job {job_id} analysis completed successfully")
            
            # FINAL VERIFICATION: Check job output files within session mount
            try:
                if os.path.exists(job_output_dir):
                    output_files = os.listdir(job_output_dir)
                    print(f"📄 [CONTAINER] Files created in job directory {job_id}:")
                    for file in output_files:
                        file_path = os.path.join(job_output_dir, file)
                        file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
                        print(f"   - {file} ({file_size} bytes)")
                    print(f"📊 [CONTAINER] Total files created for this job: {len(output_files)}")
                    
                    # Also show all job directories in this session
                    session_mount = os.path.join('execution_layer', 'output_data')
                    all_jobs = [d for d in os.listdir(session_mount) if os.path.isdir(os.path.join(session_mount, d))]
                    print(f"🗂️ [CONTAINER] All job directories in this session: {all_jobs}")
                else:
                    print(f"❌ [CONTAINER] ERROR: Job output directory doesn't exist at completion: {job_output_dir}")
                    
            except Exception as e:
                print(f"❌ [CONTAINER] Error checking final output files: {str(e)}")
            
            # Prepare response with job-specific information
            response = {
                'status': 'success',
                'job_id': job_id,
                # 'report': report_str,
                'costs': costs,
                'metrics': state["metrics"],
                'output_dir': job_output_dir,  # Container job directory
                'host_output_dir': host_output_dir,  # Host job directory path
                'container_output_dir': job_output_dir,  # Container path for debugging
                'session_mount': os.path.join('execution_layer', 'output_data'),  # Session mount point
                # Include token exhaustion indicators for job status determination
                'analysis_completed_early': state.get('analysis_completed_early', False),
                'completion_reason': state.get('completion_reason', ''),
                'final_message': state.get('final_message', '')
            }
            return response
        except Exception as e:
            # Emit error progress
            self._emit_progress(job_id, "Analysis Failed", f"Something went wrong", "❌")
            print(f"Error in job {data.get('job_id', 'unknown')} analysis: {str(e)}")
            traceback.print_exc()
            return {
                'status': 'error',
                'error': f'Job execution failed: {str(e)}',
                'error_type': 'job_execution_failure',
                'error_code': 'JOB_EXECUTION_FAILED',
                'job_id': data.get('job_id'),
                'user_email': data.get('user_email', ''),
                'message': 'An unexpected error occurred during job execution.',
                'metrics': {}
            }
        finally:
            # Remove job-specific run lock
            try:
                if os.path.exists(job_lock_path):
                    os.remove(job_lock_path)
            except Exception:
                pass
            
            # Remove job from active jobs
            with self.progress_lock:
                self.active_jobs.discard(job_id)
    
    def run_analysis(self, data):
        """Run analysis for the given data"""
        try:
            # Create file-based run lock to prevent re-entry
            try:
                with open(self.run_lock_path, 'x') as _f:
                    _f.write('running')
            except FileExistsError:
                return {
                    'status': 'busy',
                    'error': 'Analysis already in progress'
                }
            # FIXED: No longer clean up directories - preserve job outputs!
            # Just ensure output directory exists
            try:
                os.makedirs(self.output_dir, exist_ok=True)
                print(f"✅ FIXED: /analyze endpoint no longer deletes job directories")
                print(f"📁 Output directory: {self.output_dir}")
            except Exception as e:
                print(f"Error creating output directory {self.output_dir}: {e}")
            

            # Get analysis parameters
            user_query = data['query']
            model_name = data.get('model', 'gpt-4.1-mini')
            container_id = data.get('container_id', '')
            user_email = data.get('user_email', '')
            user_token_info = data.get('user_token_info', {})

            print(f"Starting analysis for query: {user_query} using model: {model_name}")
            print(f"📊 [TOKEN MANAGEMENT] User: {user_email}, Tokens: {user_token_info.get('used_token', 0)}/{user_token_info.get('issued_token', 0)} (remaining: {user_token_info.get('remaining_token', 0)})")
            
            # Check if user has enough tokens to proceed
            if user_token_info and user_token_info.get('remaining_token', 0) <= 0:
                return jsonify({
                    "status": "error",
                    "error": "🚫 INSUFFICIENT TOKENS: User has no tokens remaining. Contact admin for more tokens.",
                    "error_type": "insufficient_tokens",
                    "error_code": "TOKEN_INSUFFICIENT",
                    "user_email": user_email,
                    "token_info": {
                        "used_token": user_token_info.get('used_token', 0),
                        "issued_token": user_token_info.get('issued_token', 0),
                        "remaining_token": user_token_info.get('remaining_token', 0)
                    },
                    "message": "Please contact administrator to purchase additional tokens."
                }), 402  # 402 Payment Required - more appropriate for token limits
            
            # Initialize metrics state
            metrics: MetricsState = {
                "total_tokens": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "successful_requests": 0
            }
            
            # Initialize analysis state
            state = {
                "original_query": user_query,
                "query_analysis":{
                    "user_intent": "",
                    "sub_queries": [],
                    "plan": [],
                    "expected_output":[]
                    },
                "command": "",
                "eda_outputs": [],
                "image_paths": [],
                "eda_summary": "",
                "eda_vision_analysis": "",
                "hypothesis_findings": [],
                "hypothesis_summary":"",
                "patterns_found": [],
                "final_html_report": "",
                "narrator_frame_text": "",
                "narrator_file_analyses": [],
                "error": None,
                "history": [],
                "last_code": "",
                "last_output": "",
                "last_error": None,
                "metrics": metrics,  
                "model_name": "gpt-4.1-mini",
                "user_email": user_email,
                "user_token_info": user_token_info,  # Pass token info for internal tracking
                "output_dir": self.output_dir,
                "container_id": container_id
            }
 
            # Import TokenLimitExceededException for handling token limits
            from agents.token_manager import TokenLimitExceededException
            
            try:
                # Run analysis
                print("Initializing analysis")
                compiled = self.create_graph()
                print("Running analysis")
                state = asyncio.run(compiled.ainvoke(state))
                
            except TokenLimitExceededException as e:
                # Token limit exceeded - immediately stop and return error
                print(f"🚫 [EXECUTION_API] Token limit exceeded: {str(e)}")
                return jsonify({
                    "status": "error",
                    "error": f"🚫 ANALYSIS STOPPED: {str(e)}",
                    "error_type": "token_limit_exceeded",
                    "error_code": "TOKEN_LIMIT_EXCEEDED",
                    "user_email": user_email,
                    "job_id": data.get('job_id', 'unknown'),
                    "metrics": state.get("metrics", {}),
                    "token_info": user_token_info,
                    "message": "Token limit reached during analysis. Contact administrator for more tokens."
                }), 402  # 402 Payment Required - semantically correct for token limits
            
            # Calculate final costs
            costs = self.calculate_costs(state["metrics"], state["model_name"])
            print(f"Analysis completed with costs: {json.dumps(costs)}")
            
            # Path to the report file
            report_file = os.path.join(self.output_dir, 'analysis_report.html')
            
            try:
                if os.path.exists(report_file):
                    with open(report_file, 'r', encoding='utf-8') as f:
                        report_str = f.read()
                else:
                    report_str = state.get("final_html_report", "<p>No report generated</p>")
                    # Save report to file for future reference
                    with open(report_file, 'w', encoding='utf-8') as f:
                        f.write(report_str)
            except Exception as e:
                print(f"Error reading/writing report file: {str(e)}")
                report_str = f"<p>Error with report: {str(e)}</p>"
            
            print("Analysis completed successfully")
            
            # Prepare response
            response = {
                'status': 'success',
                'report': report_str,
                'costs': costs,
                'metrics': state["metrics"],
                'output_dir': self.output_dir,
                # Include token exhaustion indicators for job status determination
                'analysis_completed_early': state.get('analysis_completed_early', False),
                'completion_reason': state.get('completion_reason', ''),
                'final_message': state.get('final_message', '')
            }
            return response
        except Exception as e:
            print(f"Error in analysis: {str(e)}")
            traceback.print_exc()
            return {
                'status': 'error',
                'error': f'Legacy analysis execution failed: {str(e)}',
                'error_type': 'legacy_execution_failure',
                'error_code': 'LEGACY_EXECUTION_FAILED',
                'user_email': user_email,
                'message': 'An unexpected error occurred during legacy analysis execution.',
                'metrics': {}
            }
        finally:
            # Remove run lock
            try:
                if os.path.exists(self.run_lock_path):
                    os.remove(self.run_lock_path)
            except Exception:
                pass
    
    def run(self, host='0.0.0.0', port=5001, debug=True):
        """Run the execution API server (Flask only, no WebSocket)"""
        print(f"[EXECUTION LAYER] Starting Flask server on {host}:{port}")
        self.app.run(debug=debug, host=host, port=port)

def create_app():
    """Create and configure the Flask app"""
    api = ExecutionApi()
    return api.app

if __name__ == '__main__':
    api = ExecutionApi()
    api.run() 