"""
Email notification service for releases.
"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


class EmailService:
    """Service for sending email notifications."""

    def __init__(  # noqa: PLR0913
        self,
        smtp_host: str,
        smtp_port: int = 587,
        smtp_user: str | None = None,
        smtp_password: str | None = None,
        from_email: str | None = None,
        *,
        use_tls: bool = True,
    ):
        """
        Initialize email service.

        Args:
            smtp_host: SMTP server hostname
            smtp_port: SMTP server port
            smtp_user: SMTP username (optional)
            smtp_password: SMTP password (optional)
            from_email: From email address
            use_tls: Whether to use TLS
        """
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user
        self.smtp_password = smtp_password
        self.from_email = from_email or "noreply@artana.bio"
        self.use_tls = use_tls

    def send_notification(
        self,
        to_emails: list[str],
        subject: str,
        body: str,
        html_body: str | None = None,
    ) -> bool:
        """
        Send email notification.

        Args:
            to_emails: List of recipient email addresses
            subject: Email subject
            body: Plain text email body
            html_body: Optional HTML email body

        Returns:
            True if sent successfully, False otherwise
        """
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.from_email
            msg["To"] = ", ".join(to_emails)

            # Add plain text part
            text_part = MIMEText(body, "plain")
            msg.attach(text_part)

            # Add HTML part if provided
            if html_body:
                html_part = MIMEText(html_body, "html")
                msg.attach(html_part)

            # Send email
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                if self.use_tls:
                    server.starttls()

                if self.smtp_user and self.smtp_password:
                    server.login(self.smtp_user, self.smtp_password)

                server.send_message(msg)

        except Exception:
            logger.exception("Failed to send email")
            return False
        else:
            logger.info("Email sent successfully to %s", to_emails)
            return True

    def send_release_notification(
        self,
        to_emails: list[str],
        version: str,
        doi: str,
        release_notes: str | None = None,
    ) -> bool:
        """
        Send release notification email.

        Args:
            to_emails: List of recipient email addresses
            version: Release version
            doi: DOI for the release
            release_notes: Optional release notes

        Returns:
            True if sent successfully, False otherwise
        """
        subject = f"New Release: Artana Resource Library v{version}"

        body = f"""
Artana Resource Library Release Notification

Version: {version}
DOI: {doi}

{release_notes or "A new release of the Artana Resource Library is now available."}

Access the release: https://doi.org/{doi}

---
Artana
        """.strip()

        html_body = f"""
        <html>
        <body>
        <h2>Artana Resource Library Release Notification</h2>
        <p><strong>Version:</strong> {version}</p>
        <p><strong>DOI:</strong> <a href="https://doi.org/{doi}">{doi}</a></p>
        <p>{release_notes or "A new release of the Artana Resource Library is now available."}</p>
        <p><a href="https://doi.org/{doi}">Access the release</a></p>
        <hr>
        <p><em>Artana</em></p>
        </body>
        </html>
        """

        return self.send_notification(to_emails, subject, body, html_body)
