import requests
import os
from src.services.logger_service import logger_service

notification_logger = logger_service.get_logger("notification")

class NotificationService:
    def __init__(self):
        self.webhook_url = None
        self.app = None

    def init_app(self, app):
        self.app = app
        self.webhook_url = app.config.get("DISCORD_WEBHOOK_URL")
        if not self.webhook_url:
            notification_logger.warning("DISCORD_WEBHOOK_URL not set in config. Discord notifications will not be sent.")

    def send_discord_notification(self, message):
        if not self.webhook_url:
            notification_logger.error("Discord webhook URL is not configured. Cannot send notification.")
            return False

        payload = {
            "content": message,
            "username": "JS Monitor Bot"
        }
        try:
            response = requests.post(self.webhook_url, json=payload, timeout=10)
            response.raise_for_status()
            notification_logger.info(f"Discord notification sent successfully. Status: {response.status_code}")
            return True
        except requests.exceptions.RequestException as e:
            notification_logger.error(f"Failed to send Discord notification: {e}", extra={
                "error": str(e),
                "message_content": message
            })
            return False
        except Exception as e:
            notification_logger.error(f"Unexpected error sending Discord notification: {e}")
            return False

notification_service = NotificationService()

