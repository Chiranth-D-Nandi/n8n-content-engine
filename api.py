import os
from app import create_app
from app.core.config import settings

app = create_app()

if __name__ == "__main__":
    print("=" * 60)
    print(f"  {settings.APP_NAME}")
    print(f"  Environment:    {settings.APP_ENV}")
    print(f"  Video Backend:  {settings.VIDEO_BACKEND}")
    print(f"  API Server:     http://localhost:{settings.API_PORT}")
    print(f"  Dashboard:      http://localhost:{settings.API_PORT}/dashboard")
    print(f"  Metrics:        http://localhost:{settings.API_PORT}/metrics")
    print("=" * 60)
    app.run(
        host=settings.API_HOST,
        port=settings.API_PORT,
        debug=settings.DEBUG,
        use_reloader=False,
        threaded=True
    )
