"""
fetch_videos.py
YouTubeチャンネル「@zorro_taiwangourmet」の全動画のメタデータを取得し、
data/videos_raw.json に保存する。

実行方法:
    python3 scripts/fetch_videos.py

再実行時は、既に videos_raw.json に入っている動画IDをスキップし、
新規動画分だけを追加取得する（差分更新）。
"""

import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_PATH = DATA_DIR / "videos_raw.json"

CHANNEL_HANDLE = "zorro_taiwangourmet"
API_BASE = "https://www.googleapis.com/youtube/v3"


def get_api_key() -> str:
    load_dotenv(BASE_DIR / ".env")
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        sys.exit(
            "エラー: 環境変数 YOUTUBE_API_KEY が設定されていません。\n"
            "プロジェクト直下に .env ファイルを作成し、\n"
            "YOUTUBE_API_KEY=あなたのAPIキー\n"
            "の形式で記入してください（.env.example を参照）。"
        )
    return api_key


def resolve_uploads_playlist_id(api_key: str) -> str:
    resp = requests.get(
        f"{API_BASE}/channels",
        params={
            "part": "contentDetails",
            "forHandle": CHANNEL_HANDLE,
            "key": api_key,
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    items = data.get("items", [])
    if not items:
        sys.exit(f"エラー: ハンドル @{CHANNEL_HANDLE} のチャンネルが見つかりませんでした。")
    return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]


def fetch_all_playlist_items(api_key: str, playlist_id: str):
    videos = []
    page_token = None
    while True:
        params = {
            "part": "snippet",
            "playlistId": playlist_id,
            "maxResults": 50,
            "key": api_key,
        }
        if page_token:
            params["pageToken"] = page_token

        resp = requests.get(f"{API_BASE}/playlistItems", params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        for item in data.get("items", []):
            snippet = item["snippet"]
            video_id = snippet["resourceId"]["videoId"]
            videos.append(
                {
                    "video_id": video_id,
                    "title": snippet.get("title", ""),
                    "description": snippet.get("description", ""),
                    "published_at": snippet.get("publishedAt", ""),
                    "video_url": f"https://www.youtube.com/watch?v={video_id}",
                }
            )

        page_token = data.get("nextPageToken")
        if not page_token:
            break

    return videos


def load_existing(path: Path):
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    api_key = get_api_key()
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    existing = load_existing(OUTPUT_PATH)
    existing_ids = {v["video_id"] for v in existing}
    print(f"既存の動画: {len(existing)}件")

    playlist_id = resolve_uploads_playlist_id(api_key)
    print(f"アップロード再生リストID: {playlist_id}")

    all_videos = fetch_all_playlist_items(api_key, playlist_id)
    print(f"チャンネル上の全動画: {len(all_videos)}件")

    new_videos = [v for v in all_videos if v["video_id"] not in existing_ids]
    print(f"新規取得: {len(new_videos)}件")

    combined = existing + new_videos
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(combined, f, ensure_ascii=False, indent=2)

    print(f"保存しました: {OUTPUT_PATH}（合計 {len(combined)}件）")


if __name__ == "__main__":
    main()
