import json
import os
import smtplib
import threading
from collections import deque
from datetime import datetime
from email.message import EmailMessage
from urllib.error import URLError
from urllib.request import Request, urlopen


ALERT_KINDS = ("stolen", "unauthorized", "unknown", "full", "unmatched")

TITLES = {
    "stolen": "Stolen vehicle at the gate",
    "unauthorized": "Blocked vehicle tried to enter",
    "unknown": "Unregistered vehicle tried to enter",
    "full": "Car turned away: lot is full",
    "unmatched": "Car left without an entry record",
}


def alert_kind(event):
    """Which alert, if any, an occupancy event should raise."""
    if event["status"] == "entry_rejected":
        return {"STOLEN": "stolen", "UNAUTHORIZED": "unauthorized", "UNKNOWN": "unknown"}.get(
            event.get("security_status")
        )
    if event["status"] == "capacity_full":
        return "full"
    if event["status"] == "unmatched_exit":
        return "unmatched"
    return None


class AlertService:
    """Sends alerts to a webhook (Slack, Discord, ntfy, …) and/or email.

    ALERT_WEBHOOK_URL   POST JSON {"text", "content", "kind", "event"}
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, ALERT_EMAIL_FROM, ALERT_EMAIL_TO
    ALERT_ON            comma list of kinds; default stolen,unauthorized,full
    """

    def __init__(self):
        self.webhook_url = os.getenv("ALERT_WEBHOOK_URL")
        self.smtp_host = os.getenv("SMTP_HOST")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER")
        self.smtp_password = os.getenv("SMTP_PASSWORD")
        self.email_from = os.getenv("ALERT_EMAIL_FROM") or self.smtp_user
        self.email_to = [
            address.strip()
            for address in os.getenv("ALERT_EMAIL_TO", "").split(",")
            if address.strip()
        ]
        enabled = os.getenv("ALERT_ON", "stolen,unauthorized,full")
        self.enabled = {kind.strip() for kind in enabled.split(",") if kind.strip() in ALERT_KINDS}
        self.history = deque(maxlen=100)

    def channels(self):
        channels = []
        if self.webhook_url:
            channels.append("webhook")
        if self.smtp_host and self.email_to:
            channels.append("email")
        return channels

    def status(self):
        return {
            "channels": self.channels(),
            "enabled": sorted(self.enabled),
            "recent": list(self.history)[-20:][::-1],
        }

    def set_enabled(self, kinds):
        unknown = set(kinds) - set(ALERT_KINDS)
        if unknown:
            raise ValueError(f"Unknown alert kinds: {', '.join(sorted(unknown))}")
        self.enabled = set(kinds)

    def notify_event(self, event):
        kind = alert_kind(event)
        if kind is None or kind not in self.enabled:
            return None
        gate = "entry" if event["gate"] == "entry" else "exit"
        message = f"{event['plate_number']} at the {gate} gate."
        return self.send(kind, TITLES[kind], message, event)

    def send(self, kind, title, message, event=None, wait=False):
        record = {
            "kind": kind,
            "title": title,
            "message": message,
            "plate_number": (event or {}).get("plate_number"),
            "created_at": datetime.now().isoformat(),
            "delivery": {channel: "pending" for channel in self.channels()},
        }
        self.history.append(record)

        if record["delivery"]:
            thread = threading.Thread(target=self._deliver, args=(record, event), daemon=True)
            thread.start()
            if wait:
                thread.join(timeout=10)
        return record

    def _deliver(self, record, event):
        if "webhook" in record["delivery"]:
            record["delivery"]["webhook"] = self._post_webhook(record, event)
        if "email" in record["delivery"]:
            record["delivery"]["email"] = self._send_email(record)

    def _post_webhook(self, record, event):
        text = f"{record['title']}: {record['message']}"
        body = json.dumps({
            "text": text,       # Slack, Mattermost, Google Chat
            "content": text,    # Discord
            "kind": record["kind"],
            "event": event,
        }, default=str).encode()
        request = Request(
            self.webhook_url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=5) as response:
                return "sent" if response.status < 300 else f"failed: HTTP {response.status}"
        except (URLError, OSError) as exc:
            return f"failed: {getattr(exc, 'reason', exc)}"

    def _send_email(self, record):
        message = EmailMessage()
        message["Subject"] = f"[Smart Parking] {record['title']}"
        message["From"] = self.email_from
        message["To"] = ", ".join(self.email_to)
        message.set_content(f"{record['message']}\n\nTime: {record['created_at']}")
        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10) as smtp:
                smtp.starttls()
                if self.smtp_user:
                    smtp.login(self.smtp_user, self.smtp_password or "")
                smtp.send_message(message)
            return "sent"
        except (smtplib.SMTPException, OSError) as exc:
            return f"failed: {exc}"
