# 取り込み手順書（ルートA：既存 ddr-song-data リポジトリ）

2026-11-24 にルートAで確定。既存リポジトリの実態に合わせて書いてある。

## 既存リポジトリの現状（確認済み）

- ワークフローは `.github/workflows/update-songs.yml` の1本だけ。毎日03:00 JST に GAS から取得 → `dist/songs.json` を生成 → Pages アーティファクトとしてデプロイ（データは Git にコミットしていない）
- 配信URLは `https://4tuna-427.github.io/ddr-song-data/songs.json`（dist のルートがそのまま公開される）

## 取り込み手順

1. **事前設定**：リポジトリの Settings → Actions → General → Workflow permissions を **Read and write permissions** にする（パイプラインの状態をコミットするために必要。現行ワークフローは `contents: read` で動いている）
2. **ファイル配置**：このパッケージの中身をリポジトリに配置する
   - `.github/workflows/update-songs.yml` — **同名ファイルの差し替え**（旧 GAS 版はこれで置き換わる）
   - `scripts/` — 既存の `scripts/fetch_songs.py` と同居してよい（新しいスクリプト6本を追加）
   - `phase0/`、`phase1/`、`phase2/`、`phase3/`、`requirements.txt`、`.gitignore`、ドキュメント類をルートに配置
   - 配置したら main に push する（push トリガーでワークフローが起動するが、それで問題ない）
3. **初回実行の確認**：Actions タブで `Update and Deploy Songs Data` が成功することを確認する。初回は同梱の検証済みマスターが初期状態なので、差分ゼロ〜小規模のはず
4. **配信の確認**：`https://4tuna-427.github.io/ddr-song-data/songs.json` を開き、次の3点を確認する
   - 曲数が 1,485 になっている
   - Happy の `single_difficult_level` が `"8"` になっている
   - `artist` が埋まっている（例：MAKE IT BETTER → mitsu-O!）
5. **後片付け（任意・後日でよい）**：問題なく数日回ったら、GitHub Secrets の `GAS_API_URL` とスプレッドシート側の運用を終了する。`scripts/fetch_songs.py` も不要になる

## 新ワークフローの動き（旧版との違い）

- 入力段が GAS → 公式リスト＋RemyWiki＋BEMANIWiki 削除リストに変わる
- 状態（`phase3/master.json`、RemyWiki キャッシュ、changelog）が Git にコミットされるようになる。これが差分判定の前回値になる
- 配信段は従来どおり `dist/songs.json` → Pages アーティファクトで、URL は変わらない
- 取得に失敗した場合はジョブが止まり、コミットもデプロイもされない（前日のデータが配信され続ける）。加えて Issue が自動で立つ

## 注意点

- 仮ID（`remy-` 始まり）の曲が後日公式リストに載った場合は、`phase3/id_migrations.json` に旧→新の対応を1件追加して push する（次回実行で正規IDにマージされる）
- ワークフローの push トリガーは `scripts/**` と `.github/workflows/**` の変更時のみ。データコミット（phase3/**）では再起動しないのでループしない

## 切り戻し

問題が出たら、`.github/workflows/update-songs.yml` を旧版（GAS）に戻して push すれば従来運用に復帰する。パイプライン側のコミット履歴は残るが、配信には影響しない。
