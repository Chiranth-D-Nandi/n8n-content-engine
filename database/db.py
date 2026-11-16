import sqlite3
import json
from datetime import datetime
from pathlib import Path


class MatiksDatabase:
    """
    Central database for everything.
    
    Three tables:
    - trend_signals: every scraped trend (YouTube, Reddit, etc.)
    - generated_topics: topics created by LLM
    - reel_scripts: complete scripts ready for production
    """

    def __init__(self, db_path: str = "matiks.db"):
        self.db_path = db_path
        self._setup()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a fresh connection (SQLite connections aren't thread-safe)."""
        conn = sqlite3.connect(self.db_path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    def _setup(self):
        """Create all tables if they don't exist."""
        conn = self._get_connection()

        conn.executescript("""
            CREATE TABLE IF NOT EXISTS trend_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                title TEXT NOT NULL,
                niche TEXT NOT NULL,
                signal_strength REAL DEFAULT 0,
                raw_data TEXT,
                scraped_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

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
        """)
        conn.close()
        print("[Database] Tables ready at matiks.db")

    def store_trend_signal(
        self,
        platform: str,
        title: str,
        niche: str,
        signal_strength: float,
        raw_data: dict
    ) -> int:
        """Store one trend signal."""
        conn = self._get_connection()
        cursor = conn.execute(
            """
            INSERT INTO trend_signals
                (platform, title, niche, signal_strength, raw_data)
            VALUES (?, ?, ?, ?, ?)
            """,
            (platform, title, niche, signal_strength, json.dumps(raw_data))
        )
        signal_id = cursor.lastrowid
        conn.close()
        return signal_id

    def store_topic(
        self,
        channel_id: str,
        niche: str,
        topic: str,
        angle: str,
        hook_type: str,
        inspired_by: str,
        trend_context: str
    ) -> int:
        """Store generated topic."""
        conn = self._get_connection()
        cursor = conn.execute(
            """
            INSERT INTO generated_topics
                (channel_id, niche, topic, angle, hook_type,
                 inspired_by, trend_context)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (channel_id, niche, topic, angle, hook_type, inspired_by, trend_context)
        )
        topic_id = cursor.lastrowid
        conn.close()
        return topic_id

    def store_script(
        self,
        channel_id: str,
        topic: str,
        script: dict
    ) -> int:
        """Store generated script."""
        conn = self._get_connection()
        cursor = conn.execute(
            """
            INSERT INTO reel_scripts
                (channel_id, topic, hook, body, cta,
                 video_prompt, caption, hashtags, quality_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                channel_id,
                topic,
                script.get('hook', ''),
                script.get('body', ''),
                script.get('cta', ''),
                script.get('video_prompt', ''),
                script.get('caption', ''),
                json.dumps(script.get('hashtags', [])),
                script.get('quality_score', 0)
            )
        )
        script_id = cursor.lastrowid
        conn.close()
        return script_id

    def get_recent_signals(self, niche: str, hours: int = 24) -> list:
        """Get trend signals from last N hours."""
        conn = self._get_connection()
        cursor = conn.execute(
            """
            SELECT * FROM trend_signals
            WHERE niche = ?
            AND scraped_at > datetime('now', ? || ' hours')
            ORDER BY signal_strength DESC
            LIMIT 50
            """,
            (niche, f'-{hours}')
        )
        results = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return results

    def get_recent_topics(self, channel_id: str, days: int = 30) -> list:
        """Get topics used in last N days (to avoid repetition)."""
        conn = self._get_connection()
        cursor = conn.execute(
            """
            SELECT topic FROM generated_topics
            WHERE channel_id = ?
            AND created_at > datetime('now', ? || ' days')
            ORDER BY created_at DESC
            """,
            (channel_id, f'-{days}')
        )
        results = [row['topic'] for row in cursor.fetchall()]
        conn.close()
        return results

    def get_all_scripts(self) -> list:
        """Get all generated scripts."""
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT * FROM reel_scripts ORDER BY created_at DESC"
        )
        results = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return results
