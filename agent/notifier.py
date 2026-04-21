import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timezone
from . import lore
from . import logger as logger_mod


def send_report(html: str, cfg: dict):
    smtp_cfg = cfg.get("smtp", {}) or {}
    log      = logger_mod.get()

    host      = os.environ.get("SMTP_HOST")      or smtp_cfg.get("host", "")
    port      = int(os.environ.get("SMTP_PORT")  or smtp_cfg.get("port") or 587)
    user      = os.environ.get("SMTP_USER")      or smtp_cfg.get("user", "")
    password  = os.environ.get("SMTP_PASSWORD")  or smtp_cfg.get("password", "")
    recipient = os.environ.get("SMTP_RECIPIENT") or smtp_cfg.get("recipient", "")

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

    # Catch SMTP failures locally so a bad host / auth / network doesn't blow
    # up the whole eval cycle — the eval itself has already been persisted.
    try:
        with smtplib.SMTP(host, port) as s:
            s.ehlo()
            s.starttls()
            s.login(user, password)
            s.send_message(msg)
    except Exception as e:
        lore.eval_error("notifier", e)
        log.error(f"Failed to send report email to {recipient}: {e}")
        return

    lore.report_sent(recipient)
