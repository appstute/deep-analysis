from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any, List
from datetime import datetime
from .firebase_config import get_firebase_crud
import uuid


@dataclass
class JobDocument:
    """
    Data model for Job Document
    
    Path: userCollection/{userEmailID}/{session_ID}/{job_ID}
    """
    job_id: str
    created_at: datetime
    logs_url: str
    report_url: str
    total_token_used: int
    total_cost: float
    question: str
    job_status: str  # "success" or "failed"
    updated_at: Optional[datetime] = None  # Handle Firebase auto-added field
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for Firebase storage"""
        data = asdict(self)
        data['created_at'] = self.created_at
        if self.updated_at:
            data['updated_at'] = self.updated_at
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'JobDocument':
        """Create JobDocument from Firebase data with field validation"""
        # Define allowed fields for JobDocument
        allowed_fields = {
            'job_id', 'created_at', 
            'logs_url', 'report_url', 'total_token_used', 'total_cost', 
            'question', 'job_status', 'updated_at'
        }
        
        # Clean and fix the data
        clean_data = {}
        for key, value in data.items():
            # Handle field name typos and variations
            if key == 'updatted_at':  # Common typo
                key = 'updated_at'
            elif key == 'updatedat':  # Another variation
                key = 'updated_at'
            elif key == 'id':  # Skip Firebase auto-added id
                continue
                
            # Only include allowed fields
            if key in allowed_fields:
                clean_data[key] = value
        
        # Provide minimal defaults only for optional fields
        # Note: Required fields should already be validated before reaching this method
        defaults = {
            'logs_url': '',
            'report_url': '',
            'total_token_used': 0,
            'total_cost': 0.0,
            'updated_at': None
        }
        
        # Apply defaults only for optional fields
        for field_name, default_value in defaults.items():
            if field_name not in clean_data:
                clean_data[field_name] = default_value
        
        return cls(**clean_data)


@dataclass
class UserDocument:
    """
    Data model for User Document
    
    Path: userCollection/{userEmailID}
    """
    email: str
    name: str
    role: str
    used_token: int
    issued_token: int
    report_count: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for Firebase storage"""
        data = asdict(self)
        if self.created_at:
            data['created_at'] = self.created_at
        if self.updated_at:
            data['updated_at'] = self.updated_at
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UserDocument':
        """Create UserDocument from Firebase data with field validation"""
        # Define allowed fields for UserDocument
        allowed_fields = {
            'email', 'name', 'role', 'used_token', 'issued_token', 
            'report_count', 'created_at', 'updated_at'
        }
        
        # Clean and fix the data
        clean_data = {}
        for key, value in data.items():
            # Handle field name typos and variations
            if key == 'repport_token':  # Common typo
                key = 'report_count'
            elif key == 'reportcount':  # Another variation
                key = 'report_count'
            elif key == 'updatted_at':  # Common typo
                key = 'updated_at'
            elif key == 'updatedat':  # Another variation
                key = 'updated_at'
            elif key == 'id':  # Skip Firebase auto-added id
                continue
                
            # Only include allowed fields
            if key in allowed_fields:
                clean_data[key] = value
        
        return cls(**clean_data)


@dataclass
class TokenHistoryDocument:
    """
    Data model for Token History Document
    
    Path: userCollection/{userEmailID}/tokenHistory/{history_ID}
    """
    history_id: str
    user_email: str
    tokens_added: int
    previous_tokens: int
    new_total_tokens: int
    added_by: str  # admin email who added the tokens
    reason: Optional[str] = None  # optional reason for token addition
    created_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for Firebase storage"""
        data = asdict(self)
        if self.created_at:
            data['created_at'] = self.created_at
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TokenHistoryDocument':
        """Create TokenHistoryDocument from Firebase data with field validation"""
        # Define allowed fields for TokenHistoryDocument
        allowed_fields = {
            'history_id', 'user_email', 'tokens_added', 'previous_tokens', 
            'new_total_tokens', 'added_by', 'reason', 'created_at'
        }
        
        # Clean and fix the data
        clean_data = {}
        for key, value in data.items():
            # Handle field name typos and variations
            if key == 'id':  # Skip Firebase auto-added id
                continue
                
            # Only include allowed fields
            if key in allowed_fields:
                clean_data[key] = value
        
        return cls(**clean_data)


class FirebaseDataManager:
    """
    Data Manager for User-Session-Job Firebase Structure
    
    Handles all CRUD operations for the hierarchical database structure
    """
    
    def __init__(self):
        self.crud = get_firebase_crud()
        self.users_collection = "userCollection"
    
    # ==================== USER OPERATIONS ====================
    
    def create_user(self, user: UserDocument) -> bool:
        """
        Create a new user document
        
        Args:
            user: UserDocument instance
            
        Returns:
            bool: True if successful
        """
        try:
            user_data = user.to_dict()
            success = self.crud.create(self.users_collection, user.email, user_data)
            
            if success:
                print(f"👤 Created user: {user.email}")
            
            return success
            
        except Exception as e:
            print(f"❌ Failed to create user {user.email}: {str(e)}")
            return False
    
    def get_user(self, user_email: str) -> Optional[UserDocument]:
        """
        Get user by email ID
        
        Args:
            user_email: User's email address
            
        Returns:
            UserDocument or None if not found
        """
        try:
            user_data = self.crud.read(self.users_collection, user_email)
            
            if user_data:
                return UserDocument.from_dict(user_data)
            
            return None
            
        except Exception as e:
            print(f"❌ Failed to get user {user_email}: {str(e)}")
            return None
    
    def update_user(self, user_email: str, update_data: Dict[str, Any]) -> bool:
        """
        Update user document
        
        Args:
            user_email: User's email address
            update_data: Fields to update
            
        Returns:
            bool: True if successful
        """
        try:
            success = self.crud.update(self.users_collection, user_email, update_data)
            
            if success:
                print(f"📝 Updated user: {user_email}")
            
            return success
            
        except Exception as e:
            print(f"❌ Failed to update user {user_email}: {str(e)}")
            return False
    
    def delete_user(self, user_email: str) -> bool:
        """
        Delete user document (and all subcollections)
        
        Args:
            user_email: User's email address
            
        Returns:
            bool: True if successful
        """
        try:
            success = self.crud.delete(self.users_collection, user_email)
            
            if success:
                print(f"🗑️ Deleted user: {user_email}")
            
            return success
            
        except Exception as e:
            print(f"❌ Failed to delete user {user_email}: {str(e)}")
            return False
    
    def get_all_users(self, limit: int = None) -> List[UserDocument]:
        """
        Get all users
        
        Args:
            limit: Maximum number of users to return
            
        Returns:
            List of UserDocument instances
        """
        try:
            users_data = self.crud.read_all(self.users_collection, limit)
            users = []
            
            for user_data in users_data:
                try:
                    user = UserDocument.from_dict(user_data)
                    users.append(user)
                except Exception as e:
                    print(f"⚠️ Error parsing user data: {e}")
                    print(f"    Problematic data keys: {list(user_data.keys())}")
                    continue
            
            return users
            
        except Exception as e:
            print(f"❌ Failed to get all users: {str(e)}")
            return []
    
    # ==================== JOB OPERATIONS ====================
    
    def create_job(self, user_email: str, session_id: str, job: JobDocument) -> bool:
        """
        Create a new job document in user's session
        
        Args:
            user_email: User's email address
            session_id: Session identifier
            job: JobDocument instance
            
        Returns:
            bool: True if successful
        """
        try:
            collection_path = f"{self.users_collection}/{user_email}/{session_id}"
            job_data = job.to_dict()
            
            success = self.crud.create(collection_path, job.job_id, job_data)
            
            if success:
                print(f"📋 Created job {job.job_id} for user {user_email} in session {session_id}")
                # Only increment report count for successful jobs
                if job.job_status == "success":
                    self.increment_user_report_count(user_email)
                    print(f"📊 [REPORT COUNT] Incremented report count for successful job {job.job_id}")
                else:
                    print(f"⚠️ [REPORT COUNT] Skipping report count increment for failed job {job.job_id} (status: {job.job_status})")
            
            return success
            
        except Exception as e:
            print(f"❌ Failed to create job {job.job_id}: {str(e)}")
            return False
    
    def get_job(self, user_email: str, session_id: str, job_id: str) -> Optional[JobDocument]:
        """
        Get specific job by ID
        
        Args:
            user_email: User's email address
            session_id: Session identifier
            job_id: Job identifier
            
        Returns:
            JobDocument or None if not found
        """
        try:
            collection_path = f"{self.users_collection}/{user_email}/{session_id}"
            job_data = self.crud.read(collection_path, job_id)
            
            if job_data:
                return JobDocument.from_dict(job_data)
            
            return None
            
        except Exception as e:
            print(f"❌ Failed to get job {job_id}: {str(e)}")
            return None
    
    def update_job(self, user_email: str, session_id: str, job_id: str, update_data: Dict[str, Any]) -> bool:
        """
        Update job document
        
        Args:
            user_email: User's email address
            session_id: Session identifier
            job_id: Job identifier
            update_data: Fields to update
            
        Returns:
            bool: True if successful
        """
        try:
            collection_path = f"{self.users_collection}/{user_email}/{session_id}"
            success = self.crud.update(collection_path, job_id, update_data)
            
            if success:
                print(f"📝 Updated job {job_id}")
            
            return success
            
        except Exception as e:
            print(f"❌ Failed to update job {job_id}: {str(e)}")
            return False
    
    def delete_job(self, user_email: str, session_id: str, job_id: str) -> bool:
        """
        Delete job document
        
        Args:
            user_email: User's email address
            session_id: Session identifier
            job_id: Job identifier
            
        Returns:
            bool: True if successful
        """
        try:
            collection_path = f"{self.users_collection}/{user_email}/{session_id}"
            success = self.crud.delete(collection_path, job_id)
            
            if success:
                print(f"🗑️ Deleted job {job_id}")
            
            return success
            
        except Exception as e:
            print(f"❌ Failed to delete job {job_id}: {str(e)}")
            return False
    
    def get_session_jobs(self, user_email: str, session_id: str, limit: int = None) -> List[JobDocument]:
        """
        Get all jobs in a session
        
        Args:
            user_email: User's email address
            session_id: Session identifier
            limit: Maximum number of jobs to return
            
        Returns:
            List of JobDocument instances
        """
        try:
            collection_path = f"{self.users_collection}/{user_email}/{session_id}"
            jobs_data = self.crud.read_all(collection_path, limit)
            jobs = []
            
            for job_data in jobs_data:
                try:
                    job = JobDocument.from_dict(job_data)
                    jobs.append(job)
                except Exception as e:
                    continue
            
            return jobs
            
        except Exception as e:
            print(f"❌ Failed to get session jobs: {str(e)}")
            return []
    
    def get_user_all_jobs(self, user_email: str) -> Dict[str, List[JobDocument]]:
        """
        Get all jobs for a user across all sessions
        
        Args:
            user_email: User's email address
            
        Returns:
            Dictionary with session_id as key and list of jobs as value
        """
        try:
            # This would require querying all subcollections
            # For now, we'll return jobs from known sessions
            # In production, you might want to track session IDs separately
            print(f"⚠️ Getting all jobs for user {user_email} requires session enumeration")
            return {}
            
        except Exception as e:
            print(f"❌ Failed to get all user jobs: {str(e)}")
            return {}
    
    def get_user_job_history(self, user_email: str, limit: int = 50) -> List[Dict[str, Any]]:
        
        try:
            # Get user's root document path
            user_path = f"{self.users_collection}/{user_email}"
            
            # Get all session collections under this user
            try:
                # List all subcollections (sessions) for this user
                all_collections = list(self.crud.db.collection(self.users_collection).document(user_email).collections())
                # Filter out tokenHistory collection as it contains token records, not job records
                collections = [col for col in all_collections if col.id != 'tokenHistory']
                all_jobs = []
                
                print(f"🔍 Found {len(all_collections)} total collections, processing {len(collections)} job sessions (excluding tokenHistory)")
                
                for session_collection in collections:
                    session_id = session_collection.id
                    try:
                        # Get all jobs in this session
                        jobs_data = self.crud.read_all(f"{user_path}/{session_id}")
                        
                        for job_data in jobs_data:
                            try:
                                # Add session_id to job data for frontend
                                job_data['session_id'] = session_id
                                # Parse as JobDocument to validate, then convert back to dict
                                job_doc = JobDocument.from_dict(job_data)
                                
                                # Only include completed jobs (job_status == 'success')
                                if job_doc.job_status != 'success':
                                    continue
                                
                                job_dict = job_doc.to_dict()
                                job_dict['session_id'] = session_id
                                all_jobs.append(job_dict)
                            except Exception as e:
                                # print(f"⚠️ Error parsing job data in session {session_id}: {e}")
                                continue
                                
                    except Exception as e:
                        print(f"⚠️ Error reading jobs from session {session_id}: {e}")
                        continue
                
                # Sort by created_at descending (latest first)
                def sort_key(job):
                    created_at = job.get('created_at')
                    if hasattr(created_at, 'timestamp'):
                        # If it's a datetime object, convert to timestamp
                        return created_at.timestamp()
                    elif isinstance(created_at, (int, float)):
                        # If it's already a number, use it directly
                        return created_at
                    else:
                        # Default to 0 for unknown formats
                        return 0
                
                all_jobs.sort(key=sort_key, reverse=True)
                
                # Apply limit
                if limit and len(all_jobs) > limit:
                    all_jobs = all_jobs[:limit]
                
                print(f"📋 Retrieved {len(all_jobs)} completed jobs for user {user_email}")
                return all_jobs
                
            except Exception as e:
                print(f"⚠️ Error accessing user collections: {e}")
                # Fallback: return empty list
                return []
            
        except Exception as e:
            print(f"❌ Failed to get user job history: {str(e)}")
            return []
    
    # ==================== UTILITY OPERATIONS ====================
    
    def increment_user_report_count(self, user_email: str) -> bool:
        """
        Increment user's report count
        
        Args:
            user_email: User's email address
            
        Returns:
            bool: True if successful
        """
        try:
            user = self.get_user(user_email)
            if user:
                return self.update_user(user_email, {
                    'report_count': user.report_count + 1
                })
            
            return False
            
        except Exception as e:
            print(f"❌ Failed to increment report count for {user_email}: {str(e)}")
            return False
    
    def update_user_tokens(self, user_email: str, tokens_used: int) -> bool:
        """
        Update user's token usage
        
        Args:
            user_email: User's email address
            tokens_used: Number of tokens used
            
        Returns:
            bool: True if successful
        """
        try:
            user = self.get_user(user_email)
            if user:
                return self.update_user(user_email, {
                    'used_token': user.used_token + tokens_used
                })
            
            return False
            
        except Exception as e:
            print(f"❌ Failed to update tokens for {user_email}: {str(e)}")
            return False
    
    def generate_session_id(self) -> str:
        """Generate a unique session ID"""
        return f"session_{uuid.uuid4().hex[:8]}"
    
    def generate_job_id(self) -> str:
        """Generate a unique job ID"""
        return f"job_{uuid.uuid4().hex[:8]}"
    
    def generate_history_id(self) -> str:
        """Generate a unique token history ID"""
        return f"history_{uuid.uuid4().hex[:8]}"
    
    # ==================== TOKEN HISTORY OPERATIONS ====================
    
    def create_token_history(self, token_history: TokenHistoryDocument) -> bool:
        """
        Create a new token history record
        
        Args:
            token_history: TokenHistoryDocument instance
            
        Returns:
            bool: True if successful
        """
        try:
            collection_path = f"{self.users_collection}/{token_history.user_email}/tokenHistory"
            history_data = token_history.to_dict()
            # Set created timestamp
            history_data['created_at'] = datetime.now()
            
            success = self.crud.create(collection_path, token_history.history_id, history_data)
            
            if success:
                print(f"📊 Created token history {token_history.history_id} for user {token_history.user_email}")
            
            return success
            
        except Exception as e:
            print(f"❌ Failed to create token history {token_history.history_id}: {str(e)}")
            return False
    
    def get_user_token_history(self, user_email: str, limit: int = 50) -> List[TokenHistoryDocument]:
        """
        Get token history for a user
        
        Args:
            user_email: User's email address
            limit: Maximum number of history records to return
            
        Returns:
            List of TokenHistoryDocument instances ordered by created_at (newest first)
        """
        try:
            collection_path = f"{self.users_collection}/{user_email}/tokenHistory"
            history_data = self.crud.read_all(collection_path, limit)
            history_records = []
            
            for data in history_data:
                try:
                    history = TokenHistoryDocument.from_dict(data)
                    history_records.append(history)
                except Exception as e:
                    print(f"⚠️ Error parsing token history data: {e}")
                    print(f"    Problematic data keys: {list(data.keys())}")
                    continue
            
            # Sort by created_at (newest first)
            history_records.sort(key=lambda x: x.created_at or datetime.min, reverse=True)
            
            return history_records
            
        except Exception as e:
            print(f"❌ Failed to get token history for user {user_email}: {str(e)}")
            return []
    
    def get_token_history_by_id(self, user_email: str, history_id: str) -> Optional[TokenHistoryDocument]:
        """
        Get specific token history record by ID
        
        Args:
            user_email: User's email address
            history_id: History record identifier
            
        Returns:
            TokenHistoryDocument or None if not found
        """
        try:
            collection_path = f"{self.users_collection}/{user_email}/tokenHistory"
            history_data = self.crud.read(collection_path, history_id)
            
            if history_data:
                return TokenHistoryDocument.from_dict(history_data)
            
            return None
            
        except Exception as e:
            print(f"❌ Failed to get token history {history_id}: {str(e)}")
            return None
    
    def add_tokens_with_history(self, user_email: str, tokens_to_add: int, added_by: str, reason: str = None) -> Dict[str, Any]:
        """
        Add tokens to user and create history record
        
        Args:
            user_email: User's email address
            tokens_to_add: Number of tokens to add
            added_by: Admin email who is adding the tokens
            reason: Optional reason for token addition
            
        Returns:
            Dictionary with success status and details
        """
        try:
            # Get current user data
            user = self.get_user(user_email)
            if not user:
                return {
                    'success': False,
                    'error': 'User not found'
                }
            
            previous_tokens = user.issued_token
            new_total_tokens = previous_tokens + tokens_to_add
            
            # Update user's issued tokens
            success = self.update_user(user_email, {
                'issued_token': new_total_tokens
            })
            
            if not success:
                return {
                    'success': False,
                    'error': 'Failed to update user tokens'
                }
            
            # Create history record
            history_id = self.generate_history_id()
            token_history = TokenHistoryDocument(
                history_id=history_id,
                user_email=user_email,
                tokens_added=tokens_to_add,
                previous_tokens=previous_tokens,
                new_total_tokens=new_total_tokens,
                added_by=added_by,
                reason=reason,
                created_at=datetime.now()
            )
            
            history_success = self.create_token_history(token_history)
            
            if not history_success:
                print(f"⚠️ Failed to create history record, but token update succeeded")
            
            return {
                'success': True,
                'previous_tokens': previous_tokens,
                'new_total': new_total_tokens,
                'tokens_added': tokens_to_add,
                'history_created': history_success
            }
            
        except Exception as e:
            print(f"❌ Failed to add tokens with history for {user_email}: {str(e)}")
            return {
                'success': False,
                'error': 'Failed to add tokens'
            }


# Global instance for easy access
data_manager = FirebaseDataManager()


def get_data_manager() -> FirebaseDataManager:
    """Get Firebase Data Manager instance"""
    return data_manager
