"""
gmail_web.py — Gmail API wrapper for WEB (Render/cloud).
Uses OAuth 2.0 web flow with refresh tokens stored in DB.
Fixed: send_email returns proper dict, added is_authenticated()
"""

import os
import re
import base64
import json
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta

import requests

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import Flow
    from googleapiclient.discovery import build
except ImportError:
    raise ImportError("Google API libraries not installed. Run: pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client")

SCOPES = [
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/drive.file',
    'https://www.googleapis.com/auth/drive.readonly',
    'https://www.googleapis.com/auth/calendar'
]

class GmailWebClient:
    """Gmail client for web deployment using OAuth 2.0 web flow."""

    def __init__(self, db):
        self.db = db
        self.service = None
        self.is_web = True
        self._authenticate()

    def _get_client_config(self):
        """Build client config from environment variables."""
        client_id = os.environ.get('GOOGLE_CLIENT_ID')
        client_secret = os.environ.get('GOOGLE_CLIENT_SECRET')

        if not client_id or not client_secret:
            raise ValueError("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET environment variables required")

        return {
            "web": {
                "client_id": client_id,
                "project_id": os.environ.get('GOOGLE_PROJECT_ID', 'work-assistant-494216'),
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                "client_secret": client_secret,
                "redirect_uris": [
                    os.environ.get('REDIRECT_URI', 'https://raj-web-app.onrender.com/oauth2callback')
                ]
            }
        }

    def _get_redirect_uri(self):
        return os.environ.get('REDIRECT_URI', 'https://raj-web-app.onrender.com/oauth2callback')

    def _authenticate(self):
        """Try to load existing token from DB."""
        try:
            token_json = self.db.get_meta("gmail_refresh_token")
            if token_json:
                creds_data = json.loads(token_json)
                creds = Credentials.from_authorized_user_info(creds_data, SCOPES)

                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                    self._save_token(creds)

                if creds and creds.valid:
                    self.service = build('gmail', 'v1', credentials=creds)
                    print("[GmailWeb] Authenticated from stored token")
                    return
        except Exception as e:
            print(f"[GmailWeb] No stored token: {e}")

        print("[GmailWeb] No valid token. User needs to connect via /oauth2callback")

    def _save_token(self, creds):
        """Save credentials to database."""
        token_data = {
            'token': creds.token,
            'refresh_token': creds.refresh_token,
            'token_uri': creds.token_uri,
            'client_id': creds.client_id,
            'client_secret': creds.client_secret,
            'scopes': creds.scopes
        }
        self.db.set_meta("gmail_refresh_token", json.dumps(token_data))
        self.db.commit()

    def is_authenticated(self):
        """Check if Gmail is connected and service is valid."""
        return self.service is not None

    def get_auth_url(self):
        """Generate Google OAuth authorization URL."""
        try:
            client_config = self._get_client_config()
            flow = Flow.from_client_config(client_config, SCOPES)
            flow.redirect_uri = self._get_redirect_uri()

            authorization_url, state = flow.authorization_url(
                access_type='offline',
                include_granted_scopes='true',
                prompt='consent'
            )

            self.db.set_meta("gmail_oauth_state", state)
            self.db.commit()

            return authorization_url
        except Exception as e:
            print(f"[GmailWeb] Auth URL error: {e}")
            return None

    def handle_callback(self, code):
        """Handle OAuth callback from Google."""
        try:
            if not code:
                return {"success": False, "error": "No authorization code received"}

            client_config = self._get_client_config()
            flow = Flow.from_client_config(client_config, SCOPES)
            flow.redirect_uri = self._get_redirect_uri()

            flow.fetch_token(code=code)
            creds = flow.credentials

            self._save_token(creds)
            self.service = build('gmail', 'v1', credentials=creds)

            profile = self.service.users().getProfile(userId='me').execute()
            email = profile.get('emailAddress', 'unknown')

            print(f"[GmailWeb] Connected: {email}")
            return {"success": True, "email": email}

        except Exception as e:
            print(f"[GmailWeb] Callback error: {e}")
            return {"success": False, "error": str(e)}

    # ─── Gmail Operations ───

    def send_email(self, to, subject, body_html):
        if not self.service:
            return {"success": False, "error": "Gmail not connected. Please connect via Settings."}
        try:
            message = MIMEText(body_html, 'html', 'utf-8')
            message['to'] = to
            message['subject'] = subject
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
            result = self.service.users().messages().send(userId='me', body={'raw': raw}).execute()
            return {"success": True, "id": result.get('id'), "threadId": result.get('threadId')}
        except Exception as e:
            print(f"[GmailWeb] send_email failed: {e}")
            return {"success": False, "error": str(e)}

    def draft_email(self, to, subject, body_html):
        if not self.service:
            raise RuntimeError("Gmail not connected.")
        message = MIMEText(body_html, 'html', 'utf-8')
        message['to'] = to
        message['subject'] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
        return self.service.users().drafts().create(userId='me', body={'message': {'raw': raw}}).execute()

    def list_drafts(self, max_results=50):
        if not self.service:
            return []
        result = self.service.users().drafts().list(userId='me', maxResults=max_results).execute()
        drafts = result.get('drafts', [])
        out = []
        for d in drafts:
            meta = self.service.users().drafts().get(userId='me', id=d['id'], format='metadata').execute()
            msg = meta.get('message', {})
            subject = ''
            for h in msg.get('payload', {}).get('headers', []):
                if h['name'].lower() == 'subject':
                    subject = h['value']
                    break
            out.append({'id': d['id'], 'subject': subject})
        return out

    def get_draft_full(self, draft_id):
        if not self.service:
            return None
        try:
            draft = self.service.users().drafts().get(userId='me', id=draft_id, format='full').execute()
            msg = draft.get('message', {})
            payload = msg.get('payload', {})
            subject = ''
            for h in payload.get('headers', []):
                if h['name'].lower() == 'subject':
                    subject = h['value']
                    break
            html_body = self._extract_html(payload)
            return {'subject': subject, 'html_body': html_body or ''}
        except Exception as e:
            print(f'[GmailWeb] get_draft_full failed: {e}')
            return None

    def search_messages(self, query, max_results=20):
        if not self.service:
            return []
        try:
            result = self.service.users().messages().list(userId='me', q=query, maxResults=max_results).execute()
            msgs = result.get('messages', [])
            out = []
            for m in msgs:
                full = self.service.users().messages().get(userId='me', id=m['id'], format='full').execute()
                payload = full.get('payload', {})
                headers = payload.get('headers', [])
                from_addr = subject = ''
                for h in headers:
                    n = h['name'].lower()
                    if n == 'from': from_addr = h['value']
                    elif n == 'subject': subject = h['value']
                body = self._extract_text(payload)
                out.append({'id': m['id'], 'threadId': m.get('threadId', ''), 'from': from_addr, 'subject': subject, 'snippet': full.get('snippet', ''), 'body': body or ''})
            return out
        except Exception as e:
            print(f'[GmailWeb] search_messages failed: {e}')
            return []

    def draft_reply(self, thread_id, html_body, subject):
        if not self.service:
            return None
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['In-Reply-To'] = thread_id
            msg['References'] = thread_id
            msg.attach(MIMEText(html_body, 'html', 'utf-8'))
            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode('utf-8')
            body = {'message': {'raw': raw, 'threadId': thread_id}}
            return self.service.users().drafts().create(userId='me', body=body).execute()
        except Exception as e:
            print(f'[GmailWeb] draft_reply failed: {e}')
            return None

    def get_message_full(self, msg_id):
        if not self.service:
            return None
        try:
            full = self.service.users().messages().get(userId='me', id=msg_id, format='full').execute()
            payload = full.get('payload', {})
            headers = payload.get('headers', [])
            from_addr = subject = ''
            for h in headers:
                n = h['name'].lower()
                if n == 'from': from_addr = h['value']
                elif n == 'subject': subject = h['value']
            body = self._extract_text(payload)
            return {'id': msg_id, 'threadId': full.get('threadId', ''), 'from': from_addr, 'subject': subject, 'body': body or ''}
        except Exception as e:
            print(f'[GmailWeb] get_message_full failed: {e}')
            return None

    def trash_message(self, msg_id):
        if not self.service:
            return False
        try:
            self.service.users().messages().trash(userId='me', id=msg_id).execute()
            print(f'[GmailWeb] Trashed message {msg_id[:20]}...')
            return True
        except Exception as e:
            print(f'[GmailWeb] trash_message failed: {e}')
            return False

    def _extract_html(self, payload):
        if payload.get('mimeType') == 'text/html':
            data = payload.get('body', {}).get('data', '')
            if data: return base64.urlsafe_b64decode(data).decode('utf-8', errors='replace')
        for part in payload.get('parts', []):
            r = self._extract_html(part)
            if r: return r
        return ''

    def _extract_text(self, payload):
        mt = payload.get('mimeType', '')
        if mt == 'text/plain':
            data = payload.get('body', {}).get('data', '')
            if data: return base64.urlsafe_b64decode(data).decode('utf-8', errors='replace')
        if mt == 'text/html':
            data = payload.get('body', {}).get('data', '')
            if data: return base64.urlsafe_b64decode(data).decode('utf-8', errors='replace')
        for part in payload.get('parts', []):
            r = self._extract_text(part)
            if r: return r
        return ''
