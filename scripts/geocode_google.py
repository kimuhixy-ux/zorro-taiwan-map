"""
geocode_google.py
Nominatim（OpenStreetMap）で解決できなかった店舗を、Google Geocoding API /
Places API (New) で再挑戦する。

- 住所がある店舗: Geocoding API（住所文字列 -> 緯度経度）
- 住所がない店舗: Places API (New) の Text Search（店名 -> 緯度経度）
- 対象は stores.json の needs_manual_check: true の店舗のみ
- .env の GOOGLE_MAPS_API_KEY を使用する

実行方法:
    python3 scripts/geocode_google.py
"""

import json
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
STORES_PATH = DATA_DIR / "stores.json"
MANUAL_CHECK_PATH = DATA_DIR / "manual_check.csv"

load_dotenv(BASE_DIR / ".env")
API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY")

GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
PLACES_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
REQUEST_INTERVAL_SEC = 0.15

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


def geocode_by_address(address: str):
    resp = requests.get(
        GEOCODE_URL,
        params={"address": address, "region": "tw", "key": API_KEY},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") != "OK" or not data.get("results"):
        return None
    loc = data["results"][0]["geometry"]["location"]
    return loc["lat"], loc["lng"]


def geocode_by_name(name: str):
    resp = requests.post(
        PLACES_SEARCH_URL,
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": API_KEY,
            "X-Goog-FieldMask": "places.location,places.formattedAddress,places.displayName",
        },
        json={"textQuery": f"{name} 台湾", "languageCode": "zh-TW"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    places = data.get("places") or []
    if not places:
        return None
    loc = places[0]["location"]
    return loc["latitude"], loc["longitude"]


def main():
    if not API_KEY:
        raise SystemExit("エラー: .env に GOOGLE_MAPS_API_KEY が設定されていません。")

    stores = load_json(STORES_PATH, [])
    if not stores:
        raise SystemExit(f"エラー: {STORES_PATH} が見つからないか空です。")

    targets = [s for s in stores if s.get("needs_manual_check")]
    print(f"Google APIで再挑戦する店舗: {len(targets)}件 / 全{len(stores)}件")

    resolved_address = 0
    resolved_name = 0
    still_failed = 0

    for i, store in enumerate(targets, start=1):
        address = store.get("address")
        name = store.get("name")
        result = None
        method = None

        if address:
            print(f"[{i}/{len(targets)}] {name} ({address}) を住所で検索中...")
            try:
                result = geocode_by_address(address)
                method = "google-address"
            except Exception as e:
                print(f"  エラー: {e}")
        else:
            print(f"[{i}/{len(targets)}] {name} を店名で検索中...")
            try:
                result = geocode_by_name(name)
                method = "google-name"
            except Exception as e:
                print(f"  エラー: {e}")

        if result:
            store["lat"], store["lng"] = result
            store["geocode_precision"] = method
            store["needs_manual_check"] = False
            if method == "google-address":
                resolved_address += 1
            else:
                resolved_name += 1
            print("  見つかりました")
        else:
            print("  見つかりませんでした -> 手動確認へ")
            still_failed += 1

        time.sleep(REQUEST_INTERVAL_SEC)

    save_json(STORES_PATH, stores)
    print(f"保存しました: {STORES_PATH}")
    print(
        f"結果: 住所検索で{resolved_address}件, 店名検索で{resolved_name}件解決 / "
        f"未解決{still_failed}件"
    )

    manual_rows = [s for s in stores if s.get("needs_manual_check")]
    with open(MANUAL_CHECK_PATH, "w", encoding="utf-8", newline="") as f:
        import csv

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


if __name__ == "__main__":
    main()
