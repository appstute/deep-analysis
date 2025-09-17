import uuid
import time
import threading
import json
import os
import requests
import docker
from typing import Dict, Any, Optional, Tuple
from enum import Enum
from datetime import datetime
from logger import add_log, add_job_log
from .firebase_data_models import JobDocument, get_data_manager

class JobStatus(Enum):
    PENDING = "pending"
    RUNNING = "running" 
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class JobManager:
    """Manages asynchronous analysis jobs"""
    
    def __init__(self):
        self.jobs: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.Lock()
        self.jobs_file = "jobs.json"
        
        # Base directories for job data
        self.base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        self.input_base_dir = os.path.join(self.base_dir, 'execution_layer', 'input_data')
        self.output_base_dir = os.path.join(self.base_dir, 'execution_layer', 'output_data')
        
        # Firebase data manager
        self.data_manager = get_data_manager()
        
        # Docker client for container logs
        try:
            self.docker_client = docker.from_env()
        except Exception as e:
            print(f"⚠️ [DOCKER] Failed to initialize Docker client: {str(e)}")
            self.docker_client = None
    
    def save_container_logs(self, job_id: str, container_id: str) -> str:
        """
        Save Docker container logs to job output directory (like analysis_report.html)
        
        Args:
            job_id: Job identifier  
            container_id: Docker container ID or name
            
        Returns:
            str: Path to the saved log file
        """
        try:
            if not self.docker_client:
                print(f"❌ [DOCKER LOGS] Docker client not available")
                return None
                
            # Get job info to find output directory
            job_info = self.get_job(job_id)
            if not job_info:
                print(f"❌ [DOCKER LOGS] Job {job_id} not found")
                return None
                
            output_dir = job_info.get('output_dir')
            if not output_dir:
                print(f"❌ [DOCKER LOGS] No output directory found for job {job_id}")
                return None
            
            # Save logs in the same directory as analysis_report.html
            log_file = os.path.join(output_dir, 'container_logs.txt')
            
            # Get container and save logs
            container = self.docker_client.containers.get(container_id)
            
            with open(log_file, "w", encoding="utf-8") as f:
                # Get all logs (stdout and stderr) with timestamps
                logs = container.logs(stdout=True, stderr=True, timestamps=True)
                f.write(logs.decode("utf-8"))
                
            print(f"📄 [DOCKER LOGS] Saved container logs to: {log_file}")
            return log_file
            
        except Exception as e:
            print(f"❌ [DOCKER LOGS] Failed to save container logs: {str(e)}")
            return None
        
    def _load_jobs_from_file(self):
        """Load existing jobs from JSON file"""
        if os.path.exists(self.jobs_file):
            try:
                with open(self.jobs_file, 'r') as f:
                    stored_jobs = json.load(f)
                
                # Restore jobs
                for job_id, job_data in stored_jobs.items():
                    self.jobs[job_id] = job_data
                    add_log(f"Restored job {job_id} from file")
                        
            except Exception as e:
                add_log(f"Error loading jobs from file: {str(e)}")
                self.jobs = {}
    
    def _save_jobs_to_file(self):
        """Save current jobs to JSON file"""
        try:
            # Convert jobs to JSON-serializable format
            jobs_to_save = {}
            for job_id, job_info in self.jobs.items():
                jobs_to_save[job_id] = {
                    'job_id': job_info['job_id'],
                    'session_id': job_info['session_id'],
                    'status': job_info['status'].value if isinstance(job_info['status'], JobStatus) else job_info['status'],
                    'query': job_info['query'],
                    'model': job_info['model'],
                    'created_at': job_info['created_at'],
                    'started_at': job_info.get('started_at'),
                    'completed_at': job_info.get('completed_at'),
                    'error': job_info.get('error'),
                    'container_port': job_info.get('container_port'),
                    'output_dir': job_info.get('output_dir'),
                    'input_dir': job_info.get('input_dir'),
                    'user_info': job_info.get('user_info', {})
                }
            
            with open(self.jobs_file, 'w') as f:
                json.dump(jobs_to_save, f, indent=2)
                
        except Exception as e:
            add_log(f"Error saving jobs to file: {str(e)}")
    
    def create_job(self, session_id: str, query: str, model: str = "gpt-4.1-mini", 
                   session_info: Optional[Dict[str, Any]] = None,
                   user_info: Optional[Dict[str, Any]] = None) -> Tuple[str, Dict[str, Any]]:
        """Create a new analysis job with JOB prefix"""
        # Generate job ID with JOB prefix for better identification  
        job_id = f"JOB_{str(uuid.uuid4())}"
        
        with self.lock:
            try:
                # add_job_log(job_id, f"Creating new job: {job_id} for session: {session_id}")
                
                # CORRECTED: Keep original session-based design for HOST
                # Input: Session-based (shared across jobs in session)
                # Output: Session-based on HOST, job-based INSIDE container
                
                session_input_dir = os.path.join(self.input_base_dir, session_id)
                session_output_dir = os.path.join(self.output_base_dir, session_id)
                
                print(f"🔧 [JOB MANAGER] Setting up job {job_id} (session: {session_id})")
                print(f"📥 Session input dir (host): {session_input_dir}")
                print(f"📤 Session output dir (host): {session_output_dir}")
                print(f"💡 Container will create job subdir: /app/execution_layer/output_data/{job_id}/")
                
                # Ensure session input directory exists (for shared session data)
                if session_id:
                    os.makedirs(session_input_dir, exist_ok=True)
                    print(f"✅ Session input directory ensured: {session_input_dir}")
                
                # Ensure session output directory exists (container mount point)
                os.makedirs(session_output_dir, exist_ok=True)
                print(f"✅ Session output directory ensured: {session_output_dir}")
                
                # Job-specific paths for reference (used by container)
                job_input_dir = session_input_dir  # Jobs share session input
                job_output_dir = os.path.join(session_output_dir, job_id)  # Job subdir in session output
                
                # Store job information
                job_info = {
                    'job_id': job_id,
                    'session_id': session_id,
                    'status': JobStatus.PENDING,
                    'query': query,
                    'model': model,
                    'created_at': time.time(),
                    'started_at': None,
                    'completed_at': None,
                    'error': None,
                    'container_port': session_info.get('container_port') if session_info else None,
                    'output_dir': job_output_dir,
                    'input_dir': job_input_dir,
                    'user_info': user_info or {}  # Store user information for job ownership
                }
                
                self.jobs[job_id] = job_info
                self._save_jobs_to_file()
                
                # add_job_log(job_id, f"Job {job_id} created successfully")
                return job_id, job_info
                
            except Exception as e:
                # add_job_log(job_id, f"Error creating job {job_id}: {str(e)}")
                raise
    
    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job information by ID"""
        with self.lock:
            job_info = self.jobs.get(job_id)
            if job_info:
                # Ensure status is properly typed
                if isinstance(job_info['status'], str):
                    job_info['status'] = JobStatus(job_info['status'])
                return job_info.copy()
            return None
    
    def update_job_status(self, job_id: str, status: JobStatus, 
                         error: Optional[str] = None) -> bool:
        """Update job status"""
        with self.lock:
            job_info = self.jobs.get(job_id)
            if not job_info:
                return False
            
            old_status = job_info['status']
            job_info['status'] = status
            
            if status == JobStatus.RUNNING and job_info.get('started_at') is None:
                job_info['started_at'] = time.time()
            elif status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
                job_info['completed_at'] = time.time()
                
            if error:
                job_info['error'] = error
            
            self._save_jobs_to_file()
            # add_job_log(job_id, f"Job {job_id} status updated: {old_status} -> {status}")
            return True
    
    def start_job_execution(self, job_id: str, session_manager) -> bool:
        """Start asynchronous job execution"""
        job_info = self.get_job(job_id)
        if not job_info:
            return False
        
        def execute_job():
            try:
                # add_job_log(job_id, f"Starting job execution: {job_id}")
                self.update_job_status(job_id, JobStatus.RUNNING)
                
                # Get session info for container communication
                session_id = job_info['session_id']
                session_info = session_manager.get_session_container(session_id)
                
                if not session_info:
                    self.update_job_status(job_id, JobStatus.FAILED, 
                                         f"Session {session_id} not found or inactive")
                    return
                
                container_port = session_info.get('container_port')
                if not container_port:
                    self.update_job_status(job_id, JobStatus.FAILED,
                                         f"Cannot determine container port for session: {session_id}")
                    return
                
                # Forward job to execution layer
                container_url = f"http://localhost:{container_port}/analyze_job"
                
                # Create requests session with timeout
                session_req = requests.Session()
                
                try:
                    # Extract user email for token management
                    user_info = job_info.get('user_info', {})
                    user_email = user_info.get('email', '')
                    
                    # Get current user token info ONCE at the start
                    user_token_info = {}
                    if user_email and self.data_manager:
                        user = self.data_manager.get_user(user_email)
                        if user:
                            user_token_info = {
                                'used_token': user.used_token,
                                'issued_token': user.issued_token,
                                'remaining_token': user.issued_token - user.used_token
                            }
                            print(f"📊 [JOB_MANAGER] User tokens: {user.used_token}/{user.issued_token} (remaining: {user_token_info['remaining_token']})")
                        else:
                            print(f"⚠️ [JOB_MANAGER] User '{user_email}' not found in database")
                    
                    # Send job execution request with user token info for internal tracking
                    container_response = session_req.post(
                        container_url,
                        json={
                            'job_id': job_id,
                            'query': job_info['query'],
                            'model': job_info['model'],
                            'session_id': session_id,
                            'input_dir': job_info['input_dir'],
                            'output_dir': job_info['output_dir'],
                            'user_email': user_email,
                            'user_token_info': user_token_info  # Pass current token info for internal tracking
                        },
                        timeout=3600  # 1 hour timeout for analysis
                    )
                    
                    if container_response.status_code == 200:
                        result = container_response.json()
                        print("Job completed successfully")
                        print(f"Result: {result}")
                        
                        # Determine job status to decide on token update
                        execution_status = result.get('status', 'success')
                        has_error = result.get('error') is not None
                        analysis_completed_early = result.get('analysis_completed_early', False)
                        completion_reason = result.get('completion_reason', '')
                        token_limit_reached = completion_reason == 'token_limit_reached'
                        
                        # Job is successful if no errors and no token limit reached
                        job_is_successful = not (execution_status == 'error' or has_error or token_limit_reached)
                        
                        # Update user tokens ONCE at the end if tokens were consumed 
                        # (regardless of success/failure, as long as tokens were actually used)
                        if user_email and user_token_info:
                            metrics = result.get('metrics', {})
                            total_tokens_used = metrics.get('total_tokens', 0)
                            
                            if total_tokens_used > 0:
                                print(f"📊 [TOKEN UPDATE] Job used {total_tokens_used:,} tokens for user {user_email}")
                                
                                # Check if user would exceed limit
                                current_used = user_token_info.get('used_token', 0)
                                issued_tokens = user_token_info.get('issued_token', 0)
                                new_total = current_used + total_tokens_used
                                
                                if new_total > issued_tokens:
                                    print(f"⚠️ [TOKEN WARNING] Job would exceed token limit! {new_total} > {issued_tokens}")
                                    # Note: Job already completed, but warn about limit
                                
                                # Update user's token count in database
                                try:
                                    update_success = self.data_manager.update_user_tokens(user_email, total_tokens_used)
                                    if update_success:
                                        print(f"✅ [TOKEN UPDATE] Updated user {user_email}: +{total_tokens_used:,} tokens (Total: {new_total:,}/{issued_tokens:,})")
                                    else:
                                        print(f"❌ [TOKEN UPDATE] Failed to update tokens for user {user_email}")
                                except Exception as token_error:
                                    print(f"❌ [TOKEN UPDATE] Error updating tokens: {str(token_error)}")
                            else:
                                print(f"📊 [TOKEN UPDATE] No tokens consumed for job {job_id}")
                        
                        # Save Docker container logs to output directory
                        try:
                            container_id = session_info.get('container_id')
                            if container_id:
                                self.save_container_logs(job_id, container_id)
                            else:
                                print(f"⚠️ [DOCKER LOGS] No container ID found for session {session_id}")
                        except Exception as log_error:
                            print(f"❌ [DOCKER LOGS] Error saving container logs: {str(log_error)}")
                        
                        # Save job output to Firestore
                        try:
                            firestore_success = self.save_job_to_firestore(job_id, result)
                            if firestore_success:
                                print(f"📊 [PROGRESS] 🔥 Analysis Complete - Results saved to database")
                            else:
                                print(f"⚠️ [PROGRESS] 🔥 Analysis Complete - Database save failed but analysis succeeded")
                        except Exception as firestore_error:
                            print(f"❌ [FIRESTORE ERROR] Failed to save to database: {str(firestore_error)}")
                            add_log(f"Firestore save error for job {job_id}: {str(firestore_error)}")
                        
                        # add_job_log(job_id, f"Job {job_id} completed successfully")
                        self.update_job_status(job_id, JobStatus.COMPLETED)
                    elif container_response.status_code == 402:
                        # Token limit exceeded - handle gracefully
                        
                        # Save Docker container logs for failed job
                        try:
                            container_id = session_info.get('container_id')
                            if container_id:
                                self.save_container_logs(job_id, container_id)
                        except Exception as log_error:
                            print(f"❌ [DOCKER LOGS] Error saving container logs: {str(log_error)}")
                        
                        try:
                            error_data = container_response.json()
                            error_msg = error_data.get('error', 'Token limit exceeded')
                            print(f"🚫 [TOKEN LIMIT] Job {job_id} stopped: {error_msg}")
                            
                            # Save failed job to Firestore 
                            try:
                                failed_result = {
                                    'status': 'error',
                                    'error': error_msg,
                                    'metrics': error_data.get('metrics', {}),
                                    'costs': {'total_cost': 0, 'total_tokens': 0}
                                }
                                firestore_success = self.save_job_to_firestore(job_id, failed_result)
                                if firestore_success:
                                    print(f"📊 [FAILED JOB] Failed job {job_id} saved to Firestore")
                            except Exception as firestore_error:
                                print(f"❌ [FIRESTORE ERROR] Failed to save failed job to database: {str(firestore_error)}")
                            
                            self.update_job_status(job_id, JobStatus.FAILED, f"TOKEN_LIMIT_EXCEEDED: {error_msg}")
                        except:
                            error_msg = f"Token limit exceeded (HTTP 402): {container_response.text}"
                            print(f"🚫 [TOKEN LIMIT] Job {job_id} failed: {error_msg}")
                            
                            # Save failed job to Firestore 
                            try:
                                failed_result = {
                                    'status': 'error',
                                    'error': error_msg,
                                    'metrics': {},
                                    'costs': {'total_cost': 0, 'total_tokens': 0}
                                }
                                self.save_job_to_firestore(job_id, failed_result)
                            except Exception as firestore_error:
                                print(f"❌ [FIRESTORE ERROR] Failed to save failed job to database: {str(firestore_error)}")
                            
                            self.update_job_status(job_id, JobStatus.FAILED, error_msg)
                    else:
                        # Other HTTP errors (400, 500, etc.)
                        
                        # Save Docker container logs for failed job
                        try:
                            container_id = session_info.get('container_id')
                            if container_id:
                                self.save_container_logs(job_id, container_id)
                        except Exception as log_error:
                            print(f"❌ [DOCKER LOGS] Error saving container logs: {str(log_error)}")
                        
                        try:
                            error_data = container_response.json()
                            error_msg = f"Analysis failed: {error_data.get('error', container_response.text)}"
                            error_type = error_data.get('error_type', 'unknown_error')
                            print(f"❌ [JOB FAILED] {error_type}: {error_msg}")
                            
                            # Save failed job to Firestore 
                            try:
                                failed_result = {
                                    'status': 'error',
                                    'error': error_msg,
                                    'metrics': error_data.get('metrics', {}),
                                    'costs': {'total_cost': 0, 'total_tokens': 0}
                                }
                                firestore_success = self.save_job_to_firestore(job_id, failed_result)
                                if firestore_success:
                                    print(f"📊 [FAILED JOB] Failed job {job_id} saved to Firestore")
                            except Exception as firestore_error:
                                print(f"❌ [FIRESTORE ERROR] Failed to save failed job to database: {str(firestore_error)}")
                                
                        except:
                            error_msg = f"Container API returned error: {container_response.status_code} - {container_response.text}"
                            
                            # Save failed job to Firestore 
                            try:
                                failed_result = {
                                    'status': 'error',
                                    'error': error_msg,
                                    'metrics': {},
                                    'costs': {'total_cost': 0, 'total_tokens': 0}
                                }
                                self.save_job_to_firestore(job_id, failed_result)
                            except Exception as firestore_error:
                                print(f"❌ [FIRESTORE ERROR] Failed to save failed job to database: {str(firestore_error)}")
                        
                        # add_job_log(job_id, f"Job {job_id} failed: {error_msg}")
                        self.update_job_status(job_id, JobStatus.FAILED, error_msg)
                        
                except requests.RequestException as e:
                    error_msg = f"Error communicating with container API: {str(e)}"
                    
                    # Save Docker container logs for failed job (if possible)
                    try:
                        container_id = session_info.get('container_id')
                        if container_id:
                            self.save_container_logs(job_id, container_id)
                    except Exception as log_error:
                        print(f"❌ [DOCKER LOGS] Error saving container logs: {str(log_error)}")
                    
                    # Save failed job to Firestore 
                    try:
                        failed_result = {
                            'status': 'error',
                            'error': error_msg,
                            'metrics': {},
                            'costs': {'total_cost': 0, 'total_tokens': 0}
                        }
                        firestore_success = self.save_job_to_firestore(job_id, failed_result)
                        if firestore_success:
                            print(f"📊 [FAILED JOB] Failed job {job_id} saved to Firestore")
                    except Exception as firestore_error:
                        print(f"❌ [FIRESTORE ERROR] Failed to save failed job to database: {str(firestore_error)}")
                    
                    # add_job_log(job_id, f"Job {job_id} failed: {error_msg}")
                    self.update_job_status(job_id, JobStatus.FAILED, error_msg)
                    
            except Exception as e:
                error_msg = f"Job execution failed: {str(e)}"
                
                # Save Docker container logs for failed job (if possible)
                try:
                    container_id = session_info.get('container_id')
                    if container_id:
                        self.save_container_logs(job_id, container_id)
                except Exception as log_error:
                    print(f"❌ [DOCKER LOGS] Error saving container logs: {str(log_error)}")
                
                # Save failed job to Firestore 
                try:
                    failed_result = {
                        'status': 'error',
                        'error': error_msg,
                        'metrics': {},
                        'costs': {'total_cost': 0, 'total_tokens': 0}
                    }
                    firestore_success = self.save_job_to_firestore(job_id, failed_result)
                    if firestore_success:
                        print(f"📊 [FAILED JOB] Failed job {job_id} saved to Firestore")
                except Exception as firestore_error:
                    print(f"❌ [FIRESTORE ERROR] Failed to save failed job to database: {str(firestore_error)}")
                
                # add_job_log(job_id, f"Job {job_id} failed: {error_msg}")
                self.update_job_status(job_id, JobStatus.FAILED, error_msg)
        
        # Start job execution in background thread
        job_thread = threading.Thread(target=execute_job, daemon=True)
        job_thread.start()
        
        return True
    
    def get_job_report_path(self, job_id: str) -> Optional[str]:
        """Get the path to the job's analysis report"""
        job_info = self.get_job(job_id)
        if not job_info or job_info['status'] != JobStatus.COMPLETED:
            return None
            
        output_dir = job_info.get('output_dir')
        if not output_dir:
            return None
            
        report_path = os.path.join(output_dir, 'analysis_report.html')
        if os.path.exists(report_path):
            return report_path
            
        return None
    
    def cleanup_old_jobs(self, max_age_hours: int = 24):
        """Clean up jobs older than max_age_hours"""
        current_time = time.time()
        max_age_seconds = max_age_hours * 3600
        
        with self.lock:
            jobs_to_cleanup = []
            for job_id, job_info in self.jobs.items():
                if current_time - job_info['created_at'] > max_age_seconds:
                    jobs_to_cleanup.append(job_id)
            
            for job_id in jobs_to_cleanup:
                add_log(f"Cleaning up old job: {job_id}")
                self._cleanup_job(job_id)
    
    def _cleanup_job(self, job_id: str):
        """Clean up a specific job and its associated files"""
        job_info = self.jobs.get(job_id)
        if job_info:
            try:
                # Remove job directories
                import shutil
                
                input_dir = job_info.get('input_dir')
                if input_dir and os.path.exists(input_dir):
                    shutil.rmtree(input_dir)
                    
                output_dir = job_info.get('output_dir')  
                if output_dir and os.path.exists(output_dir):
                    shutil.rmtree(output_dir)
                
                # Remove from jobs dict
                del self.jobs[job_id]
                self._save_jobs_to_file()
                
                add_log(f"Job {job_id} cleaned up successfully")
                
            except Exception as e:
                add_log(f"Error cleaning up job {job_id}: {str(e)}")
    
    def get_jobs_by_session(self, session_id: str) -> list:
        """Get all jobs for a specific session"""
        with self.lock:
            session_jobs = []
            for job_id, job_info in self.jobs.items():
                if job_info.get('session_id') == session_id:
                    job_copy = job_info.copy()
                    if isinstance(job_copy['status'], JobStatus):
                        job_copy['status'] = job_copy['status'].value
                    session_jobs.append(job_copy)
            return session_jobs
    
    def get_jobs_by_user(self, user_email: str) -> list:
        """Get all jobs for a specific user"""
        with self.lock:
            user_jobs = []
            for job_id, job_info in self.jobs.items():
                job_user_info = job_info.get('user_info', {})
                if job_user_info.get('email', '').lower() == user_email.lower():
                    job_copy = job_info.copy()
                    if isinstance(job_copy['status'], JobStatus):
                        job_copy['status'] = job_copy['status'].value
                    user_jobs.append(job_copy)
            return user_jobs
    
    def _extract_user_email_from_job(self, job_info: Dict[str, Any]) -> Optional[str]:
        """Extract user email from job info for Firestore path"""
        user_info = job_info.get('user_info', {})
        return user_info.get('email')
    
    def _calculate_total_cost(self, metrics: Dict[str, Any]) -> float:
        """Calculate total cost based on token usage"""
        # Pricing for GPT-4o-mini (example pricing - adjust as needed)
        input_cost_per_1k = 0.00015  # $0.00015 per 1K input tokens
        output_cost_per_1k = 0.0006  # $0.0006 per 1K output tokens
        
        input_tokens = metrics.get('prompt_tokens', 0)
        output_tokens = metrics.get('completion_tokens', 0)
        
        input_cost = (input_tokens / 1000) * input_cost_per_1k
        output_cost = (output_tokens / 1000) * output_cost_per_1k
        
        return round(input_cost + output_cost, 6)
    
    def save_job_to_firestore(self, job_id: str, execution_response: Dict[str, Any]) -> bool:
        """
        Save job output to Firestore according to the data model [[memory:6942292]]
        
        Args:
            job_id: Job identifier
            execution_response: Response from container execution containing metrics, costs, etc.
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            job_info = self.get_job(job_id)
            if not job_info:
                add_log(f"❌ Job {job_id} not found for Firestore save")
                return False
            
            # Extract user email for Firestore path
            user_email = self._extract_user_email_from_job(job_info)
            if not user_email:
                add_log(f"❌ No user email found for job {job_id}, cannot save to Firestore")
                return False
            
            session_id = job_info['session_id']
            
            # Extract metrics from execution response
            metrics = execution_response.get('metrics', {})
            costs = execution_response.get('costs', {})
            
            # Determine job status based on execution response
            execution_status = execution_response.get('status', 'success')
            has_error = execution_response.get('error') is not None
            
            # Check for token exhaustion indicators (from graceful completion)
            analysis_completed_early = execution_response.get('analysis_completed_early', False)
            completion_reason = execution_response.get('completion_reason', '')
            token_limit_reached = completion_reason == 'token_limit_reached'
            
            # Job is failed if: execution failed OR has error OR token limit was reached
            job_status = "failed" if (execution_status == 'error' or has_error or token_limit_reached) else "success"
            
            print(f"📊 [JOB_STATUS] Job {job_id} status: {job_status}")
            print(f"📊 [JOB_STATUS] Factors: execution_status={execution_status}, has_error={has_error}, token_limit_reached={token_limit_reached}")
            
            # Upload analysis report to Firebase Storage ONLY for successful jobs
            output_dir = job_info.get('output_dir', '')
            report_path = os.path.join(output_dir, 'analysis_report.html')
            
            # Firebase Storage path: sessionId/jobId/analysis_report.html
            storage_path = f"{session_id}/{job_id}/analysis_report.html"
            
            # Upload file and get Firebase Storage URL - SKIP ERROR REPORTS
            report_url = ""
            if job_status == "success" and os.path.exists(report_path):
                try:
                    firebase_storage_url = self.data_manager.crud.upload_file_to_storage(report_path, storage_path)
                    if firebase_storage_url:
                        report_url = firebase_storage_url  # Use Firebase Storage URL ONLY
                        print(f"📤 [PROGRESS] 🔗 Report uploaded to Firebase Storage: {report_url}")
                        add_log(f"✅ Report uploaded to Firebase Storage for job {job_id}: {report_url}")
                    else:
                        print(f"❌ [PROGRESS] 🔗 Failed to upload report to Firebase Storage - Empty URL will be saved")
                        add_log(f"❌ Failed to upload report to Firebase Storage for job {job_id} - JobDocument will have empty report_url")
                        # Use empty string instead of local path - ensures ONLY Firebase Storage URLs or empty
                        report_url = ""
                except Exception as upload_error:
                    print(f"❌ [STORAGE ERROR] Failed to upload report: {str(upload_error)}")
                    add_log(f"Storage upload error for job {job_id}: {str(upload_error)}")
                    # Use empty string instead of local path - ensures ONLY Firebase Storage URLs or empty
                    report_url = ""
            elif job_status == "failed":
                if token_limit_reached:
                    print(f"🚫 [TOKEN EXHAUSTED] Not uploading partial report to Firebase Storage for token-exhausted job {job_id}")
                    add_log(f"Skipped Firebase Storage upload for token-exhausted job {job_id} - partial reports not stored in GCP")
                else:
                    print(f"🚫 [SKIPPED] Not uploading error report to Firebase Storage for failed job {job_id}")
                    add_log(f"Skipped Firebase Storage upload for failed job {job_id} - error reports not stored in GCP")
                report_url = ""
            else:
                print(f"⚠️ [WARNING] Analysis report not found at: {report_path}")
                add_log(f"Warning: Analysis report not found for job {job_id} - JobDocument will have empty report_url")
                # Use empty string instead of local path - ensures ONLY Firebase Storage URLs or empty
                report_url = ""
            
            logs_url = f"/logs/{session_id}/{job_id}/"
            
            # Final validation: Ensure report_url is either empty or a valid Firebase Storage URL
            if report_url and not report_url.startswith('https://storage.googleapis.com/'):
                print(f"⚠️ [VALIDATION WARNING] Report URL is not a Firebase Storage URL: {report_url}")
                print(f"🔒 [VALIDATION] Converting to empty string to ensure Firebase Storage URLs only")
                add_log(f"Validation: Non-Firebase Storage URL detected for job {job_id}, converting to empty string")
                report_url = ""
            
            print(f"✅ [VALIDATION] Final report_url for JobDocument: '{report_url}' (Firebase Storage URL or empty)")
            
            # Create JobDocument according to the data model
            job_document = JobDocument(
                job_id=job_id,
                created_at=datetime.fromtimestamp(job_info['created_at']),
                logs_url=logs_url,
                report_url=report_url,
                total_token_used=metrics.get('total_tokens', 0),
                total_cost=costs.get('total_cost', 0),
                question=job_info['query'],
                job_status=job_status
            )
            
            # Save to Firestore using the data manager
            success = self.data_manager.create_job(user_email, session_id, job_document)
            
            if success:
                if token_limit_reached:
                    add_log(f"⚠️ Token-exhausted job {job_id} saved to Firestore with status 'failed'")
                    print(f"🔥 [FIRESTORE] Token-exhausted job {job_id} saved as FAILED for user {user_email} in session {session_id}")
                else:
                    add_log(f"✅ Job {job_id} saved to Firestore successfully")
                    print(f"🔥 [FIRESTORE] Job {job_id} saved for user {user_email} in session {session_id}")
            else:
                add_log(f"❌ Failed to save job {job_id} to Firestore")
            
            return success
            
        except Exception as e:
            error_msg = f"Error saving job {job_id} to Firestore: {str(e)}"
            add_log(f"❌ {error_msg}")
            print(f"❌ [FIRESTORE ERROR] {error_msg}")
            return False

# Global job manager instance
job_manager = JobManager()
