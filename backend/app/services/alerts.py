import html
import json
import os
import smtplib
import threading
from collections import deque
from datetime import datetime
from email.message import EmailMessage
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


ALERT_KINDS = ("stolen", "unauthorized", "unknown", "full", "unmatched")

TITLES = {
    "stolen": "Stolen vehicle at the gate",
    "unauthorized": "Blocked vehicle tried to enter",
    "unknown": "Unregistered vehicle tried to enter",
    "full": "Car turned away: lot is full",
    "unmatched": "Car left without an entry record",
}


# What happened, in words, for each alert kind.
OUTCOMES = {
    "stolen": "Reported stolen. Turned away; the barrier stayed closed.",
    "unauthorized": "Blocked from parking here. Turned away; the barrier stayed closed.",
    "unknown": "Not in the vehicle list. Turned away; the barrier stayed closed.",
    "full": "The lot was full. Turned away; the barrier stayed closed.",
    "unmatched": "Went out, but no entry was recorded for this plate. Check the activity log.",
    "test": "Smart Parking alerts are working.",
}

# ntfy priority, and the colour used by Discord and email (see design.md).
SEVERITY = {
    "stolen": ("urgent", "#c0292f"),
    "unauthorized": ("high", "#c0292f"),
    "unknown": ("high", "#a85d00"),
    "full": ("default", "#a85d00"),
    "unmatched": ("default", "#a85d00"),
    "test": ("low", "#0b57d0"),
}
DEFAULT_SEVERITY = ("default", "#0b57d0")

GATE_NAMES = {"entry": "Entry gate", "exit": "Exit gate"}


def webhook_style(url):
    """Which format the webhook expects, from its address (or ALERT_WEBHOOK_FORMAT)."""
    style = os.getenv("ALERT_WEBHOOK_FORMAT", "auto").lower()
    if style != "auto":
        return style
    host = (urlparse(url).hostname or "").lower()
    if host == "ntfy.sh" or host.startswith("ntfy."):
        return "ntfy"
    if host == "hooks.slack.com":
        return "slack"
    if host in ("discord.com", "discordapp.com"):
        return "discord"
    return "json"


def alert_details(record, event=None):
    """The facts of an alert as (label, value) rows, shared by every channel."""
    event = event or {}
    rows = []
    if record.get("plate_number"):
        rows.append(("Plate", record["plate_number"]))
    if event.get("gate") in GATE_NAMES:
        rows.append(("Gate", GATE_NAMES[event["gate"]]))
    if event.get("slot_id"):
        rows.append(("Space", event["slot_id"]))
    created = datetime.fromisoformat(record["created_at"])
    rows.append(("Time", created.strftime("%d %b %Y, %H:%M:%S")))
    rows.append(("What happened", OUTCOMES.get(record["kind"], record["message"])))
    return rows


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

    ALERT_WEBHOOK_URL   ntfy, Slack and Discord each get their own format (from the
                        address, or set ALERT_WEBHOOK_FORMAT); anything else gets
                        JSON {"text", "content", "title", "details", "kind", "event"}
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
        gate = GATE_NAMES.get(event["gate"], "Exit gate").lower()
        message = f"{event['plate_number']} at the {gate}."
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
            record["delivery"]["email"] = self._send_email(record, event)

    def _post_webhook(self, record, event):
        rows = alert_details(record, event)
        style = webhook_style(self.webhook_url)
        priority, color = SEVERITY.get(record["kind"], DEFAULT_SEVERITY)
        headers = {"Content-Type": "application/json"}

        if style == "ntfy":
            # ntfy shows the body as the notification text, so it gets plain
            # text, with the title and urgency in headers.
            body = "\n".join(f"{label}: {value}" for label, value in rows).encode()
            headers = {
                "Content-Type": "text/plain; charset=utf-8",
                "Title": record["title"],
                "Priority": priority,
                "Tags": f"smart-parking,{record['kind']}",
            }
        elif style == "slack":
            lines = "\n".join(f"*{label}:* {value}" for label, value in rows)
            body = {"text": f"*{record['title']}*\n{lines}"}
        elif style == "discord":
            body = {"embeds": [{
                "title": record["title"],
                "color": int(color.lstrip("#"), 16),
                "fields": [
                    {"name": label, "value": str(value), "inline": label != "What happened"}
                    for label, value in rows
                ],
                "footer": {"text": "Smart Parking"},
            }]}
        else:
            summary = f"{record['title']}: {record['message']}"
            body = {
                "text": summary,      # Slack-compatible tools, Mattermost, Google Chat
                "content": summary,   # Discord-compatible tools
                "title": record["title"],
                "details": dict(rows),
                "kind": record["kind"],
                "event": event,
            }
        if not isinstance(body, bytes):
            body = json.dumps(body, default=str).encode()

        request = Request(self.webhook_url, data=body, headers=headers, method="POST")
        try:
            with urlopen(request, timeout=5) as response:
                return "sent" if response.status < 300 else f"failed: HTTP {response.status}"
        except (URLError, OSError) as exc:
            return f"failed: {getattr(exc, 'reason', exc)}"

    def build_email(self, record, event=None):
        rows = alert_details(record, event)
        color = SEVERITY.get(record["kind"], DEFAULT_SEVERITY)[1]

        message = EmailMessage()
        subject = f"[Smart Parking] {record['title']}"
        if record.get("plate_number"):
            subject += f": {record['plate_number']}"
        message["Subject"] = subject
        message["From"] = self.email_from
        message["To"] = ", ".join(self.email_to)

        width = max(len(label) for label, _ in rows)
        message.set_content(
            f"{record['title']}\n\n"
            + "\n".join(f"{label.ljust(width)}  {value}" for label, value in rows)
            + "\n\nSent by Smart Parking.\n"
        )

        # Inline styles only, since most mail apps drop <style>. Colours follow design.md.
        def value_cell(label, value):
            value = html.escape(str(value))
            if label == "Plate":
                value = (
                    '<span style="font-family:Consolas,monospace;font-weight:600;letter-spacing:0.06em;'
                    'color:#111;background:#fff;border:1.5px solid #111;border-radius:3px;padding:2px 6px">'
                    f"{value}</span>"
                )
            return f'<td style="padding:6px 0;color:#16181d">{value}</td>'

        cells = "".join(
            "<tr>"
            f'<td style="padding:6px 16px 6px 0;color:#5f6470;white-space:nowrap;vertical-align:top">'
            f"{html.escape(label)}</td>{value_cell(label, value)}</tr>"
            for label, value in rows
        )
        message.add_alternative(
            '<div style="font-family:Segoe UI,Roboto,Arial,sans-serif;font-size:15px;line-height:1.5;'
            'background:#f5f4f0;padding:24px">'
            '<div style="max-width:520px;margin:0 auto;background:#fff;border:1px solid #e2e0d9;'
            f'border-top:4px solid {color};border-radius:6px;padding:20px 24px">'
            f'<div style="font-size:18px;font-weight:600;color:{color};margin-bottom:8px">'
            f'{html.escape(record["title"])}</div>'
            f'<table style="border-collapse:collapse">{cells}</table>'
            "</div>"
            '<div style="max-width:520px;margin:12px auto 0;font-size:13px;color:#5f6470">'
            "Sent by Smart Parking.</div>"
            "</div>",
            subtype="html",
        )
        return message

    def _send_email(self, record, event=None):
        message = self.build_email(record, event)
        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10) as smtp:
                smtp.starttls()
                if self.smtp_user:
                    smtp.login(self.smtp_user, self.smtp_password or "")
                smtp.send_message(message)
            return "sent"
        except (smtplib.SMTPException, OSError) as exc:
            return f"failed: {exc}"
