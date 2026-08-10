"""
fetch_mrt.py
台湾全土のMRT路線（台北・新北・桃園・台中・高雄）を OpenStreetMap の
Overpass API から取得し、data/mrt_lines.json に保存する。

- route=subway のリレーションを台湾のバウンディングボックスで検索
- 同じ物理路線が「順向」「逆向」など往復方向ごとに別リレインとして
  登録されていることが多いため、(ref, 色, 事業者) が同じものは
  最初の1件だけを採用して重複描画を避ける
- 駅（role=stop 等のノード）は路線をまたいで名前+座標で重複排除する

実行方法:
    python3 scripts/fetch_mrt.py
"""

import json
import re
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_PATH = BASE_DIR / "data" / "mrt_lines.json"

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "zorro-taiwan-map/1.0 (personal fan-made project; contact: kimuhixy@gmail.com)"
# 台湾本島＋澎湖を含むバウンディングボックス
TAIWAN_BBOX = "21.8,119.3,25.6,122.1"

QUERY = f"""
[out:json][timeout:180];
(
  relation["route"="subway"]({TAIWAN_BBOX});
);
(._;>;);
out geom;
"""

STOP_ROLES = {"stop", "stop_entry_only", "stop_exit_only", "platform"}

# Overpassのタグにcolourが無い路線用のフォールバック色（台中MRT緑線）
FALLBACK_COLORS = {
    "臺中捷運公司": "#00a650",
}

# OSMのリレーション名には「A => B」のような方向表記や、路線名と無関係な
# 区間表記（例:「哈瑪星-大寮」）が混ざっていて分かりにくいため、
# (ref, colour) の組み合わせごとに表示用の路線名を上書きする。
# ※ refとcolourが台北/高雄の"R"（赤線）で重複するため、そこだけは
#   元の名前に「高雄」が含まれるかで判定する（下のdisplay_name算出部を参照）。
NAME_OVERRIDES = {
    ("BL", "#007ec7"): "板南線",
    ("BR", "#A74C00"): "文湖線",
    ("G", "#1e7b54"): "松山新店線",
    ("A", "#d4cde7"): "桃園機場捷運",
    ("Y", "#ffd900"): "環狀線",
    ("O", "orange"): "中和新蘆線",
    ("G", "#CEDC00"): "小碧潭支線",
    ("LB", "#6DB7D0"): "三鶯線",
    ("O", "#FFA500"): "高雄捷運橘線",
    ("1", "#00a650"): "台中捷運綠線",
}


def fetch():
    resp = requests.post(
        OVERPASS_URL,
        data={"data": QUERY},
        headers={"User-Agent": USER_AGENT},
        timeout=200,
    )
    resp.raise_for_status()
    return resp.json()["elements"]


def main():
    elements = fetch()

    ways = {}
    nodes = {}
    relations = []
    for el in elements:
        if el["type"] == "way" and "geometry" in el:
            ways[el["id"]] = [[pt["lat"], pt["lon"]] for pt in el["geometry"]]
        elif el["type"] == "node":
            nodes[el["id"]] = {
                "lat": el["lat"],
                "lng": el["lon"],
                "name": (el.get("tags") or {}).get("name"),
            }
        elif el["type"] == "relation":
            relations.append(el)

    seen_keys = set()
    lines = []
    station_map = {}  # (name, rounded_lat, rounded_lng) -> station dict

    for rel in relations:
        tags = rel.get("tags") or {}
        name = tags.get("name") or tags.get("ref") or f"relation/{rel['id']}"
        ref = tags.get("ref") or name
        operator = tags.get("operator") or "unknown"
        color = tags.get("colour") or FALLBACK_COLORS.get(operator) or "#888888"

        key = (ref, color, operator)
        if key in seen_keys:
            continue
        seen_keys.add(key)

        segments = []
        line_stations = []
        for member in rel.get("members", []):
            if member["type"] == "way" and member["ref"] in ways:
                segments.append(ways[member["ref"]])
            elif member["type"] == "node" and member.get("role") in STOP_ROLES:
                node = nodes.get(member["ref"])
                if node and node["name"]:
                    line_stations.append(node)

        if not segments:
            continue

        name_key = (ref, color)
        if name_key in NAME_OVERRIDES:
            display_name = NAME_OVERRIDES[name_key]
        elif "新北投" in name:
            display_name = "淡水信義線（新北投支線）"
        elif ref == "R" and color == "#FF0000":
            display_name = "高雄捷運紅線" if "高雄" in name else "淡水信義線"
        else:
            # 上書き定義が無い路線は「A => B」方向表記や括弧書きの補足を取り除くだけの
            # 簡易整形にとどめる（次回Overpass取得時に路線構成が変わっても壊れないように）
            display_name = re.split(r"=>|\(|（", name)[0].strip()

        lines.append(
            {
                "name": display_name,
                "ref": ref,
                "color": color,
                "segments": segments,
            }
        )

        for st in line_stations:
            sk = (st["name"], round(st["lat"], 4), round(st["lng"], 4))
            if sk not in station_map:
                station_map[sk] = {
                    "name": st["name"],
                    "lat": st["lat"],
                    "lng": st["lng"],
                    "lines": [display_name],
                }
            elif display_name not in station_map[sk]["lines"]:
                station_map[sk]["lines"].append(display_name)

    output = {
        "lines": lines,
        "stations": list(station_map.values()),
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"路線: {len(lines)}件, 駅: {len(station_map)}件 -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
