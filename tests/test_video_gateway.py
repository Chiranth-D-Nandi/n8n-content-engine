import pytest
from pathlib import Path
from services.video_gateway.gateway import VideoGenerationGateway
from services.video_gateway.backends.mock_backend import MockVideoBackend
from services.video_gateway.backends.remote_backend import RemoteGpuVideoBackend


def test_gateway_factory():
    # 1. Mock backend
    gw_mock = VideoGenerationGateway(backend_type="MOCK")
    assert isinstance(gw_mock._backend, MockVideoBackend)
    status = gw_mock.get_status()
    assert status["status"] == "available"
    assert status["is_mock"] is True

    # 2. Remote backend
    gw_remote = VideoGenerationGateway(backend_type="REAL_REMOTE")
    assert isinstance(gw_remote._backend, RemoteGpuVideoBackend)


def test_mock_generation(tmp_path):
    backend = MockVideoBackend(simulated_delay_seconds=0.1)
    out_file = tmp_path / "mock_test.mp4"
    
    res = backend.generate(
        prompt="A futuristic holographic city with flying vehicles",
        output_path=out_file,
        num_frames=25,
        num_inference_steps=15
    )
    
    assert res.is_mock is True
    assert res.backend == "MOCK"
    assert Path(res.video_path).exists()
    assert res.metadata["steps"] == 15
