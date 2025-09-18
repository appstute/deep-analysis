from flask import Blueprint, request, jsonify
import os
import tempfile
from typing import List, Dict, Any
from werkzeug.utils import secure_filename
import json
import re
from dotenv import load_dotenv

# Ensure environment variables (e.g., OPENAI_API_KEY) are loaded for this module
load_dotenv()


data_bp = Blueprint('data_bp', __name__)


@data_bp.route('/validate_data', methods=['POST'])
def validate_data():
    try:
        MAX_BYTES = 20 * 1024 * 1024
        allowed_ext = {'.csv', '.xlsx'}

        def fail(msg: str, status: int = 400):
            return jsonify({'valid': False, 'message': 'validation failed', 'error': msg}), status

        if 'file' not in request.files:
            return fail('Missing file in request', 400)

        session_id = request.form.get('session_id')
        if not session_id:
            return fail('Missing session_id in request', 400)

        f = request.files['file']
        filename = f.filename or ''
        if not filename:
            return fail('Empty filename', 400)

        if request.content_length and request.content_length > MAX_BYTES:
            return fail('File too large. Maximum allowed size is 20MB.', 413)

        ext = '.' + filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
        if ext not in allowed_ext:
            return fail('Invalid file type. Only CSV and XLSX are allowed.', 415)

        safe_name = secure_filename(filename)
        with tempfile.NamedTemporaryFile(prefix='upload_', suffix=ext, delete=False) as tmp:
            tmp_path = tmp.name
            f.save(tmp)

        try:
            if os.path.getsize(tmp_path) > MAX_BYTES:
                os.remove(tmp_path)
                return fail('File too large. Maximum allowed size is 20MB.', 413)
        except Exception:
            pass

        import pandas as pd

        errors: List[str] = []
        warnings: List[str] = []
        info: Dict[str, Any] = {}

        try:
            if ext == '.csv':
                df = pd.read_csv(tmp_path, header=0)
            else:
                try:
                    df = pd.read_excel(tmp_path, header=0, engine='openpyxl')
                except Exception:
                    df = pd.read_excel(tmp_path, header=0)
        except UnicodeDecodeError as e:
            os.remove(tmp_path)
            return fail(f'Encoding error: {str(e)}', 422)
        except ValueError as e:
            os.remove(tmp_path)
            return fail(f'Value error while reading file: {str(e)}', 422)
        except Exception as e:
            os.remove(tmp_path)
            return fail(f'Failed to read file: {str(e)}', 422)
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass

        col_names = [str(c) for c in df.columns.tolist()]

        if any((c.strip() == '' or c.lower().startswith('unnamed')) for c in col_names):
            errors.append('Header row has empty or Unnamed columns. Ensure the first row contains proper column names.')

        lowered = [c.lower() for c in col_names]
        if len(set(lowered)) != len(lowered):
            errors.append('Duplicate column names detected (case-insensitive). Column names must be unique.')

        def is_numeric_like(s: str) -> bool:
            try:
                float(s.replace(',', ''))
                return True
            except Exception:
                return False

        numeric_like_count = sum(1 for c in col_names if is_numeric_like(c))
        if df.shape[1] > 0 and numeric_like_count >= max(1, int(0.6 * df.shape[1])):
            errors.append('First row appears to be data, not headers. Please include a header row as the first line.')

        rows, cols = df.shape
        if cols > 30:
            errors.append('Too many columns. Maximum allowed is 30.')
        if rows > 500000:
            errors.append('Too many rows. Maximum allowed is 500000.')

        base64_regex = re.compile(r'^[A-Za-z0-9+/=\r\n]+$')

        def looks_like_json(text: str) -> bool:
            text = text.strip()
            if not text or (text[0] not in '{['):
                return False
            if len(text) > 20000:
                return True
            try:
                json.loads(text)
                return True
            except Exception:
                return False

        def looks_like_base64_blob(text: str) -> bool:
            if len(text) < 1000:
                return False
            compact = ''.join(ch for ch in text if not ch.isspace())
            if not base64_regex.match(compact):
                return False
            if len(compact) > 5000:
                return True
            return False

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
            pass

        valid = len(errors) == 0

        if valid:
            try:
                input_data_dir = os.path.join('execution_layer', 'input_data', session_id)
                os.makedirs(input_data_dir, exist_ok=True)
                base_filename = filename.rsplit('.', 1)[0] if '.' in filename else filename
                pkl_filename = f"{base_filename}.pkl"
                pkl_path = os.path.join(input_data_dir, pkl_filename)
                df.to_pickle(pkl_path)
                return jsonify({'valid': True, 'message': 'validation successful', 'saved_file': pkl_filename}), 200
            except Exception as e:
                return jsonify({'valid': False, 'message': 'validation failed', 'error': f'Failed to save file: {str(e)}'}), 500
        else:
            primary_error = errors[0] if errors else 'Validation failed'
            return fail(primary_error, 400)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'valid': False, 'message': 'validation failed', 'error': f'Unexpected error during validation: {str(e)}'}), 500


@data_bp.route('/generate_domain_dictionary', methods=['POST'])
def generate_domain_dictionary():
    try:
        def fail(msg: str, status: int = 400):
            return jsonify({'error': msg}), status

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

        rows, cols = df.shape
        columns_info = []
        for col in df.columns:
            dtype_str = str(df[col].dtype)
            unique_values = df[col].dropna().unique()
            if len(unique_values) > 10:
                unique_sample = unique_values[:10].tolist()
                unique_count = len(unique_values)
            else:
                unique_sample = unique_values.tolist()
                unique_count = len(unique_values)
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

        from openai import OpenAI
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
        return jsonify({'error': 'Failed to parse LLM response as JSON'}), 500
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Unexpected error: {str(e)}'}), 500


@data_bp.route('/save_domain_dictionary', methods=['POST'])
def save_domain_dictionary():
    try:
        def fail(msg: str, status: int = 400):
            return jsonify({'error': msg}), status

        data = request.get_json()
        if not data:
            return fail('Missing request data', 400)
        domain_dictionary = data.get('domain_dictionary')
        if not domain_dictionary:
            return fail('Missing domain_dictionary in request', 400)

        input_data_dir = os.path.join('execution_layer', 'input_data', data.get('session_id'))
        os.makedirs(input_data_dir, exist_ok=True)
        domain_file_path = os.path.join(input_data_dir, 'domain_directory.json')
        with open(domain_file_path, 'w', encoding='utf-8') as f:
            json.dump(domain_dictionary, f, indent=2, ensure_ascii=False)
        return jsonify({'message': 'Domain dictionary saved successfully', 'file_path': domain_file_path}), 200
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to save domain dictionary: {str(e)}'}), 500


