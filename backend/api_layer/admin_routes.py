from flask import Blueprint, request, jsonify, g
from functools import wraps

admin_bp = Blueprint('admin', __name__, url_prefix='/api')

def get_firebase_user_manager():
    """Get Firebase user manager from current app"""
    from flask import current_app
    if hasattr(current_app, 'firebase_user_manager'):
        return current_app.firebase_user_manager
    return None

def admin_required(f):
    """Decorator to require admin role for endpoints"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = getattr(g, 'user', None)
        if not user:
            return jsonify({'error': 'Authentication required'}), 401
        
        if user.get('role') != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
            
        return f(*args, **kwargs)
    return decorated_function



@admin_bp.route('/users', methods=['GET'])
@admin_required
def get_all_users():
    """Get all users (admin only)"""
    try:
        firebase_user_manager = get_firebase_user_manager()
        
        if not firebase_user_manager or not firebase_user_manager.db:
            return jsonify({
                'success': False,
                'error': 'Firebase not available'
            }), 500
        
        users_data = firebase_user_manager.get_all_users()
        
        return jsonify({
            'success': True,
            'users': users_data
        }), 200
        
    except Exception as e:
        print(f"❌ Error fetching users: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Failed to fetch users'
        }), 500

@admin_bp.route('/users/<email>', methods=['GET'])
@admin_required
def get_user_by_email(email):
    """Get specific user by email (admin only)"""
    try:
        firebase_user_manager = get_firebase_user_manager()
        
        if not firebase_user_manager or not firebase_user_manager.db:
            return jsonify({
                'success': False,
                'error': 'Firebase not available'
            }), 500
        
        user_data = firebase_user_manager.get_user_by_email(email)
        if user_data:
            return jsonify({
                'success': True,
                'user': user_data
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': 'User not found'
            }), 404
                
    except Exception as e:
        print(f"❌ Error fetching user {email}: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Failed to fetch user'
        }), 500

@admin_bp.route('/users', methods=['POST'])
@admin_required
def create_user():
    """Create new user (admin only)"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['email', 'name', 'role', 'issued_token']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'Missing required field: {field}'
                }), 400
        
        firebase_user_manager = get_firebase_user_manager()
        
        if not firebase_user_manager or not firebase_user_manager.db:
            return jsonify({
                'success': False,
                'error': 'Firebase not available'
            }), 500
        
        # Check if user already exists
        if firebase_user_manager.is_user_authorized(data['email']):
            return jsonify({
                'success': False,
                'error': 'User already exists'
            }), 409
        
        # Add user to Firestore
        success = firebase_user_manager.add_user_email(data['email'])
        if success:
            # Update user with additional data
            updates = {
                'name': data['name'],
                'role': data['role'],
                'issued_token': data['issued_token'],
                'used_token': 0,
                'report_count': 0
            }
            firebase_user_manager.update_user(data['email'], updates)
            
            return jsonify({
                'success': True,
                'message': 'User created successfully'
            }), 201
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to create user'
            }), 500
            
    except Exception as e:
        print(f"❌ Error creating user: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Failed to create user'
        }), 500

@admin_bp.route('/users/<email>', methods=['PUT'])
@admin_required
def update_user(email):
    """Update user (admin only)"""
    try:
        data = request.get_json()
        
        firebase_user_manager = get_firebase_user_manager()
        
        if not firebase_user_manager or not firebase_user_manager.db:
            return jsonify({
                'success': False,
                'error': 'Firebase not available'
            }), 500
        
        # Check if user exists
        existing_user = firebase_user_manager.get_user_by_email(email)
        if not existing_user:
            return jsonify({
                'success': False,
                'error': 'User not found'
            }), 404
        
        # Update user
        success = firebase_user_manager.update_user(email, data)
        if success:
            return jsonify({
                'success': True,
                'message': 'User updated successfully'
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to update user'
            }), 500
                
    except Exception as e:
        print(f"❌ Error updating user {email}: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Failed to update user'
        }), 500

@admin_bp.route('/users/<email>', methods=['DELETE'])
@admin_required
def delete_user(email):
    """Delete user (admin only)"""
    try:
        firebase_user_manager = get_firebase_user_manager()
        
        if not firebase_user_manager or not firebase_user_manager.db:
            return jsonify({
                'success': False,
                'error': 'Firebase not available'
            }), 500
        
        # Check if user exists
        existing_user = firebase_user_manager.get_user_by_email(email)
        if not existing_user:
            return jsonify({
                'success': False,
                'error': 'User not found'
            }), 404
        
        # Delete user
        success = firebase_user_manager.delete_user(email)
        if success:
            return jsonify({
                'success': True,
                'message': 'User deleted successfully'
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to delete user'
            }), 500
                
    except Exception as e:
        print(f"❌ Error deleting user {email}: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Failed to delete user'
        }), 500

@admin_bp.route('/profile', methods=['GET'])
def get_current_user_profile():
    """Get current user's profile with role information"""
    try:
        user = getattr(g, 'user', None)
        if not user:
            return jsonify({'error': 'Authentication required'}), 401
        
        user_email = user.get('email')
        firebase_user_manager = get_firebase_user_manager()
        
        if not firebase_user_manager or not firebase_user_manager.db:
            return jsonify({
                'success': False,
                'error': 'Firebase not available'
            }), 500
        
        user_data = firebase_user_manager.get_user_by_email(user_email)
        if user_data:
            return jsonify({
                'success': True,
                'user': user_data
            }), 200
        else:
            # Create user if doesn't exist (first time login)
            success = firebase_user_manager.add_user_email(user_email)
            if success:
                # Update with additional data
                updates = {
                    'name': user.get('name', 'Unknown'),
                    'role': 'user',  # Default role
                    'used_token': 0,
                    'issued_token': 1000,  # Default allocation
                    'report_count': 0
                }
                firebase_user_manager.update_user(user_email, updates)
                
                user_data = firebase_user_manager.get_user_by_email(user_email)
                return jsonify({
                    'success': True,
                    'user': user_data
                }), 200
            else:
                return jsonify({
                    'success': False,
                    'error': 'Failed to create user profile'
                }), 500
                
    except Exception as e:
        print(f"❌ Error fetching user profile: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Failed to fetch user profile'
        }), 500

@admin_bp.route('/admin/stats', methods=['GET'])
@admin_required
def get_admin_stats():
    """Get admin dashboard statistics"""
    try:
        firebase_user_manager = get_firebase_user_manager()
        
        if not firebase_user_manager or not firebase_user_manager.db:
            return jsonify({
                'success': False,
                'error': 'Firebase not available'
            }), 500
        
        # Get all users from Firestore
        users = firebase_user_manager.get_all_users()
        
        stats = {
            'total_users': len(users),
            'total_reports': sum(user.get('report_count', 0) for user in users),
            'total_tokens_used': sum(user.get('used_token', 0) for user in users),
            'active_users': len([user for user in users if user.get('report_count', 0) > 0])
        }
        
        return jsonify({
            'success': True,
            'stats': stats
        }), 200
        
    except Exception as e:
        print(f"❌ Error fetching admin stats: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Failed to fetch statistics'
        }), 500



@admin_bp.route('/users/<email>/add-tokens', methods=['POST'])
@admin_required
def add_tokens_to_user(email):
    """Add tokens to user's existing token allocation (admin only)"""
    try:
        data = request.get_json()
        user = getattr(g, 'user', None)
        
        # Validate required fields
        if 'tokens_to_add' not in data:
            return jsonify({
                'success': False,
                'error': 'Missing required field: tokens_to_add'
            }), 400
        
        tokens_to_add = data.get('tokens_to_add', 0)
        if not isinstance(tokens_to_add, (int, float)) or tokens_to_add <= 0:
            return jsonify({
                'success': False,
                'error': 'tokens_to_add must be a positive number'
            }), 400
        
        reason = data.get('reason', '')  # Optional reason
        added_by = user.get('email') if user else 'system'
        
        firebase_user_manager = get_firebase_user_manager()
        
        if not firebase_user_manager or not firebase_user_manager.db:
            return jsonify({
                'success': False,
                'error': 'Firebase not available'
            }), 500
        
        # Check if user exists
        existing_user = firebase_user_manager.get_user_by_email(email)
        if not existing_user:
            return jsonify({
                'success': False,
                'error': 'User not found'
            }), 404
        
        # Add tokens with history tracking
        result = firebase_user_manager.add_tokens_with_history(
            user_email=email,
            tokens_to_add=int(tokens_to_add),
            added_by=added_by,
            reason=reason if reason else None
        )
        
        if result['success']:
            return jsonify({
                'success': True,
                'message': f'Added {tokens_to_add} tokens to user',
                'previous_tokens': result['previous_tokens'],
                'new_total': result['new_total'],
                'history_created': result.get('history_created', False)
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': result.get('error', 'Failed to add tokens')
            }), 500
                
    except Exception as e:
        print(f"❌ Error adding tokens to user {email}: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Failed to add tokens'
        }), 500

@admin_bp.route('/users/<email>/token-history', methods=['GET'])
@admin_required
def get_user_token_history(email):
    """Get token history for a specific user (admin only)"""
    try:
        # Get optional limit parameter
        limit = request.args.get('limit', 50, type=int)
        if limit < 1 or limit > 100:
            limit = 50  # Default safe limit
        
        firebase_user_manager = get_firebase_user_manager()
        
        if not firebase_user_manager or not firebase_user_manager.db:
            return jsonify({
                'success': False,
                'error': 'Firebase not available'
            }), 500
        
        # Check if user exists
        existing_user = firebase_user_manager.get_user_by_email(email)
        if not existing_user:
            return jsonify({
                'success': False,
                'error': 'User not found'
            }), 404
        
        # Get token history
        history_records = firebase_user_manager.get_user_token_history(email, limit)
        
        return jsonify({
            'success': True,
            'history': history_records,
            'total_records': len(history_records)
        }), 200
        
    except Exception as e:
        print(f"❌ Error fetching token history for user {email}: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Failed to fetch token history'
        }), 500

@admin_bp.route('/admin/health', methods=['GET'])
@admin_required
def admin_health_check():
    """Admin health check endpoint"""
    firebase_user_manager = get_firebase_user_manager()
    firebase_available = firebase_user_manager and firebase_user_manager.db
    
    return jsonify({
        'status': 'healthy',
        'firebase_available': firebase_available
    }), 200
