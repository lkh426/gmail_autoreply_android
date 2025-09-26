import base64
from email import message_from_bytes
from typing import Tuple, Optional, Dict, Any

def _walk_parts(msg):
    if msg.is_multipart():
        for part in msg.get_payload():
            yield from _walk_parts(part)
    else:
        yield msg

def extract_headers(payload: Dict[str, Any]) -> Dict[str, str]:
    headers = {h['name']: h['value'] for h in payload.get('headers', [])}
    return headers

def extract_plain_and_html(payload: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    # Gmail API returns payload with parts and body.data base64url
    def _decode(data: str) -> str:
        return base64.urlsafe_b64decode(data.encode('utf-8')).decode('utf-8', errors='ignore')

    if 'parts' in payload:
        plain, html = None, None
        for part in payload['parts']:
            mime = part.get('mimeType', '')
            body = part.get('body', {})
            data = body.get('data')
            if not data and 'parts' in part:
                # nested
                p, h = extract_plain_and_html(part)
                plain = plain or p
                html = html or h
                continue
            if data:
                text = _decode(data)
                if mime.startswith('text/plain') and not plain:
                    plain = text
                elif mime.startswith('text/html') and not html:
                    html = text
        return plain, html
    else:
        data = payload.get('body', {}).get('data')
        if data:
            text = base64.urlsafe_b64decode(data.encode('utf-8')).decode('utf-8', errors='ignore')
            mime = payload.get('mimeType', '')
            if mime.startswith('text/html'):
                return None, text
            return text, None
    return None, None
