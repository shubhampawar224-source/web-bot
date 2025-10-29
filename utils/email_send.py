import os
import logging
import smtplib
from email.message import EmailMessage
from typing import Optional, Dict
from dotenv import load_dotenv
from database.db import SessionLocal
from model.models import Contact
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime, timezone
import re

load_dotenv(override=False)
logger = logging.getLogger(__name__)

class ContactManager:
    def __init__(self, db_factory=SessionLocal):
        self.db_factory = db_factory
        self.SMTP_HOST = os.getenv("SMTP_HOST")
        self.SMTP_PORT = int(os.getenv("SMTP_PORT") or 0)
        self.SMTP_USER = os.getenv("SMTP_USER")
        self.SMTP_PASS = os.getenv("SMTP_PASS")
        self.FROM_EMAIL = os.getenv("FROM_EMAIL", self.SMTP_USER)
        self.TO_EMAIL = os.getenv("TO_EMAIL")  # default recipient

        # simple email regex for light validation
        self._email_re = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

    def _valid_email(self, email: Optional[str]) -> bool:
        return bool(email and isinstance(email, str) and self._email_re.match(email))

    def _get_recipient(self, contact: Dict, notify_to: Optional[str] = None) -> str:
        """
        Resolve recipient priority:
         1) explicit notify_to passed to method
         2) contact['email'] (the user-provided email)
         3) env TO_EMAIL
         4) FROM_EMAIL as last resort
        """
        for candidate in (notify_to, contact.get("email"), self.TO_EMAIL, self.FROM_EMAIL):
            if self._valid_email(candidate):
                return candidate
        return ""  # no valid recipient found

    def _format_human_datetime(self, value):
        """
        Accepts a datetime or ISO string and returns a human-readable UTC string.
        Falls back to the original value if parsing fails.
        Example output: 'Wed, 29 Oct 2025 02:30 PM UTC'
        """
        if not value:
            return "N/A"
        try:
            # if already a datetime
            if isinstance(value, datetime):
                dt = value
            else:
                # handle common ISO formats (with or without Z)
                s = str(value)
                if s.endswith("Z"):
                    s = s[:-1] + "+00:00"
                dt = datetime.fromisoformat(s)
        except Exception:
            try:
                # last-resort: try parse as float unix timestamp
                ts = float(value)
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            except Exception:
                return str(value)

        # ensure timezone-aware and format to readable UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt_utc = dt.astimezone(timezone.utc)
        return dt_utc.strftime("%a, %d %b %Y %I:%M %p %Z")

    def _build_email(self, contact: Dict, notify_to: Optional[str] = None) -> EmailMessage:
        """
        Build a multipart email with plaintext fallback and a simple responsive HTML template.
        """
        sent_dt = datetime.now(timezone.utc)
        sent_at_readable = sent_dt.strftime("%a, %d %b %Y %I:%M %p %Z")
        created_at_readable = self._format_human_datetime(contact.get("created_at"))

        recipient = self._get_recipient(contact, notify_to)

        # Plain text fallback
        plain_lines = [
            "New contact submission",
            "----------------------",
            f"Name: {contact.get('fname','')} {contact.get('lname','')}",
            f"Email: {contact.get('email','')}",
            f"Phone: {contact.get('phone_number','')}",
            "",
            f"Submitted at: {created_at_readable}",
            f"Email sent at: {sent_at_readable}",
            "",
            "Metadata:",
            str(contact.get("metadata") or {}),
            "",
            "This message was generated automatically."
        ]
        plain_body = "\n".join(plain_lines)

        # HTML template (inline styles for better compatibility)
        html_body = f"""\
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <style>
      body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial; background:#f4f6f8; margin:0; padding:20px; }}
      .card {{ max-width:680px; margin:0 auto; background:#fff; border-radius:10px; padding:20px; box-shadow:0 8px 30px rgba(2,6,23,0.08); }}
      .header {{ display:flex; align-items:center; justify-content:space-between; gap:12px; }}
      .brand {{ font-weight:700; color:#0b79ff; font-size:18px; }}
      .meta {{ color:#64748b; font-size:13px; }}
      .section {{ margin-top:18px; }}
      .label {{ color:#334155; font-weight:600; font-size:13px; margin-bottom:6px; display:block; }}
      .value {{ color:#0b1320; font-size:15px; margin-bottom:8px; }}
      .row {{ display:flex; gap:12px; flex-wrap:wrap; }}
      .chip {{ background:#f1f5f9; padding:8px 10px; border-radius:8px; font-size:13px; color:#0b1320; }}
      .footer {{ margin-top:18px; color:#94a3b8; font-size:12px; text-align:center; }}
      a.button {{ display:inline-block; background:#0b79ff; color:#fff; padding:10px 14px; border-radius:8px; text-decoration:none; font-weight:600; }}
      @media (max-width:480px) {{ .card {{ padding:14px; }} .row {{ flex-direction:column; }} }}
    </style>
  </head>
  <body>
    <div class="card" role="article" aria-label="New contact submission">
      <div class="header">
        <div>
          <div class="brand">Contact Submission</div>
          <div class="meta">Received {sent_at_readable}</div>
        </div>
        <div class="chip">ID: {contact.get('id','-')}</div>
      </div>

      <div class="section">
        <div class="label">Name</div>
        <div class="value">{contact.get('fname','')} {contact.get('lname','')}</div>

        <div class="label">Email</div>
        <div class="value"><a href="mailto:{contact.get('email','')}" style="color:#0b79ff; text-decoration:none;">{contact.get('email','')}</a></div>

        <div class="label">Phone</div>
        <div class="value">{contact.get('phone_number','')}</div>
      </div>

      <div class="section">
        <div class="label">Submitted at</div>
        <div class="value">{created_at_readable}</div>
      </div>

      <div class="section">
        <div class="label">Metadata</div>
        <div class="value" style="white-space:pre-wrap;font-family:monospace;font-size:13px;">{(contact.get('metadata') and str(contact.get('metadata'))) or '-'}</div>
      </div>

      <div class="footer">
        This message was sent automatically. Reply to contact's email to follow up.
      </div>
    </div>
  </body>
</html>
"""

        msg = EmailMessage()
        subject = f"New contact: {contact.get('fname','')} {contact.get('lname','')} — {sent_at_readable}"
        msg["Subject"] = subject
        msg["From"] = self.FROM_EMAIL or ""
        msg["To"] = recipient or ""
        msg.set_content(plain_body)
        msg.add_alternative(html_body, subtype="html")
        return msg

    def send_email_sync(self, contact: Dict, notify_to: Optional[str] = None) -> None:
        """Send email synchronously. Safe to call in background task."""
        if not self.SMTP_HOST or not self.SMTP_PORT:
            logger.warning("SMTP not configured; skipping email send.")
            return

        msg = self._build_email(contact, notify_to=notify_to)
        # If no valid recipient resolved, skip sending
        if not msg.get("To"):
            logger.warning("No valid recipient for contact email; skipping send.")
            return

        try:
            if self.SMTP_PORT == 465:
                server = smtplib.SMTP_SSL(self.SMTP_HOST, self.SMTP_PORT, timeout=30)
            else:
                server = smtplib.SMTP(self.SMTP_HOST, self.SMTP_PORT, timeout=30)
                server.ehlo()
                server.starttls()
                server.ehlo()

            if self.SMTP_USER and self.SMTP_PASS:
                server.login(self.SMTP_USER, self.SMTP_PASS)

            server.send_message(msg)
            server.quit()
            logger.info("Contact email sent to %s for %s %s", msg.get("To"), contact.get("fname"), contact.get("lname"))
        except Exception as e:
            logger.exception("Failed to send contact email: %s", e)

    def save(self, payload: Dict) -> Contact:
        """Save contact to DB and return Contact instance."""
        db = self.db_factory()
        try:
            c = Contact(
                fname=payload.get("fname"),
                lname=payload.get("lname"),
                email=payload.get("email"),
                phone_number=payload.get("phone_number"),
                created_at=payload.get("created_at")  # optional override
            )
            db.add(c)
            db.commit()
            db.refresh(c)
            return c
        except SQLAlchemyError as e:
            db.rollback()
            logger.exception("DB save failed: %s", e)
            raise
        finally:
            db.close()

    def save_and_notify(self, payload: Dict, background_tasks=None, notify_to: Optional[str] = None) -> int:
        """
        Save contact and optionally schedule email notification.
        - payload: dict with contact fields + optional metadata
        - background_tasks: FastAPI BackgroundTasks or None
        Returns saved contact id.
        """
        contact_obj = self.save(payload)
        contact_dict = {
            "id": contact_obj.id,
            "fname": contact_obj.fname,
            "lname": contact_obj.lname,
            "email": contact_obj.email,
            "phone_number": contact_obj.phone_number,
            "created_at": contact_obj.created_at.isoformat() if hasattr(contact_obj.created_at, "isoformat") else str(contact_obj.created_at),
            "metadata": payload.get("metadata", {}),
            "notify_to": notify_to or payload.get("notify_to")
        }

        if background_tasks is not None:
            background_tasks.add_task(self.send_email_sync, contact_dict, notify_to or payload.get("notify_to"))
        else:
            # synchronous fallback
            try:
                self.send_email_sync(contact_dict, notify_to or payload.get("notify_to"))
            except Exception:
                logger.exception("Synchronous email send failed")

        return contact_obj.id



