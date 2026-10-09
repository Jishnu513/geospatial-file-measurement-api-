import io
import os
import tempfile
import zipfile
from pathlib import Path
import pytest
from fastapi import HTTPException
from shapely.geometry import Polygon
from app.services.security import SecurityValidator
from app.services.measurement import measurement_engine


def test_zip_slip_path_traversal_detection():
    """
    Verifies that a zip archive containing path traversal characters (../)
    is caught and rejected with a security error.
    """
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        # Malicious entry attempting to escape target directory
        zf.writestr("../../../evil.shp", b"malicious data")

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_zip = Path(temp_dir) / "evil.zip"
        with open(temp_zip, "wb") as f:
            f.write(zip_buffer.getvalue())

        extract_dir = Path(temp_dir) / "extracted"
        extract_dir.mkdir()

        with pytest.raises(ValueError, match="Path traversal detected"):
            SecurityValidator.safe_extract_zip(temp_zip, extract_dir)


def test_missing_shp_in_zip():
    """
    Verifies that a zip archive without a .shp file is rejected.
    """
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("test.txt", b"just a text file")

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_zip = Path(temp_dir) / "no_shp.zip"
        with open(temp_zip, "wb") as f:
            f.write(zip_buffer.getvalue())

        extract_dir = Path(temp_dir) / "extracted"
        extract_dir.mkdir()

        with pytest.raises(ValueError, match="missing required '.shp'"):
            SecurityValidator.safe_extract_zip(temp_zip, extract_dir)


def test_missing_companion_shx_dbf():
    """
    Verifies that a zip with .shp but missing .shx or .dbf is rejected.
    """
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("test.shp", b"dummy shp")

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_zip = Path(temp_dir) / "incomplete.zip"
        with open(temp_zip, "wb") as f:
            f.write(zip_buffer.getvalue())

        extract_dir = Path(temp_dir) / "extracted"
        extract_dir.mkdir()

        with pytest.raises(ValueError, match="missing companion"):
            SecurityValidator.safe_extract_zip(temp_zip, extract_dir)


def test_file_size_limit_exceeded_413():
    """
    Verifies that files exceeding 50 MB trigger HTTP 413 Payload Too Large.
    """
    huge_size = 51 * 1024 * 1024
    with pytest.raises(HTTPException) as exc_info:
        SecurityValidator.validate_file_metadata("large.zip", huge_size)
    assert exc_info.value.status_code == 413


def test_unsupported_extension_415():
    """
    Verifies that disallowed extensions trigger HTTP 415 Unsupported Media Type.
    """
    with pytest.raises(HTTPException) as exc_info:
        SecurityValidator.validate_file_metadata("data.geojson", 1000)
    assert exc_info.value.status_code == 415

    with pytest.raises(HTTPException) as exc_info:
        SecurityValidator.validate_file_metadata("script.exe", 1000)
    assert exc_info.value.status_code == 415


def test_self_intersecting_bowtie_polygon_repaired():
    """
    Verifies that an invalid self-intersecting polygon (bowtie) is repaired via make_valid
    and does not crash the measurement engine.
    """
    bowtie = Polygon([(0.0, 0.0), (0.008, 0.008), (0.008, 0.0), (0.0, 0.008), (0.0, 0.0)])
    assert not bowtie.is_valid

    result = measurement_engine.measure_feature("bowtie", bowtie, "EPSG:4326", {})
    assert result.supported is True
    assert result.measurements is not None
    assert result.measurements.area.sq_meters > 0


def test_3d_coordinates_flattened_to_2d():
    """
    Verifies that 3D geometries (with Z altitude coordinates) are cleanly flattened to 2D
    and measured accurately.
    """
    d = 0.008993216
    poly_3d = Polygon([
        (0.0, 0.0, 500.0),
        (d, 0.0, 500.0),
        (d, d, 500.0),
        (0.0, d, 500.0),
        (0.0, 0.0, 500.0)
    ])
    
    result = measurement_engine.measure_feature("3d_poly", poly_3d, "EPSG:4326", {})
    assert result.supported is True
    assert result.measurements is not None
    assert result.measurements.area.sq_meters > 990000.0
