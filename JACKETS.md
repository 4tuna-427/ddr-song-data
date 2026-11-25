# ジャケット画像の KV 配信

曲データ（songs.json）は従来どおり GitHub Pages で公開するが、ジャケット**画像**は
KONAMI の著作物であるため公開ミラーにはせず、Cloudflare Workers KV に置いて
スコア管理アプリの Worker が API トークン認証つきで配信する。

## 仕組み

- `scripts/fetch_official.py` が公式リストのジャケット画像 URL を曲レコードに保持する
  （`jacket_url`。今までは曲 ID の抽出にだけ使って捨てていた）
- `scripts/sync_jackets.py`（日次ワークフローの run_pipeline の後段）:
  - 未取得の曲だけ画像を取得する。公式 URL（小さい JPEG）が第一候補、
    公式リストに無い曲は RemyWiki のジャケットファイル（MediaWiki API で解決、
    「<ページ名> DDR」版があれば優先）
  - 全画像を JPEG・最大 256×256・quality 82 に正規化して KV へ bulk PUT
  - 取得済みは `phase3/jackets_state.json`（リポジトリにコミット）で管理し、
    日次実行では差分だけを送る。削除（tombstone）された曲は KV からも消す
  - master.json と配信 songs.json の各曲に `jacket: true/false` を反映する
  - KV の無料枠は書き込み 1,000回/日のため、1回の実行の書き込み上限は
    既定 900。初回投入（約1,450曲）は2日の日次実行に分かれて完了する
  - 上流のジャケット差し替えは検知しない（公式 URL は曲 ID のみで決まるため）

## 初期設定（1回だけ）

1. Cloudflare で KV namespace を作成する（スコア管理アプリ側の手順と共通。
   `wrangler kv namespace create DDR_JACKETS` 等）。発行された namespace ID を控える
2. Cloudflare API トークンを作成する（Workers KV の編集権限）
3. このリポジトリの GitHub Secrets に登録する:
   - `CF_API_TOKEN` … 上記トークン
   - `CF_ACCOUNT_ID` … Cloudflare のアカウント ID
   - `KV_NAMESPACE_ID` … 1 の namespace ID
4. Secrets が未設定の間、sync ステップは何もせず正常終了する（ワークフローは失敗しない）

## ローカルでの動作確認

```sh
python scripts/sync_jackets.py --dry-run          # 計画だけ表示
python scripts/sync_jackets.py --local-dir /tmp/jackets --max-writes 10
# KV の代わりにローカルフォルダへ書き出す（state と jacket フラグも更新される）
```
