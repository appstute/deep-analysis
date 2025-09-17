# Session Manager - COMMENTED OUT
# This entire file has been commented out as requested to disable session logic

import docker
from docker.errors import NotFound
import uuid
import time
import threading
import os
import json
import shutil
from typing import Dict, Optional, Tuple, Any, cast, List

from logger import add_log, get_logs, clear_logs

class SessionManager:
    """Manages session-container pairs for isolated code execution environments"""
    
    def __init__(self, docker_image: str = "code-execution-env"):
        self.docker_client = docker.from_env()
        self.docker_image = docker_image
        self.sessions: Dict[str, Dict[str, Any]] = {}  # session_id -> {container_id, container_obj, created_at}
        self.lock = threading.Lock()
        self.sessions_file = "sessions.json"
        self._load_sessions_from_file()
    
    def _load_sessions_from_file(self):
        """Load existing sessions from JSON file"""
        if os.path.exists(self.sessions_file):
            try:
                with open(self.sessions_file, 'r') as f:
                    stored_sessions = json.load(f)
                
                # Validate and restore sessions
                for session_id, session_data in stored_sessions.items():
                    if self._validate_existing_session(session_id, session_data):
                        self.sessions[session_id] = session_data
                        # add_log(f"Restored session {session_id} from file")
                    else:
                        add_log(f"Session {session_id} from file is invalid, skipping")
                        
            except Exception as e:
                add_log(f"Error loading sessions from file: {str(e)}")
                # If file is corrupted, start fresh
                self.sessions = {}
    
    def _save_sessions_to_file(self):
        """Save current sessions to JSON file"""
        try:
            # Convert sessions to JSON-serializable format
            sessions_to_save = {}
            for session_id, session_info in self.sessions.items():
                sessions_to_save[session_id] = {
                    'container_id': session_info['container_id'],
                    'created_at': session_info['created_at'],
                    'status': session_info['status'],
                    'container_ip': session_info.get('container_ip', ''),
                    'container_port': session_info.get('container_port', ''),
                    'output_dir': session_info.get('output_dir', ''),
                    'user_info': session_info.get('user_info', {})
                }
            
            with open(self.sessions_file, 'w') as f:
                json.dump(sessions_to_save, f, indent=2)
                
        except Exception as e:
            add_log(f"Error saving sessions to file: {str(e)}")
    
    def check_session_ownership(self, session_id: str, user_email: str) -> bool:
        """Check if a user owns a specific session"""
        with self.lock:
            session_info = self.sessions.get(session_id)
            if not session_info:
                return False
            
            session_user_info = session_info.get('user_info', {})
            session_user_email = session_user_info.get('email', '').lower()
            
            return session_user_email == user_email.lower()
    
    def _validate_existing_session(self, session_id: str, session_data: Dict[str, Any]) -> bool:
        """Validate if an existing session from file is still valid"""
        try:
            container_id = session_data.get('container_id')
            if not container_id:
                return False
                
            # Try to get the container
            container = self.docker_client.containers.get(container_id)
            
            # Check if container is running
            container.reload()
            if container.status == 'running':
                # Add container object to session data
                session_data['container_obj'] = container
                
                # Get container IP address
                container_ip = self._get_container_ip(container)
                if container_ip:
                    session_data['container_ip'] = container_ip
                    
                return True
            else:
                # Try to start the container if it's stopped
                add_log(f"Container {container_id[:12]} is {container.status}, attempting to start...")
                container.start()
                container.reload()
                if container.status == 'running':
                    session_data['container_obj'] = container
                    
                    # Get container IP address
                    container_ip = self._get_container_ip(container)
                    if container_ip:
                        session_data['container_ip'] = container_ip
                        
                    add_log(f"Successfully started container {container_id[:12]}")
                    return True
                else:
                    add_log(f"Failed to start container {container_id[:12]}")
                    return False
                    
        except NotFound:
            add_log(f"Container {session_data.get('container_id', 'unknown')[:12]} not found, session invalid")
            return False
        except Exception as e:
            add_log(f"Error validating session {session_id}: {str(e)}")
            return False
    
    def _get_container_ip(self, container) -> str:
        """Get container IP address"""
        try:
            container.reload()
            if not container.attrs:
                return ''
                
            network_settings = container.attrs.get('NetworkSettings', {})
            if not network_settings:
                return ''
                
            networks = network_settings.get('Networks', {})
            if not networks:
                return ''
                
            if 'bridge' in networks:
                bridge_config = networks['bridge']
                if bridge_config and 'IPAddress' in bridge_config:
                    ip_address = bridge_config['IPAddress']
                    if ip_address:
                        return ip_address
            
            # If not on bridge, get the first available network
            for network_name, network_config in networks.items():
                if network_config and 'IPAddress' in network_config:
                    ip_address = network_config['IPAddress']
                    if ip_address:
                        return ip_address
                    
            return ''
        except Exception as e:
            add_log(f"Error getting container IP: {str(e)}")
            return ''
        
    def create_session(self, user_info: Optional[Dict[str, Any]] = None) -> Tuple[str, str]:
        """Create a new session with associated Docker container"""
        session_id = str(uuid.uuid4())
        
        with self.lock:
            try:
                add_log(f"Creating new session: {session_id}")
                
                # Find a free port for the container
                port = self._find_free_port()
                add_log(f"Using port {port} for container")

                # Determine host paths for input and output directories inside execution_layer
                base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))  # Points to backend/

                # CORRECTED: Back to original session-based mounting
                # Host input data directory (session-specific, read-only)
                input_data_dir = os.path.join(base_dir, 'execution_layer', 'input_data', session_id)

                # Host output data directory (session-specific, read-write)
                session_output_dir = os.path.join(base_dir, 'execution_layer', 'output_data', session_id)
                os.makedirs(session_output_dir, exist_ok=True)
                
                # Automatically copy files from the most recent session with files
                most_recent_session = self._get_most_recent_session_with_files(user_info)
                if most_recent_session:
                    add_log(f"Auto-copying files from most recent session: {most_recent_session}")
                    self._copy_session_input_files(most_recent_session, session_id, base_dir)
                    
                    # After successful copy, cleanup the previous session completely
                    add_log(f"Cleaning up previous session after successful copy: {most_recent_session}")
                    self._cleanup_previous_session(most_recent_session)
                
                print(f"🔧 [SESSION MANAGER] Creating session {session_id}")
                print(f"📥 Host input mount: {input_data_dir} -> /app/execution_layer/input_data")
                print(f"📤 Host output mount: {session_output_dir} -> /app/execution_layer/output_data")
                print(f"💡 Jobs will create subdirectories inside container output_data/")
                
                # Create container with session-specific volume mounting (ORIGINAL DESIGN)
                container = self.docker_client.containers.run(
                    self.docker_image,
                    detach=True,
                    name=f"session-{session_id[:8]}",
                    volumes={
                        # Mount session input directory (read-only)
                        input_data_dir: {
                            'bind': '/app/execution_layer/input_data',
                            'mode': 'ro'
                        },
                        # Mount session output directory (read-write) - jobs create subdirs here
                        session_output_dir: {
                            'bind': '/app/execution_layer/output_data',
                            'mode': 'rw'
                        }
                    },
                    ports={
                        '5001/tcp': port  # Map container port 5001 to host port
                    },
                    working_dir='/app',
                    mem_limit='1g',
                    cpu_count=1,
                    network_mode='bridge',
                    remove=False,  # Keep container for debugging
                    tty=True,  # Allocate a pseudo-TTY
                    stdin_open=True,  # Keep STDIN open
                    extra_hosts={
                    'host.docker.internal': 'host-gateway'
                }

                )
                
                container_id = container.id
                
                # Ensure container is running
                container.reload()
                if container.status != 'running':
                    add_log(f"Container {container_id[:12]} is not running, attempting to start...")
                    container.start()
                    container.reload()
                    if container.status != 'running':
                        raise Exception(f"Failed to start container {container_id[:12]}")
                
                # Get container IP address
                container_ip = self._get_container_ip(container)
                
                # Store session information
                self.sessions[session_id] = {
                    'container_id': container_id,
                    'container_obj': container,
                    'container_ip': container_ip,
                    'container_port': port,
                    'created_at': time.time(),
                    'status': 'active',
                    'output_dir': session_output_dir,
                    'user_info': user_info or {}
                }
                
                # Save sessions to file
                self._save_sessions_to_file()
                
                add_log(f"Session {session_id} created with container {container_id[:12]} (status: {container.status}, IP: {container_ip}, Port: {port})")
                # Cast to ensure we return a non-None string
                return session_id, cast(str, container_id)
                
            except Exception as e:
                add_log(f"Error creating session {session_id}: {str(e)}")
                raise
    
    def _find_free_port(self) -> int:
        """Find a free port on the host"""
        import socket
        
        # Start from port 5100
        start_port = 5100
        max_port = 5999
        
        for port in range(start_port, max_port + 1):
            # Check if port is already used by another container
            if any(session_info.get('container_port') == port for session_info in self.sessions.values()):
                continue
                
            # Check if port is free on host
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind(('', port))
                    return port
                except OSError:
                    continue
                    
        # If we get here, no ports were available
        raise Exception(f"No free ports available in range {start_port}-{max_port}")
    
    def _copy_session_input_files(self, source_session_id: str, target_session_id: str, base_dir: str):
        """Copy input files from source session to target session"""
        try:
            source_input_dir = os.path.join(base_dir, 'execution_layer', 'input_data', source_session_id)
            target_input_dir = os.path.join(base_dir, 'execution_layer', 'input_data', target_session_id)
            
            # Check if source session input directory exists
            if not os.path.exists(source_input_dir):
                add_log(f"Source session {source_session_id} input directory not found: {source_input_dir}")
                return
            
            # Create target input directory
            os.makedirs(target_input_dir, exist_ok=True)
            
            # Copy all files from source to target
            files_copied = 0
            for filename in os.listdir(source_input_dir):
                source_file = os.path.join(source_input_dir, filename)
                target_file = os.path.join(target_input_dir, filename)
                
                if os.path.isfile(source_file):
                    shutil.copy2(source_file, target_file)
                    files_copied += 1
                    add_log(f"Copied file: {filename} from session {source_session_id} to {target_session_id}")
            
            add_log(f"Successfully copied {files_copied} files from session {source_session_id} to {target_session_id}")
            
        except Exception as e:
            add_log(f"Error copying files from session {source_session_id} to {target_session_id}: {str(e)}")
            raise
    
    def _cleanup_previous_session(self, session_id: str):
        """Clean up previous session completely after successful data copy (removes from sessions.json and deletes files)"""
        try:
            add_log(f"Starting complete cleanup of previous session: {session_id}")
            
            # Check if session exists and is safe to delete
            session_info = None
            
            # First check in-memory sessions
            if session_id in self.sessions:
                session_info = self.sessions[session_id]
                
                # Don't delete if session is currently active (has running container)
                if session_info.get('status') == 'active' and session_info.get('container_obj'):
                    add_log(f"⚠️ Skipping cleanup - session {session_id} is currently active with running container")
                    return
            
            # Also check persistent sessions.json file
            persistent_session_info = None
            if os.path.exists(self.sessions_file):
                try:
                    with open(self.sessions_file, 'r') as f:
                        persistent_sessions = json.load(f)
                        persistent_session_info = persistent_sessions.get(session_id)
                except Exception as e:
                    add_log(f"Error reading persistent sessions for cleanup: {str(e)}")
            
            # 1. Remove session from in-memory sessions
            if session_id in self.sessions:
                del self.sessions[session_id]
                add_log(f"✅ Removed session {session_id} from in-memory sessions")
            
            # 2. Remove session from persistent sessions.json file
            if persistent_session_info:
                try:
                    with open(self.sessions_file, 'r') as f:
                        persistent_sessions = json.load(f)
                    
                    if session_id in persistent_sessions:
                        del persistent_sessions[session_id]
                        
                        with open(self.sessions_file, 'w') as f:
                            json.dump(persistent_sessions, f, indent=2)
                        
                        add_log(f"✅ Removed session {session_id} from persistent sessions.json")
                    
                except Exception as e:
                    add_log(f"Error removing session from persistent file: {str(e)}")
            
            # 3. Remove input directory and files (the old session's data)
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
            input_dir = os.path.join(base_dir, 'execution_layer', 'input_data', session_id)
            
            if os.path.exists(input_dir):
                try:
                    files_before = len(os.listdir(input_dir))
                    shutil.rmtree(input_dir)
                    add_log(f"✅ Deleted previous session input directory {input_dir} with {files_before} files")
                except Exception as e:
                    add_log(f"Error deleting input directory {input_dir}: {str(e)}")
            else:
                add_log(f"Input directory {input_dir} does not exist - already cleaned")
            
            # 4. Also clean up output directory if it exists
            output_dir = None
            if session_info:
                output_dir = session_info.get('output_dir')
            elif persistent_session_info:
                output_dir = persistent_session_info.get('output_dir')
            
            if output_dir and os.path.exists(output_dir):
                try:
                    shutil.rmtree(output_dir)
                    add_log(f"✅ Deleted previous session output directory {output_dir}")
                except Exception as e:
                    add_log(f"Error deleting output directory {output_dir}: {str(e)}")
            
            add_log(f"🎯 Previous session {session_id} completely cleaned up - only new session remains with copied data")
            
        except Exception as e:
            add_log(f"Error during previous session cleanup {session_id}: {str(e)}")
            # Don't raise - cleanup failure shouldn't stop new session creation
    
    def _get_most_recent_session_with_files(self, current_user_info: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Get the most recent session that has input files, STRICTLY filtered by current user only"""
        try:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
            input_data_base = os.path.join(base_dir, 'execution_layer', 'input_data')
            
            if not os.path.exists(input_data_base):
                return None
            
            # If no user info provided, don't copy any data (security measure)
            if not current_user_info or not current_user_info.get('email'):
                add_log("No user info provided, skipping previous session data copy for security")
                return None
            
            current_user_email = current_user_info.get('email').lower()
            user_sessions_with_files = []
            
            # Load all session data from both memory and persistent file
            all_session_data = {}
            
            # First, load from persistent sessions.json file
            if os.path.exists(self.sessions_file):
                try:
                    with open(self.sessions_file, 'r') as f:
                        persistent_sessions = json.load(f)
                        all_session_data.update(persistent_sessions)
                        add_log(f"Loaded {len(persistent_sessions)} sessions from persistent file")
                except Exception as e:
                    add_log(f"Error reading persistent sessions file: {str(e)}")
            
            # Then, update with in-memory sessions (more recent)
            for session_id, session_info in self.sessions.items():
                if session_id not in all_session_data or session_info.get('created_at', 0) > all_session_data.get(session_id, {}).get('created_at', 0):
                    all_session_data[session_id] = session_info
            
            add_log(f"Total sessions to check: {len(all_session_data)}")
            
            for session_dir in os.listdir(input_data_base):
                session_path = os.path.join(input_data_base, session_dir)
                if os.path.isdir(session_path):
                    # Check if this directory has any files
                    files = [f for f in os.listdir(session_path) if os.path.isfile(os.path.join(session_path, f))]
                    if files:
                        add_log(f"Session {session_dir} has {len(files)} files")
                        
                        # Get session info from combined data (persistent + memory)
                        session_info = all_session_data.get(session_dir, {})
                        
                        if not session_info:
                            add_log(f"No session info found for {session_dir} - skipping")
                            continue
                            
                        session_user_info = session_info.get('user_info', {})
                        session_user_email = session_user_info.get('email', '').lower()
                        
                        add_log(f"Session {session_dir}: user_email={session_user_email}, current_user={current_user_email}")
                        
                        # STRICT USER FILTER: Only include sessions from the SAME user
                        if session_user_email == current_user_email:
                            created_at = session_info.get('created_at', 0)
                            user_sessions_with_files.append({
                                'session_id': session_dir,
                                'created_at': created_at,
                                'user_email': session_user_email
                            })
                            add_log(f"✅ Found user session with files: {session_dir} (user: {session_user_email}, created: {created_at})")
                        else:
                            add_log(f"❌ Skipping session {session_dir} - belongs to different user: {session_user_email}")
                    else:
                        add_log(f"Session {session_dir} has no files - skipping")
            
            if not user_sessions_with_files:
                add_log(f"No previous sessions with files found for user: {current_user_email}")
                return None
            
            # Sort by creation time (newest first) - only same-user sessions
            user_sessions_with_files.sort(key=lambda x: x['created_at'], reverse=True)
            
            most_recent_session = user_sessions_with_files[0]['session_id']
            add_log(f"✅ Selected most recent user session: {most_recent_session} for user: {current_user_email} (created: {user_sessions_with_files[0]['created_at']})")
            return most_recent_session
            
        except Exception as e:
            add_log(f"Error getting most recent session with files: {str(e)}")
            return None
    
    def get_session_container(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get container information for a session"""
        with self.lock:
            session_info = self.sessions.get(session_id)
            if session_info and session_info['status'] == 'active':
                # Check if container is still running
                try:
                    container = session_info['container_obj']
                    container.reload()
                    if container.status == 'running':
                        # Make sure we have the IP address
                        if not session_info.get('container_ip'):
                            container_ip = self._get_container_ip(container)
                            if container_ip:
                                session_info['container_ip'] = container_ip
                                self._save_sessions_to_file()
                        return session_info
                    else:
                        add_log(f"Container for session {session_id} is not running: {container.status}")
                        session_info['status'] = 'inactive'
                        return None
                except Exception as e:
                    add_log(f"Error checking container status for session {session_id}: {str(e)}")
                    session_info['status'] = 'error'
                    return None
            return None
    
    def execute_in_container(self, session_id: str, command: str) -> Dict[str, Any]:
        """Execute a command in the session's container"""
        session_info = self.get_session_container(session_id)
        if not session_info:
            return {
                'success': False,
                'error': f'No active container found for session {session_id}',
                'output': ''
            }
        
        try:
            container = session_info['container_obj']
            
            # Create a temporary Python file to execute the command
            # This handles multi-line code better than -c flag
            temp_file = f"/tmp/exec_{int(time.time() * 1000)}.py"
            
            # Write the command to a temporary file in the container
            exec_result = container.exec_run(
                f"python -c \"with open('{temp_file}', 'w') as f: f.write('''{command}''')\"",
                stdout=True,
                stderr=True,
                stream=False,
                demux=True
            )
            
            if exec_result.exit_code != 0:
                return {
                    'success': False,
                    'error': f'Failed to create temporary file: {exec_result.output}',
                    'output': ''
                }
            
            # Execute the Python file
            exec_result = container.exec_run(
                f"python {temp_file}",
                stdout=True,
                stderr=True,
                stream=False,
                demux=True,
                workdir='/app'
            )
            
            stdout, stderr = exec_result.output
            exit_code = exec_result.exit_code
            
            # Clean up temporary file
            container.exec_run(f"rm -f {temp_file}")
            
            # Decode output
            stdout_str = stdout.decode('utf-8') if stdout else ''
            stderr_str = stderr.decode('utf-8') if stderr else ''
            
            if exit_code == 0:
                return {
                    'success': True,
                    'output': stdout_str,
                    'error': None
                }
            else:
                return {
                    'success': False,
                    'output': stdout_str,
                    'error': stderr_str
                }
                
        except Exception as e:
            add_log(f"Error executing command in container for session {session_id}: {str(e)}")
            return {
                'success': False,
                'error': f'Container execution error: {str(e)}',
                'output': ''
            }
    
    def cleanup_session(self, session_id: str) -> bool:
        """Clean up session container and ephemeral data (PRESERVES user input data)"""
        with self.lock:
            session_info = self.sessions.get(session_id)
            if session_info:
                try:
                    # Stop and remove Docker container
                    container = session_info['container_obj']
                    container.stop(timeout=10)
                    container.remove()
                    add_log(f"Container for session {session_id} stopped and removed")
                    
                    # Mark session as inactive instead of deleting from memory
                    self.sessions[session_id]['status'] = 'cleaned'
                    self.sessions[session_id]['container_obj'] = None
                    
                    # Save updated sessions to file (preserves session history)
                    self._save_sessions_to_file()

                    # ✅ SAFE: Only remove ephemeral output directory (job results)
                    output_dir = session_info.get('output_dir')
                    if output_dir and os.path.exists(output_dir):
                        try:
                            shutil.rmtree(output_dir)
                            add_log(f"Removed ephemeral output directory: {output_dir}")
                        except Exception as e:
                            add_log(f"Error deleting output directory {output_dir}: {str(e)}")

                    # 🛡️ PRESERVE: NEVER delete input directory (contains user's persistent data)
                    # Input directories contain user uploads and are needed for future sessions
                    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
                    input_data_dir = os.path.join(base_dir, 'execution_layer', 'input_data', session_id)
                    
                    if os.path.exists(input_data_dir):
                        files = os.listdir(input_data_dir)
                        add_log(f"🛡️ PRESERVING input directory {input_data_dir} with {len(files)} files for future sessions")
                    
                    add_log(f"Session {session_id} cleaned up successfully (container removed, data preserved)")
                    return True
                    
                except Exception as e:
                    add_log(f"Error cleaning up session {session_id}: {str(e)}")
                    return False
            return False
    
    def cleanup_inactive_sessions(self, max_age_hours: int = 24):
        """Clean up sessions older than max_age_hours"""
        current_time = time.time()
        max_age_seconds = max_age_hours * 3600
        
        with self.lock:
            sessions_to_cleanup = []
            for session_id, session_info in self.sessions.items():
                if current_time - session_info['created_at'] > max_age_seconds:
                    sessions_to_cleanup.append(session_id)
            
            for session_id in sessions_to_cleanup:
                add_log(f"Cleaning up old session: {session_id}")
                self.cleanup_session(session_id)
    
    def get_session_status(self, session_id: str) -> Dict[str, Any]:
        """Get status information for a session"""
        session_info = self.get_session_container(session_id)
        if session_info:
            return {
                'session_id': session_id,
                'container_id': session_info['container_id'],
                'container_ip': session_info.get('container_ip', ''),
                'status': session_info['status'],
                'created_at': session_info['created_at'],
                'uptime': time.time() - session_info['created_at']
            }
        else:
            return {
                'session_id': session_id,
                'status': 'not_found',
                'error': 'Session not found or inactive'
            }

    def restart_session(self, session_id: str) -> bool:
        """Restart a session by fully stopping and starting its container"""
        session_info = self.get_session_container(session_id)
        if not session_info:
            return False

       

        try:
            import subprocess
            subprocess.run(["docker", "restart", session_id])
            # container = session_info['container_obj']
            return True
        except Exception as e:
            print(f"Failed to restart session {session_id}: {e}")
            return False

# Global session manager instance
session_manager = SessionManager() 