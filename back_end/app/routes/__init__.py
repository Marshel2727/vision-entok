from .detection_routes import router as detection_router
from .history_routes import router as history_router
from .upload_routes import router as upload_router
from .auth_routes import router as auth_router
from .camera_routes import router as camera_router
from .dashboard_routes import router as dashboard_router
from .event_routes import router as event_router
from .media_routes import router as media_router
from .user_routes import router as user_router

__all__ = [
    "upload_router",
    "detection_router",
    "history_router",
    "auth_router",
    "camera_router",
    "dashboard_router",
    "event_router",
    "media_router",
    "user_router",
]
