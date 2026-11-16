import sqlite3
import json
from contextlib import contextmanager
from pathlib import Path
from app.core.config import settings
from app.core.logging import logger


class BaseRepository:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or settings.DATABASE_PATH
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def get_connection(self) -> sqlite3.Connection:
        """Create a connection with WAL mode and foreign keys enabled."""
        conn = sqlite3.connect(
            self.db_path,
            timeout=15.0,
            check_same_thread=False
        )
        conn.row_factory = sqlite3.Row
        # Enable WAL mode for high concurrency without lockups
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA busy_timeout = 5000;")
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    @contextmanager
    def transaction(self):
        """Context manager for explicit transaction handling."""
        conn = self.get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self):
        """Idempotently setup database tables and indexes."""
        with self.transaction() as conn:
            conn.executescript("""
                -- Trend Signals table
                CREATE TABLE IF NOT EXISTS trend_signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform TEXT NOT NULL,
                    title TEXT NOT NULL,
                    niche TEXT NOT NULL,
                    signal_strength REAL DEFAULT 0,
                    raw_data TEXT,
                    scraped_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                -- Generated Topics table
                CREATE TABLE IF NOT EXISTS generated_topics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id TEXT NOT NULL,
                    niche TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    angle TEXT,
                    hook_type TEXT,
                    inspired_by TEXT,
                    trend_context TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    used INTEGER DEFAULT 0
                );

                -- Reel Scripts table
                CREATE TABLE IF NOT EXISTS reel_scripts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    hook TEXT,
                    body TEXT,
                    cta TEXT,
                    video_prompt TEXT,
                    caption TEXT,
                    hashtags TEXT,
                    quality_score REAL DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                -- Jobs table (Persistent async execution)
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    channel_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'queued',
                    stage TEXT DEFAULT 'init',
                    progress INTEGER DEFAULT 0,
                    payload TEXT,
                    outputs TEXT,
                    failed_reels TEXT,
                    error TEXT,
                    error_type TEXT,
                    backend_used TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    started_at TEXT,
                    completed_at TEXT,
                    duration_seconds REAL DEFAULT 0
                );

                -- Job Stages table
                CREATE TABLE IF NOT EXISTS job_stages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    stage_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    duration_seconds REAL DEFAULT 0,
                    error TEXT,
                    started_at TEXT,
                    completed_at TEXT,
                    FOREIGN KEY (job_id) REFERENCES jobs (job_id) ON DELETE CASCADE
                );

                -- Job Artifacts table
                CREATE TABLE IF NOT EXISTS job_artifacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    artifact_type TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    file_size_mb REAL DEFAULT 0,
                    mime_type TEXT,
                    metadata TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (job_id) REFERENCES jobs (job_id) ON DELETE CASCADE
                );

                -- Channels table (Replaces mutable config.json for custom channels)
                CREATE TABLE IF NOT EXISTS custom_channels (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    niche TEXT NOT NULL,
                    data TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                -- Caption Styles table
                CREATE TABLE IF NOT EXISTS caption_styles (
                    name TEXT PRIMARY KEY,
                    style_data TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                -- Indexes for fast query performance
                CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
                CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at);
                CREATE INDEX IF NOT EXISTS idx_stages_job_id ON job_stages(job_id);
                CREATE INDEX IF NOT EXISTS idx_artifacts_job_id ON job_artifacts(job_id);
                CREATE INDEX IF NOT EXISTS idx_signals_niche ON trend_signals(niche, scraped_at);
            """)
        logger.info("Database initialized successfully with WAL mode.")
