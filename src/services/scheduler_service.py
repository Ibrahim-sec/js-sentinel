import os
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR
from src.tasks import monitor_urls_task, clean_diff_files_task, clean_content_versions_task

# Configure logging for scheduler
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SchedulerService:
    """Service for managing scheduled monitoring tasks."""
    
    def __init__(self, app=None):
        self.scheduler = None
        self.app = app
        if app:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize scheduler with Flask app context."""
        self.app = app
        
        # Configure job store to use SQLite database
        db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'database', 'scheduler.db')
        jobstores = {
            'default': SQLAlchemyJobStore(url=f'sqlite:///{db_path}')
        }
        
        # Configure executors
        executors = {
            'default': ThreadPoolExecutor(20),
        }
        
        # Job defaults
        job_defaults = {
            'coalesce': False,
            'max_instances': 3
        }
        
        # Create scheduler
        self.scheduler = BackgroundScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone='UTC'
        )
        
        # Add event listeners
        self.scheduler.add_listener(self._job_executed, EVENT_JOB_EXECUTED)
        self.scheduler.add_listener(self._job_error, EVENT_JOB_ERROR)
        
        # Start scheduler
        self.scheduler.start()
        self.add_default_jobs()
        logger.info("Scheduler service initialized and started")
    
    def _job_executed(self, event):
        """Handle job execution events."""
        logger.info(f"Job {event.job_id} executed successfully")
    
    def _job_error(self, event):
        """Handle job error events."""
        logger.error(f"Job {event.job_id} failed: {event.exception}")

    def add_default_jobs(self):
        """Add default monitoring and cleanup jobs."""
        self.add_monitoring_job(
            job_id='monitor_urls',
            interval_minutes=10  # Run every 10 minutes
        )
        self.add_diff_cleanup_job(
            job_id='clean_diff_files',
            hour=2,  # Daily at 2 AM
            minute=0
        )
        self.add_content_cleanup_job(
            job_id='clean_content_versions',
            hour=3,  # Daily at 3 AM
            minute=0
        )

    def add_monitoring_job(self, job_id, interval_minutes=60):
        """Add a monitoring job with specified interval."""
        print(f"DEBUG: add_monitoring_job called with job_id={job_id}, interval_minutes={interval_minutes}")
        
        try:
            print(f"DEBUG: Scheduler exists: {self.scheduler is not None}")
            print(f"DEBUG: Scheduler running: {self.scheduler.running if self.scheduler else False}")
            
            # Check if we can import the task
            try:
                from src.tasks import monitor_urls_task
                print(f"DEBUG: Successfully imported monitor_urls_task")
            except Exception as import_error:
                print(f"DEBUG: Failed to import monitor_urls_task: {import_error}")
                return False
            
            # Add the job WITHOUT passing the app
            print(f"DEBUG: Adding job to scheduler...")
            job = self.scheduler.add_job(
                func=monitor_urls_task,
                # args=[self.app],  # REMOVED: Don't pass app to avoid pickle issues
                trigger='interval',
                minutes=interval_minutes,
                id=job_id,
                replace_existing=True,
                name=f'Monitor Job - {job_id}'
            )
            print(f"DEBUG: Job added successfully: {job.id}")
            
            # Verify it's in the job list
            jobs = self.get_jobs()
            job_found = any(j['id'] == job_id for j in jobs)
            print(f"DEBUG: Job verification - found in list: {job_found}")
            
            logger.info(f"Added monitoring job {job_id} with {interval_minutes} minute interval")
            return True
            
        except Exception as e:
            print(f"DEBUG: Exception in add_monitoring_job: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            logger.error(f"Failed to add monitoring job {job_id}: {e}")
            return False
    
    def add_diff_cleanup_job(self, job_id, hour, minute):
        """Add a job to clean old diff files."""
        try:
            self.scheduler.add_job(
                func=clean_diff_files_task,
                args=[self.app, 90], # Pass the app instance and days_to_keep
                trigger='cron',
                hour=hour,
                minute=minute,
                id=job_id,
                replace_existing=True,
                name=f'Diff Cleanup Job - {job_id}'
            )
            logger.info(f"Added diff cleanup job {job_id} at {hour:02d}:{minute:02d}")
            return True
        except Exception as e:
            logger.error(f"Failed to add diff cleanup job {job_id}: {e}")
            return False

    def add_content_cleanup_job(self, job_id, hour, minute):
        """Add a job to clean old content versions."""
        try:
            self.scheduler.add_job(
                func=clean_content_versions_task,
                args=[self.app, 5], # Pass the app instance and versions_to_keep
                trigger='cron',
                hour=hour,
                minute=minute,
                id=job_id,
                replace_existing=True,
                name=f'Content Cleanup Job - {job_id}'
            )
            logger.info(f"Added content cleanup job {job_id} at {hour:02d}:{minute:02d}")
            return True
        except Exception as e:
            logger.error(f"Failed to add content cleanup job {job_id}: {e}")
            return False

    def remove_job(self, job_id):
        """Remove a scheduled job."""
        try:
            self.scheduler.remove_job(job_id)
            logger.info(f"Removed job {job_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to remove job {job_id}: {e}")
            return False
    
    def get_jobs(self):
        """Get list of all scheduled jobs."""
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                'id': job.id,
                'name': job.name,
                'trigger': str(job.trigger),
                'next_run_time': job.next_run_time.isoformat() if job.next_run_time else None,
                'func': job.func.__name__ if job.func else None
            })
        return jobs
    
    def pause_job(self, job_id):
        """Pause a scheduled job."""
        try:
            self.scheduler.pause_job(job_id)
            logger.info(f"Paused job {job_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to pause job {job_id}: {e}")
            return False
    
    def resume_job(self, job_id):
        """Resume a paused job."""
        try:
            self.scheduler.resume_job(job_id)
            logger.info(f"Resumed job {job_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to resume job {job_id}: {e}")
            return False
    
    def shutdown(self):
        """Shutdown the scheduler."""
        if self.scheduler:
            self.scheduler.shutdown()
            logger.info("Scheduler service shutdown")

# Global scheduler instance
scheduler_service = SchedulerService()


