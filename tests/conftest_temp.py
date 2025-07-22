import pytest
from src.main import create_app
from src.database import db

@pytest.fixture(scope=\'function\') # Changed scope to function
def app():
    app = create_app()
    app.config[\'TESTING\'] = True
    app.config[\'SQLALCHEMY_DATABASE_URI\'] = \'sqlite:///:memory:\'
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove() # Ensure session is cleared
        db.drop_all()

@pytest.fixture(scope=\'function\')
def client(app):
    return app.test_client()

@pytest.fixture(scope=\'function\')
def runner(app):
    return app.test_cli_runner()


