import os
import base64
from typing import Dict, Any, List, Optional
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

def build_service(credentials_path: str = 'credentials.json', token_path: str = 'token.json'):
    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, 'w') as token:
            token.write(creds.to_json())
    service = build('gmail', 'v1', credentials=creds)
    return service

def ensure_label(service, label_name: str) -> str:
    # return label id
    labels = service.users().labels().list(userId='me').execute().get('labels', [])
    for lb in labels:
        if lb['name'] == label_name:
            return lb['id']
    # create
    created = service.users().labels().create(
        userId='me',
        body={'name': label_name, 'labelListVisibility': 'labelShow', 'messageListVisibility': 'show'}
    ).execute()
    return created['id']

def query_messages(service, q: str, include_labels: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    msgs = []
    page_token = None
    while True:
        resp = service.users().messages().list(
            userId='me', q=q, labelIds=include_labels or [], pageToken=page_token
        ).execute()
        for m in resp.get('messages', []):
            msgs.append(m)
        page_token = resp.get('nextPageToken')
        if not page_token:
            break
    return msgs

def get_message(service, msg_id: str) -> Dict[str, Any]:
    return service.users().messages().get(userId='me', id=msg_id, format='full').execute()

def send_reply(service, thread_id: str, to_addr: str, subject: str, body_text: str, in_reply_to: Optional[str]) -> Dict[str, Any]:
    msg = MIMEText(body_text, 'plain', 'utf-8')
    msg['To'] = to_addr
    msg['Subject'] = subject
    msg['Date'] = formatdate(localtime=True)
    if in_reply_to:
        msg['In-Reply-To'] = in_reply_to
        msg['References'] = in_reply_to
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    return service.users().messages().send(userId='me', body={'raw': raw, 'threadId': thread_id}).execute()

def add_labels(service, msg_id: str, add_label_ids: List[str]):
    service.users().messages().modify(
        userId='me', id=msg_id, body={'addLabelIds': add_label_ids, 'removeLabelIds': []}
    ).execute()

def modify_message(service, msg_id: str, add_label_ids: Optional[List[str]] = None, remove_label_ids: Optional[List[str]] = None):
    service.users().messages().modify(
        userId='me', id=msg_id, body={'addLabelIds': add_label_ids or [], 'removeLabelIds': remove_label_ids or []}
    ).execute()
