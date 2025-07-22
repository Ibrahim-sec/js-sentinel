import os
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv

from src.database import db
from src.routes.monitor import monitor_bp
from src.routes.user import user_bp
from src.services.scheduler_service import scheduler_service
from src.services.notification_service import notification_service
from src.services.logger_service import logger_service

def create_app(testing=False):
    load_dotenv()
    app = Flask(__name__)
    CORS(app)

    # Configure database based on environment
    if testing:
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    else:
        app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///./database/monitor.db")
        app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    
    # Configure Discord webhook - FIX: Add this line
    app.config["DISCORD_WEBHOOK_URL"] = os.getenv("DISCORD_WEBHOOK_URL")
    
    # Initialize database
    db.init_app(app)

    # Initialize services
    notification_service.init_app(app)
    logger_service.init_app(app)
    
    # Only initialize scheduler in non-testing mode
    if not testing:
        scheduler_service.init_app(app)

    # Create database tables if they don't exist
    with app.app_context():
        db.create_all()

    # Register blueprints - FIXED: Changed from /api/monitor to /api
    app.register_blueprint(monitor_bp, url_prefix="/api")
    app.register_blueprint(user_bp, url_prefix="/api/user")

    # Serve static files (frontend) - only in non-testing mode
    if not testing:
        @app.route("/")
        def serve_index():
            return send_from_directory(os.path.join(app.root_path, "static"), "index.html")

        @app.route("/<path:path>")
        def serve_static(path):
            return send_from_directory(os.path.join(app.root_path, "static"), path)

    @app.errorhandler(404)
    def not_found(error):
        return jsonify({"error": "Not found"}), 404

    return app

# Export app for run_server.py
app = create_app()

if __name__ == "__main__":
    app.run(debug=True)