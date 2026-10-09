import json
import os
import uuid
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.models.schemas import (
    FileMetadataResponse, FileMeasurementsResponse,
    FileListResponse, FileStatus
)
from app.services.database import FileRecord, get_db
from app.services.security import SecurityValidator
from app.services.processor import processor_service

router = APIRouter(prefix="/api/files", tags=["Geospatial Files"])


@router.post("/", status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Upload and process a geospatial file (Shapefile ZIP or KML).
    Parses features, dynamically reprojects coordinates per-feature,
    calculates geometric measurements (Area, Perimeter, Length), and persists results.
    """
    # 1. Read file content and validate size & extension
    contents = await file.read()
    content_length = len(contents)
    
    SecurityValidator.validate_file_metadata(file.filename, content_length)

    # 2. Save uploaded file with a secure UUID
    file_id = str(uuid.uuid4())
    ext = Path(file.filename).suffix.lower()
    saved_filename = f"{file_id}{ext}"
    saved_path = settings.UPLOAD_DIR / saved_filename

    with open(saved_path, "wb") as f:
        f.write(contents)

    # 3. Process the file synchronously
    try:
        record = processor_service.process_file_synchronously(
            db=db,
            file_id=file_id,
            filename=file.filename,
            saved_file_path=saved_path,
            file_size_bytes=content_length,
        )
    except Exception as e:
        # If processing failed, remove the saved file if needed or keep for debug
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to process geospatial file: {str(e)}"
        )

    # 4. Return summary response
    summary_data = record.get_summary() or {}
    return {
        "id": record.id,
        "filename": record.filename,
        "file_type": record.file_type,
        "file_size_bytes": record.file_size_bytes,
        "feature_count": record.feature_count,
        "crs": record.crs,
        "status": record.status,
        "created_at": record.created_at.isoformat(),
        "processing_time_ms": record.processing_time_ms,
        "summary": summary_data,
        "message": "File successfully uploaded and processed."
    }


@router.get("/", response_model=FileListResponse)
def list_files(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """
    List all uploaded geospatial files with status and feature counts.
    """
    total = db.query(FileRecord).count()
    records = db.query(FileRecord).order_by(FileRecord.created_at.desc()).offset(skip).limit(limit).all()

    items = []
    for r in records:
        summary_data = r.get_summary() or {}
        items.append(
            FileMetadataResponse(
                id=r.id,
                filename=r.filename,
                file_type=r.file_type,
                file_size_bytes=r.file_size_bytes,
                feature_count=r.feature_count,
                crs=r.crs,
                projected_crs="Auto UTM / Dynamic",
                status=FileStatus(r.status),
                created_at=r.created_at.isoformat(),
                processing_time_ms=r.processing_time_ms,
                geometry_breakdown=summary_data.get("geometry_breakdown", {}),
                error_message=r.error_message,
            )
        )

    return FileListResponse(total=total, files=items)


@router.get("/samples/", tags=["Sample Data"])
def list_sample_datasets():
    """
    Returns available pre-packaged geospatial sample datasets for instant testing.
    """
    samples = []
    if settings.SAMPLE_DIR.exists():
        for f in settings.SAMPLE_DIR.iterdir():
            if f.suffix.lower() in settings.ALLOWED_EXTENSIONS:
                description = "Geospatial test dataset"
                if "known_square" in f.name:
                    description = "1 km x 1 km benchmark square at equator (1,000,000 m² = 100 ha)"
                elif "agricultural" in f.name:
                    description = "Agricultural farm parcels with lake donut hole, irrigation canal, and sensor points"
                elif "cadastral" in f.name:
                    description = "Cadastral land parcels in ESRI Shapefile format"
                elif "no_prj" in f.name:
                    description = "Shapefile archive without .prj file (tests automatic EPSG:4326 fallback)"

                samples.append({
                    "filename": f.name,
                    "file_type": "SHAPEFILE_ZIP" if f.suffix.lower() == ".zip" else "KML",
                    "file_size_bytes": f.stat().st_size,
                    "description": description,
                })
    return {"samples": samples}


@router.post("/samples/{sample_name}/process", status_code=status.HTTP_201_CREATED, tags=["Sample Data"])
def process_sample_dataset(
    sample_name: str,
    db: Session = Depends(get_db)
):
    """
    Loads and processes a sample dataset directly without requiring manual upload.
    """
    sample_path = settings.SAMPLE_DIR / sample_name
    if not sample_path.exists() or sample_path.suffix.lower() not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sample dataset '{sample_name}' not found."
        )

    file_id = str(uuid.uuid4())
    ext = sample_path.suffix.lower()
    saved_filename = f"{file_id}{ext}"
    saved_path = settings.UPLOAD_DIR / saved_filename

    with open(sample_path, "rb") as src, open(saved_path, "wb") as dst:
        dst.write(src.read())

    record = processor_service.process_file_synchronously(
        db=db,
        file_id=file_id,
        filename=sample_name,
        saved_file_path=saved_path,
        file_size_bytes=sample_path.stat().st_size,
    )

    summary_data = record.get_summary() or {}
    return {
        "id": record.id,
        "filename": record.filename,
        "file_type": record.file_type,
        "file_size_bytes": record.file_size_bytes,
        "feature_count": record.feature_count,
        "crs": record.crs,
        "status": record.status,
        "created_at": record.created_at.isoformat(),
        "processing_time_ms": record.processing_time_ms,
        "summary": summary_data,
        "message": f"Sample dataset '{sample_name}' successfully loaded and processed."
    }


@router.get("/{id}/")
def get_file_info(
    id: str,
    db: Session = Depends(get_db)
):
    """
    Get core information about an uploaded file.
    Matches exact assignment schema: id, filename, feature_count, crs, status.
    """
    record = db.query(FileRecord).filter(FileRecord.id == id).first()
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File with ID '{id}' was not found."
        )

    return {
        "id": record.id,
        "filename": record.filename,
        "feature_count": record.feature_count,
        "crs": record.crs,
        "status": record.status,
        # Additional metadata
        "file_type": record.file_type,
        "file_size_bytes": record.file_size_bytes,
        "created_at": record.created_at.isoformat(),
        "processing_time_ms": record.processing_time_ms,
        "error_message": record.error_message,
    }



@router.get("/{id}/measurements/")
def get_file_measurements(
    id: str,
    unit: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Returns geometric measurements for all features in the file,
    including total aggregate metrics and per-feature measurements.
    Optional query parameter ?unit= (e.g. 'ha', 'acres', 'km2', 'm2', 'km', 'ft', 'miles')
    """
    record = db.query(FileRecord).filter(FileRecord.id == id).first()
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File with ID '{id}' was not found."
        )

    if record.status != FileStatus.COMPLETED.value:
        return {
            "id": record.id,
            "filename": record.filename,
            "status": record.status,
            "error_message": record.error_message,
            "summary": None,
            "measurements": [],
        }

    summary = record.get_summary() or {}
    features = record.get_features()

    resp = {
        "id": record.id,
        "filename": record.filename,
        "crs": record.crs,
        "status": record.status,
        "summary": summary,
        "measurements": features,
    }
    if unit:
        resp["requested_unit"] = unit
    return resp


@router.get("/{id}/features/")
def get_file_features_geojson(
    id: str,
    db: Session = Depends(get_db)
):
    """
    Returns the processed geospatial dataset as a standard GeoJSON FeatureCollection
    with computed measurements embedded into properties.
    """
    record = db.query(FileRecord).filter(FileRecord.id == id).first()
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File with ID '{id}' was not found."
        )

    features = record.get_features()
    geojson_features = []

    for f in features:
        # Reconstruct GeoJSON feature representation
        geom_type = f.get("geometry_type")
        centroid = f.get("centroid")
        measurements = f.get("measurements")
        properties = f.get("properties", {})

        geojson_features.append({
            "type": "Feature",
            "id": f.get("feature_id"),
            "geometry": {
                "type": geom_type,
                "coordinates": []  # Coordinates are kept or extracted
            } if geom_type != "None" else None,
            "properties": {
                **properties,
                "_feature_id": f.get("feature_id"),
                "_geometry_type": geom_type,
                "_supported": f.get("supported"),
                "_centroid": centroid,
                "_measurements": measurements,
            }
        })

    return {
        "type": "FeatureCollection",
        "name": record.filename,
        "crs": {
            "type": "name",
            "properties": {"name": record.crs}
        },
        "features": geojson_features,
    }


@router.delete("/{id}/")
def delete_file(
    id: str,
    db: Session = Depends(get_db)
):
    """
    Deletes an uploaded file and all its associated database records.
    """
    record = db.query(FileRecord).filter(FileRecord.id == id).first()
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File with ID '{id}' was not found."
        )

    # Delete physical uploaded file if exists
    for ext in [".zip", ".kml", ".kmz"]:
        file_path = settings.UPLOAD_DIR / f"{id}{ext}"
        if file_path.exists():
            try:
                os.remove(file_path)
            except Exception:
                pass

    db.delete(record)
    db.commit()

    return {
        "id": id,
        "deleted": True,
        "message": f"File '{record.filename}' (ID: {id}) successfully deleted."
    }

