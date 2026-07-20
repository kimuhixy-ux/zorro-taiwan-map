"""
geocode.py
data/stores.json の各店舗の住所を Nominatim（OpenStreetMap）でジオコーディングし、
lat / lng を追記する。

- Nominatim利用規約を遵守: リクエスト間隔1秒以上、User-Agentを明示
- 既に lat/lng がある店舗は再実行時にスキップ
- ジオコーディングに失敗した店舗・住所がない店舗は needs_manual_check: true とし、
  data/manual_check.csv に書き出す（店名・動画URL・住所・lat・lng の空欄付き）
- data/manual_check.csv に手動で lat/lng を記入して再実行すると、
  その内容が stores.json に取り込まれる（往復編集の仕組み）

実行方法:
    python3 scripts/geocode.py
"""

import csv
import json
import re
import sys
import time
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
STORES_PATH = DATA_DIR / "stores.json"
MANUAL_CHECK_PATH = DATA_DIR / "manual_check.csv"

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "zorro-taiwan-map/1.0 (personal fan-made project; contact: kimuhixy@gmail.com)"
REQUEST_INTERVAL_SEC = 1.1

CSV_FIELDS = ["name", "name_ja", "address", "video_url", "lat", "lng"]


def load_json(path: Path, default):
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def first_video_url(store: dict) -> str:
    videos = store.get("videos") or []
    return videos[0]["video_url"] if videos else ""


def import_manual_check(stores: list):
    """manual_check.csv に手入力された lat/lng を stores.json に取り込む"""
    if not MANUAL_CHECK_PATH.exists():
        return 0

    imported = 0
    with open(MANUAL_CHECK_PATH, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            lat_str = (row.get("lat") or "").strip()
            lng_str = (row.get("lng") or "").strip()
            if not lat_str or not lng_str:
                continue
            try:
                lat, lng = float(lat_str), float(lng_str)
            except ValueError:
                print(f"  警告: 緯度経度が数値ではありません（店名: {row.get('name')}）。スキップします。")
                continue

            for store in stores:
                if store.get("name") == row.get("name") and first_video_url(store) == row.get("video_url"):
                    store["lat"] = lat
                    store["lng"] = lng
                    store["needs_manual_check"] = False
                    imported += 1
                    break

    return imported


# 台湾はNominatimの建物番地(●●號)レベルのデータが手薄なため、
# 番地・階数を含めた完全住所で失敗した場合は、通り名レベルまで削って再検索する
HOUSE_NUMBER_SUFFIX = re.compile(r"[0-9０-９\-之]+\s*號.*$")


def strip_house_number(address: str):
    stripped = HOUSE_NUMBER_SUFFIX.sub("", address).strip()
    if stripped and stripped != address:
        return stripped
    return None


# Nominatimは「市」「區」「道路」が区切りなしで連結された中国語住所
# （例: 臺北市大同區延平北路四段）をうまく解釈できないことが多い。
# 「道路, 區, 市」のようにカンマ区切りへ整形すると通り名レベルでの
# ヒット率が大きく改善する。英語住所も「Street, City」の形に絞ると同様に改善する。

CITY_NAMES_ZH = [
    "臺北市", "台北市", "新北市", "桃園市", "臺中市", "台中市", "臺南市", "台南市",
    "高雄市", "基隆市", "新竹市", "新竹縣", "苗栗縣", "彰化縣", "南投縣", "雲林縣",
    "嘉義市", "嘉義縣", "屏東縣", "宜蘭縣", "花蓮縣", "臺東縣", "台東縣",
    "澎湖縣", "金門縣", "連江縣",
]
CITY_RE_ZH = re.compile("^(" + "|".join(CITY_NAMES_ZH) + ")")
DISTRICT_RE_ZH = re.compile(r"^(\S+?[區市鄉鎮])")
ROAD_RE_ZH = re.compile(r"(.+?(?:路|街|大道)(?:[一二三四五六七八九十]+段)?)")

CITY_NAMES_EN = [
    "Taipei City", "New Taipei City", "Taoyuan City", "Taichung City", "Tainan City",
    "Kaohsiung City", "Keelung City", "Hsinchu City", "Hsinchu County", "Miaoli County",
    "Changhua County", "Nantou County", "Yunlin County", "Chiayi City", "Chiayi County",
    "Pingtung County", "Yilan County", "Hualien County", "Taitung County",
    "Penghu County", "Kinmen County", "Lienchiang County",
]
ROAD_KEYWORDS_EN = re.compile(
    r"\b(Street|St|Road|Rd|Avenue|Ave|Lane|Ln|Boulevard|Blvd|Alley)\b", re.IGNORECASE
)
SECTION_RE_EN = re.compile(r"^Section\s*\d+$", re.IGNORECASE)
POSTAL_RE = re.compile(r"^\d{3,6}$")


def reformatted_query_candidates(address: str):
    """住所を「道路, 區, 市」/「Street, City」の形に整形したクエリ候補を返す。
    精度の高い順（區まで含む→道路+市のみ）にリストで返す。"""
    address = re.sub(r"^\d{3,6}\s*", "", address.strip())
    city_match = CITY_RE_ZH.match(address)

    # 「No. 20號, Jinxi Street, ...」のように英語主体でも「號」等の漢字が
    # 混ざることがあるため、判定は「先頭が中国語の市名で始まるか」で行う
    if city_match:
        city = city_match.group(1)
        rest = address[city_match.end():]

        district_match = DISTRICT_RE_ZH.match(rest)
        district = district_match.group(1) if district_match else None
        rest_after_district = rest[district_match.end():] if district_match else rest

        road_match = ROAD_RE_ZH.search(rest_after_district)
        if not road_match:
            return []
        road = road_match.group(1)

        candidates = []
        if district:
            candidates.append(f"{road}, {district}, {city}")
        candidates.append(f"{road}, {city}")
        return candidates

    # 英語住所: カンマ区切りされている前提でセグメントを分類する
    segments = [s.strip() for s in address.split(",") if s.strip()]
    city = None
    road_parts = []
    for seg in segments:
        if POSTAL_RE.match(seg):
            continue
        if seg in CITY_NAMES_EN:
            city = seg
            continue
        if seg.endswith("District") or seg.endswith("Township"):
            continue
        if SECTION_RE_EN.match(seg):
            road_parts.append(seg)
            continue
        if ROAD_KEYWORDS_EN.search(seg):
            road_parts.append(seg)

    if not city or not road_parts:
        return []

    road = " ".join(road_parts)
    return [f"{road}, {city}"]


def query_nominatim(query: str):
    resp = requests.get(
        NOMINATIM_URL,
        params={"q": query, "format": "json", "limit": 1, "countrycodes": "tw"},
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    resp.raise_for_status()
    results = resp.json()
    if not results:
        return None
    return float(results[0]["lat"]), float(results[0]["lon"])


def geocode_address(address: str):
    """住所をジオコーディングする。完全住所で見つからない場合は、
    「道路, 區, 市」形式に整形し直して再検索する（精度は落ちるがおおよその位置は取得できる）。
    戻り値: (lat, lng, precision) の3要素タプル、または None
    precision は "exact"（番地まで一致）または "approximate"（通り名レベル）
    """
    result = query_nominatim(address)
    if result:
        return result[0], result[1], "exact"

    fallback_queries = reformatted_query_candidates(address)
    simple_fallback = strip_house_number(address)
    if simple_fallback and simple_fallback not in fallback_queries:
        fallback_queries.append(simple_fallback)

    for query in fallback_queries:
        time.sleep(REQUEST_INTERVAL_SEC)
        result = query_nominatim(query)
        if result:
            return result[0], result[1], "approximate"

    return None


def main():
    stars_filter = None
    for arg in sys.argv[1:]:
        if arg.startswith("--stars="):
            stars_filter = int(arg.split("=", 1)[1])

    stores = load_json(STORES_PATH, [])
    if not stores:
        sys.exit(
            f"エラー: {STORES_PATH} が見つからないか空です。先に extract_stores.py を実行してください。"
        )

    imported = import_manual_check(stores)
    if imported:
        print(f"manual_check.csv から {imported}件の緯度経度を取り込みました。")

    to_geocode = [s for s in stores if "lat" not in s or "lng" not in s]
    if stars_filter is not None:
        to_geocode = [s for s in to_geocode if s.get("stars") == stars_filter]
        print(f"（--stars={stars_filter} 指定により対象を絞り込み）")
    print(f"ジオコーディング対象: {len(to_geocode)}件 / 全{len(stores)}件")

    for i, store in enumerate(to_geocode, start=1):
        address = store.get("address")
        if not address:
            store["needs_manual_check"] = True
            print(f"[{i}/{len(to_geocode)}] {store.get('name')}: 住所なし -> 手動確認へ")
            continue

        print(f"[{i}/{len(to_geocode)}] {store.get('name')} ({address}) をジオコーディング中...")
        try:
            result = geocode_address(address)
        except Exception as e:
            print(f"  エラー: {e}")
            result = None

        if result:
            store["lat"], store["lng"], store["geocode_precision"] = result
            store["needs_manual_check"] = False
            if store["geocode_precision"] == "approximate":
                print("  番地が見つからず、通り名レベルの位置で登録しました")
        else:
            store["needs_manual_check"] = True
            print("  見つかりませんでした -> 手動確認へ")

        time.sleep(REQUEST_INTERVAL_SEC)

    save_json(STORES_PATH, stores)
    print(f"保存しました: {STORES_PATH}")

    manual_rows = [s for s in stores if s.get("needs_manual_check")]
    with open(MANUAL_CHECK_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for store in manual_rows:
            writer.writerow(
                {
                    "name": store.get("name", ""),
                    "name_ja": store.get("name_ja") or "",
                    "address": store.get("address") or "",
                    "video_url": first_video_url(store),
                    "lat": "",
                    "lng": "",
                }
            )

    print(f"手動確認が必要な店舗: {len(manual_rows)}件 -> {MANUAL_CHECK_PATH}")
    print("緯度経度を調べて lat / lng 列に記入後、再度このスクリプトを実行すると取り込まれます。")


if __name__ == "__main__":
    main()
