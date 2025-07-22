import logging
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler

class LoggerService:
    """Centralized logging service for the application."""
    
    def __init__(self, app=None):
        self.app = app
        if app is not None:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize logging for the Flask app."""
        self.app = app
        
        # Create logs directory if it doesn't exist
        logs_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
        os.makedirs(logs_dir, exist_ok=True)
        
        # Configure logging level
        log_level = app.config.get('LOG_LEVEL', 'INFO')
        numeric_level = getattr(logging, log_level.upper(), logging.INFO)
        
        # Create formatters
        detailed_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
        )
        
        simple_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s'
        )
        
        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(numeric_level)
        
        # Remove existing handlers to avoid duplicates
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        
        # File handler for general application logs
        app_log_file = os.path.join(logs_dir, 'app.log')
        app_handler = RotatingFileHandler(
            app_log_file, 
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
        app_handler.setLevel(numeric_level)
        app_handler.setFormatter(detailed_formatter)
        root_logger.addHandler(app_handler)
        
        # File handler for monitoring-specific logs
        monitor_log_file = os.path.join(logs_dir, 'monitor.log')
        monitor_handler = RotatingFileHandler(
            monitor_log_file,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
        monitor_handler.setLevel(numeric_level)
        monitor_handler.setFormatter(detailed_formatter)
        
        # Create monitor logger
        monitor_logger = logging.getLogger('monitor')
        monitor_logger.addHandler(monitor_handler)
        monitor_logger.setLevel(numeric_level)
        monitor_logger.propagate = False  # Don't propagate to root logger
        
        # File handler for error logs
        error_log_file = os.path.join(logs_dir, 'error.log')
        error_handler = RotatingFileHandler(
            error_log_file,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(detailed_formatter)
        root_logger.addHandler(error_handler)
        
        # Console handler for development
        if app.config.get('DEBUG', False):
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.DEBUG)
            console_handler.setFormatter(simple_formatter)
            root_logger.addHandler(console_handler)
        
        # Set Flask's logger to use our configuration
        app.logger.handlers = []
        app.logger.propagate = True
        
        app.logger.info('Logging system initialized')
    
    @staticmethod
    def get_logger(name='app'):
        """Get a logger instance."""
        return logging.getLogger(name)
    
    @staticmethod
    def log_monitoring_event(url, event_type, message, extra_data=None):
        """Log monitoring-specific events."""
        logger = logging.getLogger('monitor')
        
        log_data = {
            'url': url,
            'event_type': event_type,
            'timestamp': datetime.utcnow().isoformat(),
            'message': message
        }
        
        if extra_data:
            log_data.update(extra_data)
        
        if event_type == 'error':
            logger.error(f"[{event_type.upper()}] {url}: {message}", extra=log_data)
        elif event_type == 'warning':
            logger.warning(f"[{event_type.upper()}] {url}: {message}", extra=log_data)
        elif event_type == 'change_detected':
            logger.info(f"[CHANGE] {url}: {message}", extra=log_data)
        else:
            logger.info(f"[{event_type.upper()}] {url}: {message}", extra=log_data)
    
    @staticmethod
    def log_error(error, context=None):
        """Log errors with context information."""
        logger = logging.getLogger('app')
        
        error_data = {
            'error_type': type(error).__name__,
            'error_message': str(error),
            'timestamp': datetime.utcnow().isoformat()
        }
        
        if context:
            error_data['context'] = context
        
        logger.error(f"Error occurred: {error}", extra=error_data, exc_info=True)
    
    @staticmethod
    def log_performance(operation, duration, url=None, extra_data=None):
        """Log performance metrics."""
        logger = logging.getLogger('monitor')
        
        perf_data = {
            'operation': operation,
            'duration_seconds': duration,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        if url:
            perf_data['url'] = url
        
        if extra_data:
            perf_data.update(extra_data)
        
        logger.info(f"[PERFORMANCE] {operation}: {duration:.2f}s", extra=perf_data)

# Global logger service instance
logger_service = LoggerService()

