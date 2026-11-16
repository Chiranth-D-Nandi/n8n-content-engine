import logging
import json
import time
import uuid
from flask import g, request


class StructuredJsonFormatter(logging.Formatter):
    def format(self, record):
        log_obj = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Inject correlation ID and request metadata if in Flask context
        try:
            if hasattr(g, "request_id"):
                log_obj["request_id"] = g.request_id
            if request:
                log_obj["method"] = request.method
                log_obj["path"] = request.path
                log_obj["remote_addr"] = request.remote_addr
        except RuntimeError:
            pass  # Outside request context
            
        if hasattr(record, "extra_fields"):
            log_obj.update(record.extra_fields)
            
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
            
        return json.dumps(log_obj)


def configure_logging(level=logging.INFO):
    logger = logging.getLogger("matiks")
    logger.setLevel(level)
    
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = StructuredJsonFormatter()
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
    return logger


logger = configure_logging()
