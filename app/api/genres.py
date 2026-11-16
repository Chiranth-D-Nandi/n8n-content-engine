from flask import Blueprint, jsonify
from app.services.channel_service import ChannelService

genres_bp = Blueprint("genres", __name__)


@genres_bp.route("/genres", methods=["GET"])
def get_genres():
    """
    Returns full genre catalog required by dashboard onChannelChange().
    """
    service = ChannelService()
    return jsonify(service.get_all_genres())
