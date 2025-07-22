import os
import zlib
from datetime import datetime
from src.database import db
from src.models.monitor import MonitoredUrl
from src.services.logger_service import logger_service

content_storage_logger = logger_service.get_logger("content_storage")

class ContentStorage:
    def __init__(self):
        self.base_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'content_versions')
        os.makedirs(self.base_dir, exist_ok=True)

    def _get_url_dir(self, url_id):
        return os.path.join(self.base_dir, str(url_id))

    def store_content(self, url_id, content, content_hash):
        url_dir = self._get_url_dir(url_id)
        os.makedirs(url_dir, exist_ok=True)
        
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
        filename = f"{timestamp}_{content_hash}.js.gz"
        file_path = os.path.join(url_dir, filename)
        
        compressed_content = zlib.compress(content.encode("utf-8"))
        
        with open(file_path, "wb") as f:
            f.write(compressed_content)
        
        # FIXED: Changed 'filename' to 'stored_filename' to avoid logging conflict
        content_storage_logger.info(f"Stored new content version for URL ID {url_id}: {filename}", extra={
            "url_id": url_id,
            "stored_filename": filename,
            "content_hash": content_hash,
            "size_bytes": len(compressed_content)
        })
        return file_path

    def get_previous_content(self, url_id):
        url_dir = self._get_url_dir(url_id)
        if not os.path.exists(url_dir):
            return None
        
        # List files and sort by timestamp (filename prefix)
        files = sorted(os.listdir(url_dir), reverse=True)
        
        # The most recent file is the current one, the second most recent is the previous
        if len(files) < 2:
            return None
        
        previous_file_path = os.path.join(url_dir, files[1])
        
        with open(previous_file_path, "rb") as f:
            compressed_content = f.read()
        
        decompressed_content = zlib.decompress(compressed_content).decode("utf-8")
        return decompressed_content

    def clean_old_versions(self, url_id, versions_to_keep=5):
        """Deletes older content versions for a given URL, keeping only the latest N."""
        url_dir = self._get_url_dir(url_id)
        if not os.path.exists(url_dir):
            return 0

        files = sorted(os.listdir(url_dir), reverse=True) # Sort descending by timestamp
        
        deleted_count = 0
        if len(files) > versions_to_keep:
            files_to_delete = files[versions_to_keep:]
            for filename in files_to_delete:
                file_path = os.path.join(url_dir, filename)
                try:
                    os.remove(file_path)
                    deleted_count += 1
                    # FIXED: Changed 'filename' to 'deleted_filename' to avoid logging conflict
                    content_storage_logger.info(f"Deleted old content version for URL ID {url_id}: {filename}", extra={
                        "url_id": url_id,
                        "deleted_filename": filename
                    })
                except Exception as e:
                    # FIXED: Changed 'filename' to 'failed_filename' to avoid logging conflict
                    content_storage_logger.error(f"Error deleting old content version {file_path}: {e}", extra={
                        "url_id": url_id,
                        "failed_filename": filename,
                        "error": str(e)
                    })
        return deleted_count

content_storage = ContentStorage()