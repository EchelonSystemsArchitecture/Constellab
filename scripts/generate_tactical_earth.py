import json, os, time, urllib.request
from PIL import Image, ImageDraw, ImageFilter
import numpy as np

W, H = 4096, 2048
t0 = time.time()

CACHE_DIR = os.path.join(os.path.dirname(__file__), ".geo_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

world_path = os.path.join(CACHE_DIR, "world_countries.geojson")
if not os.path.exists(world_path):
    print("Downloading world countries GeoJSON...")
    url = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_110m_admin_0_countries.geojson"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        with open(world_path, "wb") as f:
            f.write(r.read())

india_path = os.path.join(CACHE_DIR, "india_soi.geojson")
if not os.path.exists(india_path):
    print("Downloading Survey of India official boundary GeoJSON...")
    url = "https://raw.githubusercontent.com/datameet/maps/master/Country/india-soi.geojson"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        with open(india_path, "wb") as f:
            f.write(r.read())

print("Loading geo datasets...")
with open(world_path, "r", encoding="utf-8") as f:
    world_data = json.load(f)

with open(india_path, "r", encoding="utf-8") as f:
    india_data = json.load(f)

# Brand Color Discipline: Void #080B14, Orbit Navy, Anomaly Coral
ocean_col = (8, 11, 20, 255)         # Void #080B14
land_col = (46, 64, 90, 255)         # Tactical Slate #2E405A (unified for all land)

grat_major = (27, 43, 74, 180)       # Orbit Navy major lines
grat_minor = (18, 28, 48, 110)       # Deep Navy minor lines
grat_equator = (38, 58, 98, 200)

border_coral_core = (255, 130, 110, 255) # Anomaly Coral #FF765F core

img = Image.new("RGBA", (W, H), ocean_col)
draw = ImageDraw.Draw(img)

# Graticules
for lon in range(-180, 181, 15):
    x = int((lon + 180) / 360 * W)
    col = grat_major if lon % 30 == 0 else grat_minor
    draw.line([(x, 0), (x, H)], fill=col, width=1)

for lat in range(-90, 91, 15):
    y = int((90 - lat) / 180 * H)
    col = grat_equator if lat == 0 else (grat_major if lat % 30 == 0 else grat_minor)
    draw.line([(0, y), (W, y)], fill=col, width=1)

def to_pts(coords):
    pts = []
    for pt in coords:
        x = (pt[0] + 180) / 360 * W
        y = (90 - pt[1]) / 180 * H
        pts.append((x, y))
    return pts

def simplify_pts(pts, tol_sq=0.25):
    if len(pts) <= 4:
        return pts
    res = [pts[0]]
    for p in pts[1:]:
        dx = p[0] - res[-1][0]
        dy = p[1] - res[-1][1]
        if dx * dx + dy * dy >= tol_sq:
            res.append(p)
    if res[-1] != pts[-1]:
        res.append(pts[-1])
    return res

# 1. Fill world countries (excluding Natural Earth IND)
print("Filling world landmasses...")
for feat in world_data["features"]:
    if feat["properties"].get("ADM0_A3") == "IND":
        continue
    geom = feat["geometry"]
    polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
    for poly in polys:
        ext = to_pts(poly[0])
        if len(ext) > 2:
            draw.polygon(ext, fill=land_col)

# 2. Fill official India with the EXACT SAME unified land_col
print("Filling official Survey of India geometry...")
india_polys = india_data["features"][0]["geometry"]["coordinates"]
india_pts_list = []
for poly in india_polys:
    ext = to_pts(poly[0])
    if len(ext) > 2:
        simp = simplify_pts(ext, 0.3)
        if len(simp) > 2:
            draw.polygon(simp, fill=land_col)
            india_pts_list.append(simp)

# 3. Create India interior mask to erase foreign ceasefire/disputed lines
india_mask = Image.new("L", (W, H), 0)
im_draw = ImageDraw.Draw(india_mask)
for pts in india_pts_list:
    if len(pts) > 2:
        im_draw.polygon(pts, fill=255)

# Erode mask slightly (2 pixels) so external borders remain crisp
india_interior = india_mask.filter(ImageFilter.MinFilter(3))

# 4. Draw world borders onto border layer
print("Drawing borders with uniform styling...")
border_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
bdraw = ImageDraw.Draw(border_layer)

for feat in world_data["features"]:
    if feat["properties"].get("ADM0_A3") == "IND":
        continue
    geom = feat["geometry"]
    polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
    for poly in polys:
        ext = to_pts(poly[0])
        if len(ext) > 2:
            bdraw.line(ext, fill=border_coral_core, width=1)

# Mask out any foreign border lines inside India
b_arr = np.array(border_layer)
m_arr = np.array(india_interior) > 128
b_arr[m_arr] = [0, 0, 0, 0]
border_layer = Image.fromarray(b_arr)
bdraw = ImageDraw.Draw(border_layer)

# 5. Draw official India borders with EXACT SAME width=1 (no extra thickness or glow!)
for pts in india_pts_list:
    if len(pts) > 2:
        bdraw.line(pts, fill=border_coral_core, width=1)

# 6. Apply subtle, uniform glow across ALL borders identically
glow_layer = border_layer.filter(ImageFilter.GaussianBlur(radius=1.5))
img.paste(glow_layer, (0, 0), glow_layer)
img.paste(border_layer, (0, 0), border_layer)

# Save to public and dist
out_pub = os.path.join(os.path.dirname(__file__), "..", "frontend", "public", "earth-tactical-dark.png")
out_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist", "earth-tactical-dark.png")

img.save(out_pub, optimize=True)
if os.path.exists(os.path.dirname(out_dist)):
    img.save(out_dist, optimize=True)

print(f"Generated uniform tactical Earth texture in {time.time()-t0:.2f}s!")
