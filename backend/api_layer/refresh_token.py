import requests
import os

def refresh_google_token(refresh_token: str):
    """Exchange refresh token for new access and ID tokens"""
    try:
        resp = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "refresh_token": refresh_token,
                "client_id": os.getenv("GOOGLE_CLIENT_ID"),
                "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
                "grant_type": "refresh_token"
            }
        )
        if resp.status_code != 200:
            return None
        return resp.json()
    except Exception:
        return None
