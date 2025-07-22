import pytest
from unittest.mock import patch, MagicMock
import requests
from tenacity import RetryError
from src.services.monitor_service import monitor_single_url, run_monitoring_check, generate_ast_hash, download_javascript
from src.models.monitor import MonitoredUrl, DiffFile
from src.database import db
from datetime import datetime

@pytest.fixture(autouse=True)
def mock_logger_service():
    with patch("src.services.logger_service.logger_service") as mock_logger:
        mock_logger.get_logger.return_value = MagicMock()
        yield mock_logger

@pytest.fixture(autouse=True)
def mock_notification_service():
    with patch("src.services.notification_service.notification_service") as mock_notification:
        mock_notification.init_app = MagicMock()
        yield mock_notification

@pytest.fixture(autouse=True)
def mock_content_storage():
    with patch("src.services.content_storage.content_storage") as mock_storage:
        yield mock_storage

@pytest.fixture(autouse=True)
def mock_deobfuscator():
    with patch("src.services.deobfuscator.deobfuscator") as mock_deobf:
        mock_deobf.get_obfuscation_score.return_value = 0.1
        mock_deobf.detect_obfuscation_type.return_value = {}
        mock_deobf.deobfuscate.return_value = ("deobfuscated_content", {})
        yield mock_deobf

@pytest.fixture
def mock_monitored_url():
    url = MonitoredUrl(url="http://example.com/test.js", active=True, last_hash=None)
    url.id = 1
    return url

# Test cases for generate_ast_hash
def test_generate_ast_hash_valid_js():
    js_content = "var a = 1; function b() { return a; }"
    hash1 = generate_ast_hash(js_content)
    hash2 = generate_ast_hash(js_content)
    
    assert hash1 == hash2
    assert hash1 is not None
    assert len(hash1) == 32

def test_generate_ast_hash_invalid_js():
    js_content = "var a = 1; function b() { return a; "
    h = generate_ast_hash(js_content)
    assert h is not None

# Test cases for download_javascript
@patch("requests.get")
def test_download_javascript_success(mock_get):
    mock_response = MagicMock()
    mock_response.text = "console.log('hello');"
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response
    
    content = download_javascript("http://example.com/test.js")
    assert content == "console.log('hello');"
    mock_get.assert_called_once_with("http://example.com/test.js", timeout=30)

@patch("requests.get")
def test_download_javascript_failure(mock_get):
    mock_get.side_effect = requests.exceptions.RequestException("Network error")
    
    with pytest.raises((requests.exceptions.RequestException, RetryError)):
        download_javascript("http://example.com/test.js")

# Test cases for monitor_single_url
def test_monitor_single_url_no_change(app, mock_monitored_url, mock_content_storage):
    with app.app_context():
        db.session.add(mock_monitored_url)
        db.session.commit()
        mock_monitored_url.last_hash = "mock_hash"
        with patch("src.services.monitor_service.download_javascript", return_value="console.log('no change');"), \
             patch("src.services.monitor_service.generate_ast_hash", return_value="mock_hash"):
            result = monitor_single_url(mock_monitored_url)
            assert result["success"] == True
            assert result["changed"] == False
            assert "No changes detected" in result["message"]
            mock_content_storage.store_content.assert_not_called()

def test_monitor_single_url_first_check(app, mock_monitored_url, mock_content_storage):
    with app.app_context():
        db.session.add(mock_monitored_url)
        db.session.commit()
        with patch("src.services.monitor_service.download_javascript", return_value="console.log('first content');"), \
             patch("src.services.monitor_service.generate_ast_hash", return_value="new_hash"):
            result = monitor_single_url(mock_monitored_url)
            assert result["success"] == True
            assert result["changed"] == False
            assert "First check completed" in result["message"]
            mock_content_storage.store_content.assert_called_once()

def test_monitor_single_url_change_detected(app, mock_monitored_url, mock_content_storage, mock_notification_service):
    with app.app_context():
        db.session.add(mock_monitored_url)
        db.session.commit()
        mock_monitored_url.last_hash = "old_hash"
        mock_content_storage.get_previous_content.return_value = "old content"
        with patch("src.services.monitor_service.download_javascript", return_value="console.log('new content');"), \
             patch("src.services.monitor_service.generate_ast_hash", return_value="new_hash"), \
             patch("src.services.monitor_service.generate_enhanced_html_diff", return_value="<html>diff</html>"), \
             patch("src.services.monitor_service.save_diff_file", return_value=MagicMock(filename="diff.html")):
            result = monitor_single_url(mock_monitored_url)
            assert result["success"] == True
            assert result["changed"] == True
            assert "Changes detected" in result["message"]
            mock_content_storage.store_content.assert_called_once()
            mock_content_storage.get_previous_content.assert_called_once()
            mock_notification_service.send_discord_notification.assert_called_once()

def test_monitor_single_url_download_failure(app, mock_monitored_url):
    with app.app_context():
        db.session.add(mock_monitored_url)
        db.session.commit()
        with patch("src.services.monitor_service.download_javascript", return_value=None):
            result = monitor_single_url(mock_monitored_url)
            assert result["success"] == False
            assert "Failed to download" in result["message"]

# Test cases for run_monitoring_check
@patch("src.models.monitor.MonitoredUrl.query")
def test_run_monitoring_check_no_active_urls(mock_query, app):
    with app.app_context():
        mock_query.filter_by.return_value.all.return_value = []
        result = run_monitoring_check()
        assert result["message"] == "No active URLs to monitor"
        assert result["changes_detected"] == False
        assert result["urls_checked"] == 0

@patch("src.models.monitor.MonitoredUrl.query")
@patch("src.services.monitor_service.monitor_single_url")
def test_run_monitoring_check_with_changes(mock_monitor_single_url, mock_query, app):
    with app.app_context():
        mock_url1 = MagicMock(url="http://example.com/1.js", active=True)
        mock_url2 = MagicMock(url="http://example.com/2.js", active=True)
        mock_query.filter_by.return_value.all.return_value = [mock_url1, mock_url2]
        
        mock_monitor_single_url.side_effect = [
            {"success": True, "message": "No change", "changed": False},
            {"success": True, "message": "Change detected", "changed": True}
        ]
        
        result = run_monitoring_check()
        assert result["changes_detected"] == True
        assert result["urls_checked"] == 2
        assert len(result["results"]) == 2

@patch("src.models.monitor.MonitoredUrl.query")
@patch("src.services.monitor_service.monitor_single_url")
def test_run_monitoring_check_no_changes(mock_monitor_single_url, mock_query, app):
    with app.app_context():
        mock_url1 = MagicMock(url="http://example.com/1.js", active=True)
        mock_url2 = MagicMock(url="http://example.com/2.js", active=True)
        mock_query.filter_by.return_value.all.return_value = [mock_url1, mock_url2]
        
        mock_monitor_single_url.side_effect = [
            {"success": True, "message": "No change", "changed": False},
            {"success": True, "message": "No change", "changed": False}
        ]
        
        result = run_monitoring_check()
        assert result["changes_detected"] == False
        assert result["urls_checked"] == 2
        assert len(result["results"]) == 2

@patch("src.models.monitor.MonitoredUrl.query")
@patch("src.services.monitor_service.monitor_single_url")
def test_run_monitoring_check_with_failures(mock_monitor_single_url, mock_query, app):
    with app.app_context():
        mock_url1 = MagicMock(url="http://example.com/1.js", active=True)
        mock_url2 = MagicMock(url="http://example.com/2.js", active=True)
        mock_query.filter_by.return_value.all.return_value = [mock_url1, mock_url2]
        
        mock_monitor_single_url.side_effect = [
            {"success": False, "message": "Failed to download", "changed": False},
            {"success": True, "message": "No change", "changed": False}
        ]
        
        result = run_monitoring_check()
        assert result["changes_detected"] == False
        assert result["urls_checked"] == 2
        assert len(result["results"]) == 2