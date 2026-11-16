from flask import Blueprint, jsonify, request
from pydantic import ValidationError
from app.services.channel_service import ChannelService
from app.schemas.style import StyleCreateRequest
from app.core.exceptions import ValidationException

styles_bp = Blueprint("styles", __name__)


@styles_bp.route("/caption-styles", methods=["GET"])
def get_caption_styles():
    service = ChannelService()
    return jsonify(service.get_all_caption_styles())


@styles_bp.route("/caption-styles", methods=["POST"])
def add_caption_style():
    data = request.get_json(silent=True) or {}
    try:
        req = StyleCreateRequest(**data)
    except ValidationError as e:
        raise ValidationException(
            message=f"Need valid name and style: {e.errors()[0]['msg']}",
            details={"errors": e.errors()}
        )
        
    service = ChannelService()
    service.add_caption_style(req.name, req.style.dict())
    return jsonify({"success": True}), 201
