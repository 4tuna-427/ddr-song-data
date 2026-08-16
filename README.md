# DDR Song Data API

Googleスプレッドシートで管理されている楽曲マスタデータを、定期的にJSON形式に変換し、GitHub Pagesを利用して配信（CDN化）するリポジトリです。

## 🚀 API エンドポイント

最新の楽曲データ（JSON）は、以下のURLからいつでも取得できます。

```text
https://4tuna-427.github.io/ddr-song-data/songs.json
```
*(※GitHub PagesはデフォルトでCORSが許可されているため、外部のWebアプリなどから直接読み込み可能です)*

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

GitHub Actionsにより、以下のタイミングで自動的に最新のスプレッドシートデータがJSONに反映されます。

- **定期自動更新**: 毎日 午前3:00 (JST)
- **手動更新**: GitHubの `Actions` タブ ＞ `Update and Deploy Songs Data` ＞ `Run workflow` から手動で即時反映
- **プッシュ時**: このリポジトリのスクリプトや設定ファイルを更新した時

## 🔧 システムの仕組み

1. GitHub Actions が一時サーバーを立ち上げ、Pythonスクリプト (`scripts/fetch_songs.py`) を実行
2. Secretsに登録された `GAS_API_URL` を経由して、スプレッドシートのデータを取得
3. データをJSON形式に整形して `dist/songs.json` を生成
4. 生成されたファイルを直接 GitHub Pages にデプロイ（※Gitのコミット履歴を汚さずにデータのみを配信します）