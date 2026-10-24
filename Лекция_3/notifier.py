# notifier.py
"""Notifier agent – sends summaries via email.

Uses ``smtplib`` with TLS. Credentials are read from the configuration file.
"""

import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict
import logging

# Дочерний логгер – вывод настраивается у родителя «archiv_tracker» (utils.py)
logger = logging.getLogger("archiv_tracker.notifier")


def send_email(subject: str, body: str, email_cfg: Dict) -> bool:
    """Send an email using the provided configuration.

    ``email_cfg`` must contain ``smtp_server``, ``smtp_port``, ``username``,
    ``password``, ``from_address`` and ``to_address``.
    Returns ``True`` on success, ``False`` otherwise.
    """
    try:
        message = MIMEMultipart()
        message["From"] = email_cfg["from_address"]
        message["To"] = email_cfg["to_address"]
        message["Subject"] = subject
        message.attach(MIMEText(body, "plain"))

        context = ssl.create_default_context()
        with smtplib.SMTP(email_cfg["smtp_server"], email_cfg["smtp_port"]) as server:
            server.starttls(context=context)
            server.login(email_cfg["username"], email_cfg["password"])
            server.sendmail(email_cfg["from_address"], email_cfg["to_address"], message.as_string())
        logger.info("Summary email sent successfully.")
        return True
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        return False
