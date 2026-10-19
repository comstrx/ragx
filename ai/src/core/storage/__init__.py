from core.fs import S3Options

from .disk import Disk, LocalDisk, S3Disk, Stored, Uploaded
from .storage import Storage

storage = Storage()

__all__ = ["Disk", "LocalDisk", "S3Disk", "S3Options", "Storage", "Stored", "Uploaded", "storage"]
