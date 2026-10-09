from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field


class FileStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class GeometryType(str, Enum):
    POINT = "Point"
    MULTI_POINT = "MultiPoint"
    LINESTRING = "LineString"
    MULTI_LINESTRING = "MultiLineString"
    POLYGON = "Polygon"
    MULTI_POLYGON = "MultiPolygon"
    GEOMETRY_COLLECTION = "GeometryCollection"
    UNKNOWN = "Unknown"


class AreaMeasurements(BaseModel):
    sq_meters: float = Field(..., description="Area in square meters (m²)")
    hectares: float = Field(..., description="Area in hectares (ha)")
    sq_kilometers: float = Field(..., description="Area in square kilometers (km²)")
    acres: float = Field(..., description="Area in acres")
    sq_feet: float = Field(..., description="Area in square feet (ft²)")


class LengthMeasurements(BaseModel):
    meters: float = Field(..., description="Length/Perimeter in meters (m)")
    kilometers: float = Field(..., description="Length/Perimeter in kilometers (km)")
    feet: float = Field(..., description="Length/Perimeter in feet (ft)")
    miles: float = Field(..., description="Length/Perimeter in miles (mi)")


class PolygonMeasurementDetail(BaseModel):
    area: AreaMeasurements
    perimeter: LengthMeasurements
    geodesic_area_sq_meters: Optional[float] = Field(
        None, description="Exact WGS84 geodesic area in square meters"
    )
    geodesic_perimeter_meters: Optional[float] = Field(
        None, description="Exact WGS84 geodesic perimeter in meters"
    )


class LineMeasurementDetail(BaseModel):
    length: LengthMeasurements
    geodesic_length_meters: Optional[float] = Field(
        None, description="Exact WGS84 geodesic length in meters"
    )


class FeatureMeasurement(BaseModel):
    feature_id: Union[str, int]
    geometry_type: str
    supported: bool = Field(
        ..., description="True if geometry supports geometric measurement calculation"
    )
    message: Optional[str] = Field(
        None, description="Status/explanation message (e.g. for unsupported types)"
    )
    measurements: Optional[Union[PolygonMeasurementDetail, LineMeasurementDetail, Dict[str, Any]]] = None
    properties: Dict[str, Any] = Field(default_factory=dict)
    centroid: Optional[List[float]] = Field(
        None, description="Geographic coordinates [longitude, latitude] of centroid"
    )
    bounding_box: Optional[List[float]] = Field(
        None, description="[min_lon, min_lat, max_lon, max_lat]"
    )


class MeasurementsSummary(BaseModel):
    total_features: int
    supported_features_count: int
    unsupported_features_count: int
    total_area_sq_m: float
    total_area_hectares: float
    total_area_acres: float
    total_length_m: float
    total_length_km: float
    geometry_breakdown: Dict[str, int]


class FileMetadataResponse(BaseModel):
    id: str
    filename: str
    file_type: str = Field(..., description="SHAPEFILE_ZIP or KML")
    file_size_bytes: int
    feature_count: int
    crs: str = Field(..., description="Original detected input CRS (e.g. EPSG:4326)")
    projected_crs: str = Field(
        ..., description="Projected CRS used for metric measurement transformation"
    )
    status: FileStatus
    created_at: str
    processing_time_ms: Optional[float] = None
    bounding_box: Optional[List[float]] = None
    geometry_breakdown: Dict[str, int] = Field(default_factory=dict)
    error_message: Optional[str] = None


class FileMeasurementsResponse(BaseModel):
    id: str
    filename: str
    crs: str
    projected_crs: str
    status: FileStatus
    summary: MeasurementsSummary
    measurements: List[FeatureMeasurement]


class FileListResponse(BaseModel):
    total: int
    files: List[FileMetadataResponse]


class HealthResponse(BaseModel):
    status: str
    version: str
    uptime_seconds: float
    files_processed_count: int
    storage_directory: str
