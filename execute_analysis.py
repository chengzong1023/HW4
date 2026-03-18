#!/usr/bin/env python3
"""
Execute ARIA v2.0 analysis directly
"""

import geopandas as gpd
import pandas as pd
import numpy as np
import rioxarray as rxr
from rasterstats import zonal_stats
import matplotlib.pyplot as plt
from shapely.geometry import Point
from pathlib import Path
import os
import warnings
warnings.filterwarnings("ignore")

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

SLOPE_THRESHOLD = float(os.getenv("SLOPE_THRESHOLD", 30))
ELEVATION_LOW = float(os.getenv("ELEVATION_LOW", 50))
BUFFER_HIGH = float(os.getenv("BUFFER_HIGH", 500))
TARGET_COUNTY = os.getenv("TARGET_COUNTY", "花蓮縣")

# Data paths
township_path = r"C:\Users\admin\Desktop\遙測\鄉(鎮、市、區)界線1140318\TOWN_MOI_1140318.shp"
shelter_csv_path = r"C:\Users\admin\Desktop\遙測\避難收容處所點位檔案v9.csv"
dem_path = r"C:\Users\admin\Desktop\遙測\dem_20m_hualien.tif"
river_path = r"C:\Users\admin\Desktop\遙測\RIVERPOLY\riverpoly\riverpoly.shp"

print(f"Configuration: {TARGET_COUNTY}, Slope: {SLOPE_THRESHOLD}°, Elevation: {ELEVATION_LOW}m, Buffer: {BUFFER_HIGH}m")

# Load township polygons
print("Loading township boundaries...")
townships = gpd.read_file(township_path).to_crs(epsg=3826)
county_towns = townships[townships["COUNTYNAME"] == TARGET_COUNTY].copy()
county_boundary = county_towns.dissolve().reset_index(drop=True)
county_boundary_buffer = county_boundary.copy()
county_boundary_buffer["geometry"] = county_boundary_buffer.buffer(1000)

# Load shelter data
print("Loading shelter data...")
shelter_df = pd.read_csv(shelter_csv_path)
shelter_df["經度"] = pd.to_numeric(shelter_df["經度"], errors="coerce")
shelter_df["緯度"] = pd.to_numeric(shelter_df["緯度"], errors="coerce")

county_shelter_df = shelter_df[
    shelter_df["縣市及鄉鎮市區"].astype(str).str.startswith(TARGET_COUNTY)
].dropna(subset=["經度", "緯度"]).copy()

shelters = gpd.GeoDataFrame(
    county_shelter_df,
    geometry=gpd.points_from_xy(county_shelter_df["經度"], county_shelter_df["緯度"]),
    crs="EPSG:4326"
).to_crs(epsg=3826)

# Load river data
print("Loading river data...")
rivers = gpd.read_file(river_path).to_crs(epsg=3826)
rivers_in_county = gpd.sjoin(rivers, county_boundary, predicate="intersects")
rivers_county = gpd.overlay(rivers, county_boundary_buffer, how="intersection")

print(f"Data loaded: {len(county_towns)} townships, {len(shelters)} shelters, {len(rivers_county)} rivers")

# Calculate river distances
print("Calculating river distances...")
shelters["river_distance_m"] = shelters.geometry.apply(lambda geom: rivers_county.distance(geom).min())

def river_distance_category(d):
    if d < 500:
        return "<500m"
    elif d < 1000:
        return "500-1000m"
    else:
        return ">=1000m"

shelters["river_distance_category"] = shelters["river_distance_m"].apply(river_distance_category)

# Load and process DEM
print("Loading and processing DEM...")
dem = rxr.open_rasterio(dem_path, masked=True)
clip_boundary = county_boundary_buffer.copy()
if dem.rio.crs != clip_boundary.crs:
    clip_boundary = clip_boundary.to_crs(dem.rio.crs)
dem_clip = dem.rio.clip(clip_boundary.geometry, clip_boundary.crs, drop=True)

# Calculate slope
dem_arr = dem_clip.values[0].astype("float64")
if np.ma.isMaskedArray(dem_arr):
    dem_arr = dem_arr.filled(np.nan)

res_x, res_y = dem_clip.rio.resolution()
pixel_size = abs(res_x)
dy, dx = np.gradient(dem_arr, pixel_size)
slope_arr = np.degrees(np.arctan(np.sqrt(dx**2 + dy**2)))
dem_affine = dem_clip.rio.transform()

print(f"DEM processed: pixel size={pixel_size}m, elevation range={np.nanmin(dem_arr):.1f}-{np.nanmax(dem_arr):.1f}m")

# Zonal statistics
print("Calculating zonal statistics...")
shelter_buffers = shelters.copy()
shelter_buffers["geometry"] = shelter_buffers.buffer(BUFFER_HIGH)

zs_elev = zonal_stats(
    shelter_buffers,
    dem_arr,
    affine=dem_affine,
    stats=["mean", "std"],
    nodata=np.nan,
)

zs_slope = zonal_stats(
    shelter_buffers,
    slope_arr,
    affine=dem_affine,
    stats=["max"],
    nodata=np.nan,
)

terrain_df = pd.DataFrame(zs_elev).rename(columns={
    "mean": "mean_elevation",
    "std": "std_elevation",
})
terrain_df["max_slope"] = pd.DataFrame(zs_slope)["max"]

shelters = shelters.reset_index(drop=True)
shelters = pd.concat([shelters, terrain_df], axis=1)

# Risk classification
print("Classifying risk levels...")
def classify_risk(row):
    d = row["river_distance_m"]
    s = row["max_slope"]
    e = row["mean_elevation"]

    if pd.notna(d) and pd.notna(s) and d < BUFFER_HIGH and s > SLOPE_THRESHOLD:
        return "very_high"
    elif (pd.notna(d) and d < BUFFER_HIGH) or (pd.notna(s) and s > SLOPE_THRESHOLD):
        return "high"
    elif pd.notna(d) and pd.notna(e) and d < 1000 and e < ELEVATION_LOW:
        return "medium"
    else:
        return "low"

shelters["risk_level"] = shelters.apply(classify_risk, axis=1)
risk_counts = shelters["risk_level"].value_counts()
print(f"Risk classification: {dict(risk_counts)}")

# Visualization
print("Creating risk map...")
# Hillshade calculation
azimuth = np.radians(315)
altitude = np.radians(45)
grad_y, grad_x = np.gradient(dem_arr, pixel_size)
slope_rad = np.arctan(np.sqrt(grad_x**2 + grad_y**2))
aspect_rad = np.arctan2(-grad_x, grad_y)
hillshade = (
    np.sin(altitude) * np.cos(slope_rad) +
    np.cos(altitude) * np.sin(slope_rad) * np.cos(azimuth - aspect_rad)
)
hillshade = np.clip(hillshade, 0, 1)

# Create risk map
xmin, ymin, xmax, ymax = dem_clip.rio.bounds()
risk_colors = {"very_high": "red", "high": "orange", "medium": "gold", "low": "green"}

fig, ax = plt.subplots(figsize=(10, 12))
ax.imshow(hillshade, cmap="gray", extent=(xmin, xmax, ymin, ymax), origin="upper")
county_boundary.boundary.plot(ax=ax, color="black", linewidth=1)

for level, color in risk_colors.items():
    subset = shelters[shelters["risk_level"] == level]
    if len(subset) > 0:
        subset.plot(ax=ax, color=color, markersize=12, label=level, alpha=0.9)

ax.set_title(f"{TARGET_COUNTY} DEM Hillshade + Shelter Terrain Risk")
ax.legend(title="risk_level")
ax.set_xlabel("X (m)")
ax.set_ylabel("Y (m)")
plt.tight_layout()
plt.savefig("terrain_risk_map.png", dpi=300, bbox_inches="tight")
plt.show()
print("✅ terrain_risk_map.png saved")

# Save deliverables
print("Saving deliverables...")
shelters_final = shelters.copy().reset_index(drop=True)
shelters_final.insert(0, "shelter_id", shelters_final.index + 1)

# JSON audit table
audit_df = shelters_final[[
    "shelter_id",
    "避難收容處所名稱",
    "risk_level",
    "mean_elevation",
    "max_slope",
    "river_distance_category",
]].rename(columns={"避難收容處所名稱": "name"})

audit_df.to_json(
    "terrain_risk_audit.json",
    orient="records",
    force_ascii=False,
    indent=2,
)
print("✅ terrain_risk_audit.json saved")

# GeoJSON
export_gdf = shelters_final.rename(columns={
    "避難收容處所名稱": "name",
    "mean_elevation": "mean_elev",
    "std_elevation": "std_elev",
    "max_slope": "max_slope",
    "river_distance_m": "riv_dist_m",
    "river_distance_category": "riv_dist_c",
    "risk_level": "risk_lvl",
})[[
    "shelter_id",
    "name",
    "mean_elev",
    "std_elev",
    "max_slope",
    "riv_dist_m",
    "riv_dist_c",
    "risk_lvl",
    "geometry",
]].copy()

export_gdf.to_file("terrain_risk.geojson", driver="GeoJSON")
print("✅ terrain_risk.geojson saved")

print("\n🎉 Analysis completed successfully!")
print(f"Summary: {len(shelters)} shelters analyzed")
print(f"Risk distribution: {dict(risk_counts)}")
print("\nOutput files:")
print("- terrain_risk_audit.json")
print("- terrain_risk.geojson") 
print("- terrain_risk_map.png")
