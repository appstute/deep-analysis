# ============================================================================
# IMPORTS AND INITIALIZATION
# ============================================================================

from firebase_functions import https_fn
from firebase_admin import initialize_app, storage
import json
import requests
import time
import io
from datetime import datetime

# Initialize Firebase Admin SDK
initialize_app()

# ============================================================================
# SALESFORCE AUTHENTICATION
# ============================================================================

def login_to_salesforce():
    # Salesforce OAuth 2.0 token endpoint
    url = 'https://login.salesforce.com/services/oauth2/token'

    # OAuth payload with credentials
    payload = {
        'grant_type': 'password',  # Username-password flow
        'client_id': '3MVG9rZjd7MXFdLhbfl8Ne7OfHK3FsYRYBgXjXfEQPbCBNVLLiGneBcf6GP0xg_gZL4qBEWWxCSTmNNQNjbm4',
        'client_secret': 'A6098AB4B122691A0FA9F69D34641EFC10E8D7264C1A8EE68E9C83632E957B89',
        'username': 'minakshi.patil837@agentforce.com',
        'password': 'Min@990301EbsOgYxBGXgpq7cJgR8Cme8a'  # password + security_token
    }

    try:
        # Make authentication request to Salesforce
        response = requests.post(url, data=payload, timeout=60)

        # Handle successful authentication
        if response.status_code == 200:
            data = response.json()
            access_token = data['access_token']
            instance_url = data['instance_url']
                        
            return {
                "status": "success",
                "message": "Access token obtained successfully!",
                "data": data,
            }
        else:
            # Handle authentication failure
            
            return {
                "status": "connection failed",
                "message": "Authentication failed - check credentials",
                "data": response.json() if response.text else None,
            }
            
    except requests.RequestException as e:
        print(f"Network error during authentication: {str(e)}")
        return {
            "status": "connection failed",
            "message": f"Network error: {str(e)}",
            "data": None,
        }

# ============================================================================
# SALESFORCE BULK API OPERATIONS
# ============================================================================

def create_bulk_query_job(soql_query, access_token, instance_url, api_version="v59.0"):
    # Construct the bulk API endpoint URL
    url = f"{instance_url}/services/data/{api_version}/jobs/query"
    
    # Set up authentication headers
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }
    
    # Job configuration payload
    payload = {
        "operation": "query",  # Bulk query operation
        "query": soql_query,   # SOQL query to execute
    }
    
    try:
        # Submit the job creation request
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        
        if response.status_code == 200:
            job = response.json()
            job_id = job['id']
            print(f"Bulk job created successfully: {job_id}")
            return job_id
        else:
            error_msg = f"Job creation failed: {response.status_code} - {response.text}"
            print(f"{error_msg}")
            raise Exception(error_msg)
            
    except requests.RequestException as e:
        error_msg = f"Network error during job creation: {str(e)}"
        print(f"{error_msg}")
        raise Exception(error_msg)

def wait_for_job_completion(job_id, access_token, instance_url, api_version="v59.0"):
    # Construct the job status endpoint URL
    url = f"{instance_url}/services/data/{api_version}/jobs/query/{job_id}"
    
    # Set up authentication headers
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }
    
    print(f"Waiting for job {job_id} to complete...")
    
    # Poll until job completion
    while True:
        try:
            # Check job status
            response = requests.get(url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                job_state = data['state']
                
                print(f"Job status: {job_state}")
                
                # Check for completion
                if job_state == 'JobComplete':
                    print("Job completed successfully!")
                    return data
                elif job_state in ['Failed', 'Aborted']:
                    error_msg = f"Job {job_state}: {data.get('stateMessage', 'Unknown error')}"
                    print(f"{error_msg}")
                    raise Exception(error_msg)
                
                # Wait before next status check (5 seconds)
                time.sleep(5)
            else:
                error_msg = f"Failed to check job status: {response.status_code} - {response.text}"
                print(f"{error_msg}")
                raise Exception(error_msg)
                
        except requests.RequestException as e:
            error_msg = f"Network error during status check: {str(e)}"
            print(f"{error_msg}")
            raise Exception(error_msg)

def get_job_results(job_id, access_token, instance_url, api_version="v59.0"):
    # Construct the job results endpoint URL
    url = f"{instance_url}/services/data/{api_version}/jobs/query/{job_id}/results"
    
    # Set up authentication headers
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }
    
    try:
        print(f"Downloading results for job {job_id}...")
        
        # Download the results
        response = requests.get(url, headers=headers, timeout=60)
        
        if response.status_code == 200:
            csv_data = response.text
            print(f"Results downloaded successfully ({len(csv_data)} characters)")
            return csv_data
        else:
            error_msg = f"Failed to retrieve results: {response.status_code} - {response.text}"
            print(f"{error_msg}")
            raise Exception(error_msg)
            
    except requests.RequestException as e:
        error_msg = f"Network error during result download: {str(e)}"
        print(f"{error_msg}")
        raise Exception(error_msg)

# ============================================================================
# MAIN DATA FETCHING FUNCTIONS
# ============================================================================

def fetch_salesforce_data(soql_query, access_token, instance_url, api_version="v59.0", bucket_name=None, object_name="salesforce_data", user_email=None):
    try:
        print(f"Starting Salesforce data fetch...")
        print(f"Query: {soql_query[:100]}{'...' if len(soql_query) > 100 else ''}")
        
        # Step 1: Create bulk query job
        job_id = create_bulk_query_job(soql_query, access_token, instance_url, api_version)
        
        # Step 2: Wait for job completion
        job_data = wait_for_job_completion(job_id, access_token, instance_url, api_version)
        
        # Step 3: Download results
        csv_data = get_job_results(job_id, access_token, instance_url, api_version)
        
        # Step 4: Convert CSV Data into DataFrame
        import pandas as pd
        df = pd.read_csv(io.StringIO(csv_data))
        if 'CreatedDate' in df.columns:
            df['CreatedDate'] = pd.to_datetime(df['CreatedDate'], errors='coerce').dt.date.astype('datetime64[ns]')
        if 'CloseDate' in df.columns:
            df['CloseDate'] = pd.to_datetime(df['CloseDate'], errors='coerce').dt.date.astype('datetime64[ns]')

        # Step 5: Save DataFrame to Firebase Storage as pickle file (if bucket_name provided)
        firebase_result = None
        delete_result = None
        if bucket_name:
            # Step 5a: Delete old files for this user and object
            if user_email:
                delete_result = delete_old_files_from_firebase_storage(bucket_name, user_email, object_name)
                if delete_result["status"] == "success":
                    print(f"Cleaned up {delete_result['deleted_count']} old files")
                else:
                    print(f"Warning: Failed to clean up old files: {delete_result.get('error', 'Unknown error')}")
            
            # Step 5b: Generate file path with user email and timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            if user_email:
                # Sanitize user email for file path (replace @ with _ and remove special chars)
                safe_email = user_email.replace('@', '_').replace('.', '_').replace('+', '_')
                file_path = f"{safe_email}/data/salesforce/{object_name}_{timestamp}.pkl"
            else:
                file_path = f"salesforce_data/{object_name}_{timestamp}.pkl"
            
            # Step 5c: Save DataFrame as pickle file to Firebase Storage
            firebase_result = save_dataframe_to_firebase_storage(df, bucket_name, file_path)
            
            if firebase_result["status"] == "success":
                print(f"Successfully saved DataFrame to Firebase Storage as pickle file")
            else:
                print(f"Failed to save to Firebase Storage: {firebase_result.get('error', 'Unknown error')}")
    
        print(f"Successfully fetched DataFrame with {len(df)} records!")
        
        # Return DataFrame, Firebase Storage save result, and deletion result
        return {
            "dataframe": df,
            "firebase_save_result": firebase_result,
            "delete_result": delete_result,
            "record_count": len(df)
        }
        
    except Exception as e:
        print(f"Data fetch failed: {str(e)}")
        raise

# ============================================================================
# FIREBASE STORAGE UTILITIES
# ============================================================================

def delete_old_files_from_firebase_storage(bucket_name, user_email, object_name):
    try:
        # Use explicit Firebase Storage bucket
        bucket = storage.bucket(bucket_name)
        
        # Sanitize user email for file path
        safe_email = user_email.replace('@', '_').replace('.', '_').replace('+', '_')
        folder_path = f"{safe_email}/data/salesforce/"
        
        print(f"Looking for old files in folder: {folder_path}")
        
        # List all blobs in the user's folder
        blobs = bucket.list_blobs(prefix=folder_path)
        
        deleted_files = []
        for blob in blobs:
            # Check if this blob is for the specific object
            if blob.name.endswith('.pkl') and object_name in blob.name:
                try:
                    print(f"Deleting old file: {blob.name}")
                    blob.delete()
                    deleted_files.append(blob.name)
                except Exception as e:
                    print(f"Failed to delete {blob.name}: {e}")
        
        print(f"Deleted {len(deleted_files)} old files for {object_name}")
        
        return {
            "status": "success",
            "deleted_files": deleted_files,
            "deleted_count": len(deleted_files)
        }
        
    except Exception as e:
        error_msg = f"Failed to delete old files: {str(e)}"
        print(error_msg)
        return {
            "status": "error",
            "error": error_msg,
            "deleted_files": [],
            "deleted_count": 0
        }

def save_dataframe_to_firebase_storage(dataframe, bucket_name, file_path):
    try:
        # Use explicit Firebase Storage bucket
        bucket = storage.bucket(bucket_name)
        
        print(f"Using Firebase Storage bucket: {bucket.name}")
        
        # Create blob object
        blob = bucket.blob(file_path)
        
        # Serialize DataFrame to pickle format using pandas
        import io as pandas_io
        pickle_buffer = pandas_io.BytesIO()
        dataframe.to_pickle(pickle_buffer)
        pickle_data = pickle_buffer.getvalue()
        
        # Upload to Firebase Storage
        blob.upload_from_string(pickle_data, content_type='application/octet-stream')
        
        # Set public access (optional - you can remove this if you want private files)
        blob.make_public()
        
        # Get public URL (no private key required)
        public_url = blob.public_url
        
        print(f"DataFrame saved to Firebase Storage: gs://{bucket.name}/{file_path}")
        print(f"DataFrame shape: {dataframe.shape}")
        print(f"File size: {len(pickle_data)} bytes")
        print(f"Public URL: {public_url}")
        
        return {
            "status": "success",
            "bucket": bucket.name,
            "file_path": file_path,
            "file_size": len(pickle_data),
            "dataframe_shape": dataframe.shape,
            "firebase_url": f"gs://{bucket.name}/{file_path}",
            "public_url": public_url
        }
        
    except Exception as e:
        error_msg = f"Failed to save DataFrame to Firebase Storage: {str(e)}"
        print(error_msg)
        return {
            "status": "error",
            "error": error_msg,
            "bucket": bucket_name,
            "file_path": file_path
        }

# ============================================================================
# CLOUD FUNCTION MAIN ENDPOINT
# ============================================================================

@https_fn.on_request()
def zingworks_salesforce_connector(req: https_fn.Request) -> https_fn.Response:
    try:        
        # ====================================================================
        # HANDLE CORS PREFLIGHT REQUESTS
        # ====================================================================
        if req.method == 'OPTIONS':
            headers = {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Max-Age': '3600'
            }
            return https_fn.Response('', status=204, headers=headers)
        
        # ====================================================================
        # SET RESPONSE HEADERS
        # ====================================================================
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Content-Type': 'application/json'
        }
        
        # Hardcoded Salesforce objects to fetch
        sobject_names = ['Account', 'Opportunity']
        
        # Firebase Storage configuration - explicit bucket name
        FIREBASE_BUCKET_NAME = "insightbot-467305.firebasestorage.app"  # Your Firebase project's default bucket
        
        # Extract user email from request body
        try:
            request_data = req.get_json() if req.method == 'POST' else {}
            user_email = request_data.get('username') or request_data.get('user_email') or request_data.get('email')
            
            # Fallback for GET requests or missing username
            if not user_email:
                return https_fn.Response(
                    json.dumps({
                        "status": "error",
                        "message": "Username/email is required in request body. Send POST request with JSON body containing 'username', 'user_email', or 'email' field.",
                        "error_type": "MissingUsername"
                    }),
                    status=400,
                    headers=headers
                )
            else:
                print(f"Processing request for user: {user_email}")
            
        except Exception as e:
            return https_fn.Response(
                json.dumps({
                    "status": "error",
                    "message": f"Failed to parse request body: {str(e)}",
                    "error_type": "RequestParseError"
                }),
                status=400,
                headers=headers
            )
        
        # Hardcoded column mappings for each Salesforce object
        object_columns = {
            'Account': [
                "Account_Type__c", "AccountNumber", "AccountSource", "Active__c", "AnnualRevenue",
                "BillingCity","BillingCountry","BillingCountryCode","BillingPostalCode","BillingState",
                "BillingStateCode", "BillingStreet", "CleanStatus", "CreatedById", "CreatedDate", "CustomerPriority__c", 
                "Description", "Id", "Industry", "Name","NumberOfEmployees","NumberofLocations__c","OperatingHoursId",
                "ParentId","Rating","ShippingCity", "ShippingCountry","ShippingCountryCode","ShippingPostalCode", "ShippingState",
                "ShippingStateCode","ShippingStreet","Site", "Type", "UpsellOpportunity__c", "YearStarted"
                ],
            'Opportunity': [
                "AccountId", "Amount", "CampaignId", "CloseDate", "CreatedById", "CreatedDate",
                "CurrentGenerators__c","DeliveryInstallationStatus__c","Description","ExpectedRevenue","ForecastCategoryName",
                "Id","IsWon","LeadSource","MainCompetitors__c","Name","NextStep",
                "OrderNumber__c","OwnerId","Pricebook2Id","Probability","StageName",
                "TotalOpportunityQuantity", "TrackingNumber__c"
                ]
        }
                
        # ====================================================================
        # STEP 1: AUTHENTICATE WITH SALESFORCE
        # ====================================================================
        auth_result = login_to_salesforce()
        
        if auth_result['status'] != 'success':
            return https_fn.Response(json.dumps(auth_result), status=401, headers=headers)
        
        # Extract credentials
        access_token = auth_result['data']['access_token']
        instance_url = auth_result['data']['instance_url']
        
        # ====================================================================
        # STEP 2: PROCESS EACH OBJECT (FETCH ALL RECORDS + SAVE TO FIREBASE)
        # ====================================================================
        
        results = {}
        total_records = 0
        successful_objects = 0
        
        for i, sobject_name in enumerate(sobject_names, 1):
            try:
                # Use hardcoded field names for this object
                fields = object_columns.get(sobject_name, [])
                
                if not fields:
                    print(f"No hardcoded fields found for {sobject_name} - skipping")
                    continue

                # Generate SOQL query with hardcoded field names
                fields_str = ', '.join(fields)
                soql_query = f"SELECT {fields_str} FROM {sobject_name}"
                
                # Fetch all data for this object using Bulk API
                fetch_result = fetch_salesforce_data(soql_query, access_token, instance_url, bucket_name=FIREBASE_BUCKET_NAME, object_name=sobject_name, user_email=user_email)
                df = fetch_result["dataframe"]
                firebase_result = fetch_result["firebase_save_result"]
                delete_result = fetch_result["delete_result"]
                
                if df is not None and len(df) > 0:
                    results[sobject_name] = {
                        "record_count": len(df),
                        "dataframe_shape": df.shape,
                        "firebase_pickle_file": firebase_result.get("firebase_url") if firebase_result and firebase_result.get("status") == "success" else None,
                        "firebase_public_url": firebase_result.get("public_url") if firebase_result and firebase_result.get("status") == "success" else None,
                        "firebase_file_size": firebase_result.get("file_size") if firebase_result and firebase_result.get("status") == "success" else None,
                        "firebase_save_status": firebase_result.get("status") if firebase_result else "not_attempted",
                        "deleted_old_files": delete_result.get("deleted_files", []) if delete_result else [],
                        "deleted_files_count": delete_result.get("deleted_count", 0) if delete_result else 0,
                        "status": "success"
                    }
                    total_records += len(df)
                    successful_objects += 1
                else:
                    results[sobject_name] = {
                        "record_count": 0,
                        "dataframe_shape": (0, 0),
                        "firebase_pickle_file": None,
                        "status": "no_data"
                    }
                    
            except Exception as obj_error:
                error_msg = str(obj_error)
                results[sobject_name] = {
                    "record_count": 0,
                    "status": "error",
                    "error": error_msg
                }
        
        # ====================================================================
        # STEP 3: PREPARE AND RETURN RESULTS
        # ====================================================================
        result = {
            "status": "success",
            "message": f"One-go extraction complete: {successful_objects}/{len(sobject_names)} objects processed, {total_records} total records",
            "summary": {
                "total_objects_requested": len(sobject_names),
                "successful_objects": successful_objects,
                "total_records_extracted": total_records
            },
        }
        return https_fn.Response(json.dumps(result), headers=headers)
    
    # ========================================================================
    # GLOBAL ERROR HANDLER
    # ========================================================================
    except Exception as e:
        error_msg = str(e)        
        error_result = {
            "status": "error",
            "message": error_msg,
            "error_type": type(e).__name__
        }
        
        return https_fn.Response(
            json.dumps(error_result),
            status=500,
            headers={'Access-Control-Allow-Origin': '*', 'Content-Type': 'application/json'}
        )



# NOTE
# 1. This function is used to fetch data from Salesforce and save it to Firebase Storage
# 2. Data will store in the following path: {user_email}/data/salesforce/{object_name}_{timestamp}.pkl
# 3. If data fetch again then previous one will delete and new one will be saved
# TODO
# 1. Apply an API key to use this function
# 2. instead of saving the data to Firebase Storage with email use UserID