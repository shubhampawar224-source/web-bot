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

from email.message import EmailMessage
from datetime import datetime, timezone
import logging
import smtplib
import os
import re
from typing import Optional, Dict
from dotenv import load_dotenv
from database.db import SessionLocal
from model.models import Contact
from sqlalchemy.exc import SQLAlchemyError

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

    def _format_human_datetime(self, value):
        if not value:
            return "N/A"
        try:
            if isinstance(value, datetime):
                dt = value
            else:
                s = str(value)
                if s.endswith("Z"):
                    s = s[:-1] + "+00:00"
                dt = datetime.fromisoformat(s)
        except Exception:
            try:
                ts = float(value)
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            except Exception:
                return str(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt_utc = dt.astimezone(timezone.utc)
        return dt_utc.strftime("%a, %d %b %Y %I:%M %p")

    def _valid_email(self, email: Optional[str]) -> bool:
        return bool(email and isinstance(email, str) and self._email_re.match(email))

    def _get_recipient(self, contact: Dict, notify_to: Optional[str] = None) -> str:
        for candidate in (notify_to, contact.get("email"), self.TO_EMAIL, self.FROM_EMAIL):
            if self._valid_email(candidate):
                return candidate
        return ""

    def _build_team_email(self, contact: Dict, notify_to: Optional[str] = None) -> EmailMessage:
        sent_dt = datetime.now(timezone.utc)
        sent_readable = sent_dt.strftime("%a, %d %b %Y %I:%M %p %Z")
        recipient = self._get_recipient(contact, notify_to)

        created_at_readable = self._format_human_datetime(contact.get("created_at"))

        plain_lines = [
            "New contact submission",
            "----------------------",
            f"Name: {contact.get('fname','')} {contact.get('lname','')}",
            f"Email: {contact.get('email','')}",
            f"Phone: {contact.get('phone_number','')}",
            "",
            f"Submitted at: {created_at_readable}",
            f"Email sent at: {sent_readable}",
        ]
        plain_body = "\n".join(plain_lines)

        html_body = f"""\
<!doctype html>
<html>
  <body style="font-family:Arial,Helvetica,sans-serif;background:#f4f6f8;padding:20px;">
    <div style="max-width:680px;margin:0 auto;background:#fff;padding:18px;border-radius:10px;">
      <h2 style="color:#0b79ff;margin:0 0 8px 0;">New contact submission</h2>
      <p style="color:#64748b;margin:0 0 12px 0;">Received {sent_readable}</p>
      <table style="width:100%;border-collapse:collapse;">
        <tr><td style="font-weight:600;padding:6px 8px;">Name</td><td style="padding:6px 8px;">{contact.get('fname','')} {contact.get('lname','')}</td></tr>
        <tr><td style="font-weight:600;padding:6px 8px;">Email</td><td style="padding:6px 8px;"><a href='mailto:{contact.get('email','')}' style='color:#0b79ff'>{contact.get('email','')}</a></td></tr>
        <tr><td style="font-weight:600;padding:6px 8px;">Phone</td><td style="padding:6px 8px;">{contact.get('phone_number','')}</td></tr>
        <tr><td style="font-weight:600;padding:6px 8px;">Submitted at</td><td style="padding:6px 8px;">{created_at_readable}</td></tr>
      </table>
    </div>
  </body>
</html>
"""
        msg = EmailMessage()
        subj = f"New contact: {contact.get('fname','')} {contact.get('lname','')} — {sent_readable}"
        msg["Subject"] = subj
        msg["From"] = self.FROM_EMAIL or ""
        msg["To"] = recipient or ""
        msg.set_content(plain_body)
        msg.add_alternative(html_body, subtype="html")
        return msg

    def _build_user_confirmation_email(self, contact: Dict) -> Optional[EmailMessage]:
        # send confirmation to the user who submitted the form
        user_email = contact.get("email")
        if not self._valid_email(user_email):
            return None

        sent_dt = datetime.now(timezone.utc)
        sent_readable = sent_dt.strftime("%a, %d %b %Y %I:%M %p %Z")
        created_at_readable = self._format_human_datetime(contact.get("created_at"))

        plain = (
            f"Hi {contact.get('fname','')},\n\n"
            "Thank you for contacting us. We have received your details and our team will reach out to you shortly.\n\n"
            f"Submitted at: {created_at_readable}\n\n"
            "If you need immediate assistance, reply to this email.\n\n"
            "Regards,\nTeam"
        )

        html = f"""\
<!doctype html>
<html>
  <body style="font-family:Arial,Helvetica,sans-serif;background:#f9fafb;padding:20px;">
    <div style="max-width:620px;margin:0 auto;background:#fff;padding:18px;border-radius:10px;">
      <h3 style="margin:0 0 8px 0;color:#0b79ff;">Thanks, {contact.get('fname','')}</h3>
      <p style="color:#334155;margin:0 0 12px 0;">We received your submission and our team will reach out to you soon.</p>
      <div style="font-size:13px;color:#64748b;">
        <div>Submitted at: <strong style="color:#0b1320">{created_at_readable}</strong></div>
      </div>
      <div style="margin-top:14px;">
        <a href="mailto:{self.FROM_EMAIL}" style="display:inline-block;padding:10px 14px;background:#0b79ff;color:#fff;border-radius:8px;text-decoration:none;">Contact Support</a>
      </div>
      <p style="font-size:12px;color:#94a3b8;margin-top:14px;">This is an automatic confirmation.</p>
    </div>
  </body>
</html>
"""
        msg = EmailMessage()
        subj = "We've received your message — we'll reach out soon"
        msg["Subject"] = subj
        msg["From"] = self.FROM_EMAIL or ""
        msg["To"] = user_email
        msg.set_content(plain)
        msg.add_alternative(html, subtype="html")
        return msg

    def send_email_sync(self, contact: Dict, notify_to: Optional[str] = None) -> None:
        """
        Send team notification and user confirmation (if user email valid).
        """
        if not self.SMTP_HOST or not self.SMTP_PORT:
            logger.warning("SMTP not configured; skipping email send.")
            return

        team_msg = self._build_team_email(contact, notify_to=notify_to)
        user_msg = self._build_user_confirmation_email(contact)

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

            # send team notification if recipient present
            if team_msg.get("To"):
                try:
                    server.send_message(team_msg)
                    logger.info("Team notification sent to %s", team_msg.get("To"))
                except Exception:
                    logger.exception("Failed sending team notification")

            # send confirmation to user if available
            if user_msg:
                try:
                    server.send_message(user_msg)
                    logger.info("Confirmation email sent to user %s", user_msg.get("To"))
                except Exception:
                    logger.exception("Failed sending confirmation to user")

            server.quit()
        except Exception as e:
            logger.exception("SMTP connection/send failed: %s", e)
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



