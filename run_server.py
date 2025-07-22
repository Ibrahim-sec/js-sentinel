#!/usr/bin/env python3
import os
import sys
from dotenv import load_dotenv

# Add the project root to the path
sys.path.insert(0, os.path.dirname(__file__))

# Load environment variables
load_dotenv()

from src.main import create_app

# Create Flask app
app = create_app()

# Ensure DISCORD_WEBHOOK_URL is in app.config
app.config['DISCORD_WEBHOOK_URL'] = os.getenv('DISCORD_WEBHOOK_URL')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
