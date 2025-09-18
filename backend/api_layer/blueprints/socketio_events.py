from flask import request
from flask_socketio import emit, join_room, leave_room


def register_socketio_events(socketio, job_manager, session_manager):
    """Register WebSocket event handlers for job progress streaming.

    This mirrors the handlers defined in ApiServer.register_socketio_events
    without changing functionality.
    """

    @socketio.on('connect')
    def handle_connect():
        print(f"[API LAYER] WebSocket client connected: {request.sid}")

    @socketio.on('disconnect')
    def handle_disconnect():
        print(f"[API LAYER] WebSocket client disconnected: {request.sid}")

    @socketio.on('execution_progress')
    def handle_execution_progress(data):
        """Forward progress events from execution layer to frontend"""
        try:
            job_id = data.get('job_id')
            if job_id:
                print(f"[API LAYER] 📡 Forwarding progress for job {job_id}: {data.get('emoji', '')} {data.get('stage', '')} - {data.get('message', '')}")
                job_info = job_manager.get_job(job_id)
                if job_info:
                    session_id = job_info.get('session_id', '')
                    if session_id:
                        room_name = f'session_{session_id}_job_{job_id}'
                        socketio.emit('job_progress', data, room=room_name)
                        print(f"[API LAYER] ✅ Progress forwarded to room: {room_name}")
                    else:
                        socketio.emit('job_progress', data, room=f'job_{job_id}')
                        print(f"[API LAYER] ✅ Progress forwarded to room: job_{job_id}")
                else:
                    print(f"[API LAYER] ⚠️  Job not found for progress event: {job_id}")
        except Exception as e:
            print(f"[API LAYER] ❌ Error forwarding execution progress: {e}")

    @socketio.on('join_job')
    def handle_join_job(data):
        job_id = data.get('job_id')
        user_email = data.get('user_email', '').lower()
        session_id = data.get('session_id', '')

        if job_id and user_email and session_id:
            if not session_manager.check_session_ownership(session_id, user_email):
                emit('join_error', {'job_id': job_id, 'error': 'Access denied: You do not own this session'})
                print(f"[API LAYER] Session access denied for user {user_email} to session {session_id}")
                return

            job_info = job_manager.get_job(job_id)
            if job_info:
                job_user_info = job_info.get('user_info', {})
                job_user_email = job_user_info.get('email', '').lower()
                job_session_id = job_info.get('session_id', '')

                if job_user_email == user_email and job_session_id == session_id:
                    room_name = f'session_{session_id}_job_{job_id}'
                    join_room(room_name)

                    # Start simple job monitoring for this job
                    # Reuse ApiServer.monitor_job_status via socket emission from here is non-trivial.
                    # To preserve behavior without cross-imports, we emit a minimal status request event
                    # that ApiServer can choose to handle, but since original code called a method,
                    # we replicate the polling here inline to avoid changing functionality.
                    def run_monitoring():
                        import time
                        try:
                            print(f"[API LAYER] 📊 Starting job status monitoring for: {job_id}")
                            while True:
                                ji = job_manager.get_job(job_id)
                                if not ji:
                                    print(f"[API LAYER] Job {job_id} not found, stopping monitoring")
                                    break
                                status = ji['status']
                                status_str = getattr(status, 'value', status)
                                status_data = {
                                    'job_id': ji['job_id'],
                                    'status': status_str,
                                    'created_at': ji['created_at'],
                                    'started_at': ji.get('started_at'),
                                    'completed_at': ji.get('completed_at'),
                                    'error': ji.get('error')
                                }
                                sid = ji.get('session_id', '')
                                if sid:
                                    room = f'session_{sid}_job_{job_id}'
                                    socketio.emit('job_status', status_data, room=room)
                                else:
                                    socketio.emit('job_status', status_data, room=f'job_{job_id}')
                                if status_str in ['completed', 'failed', 'cancelled']:
                                    print(f"[API LAYER] 🏁 Job {status_str}: {job_id} - Final status reached")
                                    if sid:
                                        room = f'session_{sid}_job_{job_id}'
                                        socketio.emit('job_complete', status_data, room=room)
                                    else:
                                        socketio.emit('job_complete', status_data, room=f'job_{job_id}')
                                    break
                                time.sleep(2)
                        except Exception as e:
                            print(f"[API LAYER] ❌ Job monitoring error for {job_id}: {str(e)}")
                            error_data = {'job_id': job_id, 'error': str(e)}
                            ji = job_manager.get_job(job_id)
                            if ji:
                                sid = ji.get('session_id', '')
                                if sid:
                                    room = f'session_{sid}_job_{job_id}'
                                    socketio.emit('job_error', error_data, room=room)
                                else:
                                    socketio.emit('job_error', error_data, room=f'job_{job_id}')
                            else:
                                socketio.emit('job_error', error_data, room=f'job_{job_id}')

                    import threading
                    threading.Thread(target=run_monitoring, daemon=True).start()

                    emit('joined_job', {'job_id': job_id, 'session_id': session_id, 'status': 'joined', 'room': room_name})
                    print(f"[API LAYER] User {user_email} joined session-aware job monitoring: {job_id} in session {session_id}")
                else:
                    emit('join_error', {'job_id': job_id, 'error': 'Access denied: Job not found in your session'})
                    print(f"[API LAYER] Job access denied for user {user_email} to job {job_id}")
            else:
                emit('join_error', {'job_id': job_id, 'error': 'Job not found'})
        else:
            emit('join_error', {'error': 'Missing job_id, user_email, or session_id'})

    @socketio.on('leave_job')
    def handle_leave_job(data):
        job_id = data.get('job_id')
        user_email = data.get('user_email', '').lower()
        session_id = data.get('session_id', '')

        if job_id and user_email and session_id:
            room_name = f'session_{session_id}_job_{job_id}'
            leave_room(room_name)
            emit('left_job', {'job_id': job_id, 'session_id': session_id, 'status': 'left', 'room': room_name})
            print(f"[API LAYER] User {user_email} left session-aware job monitoring: {job_id} in session {session_id}")

    @socketio.on('join_job_logs')
    def handle_join_job_logs(data):
        job_id = data.get('job_id')
        user_email = data.get('user_email', '').lower()
        session_id = data.get('session_id', '')

        if job_id and user_email and session_id:
            if not session_manager.check_session_ownership(session_id, user_email):
                emit('join_logs_error', {'job_id': job_id, 'error': 'Access denied: You do not own this session'})
                print(f"[API LAYER] Log session access denied for user {user_email} to session {session_id}")
                return

            job_info = job_manager.get_job(job_id)
            if job_info:
                job_user_info = job_info.get('user_info', {})
                job_user_email = job_user_info.get('email', '').lower()
                job_session_id = job_info.get('session_id', '')

                if job_user_email == user_email and job_session_id == session_id:
                    log_room_name = f'job_logs_{job_id}'
                    join_room(log_room_name)

                    from logger import get_job_logs
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

    @socketio.on('leave_job_logs')
    def handle_leave_job_logs(data):
        job_id = data.get('job_id')
        user_email = data.get('user_email', '').lower()
        if job_id and user_email:
            log_room_name = f'job_logs_{job_id}'
            leave_room(log_room_name)
            emit('left_job_logs', {'job_id': job_id, 'status': 'left', 'room': log_room_name})
            print(f"[API LAYER] User {user_email} left job log streaming: {job_id}")


