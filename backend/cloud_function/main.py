# ============================================================================
# IMPORTS AND INITIALIZATION
# ============================================================================

from firebase_functions import https_fn
from firebase_admin import initialize_app
import json
import requests
import time
import csv
import io
import os
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
    # TODO: Move these credentials to Google Secret Manager for production
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
            
            print("Salesforce authentication successful!")
            print(f"Instance URL: {instance_url}")
            print(f"Access Token: {access_token[:20]}...")
            
            return {
                "status": "success",
                "message": "Access token obtained successfully!",
                "data": data,
            }
        else:
            # Handle authentication failure
            print("Salesforce authentication failed!")
            print(f"Status Code: {response.status_code}")
            print(f"Response: {response.text}")
            
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

def parse_csv_to_records(csv_data):
    try:
        print("Parsing CSV data to records...")
        
        # Use CSV DictReader to parse the data
        csv_reader = csv.DictReader(io.StringIO(csv_data))
        records = list(csv_reader)
        
        print(f"Parsed {len(records)} records from CSV")
        return records
        
    except Exception as e:
        error_msg = f"CSV parsing failed: {str(e)}"
        print(f"{error_msg}")
        raise Exception(error_msg)

def get_object_fields(object_name, access_token, instance_url, api_version="v59.0"):
    """Get all non-compound field names for a Salesforce object"""
    try:
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        url = f"{instance_url}/services/data/{api_version}/sobjects/{object_name}/describe"
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            describe = response.json()
            # Filter out compound fields
            fields = [
                field['name'] 
                for field in describe['fields'] 
                if not field.get('compoundFieldName') and field.get('type') not in ['address', 'location']
            ]
            return fields
        else:
            raise Exception(f"Failed to describe object {object_name}: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"❌ Error getting fields for {object_name}: {e}")
        return None

# ============================================================================
# SALESFORCE METADATA OPERATIONS
# ============================================================================

def get_all_tables(access_token, instance_url, api_version="v59.0"):
    # Construct the sObjects metadata endpoint URL
    url = f"{instance_url}/services/data/{api_version}/sobjects/"
    
    # Set up authentication headers
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }
    
    try:
        print("Retrieving Salesforce object metadata...")
        
        # Get all object metadata
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            tables = []
            
            # Filter and format queryable objects
            for obj in data['sobjects']:
                if obj['queryable']:  # Only include queryable objects
                    tables.append({
                        'name': obj['name'],
                        'label': obj['label'],
                        'keyPrefix': obj.get('keyPrefix', ''),
                        'custom': obj['custom']
                    })
            
            print(f"Retrieved {len(tables)} queryable objects")
            return tables
        else:
            error_msg = f"Failed to get tables: {response.status_code} - {response.text}"
            print(f"{error_msg}")
            raise Exception(error_msg)
            
    except requests.RequestException as e:
        error_msg = f"Network error during metadata retrieval: {str(e)}"
        print(f"{error_msg}")
        raise Exception(error_msg)

# ============================================================================
# MAIN DATA FETCHING FUNCTIONS
# ============================================================================

def fetch_salesforce_data(soql_query, access_token, instance_url, api_version="v59.0"):
    try:
        print(f"Starting Salesforce data fetch...")
        print(f"Query: {soql_query[:100]}{'...' if len(soql_query) > 100 else ''}")
        
        # Step 1: Create bulk query job
        job_id = create_bulk_query_job(soql_query, access_token, instance_url, api_version)
        
        # Step 2: Wait for job completion
        job_data = wait_for_job_completion(job_id, access_token, instance_url, api_version)
        
        # Step 3: Download results
        csv_data = get_job_results(job_id, access_token, instance_url, api_version)
        
        # Steep 3.1: Convert CSV Data into Dataframe
        import pandas as pd
        df = pd.read_csv(io.StringIO(csv_data))
        records = df.to_dict(orient='records')
        print(records)
        
        # Step 4: Parse CSV to structured data
        # records = parse_csv_to_records(csv_data)
    
        print(f"Successfully fetched {len(records)} records!")
        return records
        
    except Exception as e:
        print(f"Data fetch failed: {str(e)}")
        raise

# ============================================================================
# DATA CONVERSION AND STORAGE UTILITIES
# ============================================================================

def convert_salesforce_data_to_csv(records, object_name):
    if not records:
        print("No records to convert")
        return ""
    
    try:
        print(f"Converting {len(records)} records to CSV format...")
        
        # Create CSV output using StringIO
        output = io.StringIO()
        fieldnames = records[0].keys()
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        
        # Write header and data
        writer.writeheader()
        writer.writerows(records)
        
        csv_content = output.getvalue()
        print(f"CSV conversion complete ({len(csv_content)} characters)")
        return csv_content
        
    except Exception as e:
        error_msg = f"Failed to convert to CSV: {str(e)}"
        print(f"{error_msg}")
        raise Exception(error_msg)

def save_csv_file_to_cloud_storage(csv_content, filename=None, object_name="data"):
    # Define the local storage directory
    storage_dir = "/salesforcedata"
    
    # Create directory if it doesn't exist
    try:
        os.makedirs(storage_dir, exist_ok=True)
        print(f"✅ Storage directory created/verified: {storage_dir}")
    except Exception as e:
        print(f"❌ Error creating storage directory: {e}")
        return {
            "filename": None,
            "file_path": None,
            "size": 0,
            "status": "error",
            "error": f"Failed to create directory: {e}"
        }
    
    # Generate filename if not provided
    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"salesforce_{object_name}_{timestamp}.csv"
    
    # Full file path
    file_path = os.path.join(storage_dir, filename)
    
    try:
        # Write CSV content to file
        with open(file_path, 'w', encoding='utf-8', newline='') as f:
            f.write(csv_content)
        
        print(f"✅ File saved successfully: {file_path}")
        print(f"📊 File size: {len(csv_content)} characters")
        
        return {
            "filename": filename,
            "file_path": file_path,
            "size": len(csv_content),
            "status": "saved"
        }
        
    except Exception as e:
        print(f"❌ Error saving file: {e}")
        return {
            "filename": filename,
            "file_path": file_path,
            "size": 0,
            "status": "error",
            "error": f"Failed to save file: {e}"
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
        
        # Hardcoded Salesforce objects to fetch (no request body needed)
        sobject_names = ['Account', 'Opportunity']
                
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
        # STEP 2: PROCESS EACH OBJECT (FETCH ALL RECORDS + CONVERT TO CSV)
        # ====================================================================
        
        results = {}
        total_records = 0
        successful_objects = 0
        
        for i, sobject_name in enumerate(sobject_names, 1):
            try:
                # Get all field names for this object (Bulk API doesn't support SELECT *)
                fields = get_object_fields(sobject_name, access_token, instance_url)
                
                if not fields:
                    print(f"No fields found for {sobject_name} - skipping")
                    continue

                # Generate SOQL query with explicit field names
                fields_str = ', '.join(fields)
                soql_query = f"SELECT {fields_str} FROM {sobject_name}"
                
                # Fetch all data for this object using Bulk API
                records = fetch_salesforce_data(soql_query, access_token, instance_url)
                
                if records:
                    # Convert to CSV format  
                    results[sobject_name] = {
                        "record_count": len(records),
                        "status": "success"
                    }
                    total_records += len(records)
                    successful_objects += 1
                else:
                    results[sobject_name] = {
                        "record_count": 0,
                        "csv_data": "",
                        "status": "no_data"
                    }
                    
            except Exception as obj_error:
                error_msg = str(obj_error)
                results[sobject_name] = {
                    "record_count": 0,
                    "csv_data": "",
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
            "objects": results
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
