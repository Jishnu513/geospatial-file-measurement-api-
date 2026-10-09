import os
import zipfile
from pathlib import Path
import geopandas as gpd
from shapely.geometry import Polygon, LineString, Point

SAMPLE_DIR = Path(__file__).resolve().parent
SAMPLE_DIR.mkdir(parents=True, exist_ok=True)


def generate_known_1km_square_kml():
    """
    Generates a 1 km x 1 km square at the equator (lon 0 to 0.0089932, lat 0 to 0.0089932)
    in EPSG:4326.
    Exact area should be ~1,000,000 m² (1 sq km = 100 hectares).
    """
    kml_content = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>Known 1km Square</name>
    <Placemark id="square_1km">
      <name>Benchmark 1km Square</name>
      <description>Known 1km x 1km calibration square</description>
      <ExtendedData>
        <Data name="expected_area_sq_m"><value>1000000</value></Data>
        <Data name="expected_side_length_m"><value>1000</value></Data>
      </ExtendedData>
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
    kml_path = SAMPLE_DIR / "sample_known_square.kml"
    with open(kml_path, "w", encoding="utf-8") as f:
        f.write(kml_content)
    print(f"Created {kml_path}")


def generate_agricultural_kml():
    """
    Generates agricultural dataset with polygons, polygon with a hole, linestrings, and points.
    """
    kml_content = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>GreenValley Agricultural Farm</name>
    <Placemark id="field_alpha">
      <name>Field Alpha (Wheat)</name>
      <description>Primary wheat cultivation sector</description>
      <ExtendedData>
        <Data name="crop_type"><value>Wheat</value></Data>
        <Data name="irrigation"><value>Drip</value></Data>
      </ExtendedData>
      <Polygon>
        <outerBoundaryIs>
          <LinearRing>
            <coordinates>
              77.5800,12.9700,0
              77.5850,12.9700,0
              77.5850,12.9750,0
              77.5800,12.9750,0
              77.5800,12.9700,0
            </coordinates>
          </LinearRing>
        </outerBoundaryIs>
      </Polygon>
    </Placemark>
    <Placemark id="field_donut">
      <name>Field Donut (With Lake Hole)</name>
      <Polygon>
        <outerBoundaryIs>
          <LinearRing>
            <coordinates>
              77.5900,12.9700,0
              77.6000,12.9700,0
              77.6000,12.9800,0
              77.5900,12.9800,0
              77.5900,12.9700,0
            </coordinates>
          </LinearRing>
        </outerBoundaryIs>
        <innerBoundaryIs>
          <LinearRing>
            <coordinates>
              77.5930,12.9730,0
              77.5970,12.9730,0
              77.5970,12.9770,0
              77.5930,12.9770,0
              77.5930,12.9730,0
            </coordinates>
          </LinearRing>
        </innerBoundaryIs>
      </Polygon>
    </Placemark>
    <Placemark id="canal_main">
      <name>Main Irrigation Canal</name>
      <LineString>
        <coordinates>
          77.5800,12.9700,0
          77.5850,12.9720,0
          77.5900,12.9750,0
          77.6000,12.9800,0
        </coordinates>
      </LineString>
    </Placemark>
    <Placemark id="sensor_01">
      <name>Soil Moisture Sensor 1</name>
      <Point>
        <coordinates>77.5825,12.9725,0</coordinates>
      </Point>
    </Placemark>
  </Document>
</kml>"""
    kml_path = SAMPLE_DIR / "sample_agricultural_parcels.kml"
    with open(kml_path, "w", encoding="utf-8") as f:
        f.write(kml_content)
    print(f"Created {kml_path}")


def generate_cadastral_shapefile_zip():
    """
    Generates a Shapefile ZIP containing polygons, lines, and points.
    """
    # 1. Parcels (Polygons)
    p1 = Polygon([(73.850, 18.520), (73.855, 18.520), (73.855, 18.525), (73.850, 18.525)])
    p2 = Polygon([(73.856, 18.520), (73.860, 18.520), (73.860, 18.525), (73.856, 18.525)])
    
    gdf_parcels = gpd.GeoDataFrame({
        "parcel_id": ["P-101", "P-102"],
        "zone_type": ["Commercial", "Residential"],
        "geometry": [p1, p2]
    }, crs="EPSG:4326")

    temp_shp_dir = SAMPLE_DIR / "temp_shp"
    temp_shp_dir.mkdir(parents=True, exist_ok=True)
    
    shp_file = temp_shp_dir / "cadastral_parcels.shp"
    gdf_parcels.to_file(shp_file, driver="ESRI Shapefile")

    # Zip files together
    zip_path = SAMPLE_DIR / "sample_cadastral.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in temp_shp_dir.iterdir():
            zf.write(f, arcname=f.name)
            
    # Cleanup temp dir
    for f in temp_shp_dir.iterdir():
        f.unlink()
    temp_shp_dir.rmdir()

    print(f"Created {zip_path}")


def generate_no_prj_shapefile_zip():
    """
    Generates a Shapefile ZIP without a .prj file to test fallback behavior.
    """
    p1 = Polygon([(10.0, 50.0), (10.01, 50.0), (10.01, 50.01), (10.0, 50.01)])
    gdf = gpd.GeoDataFrame({"name": ["Zone A"], "geometry": [p1]}, crs="EPSG:4326")
    
    temp_shp_dir = SAMPLE_DIR / "temp_no_prj"
    temp_shp_dir.mkdir(parents=True, exist_ok=True)
    shp_file = temp_shp_dir / "no_prj_sample.shp"
    gdf.to_file(shp_file, driver="ESRI Shapefile")

    # Remove the .prj file
    prj_file = temp_shp_dir / "no_prj_sample.prj"
    if prj_file.exists():
        prj_file.unlink()

    zip_path = SAMPLE_DIR / "sample_no_prj.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in temp_shp_dir.iterdir():
            zf.write(f, arcname=f.name)

    for f in temp_shp_dir.iterdir():
        f.unlink()
    temp_shp_dir.rmdir()
    print(f"Created {zip_path}")


if __name__ == "__main__":
    generate_known_1km_square_kml()
    generate_agricultural_kml()
    generate_cadastral_shapefile_zip()
    generate_no_prj_shapefile_zip()
    print("All sample datasets generated successfully!")
