from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pyproj
from pyproj import Geod
import shapely
from shapely.geometry.base import BaseGeometry
from shapely.geometry import (
    Point, MultiPoint, LineString, MultiLineString,
    Polygon, MultiPolygon, GeometryCollection
)
from app.models.schemas import (
    AreaMeasurements, LengthMeasurements,
    PolygonMeasurementDetail, LineMeasurementDetail,
    FeatureMeasurement, MeasurementsSummary
)
from app.services.crs_transformer import crs_service


class MeasurementEngine:
    def __init__(self):
        self.geod = Geod(ellps="WGS84")

    def _convert_area(self, sq_meters: float) -> AreaMeasurements:
        return AreaMeasurements(
            sq_meters=round(sq_meters, 4),
            hectares=round(sq_meters / 10000.0, 6),
            sq_kilometers=round(sq_meters / 1000000.0, 6),
            acres=round(sq_meters * 0.000247105381, 6),
            sq_feet=round(sq_meters * 10.7639104, 4),
        )

    def _convert_length(self, meters: float) -> LengthMeasurements:
        return LengthMeasurements(
            meters=round(meters, 4),
            kilometers=round(meters / 1000.0, 6),
            feet=round(meters * 3.2808399, 4),
            miles=round(meters * 0.000621371192, 6),
        )

    def measure_feature(
        self,
        feature_id: Any,
        raw_geom: Optional[BaseGeometry],
        input_crs_str: str,
        properties: Dict[str, Any],
    ) -> FeatureMeasurement:
        """
        Calculates metric measurements for a single feature geometry.
        Applies repair (make_valid), per-feature projection to UTM/Cartesian,
        and computes both Cartesian measurements and Geodesic WGS84 cross-checks.
        """
        # 1. Check for null or empty geometry
        if raw_geom is None or raw_geom.is_empty:
            return FeatureMeasurement(
                feature_id=feature_id,
                geometry_type="None" if raw_geom is None else raw_geom.geom_type,
                supported=False,
                message="Geometry is null or empty.",
                measurements=None,
                properties=properties,
                centroid=None,
                bounding_box=None,
            )

        # 2. Geometry repair and 2D conversion
        if not raw_geom.is_valid:
            geom = shapely.make_valid(raw_geom)
        else:
            geom = raw_geom
        geom = shapely.force_2d(geom)

        geom_type = geom.geom_type
        input_crs = crs_service.parse_crs(input_crs_str)

        # Compute centroid & bounds
        try:
            centroid_pt = geom.centroid
            centroid_coords = [round(centroid_pt.x, 6), round(centroid_pt.y, 6)]
            bounds = [round(b, 6) for b in geom.bounds]
        except Exception:
            centroid_coords = None
            bounds = None

        # 3. Handle Points / MultiPoints (Unsupported for area/length measurement)
        if isinstance(geom, (Point, MultiPoint)):
            return FeatureMeasurement(
                feature_id=feature_id,
                geometry_type=geom_type,
                supported=False,
                message="Point geometries represent 0-dimensional coordinates and do not possess length or area.",
                measurements=None,
                properties=properties,
                centroid=centroid_coords,
                bounding_box=bounds,
            )

        # 4. Project geometry to Cartesian metric CRS (per-feature UTM)
        try:
            proj_geom, proj_crs_name, target_crs = crs_service.project_geometry(geom, input_crs)
        except Exception as e:
            return FeatureMeasurement(
                feature_id=feature_id,
                geometry_type=geom_type,
                supported=False,
                message=f"Reprojection failed: {str(e)}",
                measurements=None,
                properties=properties,
                centroid=centroid_coords,
                bounding_box=bounds,
            )

        # 5. Measure Polygons & MultiPolygons
        if isinstance(geom, (Polygon, MultiPolygon)):
            cartesian_area = float(proj_geom.area)
            cartesian_perimeter = float(proj_geom.length)

            # Calculate geodesic WGS84 area and perimeter
            geodesic_area = None
            geodesic_perimeter = None
            try:
                # If input is geographic or can be converted to WGS84
                if input_crs.is_geographic:
                    wgs84_geom = geom
                else:
                    to_wgs84 = crs_service.get_transformer(input_crs, crs_service.parse_crs("EPSG:4326"))
                    wgs84_geom = shapely.transform(
                        geom,
                        lambda coords: np.column_stack(to_wgs84.transform(coords[:, 0], coords[:, 1]))
                    )
                
                geo_area, geo_perim = self.geod.geometry_area_perimeter(wgs84_geom)
                geodesic_area = round(abs(geo_area), 4)
                geodesic_perimeter = round(abs(geo_perim), 4)
            except Exception:
                pass

            detail = PolygonMeasurementDetail(
                area=self._convert_area(cartesian_area),
                perimeter=self._convert_length(cartesian_perimeter),
                geodesic_area_sq_meters=geodesic_area,
                geodesic_perimeter_meters=geodesic_perimeter,
            )

            # Add projected CRS info to properties
            props_with_crs = {**properties, "_projected_crs": proj_crs_name}

            return FeatureMeasurement(
                feature_id=feature_id,
                geometry_type=geom_type,
                supported=True,
                message="Successfully calculated area and perimeter.",
                measurements=detail,
                properties=props_with_crs,
                centroid=centroid_coords,
                bounding_box=bounds,
            )

        # 6. Measure LineStrings & MultiLineStrings
        if isinstance(geom, (LineString, MultiLineString)):
            cartesian_length = float(proj_geom.length)

            # Geodesic length
            geodesic_length = None
            try:
                if input_crs.is_geographic:
                    wgs84_geom = geom
                else:
                    to_wgs84 = crs_service.get_transformer(input_crs, crs_service.parse_crs("EPSG:4326"))
                    wgs84_geom = shapely.transform(
                        geom,
                        lambda coords: np.column_stack(to_wgs84.transform(coords[:, 0], coords[:, 1]))
                    )
                
                geo_len = self.geod.geometry_length(wgs84_geom)
                geodesic_length = round(abs(geo_len), 4)
            except Exception:
                pass

            detail = LineMeasurementDetail(
                length=self._convert_length(cartesian_length),
                geodesic_length_meters=geodesic_length,
            )

            props_with_crs = {**properties, "_projected_crs": proj_crs_name}

            return FeatureMeasurement(
                feature_id=feature_id,
                geometry_type=geom_type,
                supported=True,
                message="Successfully calculated line length.",
                measurements=detail,
                properties=props_with_crs,
                centroid=centroid_coords,
                bounding_box=bounds,
            )

        # 7. GeometryCollection / Composite Handling
        if isinstance(geom, GeometryCollection):
            total_sub_area = 0.0
            total_sub_length = 0.0
            sub_count = 0
            for part in geom.geoms:
                part_proj, _, _ = crs_service.project_geometry(part, input_crs)
                if isinstance(part, (Polygon, MultiPolygon)):
                    total_sub_area += float(part_proj.area)
                    sub_count += 1
                elif isinstance(part, (LineString, MultiLineString)):
                    total_sub_length += float(part_proj.length)
                    sub_count += 1

            props_with_crs = {**properties, "_projected_crs": proj_crs_name}
            composite_meas = {
                "composite_parts_count": len(geom.geoms),
                "total_area": self._convert_area(total_sub_area).model_dump(),
                "total_length": self._convert_length(total_sub_length).model_dump(),
            }

            return FeatureMeasurement(
                feature_id=feature_id,
                geometry_type=geom_type,
                supported=True if sub_count > 0 else False,
                message=f"Measured composite GeometryCollection containing {len(geom.geoms)} parts.",
                measurements=composite_meas,
                properties=props_with_crs,
                centroid=centroid_coords,
                bounding_box=bounds,
            )

        # 8. Any other unrecognized geometry type
        return FeatureMeasurement(
            feature_id=feature_id,
            geometry_type=geom_type,
            supported=False,
            message=f"Geometry type '{geom_type}' is not supported for measurement.",
            measurements=None,
            properties=properties,
            centroid=centroid_coords,
            bounding_box=bounds,
        )

    def aggregate_measurements(
        self, measurements: List[FeatureMeasurement]
    ) -> MeasurementsSummary:
        """
        Computes aggregate metrics across all processed features.
        """
        total_features = len(measurements)
        supported_count = 0
        unsupported_count = 0
        total_area_sq_m = 0.0
        total_length_m = 0.0
        breakdown: Dict[str, int] = {}

        for m in measurements:
            geom_t = m.geometry_type
            breakdown[geom_t] = breakdown.get(geom_t, 0) + 1

            if m.supported and m.measurements:
                supported_count += 1
                meas = m.measurements
                # Polygon measurements
                if isinstance(meas, PolygonMeasurementDetail):
                    total_area_sq_m += meas.area.sq_meters
                elif isinstance(meas, dict) and "area" in meas:
                    area_dict = meas.get("area", {})
                    total_area_sq_m += area_dict.get("sq_meters", 0.0)
                # Line measurements
                elif isinstance(meas, LineMeasurementDetail):
                    total_length_m += meas.length.meters
                elif isinstance(meas, dict) and "length" in meas:
                    len_dict = meas.get("length", {})
                    total_length_m += len_dict.get("meters", 0.0)
                elif isinstance(meas, dict) and "total_area" in meas:
                    total_area_sq_m += meas.get("total_area", {}).get("sq_meters", 0.0)
                    total_length_m += meas.get("total_length", {}).get("meters", 0.0)
            else:
                unsupported_count += 1

        return MeasurementsSummary(
            total_features=total_features,
            supported_features_count=supported_count,
            unsupported_features_count=unsupported_count,
            total_area_sq_m=round(total_area_sq_m, 4),
            total_area_hectares=round(total_area_sq_m / 10000.0, 6),
            total_area_acres=round(total_area_sq_m * 0.000247105381, 6),
            total_length_m=round(total_length_m, 4),
            total_length_km=round(total_length_m / 1000.0, 6),
            geometry_breakdown=breakdown,
        )


measurement_engine = MeasurementEngine()
