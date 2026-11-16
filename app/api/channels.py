from flask import Blueprint, jsonify, request
from pydantic import ValidationError
from app.services.channel_service import ChannelService
from app.schemas.channel import ChannelCreateRequest, ChannelUpdateRequest
from app.core.exceptions import ValidationException

channels_bp = Blueprint("channels", __name__)


@channels_bp.route("/channels", methods=["GET"])
def list_channels():
    service = ChannelService()
    return jsonify(service.get_all_channels())


@channels_bp.route("/channels", methods=["POST"])
def add_channel():
    data = request.get_json(silent=True) or {}
    try:
        req = ChannelCreateRequest(**data)
    except ValidationError as e:
        raise ValidationException(
            message=f"Missing or invalid field: {e.errors()[0]['loc'][-1]}",
            details={"errors": e.errors()}
        )
        
    service = ChannelService()
    new_channel = service.create_channel(req)
    return jsonify({"success": True, "channel": new_channel}), 201


@channels_bp.route("/channels/<channel_id>", methods=["PUT"])
def update_channel(channel_id: str):
    data = request.get_json(silent=True) or {}
    try:
        req = ChannelUpdateRequest(**data)
    except ValidationError as e:
        raise ValidationException(
            message=f"Invalid field: {e.errors()[0]['loc'][-1]}",
            details={"errors": e.errors()}
        )
        
    service = ChannelService()
    updated = service.update_channel(channel_id, req)
    return jsonify({"success": True, "channel": updated})


@channels_bp.route("/channels/<channel_id>", methods=["DELETE"])
def delete_channel(channel_id: str):
    service = ChannelService()
    service.delete_channel(channel_id)
    return jsonify({"success": True})
