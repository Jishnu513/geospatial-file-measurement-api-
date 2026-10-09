import json
import os
import shutil
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from app.config import settings
from app.models.schemas import FileStatus, FeatureMeasurement
from app.services.database import FileRecord
from app.services.parser import parser_service, ParsedFeature
from app.services.measurement import measurement_engine
from app.services.crs_transformer import crs_service


class FileProcessorService:
    @staticmethod
    def process_file_synchronously(
        db: Session,
        file_id: str,
        filename: str,
        saved_file_path: Path,
        file_size_bytes: int,
    ) -> FileRecord:
        """
        Executes end-to-end processing of an uploaded geospatial file.
        Updates FileRecord lifecycle (PENDING -> PROCESSING -> COMPLETED/FAILED).
        """
        start_time = time.perf_counter()
        
        # 1. Fetch or create DB record
        record = db.query(FileRecord).filter(FileRecord.id == file_id).first()
        if not record:
            ext = saved_file_path.suffix.lower()
            file_type = "SHAPEFILE_ZIP" if ext == ".zip" else "KML"
            record = FileRecord(
                id=file_id,
                filename=filename,
                file_type=file_type,
                file_size_bytes=file_size_bytes,
                status=FileStatus.PROCESSING.value,
                created_at=datetime.now(timezone.utc),
            )
            db.add(record)
            db.commit()
        else:
            record.status = FileStatus.PROCESSING.value
            db.commit()

        # Temporary workspace for extraction
        temp_dir = tempfile.mkdtemp(prefix=f"geo_proc_{file_id}_")

        try:
            ext = saved_file_path.suffix.lower()
            features: List[ParsedFeature] = []
            detected_crs = "EPSG:4326"
            crs_warning = None

            # 2. Parse file
            if ext == ".zip":
                features, detected_crs, crs_warning = parser_service.parse_shapefile_zip(
                    saved_file_path, Path(temp_dir)
                )
            elif ext == ".kml":
                features, detected_crs, crs_warning = parser_service.parse_kml(saved_file_path)
            else:
                raise ValueError(f"Unsupported file format '{ext}'")

            # 3. Process measurements for each feature
            measured_features: List[FeatureMeasurement] = []
            geojson_features: List[Dict[str, Any]] = []

            for f in features:
                # If feature had a prior parse error
                if f.error and not f.shapely_geom:
                    m = FeatureMeasurement(
                        feature_id=f.feature_id,
                        geometry_type=f.geometry_type,
                        supported=False,
                        message=f.error,
                        measurements=None,
                        properties=f.properties,
                        centroid=None,
                        bounding_box=None,
                    )
                else:
                    m = measurement_engine.measure_feature(
                        feature_id=f.feature_id,
                        raw_geom=f.shapely_geom,
                        input_crs_str=f.crs,
                        properties=f.properties,
                    )
                
                measured_features.append(m)

                # Prepare GeoJSON feature dictionary
                geojson_feat = {
                    "type": "Feature",
                    "id": f.feature_id,
                    "geometry": f.geojson_geom,
                    "properties": {
                        **f.properties,
                        "_supported": m.supported,
                        "_geometry_type": m.geometry_type,
                        "_measurements": m.measurements.model_dump() if hasattr(m.measurements, "model_dump") else m.measurements,
                    }
                }
                geojson_features.append(geojson_feat)

            # 4. Aggregate metrics across all features
            summary = measurement_engine.aggregate_measurements(measured_features)

            # 5. Measure processing duration
            duration_ms = round((time.perf_counter() - start_time) * 1000.0, 2)

            # 6. Update database record to COMPLETED
            record.status = FileStatus.COMPLETED.value
            record.crs = detected_crs
            record.feature_count = len(measured_features)
            record.processing_time_ms = duration_ms
            record.summary_json = json.dumps(summary.model_dump())
            record.features_json = json.dumps([m.model_dump() for m in measured_features])
            record.error_message = crs_warning

            db.commit()
            db.refresh(record)
            return record

        except Exception as err:
            # Handle processing failure safely
            duration_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
            record.status = FileStatus.FAILED.value
            record.error_message = str(err)
            record.processing_time_ms = duration_ms
            db.commit()
            db.refresh(record)
            raise err

        finally:
            # Safe cleanup of temporary extraction directory
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass


processor_service = FileProcessorService()
