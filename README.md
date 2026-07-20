# ゾロの台湾グルメ 紹介店舗マップ（非公式）

YouTubeチャンネル「[ゾロの台湾グルメ](https://www.youtube.com/@zorro_taiwangourmet)」で紹介された飲食店を地図上にプロットする非公式ファンメイドPWAです。

本アプリは非公式のファンメイドです。店舗情報はYouTubeチャンネル「ゾロの台湾グルメ」の公開情報に基づきます。

**公開URL: https://kimuhixy-ux.github.io/zorro-taiwan-map/**

## 現在の進捗

- [x] フェーズ1: データ収集パイプライン（Pythonスクリプト）
- [x] フェーズ2: マップPWA（フロントエンド）
- [x] フェーズ3: デプロイと運用

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

この3つを順に実行すると `data/stores.json` が完成します。

---

## フェーズ2: 地図アプリ（フロントエンド）

`index.html` / `style.css` / `app.js` からなる素のHTML/CSS/JS製PWAです。Leaflet.js（CDN読み込み）とOpenStreetMapタイルを使い、`data/stores.json` を読み込んで地図上にマーカー表示します。ビルド不要で、ローカルではHTTPサーバーを立てて確認できます。

```bash
python3 -m http.server 8765
# ブラウザで http://localhost:8765/index.html を開く
```

---

## フェーズ3: デプロイと運用

**公開URL: https://kimuhixy-ux.github.io/zorro-taiwan-map/**

GitHubリポジトリ `kimuhixy-ux/zorro-taiwan-map` の `main` ブランチから GitHub Pages で自動公開されています。`main` にプッシュすると数分で公開サイトに反映されます。

### データを更新する

新しい動画が公開されたら、以下のいずれかの方法でデータを更新できます。

**方法A: まとめて実行するスクリプトを使う**

```bash
./scripts/update.sh
```

**方法B: 手動で1つずつ実行する**

```bash
python3 scripts/fetch_videos.py
python3 scripts/extract_stores.py
python3 scripts/geocode.py
```

どちらの方法でも、実行後は変更内容を確認してからGitHubに反映します。

```bash
git add data/stores.json data/processed_video_ids.json data/manual_check.csv
git commit -m "店舗データを更新"
git push
```

プッシュしてから数分待つと、公開サイトに新しいデータが反映されます（Service Workerがオフラインキャッシュを持つため、スマホ側で更新が反映されない場合はブラウザのリロードが必要な場合があります）。

### 手動確認が必要な店舗の座標を埋める

`data/manual_check.csv` に、住所からの自動ジオコーディングができなかった店舗が一覧で書き出されます。このCSVの `lat` / `lng` 列に緯度経度を手入力して保存し、`python3 scripts/geocode.py` を再実行すると、内容が `data/stores.json` に取り込まれます。

緯度経度の調べ方の例: [Google マップ](https://maps.google.com/) で店舗を検索 → 地図を右クリック →「この場所について」で座標が表示されます。

---

## ディレクトリ構成

```
zorro-taiwan-map/
├── .env                       # APIキー（Gitには含まれません）
├── .env.example                # .env のひな形
├── requirements.txt             # Python依存パッケージ
├── index.html / style.css / app.js  # 地図PWA本体
├── manifest.json / sw.js         # PWA設定・Service Worker
├── icons/                      # PWAアイコン
├── scripts/
│   ├── fetch_videos.py          # 1. 動画取得
│   ├── extract_stores.py        # 2. 店舗情報抽出
│   ├── geocode.py               # 3. 緯度経度付与
│   └── update.sh                # 1〜3をまとめて実行
└── data/
    ├── videos_raw.json          # 動画の生データ（Gitには含まれません）
    ├── stores.json              # 完成した店舗データ（フロントエンドが読み込む）
    ├── processed_video_ids.json # 抽出処理済みの動画ID一覧
    └── manual_check.csv         # 手動確認が必要な店舗一覧
```
