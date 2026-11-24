# DDR Song Data API

DDR（Dance Dance Revolution）の楽曲・譜面データを、公開ソースから自動収集してJSON形式に変換し、GitHub Pagesを利用して配信（CDN化）するリポジトリです。

## 🚀 API エンドポイント

最新の楽曲データ（JSON）は、以下のURLからいつでも取得できます。

```text
https://4tuna-427.github.io/ddr-song-data/songs.json
```

*(※GitHub PagesはデフォルトでCORSが許可されているため、外部のWebアプリなどから直接読み込み可能です)*

BPM・ノーツ数・初出バージョンなどを含む拡張版（v2形式）は、リポジトリ内の `phase3/out/songs_v2.json` にあります。

## 💡 データの取得例 (JavaScript)

```javascript
fetch("https://4tuna-427.github.io/ddr-song-data/songs.json")
  .then(response => response.json())
  .then(data => {
    console.log("楽曲データを取得しました:", data);
  })
  .catch(error => {
    console.error("エラーが発生しました:", error);
  });
```

## ⚙️ データの更新タイミング

GitHub Actionsにより、以下のタイミングで自動的に最新データがJSONに反映されます。

- **定期自動更新**: 毎日 午前3:00 (JST)
- **手動更新**: GitHubの `Actions` タブ ＞ `Update and Deploy Songs Data` ＞ `Run workflow` から手動で即時反映
- **プッシュ時**: このリポジトリのスクリプトや設定ファイルを更新した時

## 🔧 システムの仕組み

1. GitHub Actions が一時サーバーを立ち上げ、3つの公開ソースからデータを取得
   - **公式 e-amusement ALL MUSIC リスト**: 収録曲のID・タイトル・アーティスト・難易度（Challenge以外）
   - **RemyWiki**（MediaWiki API）: BPM・曲の長さ・ノーツ数・初出バージョン・Challenge難易度・最新追加曲
   - **BEMANIWiki 削除曲リスト**: 削除された曲の検出
2. 取得データを統合し、前回のマスタデータとの差分を適用（追加・レベル変更・削除を検出して `created_at` / `updated_at` / `deleted_at` を自動で管理。削除された曲はデータから消さず、`deleted_at` を付けて残します）
3. 状態（マスタデータ・変更履歴）をGitにコミット
4. 配信ファイル `dist/songs.json` を生成し、GitHub Pages にデプロイ

取得に失敗した場合はコミットもデプロイも行われず、前日のデータが配信され続けます（あわせてIssueが自動で作成されます）。

### データソースについての方針

- 公式リストにはイベント解禁曲などが載らないため、「公式リストに無い＝削除」とは扱いません。削除の判定はBEMANIWikiの削除曲リストへの掲載をもって行います（復活した曲を誤判定しないための確認付き）
- 公式リストにまだ載っていない新曲は、RemyWikiの情報で仮ID（`remy-` 始まり）のまま先行収録し、公式リストに載った時点で正規IDへ自動マージできるようになっています
- 各ソースへは1日1回・低頻度でアクセスし、取得元の規約・robots.txtに従います

## 📝 運用メモ

- 曲ごとの手動対応付け: `phase3/manual_title_map.json`（表記ゆれで自動突合できない曲）
- IDが変わった曲の対応表: `phase3/id_migrations.json`
- 期間限定イベント曲・EXTRA SAVIOR解禁曲などの区分: `phase3/availability_overrides.json`
- 次バージョン（AC DDR STOMP等）への追随手順: `NEXT_VERSION.md`
- 変更履歴は `phase3/changelog-*.json` に実行日ごとに残ります
