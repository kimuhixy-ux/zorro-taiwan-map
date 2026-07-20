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
    番地・階数を除いた通り名レベルで再検索する（精度は落ちるがおおよその位置は取得できる）。
    戻り値: (lat, lng, precision) の3要素タプル、または None
    precision は "exact"（番地まで一致）または "approximate"（通り名レベル）
    """
    result = query_nominatim(address)
    if result:
        return result[0], result[1], "exact"

    fallback = strip_house_number(address)
    if fallback:
        time.sleep(REQUEST_INTERVAL_SEC)
        result = query_nominatim(fallback)
        if result:
            return result[0], result[1], "approximate"

    return None


def main():
    stores = load_json(STORES_PATH, [])
    if not stores:
        sys.exit(
            f"エラー: {STORES_PATH} が見つからないか空です。先に extract_stores.py を実行してください。"
        )

    imported = import_manual_check(stores)
    if imported:
        print(f"manual_check.csv から {imported}件の緯度経度を取り込みました。")

    to_geocode = [s for s in stores if "lat" not in s or "lng" not in s]
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
