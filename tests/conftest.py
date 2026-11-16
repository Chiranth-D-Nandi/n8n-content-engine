import os
import tempfile
from pathlib import Path
import pytest

# Create a temporary file for test database
temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
temp_db_path = temp_db.name
temp_db.close()

os.environ["APP_ENV"] = "testing"
os.environ["CELERY_ALWAYS_EAGER"] = "true"
os.environ["VIDEO_BACKEND"] = "MOCK"
os.environ["DATABASE_PATH"] = temp_db_path
os.environ["RATE_LIMIT_PER_MINUTE"] = "100"
os.environ["WHISPER_LOCAL_FALLBACK"] = "false"

from app import create_app
from app.repositories.base import BaseRepository
from app.repositories.job_repository import JobRepository
from app.repositories.channel_repository import ChannelRepository


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    BaseRepository(db_path=temp_db_path)
    yield
    try:
        Path(temp_db_path).unlink(missing_ok=True)
    except Exception:
        pass


@pytest.fixture
def app():
    app = create_app()
    app.config.update({
        "TESTING": True,
    })
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def job_repo():
    return JobRepository(db_path=temp_db_path)


@pytest.fixture
def channel_repo():
    return ChannelRepository(db_path=temp_db_path)
