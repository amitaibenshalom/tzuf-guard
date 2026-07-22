import logging
import smtplib
from email.message import EmailMessage
from urllib.parse import urlencode

from flask import current_app

logger = logging.getLogger(__name__)


class EmailService:
    def password_reset_url(self, token):
        return f"{current_app.config['PASSWORD_RESET_BASE_URL']}?{urlencode({'token': token})}"

    def send_password_reset(self, user, token):
        reset_url = self.password_reset_url(token)
        smtp_host = current_app.config["SMTP_HOST"]
        if not smtp_host:
            logger.warning(
                "Password reset email not sent because SMTP_HOST is not configured user_id=%s",
                user.id,
            )
            return

        message = EmailMessage()
        message["Subject"] = "Reset your TzufGuard password"
        message["From"] = current_app.config["MAIL_FROM"]
        message["To"] = user.email
        message.set_content(
            "\n".join(
                [
                    "Reset your TzufGuard password using this link:",
                    reset_url,
                    "",
                    "If you did not request this, you can ignore this email.",
                ]
            )
        )

        with smtplib.SMTP(
            smtp_host,
            current_app.config["SMTP_PORT"],
            timeout=10,
        ) as smtp:
            if current_app.config["SMTP_USE_TLS"]:
                smtp.starttls()
            username = current_app.config["SMTP_USERNAME"]
            password = current_app.config["SMTP_PASSWORD"]
            if username and password:
                smtp.login(username, password)
            smtp.send_message(message)


email_service = EmailService()
