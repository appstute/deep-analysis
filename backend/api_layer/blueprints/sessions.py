from flask import Blueprint, current_app, request, jsonify, Response, g
import os
import time
import requests
from logger import add_log, get_job_logs
from ..job_manager import JobStatus


sessions_bp = Blueprint('sessions_bp', __name__)


def _check_session_has_input_data(session_id: str) -> bool:
    try:
        input_data_dir = os.path.join('execution_layer', 'input_data', session_id)
        if not os.path.exists(input_data_dir):
            return False
        files = [f for f in os.listdir(input_data_dir) if os.path.isfile(os.path.join(input_data_dir, f))]
        return len(files) > 0
    except Exception as e:
        add_log(f"Error checking input data for session {session_id}: {str(e)}")
        return False


@sessions_bp.route('/session_id')
def session_id():
    try:
        token_payload = g.get('user', {})
        session_manager = current_app.session_manager
        session_id, container_id = session_manager.create_session(user_info=token_payload)
        add_log(f"Session created: {session_id} with container: {container_id[:12]} for user: {token_payload.get('email', 'unknown')}")
        return jsonify({'session_id': session_id, 'container_id': container_id, 'status': 'success'})
    except Exception as e:
        add_log(f"Error creating session: {str(e)}")
        return jsonify({'error': f'Failed to create session: {str(e)}', 'status': 'error'}), 500


@sessions_bp.route('/validate_session/<session_id>')
def validate_session(session_id):
    try:
        session_manager = current_app.session_manager
        http = current_app.requests_session
        session_info = session_manager.get_session_container(session_id)
        if session_info:
            has_input_data = _check_session_has_input_data(session_id)
            container_port = session_info.get('container_port')
            if container_port:
                try:
                    resp = http.get(f"http://localhost:{container_port}/health", timeout=5)
                    if resp.status_code == 200:
                        return jsonify({'session_id': session_id, 'container_id': session_info['container_id'], 'status': 'active', 'valid': True, 'has_input_data': has_input_data})
                except requests.RequestException as e:
                    add_log(f"Container for session {session_id} is not responding: {str(e)}")
            return jsonify({'session_id': session_id, 'container_id': session_info['container_id'], 'status': 'active', 'valid': True, 'has_input_data': has_input_data})
        else:
            has_input_data = _check_session_has_input_data(session_id)
            add_log(f"Session {session_id} validation failed - not found or inactive")
            return jsonify({'session_id': session_id, 'status': 'not_found', 'valid': False, 'has_input_data': has_input_data})
    except Exception as e:
        add_log(f"Error validating session {session_id}: {str(e)}")
        return jsonify({'error': f'Failed to validate session: {str(e)}', 'status': 'error', 'valid': False, 'has_input_data': False}), 500


@sessions_bp.route('/session_status/<session_id>')
def session_status(session_id):
    try:
        status = current_app.session_manager.get_session_status(session_id)
        return jsonify(status)
    except Exception as e:
        add_log(f"Error getting session status: {str(e)}")
        return jsonify({'error': f'Failed to get session status: {str(e)}', 'status': 'error'}), 500


@sessions_bp.route('/restart_session/<session_id>', methods=['POST'])
def restart_user_session(session_id):
    try:
        success = current_app.session_manager.restart_session(session_id)
        if success:
            return jsonify({'message': f'Session {session_id} restarted successfully', 'status': 'success'})
        else:
            return jsonify({'error': f'Failed to restart session {session_id}', 'status': 'error'}), 404
    except Exception as e:
        add_log(f"Error restarting session: {str(e)}")
        return jsonify({'error': f'Failed to restart session: {str(e)}', 'status': 'error'}), 500


@sessions_bp.route('/cleanup_session/<session_id>', methods=['POST'])
def cleanup_session(session_id):
    try:
        success = current_app.session_manager.cleanup_session(session_id)
        if success:
            return jsonify({'message': f'Session {session_id} cleaned up successfully', 'status': 'success'})
        else:
            return jsonify({'error': f'Failed to cleanup session {session_id}', 'status': 'error'}), 404
    except Exception as e:
        add_log(f"Error cleaning up session: {str(e)}")
        return jsonify({'error': f'Failed to cleanup session: {str(e)}', 'status': 'error'}), 500


@sessions_bp.route('/create_job', methods=['POST'])
def create_job():
    token_payload = g.get('user', {})
    data = request.get_json()
    if not data or 'query' not in data:
        add_log("Error: Missing analysis query")
        return jsonify({'error': 'Missing analysis query'}), 400

    session_id = data.get('session_id')
    if not session_id:
        add_log("Error: Missing session ID")
        return jsonify({'error': 'Missing session ID'}), 400

    session_info = current_app.session_manager.get_session_container(session_id)
    if not session_info:
        add_log(f"Error: Invalid or inactive session: {session_id}")
        return jsonify({'error': f'Invalid or inactive session: {session_id}'}), 400

    user_query = data['query']
    model_name = data.get('model', "gpt-4.1-mini")

    try:
        job_id, job_info = current_app.job_manager.create_job(
            session_id=session_id,
            query=user_query,
            model=model_name,
            session_info=session_info,
            user_info=token_payload
        )

        success = current_app.job_manager.start_job_execution(job_id, current_app.session_manager)
        if not success:
            return jsonify({'error': 'Failed to start job execution'}), 500

        response_data = {'status': 'success', 'job_id': job_id, 'message': 'Job created and started successfully'}
        print(f"[API LAYER] ✅ Job created and started: {job_id} - Query: {user_query[:50]}...")
        return jsonify(response_data)
    except Exception as e:
        error_msg = f"Job creation failed: {str(e)}"
        add_log(error_msg)
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@sessions_bp.route('/job_status/<job_id>')
def get_job_status(job_id):
    try:
        job_info = current_app.job_manager.get_job(job_id)
        if not job_info:
            return jsonify({'error': 'Job not found'}), 404
        status = job_info['status']
        status_str = getattr(status, 'value', status)
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


@sessions_bp.route('/job_report/<job_id>')
def get_job_report(job_id):
    try:
        job_info = current_app.job_manager.get_job(job_id)
        if not job_info:
            return jsonify({'error': 'Job not found'}), 404
        status = job_info['status']
        status_str = getattr(status, 'value', status)
        if status_str != 'completed':
            return jsonify({'error': f'Job is not completed. Current status: {status_str}'}), 400
        report_path = current_app.job_manager.get_job_report_path(job_id)
        if not report_path:
            return jsonify({'error': 'Report not found'}), 404
        with open(report_path, 'r', encoding='utf-8') as f:
            html = f.read()
        return Response(html, mimetype='text/html')
    except Exception as e:
        return jsonify({'error': f'Failed to read report: {str(e)}'}), 500


@sessions_bp.route('/analysis_history', methods=['GET'])
def get_analysis_history():
    try:
        user_info = g.get('user')
        if not user_info:
            return jsonify({'error': 'Authentication required'}), 401
        user_email = user_info.get('email')
        if not user_email:
            return jsonify({'error': 'User email not found'}), 401
        job_history = current_app.job_manager.data_manager.get_user_job_history(user_email, limit=50)
        history_items = []
        for job_data in job_history:
            try:
                created_at = job_data.get('created_at')
                timestamp_str = "Unknown"
                if created_at:
                    try:
                        if hasattr(created_at, 'strftime'):
                            timestamp_str = created_at.strftime('%Y-%m-%d %H:%M:%S')
                        else:
                            timestamp_str = str(created_at)
                    except:
                        timestamp_str = str(created_at)
                job_status = job_data.get('job_status', 'unknown')
                if job_status == 'success':
                    frontend_status = 'completed'
                elif job_status == 'failed':
                    frontend_status = 'failed'
                elif job_status == 'running':
                    frontend_status = 'running'
                else:
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
        return jsonify({'history': history_items, 'total': len(history_items), 'message': f'Retrieved {len(history_items)} completed analysis records'})
    except Exception as e:
        add_log(f"Error getting analysis history: {str(e)}")
        return jsonify({'error': f'Failed to get analysis history: {str(e)}'}), 500


@sessions_bp.route('/analysis_report/<job_id>', methods=['GET'])
def get_analysis_report(job_id):
    try:
        user_info = g.get('user')
        if not user_info:
            return jsonify({'error': 'Authentication required'}), 401
        user_email = user_info.get('email')
        if not user_email:
            return jsonify({'error': 'User email not found'}), 401
        job_history = current_app.job_manager.data_manager.get_user_job_history(user_email, limit=500)
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


