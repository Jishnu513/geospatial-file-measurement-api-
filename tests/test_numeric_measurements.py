import math
import pytest
from shapely.geometry import Polygon, LineString, Point, MultiPolygon, MultiLineString, GeometryCollection
from app.services.measurement import measurement_engine
from app.services.crs_transformer import crs_service


def test_known_1km_square_area():
    """
    Known-answer test: A 1 km x 1 km square at the equator.
    Longitude: 0.0 to 0.008993216 deg
    Latitude:  0.0 to 0.008993216 deg
    Expected area: ~1,000,000 m² (1 sq km = 100 hectares).
    """
    d = 0.008993216
    square = Polygon([(0.0, 0.0), (d, 0.0), (d, d), (0.0, d), (0.0, 0.0)])
    
    result = measurement_engine.measure_feature(
        feature_id="test_square_1km",
        raw_geom=square,
        input_crs_str="EPSG:4326",
        properties={"label": "1km Square"}
    )
    
    assert result.supported is True
    assert result.measurements is not None
    
    # Check projected Cartesian area in UTM zone (should be within 0.5% of 1,000,000 m²)
    area_m2 = result.measurements.area.sq_meters
    assert math.isclose(area_m2, 1000000.0, rel_tol=0.005), f"Expected ~1,000,000 m², got {area_m2}"
    
    # Check hectares conversion
    assert math.isclose(result.measurements.area.hectares, 100.0, rel_tol=0.005)
    
    # Check sq kilometers conversion
    assert math.isclose(result.measurements.area.sq_kilometers, 1.0, rel_tol=0.005)
    
    # Check geodesic cross-check area (within 1% ellipsoidal curvature tolerance)
    geod_area = result.measurements.geodesic_area_sq_meters
    assert geod_area is not None
    assert math.isclose(geod_area, 1000000.0, rel_tol=0.01), f"Expected geodesic ~1,000,000 m², got {geod_area}"


def test_naive_degrees_vs_projected_area():
    """
    Demonstrates why calculating area directly in lat/lon degrees is mathematically invalid.
    Naive degree area is ~8.08e-5 deg², which has no physical meaning.
    """
    d = 0.008993216
    square = Polygon([(0.0, 0.0), (d, 0.0), (d, d), (0.0, d), (0.0, 0.0)])
    
    naive_degree_area = square.area
    assert math.isclose(naive_degree_area, d * d, rel_tol=1e-5)
    assert naive_degree_area < 0.0001, "Naive area is in square degrees, not square meters!"
    
    # With our projection service, it is accurately transformed to meters
    result = measurement_engine.measure_feature("sq", square, "EPSG:4326", {})
    assert result.measurements.area.sq_meters > 990000.0


def test_known_1km_line_length():
    """
    Known-answer test: A 1 km straight line along the equator.
    Expected length: ~1,000 m.
    """
    d = 0.008993216
    line = LineString([(0.0, 0.0), (d, 0.0)])
    
    result = measurement_engine.measure_feature("line_1km", line, "EPSG:4326", {})
    
    assert result.supported is True
    assert result.measurements is not None
    length_m = result.measurements.length.meters
    assert math.isclose(length_m, 1000.0, rel_tol=0.005), f"Expected ~1,000 m, got {length_m}"
    assert math.isclose(result.measurements.length.kilometers, 1.0, rel_tol=0.005)


def test_polygon_with_hole():
    """
    Verifies that a polygon with a hole has area = exterior area minus hole area.
    """
    # Outer square: 1000m x 1000m (d = 0.008993216)
    d = 0.008993216
    exterior = [(0.0, 0.0), (d, 0.0), (d, d), (0.0, d), (0.0, 0.0)]
    
    # Inner hole: 500m x 500m (centered)
    h_min = d * 0.25
    h_max = d * 0.75
    interior = [(h_min, h_min), (h_max, h_min), (h_max, h_max), (h_min, h_max), (h_min, h_min)]
    
    donut = Polygon(shell=exterior, holes=[interior])
    result = measurement_engine.measure_feature("donut", donut, "EPSG:4326", {})
    
    # Outer area is ~1,000,000 m², hole is ~250,000 m², expected net area ~750,000 m²
    net_area = result.measurements.area.sq_meters
    assert math.isclose(net_area, 750000.0, rel_tol=0.01), f"Expected ~750,000 m², got {net_area}"


def test_point_geometry_graceful_handling():
    """
    Verifies that Point and MultiPoint geometries do not crash and return supported: false.
    """
    pt = Point(77.5946, 12.9716)
    result = measurement_engine.measure_feature("pt_1", pt, "EPSG:4326", {"name": "Bangalore"})
    
    assert result.supported is False
    assert result.measurements is None
    assert "0-dimensional" in result.message
    assert result.centroid == [77.5946, 12.9716]


def test_winding_order_geodesic_area_always_positive():
    """
    Verifies that geodesic area is strictly positive regardless of clockwise / counter-clockwise vertex order.
    """
    d = 0.008993216
    # Counter-clockwise
    ccw_poly = Polygon([(0.0, 0.0), (d, 0.0), (d, d), (0.0, d), (0.0, 0.0)])
    # Clockwise
    cw_poly = Polygon([(0.0, 0.0), (0.0, d), (d, d), (d, 0.0), (0.0, 0.0)])
    
    res_ccw = measurement_engine.measure_feature("ccw", ccw_poly, "EPSG:4326", {})
    res_cw = measurement_engine.measure_feature("cw", cw_poly, "EPSG:4326", {})
    
    assert res_ccw.measurements.geodesic_area_sq_meters > 0
    assert res_cw.measurements.geodesic_area_sq_meters > 0
    assert math.isclose(
        res_ccw.measurements.geodesic_area_sq_meters,
        res_cw.measurements.geodesic_area_sq_meters,
        rel_tol=1e-4
    )
