from typing import Optional, List, Dict, Any
from app.repositories.channel_repository import ChannelRepository
from app.schemas.channel import ChannelCreateRequest, ChannelUpdateRequest
from app.core.exceptions import NotFoundException, ConflictException, ValidationException
from genres import list_genres_full, get_genre


class ChannelService:
    def __init__(self, repo: ChannelRepository = None):
        self.repo = repo or ChannelRepository()

    def get_all_channels(self) -> List[Dict[str, Any]]:
        return self.repo.list_channels()

    def get_channel_by_id(self, channel_id: str) -> Dict[str, Any]:
        channel = self.repo.get_channel(channel_id)
        if not channel:
            raise NotFoundException(f"Channel '{channel_id}' not found.")
        return channel

    def create_channel(self, req: ChannelCreateRequest) -> Dict[str, Any]:
        existing = self.repo.get_channel(req.id)
        if existing:
            raise ConflictException(f"Channel ID '{req.id}' already exists.")
        return self.repo.save_channel(req.dict())

    def update_channel(self, channel_id: str, updates: ChannelUpdateRequest) -> Dict[str, Any]:
        existing = self.repo.get_channel(channel_id)
        if not existing:
            raise NotFoundException(f"Channel '{channel_id}' not found.")
            
        update_data = {k: v for k, v in updates.dict().items() if v is not None}
        existing.update(update_data)
        return self.repo.save_channel(existing)

    def delete_channel(self, channel_id: str) -> bool:
        deleted = self.repo.delete_channel(channel_id)
        if not deleted:
            # Check if it was a protected preset
            existing = self.repo.get_channel(channel_id)
            if existing:
                raise ValidationException(f"Cannot delete built-in config/genre channel '{channel_id}'.")
            raise NotFoundException(f"Channel '{channel_id}' not found.")
        return True

    def get_all_caption_styles(self) -> Dict[str, Any]:
        return self.repo.list_caption_styles()

    def add_caption_style(self, name: str, style_dict: dict):
        self.repo.save_caption_style(name, style_dict)

    def get_all_genres(self) -> List[Dict[str, Any]]:
        return list_genres_full()
