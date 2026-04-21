import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timezone
from . import lore


def send_report(html: str, cfg: dict):
    smtp_cfg = cfg["smtp"]

    host      = os.environ.get("SMTP_HOST")      or smtp_cfg["host"]
    port      = int(os.environ.get("SMTP_PORT")  or smtp_cfg["port"])
    user      = os.environ.get("SMTP_USER")      or smtp_cfg["user"]
    password  = os.environ.get("SMTP_PASSWORD")  or smtp_cfg["password"]
    recipient = os.environ.get("SMTP_RECIPIENT") or smtp_cfg["recipient"]

    if not all([host, user, password, recipient]):
        lore.report_skipped()
        return

    ts      = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    subject = f"Copilot Eval — Model Swap Impact Report — {ts}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = user
    msg["To"]      = recipient
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP(host, port) as s:
        s.ehlo()
        s.starttls()
        s.login(user, password)
        s.send_message(msg)

    lore.report_sent(recipient)
