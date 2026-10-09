# Geospatial File Measurement API

A production-grade REST API and GIS Visualizer for processing geospatial files (Shapefile ZIP and KML), dynamically reprojecting coordinates per feature into optimal UTM zones, and computing precise geometric measurements — area, perimeter, and length — with geodesic ellipsoidal verification.

---

## Table of Contents

1. [Overview](#overview)
2. [Interactive Web Dashboard](#interactive-web-dashboard)
3. [Setup & Quickstart](#setup)
4. [API Documentation](#api-documentation)
5. [Architecture](#architecture)
6. [Design Decisions](#design-decisions)
7. [Limitations](#limitations)
8. [Learnings](#learnings)
9. [Future Scope](#future-scope)

---

## Overview

The API accepts **Shapefile ZIP** (`.zip`) and **KML** (`.kml`) uploads, processes them, and returns exact metric measurements:

| Geometry Type | Measurement | Units Computed |
|---|---|---|
| **Polygon / MultiPolygon** | Area + Perimeter | m², ha, km², acres, ft² (Area) & m, km, ft, mi (Perimeter) |
| **LineString / MultiLineString** | Length | m, km, ft, miles |
| **Point / MultiPoint** | `supported: false` | Handled gracefully — 0D coordinate without area/length |
| **GeometryCollection** | Composite aggregation | Recursive calculation of all measurable sub-geometries |
| **Null / Empty** | `supported: false` | Gracefully skipped with descriptive message |

Each measurement is returned in **multiple units**, alongside a **geodesic WGS84 cross-check** value computed with `pyproj.Geod(ellps="WGS84")`.

---

## Interactive Web Dashboard

A GIS visualizer is included at **`http://localhost:8000/dashboard`**:
- **Interactive Map:** Leaflet map with Dark Matter, Positron, and Satellite imagery layers.
- **Drag & Drop Upload:** Upload `.zip` Shapefiles or `.kml` files with real-time visual feedback.
- **One-Click Benchmark Datasets:** Test with pre-packaged benchmarks:
  - 📐 **1 km² Calibration Square** at the equator (100.00 ha verification)
  - 🌾 **Agricultural Farm** (Parcels, donut polygon with lake hole, canal linestring, sensor points)
  - 🗺️ **Cadastral Parcels** (ESRI Shapefile ZIP)
  - ⚠️ **Missing .PRJ Shapefile** (Demonstrating automatic EPSG:4326 fallback)
- **Visual Geometry Overlays:** Interactive vector layers with popup cards showing area, length, and UTM zones.
- **API Inspector & cURL Generator:** Live JSON inspector for measurements, metadata, GeoJSON, and ready-to-run terminal commands.

---

## Setup

### Requirements

- Python 3.11+
- GDAL (for `pyogrio` driver; see Docker for system dependencies)

### Local — Virtual Environment

```bash
# 1. Clone the repo
git clone <your-repo-url>
cd geo-measurement-api

# 2. Create and activate a virtual environment
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Start the development server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- Web Dashboard: **http://localhost:8000/dashboard**
- Interactive Swagger UI: **http://localhost:8000/docs**
- ReDoc: **http://localhost:8000/redoc**

### Docker

```bash
# Build the image
docker build -t geo-measurement-api .

# Run the container
docker run -p 8000:8000 geo-measurement-api

# Or with a persistent volume for the SQLite DB
docker run -p 8000:8000 -v $(pwd)/storage:/app/storage geo-measurement-api
```

### Running Tests

```bash
# Run all tests
pytest -v

# Run with coverage
pytest -v --cov=app --cov-report=term-missing
```

All **61 automated tests** pass in a clean environment with no test data pre-seeded — all fixtures are generated programmatically in `tests/conftest.py`.

---

## API Documentation


Interactive Swagger UI: **http://localhost:8000/docs**
ReDoc: **http://localhost:8000/redoc**

---

### `POST /api/files/`

Upload and process a geospatial file.

**Request:** `multipart/form-data` with `file` field (`.zip` or `.kml`).

**Response `201 Created`:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "filename": "survey.kml",
  "file_type": "KML",
  "file_size_bytes": 2048,
  "feature_count": 3,
  "crs": "EPSG:4326",
  "status": "COMPLETED",
  "created_at": "2024-01-15T10:30:00.000Z",
  "processing_time_ms": 142.5,
  "summary": {
    "total_features": 3,
    "supported_features_count": 2,
    "unsupported_features_count": 1,
    "total_area_sq_m": 1000000.0,
    "total_area_hectares": 100.0,
    "total_length_m": 1500.0,
    "geometry_breakdown": {"Polygon": 1, "LineString": 1, "Point": 1}
  }
}
```

**curl example:**
```bash
curl -X POST "http://localhost:8000/api/files/" \
  -H "accept: application/json" \
  -F "file=@sample_data/sample_known_square.kml"
```

**Error responses:**
| Status | Condition |
|---|---|
| `413` | File exceeds 50 MB |
| `415` | Unsupported extension (not `.zip` or `.kml`) |
| `422` | Corrupt ZIP, missing `.shp`, bad KML, no Placemarks |

---

### `GET /api/files/{id}/`

Retrieve metadata for a processed file.

**Response `200 OK`** (exact assignment schema):
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "filename": "survey.kml",
  "feature_count": 3,
  "crs": "EPSG:4326",
  "status": "COMPLETED",
  "created_at": "2024-01-15T10:30:00.000Z",
  "processing_time_ms": 142.5
}
```

**curl example:**
```bash
curl "http://localhost:8000/api/files/550e8400-e29b-41d4-a716-446655440000/"
```

---

### `GET /api/files/{id}/measurements/`

Retrieve per-feature measurements.

**Response `200 OK`:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "filename": "survey.kml",
  "crs": "EPSG:4326",
  "status": "COMPLETED",
  "summary": { ... },
  "measurements": [
    {
      "feature_id": 0,
      "geometry_type": "Polygon",
      "supported": true,
      "message": "Successfully calculated area and perimeter.",
      "measurements": {
        "area": {
          "sq_meters": 1000432.5,
          "hectares": 100.04325,
          "sq_kilometers": 1.0004325,
          "acres": 247.213,
          "sq_feet": 10768201.4
        },
        "perimeter": {
          "meters": 4002.1,
          "kilometers": 4.0021,
          "feet": 13130.25,
          "miles": 2.487
        },
        "geodesic_area_sq_meters": 1000431.9,
        "geodesic_perimeter_meters": 4002.0
      },
      "properties": { "name": "Plot A", "_projected_crs": "UTM Zone 31N (EPSG:32631)" },
      "centroid": [0.004497, 0.004497],
      "bounding_box": [0.0, 0.0, 0.008993, 0.008993]
    }
  ]
}
```

**curl example:**
```bash
curl "http://localhost:8000/api/files/550e8400-e29b-41d4-a716-446655440000/measurements/"
```

---

### `GET /api/files/`

List all uploaded files with pagination.

**Query params:** `skip` (default 0), `limit` (default 50)

```bash
curl "http://localhost:8000/api/files/?skip=0&limit=10"
```

---

### `GET /api/files/{id}/features/`

Returns the processed features as a **GeoJSON FeatureCollection** with measurements embedded in properties.

```bash
curl "http://localhost:8000/api/files/550e8400-e29b-41d4-a716-446655440000/features/"
```

---

### `DELETE /api/files/{id}/`

Deletes the database record and the uploaded file from disk.

**Response `200 OK`:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "deleted": true,
  "message": "File 'survey.kml' (ID: 550e8400-e29b-41d4-a716-446655440000) successfully deleted."
}
```

---

## Architecture

### Project Structure

```
geo-measurement-api/
├── app/
│   ├── main.py                  # FastAPI app factory, middleware, routers
│   ├── config.py                # Pydantic Settings (env vars, limits, paths)
│   ├── api/
│   │   └── routes_files.py      # All /api/files/ endpoints
│   ├── models/
│   │   └── schemas.py           # Pydantic request/response models
│   └── services/
│       ├── database.py          # SQLAlchemy engine, FileRecord ORM model
│       ├── security.py          # Zip-slip, zip-bomb, extension/size guards
│       ├── parser.py            # Shapefile + KML readers (pyogrio + defusedxml)
│       ├── crs_transformer.py   # Per-feature UTM selection, reprojection cache
│       ├── measurement.py       # Area/length/geodesic engine
│       └── processor.py        # Orchestration: validate → parse → measure → persist
├── tests/
│   ├── conftest.py              # All fixtures generated in-code (no binaries committed)
│   ├── test_numeric_measurements.py
│   ├── test_crs_reprojection.py
│   ├── test_security_robustness.py
│   ├── test_api_endpoints.py
│   ├── test_api_bad_inputs.py
│   └── test_geometry_types.py
├── sample_data/                 # 2 small real files for manual testing
├── Dockerfile
├── requirements.txt
└── .gitignore
```

### File Processing Flow

```
POST /api/files/
    │
    ├─ SecurityValidator.validate_file_metadata()   ← 415 / 413 guard
    ├─ Save file as <uuid>.{zip,kml}
    │
    └─ FileProcessorService.process_file_synchronously()
           │
           ├─ SecurityValidator.safe_extract_zip()  ← zip-slip / zip-bomb / companion-file checks
           │
           ├─ GeospatialParser.parse_shapefile_zip() / parse_kml()
           │     ├─ pyogrio.read_dataframe()         ← primary engine
           │     └─ _parse_kml_xml_fallback()        ← defusedxml if pyogrio fails
           │
           ├─ Per-feature loop (each feature isolated in try/except)
           │     ├─ shapely.make_valid()             ← geometry repair
           │     ├─ shapely.force_2d()               ← strip Z coordinates
           │     ├─ CRSTransformerService.project_geometry()  ← per-feature UTM
           │     └─ MeasurementEngine.measure_feature()       ← Cartesian + geodesic
           │
           ├─ MeasurementEngine.aggregate_measurements()
           └─ FileRecord.status = COMPLETED → db.commit()
```

### CRS Reprojection Strategy

Each feature is independently reprojected into its **own UTM zone**, derived from the feature's centroid:

```python
zone  = int((lon + 180) // 6) + 1                    # zone 1–60
epsg  = (32600 if lat >= 0 else 32700) + zone         # N/S hemisphere
```

Special cases:
- **Polar (|lat| > 84°):** UPS North (EPSG:32661) or UPS South (EPSG:32761)
- **Already-projected CRS:** used as-is (no unnecessary reprojection)
- **Missing `.prj`:** defaults to EPSG:4326 with a warning in `error_message`
- **Transformer caching:** `(src_crs, dst_crs)` pairs cached to avoid repeated instantiation

Geodesic cross-check uses `pyproj.Geod(ellps="WGS84").geometry_area_perimeter()` and `.geometry_length()` directly on WGS84 coordinates, with `abs()` applied to handle both winding orders.

---

## Design Decisions

### FastAPI vs Django
FastAPI was chosen for its async-ready design, automatic OpenAPI/Swagger docs, Pydantic integration, and minimal boilerplate. Django REST Framework would add unnecessary overhead for a single-domain API without complex ORM relationships.

### Per-Feature UTM vs One Dataset Zone vs Equal-Area
- **One dataset zone** is fast but distorts features at zone boundaries or in wide datasets.
- **Equal-area projection (e.g., EPSG:6933)** minimises area distortion globally but is less intuitive and less standard.
- **Per-feature UTM** (chosen) gives the best accuracy for each individual feature at the cost of slightly more computation. Transformers are cached to mitigate this.

### Projected Measurement + Geodesic Verification
Cartesian measurements in UTM give intuitive, accurate results for moderate-size features. The geodesic cross-check (`pyproj.Geod`) serves as a mathematical ground truth from the WGS84 ellipsoid, stored as `geodesic_value` for comparison.

### Synchronous Processing
Processing happens synchronously during the POST request. This is acceptable for the current scope (small files, development/demo use). See [Future Scope](#future-scope) for async queue design.

### SQLite vs PostGIS
SQLite (via SQLAlchemy) requires zero infrastructure, is sufficient for single-instance usage, and keeps the setup frictionless. PostGIS would enable spatial queries and horizontal scaling but requires PostgreSQL infrastructure. Feature geometry is stored as JSON (GeoJSON), not as PostGIS geometry columns.

### pyogrio vs Fiona vs Custom KML Parser
- **pyogrio** (primary): fastest reader, based on GDAL, handles both Shapefile and KML in one library.
- **defusedxml** (fallback): safe against XXE attacks; handles nested Folders, holes (`innerBoundaryIs`), `MultiGeometry`, and custom ExtendedData properties.

### Missing `.prj` Handling
When a Shapefile ZIP lacks a `.prj` file, the API defaults to EPSG:4326 and records a warning in `error_message`. An alternative — returning a `422` — is stricter but unhelpful when coordinates are obviously geographic. The lenient approach was chosen.

---

## Limitations

- **Zone boundary distortion:** Features straddling two UTM zones use a single zone (the centroid's). For very wide features (>3° of longitude), geodesic values are a better reference.
- **Polar regions:** UPS projections (EPSG:32661/32761) are used above ±84° but have different accuracy characteristics.
- **Synchronous-only processing:** Large files (near the 50 MB limit) block the request. No job queue currently exists.
- **Single file per upload:** Only one Shapefile ZIP or KML per request.
- **No authentication:** The API is open. Not suitable for public deployment without an auth layer.

---

## Learnings

- **CRS axis order pitfalls:** GDAL/pyproj historically used (lat, lon) in some contexts. Using `always_xy=True` in `Transformer.from_crs()` is mandatory for predictable (x=lon, y=lat) behaviour.
- **Geodesic winding order:** `Geod.geometry_area_perimeter()` can return negative area depending on polygon orientation. Always wrap with `abs()`.
- **KML quirks:** The `<LinearRing>` inside `<outerBoundaryIs>` uses `lon,lat,alt` order (not lat,lon). The KML namespace (`xmlns="http://www.opengis.net/kml/2.2"`) must be stripped for reliable element matching.
- **Shapely 2.x:** `shapely.make_valid()` and `shapely.force_2d()` are module-level functions in Shapely 2.x (not methods). `shapely.ops.transform()` still works but is deprecated in favour of `shapely.transform()`.
- **Z coordinates:** Many real-world KML files include altitude as the third coordinate. Stripping with `shapely.force_2d()` before projection prevents incorrect 3D transformations.
- **ZIP security:** Python's `zipfile` module does not validate paths by default. Manual `os.path.realpath()` comparison is required for zip-slip protection.

---

## Future Scope

1. **Async processing queue:** Celery + Redis (or FastAPI BackgroundTasks) to handle large files without blocking the request.
2. **Additional formats:** GeoJSON, GeoPackage (GPKG), KMZ, GML.
3. **PostGIS backend:** Replace SQLite with PostgreSQL + PostGIS for spatial indexing and queries (e.g., bounding-box search).
4. **Authentication & rate limiting:** OAuth2 / API keys, per-user quotas.
5. **Per-feature custom CRS override:** Accept a `?crs=EPSG:XXXX` query param to override automatic UTM selection.
6. **Unit conversion query param:** `?unit=ha`, `?unit=acres`, `?unit=ft2` to return only the requested unit.
7. **Dashboard UI:** Simple web interface to visualise uploaded geometries on a map with measurement overlays.
8. **Webhook callbacks:** POST to a client URL when async processing completes.
9. **Streaming upload:** Accept chunked uploads for very large files.
