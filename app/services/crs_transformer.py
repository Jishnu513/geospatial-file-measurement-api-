import math
from functools import lru_cache
from typing import Optional, Tuple
import numpy as np
import pyproj
from pyproj import CRS, Transformer
from shapely.geometry.base import BaseGeometry
import shapely


class CRSTransformerService:
    def __init__(self):
        self._transformer_cache = {}

    @lru_cache(maxsize=128)
    def parse_crs(self, crs_input: Optional[str]) -> CRS:
        """
        Parses and normalizes a CRS input string/WKT into a pyproj CRS object.
        Falls back to EPSG:4326 if None or invalid.
        """
        if not crs_input:
            return CRS.from_epsg(4326)
        try:
            return CRS.from_user_input(crs_input)
        except Exception:
            return CRS.from_epsg(4326)

    def get_utm_epsg_for_coordinate(self, lon: float, lat: float) -> Tuple[int, str]:
        """
        Calculates the appropriate projected EPSG code for a given lon/lat coordinate.
        Handles standard UTM zones (lat between -84 and 84) and polar regions.
        """
        # Polar regions fallback to UPS (Universal Polar Stereographic) or World Equal-Area
        if lat > 84.0:
            return 32661, "UPS North (EPSG:32661)"
        elif lat < -80.0:
            return 32761, "UPS South (EPSG:32761)"

        # Normalize longitude between -180 and 180
        norm_lon = ((lon + 180.0) % 360.0) - 180.0
        utm_zone = int(math.floor((norm_lon + 180.0) / 6.0)) + 1
        utm_zone = max(1, min(60, utm_zone))

        if lat >= 0:
            epsg = 32600 + utm_zone
            name = f"UTM Zone {utm_zone}N (EPSG:{epsg})"
        else:
            epsg = 32700 + utm_zone
            name = f"UTM Zone {utm_zone}S (EPSG:{epsg})"

        return epsg, name

    def get_transformer(self, source_crs: CRS, target_crs: CRS) -> Transformer:
        """
        Returns a cached pyproj Transformer with always_xy=True.
        """
        cache_key = (source_crs.to_string(), target_crs.to_string())
        if cache_key not in self._transformer_cache:
            self._transformer_cache[cache_key] = Transformer.from_crs(
                source_crs, target_crs, always_xy=True
            )
        return self._transformer_cache[cache_key]

    def project_geometry(
        self, geom: BaseGeometry, input_crs: CRS
    ) -> Tuple[BaseGeometry, str, CRS]:
        """
        Projects a shapely geometry to an optimal metric Cartesian CRS.
        - If input_crs is already projected, returns the geometry directly with its CRS.
        - If input_crs is geographic, dynamically calculates the optimal UTM zone from the
          feature's centroid and reprojects to meters.
        """
        if geom is None or geom.is_empty:
            return geom, str(input_crs.to_string()), input_crs

        # Ensure 2D geometry (strip any Z values)
        geom_2d = shapely.force_2d(geom)

        # 1. If already projected (units are linear/meters/feet)
        if input_crs.is_projected:
            crs_name = input_crs.name or input_crs.to_string()
            return geom_2d, crs_name, input_crs

        # 2. If geographic (degrees), find centroid in lon/lat
        try:
            centroid = geom_2d.centroid
            lon, lat = centroid.x, centroid.y
        except Exception:
            lon, lat = 0.0, 0.0

        target_epsg, crs_name = self.get_utm_epsg_for_coordinate(lon, lat)
        target_crs = CRS.from_epsg(target_epsg)

        # Reproject using vectorized shapely 2.x transform
        transformer = self.get_transformer(input_crs, target_crs)
        projected_geom = shapely.transform(
            geom_2d,
            lambda coords: np.column_stack(transformer.transform(coords[:, 0], coords[:, 1]))
        )

        return projected_geom, crs_name, target_crs


crs_service = CRSTransformerService()

