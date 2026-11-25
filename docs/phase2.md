# Phase 2 の地形検証

2026-11-25 JST。Windows の ASA 98.9 / Steam build 26749470、AsaApi 2.11（`bd376a0422291b0b1bf15a0b7868e7e275605da9`）、MOD なし。Phase 1 と同じサーバーバイナリを使用。The Island は `AltSaveDirectoryName=Phase2Terrain` で新規作成し、Phase 1 のテストセーブも試験前後で SHA-256 が一致した。

## PoC 04 実機結果

座標は UE cm。最大 8 本の鉛直線を 1 バッチで指定し、接続ごとの初回観測で処理。Visibility チャンネルの最初の衝突から位置、法線、コンポーネント、所有アクターの型を取得する。地形型の確認と法線の検査を通った結果にだけ斜度を返す。空振りは `unobserved`。水面や水深、建築可能性はこの結果からは判定できない。

| 観測対象 | X, Y（cm） | 実機結果 |
|---|---|---|
| 平坦な地形衝突 | 125000, 125000 | Z −14555.96 cm、0.00°。±150 cm の東西南北 4 点も同じ高さ |
| 傾斜した地形衝突 | −125000, 125000 | Z −10722.50 cm、10.09° |
| メッシュ | 0, 0 | StaticMeshActor に最初に衝突。地形高さとして採用しない |
| 植生インスタンス | −125000, −125000 | InstancedFoliageActor に衝突。地形高さとして採用しない |
| マップ外側・空中のみ | 600000, 600000 / 0, 0（Z 80000–90000） | unobserved。空き地判定に使用しない |

実機 2 バッチ、計 16 本。再照会では平地と斜面の探索範囲を Z ±80000 cm から ±40000 cm に短縮した。2 点とも高さ 1 cm、斜度 0.1° の再現性基準を満たした。独立した目視実測、地表か水底かの判定、建築物や壁の衝突照合、プレイヤー参加時の追試は保留。生ログは `%LOCALAPPDATA%/ASA-Civilization-Phase1/logs/terrain-bridge.log` と `terrain-bridge-repeat.log`。

公開宣言と試験ビルドのキャッシュで `UVictoryCore.VTraceSingleBP`、`UStruct.InitializeStruct` / `DestroyStruct`、`FHitResult` の衝突フィールドを確認した。SDK の `FHitResult` はフィールド参照用なので、UE から取得したサイズ・アライメントに合う領域をゲームスレッドで初期化して使う。`ImpactNormal` は SDK が前方宣言のみのため Epic の公開定義で double ベクトルの基底型を確認した。 [トレース宣言](https://github.com/ArkServerApi/AsaApi/blob/2.11/AsaApi/Core/Public/API/ARK/UVictoryCore.h#L297) [構造体初期化](https://github.com/ArkServerApi/AsaApi/blob/2.11/AsaApi/Core/Public/API/ARK/UStruct.h#L11-L37) [Epic の型定義](https://dev.epicgames.com/documentation/unreal-engine/API/Runtime/Engine/FVector_NetQuantizeNormal?application_version=5.8)

## 再現

Phase 1 のローカルトークンと起動手順を使用する。プラグインを再ビルド・配備し、サーバーを起動する前に既存の `SavedArks` と分離した保存先を指定する。ブリッジに `--trace` を渡したときだけ測定する。

```powershell
$python = uv python find --offline 3.12
& $python -m unittest discover -s tests -v
& $python -m simulator.phase1 --trace 125000 125000 80000 -80000 --trace -125000 125000 80000 -80000 --trace 600000 600000 80000 -80000
```

## 建築 PoC への引き継ぎ

木の土台ではアイテム BP の解決と `UPrimalItem.StructureToBuild` の参照を候補にする。アイテムと実際に生成する構造物クラスを実機で照合してから配置を試す。今回の平坦な座標だけで乾地・建築可と判断せず、試験セルで水と占有を別確認する。`ServerRequestPlaceStructure` はプレイヤーコントローラーの経路で、プレイヤー不在時の成功を保証しない。 [クラス解決と内部アクセスの調査](api_research.md)

Linux の仮想環境は Windows の専用サーバーと DLL の検証には不要。Linux へ Python を移せることを確かめる場合に同じテストを実行する。既存の Linux PC、CI、WSL2、仮想マシンはいずれも候補で、この PC に Linux 環境を追加する前提はない。
