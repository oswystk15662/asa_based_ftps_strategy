# ARK: Survival Ascended 自律文明シミュレーション

ASA の専用ワールドで、人口・経済・都市・物流・外交を持つ文明が自律的に発展する環境を設計する。近距離では既存のゲームアセットを使い、遠隔地は外部シミュレーターで進行させる。

2026-11-24（JST）に Phase 0 の調査・設計を完了。11-25 に Phase 1 のテスト環境を導入し、ASA 98.9 と AsaApi 2.11 で読み取り DLL のロード、サーバー状態取得、ローカル通信の再接続を確認した。最初のゲーム内目標は、外部で資材を計上して選んだ建設地点に既存部材を配置し、再起動しても重複配置しない単一集落。人間型 NPC の制御は独立した成立条件とする。

| 文書 | 内容 |
|---|---|
| [環境](docs/environment.md) | 実測、容量、構成 A/B/C |
| [要求](docs/requirements.md) | 最終仕様と最小プロトタイプ |
| [API 調査](docs/api_research.md) | ASA 専用のソース、対応版、NPC MOD |
| [実現可能性](docs/feasibility_matrix.md) | 機能別判定と検証 |
| [アーキテクチャ](docs/architecture.md) | 責務、構成、障害時の動作 |
| [アルゴリズム](docs/algorithms.md) | 11 個の意思決定問題 |
| [通信](docs/communication_protocol.md) | 比較と v1 草案 |
| [データモデル](docs/data_model.md) | 状態の正、台帳、復旧 |
| [性能](docs/performance.md) | 詳細度と計測 |
| [技術検証](docs/poc_plan.md) | PoC 01–14 |
| [Phase 1 基盤](docs/phase1.md) | ビルド、仮想通信、実機検証 |
| [Phase 2 地形](docs/phase2.md) | 実機の地形・衝突トレースと建築 PoC の前提 |
| [外部シミュレーター](docs/simulator.md) | 集落・道路・物流・文明のデモと再現手順 |
| [ロードマップ](docs/roadmap.md) | 工数、承認事項、Phase 1 の手順 |
| [リスク](docs/risks.md) | 検証による判断と代替案 |
| [設計判断](docs/decisions/) | ADR |
| [用語](CONTEXT.md) | 文明、都市、実体、資源台帳 |
| [作業ルール](AGENTS.md) | Codex と開発者向け |

将来の配置は `plugin/`（Windows C++）、`simulator/`（Python）、`protocol/`（スキーマとサンプル）、`tools/`（診断）、`configs/`（公開可能な雛形）、`tests/`（契約・再生テスト）、`benchmarks/`（負荷条件）、`scripts/`（再現手順）。実装する Phase で追加する。
