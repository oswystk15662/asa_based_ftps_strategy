# 外部文明シミュレーター

ASA との読み取り接続とは独立に、サンプル地形で集落・道路・輸送・工業化・国家間の関係を再生できる。Python 3.12 の標準ライブラリと SQLite を使う。ゲームへの反映は Phase 2 の配置・所有・保存試験後に接続する。

## 実行

リポジトリルートで実行。初回だけ `--scenario` を指定する。以下は使い捨ての新規 DB を作る PowerShell の例。

```powershell
$python = uv python find --offline 3.12
$db = Join-Path $env:TEMP ("asa-estuary-" + [guid]::NewGuid() + ".sqlite")
& $python -m simulator.civilization --database $db --scenario configs/estuary-demo.json --ticks 16
& $python -m simulator.civilization --database $db --ticks 16 --focus Quarry
& $python -m unittest discover -s tests -v
& $python -m benchmarks.benchmark_civilization --ticks 80 --cities 120
```

Linux では `python3.12` と書き込み可能な DB パスで同じモジュールを実行できる。GitHub Actions の Windows Server 2025 と Ubuntu 24.04 で、Python 3.12 の同じテスト 10 件が通過した。 [実行結果](https://github.com/oswystk15662/asa_based_ftps_strategy/actions/runs/45622168516)

## 現在の範囲

| Phase | 一連のシナリオで確認できる機能 | 実機・拡張で残る機能 |
|---|---|---|
| 2 | 独立ワールドで地表トレース、木の土台の生成・削除・保存、小型収納箱の木材を外部 SQLite へ反映 | 通常建築・プレイヤー別の権限、遠隔区画の実体操作、人間型 NPC の移動 |
| 3 | 人口に応じた採集担当の配分、食料と人口、土台の資材予約と占有時の予約解除 | ASA の現物状態・台帳との照合、NPC の作業 |
| 4 | 斜面・水域・障害物を考慮した経路、既存道路の優先、通行止め時の新規輸送の迂回と輸送中の待機 | 実機での地形への適合、道路網全体の最適化、耐久・維持管理 |
| 5 | 容量予約付き輸送。精錬の倍量処理で発電燃料も計上し、燃料不足時に通常処理へ戻る | ASA の設備・レシピ・電力との一致、複数品種の同時最適化 |
| 6 | 初期同盟、食料不足による対立、第三勢力からの物資到着による停戦。対立中は当事者間の新規輸送を停止 | 動的な国境や外交戦略、ASA の実勢力と部隊の接続 |
| 7 | `--focus` で都市を毎 tick 更新と 4 tick 集約の間で切替。SQLite 復元と複数規模の計測 | 個体・実体の詳細度遷移、時間予算に基づく調整、実機規模測定 |

コードは `simulator/civilization/` に配置。初期化は `scenario.py`、地形と領域は `terrain.py`、建設と生産は `economy.py`、輸送は `logistics.py`、外交は `diplomacy.py`、tick と資源収支は `simulation.py`、SQLite は `storage.py` が担当する。v1 の DB は次の tick で v2 の計算規則に進み、切替を `model_upgraded` に記録する。

シナリオ JSON の `road_closures` には、例えば `{"from":[0,0],"to":[1,0],"start":2,"end":4}` を配列に入れる。隣接区間が tick 2 から 3 の間閉じ、tick 4 に開く。輸送中の荷は経路を予約したまま待機し、開通後に進む。`alliances` には初期同盟を結ぶ勢力のペアを指定する。例は `[["Estuary","Upland"]]`。

在庫・輸送中・建設予約を足した資源総量が、採集・消費・加工の明示差分に一致するか毎 tick チェックする。状態とイベントの書き込みを SQLite の同一トランザクションで確定する。中断や書き込みエラーでは、その tick の変更全体をロールバックする。Windows で、連続 32 tick と再起動を挟んだ 32 tick の状態・イベント列が一致した。

初期モデルでは輸送が通る全区間の容量を到着まで予約する。各 tick の経路探索は最大 8 回、発送は 1 件までとし、候補先を tick ごとに巡回する。資材単位、レシピと損耗は外部シナリオ用の仮値。デモの都市、領域、建設は合成地図上の状態で、ASA のマップやセーブと紐付いていない。

## ベンチマーク

2026-11-25 JST、Windows、Python 3.12.11、モデル v2。各都市の初期人口は 1,000。食料不足を含む合成地図で各 80 tick を実行した。時間にはディスク上の SQLite の読み書きを含む。

| 都市数 | 中央値 (ms) | p95 (ms) | 最大 (ms) |
|---:|---:|---:|---:|
| 15 | 15.9 | 23.2 | 31.1 |
| 30 | 20.0 | 26.6 | 29.4 |
| 60 | 27.1 | 41.2 | 135.3 |
| 120 | 59.8 | 87.5 | 133.8 |
| 240 | 108.6 | 194.5 | 260.2 |

数値は外部シミュレーターの処理時間。ASA の実体数、サーバーのフレーム時間、クライアント同居時の負荷の上限は別途測定する。
