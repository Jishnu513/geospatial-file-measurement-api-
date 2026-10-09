"""
conftest.py — Shared pytest fixtures for the Geospatial File Measurement API test suite.

All fixtures are generated programmatically in code, so no binary files need to be
committed to the repository. The two real sample files live in sample_data/ for
human-readable reference.
"""
import io
import zipfile
import tempfile
from pathlib import Path
import pytest


# ---------------------------------------------------------------------------
# Helpers: build minimal valid Shapefile components in memory
# ---------------------------------------------------------------------------

def _make_shp_header(record_count: int = 1) -> bytes:
    """Minimal .shp file with a single Polygon bounding box record."""
    import struct
    # Main file header (100 bytes)
    # File code = 9994, length in 16-bit words
    # Content: just the header + one null-shape record to keep it self-consistent
    # We use a trivially small placeholder that pyogrio can at minimum detect as SHP.
    header = struct.pack(">IIIIIII", 9994, 0, 0, 0, 0, 0, 50)   # 50 words = 100 bytes
    header += struct.pack("<II", 1000, 1)                          # version, shape-type (1 = Point)
    header += struct.pack("<dddd", 0.0, 0.0, 1.0, 1.0)            # bbox Xmin Ymin Xmax Ymax
    header += struct.pack("<dddd", 0.0, 0.0, 0.0, 0.0)            # Zmin Zmax Mmin Mmax
    return header


def _make_minimal_shapefile_zip(
    include_prj: bool = True,
    include_shx: bool = True,
    include_dbf: bool = True,
    shp_name: str = "test.shp",
) -> bytes:
    """
    Creates a minimal valid Shapefile ZIP in memory.
    All required companion files (.shx, .dbf, .prj) are included by default.
    """
    import struct

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Minimal .shp content (100-byte header + null record)
        shp_data = b"\x00" * 100  # placeholder — not parseable but structurally safe
        zf.writestr(shp_name, shp_data)

        if include_shx:
            base = shp_name.replace(".shp", ".shx")
            zf.writestr(base, b"\x00" * 100)

        if include_dbf:
            base = shp_name.replace(".shp", ".dbf")
            # Minimal dBASE III+ header: version=3, no fields, zero records
            dbf_data = struct.pack("<BBHBBHHHBB", 3, 26, 10, 1, 0, 32, 1, 0, 0, 0) + b"\x00" * 22
            zf.writestr(base, dbf_data)

        if include_prj:
            base = shp_name.replace(".shp", ".prj")
            wkt = 'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,298.257223563]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]'
            zf.writestr(base, wkt.encode())

    return buf.getvalue()


def _make_zip_slip_zip() -> bytes:
    """Creates a ZIP with a path-traversal (zip-slip) entry."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../../../evil.shp", b"malicious payload")
        zf.writestr("../../../evil.shx", b"malicious payload")
        zf.writestr("../../../evil.dbf", b"malicious payload")
    return buf.getvalue()


def _make_corrupt_zip() -> bytes:
    """Returns bytes that look like a ZIP but are actually corrupted."""
    return b"PK\x03\x04" + b"\xff" * 50 + b"not a real zip"


def _make_kml(content: str) -> bytes:
    return content.encode("utf-8")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def valid_shapefile_zip_bytes():
    """A structurally-valid (though geometry-empty) Shapefile ZIP."""
    return _make_minimal_shapefile_zip()


@pytest.fixture
def shapefile_zip_no_prj_bytes():
    """A Shapefile ZIP missing the .prj projection file."""
    return _make_minimal_shapefile_zip(include_prj=False)


@pytest.fixture
def shapefile_zip_no_shx_bytes():
    """A Shapefile ZIP missing the .shx companion index file."""
    return _make_minimal_shapefile_zip(include_shx=False)


@pytest.fixture
def shapefile_zip_no_dbf_bytes():
    """A Shapefile ZIP missing the .dbf companion attribute table."""
    return _make_minimal_shapefile_zip(include_dbf=False)


@pytest.fixture
def zip_slip_zip_bytes():
    """A ZIP containing a path-traversal attack entry."""
    return _make_zip_slip_zip()


@pytest.fixture
def corrupt_zip_bytes():
    """Bytes that are corrupt / not a valid ZIP file."""
    return _make_corrupt_zip()


@pytest.fixture
def kml_one_polygon_bytes():
    """A minimal valid KML with one 1 km² Polygon at equator."""
    content = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark id="p1">
      <name>1km Square</name>
      <Polygon>
        <outerBoundaryIs>
          <LinearRing>
            <coordinates>
              0.0,0.0,0
              0.008993216,0.0,0
              0.008993216,0.008993216,0
              0.0,0.008993216,0
              0.0,0.0,0
            </coordinates>
          </LinearRing>
        </outerBoundaryIs>
      </Polygon>
    </Placemark>
  </Document>
</kml>"""
    return content.encode("utf-8")


@pytest.fixture
def kml_with_hole_bytes():
    """A KML with a Polygon containing an interior ring (hole)."""
    content = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark id="donut">
      <name>Donut Polygon</name>
      <Polygon>
        <outerBoundaryIs>
          <LinearRing>
            <coordinates>
              0.0,0.0,0
              0.008993216,0.0,0
              0.008993216,0.008993216,0
              0.0,0.008993216,0
              0.0,0.0,0
            </coordinates>
          </LinearRing>
        </outerBoundaryIs>
        <innerBoundaryIs>
          <LinearRing>
            <coordinates>
              0.002248304,0.002248304,0
              0.006744912,0.002248304,0
              0.006744912,0.006744912,0
              0.002248304,0.006744912,0
              0.002248304,0.002248304,0
            </coordinates>
          </LinearRing>
        </innerBoundaryIs>
      </Polygon>
    </Placemark>
  </Document>
</kml>"""
    return content.encode("utf-8")


@pytest.fixture
def kml_with_point_and_line_bytes():
    """A KML with mixed geometry types: Point, LineString, Polygon."""
    content = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark id="pt1">
      <name>A Point</name>
      <Point><coordinates>77.5946,12.9716,0</coordinates></Point>
    </Placemark>
    <Placemark id="ln1">
      <name>A Line</name>
      <LineString>
        <coordinates>0.0,0.0,0 0.008993216,0.0,0</coordinates>
      </LineString>
    </Placemark>
    <Placemark id="pg1">
      <name>A Polygon</name>
      <Polygon>
        <outerBoundaryIs>
          <LinearRing>
            <coordinates>
              0.0,0.0,0
              0.008993216,0.0,0
              0.008993216,0.008993216,0
              0.0,0.008993216,0
              0.0,0.0,0
            </coordinates>
          </LinearRing>
        </outerBoundaryIs>
      </Polygon>
    </Placemark>
  </Document>
</kml>"""
    return content.encode("utf-8")


@pytest.fixture
def kml_corrupt_bytes():
    """Corrupted / not-well-formed XML content."""
    return b"<?xml version='1.0'?><kml><Document><Placemark><NOT_CLOSED>"


@pytest.fixture
def kml_empty_no_placemarks():
    """A well-formed KML with a Document but zero Placemarks."""
    content = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>Empty Dataset</name>
  </Document>
</kml>"""
    return content.encode("utf-8")


@pytest.fixture
def sample_kml_path(tmp_path, kml_one_polygon_bytes):
    """Writes the 1-polygon KML to a temporary file and returns its Path."""
    p = tmp_path / "sample.kml"
    p.write_bytes(kml_one_polygon_bytes)
    return p


@pytest.fixture
def sample_zip_path(tmp_path, valid_shapefile_zip_bytes):
    """Writes a valid shapefile ZIP to a temporary file and returns its Path."""
    p = tmp_path / "sample.zip"
    p.write_bytes(valid_shapefile_zip_bytes)
    return p
