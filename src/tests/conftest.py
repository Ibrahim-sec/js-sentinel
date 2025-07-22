import pytest
from src.main import create_app
from src.database import db

@pytest.fixture(scope='function')
def app():
    """Create a fresh app instance for each test"""
    app = create_app(testing=True)
    
    with app.app_context():
        yield app
        
        # Cleanup after test
        db.session.remove()
        db.drop_all()

@pytest.fixture(scope='function')
def client(app):
    return app.test_client()

@pytest.fixture(scope='function') 
def runner(app):
    return app.test_cli_runner()
