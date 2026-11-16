import pytest
from pathlib import Path
from services.whisper_service.client import WhisperClient


def test_whisper_client_initialization():
    client = WhisperClient(service_url="http://localhost:3000")
    assert client.service_url == "http://localhost:3000"


def test_whisper_file_not_found():
    client = WhisperClient()
    with pytest.raises(FileNotFoundError):
        client.transcribe(Path("non_existent_audio.mp3"))
