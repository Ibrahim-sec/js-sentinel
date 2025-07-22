import pytest
from unittest.mock import patch, MagicMock
import requests
from src.services.notification_service import NotificationService

@pytest.fixture
def notification_service_instance(app):
    service = NotificationService()
    service.init_app(app)
    return service

@patch("requests.post")
def test_send_discord_notification_success(mock_post, notification_service_instance, app):
    with app.app_context():
        app.config["DISCORD_WEBHOOK_URL"] = "http://mock.webhook.url"
        notification_service_instance.webhook_url = "http://mock.webhook.url"
        
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        message = "Test notification"
        result = notification_service_instance.send_discord_notification(message)
        
        assert result == True
        mock_post.assert_called_once_with(
            "http://mock.webhook.url",
            json={
                "content": message,
                "username": "JS Monitor Bot"
            },
            timeout=10
        )

@patch("requests.post")
def test_send_discord_notification_failure(mock_post, notification_service_instance, app):
    with app.app_context():
        app.config["DISCORD_WEBHOOK_URL"] = "http://mock.webhook.url"
        notification_service_instance.webhook_url = "http://mock.webhook.url"
        
        mock_post.side_effect = requests.exceptions.RequestException("Network error")
        
        message = "Test notification"
        result = notification_service_instance.send_discord_notification(message)
        
        assert result == False
        mock_post.assert_called_once()

def test_send_discord_notification_no_webhook_url(notification_service_instance, app):
    with app.app_context():
        app.config["DISCORD_WEBHOOK_URL"] = None
        notification_service_instance.webhook_url = None
        
        with patch("requests.post") as mock_post:
            message = "Test notification"
            result = notification_service_instance.send_discord_notification(message)
            
            assert result == False
            mock_post.assert_not_called()

@patch("requests.post")
def test_send_discord_notification_exception(mock_post, notification_service_instance, app):
    with app.app_context():
        app.config["DISCORD_WEBHOOK_URL"] = "http://mock.webhook.url"
        notification_service_instance.webhook_url = "http://mock.webhook.url"
        
        mock_post.side_effect = Exception("Unexpected error")
        
        message = "Test notification"
        result = notification_service_instance.send_discord_notification(message)
        
        assert result == False
        mock_post.assert_called_once()