import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from app.repositories.base import BaseRepository
from app.core.config import settings
from genres import GENRE_LIBRARY


class ChannelRepository(BaseRepository):
    def __init__(self, db_path: str = None):
        super().__init__(db_path)
        self._seed_default_styles()

    def _seed_default_styles(self):
        """Seed default styles into database if not present."""
        default_styles = {
            "bold_white": {
                "font": "Arial Black",
                "font_size": 80,
                "primary_color": "#FFFFFF",
                "stroke_color": "#000000",
                "stroke_width": 4,
                "position": "center",
                "bold": True,
                "italic": False
            },
            "bold_yellow": {
                "font": "Arial Black",
                "font_size": 80,
                "primary_color": "#FFFF00",
                "stroke_color": "#000000",
                "stroke_width": 4,
                "position": "center",
                "bold": True,
                "italic": False
            }
        }
        with self.transaction() as conn:
            for name, style in default_styles.items():
                conn.execute(
                    """
                    INSERT OR IGNORE INTO caption_styles (name, style_data)
                    VALUES (?, ?)
                    """,
                    (name, json.dumps(style)),
                )

    def _get_base_config_channels(self) -> List[Dict[str, Any]]:
        config_path = Path("config.json")
        if not config_path.exists():
            return []
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("channels", [])
        except Exception:
            return []

    def list_channels(self) -> List[Dict[str, Any]]:
        """Return combined channels from base config + database overrides."""
        channels_map = {}
        
        # 1. Base config channels
        for ch in self._get_base_config_channels():
            channels_map[ch["id"]] = ch
            
        # 2. Database channels (custom or overrides)
        with self.transaction() as conn:
            cursor = conn.execute("SELECT id, data FROM custom_channels")
            for row in cursor.fetchall():
                ch_data = json.loads(row["data"])
                channels_map[row["id"]] = ch_data
                
        return list(channels_map.values())

    def get_channel(self, channel_id: str) -> Optional[Dict[str, Any]]:
        # 1. Check database
        with self.transaction() as conn:
            cursor = conn.execute("SELECT data FROM custom_channels WHERE id = ?", (channel_id,))
            row = cursor.fetchone()
            if row:
                return json.loads(row["data"])
                
        # 2. Check base config
        for ch in self._get_base_config_channels():
            if ch["id"] == channel_id:
                return ch.copy()
                
        # 3. Check genre library
        if channel_id in GENRE_LIBRARY:
            return GENRE_LIBRARY[channel_id].copy()
            
        return None

    def save_channel(self, channel_data: dict) -> Dict[str, Any]:
        ch_id = channel_data["id"]
        ch_name = channel_data["name"]
        ch_niche = channel_data["niche"]
        
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO custom_channels (id, name, niche, data, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    niche = excluded.niche,
                    data = excluded.data,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (ch_id, ch_name, ch_niche, json.dumps(channel_data)),
            )
        return channel_data

    def delete_channel(self, channel_id: str) -> bool:
        with self.transaction() as conn:
            cursor = conn.execute("DELETE FROM custom_channels WHERE id = ?", (channel_id,))
            return cursor.rowcount > 0

    def list_caption_styles(self) -> Dict[str, Any]:
        styles = {}
        # Read from database
        with self.transaction() as conn:
            cursor = conn.execute("SELECT name, style_data FROM caption_styles")
            for row in cursor.fetchall():
                styles[row["name"]] = json.loads(row["style_data"])
        return styles

    def save_caption_style(self, name: str, style_data: dict):
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO caption_styles (name, style_data)
                VALUES (?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    style_data = excluded.style_data
                """,
                (name, json.dumps(style_data)),
            )
