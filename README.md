# ゾロの台湾グルメ 紹介店舗マップ（非公式）

YouTubeチャンネル「[ゾロの台湾グルメ](https://www.youtube.com/@zorro_taiwangourmet)」で紹介された飲食店を地図上にプロットする非公式ファンメイドPWAです。

本アプリは非公式のファンメイドです。店舗情報はYouTubeチャンネル「ゾロの台湾グルメ」の公開情報に基づきます。

## 現在の進捗

- [x] フェーズ1: データ収集パイプライン（Pythonスクリプト）
- [ ] フェーズ2: マップPWA（フロントエンド）
- [ ] フェーズ3: デプロイと運用

---

## フェーズ1: データ収集パイプラインの使い方

初めての方向けに、順番にコマンドを実行する手順を説明します。ターミナルで以下を実行してください。

### 0. 準備（最初の1回だけ）

```bash
cd /Users/user/zorro-taiwan-map

# Python パッケージをインストール
pip3 install -r requirements.txt

# .env ファイルを作成してAPIキーを設定
cp .env.example .env
```

作成した `.env` ファイルをエディタで開き、以下の2つのAPIキーを記入してください。

- `YOUTUBE_API_KEY`: [Google Cloud Console](https://console.cloud.google.com/) で YouTube Data API v3 を有効化して取得したAPIキー
- `ANTHROPIC_API_KEY`: Anthropic APIキー

`.env` はGitには絶対にコミットされません（`.gitignore` で除外済み）。

### 1. `fetch_videos.py` — 全動画を取得する

```bash
python3 scripts/fetch_videos.py
```

チャンネルの全動画（タイトル・概要欄・公開日・URL）を取得し、`data/videos_raw.json` に保存します。
再実行すると、新しく公開された動画だけを追加取得します（既存分は再取得しません）。

### 2. `extract_stores.py` — 店舗情報を抽出する

```bash
python3 scripts/extract_stores.py
```

`videos_raw.json` の各動画をAI（Claude Haiku）に読ませて、店舗の事実情報（店名・住所・⭐評価・ジャンル・営業時間）だけを抽出し、`data/stores.json` にまとめます。
レビュー文・感想文は一切抽出しません。同じ店舗が複数動画に登場する場合は自動的に1件にまとめられます。
こちらも再実行すると、未処理の動画分だけAPIを呼び出します（差分処理）。

### 3. `geocode.py` — 緯度経度を付与する

```bash
python3 scripts/geocode.py
```

`stores.json` の各店舗の住所から緯度経度を調べて追記します（OpenStreetMapのNominatimを利用、1秒に1回まで）。

住所が概要欄になかったり、ジオコーディングに失敗した店舗は `needs_manual_check: true` が付き、`data/manual_check.csv` に書き出されます。このCSVを開いて `lat` / `lng` 列に緯度経度を手入力し、保存してから `geocode.py` を再実行すると、その内容が `stores.json` に取り込まれます。

緯度経度の調べ方の例: [Google マップ](https://maps.google.com/) で店舗を検索 → 地図を右クリック →「この場所について」で座標が表示されます。

### 実行順序のまとめ

```bash
python3 scripts/fetch_videos.py
python3 scripts/extract_stores.py
python3 scripts/geocode.py
```

この3つを順に実行すると `data/stores.json` が完成します。中身を確認してからフェーズ2（地図アプリ）に進みます。

---

## ディレクトリ構成（フェーズ1時点）

```
zorro-taiwan-map/
├── .env                  # APIキー（Gitには含まれません）
├── .env.example           # .env のひな形
├── requirements.txt        # Python依存パッケージ
├── scripts/
│   ├── fetch_videos.py     # 1. 動画取得
│   ├── extract_stores.py   # 2. 店舗情報抽出
│   └── geocode.py          # 3. 緯度経度付与
└── data/
    ├── videos_raw.json     # 動画の生データ（Gitには含まれません）
    ├── stores.json         # 完成した店舗データ（フロントエンドが読み込む）
    ├── processed_video_ids.json  # 抽出処理済みの動画ID一覧
    └── manual_check.csv    # 手動確認が必要な店舗一覧
```
