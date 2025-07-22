# Create/update src/tasks.py
def monitor_urls_task():
    """Background task to monitor URLs - no app parameter needed"""
    # Import here to avoid circular imports
    from src.main import app
    
    with app.app_context():
        print("DEBUG: Running scheduled monitoring task")
        from src.services.monitor_service import run_monitoring_check
        result = run_monitoring_check()
        print(f"DEBUG: Scheduled monitoring result: {result}")
        return result

def clean_diff_files_task(days_to_keep=90):
    """Background task to clean old diff files"""
    from src.main import app
    
    with app.app_context():
        from src.services.storage_cleanup_service import storage_cleanup_service
        result = storage_cleanup_service.clean_old_diff_files(days_to_keep)
        print(f"DEBUG: Cleaned {result['deleted_count']} diff files")
        return result

def clean_content_versions_task(versions_to_keep=5):
    """Background task to clean old content versions"""
    from src.main import app
    
    with app.app_context():
        from src.services.storage_cleanup_service import storage_cleanup_service
        result = storage_cleanup_service.clean_old_content_versions(versions_to_keep)
        print(f"DEBUG: Cleaned {result['total_deleted_versions']} content versions")
        return result