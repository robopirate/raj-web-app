"""
calendar_integration.py — Google Calendar for Raj v4.0
Schedule meetings from positive replies.
"""

import os
import pickle
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from datetime import datetime, timedelta

SCOPES = ['https://www.googleapis.com/auth/calendar']

class CalendarManager:
    def __init__(self, credentials_path='credentials.json', token_path='calendar_token.pickle'):
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.service = None
        self._authenticate()

    def _authenticate(self):
        creds = None
        if os.path.exists(self.token_path):
            with open(self.token_path, 'rb') as token:
                creds = pickle.load(token)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(self.credentials_path):
                    print("[Calendar] credentials.json not found. Calendar integration disabled.")
                    return
                flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, SCOPES)
                creds = flow.run_local_server(port=0)
            with open(self.token_path, 'wb') as token:
                pickle.dump(creds, token)

        self.service = build('calendar', 'v3', credentials=creds)
        print("[Calendar] Connected to Google Calendar")

    def create_meeting(self, recipient_email, recipient_name, subject, duration_minutes=30, 
                      days_from_now=2, time_hour=10, time_minute=0, description=""):
        """Create a calendar event and send invite."""
        if not self.service:
            return None, "Calendar not connected"

        try:
            start_time = datetime.now() + timedelta(days=days_from_now)
            start_time = start_time.replace(hour=time_hour, minute=time_minute, second=0, microsecond=0)
            end_time = start_time + timedelta(minutes=duration_minutes)

            event = {
                'summary': f'Meeting: {subject}',
                'description': description or f'Meeting with {recipient_name} regarding {subject}',
                'start': {
                    'dateTime': start_time.isoformat(),
                    'timeZone': 'Asia/Kolkata',
                },
                'end': {
                    'dateTime': end_time.isoformat(),
                    'timeZone': 'Asia/Kolkata',
                },
                'attendees': [
                    {'email': recipient_email},
                ],
                'reminders': {
                    'useDefault': False,
                    'overrides': [
                        {'method': 'email', 'minutes': 1440},  # 1 day before
                        {'method': 'popup', 'minutes': 30},
                    ],
                },
            }

            event = self.service.events().insert(calendarId='primary', body=event, sendUpdates='all').execute()

            return {
                'event_id': event['id'],
                'calendar_link': event.get('htmlLink', ''),
                'scheduled_at': start_time.isoformat(),
                'status': 'sent'
            }, None

        except Exception as e:
            return None, str(e)

    def list_upcoming(self, max_results=10):
        """List upcoming meetings."""
        if not self.service:
            return []

        now = datetime.utcnow().isoformat() + 'Z'
        events_result = self.service.events().list(
            calendarId='primary', timeMin=now, maxResults=max_results,
            singleEvents=True, orderBy='startTime').execute()

        return events_result.get('items', [])

    def cancel_event(self, event_id):
        """Cancel a meeting."""
        if not self.service:
            return False

        try:
            self.service.events().delete(calendarId='primary', eventId=event_id, sendUpdates='all').execute()
            return True
        except:
            return False
