from .detection_service import DetectionService
from .file_service import FileService
from .auth_service import AuthService
from .camera_service import CameraRuntimeManager
from .encryption_service import EncryptionService
from .retention_service import RetentionService

file_service = FileService()
detection_service = DetectionService()
encryption_service = EncryptionService()
camera_manager = CameraRuntimeManager(detection_service, file_service)
retention_service = RetentionService(file_service)

__all__ = [
    "FileService",
    "DetectionService",
    "file_service",
    "detection_service",
    "AuthService",
    "CameraRuntimeManager",
    "EncryptionService",
    "camera_manager",
    "encryption_service",
    "RetentionService",
    "retention_service",
]
