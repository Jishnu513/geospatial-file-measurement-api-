import os
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import ConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    model_config = ConfigDict(env_prefix="GEO_API_")

    PROJECT_NAME: str = "Geospatial File Measurement API"
    PROJECT_DESCRIPTION: str = (
        "Production-grade backend service for processing geospatial files (Shapefile ZIP & KML), "
        "reprojecting coordinates per feature into optimal UTM zones, and calculating precise "
        "measurements (Area, Perimeter, Length) with geodesic validation."
    )
    PROJECT_VERSION: str = "1.0.0"
    
    # Storage directories
    STORAGE_DIR: Path = BASE_DIR / "storage"
    UPLOAD_DIR: Path = BASE_DIR / "storage" / "uploads"
    SAMPLE_DIR: Path = BASE_DIR / "sample_data"
    
    # Database
    DATABASE_URL: str = f"sqlite:///{BASE_DIR / 'storage' / 'geospatial_api.db'}"
    
    # Security limits
    MAX_UPLOAD_SIZE_BYTES: int = 50 * 1024 * 1024  # 50 MB
    MAX_UNCOMPRESSED_SIZE_BYTES: int = 200 * 1024 * 1024  # 200 MB
    MAX_COMPRESSION_RATIO: float = 20.0
    ALLOWED_EXTENSIONS: set = {".zip", ".kml"}
    
    # CRS defaults
    DEFAULT_GEOGRAPHIC_CRS: str = "EPSG:4326"
    
    # Server settings
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    def init_dirs(self):
        self.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        self.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        self.SAMPLE_DIR.mkdir(parents=True, exist_ok=True)

settings = Settings()
settings.init_dirs()
