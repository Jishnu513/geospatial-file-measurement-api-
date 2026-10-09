import pytest
from pyproj import CRS
from shapely.geometry import Polygon
from app.services.crs_transformer import crs_service


@pytest.mark.parametrize(
    "lon,lat,expected_epsg,expected_name_part",
    [
        (77.59, 12.97, 32643, "UTM Zone 43N"),
        (-0.12, 51.50, 32630, "UTM Zone 30N"),
        (-43.17, -22.90, 32723, "UTM Zone 23S"),
        (139.69, 35.68, 32654, "UTM Zone 54N"),
        (151.20, -33.86, 32756, "UTM Zone 56S"),
        (0.0, 85.0, 32661, "UPS North"),
        (0.0, -85.0, 32761, "UPS South"),
    ]
)
def test_utm_zone_selection(lon, lat, expected_epsg, expected_name_part):
    epsg, name = crs_service.get_utm_epsg_for_coordinate(lon, lat)
    assert epsg == expected_epsg
    assert expected_name_part in name


def test_already_projected_crs_passthrough():
    """
    Verifies that if a dataset is already in a projected CRS (e.g. EPSG:3857 or UTM),
    the CRS service retains the projected CRS.
    """
    # Square in Web Mercator meters
    square_meters = Polygon([(0, 0), (1000, 0), (1000, 1000), (0, 1000), (0, 0)])
    proj_crs = CRS.from_epsg(3857)
    
    out_geom, out_name, out_crs = crs_service.project_geometry(square_meters, proj_crs)
    
    assert out_crs.is_projected is True
    assert out_geom.area == 1000000.0


def test_missing_crs_defaults_to_epsg4326():
    """
    Verifies that None or invalid CRS string falls back to EPSG:4326.
    """
    crs_none = crs_service.parse_crs(None)
    assert crs_none.to_epsg() == 4326
    
    crs_invalid = crs_service.parse_crs("INVALID_CRS_STRING_123")
    assert crs_invalid.to_epsg() == 4326
