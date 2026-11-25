# Phase 1 基盤と検証

2026-11-25 JST。ASA サーバーへの書き込みを伴わない、読み取り専用の PoC 01–03。

## 固定版

Windows x64、MSVC 14.44（v143）、Windows SDK 10.0.26100.0、AsaApi 2.11 の公開ソースと配布 import library、fmt 12.1.0。実機は ASA 98.9 / Steam build 26749470、The Island、MOD なし。詳細は [版一覧](../configs/phase1-versions.json) と [API 調査](api_research.md)。

ゲーム API の呼び出しは [S1/S2](api_research.md#ソース索引) で確認した Ready 後の tick に限定。ワールドのマップ名、時刻、現在取得できるプレイヤーコントローラー数を、最大 1 件ずつ送る。AsaApi Requests が HTTP をワーカーで処理し、完了応答は tick 経由。S9 の 2.11 解除処理は保留中のコールバックを破棄する実装で、動作中のアンロード試験は未実施。

## ビルドと仮想検証

PowerShell 7 をリポジトリルートで開く。ビルドスクリプトは約 35 MB の SDK などを一時フォルダーへ取得し、チェックサムを検証して、Release x64 の DLL と PDB を生成する。通信テストは Python 標準ライブラリのみ。

```powershell
./scripts/build-phase1.ps1 -SdkDirectory (Join-Path $env:TEMP 'asa-civ-phase1-sdk')
$python = uv python find --offline 3.12
& $python -m unittest discover -s tests -v
```

Linux の再生コマンドは `python3.12 -m unittest discover -s tests -v`。Windows で同じケースを検証済み。Linux は実行環境の利用可否を確認してから実施する。

## サーバー側検証

1. Phase 1 専用の新しいサーバールートを作り、Steam の専用サーバー 2430930 を導入する。SteamCMD 初回の匿名取得は `Missing configuration` で終了。Windows 配布の明示とアプリ情報の更新を入れた再試行で成功した。新規 The Island のバニラ起動後、表示版と Steam build ID を記録して停止する。
2. 停止状態で 2.11 配布物からローダー、設定、依存 DLL、および `ArkApi/` の本体 DLL 等を `ShooterGame/Binaries/Win64` に配備する。今回、サーバー側の `msvcp140.dll`（14.50）が同梱版（14.40）より新しいため保持した。同梱 Permissions は検証対象外。自動リロードを無効化し、`AsaApiLoader.exe` でキャッシュと起動を確認した。
3. 停止状態で `Win64/ArkApi/Plugins/AsaCivilizationPhase1/` に DLL、PDB、[PluginInfo.json](../plugin/PluginInfo.json) を配置する。ローカル端末で十分長い一時トークンを生成し、サーバーと Python の子プロセスへ `ASA_PHASE1_TOKEN` を渡す。サーバーに実測した `ASA_PHASE1_SERVER_BUILD` も渡す。設定ファイルやコマンドラインに秘密値を置かない。Python は標準値 `127.0.0.1:8765` と world `phase1` を使う。
4. `python -m simulator.phase1`（選択した Python 3.12 の実体）を起動し、専用検証サーバーを起動。バニラ→ローダー→DLL の起動差を記録。セーブや通常終了に影響がないことを確かめる。
5. Ready 後にシミュレーターのマップ・時刻・人数をサーバーログと比較。クライアントが利用可能なら、参加・退出それぞれで人数を照合する。Python のみ停止・再起動し、サーバーのログで再接続、Python で新しい command ID と seq の再開を確認。途中の互換性、接続失敗は失敗条件として記録する。

## Phase 1 の通信範囲

`POST /v1/hello` で現在の boot と版を送信し、`POST /v1/exchange` で読み取り結果を返す。1 種類のコマンド `observe_server` のみ。スナップショットは 1 メッセージで完結し、接続の再確立で ACK とコマンド ID を照合する。実装上の上限は本文 16 KiB、未完了通信 1、送信間隔 250 ms、失敗時バックオフ 0.5–8 s。受領カーソルはシミュレーターのメモリにあり、プロセスが再起動すると観測し直す。ゲーム変更を追加するときは [通信仕様](communication_protocol.md) の永続ジャーナル・操作単位の事前条件を先に実装する。

## 2026-11-25 の検証状態

| PoC | 確認結果 | 残る確認 |
|---|---|---|
| 01 DLL | MSVC v143 で Release x64 DLL と PDB を生成。バニラ起動、AsaApi オフセットキャッシュ取得と再利用、DLL ロード、検証サーバー停止を実機で確認 | 動作中のホットアンロードと `Plugin_Unload` の呼び出し |
| 02 状態 | 実機で Ready 後に TheIsland_WP、人数 0、増加するワールド時計を観測。マップと MOD なしの起動ログが一致 | ASA クライアント参加・退出後の人数差 |
| 03 通信 | Windows の仮想テスト 3 件に加え、ASA 実機でループバック通信を確立。Python を停止すると接続タイムアウトを検出し、再起動後に同じ ASA boot ID で観測を seq 1 から再開 | Linux での同じ仮想試験、ゲーム tick に加えた処理コストの対照測定 |

実機は `%LOCALAPPDATA%/ASA-Civilization-Phase1/server`、実験ログは同ルートの `logs/`、AsaApi 詳細ログは `server/ShooterGame/Binaries/Win64/logs/` に保存。インストール時の容量は約 11.47 GiB。バニラ初回に Steam Query が全 IPv4 アドレスで待受けたため、以降の試験では `-nosteam` を付けた。ゲーム UDP は `127.0.0.1:17777`、Python HTTP は `127.0.0.1:8765`、RCON は無効。ローダー試験では `-NoBattlEye` も使用した。

Python 停止前は観測 3 件を確認。再起動後の確認時点で、同じ boot ID の連続した 87 件を検証した。先頭 2 件を除く到着間隔は中央値 302 ms、最大 600 ms（84 区間）。これはデータ到着間隔の短時間サンプル。HTTP RTT や tick 負荷は別途計測する。検証の終了時に ASA、ローダー、Python の停止を確認した。
