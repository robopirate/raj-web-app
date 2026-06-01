"""
gmail.py — Gmail API wrapper for RoboPirate Campaign Agent.
Handles OAuth, sending, drafting, searching, reading.
"""

import os
import re
import base64
import pickle
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
except ImportError:
    raise ImportError("Google API libraries not installed. Run: pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client")

SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
TOKEN_PATH = Path(__file__).parent / "token.pickle"
CREDS_PATH = Path(__file__).parent / "credentials.json"

class GmailClient:
    def __init__(self):
        self.service = None
        self._authenticate()

    def _authenticate(self):
        creds = None
        if TOKEN_PATH.exists():
            with open(TOKEN_PATH, 'rb') as token:
                creds = pickle.load(token)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not CREDS_PATH.exists():
                    raise FileNotFoundError(f"credentials.json not found. Download it from Google Cloud Console and place it here: {CREDS_PATH}")
                flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_PATH), SCOPES)
                creds = flow.run_local_server(port=0)

            with open(TOKEN_PATH, 'wb') as token:
                pickle.dump(creds, token)

        self.service = build('gmail', 'v1', credentials=creds)

    def send_email(self, to, subject, body_html):
        message = MIMEText(body_html, 'html', 'utf-8')
        message['to'] = to
        message['subject'] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
        return self.service.users().messages().send(userId='me', body={'raw': raw}).execute()

    def draft_email(self, to, subject, body_html):
        message = MIMEText(body_html, 'html', 'utf-8')
        message['to'] = to
        message['subject'] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
        return self.service.users().drafts().create(userId='me', body={'message': {'raw': raw}}).execute()

    def list_drafts(self, max_results=50):
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
            print(f'[Gmail] get_draft_full failed: {e}')
            return None

    def search_messages(self, query, max_results=20):
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
            print(f'[Gmail] search_messages failed: {e}')
            return []

    def draft_reply(self, thread_id, html_body, subject):
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
            print(f'[Gmail] draft_reply failed: {e}')
            return None

    def get_message_full(self, msg_id):
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
            print(f'[Gmail] get_message_full failed: {e}')
            return None

    def _extract_html(self, payload):
        if payload.get('mimeType') == 'text/html':
            data = payload.get('body', {}).get('data', '')
            if data: return base64.urlsafe_b64decode(data).decode('utf-8', errors='replace')
        for part in payload.get('parts', []):
            r = self._extract_html(part)
            if r: return r
        return ''


    def trash_message(self, msg_id):
        """Move a message to trash."""
        try:
            self.service.users().messages().trash(userId='me', id=msg_id).execute()
            print(f'[Gmail] Trashed message {msg_id[:20]}...')
            return True
        except Exception as e:
            print(f'[Gmail] trash_message failed: {e}')
            return False

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
