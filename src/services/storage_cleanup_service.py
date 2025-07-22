from datetime import datetime, timedelta
from src.database import db
from src.models.monitor import DiffFile, MonitoredUrl
from src.services.content_storage import content_storage
from src.services.logger_service import logger_service
import os

cleanup_logger = logger_service.get_logger("cleanup")

class StorageCleanupService:
    def __init__(self):
        self.app = None

    def init_app(self, app):
        self.app = app

    def clean_old_diff_files(self, days_to_keep=90):
        """Deletes diff files older than a specified number of days."""
        cleanup_logger.info(f"Starting cleanup of diff files older than {days_to_keep} days.")
        cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)
        
        old_diff_files = DiffFile.query.filter(DiffFile.created_at < cutoff_date).all()
        
        deleted_count = 0
        for diff_file in old_diff_files:
            try:
                if os.path.exists(diff_file.file_path):
                    os.remove(diff_file.file_path)
                    cleanup_logger.info(f"Deleted diff file: {diff_file.file_path}")
                db.session.delete(diff_file)
                deleted_count += 1
            except Exception as e:
                cleanup_logger.error(f"Error deleting diff file {diff_file.file_path}: {e}", extra={
                    "file_path": diff_file.file_path,
                    "error": str(e)
                })
        
        db.session.commit()
        cleanup_logger.info(f"Finished cleanup. Deleted {deleted_count} old diff files.")
        return {"deleted_count": deleted_count}

    def clean_old_content_versions(self, versions_to_keep=5):
        """Keeps only the latest N versions of content for each monitored URL."""
        cleanup_logger.info(f"Starting cleanup of old content versions, keeping latest {versions_to_keep}.")
        monitored_urls = MonitoredUrl.query.all()
        total_deleted_versions = 0

        for url in monitored_urls:
            deleted_versions = content_storage.clean_old_versions(url.id, versions_to_keep)
            total_deleted_versions += deleted_versions
            if deleted_versions > 0:
                cleanup_logger.info(f"Cleaned {deleted_versions} old content versions for URL ID {url.id}.")
        
        cleanup_logger.info(f"Finished content cleanup. Total deleted versions: {total_deleted_versions}.")
        return {"total_deleted_versions": total_deleted_versions}

storage_cleanup_service = StorageCleanupService()