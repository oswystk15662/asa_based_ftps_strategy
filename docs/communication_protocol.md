# 通信仕様 v1 草案

名前はこのプロジェクトの提案。ASA API 名は [調査索引](api_research.md) を参照。

| 方式 | 遅延・更新・データ量 | スレッド・運用・採否 |
|---|---|---|
| 生 TCP | 継続接続で低オーバーヘッド。フレーム化、再送境界、再接続は自前 | ワーカーで実行。初期の保守コストが高い |
| HTTP/REST | 短いポーリング/バッチ。低頻度の更新に対応、遅延は周期に依存 | 診断容易。AsaApi の外向き非同期 HTTP を候補に採用 |
| WebSocket | 双方から低遅延で通知、接続生存を管理 | 再接続時の再生とバックプレッシャーが必要。ポーリングの限界を測定後に再評価 |
| gRPC | 型付きバイナリ、ストリームと deadline | C++/Python の生成・ランタイム配布が増える。通信が支配的な場合の候補 |
| ZeroMQ | メッセージングと複数接続に適する | 永続再生とアプリレベル ACK は別途必要。初期は依存が増える |
| 共有メモリ | 同一ホストで低遅延・大容量 | 世代管理、プロセス停止、プラットフォーム差の負担。別 PC への分離に不適 |

## 接続と配送

Python が `127.0.0.1` にだけ bind。DLL が定期的に POST し、送信バッチの ACK と次のコマンドを受け取る。単一の未完了リクエストで開始し、tick 内で JSON の大きなデコードやシリアライズをしない。PoC 03 では Requests のコールバック配送コストも測定し、重ければ DLL の I/O ワーカーに移す。ローカルの別プロセスからの誤操作を避けるため設定外の認証トークンと型別許可リストを使い、本文・認証値のログ出力を制限する。リモート化には別の承認と到達範囲・暗号化・相互認証の設計が必要。

| エンドポイント | 内容 |
|---|---|
| POST /v1/hello | protocol major/minor、world_id、server build、API・MOD 版、boot_id、capabilities、直近の受領カーソル。major 不一致または未知 world は変更不可 |
| POST /v1/exchange | 観測差分、結果、イベントのバッチと受領済み seq。応答は delivery seq、コマンド、backpressure、必要な snapshot 範囲。ハートビートを兼ねる |
| POST /v1/snapshot | 同一 snapshot_id / base_seq の範囲とページ。観測範囲・完全性・終了マーカーを含む。差分欠落や再起動時に使用 |

コマンドの必須項目は `command_id`（UUID）、`world_id`、`boot_id`、`kind`、`object_id`、`expected_revision` または未作成条件、`issued_at`、`ttl_ms`、型付き `payload`。時刻は UTC、期限判定は受信後も単調時計で管理し、古い boot_id を拒否。クライアントとサーバーの時刻差を性能指標と分離する。座標は UE cm、回転は度の名前付き軸。地図と座標系の識別子を伴う。外部ロジックでは変換地点を一つにする。

ACK は受領とゲーム実行結果を区別する。結果には `command_id`、`status`、`reason`、観測された revision、実行/観測時刻、可能なら実体キー。状態は `accepted`、`applied`、`rejected`、`expired`、`unknown`。再送は同 ID・同内容、同 ID 異内容は拒否。アプリが ACK を失っても、永続化された操作と観測を照合してから判定する。欠番は再送を要求し、保持期間を超過したらスナップショットへ移る。イベント・結果を受け取った側は DB にコミットしてから ACK を返す。複数操作を束ねても各操作の結果を保持し、一部失敗でバッチ全体を再実行しない。

PoC 03 の初期試験値は polling 250 ms、HTTP timeout 2 s、最大 32 コマンド/バッチ、本文 256 KiB、キュー 128 件、再接続 0.5–8 s の指数バックオフ＋ジッター。実際の機能上限ではなく、超過時の挙動を確認するための値。飽和時は新規変更を受理せず、観測をまとめる。結果を落とした場合は欠番から再照合を要求する。切断・セッション更新中は新規変更を停止し、観測とゲーム継続を優先する。

## Phase 2 の NPC 移動試験

ローカルブリッジを `python -m simulator.phase1 --npc-trial` で起動し、ASA は `ASA_PHASE2_HUMAN_NPC_TRIAL=move-external` と新規の `AltSaveDirectoryName=Phase2HumanNPCExternalMove` を指定する。既存の Bearer トークンを双方に設定する。変更を許す対象は、専用の無人ワールドの試験コードが生成した管理 NPC 1 体と、その区画内で観測した既定の乾いた地表のみ。送信側は任意の座標を指定しない。

1. `/v1/npc-trial` へ `protocol: 1` と `world_id: "phase1"` を JSON の POST 本文で送り、`trial.status` が `ready` になったら `boot_id` と `trial.npc_id` を取得する。`npc_id` は 64 bit 値を保つため十進文字列。
2. `/v1/npc-move` へ同じ `protocol`、`world_id` と、現在の `boot_id`、`npc_id`、新しい UUID の `command_id` を POST する。一つの起動で 1 件だけ受理する。同一の再送は HTTP 202、別 ID や違う対象は HTTP 409。未配送の指示は 5 秒で期限切れになる。
3. `/v1/npc-trial` を再照会し、`command_id` と `status` を確認する。`engine_response` はエンジンの要求応答。水平 80 cm 以内かつ高さ差 150 cm 以内に入ったかを `ever_reached`、最後の観測時点で条件内かを `last_at_goal` で記録する。

この経路は使い捨てワールド用の 1 件枠で、配送と結果はメモリー内に保持する。ブリッジを再起動した場合は、ゲーム側の再観測から状態を確かめる。配送済みか分からない指示の自動回復には永続ジャーナルが必要。
