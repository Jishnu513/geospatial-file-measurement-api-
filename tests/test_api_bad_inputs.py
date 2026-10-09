"""
test_api_bad_inputs.py — API-level tests for all bad-input scenarios:
- Corrupt zip (not a valid ZIP)
- Missing .shp inside a ZIP
- Wrong file extension
- Oversized file (413)
- Corrupt/garbage KML
- Empty KML (no Placemarks)
- Upload → 404 after delete
- Pagination on /api/files/
"""
import io
import zipfile
import struct
import math
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def _make_corrupt_zip_bytes() -> bytes:
    """Returns bytes that look like a ZIP PK header but are actually corrupted."""
    return b"PK\x03\x04" + b"\xff" * 50 + b"deliberately corrupt"


def _make_zip_no_shp_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("just_a_text_file.txt", b"nothing useful here")
    return buf.getvalue()


def _make_zip_with_only_shp_bytes() -> bytes:
    """ZIP with .shp but missing .shx and .dbf — should be rejected."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("test.shp", b"\x00" * 100)
        # deliberately omit .shx and .dbf
    return buf.getvalue()


def _make_kml_corrupt_bytes() -> bytes:
    return b"<?xml version='1.0'?><kml><NOT_CLOSED>"


def _make_kml_empty_bytes() -> bytes:
    return b"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document><name>Empty</name></Document>
</kml>"""


def _make_kml_polygon_bytes() -> bytes:
    d = "0.008993216"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark id="p1">
      <name>Square</name>
      <Polygon>
        <outerBoundaryIs>
          <LinearRing>
            <coordinates>0.0,0.0,0 {d},0.0,0 {d},{d},0 0.0,{d},0 0.0,0.0,0</coordinates>
          </LinearRing>
        </outerBoundaryIs>
      </Polygon>
    </Placemark>
  </Document>
</kml>""".encode("utf-8")


class TestBadInputs:
    def test_wrong_extension_returns_415(self):
        """Uploading a .geojson file must return 415."""
        response = client.post(
            "/api/files/",
            files={"file": ("data.geojson", b'{"type":"FeatureCollection"}', "application/json")}
        )
        assert response.status_code == 415

    def test_txt_file_returns_415(self):
        """A plain text file must return 415."""
        response = client.post(
            "/api/files/",
            files={"file": ("readme.txt", b"hello world", "text/plain")}
        )
        assert response.status_code == 415

    def test_oversized_file_returns_413(self):
        """A file > 50 MB must return 413."""
        big_content = b"\x00" * (51 * 1024 * 1024)
        response = client.post(
            "/api/files/",
            files={"file": ("huge.zip", big_content, "application/zip")}
        )
        assert response.status_code == 413

    def test_corrupt_zip_returns_error(self):
        """Uploading a corrupt ZIP should return 422."""
        response = client.post(
            "/api/files/",
            files={"file": ("corrupt.zip", _make_corrupt_zip_bytes(), "application/zip")}
        )
        assert response.status_code in (422, 400)

    def test_zip_without_shp_returns_error(self):
        """A ZIP with no .shp file must return 422."""
        response = client.post(
            "/api/files/",
            files={"file": ("no_shp.zip", _make_zip_no_shp_bytes(), "application/zip")}
        )
        assert response.status_code in (422, 400)

    def test_zip_missing_companion_files_returns_error(self):
        """A ZIP with .shp but missing .shx/.dbf must return 422."""
        response = client.post(
            "/api/files/",
            files={"file": ("incomplete.zip", _make_zip_with_only_shp_bytes(), "application/zip")}
        )
        assert response.status_code in (422, 400)

    def test_corrupt_kml_returns_error(self):
        """Uploading a corrupt / non-parseable KML should return 422."""
        response = client.post(
            "/api/files/",
            files={"file": ("bad.kml", _make_kml_corrupt_bytes(), "application/vnd.google-earth.kml+xml")}
        )
        assert response.status_code in (422, 400)

    def test_empty_kml_no_placemarks_returns_error(self):
        """A KML with no Placemarks should return 422."""
        response = client.post(
            "/api/files/",
            files={"file": ("empty.kml", _make_kml_empty_bytes(), "application/vnd.google-earth.kml+xml")}
        )
        assert response.status_code in (422, 400)


class TestFullLifecycle:
    def test_upload_get_measurements_delete_get_404(self):
        """
        Full lifecycle: upload KML → GET info → GET measurements → DELETE → GET 404.
        """
        kml_bytes = _make_kml_polygon_bytes()

        # 1. Upload
        upload_resp = client.post(
            "/api/files/",
            files={"file": ("lifecycle.kml", kml_bytes, "application/vnd.google-earth.kml+xml")}
        )
        assert upload_resp.status_code == 201
        body = upload_resp.json()
        file_id = body["id"]
        assert body["status"] == "COMPLETED"
        assert body["feature_count"] == 1
        assert body["crs"] == "EPSG:4326"

        # 2. GET /api/files/{id}/ — must match exact spec fields
        info_resp = client.get(f"/api/files/{file_id}/")
        assert info_resp.status_code == 200
        info = info_resp.json()
        assert info["id"] == file_id
        assert info["filename"] == "lifecycle.kml"
        assert info["feature_count"] == 1
        assert info["crs"] == "EPSG:4326"
        assert info["status"] == "COMPLETED"

        # 3. GET /api/files/{id}/measurements/
        meas_resp = client.get(f"/api/files/{file_id}/measurements/")
        assert meas_resp.status_code == 200
        meas = meas_resp.json()
        assert meas["id"] == file_id
        assert len(meas["measurements"]) == 1
        feat = meas["measurements"][0]
        assert feat["geometry_type"] == "Polygon"
        assert feat["supported"] is True
        area = feat["measurements"]["area"]["sq_meters"]
        assert math.isclose(area, 1_000_000.0, rel_tol=0.01), f"Expected ~1M m², got {area}"

        # 4. DELETE
        del_resp = client.delete(f"/api/files/{file_id}/")
        assert del_resp.status_code == 200
        assert del_resp.json()["deleted"] is True

        # 5. Confirm 404
        assert client.get(f"/api/files/{file_id}/").status_code == 404
        assert client.get(f"/api/files/{file_id}/measurements/").status_code == 404

    def test_list_endpoint_pagination(self):
        """GET /api/files/ with ?skip=0&limit=5 must return valid shape."""
        resp = client.get("/api/files/?skip=0&limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "files" in data
        assert isinstance(data["files"], list)
        assert len(data["files"]) <= 5

    def test_get_nonexistent_returns_404(self):
        resp = client.get("/api/files/does-not-exist-xyzzy/")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_delete_nonexistent_returns_404(self):
        resp = client.delete("/api/files/does-not-exist-xyzzy/")
        assert resp.status_code == 404
