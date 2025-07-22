import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
from src.services.storage_cleanup_service import StorageCleanupService
from src.models.monitor import DiffFile, MonitoredUrl
from src.database import db

@pytest.fixture
def storage_cleanup_service_instance(app):
    service = StorageCleanupService()
    service.init_app(app)
    return service

@pytest.fixture(autouse=True)
def mock_logger_service():
    with patch("src.services.logger_service.logger_service") as mock_logger:
        mock_logger.get_logger.return_value = MagicMock()
        yield mock_logger

@pytest.fixture(autouse=True)
def mock_content_storage():
    with patch("src.services.content_storage.content_storage") as mock_storage:
        yield mock_storage

@patch("os.path.exists")
@patch("os.remove")
@patch("src.models.monitor.DiffFile.query")
def test_clean_old_diff_files_success(mock_query, mock_remove, mock_exists, storage_cleanup_service_instance, app):
    # Create mock old diff files
    old_date = datetime.utcnow() - timedelta(days=100)
    mock_diff_file1 = DiffFile(filename="old_diff1.html", file_path="/path/to/old_diff1.html", url_id=1, file_size=100, preview="test")
    mock_diff_file1.created_at = old_date
    
    mock_diff_file2 = DiffFile(filename="old_diff2.html", file_path="/path/to/old_diff2.html", url_id=1, file_size=100, preview="test")
    mock_diff_file2.created_at = old_date
    
    mock_query.filter.return_value.all.return_value = [mock_diff_file1, mock_diff_file2]
    mock_exists.return_value = True
    
    with app.app_context():
        result = storage_cleanup_service_instance.clean_old_diff_files(days_to_keep=90)
    
    assert result["deleted_count"] == 2
    assert mock_remove.call_count == 2

@patch("os.path.exists")
@patch("os.remove")
@patch("src.models.monitor.DiffFile.query")
def test_clean_old_diff_files_file_not_exists(mock_query, mock_remove, mock_exists, storage_cleanup_service_instance, app):
    # Create mock old diff file that doesn't exist on filesystem
    old_date = datetime.utcnow() - timedelta(days=100)
    mock_diff_file = DiffFile(filename="nonexistent_diff.html", file_path="/path/to/nonexistent_diff.html", url_id=1, file_size=100, preview="test")
    mock_diff_file.created_at = old_date
    
    mock_query.filter.return_value.all.return_value = [mock_diff_file]
    mock_exists.return_value = False
    
    with app.app_context():
        result = storage_cleanup_service_instance.clean_old_diff_files(days_to_keep=90)
    
    assert result["deleted_count"] == 1
    mock_remove.assert_not_called()

@patch("os.path.exists")
@patch("os.remove")
@patch("src.models.monitor.DiffFile.query")
def test_clean_old_diff_files_remove_error(mock_query, mock_remove, mock_exists, storage_cleanup_service_instance, app):
    # Create mock old diff file that causes error during removal
    old_date = datetime.utcnow() - timedelta(days=100)
    mock_diff_file = DiffFile(filename="error_diff.html", file_path="/path/to/error_diff.html", url_id=1, file_size=100, preview="test")
    mock_diff_file.created_at = old_date
    
    mock_query.filter.return_value.all.return_value = [mock_diff_file]
    mock_exists.return_value = True
    mock_remove.side_effect = OSError("Permission denied")
    
    with app.app_context():
        result = storage_cleanup_service_instance.clean_old_diff_files(days_to_keep=90)
    
    assert result["deleted_count"] == 0
    mock_remove.assert_called_once()

@patch("src.models.monitor.MonitoredUrl.query")
def test_clean_old_content_versions_success(mock_query, storage_cleanup_service_instance, mock_content_storage, app):
    # Create mock monitored URLs
    mock_url1 = MonitoredUrl(url="http://example.com/1.js", active=True)
    mock_url1.id = 1
    mock_url2 = MonitoredUrl(url="http://example.com/2.js", active=True)
    mock_url2.id = 2
    
    mock_query.all.return_value = [mock_url1, mock_url2]
    mock_content_storage.clean_old_versions.side_effect = [3, 2]
    
    with app.app_context():
        result = storage_cleanup_service_instance.clean_old_content_versions(versions_to_keep=5)
    
    assert result["total_deleted_versions"] == 5
    assert mock_content_storage.clean_old_versions.call_count == 2
    mock_content_storage.clean_old_versions.assert_any_call(1, 5)
    mock_content_storage.clean_old_versions.assert_any_call(2, 5)

@patch("src.models.monitor.MonitoredUrl.query")
def test_clean_old_content_versions_no_urls(mock_query, storage_cleanup_service_instance, mock_content_storage, app):
    mock_query.all.return_value = []
    
    with app.app_context():
        result = storage_cleanup_service_instance.clean_old_content_versions(versions_to_keep=5)
    
    assert result["total_deleted_versions"] == 0
    mock_content_storage.clean_old_versions.assert_not_called()

@patch("src.models.monitor.MonitoredUrl.query")
def test_clean_old_content_versions_no_deletions(mock_query, storage_cleanup_service_instance, mock_content_storage, app):
    # Create mock monitored URLs
    mock_url1 = MonitoredUrl(url="http://example.com/1.js", active=True)
    mock_url1.id = 1
    
    mock_query.all.return_value = [mock_url1]
    mock_content_storage.clean_old_versions.return_value = 0
    
    with app.app_context():
        result = storage_cleanup_service_instance.clean_old_content_versions(versions_to_keep=5)
    
    assert result["total_deleted_versions"] == 0
    mock_content_storage.clean_old_versions.assert_called_once_with(1, 5)