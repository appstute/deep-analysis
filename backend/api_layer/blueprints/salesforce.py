from flask import Blueprint, request, jsonify, current_app, g
import os
import json
import re
import requests
from typing import Dict, Any, List
from google.cloud import secretmanager
from google.api_core.exceptions import NotFound, AlreadyExists, PermissionDenied
from google.oauth2 import service_account

salesforce_bp = Blueprint('salesforce_bp', __name__)


def _validate_non_empty_string(value: Any, field: str, min_len: int = 8) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    trimmed = value.strip()
    if not trimmed:
        raise ValueError(f"{field} is required")
    if len(trimmed) < min_len:
        raise ValueError(f"{field} must be at least {min_len} characters")
    return trimmed


def _sanitize_secret_id_component(text: str) -> str:
    """Sanitize user-provided text (e.g., email) for Secret Manager ID component."""
    component = (text or '').strip().lower()
    component = re.sub(r'[^a-z0-9_-]+', '-', component)
    component = component.strip('-_') or 'user'
    # Keep it reasonably short to leave room for suffix
    return component[:128]


def _store_secret_in_gcp(secret_id: str, payload: Dict[str, Any]) -> None:
    """Create or update a secret in Google Secret Manager with JSON payload."""
    try:
        # Try env vars first
        project_id = os.getenv('GCP_PROJECT') or os.getenv('GOOGLE_CLOUD_PROJECT')
        credentials_obj = None

        # Fallback to Firebase service account JSON in api_layer/config if project not set
        if not project_id:
            config_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'config'))
            service_key_path = None
            try:
                if os.path.isdir(config_dir):
                    for fname in os.listdir(config_dir):
                        if fname.endswith('.json'):
                            service_key_path = os.path.join(config_dir, fname)
                            break
            except Exception:
                service_key_path = None

            if service_key_path and os.path.exists(service_key_path):
                try:
                    credentials_obj = service_account.Credentials.from_service_account_file(service_key_path)
                    try:
                        with open(service_key_path, 'r', encoding='utf-8') as f:
                            info = json.load(f)
                            project_id = info.get('project_id') or project_id
                    except Exception:
                        pass
                except Exception as ce:
                    raise RuntimeError(f"Failed to load service account JSON: {str(ce)}")

        if not project_id:
            raise RuntimeError("GCP project not configured. Set GCP_PROJECT or GOOGLE_CLOUD_PROJECT env var.")

        client = secretmanager.SecretManagerServiceClient(credentials=credentials_obj) if credentials_obj else secretmanager.SecretManagerServiceClient()

        parent = f"projects/{project_id}"
        secret_name = f"projects/{project_id}/secrets/{secret_id}"

        # Ensure secret exists without requiring secrets.get (avoid 403 on get)
        try:
            client.create_secret(
                parent=parent,
                secret_id=secret_id,
                secret={"replication": {"automatic": {}}},
            )
        except AlreadyExists:
            pass
        except PermissionDenied:
            # If we can add versions but not create or get, continue; add_version may still succeed
            pass

        # Add new version
        payload_bytes = json.dumps(payload).encode('utf-8')
        client.add_secret_version(
            parent=secret_name,
            payload={"data": payload_bytes},
        )
    except Exception as e:
        raise RuntimeError(f"Failed to store secret: {str(e)}")


@salesforce_bp.route('/salesforce/save_credentials', methods=['POST'])
def save_salesforce_credentials():
    try:
        data = request.get_json(silent=True) or {}

        user_email = _validate_non_empty_string(data.get('user_email'), 'user_email', min_len=3)
        client_id = _validate_non_empty_string(data.get('client_id'), 'client_id')
        client_secret = _validate_non_empty_string(data.get('client_secret'), 'client_secret')
        username = _validate_non_empty_string(data.get('username'), 'username')
        password = _validate_non_empty_string(data.get('password'), 'password')
    
        secret_payload = {
            'client_id': client_id,
            'client_secret': client_secret,
            'username': username,
            'password': password,
        }
        print("secret_payload", secret_payload)
        # Secret name format: <sanitized_user_email>_salesforce
        secret_id = f"{_sanitize_secret_id_component(user_email)}_salesforce"
        print("secret_id", secret_id)
        _store_secret_in_gcp(secret_id, secret_payload)

        return jsonify({'message': 'Credentials saved to Secret Manager', 'secret_id': secret_id}), 200
    except ValueError as ve:
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        return jsonify({'error': f'Failed to save credentials: {str(e)}'}), 500


def _download_pickle_files_from_firebase(user_email: str, target_dir: str) -> List[str]:
    """Download all pickle files from Firebase Storage path <user_email>/data/salesforce into target_dir.

    Note: Using Firebase Admin Storage SDK listing would be ideal, but if not configured,
    attempt HTTPS download for known .pkl files when an index is provided by a Cloud Function.
    """
    os.makedirs(target_dir, exist_ok=True)
    saved_files: List[str] = []

    try:
        # We expect the Cloud Function to have created files and possibly returned their names.
        # As a fallback, list using firebase_admin if available.
        try:
            import firebase_admin
            from firebase_admin import storage
            if not firebase_admin._apps:
                # If Firebase not initialized elsewhere, attempt default init via env
                raise Exception('Firebase not initialized')
            bucket = storage.bucket()
            prefix = f"{user_email}/data/salesforce/"
            # List blobs under the prefix
            blobs = list(bucket.list_blobs(prefix=prefix))
            for blob in blobs:
                if blob.name.lower().endswith('.pkl'):
                    local_path = os.path.join(target_dir, os.path.basename(blob.name))
                    blob.download_to_filename(local_path)
                    saved_files.append(local_path)
            return saved_files
        except Exception:
            # Fallback path: rely on known Firebase Hosting URL pattern - requires exact filenames
            # Without list capability, we can't discover files reliably; skip in fallback
            return saved_files
    except Exception as e:
        raise RuntimeError(f"Failed to download pickle files: {str(e)}")


@salesforce_bp.route('/salesforce/import_user_data', methods=['POST'])
def import_salesforce_user_data():
    try:
        data = request.get_json(silent=True) or {}
        user_email = _validate_non_empty_string(data.get('user_email'), 'user_email', min_len=3)
        session_id = _validate_non_empty_string(data.get('session_id'), 'session_id', min_len=8)

        # Call Cloud Function to prepare/export data for this user
        fn_url = 'https://us-central1-insightbot-467305.cloudfunctions.net/zingworks_salesforce_connector'
        try:
            resp = requests.post(fn_url, json={'user_email': user_email}, timeout=60)
            # Do not hard-fail on non-200, but capture message
            cf_message = resp.text
        except Exception as e:
            cf_message = f"Cloud Function call failed: {str(e)}"

        # Target directory inside this backend for the session
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        input_data_dir = os.path.join(base_dir, 'execution_layer', 'input_data', session_id)
        os.makedirs(input_data_dir, exist_ok=True)

        saved_files = _download_pickle_files_from_firebase(user_email=user_email, target_dir=input_data_dir)

        return jsonify({
            'message': 'Import completed',
            'cloud_function_response': cf_message,
            'saved_files': [os.path.basename(p) for p in saved_files],
            'target_dir': input_data_dir,
        }), 200
    except ValueError as ve:
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        return jsonify({'error': f'Failed to import user data: {str(e)}'}), 500


