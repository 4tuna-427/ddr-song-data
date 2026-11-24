# 次バージョン（AC DDR STOMP 等）への追随手順

新バージョンが稼働したら、パイプラインは次の4点を差し替えるだけで追随できる。それ以外（マスター、ID、タイムスタンプ）はそのまま引き継ぐ。

## 差し替え箇所

| # | 対象 | 現在（WORLD） | 変更内容 |
|---|---|---|---|
| 1 | `scripts/fetch_official.py` のベースURL | `p.eagate.573.jp/game/ddr/ddrworld/...` | 新バージョンの ALL MUSIC リストのパスに変更。パラメータ（filter=7 等）が変わっていないか初回は目視確認 |
| 2 | `scripts/fetch_full_list.py` の `PAGE` | `DanceDanceRevolution WORLD Full Song List` | 新バージョンの Full Song List ページ名（例：`DanceDanceRevolution STOMP Full Song List`） |
| 3 | `scripts/fetch_remywiki.py` の `VERSION_ORDER` と対象バージョン | 末尾が `WORLD` | 末尾に新バージョン名を追加し、`game_range_covers_world` の対象を新バージョンに読み替える（関数名含め、対象バージョンを定数化して差し替えるのが確実） |
| 4 | `scripts/fetch_bemani_removed.py` の URL | `DanceDanceRevolution WORLD/削除曲リスト` | 新バージョンの削除曲リストのパス |

## バージョン移行時に起きること

- **大量の tombstone**：移行時に削除される曲は新バージョン側の削除曲リストに載る。パイプラインのガード（公式リスト掲載中は tombstone しない）により、存続曲は誤判定されない
- **解禁曲・限定曲の区分**：`phase3/availability_overrides.json` は移行のタイミングで見直す（限定イベントは新バージョンでは終了していることが多い）
- **ID は継続**：e-amusement の曲IDはバージョンをまたいで維持されるのが通例。万一変わった曲があれば `id_migrations.json` に追加する
- **RemyWiki の譜面行の範囲表記**：移行直後は「WORLD→STOMP」のような範囲表記が増える。範囲解釈（開始 ≤ 対象 ≤ 終了）が両バージョンを含むようになっているか、移行後の初回実行で changelog を確認する

## 移行チェックリスト

1. 上記4点を差し替える
2. ローカルで一式を実行し、changelog の追加・更新・tombstone 件数が想定の範囲か確認する（特に tombstone の大量発生が「移行時削除」の実態と合っているか、BEMANIWiki の告知と照合）
3. 問題なければ通常の日次実行に任せる
