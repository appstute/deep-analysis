"""
Firebase User Manager
Handles user authentication and authorization using Firebase Firestore
"""

import os
import firebase_admin
from firebase_admin import credentials, firestore
from typing import List, Dict, Any, Optional


class FirebaseUserManager:
    """User Management using Firestore"""
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(FirebaseUserManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self.db = None
            self.collection_name = 'userCollection'
            self.initialize_firebase()
            FirebaseUserManager._initialized = True 
    
    def initialize_firebase(self):
        """Initialize Firebase Admin SDK"""
        try:
            # Check if Firebase is already initialized
            if not firebase_admin._apps:
                # Get the service account key file path
                config_dir = os.path.join(os.path.dirname(__file__), 'config')
                service_account_path = os.path.join(config_dir, 'insightbot-467305-firebase-adminsdk-fbsvc-7a3d9adf09.json')
                
                if os.path.exists(service_account_path):
                    # Initialize Firebase Admin SDK
                    cred = credentials.Certificate(service_account_path)
                    firebase_admin.initialize_app(cred)
                    print("Firebase Admin SDK initialized successfully")
                else:
                    print(f"Firebase service account file not found: {service_account_path}")
                    return False
            
            # Initialize Firestore client
            self.db = firestore.client()
            print("Firestore client initialized successfully")
            return True
            
        except Exception as e:
            print(f"❌ Failed to initialize Firebase: {str(e)}")
            print("   Please ensure Firebase service account file is properly configured")
            self.db = None
            return False
    
    def add_user_email(self, email: str) -> bool:
        """Add a user email to authorized users collection"""
        try:
            if not self.db:
                print("❌ Firestore client not initialized")
                return False
            
            email = email.lower().strip()
            
            # Check if user already exists
            if self.is_user_authorized(email):
                print(f"✅ User {email} already exists in authorized users")
                return True
            
            # Add user to Firestore
            user_doc = {
                'email': email,
                'role': 'user',  # Default role
                'created_at': firestore.SERVER_TIMESTAMP,
                'updated_at': firestore.SERVER_TIMESTAMP,
                'status': 'active'
            }
            
            self.db.collection(self.collection_name).document(email).set(user_doc)
            print(f"✅ User {email} added to authorized users in Firestore")
            return True
            
        except Exception as e:
            print(f"❌ Failed to add user {email} to Firestore: {str(e)}")
            return False
    
    def is_user_authorized(self, email: str) -> bool:
        """Check if user email is in authorized users"""
        try:
            if not self.db:
                return False
            
            email = email.lower().strip()
            doc_ref = self.db.collection(self.collection_name).document(email)
            doc = doc_ref.get()
            
            if doc.exists:
                user_data = doc.to_dict()
                return user_data.get('status', 'active') == 'active'
            
            return False
            
        except Exception as e:
            print(f"Failed to check user authorization for {email}: {str(e)}")
            return False
    
    def get_all_users(self) -> List[Dict[str, Any]]:
        """Get all authorized users"""
        try:
            if not self.db:
                return []
            
            users = []
            docs = self.db.collection(self.collection_name).stream()
            
            for doc in docs:
                user_data = doc.to_dict()
                user_data['id'] = doc.id
                # Convert timestamps to ISO format for JSON serialization
                if 'created_at' in user_data and user_data['created_at']:
                    user_data['created_at'] = user_data['created_at'].isoformat()
                if 'updated_at' in user_data and user_data['updated_at']:
                    user_data['updated_at'] = user_data['updated_at'].isoformat()
                users.append(user_data)
            
            return users
            
        except Exception as e:
            print(f"Failed to get all users: {str(e)}")
            return []
    
    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Get user data by email"""
        try:
            if not self.db:
                return None
            
            email = email.lower().strip()
            doc_ref = self.db.collection(self.collection_name).document(email)
            doc = doc_ref.get()
            
            if doc.exists:
                user_data = doc.to_dict()
                user_data['id'] = doc.id
                # Convert timestamps to ISO format
                if 'created_at' in user_data and user_data['created_at']:
                    user_data['created_at'] = user_data['created_at'].isoformat()
                if 'updated_at' in user_data and user_data['updated_at']:
                    user_data['updated_at'] = user_data['updated_at'].isoformat()
                return user_data
            
            return None
            
        except Exception as e:
            print(f"Failed to get user {email}: {str(e)}")
            return None
    
    def update_user(self, email: str, updates: Dict[str, Any]) -> bool:
        """Update user data"""
        try:
            if not self.db:
                return False
            
            email = email.lower().strip()
            updates['updated_at'] = firestore.SERVER_TIMESTAMP
            
            doc_ref = self.db.collection(self.collection_name).document(email)
            doc_ref.update(updates)
            
            print(f"User {email} updated successfully in Firestore")
            return True
            
        except Exception as e:
            print(f"Failed to update user {email}: {str(e)}")
            return False
    
    def delete_user(self, email: str) -> bool:
        """Delete user from authorized users"""
        try:
            if not self.db:
                return False
            
            email = email.lower().strip()
            doc_ref = self.db.collection(self.collection_name).document(email)
            doc_ref.delete()
            
            print(f"User {email} deleted successfully from Firestore")
            return True
            
        except Exception as e:
            print(f"Failed to delete user {email}: {str(e)}")
            return False
    
    def get_user_role(self, email: str) -> str:
        """Get user role (default: 'user')"""
        try:
            user_data = self.get_user_by_email(email)
            if user_data:
                return user_data.get('role', 'user')
            return 'user'
        except Exception as e:
            print(f"Failed to get user role for {email}: {str(e)}")
            return 'user'
    
    def get_authorized_emails(self) -> List[str]:
        """Get list of all authorized email addresses"""
        try:
            users = self.get_all_users()
            return [user['email'] for user in users if user.get('status', 'active') == 'active']
        except Exception as e:
            print(f"Failed to get authorized emails: {str(e)}")
            return []
    
    def clear_all_users(self) -> bool:
        """Delete all users (use with caution!)"""
        try:
            if not self.db:
                return False
            
            # Get all documents
            docs = self.db.collection(self.collection_name).stream()
            
            # Delete each document
            for doc in docs:
                doc.reference.delete()
            
            print("All users cleared from authorized users collection")
            return True
            
        except Exception as e:
            print(f"Failed to clear all users: {str(e)}")
            return False
    
    def add_tokens_with_history(self, user_email: str, tokens_to_add: int, added_by: str, reason: str = None) -> Dict[str, Any]:
        """
        Add tokens to user and create history record using FirebaseDataManager
        
        Args:
            user_email: User's email address
            tokens_to_add: Number of tokens to add
            added_by: Admin email who is adding the tokens
            reason: Optional reason for token addition
            
        Returns:
            Dictionary with success status and details
        """
        try:
            from .firebase_data_models import get_data_manager
            data_manager = get_data_manager()
            
            result = data_manager.add_tokens_with_history(
                user_email=user_email,
                tokens_to_add=tokens_to_add,
                added_by=added_by,
                reason=reason
            )
            
            return result
            
        except Exception as e:
            print(f"❌ Failed to add tokens with history for {user_email}: {str(e)}")
            return {
                'success': False,
                'error': 'Failed to add tokens'
            }
    
    def get_user_token_history(self, user_email: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get token history for a user
        
        Args:
            user_email: User's email address
            limit: Maximum number of history records to return
            
        Returns:
            List of token history records as dictionaries
        """
        try:
            from .firebase_data_models import get_data_manager
            data_manager = get_data_manager()
            
            history_records = data_manager.get_user_token_history(user_email, limit)
            
            # Convert to dictionaries for JSON serialization
            history_dicts = []
            for record in history_records:
                record_dict = record.to_dict()
                # Convert datetime to ISO format for JSON
                if record_dict.get('created_at'):
                    record_dict['created_at'] = record_dict['created_at'].isoformat()
                history_dicts.append(record_dict)
            
            return history_dicts
            
        except Exception as e:
            print(f"❌ Failed to get token history for {user_email}: {str(e)}")
            return []


# Global instance for easy access
firebase_user_manager = FirebaseUserManager()


def get_firebase_user_manager() -> FirebaseUserManager:
    """Get Firebase User Manager instance"""
    return firebase_user_manager
