# scripts/approval_check.py
import os
import time
import secrets
import base64
from email.message import EmailMessage

from supabase import create_client
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

APPROVE_BASE = os.getenv("APPROVAL_BASE_URL")
EMAIL_TO = os.getenv("APPROVAL_EMAIL_TO")
EMAIL_FROM = os.getenv("APPROVAL_GMAIL_FROM")

GMAIL_CLIENT_ID = os.getenv("GMAIL_CLIENT_ID")
GMAIL_CLIENT_SECRET = os.getenv("GMAIL_CLIENT_SECRET")
GMAIL_REFRESH_TOKEN = os.getenv("GMAIL_REFRESH_TOKEN")

sb = create_client(SUPABASE_URL, SUPABASE_KEY)

def generate_code():
    return secrets.token_urlsafe(24)

def create_approval_row(code, ttl_hours=8):
    expires_at = int(time.time() + ttl_hours * 3600)
    payload = {
        "code": code,
        "approved": False,
        "expires_at": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(expires_at))
    }
    sb.table("approvals").insert(payload).execute()

def send_email(link):
    creds = Credentials(
        None,
        refresh_token=GMAIL_REFRESH_TOKEN,
        client_id=GMAIL_CLIENT_ID,
        client_secret=GMAIL_CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/gmail.send"],
    )

    service = build("gmail", "v1", credentials=creds)

    msg = EmailMessage()
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO
    msg["Subject"] = "SPACEAPP: Approve satellite update"
    msg.set_content(
        f"Click to approve the update:\n\n{link}\n\nIgnore if unexpected."
    )

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

    service.users().messages().send(
        userId="me",
        body={"raw": raw}
    ).execute()

def wait_for_approval(code, timeout=3600*6, poll_interval=30):
    deadline = time.time() + timeout

    while time.time() < deadline:
        res = sb.table("approvals") \
            .select("approved") \
            .eq("code", code) \
            .single() \
            .execute()

        if res.data and res.data.get("approved"):
            print("APPROVED=true")
            return True

        time.sleep(poll_interval)

    print("APPROVED=false")
    return False

def main():
    code = generate_code()
    create_approval_row(code)

    link = f"{APPROVE_BASE}?code={code}"
    send_email(link)

    wait_for_approval(code)

if __name__ == "__main__":
    main()
