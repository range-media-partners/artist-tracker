#!/usr/bin/env python3
"""Send the latest HTML/text report via SMTP.

Required keys in config/config.env:
  SMTP_HOST       e.g. smtp.gmail.com
  SMTP_PORT       e.g. 587
  SMTP_USER       sender address
  SMTP_PASSWORD   sender password / app password
  REPORT_EMAIL_TO comma-separated recipient addresses
"""

import os
import logging
import smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
import storage

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / "config" / "config.env")

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", 25))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
REPORT_EMAIL_TO = os.getenv("REPORT_EMAIL_TO", "")

REPORTS_DIR = BASE_DIR / "reports"
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "send_report.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)


def find_latest_report() -> tuple[Path | None, Path | None]:
    """Download the latest report from Cloud Storage to a local temp location.
    Returns (html_path, txt_path), or (None, None) if not found."""
    tmp_dir = Path("/tmp")
    html_local = tmp_dir / "report_latest.html"
    txt_local = tmp_dir / "report_latest.txt"

    html_ok = storage.download_report("report_latest.html", html_local)
    txt_ok = storage.download_report("report_latest.txt", txt_local)

    if html_ok and txt_ok:
        return html_local, txt_local
    return None, None


def send(html_path: Path, txt_path: Path):
    if not all([SMTP_HOST, SMTP_USER, REPORT_EMAIL_TO]):
        log.error(
            "SMTP config incomplete. Set SMTP_HOST, SMTP_USER, SMTP_PASSWORD, REPORT_EMAIL_TO in config.env"
        )
        return False

    recipients = [r.strip() for r in REPORT_EMAIL_TO.split(",") if r.strip()]
    from datetime import date
    report_date = str(date.today())

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Artist Tracking Report — {report_date}"
    msg["From"] = SMTP_USER
    msg["To"] = ", ".join(recipients)

    with open(txt_path) as f:
        txt_body = f.read()
    with open(html_path) as f:
        html_body = f.read()

    msg.attach(MIMEText(txt_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        log.info("Connecting to %s:%s", SMTP_HOST, SMTP_PORT)
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.ehlo()
            try:
                server.starttls()
                server.ehlo()
            except Exception:
                pass
            if SMTP_PASSWORD: server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, recipients, msg.as_string())
        log.info("Report sent to: %s", ", ".join(recipients))
        return True
    except smtplib.SMTPAuthenticationError:
        log.error("SMTP authentication failed — check SMTP_USER and SMTP_PASSWORD")
    except smtplib.SMTPException as e:
        log.error("SMTP error: %s", e)
    except Exception as e:
        log.error("Unexpected error sending report: %s", e)
    return False


def run():
    html_path, txt_path = find_latest_report()
    if not html_path:
        log.error("No report files found in %s", REPORTS_DIR)
        return False
    log.info("Sending report: %s", html_path.name)
    return send(html_path, txt_path)


if __name__ == "__main__":
    ok = run()
    raise SystemExit(0 if ok else 1)
