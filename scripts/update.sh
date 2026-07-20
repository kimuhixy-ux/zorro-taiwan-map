#!/bin/bash
# データ更新スクリプト
# 新しい動画の取得 → 店舗情報抽出 → ジオコーディング を順番に実行します。
#
# 使い方:
#   ./scripts/update.sh
#
# 完了後、変更内容を確認して git commit / git push してください。

set -e

cd "$(dirname "$0")/.."

echo "==> 1/3 新しい動画を取得しています..."
python3 scripts/fetch_videos.py

echo "==> 2/3 店舗情報を抽出しています..."
python3 scripts/extract_stores.py

echo "==> 3/3 緯度経度を付与しています..."
python3 scripts/geocode.py

echo ""
echo "完了しました。変更内容を確認してください:"
echo "  git status"
echo "  git diff data/stores.json"
echo ""
echo "問題なければ以下でGitHub Pagesに反映します:"
echo "  git add data/stores.json data/processed_video_ids.json data/manual_check.csv"
echo "  git commit -m \"店舗データを更新\""
echo "  git push"
