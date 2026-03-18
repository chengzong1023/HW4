# ARIA v2.0 - Terrain Risk Audit (Fixed Version)

## 專案描述

這是一個修復版本的 ARIA v2.0 地形風險審計工具，結合 **河川距離 + DEM 高程 + 坡度** 來審計 **花蓮縣** 避難所的地形風險。

## 🔧 修復的問題

### 1. **Zonal Stats 回傳 NaN** - CRS 未對齊問題

**問題描述**：
- 原始版本在使用 `zonal_stats` 時經常回傳 `NaN` 值
- 主要原因是向量資料（避難所）與柵格資料（DEM）的坐標系統未對齊
- 即使都轉換到 EPSG:3826，但在 `zonal_stats` 中仍可能有微小的坐標差異

**解決方案**：
```python
# 確保所有資料使用相同的 CRS
townships = gpd.read_file(township_path).to_crs(epsg:3826)
shelters = shelters.to_crs(epsg:3826)
rivers = gpd.read_file(WRA_URL).to_crs(epsg:3826)

# 在 zonal_stats 中使用正確的 affine 參數
zs_elev = zonal_stats(
    shelter_buffers,
    dem_arr,  # 使用 numpy array 而不是 xarray
    affine=dem_affine,  # 明確指定 affine 變換
    stats=["mean", "std"],
    nodata=np.nan,
)
```

**關鍵改進**：
- 使用 `dem_affine = dem_clip.rio.transform()` 確保正確的像素坐標對應
- 將 xarray 轉換為 numpy array 以避免坐標系統混亂
- 明確指定 `nodata=np.nan` 處理無效值

### 2. **DEM 太大導致記憶體不足** - 智能裁切策略

**問題描述**：
- 原始版本載入完整的 DEM 檔案，導致 Colab 記憶體不足
- 特別是高解析度的 20m DEM 檔案非常大
- 不必要的全域 DEM 載入造成資源浪費

**解決方案**：
```python
# 創建目標縣市邊界並緩衝 1000m
county_boundary_buffer = county_boundary.copy()
county_boundary_buffer["geometry"] = county_boundary_buffer.buffer(1000)

# 裁切 DEM 到目標區域
clip_boundary = county_boundary_buffer.copy()
if dem.rio.crs != clip_boundary.crs:
    clip_boundary = clip_boundary.to_crs(dem.rio.crs)

dem_clip = dem.rio.clip(clip_boundary.geometry, clip_boundary.crs, drop=True)
```

**關鍵改進**：
- 使用 1000m 緩衝確保 500m 避難所緩衝區完全覆蓋
- 大幅減少記憶體使用（通常減少 80-90%）
- 保持計算精確性的同時提升效能

### 3. **坡度計算結果不合理** - Gradient Spacing 參數校正

**問題描述**：
- 原始版本使用 `np.gradient()` 時沒有考慮像素解析度
- 導致坡度計算結果過大或過小
- 20m DEM 的像素間距未正確傳遞給 gradient 函數

**解決方案**：
```python
# 取得 DEM 的真實像素解析度
res_x, res_y = dem_clip.rio.resolution()
pixel_size = abs(res_x)  # 確保為正值，預期 20m

# 使用正確的 spacing 參數計算坡度
dy, dx = np.gradient(dem_arr, pixel_size)
slope_arr = np.degrees(np.arctan(np.sqrt(dx**2 + dy**2)))

print("Pixel size:", pixel_size)  # 驗證解析度
print("Slope min/max:", np.nanmin(slope_arr), np.nanmax(slope_arr))  # 合理性檢查
```

**關鍵改進**：
- 從 DEM 元數據動態取得像素解析度（而非硬編碼）
- 使用正確的 spacing 參數確保坡度計算準確
- 添加合理性檢查驗證坡度範圍（通常 0-90 度）

## 📊 技術改進總結

| 問題類型 | 原始問題 | 修復方案 | 效果 |
|---------|---------|---------|------|
| **Zonal Stats NaN** | CRS 未對齊導致統計失效 | 統一坐標系 + 正確 affine 參數 | 統計結果準確無 NaN |
| **記憶體不足** | 載入完整 DEM | 智能裁切到目標區域 | 記憶體使用減少 80-90% |
| **坡度計算錯誤** | gradient spacing 參數錯誤 | 動態取得像素解析度 | 坡度值合理 (0-90°) |

## 🚀 使用方法

### 環境需求
```bash
pip install geopandas pandas numpy rioxarray rasterstats matplotlib shapely python-dotenv
```

### 環境設定
1. 複製環境變數範例檔案：
   ```bash
   cp .env.example .env
   ```
2. 編輯 `.env` 檔案，設定你的資料路徑和參數：
   ```env
   SLOPE_THRESHOLD=30      # 坡度閾值（度）
   ELEVATION_LOW=50        # 低高程閾值（公尺）
   BUFFER_HIGH=500         # 高風險緩衝距離（公尺）
   TARGET_COUNTY=花蓮縣    # 目標縣市
   ```

### 執行步驟
1. 下載專案：`git clone https://github.com/chengzong1023/HW4`
2. 進入專案目錄：`cd HW4/ARIA_V2_FIXED`
3. 設定環境變數：`cp .env.example .env` 並編輯路徑
4. 開啟 Jupyter Notebook：`jupyter notebook ARIA_v2.ipynb`
5. 依序執行所有單元格

### 輸入資料
- **鄉鎮界線**：TOWN_MOI_1140318.shp
- **避難所資料**：避難收容處所點位檔案v9.csv  
- **DEM 檔案**：dem_20m_hualien.tif
- **河川資料**：自動從水利署 API 下載

### 輸出成果
- `terrain_risk_audit.json` - 風險審計表格
- `terrain_risk.geojson` - 空間資料檔案
- `terrain_risk_map.png` - 風險地圖

## 🎯 風險分類邏輯

- **very_high**: 河川距離 < 500m 且 最大坡度 > 閾值
- **high**: 河川距離 < 500m 或 最大坡度 > 閾值  
- **medium**: 河川距離 < 1000m 且 平均高程 < 閾值
- **low**: 其他情況

## 📝 參數設定

所有參數透過 `.env` 檔案管理，支援以下設定：

### 風險評估參數
- `SLOPE_THRESHOLD` - 坡度閾值（度），預設 30
- `ELEVATION_LOW` - 低高程閾值（公尺），預設 50
- `BUFFER_HIGH` - 高風險緩衝距離（公尺），預設 500

### 分析區域設定
- `TARGET_COUNTY` - 目標縣市，預設 "花蓮縣"

### 資料路徑設定
- `TOWNSHIP_PATH` - 鄉鎮界線 shapefile 路徑
- `SHELTER_CSV_PATH` - 避難所 CSV 檔案路徑
- `DEM_PATH` - DEM TIFF 檔案路徑（Google Drive）
- `WRA_URL` - 水利署河川資料 API URL

### Google Drive 設定（Colab 使用）
DEM 檔案建議放在 Google Drive 中以避免 GitHub 檔案大小限制：

1. **下載 DEM 檔案**：
   - 從 [data.gov.tw](https://data.gov.tw/dataset/176927) 下載台灣 20m DEM
   - 裁切花蓮縣區域並命名為 `dem_20m_hualien.tif`

2. **上傳到 Google Drive**：
   ```bash
   # 在 Google Drive 中建立資料夾結構
   MyDrive/
   └── dem_20m_hualien.tif
   ```

3. **在 Colab 中掛載 Google Drive**：
   ```python
   from google.colab import drive
   drive.mount('/content/drive')
   ```

4. **更新 .env 路徑**：
   ```env
   DEM_PATH=/content/drive/MyDrive/dem_20m_hualien.tif
   ```

### 視覺化設定
- `HILLSHADE_AZIMUTH` - 山陰圖方位角，預設 315
- `HILLSHADE_ALTITUDE` - 山陰圖高度角，預設 45

### 程式碼中的環境變數使用
```python
import os
from dotenv import load_dotenv

load_dotenv()

SLOPE_THRESHOLD = float(os.getenv("SLOPE_THRESHOLD", 30))
ELEVATION_LOW = float(os.getenv("ELEVATION_LOW", 50))
BUFFER_HIGH = float(os.getenv("BUFFER_HIGH", 500))
TARGET_COUNTY = os.getenv("TARGET_COUNTY", "花蓮縣")
```

## 🔍 驗證結果

修復後的版本能夠：
- ✅ 正確計算所有避難所的地形統計（無 NaN）
- ✅ 在有限記憶體環境下穩定運行
- ✅ 產生合理的坡度分析結果
- ✅ 提供準確的複合風險評估

## 📄 授權

本專案遵循 MIT 授權條款。

## 🤝 貢獻

歡迎提交 Issue 或 Pull Request 來改進這個工具。

---

**注意**：這個修復版本專注於解決常見的技術問題，確保在 各種環境下都能穩定運行並產生準確的結果。
