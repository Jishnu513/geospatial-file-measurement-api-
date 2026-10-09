import io
import math
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings

client = TestClient(app)


def test_health_check_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "HEALTHY"
    assert "uptime_seconds" in data


def test_upload_and_process_kml():
    kml_path = settings.SAMPLE_DIR / "sample_known_square.kml"
    assert kml_path.exists(), "Sample KML must exist"

    with open(kml_path, "rb") as f:
        response = client.post(
            "/api/files/",
            files={"file": ("sample_known_square.kml", f, "application/vnd.google-earth.kml+xml")}
        )

    assert response.status_code == 201
    data = response.json()
    file_id = data["id"]
    assert data["filename"] == "sample_known_square.kml"
    assert data["status"] == "COMPLETED"
    assert data["feature_count"] == 1
    assert data["crs"] == "EPSG:4326"

    # Verify summary
    summary = data["summary"]
    assert summary["total_features"] == 1
    assert summary["supported_features_count"] == 1
    assert math.isclose(summary["total_area_sq_m"], 1000000.0, rel_tol=0.01)

    # 1. Test GET /api/files/{id}/ (Exact assignment schema)
    info_resp = client.get(f"/api/files/{file_id}/")
    assert info_resp.status_code == 200
    info = info_resp.json()
    assert info["id"] == file_id
    assert info["filename"] == "sample_known_square.kml"
    assert info["feature_count"] == 1
    assert info["crs"] == "EPSG:4326"
    assert info["status"] == "COMPLETED"

    # 2. Test GET /api/files/{id}/measurements/
    meas_resp = client.get(f"/api/files/{file_id}/measurements/")
    assert meas_resp.status_code == 200
    meas_data = meas_resp.json()
    assert meas_data["id"] == file_id
    assert meas_data["status"] == "COMPLETED"
    assert len(meas_data["measurements"]) == 1
    
    first_feat = meas_data["measurements"][0]
    assert first_feat["geometry_type"] == "Polygon"
    assert first_feat["supported"] is True
    assert math.isclose(first_feat["measurements"]["area"]["sq_meters"], 1000000.0, rel_tol=0.01)
    assert math.isclose(first_feat["measurements"]["area"]["hectares"], 100.0, rel_tol=0.01)

    # 3. Test GET /api/files/{id}/features/ (GeoJSON FeatureCollection)
    geojson_resp = client.get(f"/api/files/{file_id}/features/")
    assert geojson_resp.status_code == 200
    geojson_data = geojson_resp.json()
    assert geojson_data["type"] == "FeatureCollection"
    assert len(geojson_data["features"]) == 1

    # 4. Test DELETE /api/files/{id}/
    del_resp = client.delete(f"/api/files/{file_id}/")
    assert del_resp.status_code == 200
    assert del_resp.json()["deleted"] is True

    # 5. Subsequent GET should be 404
    assert client.get(f"/api/files/{file_id}/").status_code == 404


def test_upload_and_process_shapefile_zip():
    zip_path = settings.SAMPLE_DIR / "sample_cadastral.zip"
    assert zip_path.exists(), "Sample Shapefile ZIP must exist"

    with open(zip_path, "rb") as f:
        response = client.post(
            "/api/files/",
            files={"file": ("sample_cadastral.zip", f, "application/zip")}
        )

    assert response.status_code == 201
    data = response.json()
    file_id = data["id"]
    assert data["filename"] == "sample_cadastral.zip"
    assert data["status"] == "COMPLETED"
    assert data["feature_count"] == 2
    assert data["file_type"] == "SHAPEFILE_ZIP"

    # Verify measurements endpoint
    meas_resp = client.get(f"/api/files/{file_id}/measurements/")
    assert meas_resp.status_code == 200
    meas_data = meas_resp.json()
    assert len(meas_data["measurements"]) == 2
    for m in meas_data["measurements"]:
        assert m["supported"] is True
        assert m["geometry_type"] == "Polygon"
        assert m["measurements"]["area"]["sq_meters"] > 0


def test_upload_shapefile_missing_prj_fallback():
    zip_path = settings.SAMPLE_DIR / "sample_no_prj.zip"
    assert zip_path.exists()

    with open(zip_path, "rb") as f:
        response = client.post(
            "/api/files/",
            files={"file": ("sample_no_prj.zip", f, "application/zip")}
        )

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "COMPLETED"
    assert data["crs"] == "EPSG:4326"


def test_list_files_pagination():
    response = client.get("/api/files/?skip=0&limit=10")
    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert "files" in data
    assert isinstance(data["files"], list)


def test_get_nonexistent_file_404():
    response = client.get("/api/files/non_existent_uuid_12345/")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_delete_nonexistent_file_404():
    response = client.delete("/api/files/non_existent_uuid_12345/")
    assert response.status_code == 404


def test_dashboard_endpoint():
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "GeoMeasure API" in response.text
    assert "map" in response.text


def test_list_samples_and_process_sample():
    # 1. List samples
    resp = client.get("/api/files/samples/")
    assert resp.status_code == 200
    data = resp.json()
    assert "samples" in data
    assert len(data["samples"]) >= 3

    # 2. Process sample directly
    proc_resp = client.post("/api/files/samples/sample_known_square.kml/process")
    assert proc_resp.status_code == 201
    proc_data = proc_resp.json()
    assert proc_data["status"] == "COMPLETED"
    assert proc_data["feature_count"] == 1
    assert math.isclose(proc_data["summary"]["total_area_sq_m"], 1000000.0, rel_tol=0.01)

    # 3. Process non-existent sample 404
    bad_resp = client.post("/api/files/samples/non_existent_sample.kml/process")
    assert bad_resp.status_code == 404

