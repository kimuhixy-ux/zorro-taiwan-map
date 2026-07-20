"""
extract_stores.py
data/videos_raw.json の各動画（タイトル＋概要欄）を Anthropic API（Haiku系モデル）に渡し、
登場する飲食店の事実情報（店名・住所・星評価・ジャンル・営業時間）を抽出して
data/stores.json にまとめる。

- 概要欄のレビュー文・感想文は抽出・転載しない（事実情報のみ）
- 同一店舗（店名＋住所が一致）が複数動画に登場する場合は1店舗にまとめ、
  紐づく動画情報を videos 配列に追加する
- 既に処理済みの動画IDはスキップする（差分処理。API呼び出しを最小化）

実行方法:
    python3 scripts/extract_stores.py
"""

import json
import os
import sys
import time
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
VIDEOS_PATH = DATA_DIR / "videos_raw.json"
STORES_PATH = DATA_DIR / "stores.json"
PROCESSED_PATH = DATA_DIR / "processed_video_ids.json"

MODEL = "claude-haiku-4-5-20251001"

EXTRACT_TOOL = {
    "name": "record_stores",
    "description": "動画のタイトルと概要欄に登場する飲食店の事実情報を記録する。レビューや感想は含めない。",
    "input_schema": {
        "type": "object",
        "properties": {
            "stores": {
                "type": "array",
                "description": "動画に登場する飲食店のリスト。登場しない場合は空配列。",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "店名（概要欄の表記どおり。中国語表記）",
                        },
                        "name_ja": {
                            "type": ["string", "null"],
                            "description": "日本語での店名・読み。記載がなければ null",
                        },
                        "address": {
                            "type": ["string", "null"],
                            "description": "住所。概要欄に記載がなければ null（推測しない）",
                        },
                        "stars": {
                            "type": ["integer", "null"],
                            "enum": [1, 2, 3, None],
                            "description": "⭐の数（3=自信を持っておすすめ, 2=安くて美味しくて値打ちあり, 1=それ以外）。判定できなければ null（推測しない）",
                        },
                        "genre": {
                            "type": ["string", "null"],
                            "description": "ジャンル（例: 小籠包、牛肉麺、朝ごはん、夜市、スイーツ など）。判断できなければ null",
                        },
                        "hours": {
                            "type": ["string", "null"],
                            "description": "営業時間。記載がなければ null",
                        },
                    },
                    "required": ["name", "name_ja", "address", "stars", "genre", "hours"],
                },
            }
        },
        "required": ["stores"],
    },
}

SYSTEM_PROMPT = """あなたは台湾グルメYouTube動画のタイトルと概要欄から、紹介されている飲食店の事実情報だけを構造化抽出するアシスタントです。

厳守事項:
- 概要欄のレビュー文・感想文・おすすめコメントなどの文章は一切抽出・転記しないこと。抽出するのは店名・住所・星評価・ジャンル・営業時間などの事実情報のみ。
- 星評価(stars)は、タイトルや概要欄に明記された⭐の数（1〜3）からのみ判定すること。記載が曖昧・不明な場合は絶対に推測せず null にすること。
- 住所(address)は概要欄に記載がある場合のみ設定し、記載がなければ null にすること。推測しないこと。
- 1つの動画に複数の店舗が登場する場合は、すべて配列に含めること。
- 飲食店が登場しない動画（お知らせ動画など）の場合は空配列を返すこと。
"""


def get_client() -> Anthropic:
    load_dotenv(BASE_DIR / ".env")
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit(
            "エラー: 環境変数 ANTHROPIC_API_KEY が設定されていません。\n"
            ".env ファイルに ANTHROPIC_API_KEY=あなたのAPIキー を記入してください。"
        )
    return Anthropic(api_key=api_key)


def load_json(path: Path, default):
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def normalize(value):
    if value is None:
        return None
    return " ".join(value.split()).strip().lower()


def find_matching_store(stores, name, address):
    norm_name = normalize(name)
    norm_addr = normalize(address)
    for store in stores:
        if normalize(store.get("name")) != norm_name:
            continue
        existing_addr = normalize(store.get("address"))
        if norm_addr is not None and existing_addr is not None:
            if norm_addr == existing_addr:
                return store
        elif norm_addr is None and existing_addr is None:
            return store
        elif norm_addr is None or existing_addr is None:
            # 片方しか住所が分からない場合も、店名一致なら同一店舗とみなす
            return store
    return None


def extract_stores_from_video(client: Anthropic, video: dict):
    user_content = (
        f"タイトル: {video['title']}\n\n"
        f"概要欄:\n{video['description']}"
    )
    message = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        tools=[EXTRACT_TOOL],
        tool_choice={"type": "tool", "name": "record_stores"},
        messages=[{"role": "user", "content": user_content}],
    )
    for block in message.content:
        if block.type == "tool_use" and block.name == "record_stores":
            return block.input.get("stores", [])
    return []


def main():
    client = get_client()

    videos = load_json(VIDEOS_PATH, [])
    if not videos:
        sys.exit(
            f"エラー: {VIDEOS_PATH} が見つからないか空です。先に fetch_videos.py を実行してください。"
        )

    stores = load_json(STORES_PATH, [])
    processed_ids = set(load_json(PROCESSED_PATH, []))

    new_videos = [v for v in videos if v["video_id"] not in processed_ids]
    print(f"未処理の動画: {len(new_videos)}件 / 全{len(videos)}件")

    for i, video in enumerate(new_videos, start=1):
        print(f"[{i}/{len(new_videos)}] {video['title'][:40]} を処理中...")
        try:
            extracted = extract_stores_from_video(client, video)
        except Exception as e:
            print(f"  エラーが発生したためスキップします: {e}")
            continue

        video_entry = {
            "video_id": video["video_id"],
            "video_url": video["video_url"],
            "video_title": video["title"],
            "published_at": video["published_at"],
        }

        for item in extracted:
            match = find_matching_store(stores, item.get("name"), item.get("address"))
            if match is None:
                match = {
                    "name": item.get("name"),
                    "name_ja": item.get("name_ja"),
                    "address": item.get("address"),
                    "stars": item.get("stars"),
                    "genre": item.get("genre"),
                    "hours": item.get("hours"),
                    "videos": [],
                }
                stores.append(match)
            else:
                # 既存店舗で欠けている情報があれば補完する
                for field in ("name_ja", "address", "stars", "genre", "hours"):
                    if match.get(field) is None and item.get(field) is not None:
                        match[field] = item.get(field)

            existing_video_ids = {v["video_id"] for v in match["videos"]}
            if video_entry["video_id"] not in existing_video_ids:
                match["videos"].append(video_entry)

        processed_ids.add(video["video_id"])

        # 中断されても再実行時にやり直しにならないよう毎回保存する
        save_json(STORES_PATH, stores)
        save_json(PROCESSED_PATH, sorted(processed_ids))

        time.sleep(0.3)

    print(f"完了。店舗数: {len(stores)}件 -> {STORES_PATH}")


if __name__ == "__main__":
    main()
