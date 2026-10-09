import os
import zipfile
from pathlib import Path
from typing import Tuple
from fastapi import HTTPException, status
from app.config import settings


class SecurityValidator:
    @staticmethod
    def validate_file_metadata(filename: str, content_length: int) -> str:
        """
        Validates file extension and uploaded content length.
        Returns the normalized file extension or raises HTTPException.
        """
        if not filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file must have a valid filename."
            )
        
        ext = Path(filename).suffix.lower()
        if ext not in settings.ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"Unsupported file format '{ext}'. Only .zip (Shapefile) and .kml are supported."
            )

        if content_length > settings.MAX_UPLOAD_SIZE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"File size exceeds maximum allowed limit of {settings.MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)} MB."
            )
            
        return ext

    @staticmethod
    def safe_extract_zip(zip_path: Path, target_dir: Path) -> Tuple[Path, bool]:
        """
        Safely inspects and extracts a zip archive.
        Applies Zip-Slip path traversal protection and Zip-Bomb size verification.
        Returns (shp_file_path, has_prj_file).
        """
        target_dir_real = os.path.realpath(str(target_dir))
        total_uncompressed_size = 0
        compressed_size = os.path.getsize(zip_path)
        
        if not zipfile.is_zipfile(zip_path):
            raise ValueError("The uploaded archive is not a valid ZIP file or is corrupted.")

        with zipfile.ZipFile(zip_path, 'r') as zf:
            # 1. Zip bomb check
            for info in zf.infolist():
                total_uncompressed_size += info.file_size
                if total_uncompressed_size > settings.MAX_UNCOMPRESSED_SIZE_BYTES:
                    raise ValueError(
                        f"Uncompressed archive size exceeds maximum limit of "
                        f"{settings.MAX_UNCOMPRESSED_SIZE_BYTES // (1024 * 1024)} MB."
                    )
            
            if compressed_size > 0:
                ratio = total_uncompressed_size / compressed_size
                if ratio > settings.MAX_COMPRESSION_RATIO and total_uncompressed_size > 10 * 1024 * 1024:
                    raise ValueError("Suspicious compression ratio detected (potential zip bomb).")

            # 2. Strict Zip slip check across ALL archive members
            shp_file = None
            has_prj = False
            for member in zf.namelist():
                dest_path = os.path.realpath(os.path.join(target_dir_real, member))
                
                # Ensure destination stays strictly inside target directory
                if not (dest_path == target_dir_real or dest_path.startswith(target_dir_real + os.sep)):
                    raise ValueError(f"Path traversal detected in archive entry: {member}")

                # Skip macOS metadata files
                if member.startswith("__MACOSX") or member.startswith("./") or Path(member).name.startswith("."):
                    continue

                # Extract member safely
                zf.extract(member, target_dir_real)
                
                if member.lower().endswith(".shp"):
                    shp_file = Path(dest_path)
                elif member.lower().endswith(".prj"):
                    has_prj = True

        if not shp_file or not shp_file.exists():
            raise ValueError("Invalid Shapefile archive: missing required '.shp' file in ZIP.")

        # Check required companion files: .shx and .dbf
        base_name = shp_file.stem
        parent_dir = shp_file.parent
        
        # Check case-insensitively
        existing_files = {f.name.lower(): f for f in parent_dir.iterdir()}
        if f"{base_name.lower()}.shx" not in existing_files:
            raise ValueError(f"Invalid Shapefile archive: missing companion index file '{base_name}.shx'.")
        if f"{base_name.lower()}.dbf" not in existing_files:
            raise ValueError(f"Invalid Shapefile archive: missing companion attribute table '{base_name}.dbf'.")

        return shp_file, has_prj
