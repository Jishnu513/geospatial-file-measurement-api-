import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import defusedxml.ElementTree as ET
import numpy as np
import pandas as pd
import pyogrio
from shapely.geometry import (
    Point, MultiPoint, LineString, MultiLineString,
    Polygon, MultiPolygon, GeometryCollection, shape, mapping
)
from shapely.geometry.base import BaseGeometry
import shapely

from app.services.security import SecurityValidator


class ParsedFeature:
    def __init__(
        self,
        feature_id: Any,
        geometry_type: str,
        shapely_geom: Optional[BaseGeometry],
        geojson_geom: Optional[Dict[str, Any]],
        crs: str,
        properties: Dict[str, Any],
        error: Optional[str] = None,
    ):
        self.feature_id = feature_id
        self.geometry_type = geometry_type
        self.shapely_geom = shapely_geom
        self.geojson_geom = geojson_geom
        self.crs = crs
        self.properties = properties
        self.error = error


class GeospatialParser:
    @staticmethod
    def _sanitize_properties(props: Dict[str, Any]) -> Dict[str, Any]:
        """Convert numpy types, timestamps, and NaN to clean Python primitives."""
        sanitized = {}
        for k, v in props.items():
            if k == "geometry":
                continue
            if pd.isna(v):
                sanitized[k] = None
            elif isinstance(v, (np.integer, int)):
                sanitized[k] = int(v)
            elif isinstance(v, (np.floating, float)):
                sanitized[k] = float(v)
            elif isinstance(v, (pd.Timestamp, np.datetime64)):
                sanitized[k] = str(v)
            elif isinstance(v, bytes):
                sanitized[k] = v.decode("utf-8", errors="replace")
            else:
                sanitized[k] = str(v) if not isinstance(v, (str, bool, list, dict, type(None))) else v
        return sanitized

    @classmethod
    def parse_shapefile_zip(
        cls, zip_path: Path, extract_dir: Path
    ) -> Tuple[List[ParsedFeature], str, Optional[str]]:
        """
        Extracts and parses a Shapefile ZIP archive using Pyogrio.
        Returns (features_list, detected_crs_str, optional_warning).
        """
        shp_file, has_prj = SecurityValidator.safe_extract_zip(zip_path, extract_dir)
        warning = None
        if not has_prj:
            warning = "Missing .prj projection file in Shapefile archive; defaulting to EPSG:4326."

        try:
            df = pyogrio.read_dataframe(str(shp_file))
        except Exception as e:
            raise ValueError(f"Failed to read Shapefile with Pyogrio engine: {str(e)}")

        crs_str = "EPSG:4326"
        if df.crs is not None:
            crs_str = df.crs.to_string()
        elif not has_prj:
            crs_str = "EPSG:4326"

        features: List[ParsedFeature] = []
        for idx, row in df.iterrows():
            geom = row.get("geometry")
            raw_props = {col: row[col] for col in df.columns if col != "geometry"}
            clean_props = cls._sanitize_properties(raw_props)

            if geom is None or (isinstance(geom, BaseGeometry) and geom.is_empty):
                features.append(
                    ParsedFeature(
                        feature_id=idx,
                        geometry_type="None",
                        shapely_geom=None,
                        geojson_geom=None,
                        crs=crs_str,
                        properties=clean_props,
                        error="Geometry is empty or null.",
                    )
                )
                continue

            try:
                geom_2d = shapely.force_2d(geom)
                if not geom_2d.is_valid:
                    geom_2d = shapely.make_valid(geom_2d)

                features.append(
                    ParsedFeature(
                        feature_id=idx,
                        geometry_type=geom_2d.geom_type,
                        shapely_geom=geom_2d,
                        geojson_geom=mapping(geom_2d),
                        crs=crs_str,
                        properties=clean_props,
                    )
                )
            except Exception as feat_err:
                features.append(
                    ParsedFeature(
                        feature_id=idx,
                        geometry_type=getattr(geom, "geom_type", "Unknown"),
                        shapely_geom=geom,
                        geojson_geom=None,
                        crs=crs_str,
                        properties=clean_props,
                        error=f"Error processing feature geometry: {str(feat_err)}",
                    )
                )

        return features, crs_str, warning

    @classmethod
    def parse_kml(cls, kml_path: Path) -> Tuple[List[ParsedFeature], str, Optional[str]]:
        """
        Parses a KML file. First attempts pyogrio KML driver; falls back to
        secure XML parsing with defusedxml.
        """
        crs_str = "EPSG:4326"
        
        # 1. Attempt pyogrio reading
        try:
            df = pyogrio.read_dataframe(str(kml_path))
            features: List[ParsedFeature] = []
            for idx, row in df.iterrows():
                geom = row.get("geometry")
                raw_props = {col: row[col] for col in df.columns if col != "geometry"}
                clean_props = cls._sanitize_properties(raw_props)

                if geom is None or (isinstance(geom, BaseGeometry) and geom.is_empty):
                    features.append(
                        ParsedFeature(
                            feature_id=idx,
                            geometry_type="None",
                            shapely_geom=None,
                            geojson_geom=None,
                            crs=crs_str,
                            properties=clean_props,
                            error="Empty geometry",
                        )
                    )
                    continue

                geom_2d = shapely.force_2d(geom)
                if not geom_2d.is_valid:
                    geom_2d = shapely.make_valid(geom_2d)

                features.append(
                    ParsedFeature(
                        feature_id=idx,
                        geometry_type=geom_2d.geom_type,
                        shapely_geom=geom_2d,
                        geojson_geom=mapping(geom_2d),
                        crs=crs_str,
                        properties=clean_props,
                    )
                )
            return features, crs_str, None
        except Exception:
            # 2. Fallback to robust pure-python defusedxml KML parser
            return cls._parse_kml_xml_fallback(kml_path)

    @classmethod
    def _parse_kml_xml_fallback(
        cls, kml_path: Path
    ) -> Tuple[List[ParsedFeature], str, Optional[str]]:
        """
        Pure-Python fallback KML Placemark parser with defusedxml.
        Handles nested Folders, Polygons with inner holes (innerBoundaryIs),
        LineStrings, Points, and MultiGeometry.
        """
        try:
            tree = ET.parse(str(kml_path))
            root = tree.getroot()
        except Exception as e:
            raise ValueError(f"Corrupted or invalid KML file: {str(e)}")

        crs_str = "EPSG:4326"
        features: List[ParsedFeature] = []
        feature_idx = 0

        # Helper to strip XML namespaces
        def strip_ns(tag: str) -> str:
            return tag.split("}")[-1] if "}" in tag else tag

        def parse_coord_str(text: str) -> List[Tuple[float, float]]:
            coords = []
            if not text:
                return coords
            for token in text.strip().split():
                parts = token.strip().split(",")
                if len(parts) >= 2:
                    try:
                        lon = float(parts[0])
                        lat = float(parts[1])
                        coords.append((lon, lat))
                    except ValueError:
                        continue
            return coords

        def parse_geometry_element(elem) -> Optional[BaseGeometry]:
            tag = strip_ns(elem.tag)
            if tag == "Point":
                coord_elem = None
                for c in elem.iter():
                    if strip_ns(c.tag) == "coordinates":
                        coord_elem = c
                        break
                if coord_elem is not None and coord_elem.text:
                    coords = parse_coord_str(coord_elem.text)
                    if coords:
                        return Point(coords[0])
                return None

            elif tag in ("LineString", "LinearRing"):
                coord_elem = None
                for c in elem.iter():
                    if strip_ns(c.tag) == "coordinates":
                        coord_elem = c
                        break
                if coord_elem is not None and coord_elem.text:
                    coords = parse_coord_str(coord_elem.text)
                    if len(coords) >= 2:
                        return LineString(coords)
                return None

            elif tag == "Polygon":
                exterior_coords = []
                interiors = []
                for child in elem:
                    child_tag = strip_ns(child.tag)
                    if child_tag == "outerBoundaryIs":
                        for sub in child.iter():
                            if strip_ns(sub.tag) == "coordinates" and sub.text:
                                exterior_coords = parse_coord_str(sub.text)
                    elif child_tag == "innerBoundaryIs":
                        for sub in child.iter():
                            if strip_ns(sub.tag) == "coordinates" and sub.text:
                                hole_coords = parse_coord_str(sub.text)
                                if len(hole_coords) >= 3:
                                    interiors.append(hole_coords)

                if len(exterior_coords) >= 3:
                    return Polygon(shell=exterior_coords, holes=interiors if interiors else None)
                return None

            elif tag == "MultiGeometry":
                sub_geoms = []
                for child in elem:
                    sub_g = parse_geometry_element(child)
                    if sub_g is not None:
                        sub_geoms.append(sub_g)
                if sub_geoms:
                    return GeometryCollection(sub_geoms)
                return None

            return None

        # Find all Placemarks across all Folders and Document roots
        for elem in root.iter():
            if strip_ns(elem.tag) == "Placemark":
                feature_idx += 1
                fid = elem.attrib.get("id", f"feature_{feature_idx}")
                props: Dict[str, Any] = {}
                geom: Optional[BaseGeometry] = None

                for child in elem:
                    child_tag = strip_ns(child.tag)
                    if child_tag == "name":
                        props["name"] = child.text.strip() if child.text else ""
                    elif child_tag == "description":
                        props["description"] = child.text.strip() if child.text else ""
                    elif child_tag == "ExtendedData":
                        for data_child in child.iter():
                            d_tag = strip_ns(data_child.tag)
                            if d_tag in ("Data", "SimpleData"):
                                name_attr = data_child.attrib.get("name")
                                val = data_child.find(f"{{{data_child.tag.split('}')[0][1:]}}}value") if "}" in data_child.tag else data_child.find("value")
                                val_text = val.text if val is not None else data_child.text
                                if name_attr:
                                    props[name_attr] = val_text.strip() if val_text else ""
                    elif child_tag in ("Point", "LineString", "LinearRing", "Polygon", "MultiGeometry"):
                        geom = parse_geometry_element(child)

                if geom is None:
                    features.append(
                        ParsedFeature(
                            feature_id=fid,
                            geometry_type="None",
                            shapely_geom=None,
                            geojson_geom=None,
                            crs=crs_str,
                            properties=props,
                            error="No supported geometry found in Placemark.",
                        )
                    )
                else:
                    geom_2d = shapely.force_2d(geom)
                    if not geom_2d.is_valid:
                        geom_2d = shapely.make_valid(geom_2d)

                    features.append(
                        ParsedFeature(
                            feature_id=fid,
                            geometry_type=geom_2d.geom_type,
                            shapely_geom=geom_2d,
                            geojson_geom=mapping(geom_2d),
                            crs=crs_str,
                            properties=props,
                        )
                    )

        if not features:
            raise ValueError("KML file contains no valid Placemark features.")

        return features, crs_str, None


parser_service = GeospatialParser()
