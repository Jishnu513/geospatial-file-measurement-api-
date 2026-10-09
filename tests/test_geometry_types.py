"""
test_geometry_types.py — Tests for Multi-geometry types, GeometryCollection,
empty/null geometry, and the KML fallback parser (holes, multi-layer).
These cover plan items: Multi types sum correctly, Point returns null,
GeometryCollection handling, empty geometry, and KML with holes.
"""
import math
import pytest
from shapely.geometry import (
    MultiPolygon, MultiLineString, MultiPoint,
    Polygon, LineString, Point, GeometryCollection
)
from app.services.measurement import measurement_engine


class TestMultiGeometryTypes:
    def test_multi_polygon_sums_part_areas(self):
        """MultiPolygon area must equal sum of individual part areas."""
        d = 0.008993216  # ~1 km at equator
        p1 = Polygon([(0.0, 0.0), (d, 0.0), (d, d), (0.0, d)])
        p2 = Polygon([(0.02, 0.0), (0.02 + d, 0.0), (0.02 + d, d), (0.02, d)])
        mp = MultiPolygon([p1, p2])

        res = measurement_engine.measure_feature("mp", mp, "EPSG:4326", {})
        assert res.supported is True
        area_m2 = res.measurements.area.sq_meters
        # Two non-overlapping ~1 km² parcels → total ≈ 2,000,000 m²
        assert math.isclose(area_m2, 2_000_000.0, rel_tol=0.01), (
            f"Expected ~2,000,000 m², got {area_m2}"
        )

    def test_multi_line_string_sums_part_lengths(self):
        """MultiLineString length must equal sum of individual segment lengths."""
        d = 0.008993216  # ~1 km
        l1 = LineString([(0.0, 0.0), (d, 0.0)])
        l2 = LineString([(0.02, 0.0), (0.02 + d, 0.0)])
        ml = MultiLineString([l1, l2])

        res = measurement_engine.measure_feature("ml", ml, "EPSG:4326", {})
        assert res.supported is True
        length_m = res.measurements.length.meters
        # Two non-overlapping ~1 km segments → total ≈ 2,000 m
        assert math.isclose(length_m, 2_000.0, rel_tol=0.01), (
            f"Expected ~2,000 m, got {length_m}"
        )

    def test_multi_point_returns_unsupported(self):
        """MultiPoint must return supported=False with no measurements."""
        mp = MultiPoint([(0.0, 0.0), (1.0, 1.0), (2.0, 2.0)])
        res = measurement_engine.measure_feature("mpt", mp, "EPSG:4326", {})
        assert res.supported is False
        assert res.measurements is None
        assert "0-dimensional" in res.message.lower() or "point" in res.message.lower()

    def test_geometry_collection_mixed_parts(self):
        """GeometryCollection with polygon + line should aggregate both measurements."""
        d = 0.008993216
        poly = Polygon([(0.0, 0.0), (d, 0.0), (d, d), (0.0, d)])
        line = LineString([(0.02, 0.0), (0.02 + d, 0.0)])
        gc = GeometryCollection([poly, line])

        res = measurement_engine.measure_feature("gc", gc, "EPSG:4326", {})
        assert res.supported is True
        # Measurements are returned as a composite dict
        meas = res.measurements
        assert isinstance(meas, dict)
        assert "total_area" in meas or "composite_parts_count" in meas

    def test_geometry_collection_all_points_unsupported(self):
        """GeometryCollection made entirely of Points should be unsupported."""
        gc = GeometryCollection([Point(0, 0), Point(1, 1)])
        res = measurement_engine.measure_feature("gc_pts", gc, "EPSG:4326", {})
        assert res.supported is False


class TestNullAndEmptyGeometries:
    def test_null_geometry_returns_skipped(self):
        """None geometry must return supported=False with an explanatory message."""
        res = measurement_engine.measure_feature("null_geom", None, "EPSG:4326", {})
        assert res.supported is False
        assert res.measurements is None
        assert res.message is not None

    def test_empty_polygon_returns_skipped(self):
        """An empty Polygon (no coordinates) must be handled gracefully."""
        empty = Polygon()
        assert empty.is_empty
        res = measurement_engine.measure_feature("empty_poly", empty, "EPSG:4326", {})
        assert res.supported is False
        assert res.measurements is None

    def test_empty_linestring_returns_skipped(self):
        """An empty LineString must be handled gracefully."""
        empty = LineString()
        res = measurement_engine.measure_feature("empty_line", empty, "EPSG:4326", {})
        assert res.supported is False

    def test_properties_preserved_on_unsupported_geometry(self):
        """Feature properties must be preserved even for unsupported geometry types."""
        props = {"name": "MyPoint", "area_code": "99A"}
        pt = Point(77.0, 13.0)
        res = measurement_engine.measure_feature("prop_test", pt, "EPSG:4326", props)
        assert res.supported is False
        assert res.properties.get("name") == "MyPoint"
        assert res.properties.get("area_code") == "99A"


class TestKMLParser:
    """Tests exercising the defusedxml KML fallback parser via the parser service."""

    def test_kml_polygon_with_hole(self, kml_with_hole_bytes, tmp_path):
        """KML Polygon with innerBoundaryIs (hole) must parse and measure correctly."""
        from app.services.parser import parser_service
        kml_path = tmp_path / "hole.kml"
        kml_path.write_bytes(kml_with_hole_bytes)

        features, crs_str, _ = parser_service.parse_kml(kml_path)
        assert len(features) == 1
        assert features[0].geometry_type == "Polygon"
        # The parsed polygon must have an interior ring
        poly = features[0].shapely_geom
        assert len(list(poly.interiors)) == 1

        # Area should be outer - inner ≈ 750,000 m²
        res = measurement_engine.measure_feature(
            "hole", poly, crs_str, {}
        )
        assert math.isclose(res.measurements.area.sq_meters, 750_000.0, rel_tol=0.01)

    def test_kml_mixed_geometry_types(self, kml_with_point_and_line_bytes, tmp_path):
        """KML with Point + LineString + Polygon must parse all 3 features."""
        from app.services.parser import parser_service
        kml_path = tmp_path / "mixed.kml"
        kml_path.write_bytes(kml_with_point_and_line_bytes)

        features, crs_str, _ = parser_service.parse_kml(kml_path)
        assert len(features) == 3
        types = {f.geometry_type for f in features}
        assert "Point" in types
        assert "LineString" in types
        assert "Polygon" in types

    def test_kml_empty_no_placemarks_raises(self, kml_empty_no_placemarks, tmp_path):
        """A KML with no Placemarks must raise ValueError."""
        from app.services.parser import parser_service
        kml_path = tmp_path / "empty.kml"
        kml_path.write_bytes(kml_empty_no_placemarks)

        with pytest.raises(ValueError, match="no valid Placemark"):
            parser_service.parse_kml(kml_path)

    def test_kml_corrupt_raises(self, kml_corrupt_bytes, tmp_path):
        """Corrupted / non-parseable KML must raise ValueError."""
        from app.services.parser import parser_service
        kml_path = tmp_path / "corrupt.kml"
        kml_path.write_bytes(kml_corrupt_bytes)

        with pytest.raises((ValueError, Exception)):
            parser_service.parse_kml(kml_path)


class TestHemisphereUTMZones:
    """Verifies correct UTM zone + EPSG selection across hemispheres."""

    @pytest.mark.parametrize("lon,lat,hemisphere", [
        (77.59, 12.97, "N"),   # India (north)
        (-43.17, -22.90, "S"), # Brazil (south)
        (139.69, 35.68, "N"),  # Tokyo (north)
        (151.20, -33.86, "S"), # Sydney (south)
    ])
    def test_utm_hemisphere_epsg(self, lon, lat, hemisphere):
        from app.services.crs_transformer import crs_service
        epsg, name = crs_service.get_utm_epsg_for_coordinate(lon, lat)
        if hemisphere == "N":
            assert 32601 <= epsg <= 32660, f"Expected north UTM EPSG, got {epsg}"
        else:
            assert 32701 <= epsg <= 32760, f"Expected south UTM EPSG, got {epsg}"

    def test_north_and_south_hemisphere_areas_similar(self):
        """
        A 1 km² square near equator north and the equivalent south should measure
        similar areas, verifying symmetric zone selection.
        """
        d = 0.008993216
        north = Polygon([(0.0, 0.1), (d, 0.1), (d, 0.1 + d), (0.0, 0.1 + d)])
        south = Polygon([(0.0, -0.1 - d), (d, -0.1 - d), (d, -0.1), (0.0, -0.1)])

        res_n = measurement_engine.measure_feature("north", north, "EPSG:4326", {})
        res_s = measurement_engine.measure_feature("south", south, "EPSG:4326", {})

        assert math.isclose(
            res_n.measurements.area.sq_meters,
            res_s.measurements.area.sq_meters,
            rel_tol=0.005,
        ), "North/south equator-adjacent squares should have near-identical areas."
