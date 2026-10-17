from .local import LocalDisk
from .s3 import S3Disk, S3Options
from .storage import Disk, Storage, Stored, Uploaded

storage = Storage()

__all__ = ["Disk", "LocalDisk", "S3Disk", "S3Options", "Storage", "Stored", "Uploaded", "storage"]
