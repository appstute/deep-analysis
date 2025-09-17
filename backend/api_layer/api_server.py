import re
import uuid
from flask import Flask, request, jsonify, Response, g, abort
import asyncio
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room, leave_room
import threading
from dotenv import load_dotenv
from .session_manager import SessionManager
from .refresh_token import refresh_google_token
from .job_manager import JobManager, JobStatus
from .firebase_user_manager import FirebaseUserManager
from .admin_routes import admin_bp
from .email_routes import email_bp
from .user_routes import user_bp
import time
import json
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import os
import shutil
import traceback
from logger import add_log, get_logs, clear_logs, get_job_logs, add_job_log, clear_job_logs
import tempfile
from werkzeug.utils import secure_filename
from typing import List, Dict, Any, Optional
from io import StringIO
from pydantic import BaseModel
from openai import OpenAI
import numpy as np
import math

# Global variable to store the socketio instance
_global_socketio_instance = None

def get_socketio_instance():
    """Get the global socketio instance for use in other modules"""
    return _global_socketio_instance

class ApiServer:
    def __init__(self):
        self.app = Flask(__name__)
        CORS(self.app, 
             origins=["http://localhost:3000", "http://127.0.0.1:3000"],
             methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
             allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
             supports_credentials=True)
        
        # Initialize SocketIO for real-time communication with frontend
        self.socketio = SocketIO(self.app, cors_allowed_origins="*", async_mode='threading')
        
        # Set global socketio instance for use in other modules
        global _global_socketio_instance
        _global_socketio_instance = self.socketio
        
        load_dotenv()
        # Configure requests session with longer timeouts
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            # Avoid retrying non-idempotent methods like POST to prevent duplicate analysis runs
            allowed_methods=["HEAD", "GET", "OPTIONS", "TRACE"]
        )
        self.session.mount("http://", HTTPAdapter(max_retries=retry_strategy))
        self.session.mount("https://", HTTPAdapter(max_retries=retry_strategy))
        
        # Initialize session manager and job manager
        self.session_manager = SessionManager(docker_image="code-execution-env")
        self.job_manager = JobManager()

        # Per-session run guards
        self._mutex = threading.Lock()
        self._active_sessions = set()

        # Initialize Firebase User Manager
        self.firebase_user_manager = FirebaseUserManager()
        
        # Load allowed emails from Firestore
        self.allowed_emails = self.load_emails_from_firestore()
        

        
        if self.firebase_user_manager.db:
            print(f"🔥 Firebase connected - {len(self.allowed_emails)} authorized users loaded from Firestore")
        else:
            print("⚠️  Firebase not connected - no users loaded")
        
        # Make firebase_user_manager available to all blueprints
        self.app.firebase_user_manager = self.firebase_user_manager
        
        # Register blueprints
        self.app.register_blueprint(admin_bp)
        self.app.register_blueprint(email_bp)
        self.app.register_blueprint(user_bp)
        
        # Register routes and WebSocket events
        self.register_routes()
        self.register_socketio_events()

        # Register global auth middleware
        @self.app.before_request
        def global_auth_middleware():
            # Skip auth for OPTIONS preflight and health check or hello route
            if (request.method == 'OPTIONS' or 
                request.path == '/hello' or 
                request.path.startswith('/getUser') or 
                request.path.startswith('/users/') or 
                request.path == '/google_auth' or 
                request.path == '/refresh_token' or 
                request.path == '/system/status'):
                return None

            # Handle Bearer token authentication for core endpoints
            if True:
                # Use Google OAuth for other endpoints (analysis, sessions, etc.)
                # Extract token from header or query param (for SSE)
                auth_header = request.headers.get('Authorization', '')
                token = None
                if auth_header.startswith('Bearer '):
                    token = auth_header.split('Bearer ')[-1]
                else:
                    token = request.args.get('token')

                payload = self.verify_google_token(token)

                if payload is None:
                    return jsonify({'error': 'Unauthorized'}), 401

                email = payload.get('email', '').lower()
                
                # Check Firebase availability
                if not self.firebase_user_manager.db:
                    print(f"⚠️  Firebase unavailable - allowing authenticated user {email} (no-auth mode)")
                    payload['role'] = 'admin'  # Grant admin access when Firebase is down
                    g.user = payload
                    return None
                
                # Check if user is authorized using Firestore
                is_authorized = self.firebase_user_manager.is_user_authorized(email)
                current_allowed_emails = self.firebase_user_manager.get_authorized_emails()
                
                # Bootstrap mode: If no emails are stored, allow any authenticated user
                # This allows the first user to set up the email system
                if not current_allowed_emails:
                    print(f"🚀 Bootstrap mode: No emails stored, allowing authenticated user {email}")
                    # Add the first user to Firestore as admin
                    success = self.firebase_user_manager.add_user_email(email)
                    if success:
                        self.firebase_user_manager.update_user(email, {'role': 'admin'})
                    payload['role'] = 'admin'
                    g.user = payload
                    return None
                
                # Check if user is authorized
                if not is_authorized:
                    print(f"🚫 User {email} not authorized to access the API")
                    return jsonify({
                        'error': 'Forbidden', 
                        'message': 'User not authorized to access this API',
                        'hint': 'Contact an administrator to add your email to the authorized list'
                    }), 403

                # User is authorized - get their role from Firestore
                print(f"✅ User {email} authorized for API access")
                user_role = self.firebase_user_manager.get_user_role(email)
                payload['role'] = user_role
                
                g.user = payload
                return None
    
    def register_socketio_events(self):
        """Register WebSocket event handlers for job progress streaming"""
        
        @self.socketio.on('connect')
        def handle_connect():
            print(f"[API LAYER] WebSocket client connected: {request.sid}")
        
        @self.socketio.on('disconnect')
        def handle_disconnect():
            print(f"[API LAYER] WebSocket client disconnected: {request.sid}")
            
        # RESTORED: Handle progress events from execution layer
        @self.socketio.on('execution_progress')
        def handle_execution_progress(data):
            """Forward progress events from execution layer to frontend"""
            try:
                job_id = data.get('job_id')
                if job_id:
                    print(f"[API LAYER] 📡 Forwarding progress for job {job_id}: {data.get('emoji', '')} {data.get('stage', '')} - {data.get('message', '')}")
                    
                    # Get job info to determine session
                    job_info = self.job_manager.get_job(job_id)
                    if job_info:
                        session_id = job_info.get('session_id', '')
                        if session_id:
                            # Emit to session-specific room
                            room_name = f'session_{session_id}_job_{job_id}'
                            self.socketio.emit('job_progress', data, room=room_name)
                            print(f"[API LAYER] ✅ Progress forwarded to room: {room_name}")
                        else:
                            # Fallback to job-only room
                            self.socketio.emit('job_progress', data, room=f'job_{job_id}')
                            print(f"[API LAYER] ✅ Progress forwarded to room: job_{job_id}")
                    else:
                        print(f"[API LAYER] ⚠️  Job not found for progress event: {job_id}")
            except Exception as e:
                print(f"[API LAYER] ❌ Error forwarding execution progress: {e}")
        
        @self.socketio.on('join_job')
        def handle_join_job(data):
            job_id = data.get('job_id')
            user_email = data.get('user_email', '').lower()  # Get user email from client
            session_id = data.get('session_id', '')  # Get session ID from client
            
            if job_id and user_email and session_id:
                # First verify that the user owns the session
                if not self.session_manager.check_session_ownership(session_id, user_email):
                    emit('join_error', {'job_id': job_id, 'error': 'Access denied: You do not own this session'})
                    print(f"[API LAYER] Session access denied for user {user_email} to session {session_id}")
                    return
                
                # Then verify that the user owns this job and it's in their session
                job_info = self.job_manager.get_job(job_id)
                if job_info:
                    job_user_info = job_info.get('user_info', {})
                    job_user_email = job_user_info.get('email', '').lower()
                    job_session_id = job_info.get('session_id', '')
                    
                    if job_user_email == user_email and job_session_id == session_id:
                        # User owns both the session and the job - join session-aware room
                        room_name = f'session_{session_id}_job_{job_id}'
                        join_room(room_name)
                        
                        # Start simple job monitoring for this job
                        self.monitor_job_status(job_id)
                        emit('joined_job', {'job_id': job_id, 'session_id': session_id, 'status': 'joined', 'room': room_name})
                        print(f"[API LAYER] User {user_email} joined session-aware job monitoring: {job_id} in session {session_id}")
                    else:
                        # User doesn't own this job or job is in wrong session
                        emit('join_error', {'job_id': job_id, 'error': 'Access denied: Job not found in your session'})
                        print(f"[API LAYER] Job access denied for user {user_email} to job {job_id}")
                else:
                    emit('join_error', {'job_id': job_id, 'error': 'Job not found'})
            else:
                emit('join_error', {'error': 'Missing job_id, user_email, or session_id'})
        
        @self.socketio.on('leave_job')
        def handle_leave_job(data):
            job_id = data.get('job_id')
            user_email = data.get('user_email', '').lower()
            session_id = data.get('session_id', '')
            
            if job_id and user_email and session_id:
                # Leave session-aware job room
                room_name = f'session_{session_id}_job_{job_id}'
                leave_room(room_name)
                emit('left_job', {'job_id': job_id, 'session_id': session_id, 'status': 'left', 'room': room_name})
                print(f"[API LAYER] User {user_email} left session-aware job monitoring: {job_id} in session {session_id}")
        
        @self.socketio.on('join_job_logs')
        def handle_join_job_logs(data):
            """Handle joining a job-specific log streaming room"""
            job_id = data.get('job_id')
            user_email = data.get('user_email', '').lower()
            session_id = data.get('session_id', '')
            
            if job_id and user_email and session_id:
                # First verify that the user owns the session
                if not self.session_manager.check_session_ownership(session_id, user_email):
                    emit('join_logs_error', {'job_id': job_id, 'error': 'Access denied: You do not own this session'})
                    print(f"[API LAYER] Log session access denied for user {user_email} to session {session_id}")
                    return
                
                # Then verify that the user owns this job and it's in their session
                job_info = self.job_manager.get_job(job_id)
                if job_info:
                    job_user_info = job_info.get('user_info', {})
                    job_user_email = job_user_info.get('email', '').lower()
                    job_session_id = job_info.get('session_id', '')
                    
                    if job_user_email == user_email and job_session_id == session_id:
                        # User owns both the session and the job - join job-specific log room
                        log_room_name = f'job_logs_{job_id}'
                        join_room(log_room_name)
                        
                        # Send existing job logs immediately
                        existing_logs = get_job_logs(job_id)
                        for log in existing_logs:
                            emit('job_log', log)
                        
                        emit('joined_job_logs', {'job_id': job_id, 'session_id': session_id, 'status': 'joined', 'room': log_room_name})
                        print(f"[API LAYER] User {user_email} joined job log streaming: {job_id}")
                    else:
                        emit('join_logs_error', {'job_id': job_id, 'error': 'Access denied: Job not found in your session'})
                        print(f"[API LAYER] Job log access denied for user {user_email} to job {job_id}")
                else:
                    emit('join_logs_error', {'job_id': job_id, 'error': 'Job not found'})
            else:
                emit('join_logs_error', {'error': 'Missing job_id, user_email, or session_id'})
        
        @self.socketio.on('leave_job_logs')
        def handle_leave_job_logs(data):
            """Handle leaving a job-specific log streaming room"""
            job_id = data.get('job_id')
            user_email = data.get('user_email', '').lower()
            
            if job_id and user_email:
                # Leave job log room
                log_room_name = f'job_logs_{job_id}'
                leave_room(log_room_name)
                emit('left_job_logs', {'job_id': job_id, 'status': 'left', 'room': log_room_name})
                print(f"[API LAYER] User {user_email} left job log streaming: {job_id}")
    
    def monitor_job_status(self, job_id):
        """Simple job status monitoring without complex WebSocket forwarding"""
        def run_monitoring():
            try:
                print(f"[API LAYER] 📊 Starting job status monitoring for: {job_id}")
                
                while True:
                    # Check job status
                    job_info = self.job_manager.get_job(job_id)
                    if not job_info:
                        print(f"[API LAYER] Job {job_id} not found, stopping monitoring")
                        break
                    
                    status_str = job_info['status'].value if isinstance(job_info['status'], JobStatus) else job_info['status']
                    
                    # Create status data
                    status_data = {
                        'job_id': job_info['job_id'],
                        'status': status_str,
                        'created_at': job_info['created_at'],
                        'started_at': job_info.get('started_at'),
                        'completed_at': job_info.get('completed_at'),
                        'error': job_info.get('error')
                    }
                    
                    # Emit to session-aware room
                    session_id = job_info.get('session_id', '')
                    if session_id:
                        room_name = f'session_{session_id}_job_{job_id}'
                        self.socketio.emit('job_status', status_data, room=room_name)
                    else:
                        # Fallback to job-only room
                        self.socketio.emit('job_status', status_data, room=f'job_{job_id}')
                    
                    # If job is complete, send final status and break
                    if status_str in ['completed', 'failed', 'cancelled']:
                        print(f"[API LAYER] 🏁 Job {status_str}: {job_id} - Final status reached")
                        if session_id:
                            room_name = f'session_{session_id}_job_{job_id}'
                            self.socketio.emit('job_complete', status_data, room=room_name)
                        else:
                            self.socketio.emit('job_complete', status_data, room=f'job_{job_id}')
                        break
                    
                    # Poll every 2 seconds
                    time.sleep(2)
                    
            except Exception as e:
                print(f"[API LAYER] ❌ Job monitoring error for {job_id}: {str(e)}")
                # Emit job error only to the session-aware job room
                error_data = {'job_id': job_id, 'error': str(e)}
                job_info = self.job_manager.get_job(job_id)
                if job_info:
                    session_id = job_info.get('session_id', '')
                    if session_id:
                        room_name = f'session_{session_id}_job_{job_id}'
                        self.socketio.emit('job_error', error_data, room=room_name)
                    else:
                        self.socketio.emit('job_error', error_data, room=f'job_{job_id}')
                else:
                    self.socketio.emit('job_error', error_data, room=f'job_{job_id}')
        
        # Start monitoring in a separate thread  
        threading.Thread(target=run_monitoring, daemon=True).start()
    
    def load_emails_from_firestore(self):
        """Load allowed emails from Firestore"""
        try:
            if self.firebase_user_manager.db:
                emails = self.firebase_user_manager.get_authorized_emails()
                print(f"📧 Loaded {len(emails)} authorized users from Firestore")
                return set(emails)
            else:
                print("⚠️  Firebase not available - no users loaded")
            return set()
            
        except Exception as e:
            print(f"❌ Error loading emails from Firestore: {str(e)}")
            return set()
    
    def verify_google_token(self, token: str):
        """Verify Google ID token using Google's tokeninfo endpoint.

        Returns payload dict if valid, otherwise None.
        Optionally checks audience (client id) if env var GOOGLE_CLIENT_ID present.
        """
        if not token:
            return None
        try:
            resp = requests.get(
                "https://oauth2.googleapis.com/tokeninfo",
                params={"id_token": token},
                timeout=5,
            )
            print("resp", resp.json())
            if resp.status_code != 200:
                return None
            payload = resp.json()
            # Optional audience check
            expected_aud = os.getenv("GOOGLE_CLIENT_ID")
            if expected_aud and payload.get("aud") != expected_aud:
                return None
            # Verify expiry
            if int(payload.get("exp", 0)) < int(time.time()):
                return None
            return payload
        except Exception:
            return None
    
    def google_auth(self, code: str):
        """Exchange Google auth code for tokens"""
        try:
            resp = requests.post(
                "https://oauth2.googleapis.com/token",
                data={"code": code, "client_id": os.getenv("GOOGLE_CLIENT_ID"), "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"), "redirect_uri": os.getenv("GOOGLE_REDIRECT_URI"), "grant_type": "authorization_code"}
            )
            print("resp", resp.json())
            if resp.status_code != 200:
                return None
            return resp.json()
        except Exception:
            return None
    
    def register_routes(self):
        """Register all API routes"""
        
        @self.app.route('/refresh_token', methods=['POST', 'OPTIONS'])
        def refresh_token_endpoint():
            if request.method == 'OPTIONS':
                return '', 204
            try:
                data = request.get_json()
                if not data or 'refresh_token' not in data:
                    return jsonify({'error': 'Missing refresh token'}), 400
                
                refresh_token = data['refresh_token']
                tokens = refresh_google_token(refresh_token)
                
                if not tokens:
                    return jsonify({'error': 'Failed to refresh token'}), 500
                
                # Extract user info from the new ID token to get email
                try:
                    import jwt
                    id_token = tokens.get('id_token')
                    if id_token:
                        # Decode token to get user email (don't verify signature since we just got it from Google)
                        decoded = jwt.decode(id_token, options={"verify_signature": False})
                        email = decoded.get('email', '').lower()
                        
                        if email and self.firebase_user_manager and self.firebase_user_manager.db:
                            # Get user role from database
                            user_role = self.firebase_user_manager.get_user_role(email)
                            if user_role:
                                # Add role to the token response
                                tokens['role'] = user_role
                                print(f"✅ Token refresh with role preserved: {email} -> {user_role}")
                            else:
                                print(f"⚠️  No role found for user {email} during token refresh")
                        else:
                            print(f"⚠️  Could not extract email from token or Firebase unavailable during refresh")
                except Exception as role_error:
                    print(f"⚠️  Error preserving role during token refresh: {str(role_error)}")
                    # Continue without role - don't fail the refresh
                    
                return jsonify(tokens), 200
            except Exception as e:
                print(f"Token refresh error: {str(e)}")
                return jsonify({'error': str(e)}), 500

        @self.app.route('/google_auth', methods=['POST', 'OPTIONS'])
        def google_auth_endpoint():
            if request.method == 'OPTIONS':
                return '', 204
            try:
                data = request.get_json()
                if not data or 'code' not in data:
                    return jsonify({'error': 'Missing authorization code'}), 400
                
                auth_code = data['code']
                tokens = self.google_auth(auth_code)
                
                if not tokens:
                    return jsonify({'error': 'Failed to exchange authorization code'}), 500
                    
                return jsonify(tokens), 200
            except Exception as e:
                print(f"Google auth error: {str(e)}")
                return jsonify({'error': str(e)}), 500

        @self.app.route('/hello')
        def hello():
            return jsonify({'message': 'Insight Bot Running'})
        
        @self.app.route('/system/status')
        def system_status():
            """Get system status and bootstrap information"""
            try:
                # Check Firebase availability first
                firebase_available = bool(self.firebase_user_manager.db)
                
                if not firebase_available:
                    return jsonify({
                        'system_state': 'firebase_unavailable',
                        'message': 'Firebase is not connected - system is in no-auth mode',
                        'firebase_connected': False,
                        'total_authorized_emails': 0,
                        'bootstrap_mode': False,
                        'storage': 'None',
                        'available_actions': {
                            'add_email': False,
                            'view_emails': False,
                            'manage_emails': False,
                            'use_analysis_api': True  # Always allow when Firebase is down
                        }
                    })
                
                # Load current emails from Firestore
                current_allowed_emails = self.firebase_user_manager.get_authorized_emails()
                
                # Check if request is authenticated with API key
                if hasattr(g, 'api_key_auth') and g.api_key_auth:
                    return jsonify({
                        'system_state': 'api_key_authenticated',
                        'message': 'Authenticated with API key - full email management access',
                        'authentication_method': 'API Key',
                        'firebase_connected': True,
                        'total_authorized_emails': len(current_allowed_emails),
                        'storage': 'Firestore',
                        'available_actions': {
                            'add_email': True,
                            'view_emails': True,
                            'manage_emails': True,
                            'delete_emails': True,
                            'update_emails': True
                        }
                    })
                
                # For Bearer token authentication
                user_email = g.user.get('email', '').lower() if hasattr(g, 'user') else None
                
                # Determine system state
                if not current_allowed_emails:
                    system_state = "bootstrap"
                    message = "System is in bootstrap mode - any authenticated user becomes admin"
                elif user_email in current_allowed_emails:
                    system_state = "authorized"
                    message = "You are authorized to use all API endpoints"
                else:
                    system_state = "unauthorized"
                    message = "You are not authorized - contact an admin to add your email"
                
                return jsonify({
                    'system_state': system_state,
                    'message': message,
                    'your_email': user_email,
                    'authentication_method': 'Bearer Token',
                    'firebase_connected': True,
                    'is_authorized': user_email in current_allowed_emails if current_allowed_emails else True,
                    'total_authorized_emails': len(current_allowed_emails),
                    'bootstrap_mode': not bool(current_allowed_emails),
                    'storage': 'Firestore',
                    'available_actions': {
                        'add_email': False,  # Email management requires API key
                        'view_emails': False,  # Email management requires API key
                        'manage_emails': False,  # Email management requires API key
                        'use_analysis_api': not current_allowed_emails or user_email in current_allowed_emails
                    }
                })
                
            except Exception as e:
                add_log(f"Error getting system status: {str(e)}")
                return jsonify({'error': f'Failed to get system status: {str(e)}'}), 500
        
        @self.app.route('/session_id')
        def session_id():
            try:
                # Get user info for session ownership
                token_payload = g.get('user', {})
                
                # Create session with Docker container and user info
                session_id, container_id = self.session_manager.create_session(user_info=token_payload)
                add_log(f"Session created: {session_id} with container: {container_id[:12]} for user: {token_payload.get('email', 'unknown')}")
                return jsonify({
                    'session_id': session_id,
                    'container_id': container_id,
                    'status': 'success'
                })
            except Exception as e:
                add_log(f"Error creating session: {str(e)}")
                return jsonify({
                    'error': f'Failed to create session: {str(e)}',
                    'status': 'error'
                }), 500
        
        def check_session_has_input_data(session_id):
            """Check if session has any input data files"""
            try:
                input_data_dir = os.path.join('execution_layer', 'input_data', session_id)
                
                if not os.path.exists(input_data_dir):
                    return False
                    
                # Check if directory has any files
                files = [f for f in os.listdir(input_data_dir) if os.path.isfile(os.path.join(input_data_dir, f))]
                return len(files) > 0
                
            except Exception as e:
                add_log(f"Error checking input data for session {session_id}: {str(e)}")
                return False

        @self.app.route('/validate_session/<session_id>')
        def validate_session(session_id):
            """Validate if a session exists and is active"""
            try:
                session_info = self.session_manager.get_session_container(session_id)
                if session_info:
                    # Check if session has input data
                    has_input_data = check_session_has_input_data(session_id)
                    
                    # Check if container API is responsive
                    container_port = session_info.get('container_port')
                    if container_port:
                        try:
                            # Try to ping the container's health endpoint
                            response = self.session.get(f"http://localhost:{container_port}/health", timeout=5)
                            if response.status_code == 200:
                                # add_log(f"Session {session_id} validated successfully")
                                return jsonify({
                                    'session_id': session_id,
                                    'container_id': session_info['container_id'],
                                    'status': 'active',
                                    'valid': True,
                                    'has_input_data': has_input_data
                                })
                        except requests.RequestException as e:
                            add_log(f"Container for session {session_id} is not responding: {str(e)}")
                            # Container exists but API is not responding
                            pass
                    
                    # If we couldn't validate via API, just check if container exists
                    # add_log(f"Session {session_id} validated successfully (container exists)")
                    return jsonify({
                        'session_id': session_id,
                        'container_id': session_info['container_id'],
                        'status': 'active',
                        'valid': True,
                        'has_input_data': has_input_data
                    })
                else:
                    # Check if session has input data even when not active
                    has_input_data = check_session_has_input_data(session_id)
                    add_log(f"Session {session_id} validation failed - not found or inactive")
                    return jsonify({
                        'session_id': session_id,
                        'status': 'not_found',
                        'valid': False,
                        'has_input_data': has_input_data
                    })
            except Exception as e:
                add_log(f"Error validating session {session_id}: {str(e)}")
                return jsonify({
                    'error': f'Failed to validate session: {str(e)}',
                    'status': 'error',
                    'valid': False,
                    'has_input_data': False
                }), 500
        
        @self.app.route('/session_status/<session_id>')
        def session_status(session_id):
            """Get status of a specific session"""
            try:
                status = self.session_manager.get_session_status(session_id)
                return jsonify(status)
            except Exception as e:
                add_log(f"Error getting session status: {str(e)}")
                return jsonify({
                    'error': f'Failed to get session status: {str(e)}',
                    'status': 'error'
                }), 500
        
        @self.app.route('/restart_session/<session_id>', methods=['POST'])
        def restart_user_session(session_id):
            """Restart a specific session"""
            try:
                success = self.session_manager.restart_session(session_id)
                if success:
                    return jsonify({
                        'message': f'Session {session_id} restarted successfully',
                        'status': 'success'
                    })
                else:
                    return jsonify({
                        'error': f'Failed to restart session {session_id}',
                        'status': 'error'
                    }), 404
            except Exception as e:
                add_log(f"Error restarting session: {str(e)}")
                return jsonify({
                    'error': f'Failed to restart session: {str(e)}',
                    'status': 'error'
                }), 500

        @self.app.route('/cleanup_session/<session_id>', methods=['POST'])
        def cleanup_session(session_id):
            """Clean up a specific session"""
            try:
                success = self.session_manager.cleanup_session(session_id)
                if success:
                    return jsonify({
                        'message': f'Session {session_id} cleaned up successfully',
                        'status': 'success'
                    })
                else:
                    return jsonify({
                        'error': f'Failed to cleanup session {session_id}',
                        'status': 'error'
                    }), 404
            except Exception as e:
                add_log(f"Error cleaning up session: {str(e)}")
                return jsonify({
                    'error': f'Failed to cleanup session: {str(e)}',
                    'status': 'error'
                }), 500
        
        @self.app.route('/logs')
        @self.app.route('/logs/<session_id>')
        def logs(session_id=None):
            def event_stream():
                # Send initial logs
                current_logs = get_logs()
                for log in current_logs:
                    yield f"event: log\ndata: {json.dumps(log)}\n\n"
                
                # Keep track of last sent log count
                last_count = len(current_logs)
                
                # Keep connection alive and check for new logs
                while True:
                    current_logs = get_logs()
                    current_count = len(current_logs)
                    
                    # If new logs exist, send them
                    if current_count > last_count:
                        for log in current_logs[last_count:]:
                            yield f"event: log\ndata: {json.dumps(log)}\n\n"
                        last_count = current_count
                    
                    # Send keep-alive every 3 seconds
                    yield f"event: keepalive\ndata: ping\n\n"
                    time.sleep(3)    
            try:
                return Response(
                    event_stream(),
                    mimetype="text/event-stream",
                    headers={
                        'Cache-Control': 'no-cache',
                        'Connection': 'keep-alive',
                        'X-Accel-Buffering': 'no'  # Disable proxy buffering
                    }
                )
            except Exception as e:
                add_log(f"Error getting logs: {str(e)}")
                return jsonify({'error': f'Failed to get logs: {str(e)}'}), 500
        
        @self.app.route('/job_logs/<job_id>')
        def job_logs(job_id):
            """Stream logs specific to a job with ownership verification"""
            try:
                # Get user info for verification
                token_payload = g.get('user', {})
                user_email = token_payload.get('email', '').lower()
                
                if not user_email:
                    return jsonify({'error': 'Unauthorized'}), 401
                
                # Verify job ownership
                job_info = self.job_manager.get_job(job_id)
                if not job_info:
                    return jsonify({'error': 'Job not found'}), 404
                
                job_user_info = job_info.get('user_info', {})
                job_user_email = job_user_info.get('email', '').lower()
                
                if job_user_email != user_email:
                    return jsonify({'error': 'Access denied: You do not own this job'}), 403
                
                def job_event_stream():
                    # Send initial job-specific logs
                    current_job_logs = get_job_logs(job_id)
                    for log in current_job_logs:
                        yield f"event: log\ndata: {json.dumps(log)}\n\n"
                    
                    # Keep track of last sent log count
                    last_count = len(current_job_logs)
                    
                    # Keep connection alive and check for new job logs
                    while True:
                        current_job_logs = get_job_logs(job_id)
                        current_count = len(current_job_logs)
                        
                        # If new logs exist, send them
                        if current_count > last_count:
                            for log in current_job_logs[last_count:]:
                                yield f"event: log\ndata: {json.dumps(log)}\n\n"
                            last_count = current_count
                        
                        # Send keep-alive every 3 seconds
                        yield f"event: keepalive\ndata: ping\n\n"
                        time.sleep(3)
                
                return Response(
                    job_event_stream(),
                    mimetype="text/event-stream",
                    headers={
                        'Cache-Control': 'no-cache',
                        'Connection': 'keep-alive',
                        'X-Accel-Buffering': 'no'  # Disable proxy buffering
                    }
                )
            except Exception as e:
                add_log(f"Error getting job logs for {job_id}: {str(e)}")
                return jsonify({'error': f'Failed to get job logs: {str(e)}'}), 500

                
        @self.app.route('/validate_data', methods=['POST'])
        def validate_data():
            """Validate uploaded CSV/XLSX file and return a strict response shape."""
            try:
                MAX_BYTES = 20 * 1024 * 1024  # 20MB
                allowed_ext = {'.csv', '.xlsx'}

                # Helper for uniform failure
                def fail(msg: str, status: int = 400):
                    return jsonify({
                        'valid': False,
                        'message': 'validation failed',
                        'error': msg,
                    }), status

                # Check file in form-data
                if 'file' not in request.files:
                    return fail('Missing file in request', 400)

                session_id = request.form.get('session_id')
                if not session_id:
                    return fail('Missing session_id in request', 400)

                f = request.files['file']
                filename = f.filename or ''
                if not filename:
                    return fail('Empty filename', 400)

                # Size check via content_length (entire request) – fallback to stream size when possible
                if request.content_length and request.content_length > MAX_BYTES:
                    return fail('File too large. Maximum allowed size is 20MB.', 413)

                ext = '.' + filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
                if ext not in allowed_ext:
                    return fail('Invalid file type. Only CSV and XLSX are allowed.', 415)

                # Persist to a temporary file to allow pandas to read
                safe_name = secure_filename(filename)
                with tempfile.NamedTemporaryFile(prefix='upload_', suffix=ext, delete=False) as tmp:
                    tmp_path = tmp.name
                    f.save(tmp)

                # Post-save size check (for clients that omit content-length)
                try:
                    if os.path.getsize(tmp_path) > MAX_BYTES:
                        os.remove(tmp_path)
                        return fail('File too large. Maximum allowed size is 20MB.', 413)
                except Exception:
                    pass

                import pandas as pd  # local import to reduce cold-start cost

                errors: List[str] = []
                warnings: List[str] = []
                info: Dict[str, Any] = {}

                # Load with pandas
                try:
                    if ext == '.csv':
                        # Read limited rows first to validate quickly
                        df = pd.read_csv(tmp_path, header=0)
                    else:  # .xlsx
                        try:
                            df = pd.read_excel(tmp_path, header=0, engine='openpyxl')
                        except Exception:
                            # Fallback without specifying engine
                            df = pd.read_excel(tmp_path, header=0)
                except UnicodeDecodeError as e:
                    os.remove(tmp_path)
                    msg = f'Encoding error: {str(e)}'
                    return fail(msg, 422)
                except ValueError as e:
                    os.remove(tmp_path)
                    msg = f'Value error while reading file: {str(e)}'
                    return fail(msg, 422)
                except Exception as e:
                    os.remove(tmp_path)
                    msg = f'Failed to read file: {str(e)}'
                    return fail(msg, 422)
                finally:
                    # Remove temp file regardless of parse result
                    try:
                        if os.path.exists(tmp_path):
                            os.remove(tmp_path)
                    except Exception:
                        pass

                # Basic header checks
                col_names = [str(c) for c in df.columns.tolist()]

                # 1) No empty or Unnamed columns
                if any((c.strip() == '' or c.lower().startswith('unnamed')) for c in col_names):
                    errors.append('Header row has empty or Unnamed columns. Ensure the first row contains proper column names.')

                # 2) No duplicate columns (case-insensitive)
                lowered = [c.lower() for c in col_names]
                if len(set(lowered)) != len(lowered):
                    errors.append('Duplicate column names detected (case-insensitive). Column names must be unique.')

                # 3) Heuristic: column names should not be numeric-like (indicates missing header)
                def is_numeric_like(s: str) -> bool:
                    try:
                        float(s.replace(',', ''))
                        return True
                    except Exception:
                        return False

                numeric_like_count = sum(1 for c in col_names if is_numeric_like(c))
                if df.shape[1] > 0 and numeric_like_count >= max(1, int(0.6 * df.shape[1])):
                    errors.append('First row appears to be data, not headers. Please include a header row as the first line.')

                # Shape checks (updated limits)
                rows, cols = df.shape
                if cols > 30:
                    errors.append('Too many columns. Maximum allowed is 30.')
                if rows > 500000:
                    errors.append('Too many rows. Maximum allowed is 500000.')

                # Content checks: disallow JSON/blob/image-like payloads in textual columns
                import re
                import json as pyjson

                base64_regex = re.compile(r'^[A-Za-z0-9+/=\r\n]+$')

                def looks_like_json(text: str) -> bool:
                    text = text.strip()
                    if not text or (text[0] not in '{['):
                        return False
                    # Fast path: avoid huge payloads
                    if len(text) > 20000:
                        return True
                    try:
                        pyjson.loads(text)
                        return True
                    except Exception:
                        return False

                def looks_like_base64_blob(text: str) -> bool:
                    # Heuristic: long and restricted alphabet typical of base64
                    if len(text) < 1000:
                        return False
                    # Remove whitespace/newlines
                    compact = ''.join(ch for ch in text if not ch.isspace())
                    if not base64_regex.match(compact):
                        return False
                    # Lots of padding or excessive length suggests blob
                    if len(compact) > 5000:
                        return True
                    return False

                # Examine object columns only
                try:
                    object_cols = [c for c in df.columns if str(df[c].dtype) == 'object']
                    sample_size = min(int(rows), 1000)
                    for col in object_cols:
                        series = df[col].dropna().astype(str).head(sample_size)
                        if series.empty:
                            continue
                        very_long = (series.str.len() > 50000).any()
                        json_like_ratio = series.apply(looks_like_json).mean() if len(series) > 0 else 0
                        b64_like_ratio = series.apply(looks_like_base64_blob).mean() if len(series) > 0 else 0
                        if very_long or json_like_ratio >= 0.2 or b64_like_ratio >= 0.2:
                            errors.append(f"Column '{col}' appears to contain non-text payloads (JSON/blob/image/base64). These are not allowed.")
                except Exception:
                    # Non-fatal: if inspection fails, skip content checks
                    pass

                # Decide result strictly
                valid = len(errors) == 0

                if valid:
                    # Save validated file as .pkl for future use
                    try:
                        input_data_dir = os.path.join('execution_layer', 'input_data', session_id)
                        os.makedirs(input_data_dir, exist_ok=True)
                        
                        # Create filename without extension and add .pkl
                        base_filename = filename.rsplit('.', 1)[0] if '.' in filename else filename
                        pkl_filename = f"{base_filename}.pkl"
                        pkl_path = os.path.join(input_data_dir, pkl_filename)
                        
                        # Save as pickle
                        df.to_pickle(pkl_path)
                        
                        return jsonify({
                            'valid': True,
                            'message': 'validation successful',
                            'saved_file': pkl_filename
                        }), 200
                    except Exception as e:
                        return jsonify({
                            'valid': False,
                            'message': 'validation failed',
                            'error': f'Failed to save file: {str(e)}'
                        }), 500
                else:
                    primary_error = errors[0] if errors else 'Validation failed'
                    return fail(primary_error, 400)
            except Exception as e:
                traceback.print_exc()
                msg = f'Unexpected error during validation: {str(e)}'
                return jsonify({'valid': False, 'message': 'validation failed', 'error': msg}), 500

        @self.app.route('/generate_domain_dictionary', methods=['POST'])
        def generate_domain_dictionary():
            """Generate a domain dictionary JSON from user-provided context and the saved pkl file."""
            try:
                def fail(msg: str, status: int = 400):
                    return jsonify({'error': msg}), status

                # Get data from JSON body instead of form data
                data = request.get_json()
                if not data:
                    return fail('Missing request data', 400)

                domain_desc = (data.get('domain') or '').strip()
                file_info = (data.get('file_info') or '').strip()
                filename = (data.get('filename') or '').strip()
                underlying_csv = (data.get('underlying_conditions_about_dataset') or '').strip()

                if not domain_desc:
                    return fail('Missing field: domain', 400)
                if not file_info:
                    return fail('Missing field: file_info', 400)
                if not filename:
                    return fail('Missing field: filename', 400)

                # Load the saved .pkl file
                input_data_dir = os.path.join('execution_layer', 'input_data', data.get('session_id'))
                base_filename = filename.rsplit('.', 1)[0] if '.' in filename else filename
                pkl_filename = f"{base_filename}.pkl"
                pkl_path = os.path.join(input_data_dir, pkl_filename)

                if not os.path.exists(pkl_path):
                    return fail(f'Saved file not found: {pkl_filename}. Please validate the file first.', 404)

                try:
                    import pandas as pd
                    df = pd.read_pickle(pkl_path)
                except Exception as e:
                    return fail(f'Failed to load saved file: {str(e)}', 500)

                # Prepare data summary with unique values for better descriptions
                rows, cols = df.shape
                columns_info = []
                for col in df.columns:
                    dtype_str = str(df[col].dtype)
                    # Get unique values for better context (limit to prevent huge payloads)
                    unique_values = df[col].dropna().unique()
                    if len(unique_values) > 10:
                        unique_sample = unique_values[:10].tolist()
                        unique_count = len(unique_values)
                    else:
                        unique_sample = unique_values.tolist()
                        unique_count = len(unique_values)
                    
                    # Also get sample values
                    sample_values = df[col].dropna().head(3).tolist()
                    
                    columns_info.append({
                        'name': str(col),
                        'dtype': dtype_str,
                        'sample_values': [str(v) for v in sample_values],
                        'unique_values': [str(v) for v in unique_sample],
                        'unique_count': unique_count,
                        'null_count': int(df[col].isnull().sum())
                    })

                underlying_list = [c.strip() for c in underlying_csv.split(',') if c.strip()] if underlying_csv else []

                # Create enhanced prompt
                prompt = f"""Create a comprehensive domain dictionary JSON for this dataset:

Domain: {domain_desc}
File Info: {file_info}
File: {filename}
Shape: {rows} rows, {cols} columns

Detailed Column Analysis:
{json.dumps(columns_info, indent=2)}

Business Rules: {underlying_list}

Instructions:
- Write detailed, meaningful descriptions for each column based on the unique values, data patterns, and domain context
- For ID columns, specify what entity they identify
- For categorical columns, mention the categories/types if clear from unique values
- For date columns, specify the purpose (creation, modification, expiry, etc.)
- For amount/numeric columns, specify what they measure
- Consider null counts and data quality in descriptions

Return ONLY a JSON object with this structure:
{{
  "domain": "detailed domain description",
  "data_set_files": {{"{filename}": "comprehensive file description"}},
  "columns": [
    {{"name": "column_name", "description": "detailed, context-aware description based on data analysis", "dtype": "data_type"}}
  ],
  "underlying_conditions_about_dataset": ["detailed business rule 1", "detailed business rule 2"]
}}"""

                # Call OpenAI using same pattern as analyze_user_query
                client = OpenAI()
                response = client.chat.completions.create(
                    model="gpt-4.1-mini",
                    messages=[
                        {"role": "system", "content": "You are a senior data analyst. Create concise, accurate domain dictionaries."},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.2,
                    max_tokens=2000
                )

                content = response.choices[0].message.content
                result = json.loads(content)

                # Ensure all required fields exist
                if 'domain' not in result:
                    result['domain'] = domain_desc
                if 'data_set_files' not in result:
                    result['data_set_files'] = {filename: file_info}
                if 'columns' not in result:
                    result['columns'] = [{'name': str(col), 'description': f'Column {col}', 'dtype': str(df[col].dtype)} for col in df.columns]
                if 'underlying_conditions_about_dataset' not in result:
                    result['underlying_conditions_about_dataset'] = underlying_list

                return jsonify({'message': 'generated', 'domain_dictionary': result}), 200

            except json.JSONDecodeError:
                return fail('Failed to parse LLM response as JSON', 500)
            except Exception as e:
                traceback.print_exc()
                return fail(f'Unexpected error: {str(e)}', 500)

        @self.app.route('/save_domain_dictionary', methods=['POST'])
        def save_domain_dictionary():
            """Save the domain dictionary to domain_directory.json file."""
            try:
                def fail(msg: str, status: int = 400):
                    return jsonify({'error': msg}), status

                # Get data from JSON body
                data = request.get_json()
                if not data:
                    return fail('Missing request data', 400)

                domain_dictionary = data.get('domain_dictionary')
                if not domain_dictionary:
                    return fail('Missing domain_dictionary in request', 400)

                # Save to domain_directory.json
                input_data_dir = os.path.join('execution_layer', 'input_data', data.get('session_id'))
                os.makedirs(input_data_dir, exist_ok=True)
                
                domain_file_path = os.path.join(input_data_dir, 'domain_directory.json')
                
                with open(domain_file_path, 'w', encoding='utf-8') as f:
                    json.dump(domain_dictionary, f, indent=2, ensure_ascii=False)

                return jsonify({
                    'message': 'Domain dictionary saved successfully',
                    'file_path': domain_file_path
                }), 200

            except Exception as e:
                traceback.print_exc()
                return fail(f'Failed to save domain dictionary: {str(e)}', 500)

        @self.app.route('/create_job', methods=['POST'])
        def create_job():
            """Create a new analysis job and return job ID immediately"""
            token_payload = g.get('user', {})
            #
            # Get analysis request from JSON body
            data = request.get_json()
            if not data or 'query' not in data:
                add_log("Error: Missing analysis query")
                return jsonify({'error': 'Missing analysis query'}), 400
            
            # Check for session ID
            session_id = data.get('session_id')
            if not session_id:
                add_log("Error: Missing session ID")
                return jsonify({'error': 'Missing session ID'}), 400
            
            # Validate session exists and has active container
            session_info = self.session_manager.get_session_container(session_id)
            if not session_info:
                add_log(f"Error: Invalid or inactive session: {session_id}")
                return jsonify({'error': f'Invalid or inactive session: {session_id}'}), 400
            
            user_query = data['query']
            model_name = data.get('model', "gpt-4.1-mini")
            
            # add_log(f"Creating job for user {token_payload.get('email', 'unknown')}")
            # add_log(f"Job query: {user_query} using model: {model_name}")
            
            try:
                # Create job using job manager with user info
                job_id, job_info = self.job_manager.create_job(
                    session_id=session_id,
                    query=user_query,
                    model=model_name,
                    session_info=session_info,
                    user_info=token_payload  # Pass user info for job ownership
                )
                
                # Start job execution asynchronously
                success = self.job_manager.start_job_execution(job_id, self.session_manager)
                
                if not success:
                    # add_job_log(job_id, "Failed to start job execution")
                    return jsonify({'error': 'Failed to start job execution'}), 500
                
                # Return job ID immediately
                response_data = {
                    'status': 'success',
                    'job_id': job_id,
                    'message': 'Job created and started successfully'
                }
                
                print(f"[API LAYER] ✅ Job created and started: {job_id} - Query: {user_query[:50]}...")
                # add_job_log(job_id, f"Job created and started successfully - Query: {user_query[:100]}")
                return jsonify(response_data)
                
            except Exception as e:
                error_msg = f"Job creation failed: {str(e)}"
                add_log(error_msg)
                traceback.print_exc()
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/job_status/<job_id>')
        def get_job_status(job_id):
            """Get status of a specific job"""
            try:
                job_info = self.job_manager.get_job(job_id)
                if not job_info:
                    return jsonify({'error': 'Job not found'}), 404
                
                # Convert JobStatus enum to string
                status_str = job_info['status'].value if isinstance(job_info['status'], JobStatus) else job_info['status']
                
                response_data = {
                    'job_id': job_info['job_id'],
                    'status': status_str,
                    'created_at': job_info['created_at'],
                    'started_at': job_info.get('started_at'),
                    'completed_at': job_info.get('completed_at'),
                    'error': job_info.get('error')
                }
                
                return jsonify(response_data)
                
            except Exception as e:
                add_log(f"Error getting job status: {str(e)}")
                return jsonify({'error': f'Failed to get job status: {str(e)}'}), 500
        

        
        @self.app.route('/job_report/<job_id>')
        def get_job_report(job_id):
            """Get the analysis report for a completed job"""
            try:
                job_info = self.job_manager.get_job(job_id)
                if not job_info:
                    return jsonify({'error': 'Job not found'}), 404
                
                status_str = job_info['status'].value if isinstance(job_info['status'], JobStatus) else job_info['status']
                
                if status_str != 'completed':
                    return jsonify({'error': f'Job is not completed. Current status: {status_str}'}), 400
                
                report_path = self.job_manager.get_job_report_path(job_id)
                if not report_path:
                    return jsonify({'error': 'Report not found'}), 404
                
                with open(report_path, 'r', encoding='utf-8') as f:
                    html = f.read()
                
                return Response(html, mimetype='text/html')
                
            except Exception as e:
                return jsonify({'error': f'Failed to read report: {str(e)}'}), 500
        
        # Analysis History API endpoints
        @self.app.route('/analysis_history', methods=['GET'])
        def get_analysis_history():
            """Get user's completed analysis history across all sessions (latest first, no pagination)"""
            try:
                # Get authenticated user info from global context
                user_info = g.get('user')
                if not user_info:
                    return jsonify({'error': 'Authentication required'}), 401
                
                user_email = user_info.get('email')
                if not user_email:
                    return jsonify({'error': 'User email not found'}), 401
                
                # Get job history from Firebase
                job_history = self.job_manager.data_manager.get_user_job_history(user_email, limit=50)
                
                # Transform data for frontend
                history_items = []
                for job_data in job_history:
                    try:
                        
                        # Format timestamp for display
                        created_at = job_data.get('created_at')
                        timestamp_str = "Unknown"
                        if created_at:
                            try:
                                if hasattr(created_at, 'strftime'):
                                    timestamp_str = created_at.strftime('%Y-%m-%d %H:%M:%S')
                                else:
                                    # Handle timestamp if it's already a string
                                    timestamp_str = str(created_at)
                            except:
                                timestamp_str = str(created_at)
                        
                        # Map job status to frontend-expected values
                        job_status = job_data.get('job_status', 'unknown')
                        if job_status == 'success':
                            frontend_status = 'completed'
                        elif job_status == 'failed':
                            frontend_status = 'failed'
                        elif job_status == 'running':
                            frontend_status = 'running'
                        else:
                            # Handle unknown/legacy statuses
                            frontend_status = 'failed'
                        
                        history_item = {
                            'id': job_data.get('job_id'),
                            'query': job_data.get('question', ''),
                            'timestamp': timestamp_str,
                            'status': frontend_status,
                            'reportUrl': job_data.get('report_url', ''),
                            'sessionId': job_data.get('session_id', ''),
                            'totalTokens': job_data.get('total_token_used', 0),
                            'totalCost': job_data.get('total_cost', 0.0)
                        }
                        history_items.append(history_item)
                    except Exception as e:
                        print(f"⚠️ Error processing job data: {e}")
                        continue
                
                return jsonify({
                    'history': history_items,
                    'total': len(history_items),
                    'message': f'Retrieved {len(history_items)} completed analysis records'
                })
                
            except Exception as e:
                add_log(f"Error getting analysis history: {str(e)}")
                return jsonify({'error': f'Failed to get analysis history: {str(e)}'}), 500
        
        @self.app.route('/analysis_report/<job_id>', methods=['GET'])
        def get_analysis_report(job_id):
            """Get analysis report by fetching HTML content from Firebase Storage URL"""
            try:
                # Get authenticated user info from global context
                user_info = g.get('user')
                if not user_info:
                    return jsonify({'error': 'Authentication required'}), 401
                
                user_email = user_info.get('email')
                if not user_email:
                    return jsonify({'error': 'User email not found'}), 401
                
                # Find the job in user's history
                job_history = self.job_manager.data_manager.get_user_job_history(user_email, limit=500)
                target_job = None
                
                for job_data in job_history:
                    if job_data.get('job_id') == job_id:
                        target_job = job_data
                        break
                
                if not target_job:
                    return jsonify({'error': 'Analysis report not found or access denied'}), 404
                
                report_url = target_job.get('report_url', '')
                if not report_url:
                    return jsonify({'error': 'Report URL not available'}), 404
                
                # Fetch HTML content from Firebase Storage URL
                try:
                    response = requests.get(report_url, timeout=30)
                    response.raise_for_status()
                    html_content = response.text
                    
                    return Response(html_content, mimetype='text/html')
                    
                except requests.RequestException as e:
                    print(f"❌ Failed to fetch report from URL {report_url}: {str(e)}")
                    return jsonify({'error': f'Failed to fetch report: {str(e)}'}), 500
                
            except Exception as e:
                add_log(f"Error getting analysis report: {str(e)}")
                return jsonify({'error': f'Failed to get analysis report: {str(e)}'}), 500
        
        # Backward compatibility routes
        @self.app.route('/generate_pdf', methods=['POST'])

        def generate_pdf():
            from flask import Flask, request, send_file, make_response
            from weasyprint import HTML, CSS
            import io
            
            data = request.get_json()
            html_content = data.get("html")

            # Extra CSS to override margins
            custom_css = CSS(string="""
                    @page { size: A4; margin: 10mm; }  /* Reduce big page borders */
                    body { margin: 0; padding: 0; }
                    .report-container {
                        padding-left: 0% !important;  /* Much smaller */
                        padding-right: 0% !important;
                    }
                    .visualization-container {
                        padding-top: auto !important;
                    }
                    
                """)

            pdf_file = io.BytesIO()
            HTML(string=html_content).write_pdf(pdf_file, stylesheets=[custom_css])
            pdf_file.seek(0)

            response = make_response(pdf_file.read())
            response.headers['Content-Type'] = 'application/pdf'
            response.headers['Content-Disposition'] = 'attachment; filename=report.pdf'
            return response

    def run(self, host='0.0.0.0', port=5000, debug=False):
        """Run the API server with WebSocket support"""
        # Clean up any old sessions on startup
        try:
            self.session_manager.cleanup_inactive_sessions(max_age_hours=9)  # Clean up sessions older than 1 hour
        except Exception as e:
            add_log(f"Error cleaning up old sessions on startup: {str(e)}")
        
        print(f"[API LAYER] Starting WebSocket server on {host}:{port}")
        self.socketio.run(self.app, debug=debug, host=host, port=port) 