# Phase 2 の実機検証

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

追試では `ASA_PHASE2_INSPECT_FOUNDATION=1` を指定して、新規の `Phase2FoundationInspect` ワールドで `PrimalItemStructure_WoodFloor_C` の既定値から `/Game/PrimalEarth/Structures/Wooden/Floor_Wood_SM_New.Floor_Wood_SM_New_C` を実際に解決した。`TSoftClassPtr.LoadSynchronous` と `UClass.GetDefaultObject(false)` を使用し、構造物の生成は行っていない。 [アイテムの構造物参照](https://github.com/ArkServerApi/AsaApi/blob/2.11/AsaApi/Core/Public/API/ARK/UPrimalItem.h#L152)

## PoC 05・13 の実機試験

水域候補は `ASA_PHASE2_SURVEY_WATER=1` で確認した。ロード済みの水域ボリューム 118 件に対し、衝突面から 75 cm 上の点を `AVolume.EncompassesPoint` で測定。以前の平坦面 (125000, 125000) は水域内だった。試験セル (107449, 211985) では中心と四隅が水域外で、地表の斜度は 2.27–3.60°、高低差は 22.47 cm。水深や未ロード地域の水域は対象外。 [水域判定の公開宣言](https://github.com/ArkServerApi/AsaApi/blob/2.11/AsaApi/Core/Public/API/ARK/AVolume.h#L21)

The Island の新規 `AltSaveDirectoryName=Phase2FoundationPlacement` で、プレイヤーなしの状態に限定して試験。土台クラスの地表オフセット、設置面中央と四隅、周囲の構造物の数を確認し、衝突時は生成を拒否する設定で `UWorld.SpawnActor` を実行する。後続の確認・削除には同一クラス、検証区画内の個数 1、記録済みの非ゼロ `StructureID` が必要。通信経由では試験操作を受付けない。 [生成の公開宣言](https://github.com/ArkServerApi/AsaApi/blob/2.11/AsaApi/Core/Public/API/ARK/UWorld.h#L168) [構造物 ID の公開宣言](https://github.com/ArkServerApi/AsaApi/blob/2.11/AsaApi/Core/Public/API/ARK/APrimalStructure.h#L111) [セーブの公開宣言](https://github.com/ArkServerApi/AsaApi/blob/2.11/AsaApi/Core/Public/API/ARK/AShooterGameMode.h#L900)

| 試験 | 結果 |
|---|---|
| 生成と同期保存 | 土台 1 個、ID 9222819。配置座標は (107449, 211985, −14381.93) cm |
| 再起動後の照合 | 土台 1 個、同じ ID 9222819 |
| 占有済みセルへの再指示 | `trial cell already occupied` として拒否 |
| ID 指定の削除 | クラス・ID・個数照合後に削除し、同期保存 |
| 削除後の再起動 | 同じ試験区画で地表を再確認し、構造物 0 個 |
| 同期保存直後の強制終了 | 追試の土台 ID 3271002 を保存してから検証プロセスを強制終了。再起動後も同じ ID の土台が 1 個。検証後に削除し、再起動して 0 個を照合 |
| 明示保存前の強制終了 | `place-unsaved` でアクター ID 221420427 を生成した直後に `Stop-Process -Force`。ワールドファイルのハッシュには差があったが、再起動後の区画は 0 個だった。永続化は再観測で判定した |
| 耐久と衝突の追試 | ID 454007828 は生成時・再起動後とも `GetHealth` と `GetMaxHealth` が 0、所有プレイヤー ID 0。再起動後、土台中央の Visibility トレースは土台に当たらず、地形 Z −14421.93 cm に到達した。ID 指定で削除し、再起動後に 0 個を照合 |

試験の起動ごとに `ASA_PHASE2_FOUNDATION_POC` に `place`、`place-unsaved`、`verify`、`remove`、`verify-empty` のいずれかを指定する。`place-unsaved` は明示保存前の異常終了を再現するための操作。`verify` と `remove` は実際のログの ID を `ASA_PHASE2_FOUNDATION_ID` に設定する。起動設定とログの取り扱いは [Phase 1](phase1.md) と同じ。保存・照合は試験用アクターの範囲。現在の無人生成経路は PoC 05 の耐久・衝突条件を満たさないため、通常建築経路の検証が必要。 [ASA 耐久取得の公開宣言](https://github.com/ArkServerApi/AsaApi/blob/2.11/AsaApi/Core/Public/API/ARK/APrimalTargetableActor.h#L94-L98)

プラグインは `plugin/phase2/Terrain.cpp` が地形・水域、`plugin/phase2/Foundation.cpp` が土台のクラス解決・配置・保存照合を担当し、`plugin/Main.cpp` が起動とブリッジの制御を持つ。

## PoC 08・09 の倉庫在庫試験

同じ ASA 98.9 / build 26749470 と AsaApi 2.11 で、独立した `AltSaveDirectoryName=Phase2Inventory` に小型の収納箱を生成した。インベントリ操作は `plugin/phase2/Inventory.cpp`、試験ワールドの確認・場所・生成処理は `plugin/phase2/TrialSite.cpp` に配置。ローカル起動時の `ASA_PHASE2_INVENTORY_POC` で試験操作を選び、`create` 以外は実機ログの ID を `ASA_PHASE2_INVENTORY_ID` に渡す。試験ワールド、プレイヤー不在、区画、箱の型、ID、操作前数量を照合する。

| 起動ごとの操作 | 実機結果 |
|---|---|
| `create` | 小型収納箱 1 個、構造物 ID 666419875、所有プレイヤー ID 0 |
| `stock` | 空の箱に木材を 7 個追加し、同じスタックを 3 個減量。4 個を読み取って同期保存 |
| 同じ `stock` を再送 | 再起動後、空を要求する事前条件に合わず拒否 |
| `clear` | 再起動後に木材 4 個を読み取り、アイテム ID で削除。0 個を確認して同期保存。所有プレイヤー ID は 0 |
| `verify-empty` | 再起動後、同じ箱が空であることを確認 |
| `capacity` | 木材 1 個を 1 スタックとして 15 スロットを満たした。エンジンは容量上限と判定し、新規スロットを使う石 1 個の受け入れ照会を拒否。作成したスタックを ID 指定で削除し、0 個に戻した |

在庫 API は `InventoryItemsField`、`AddNewItem`、`IncrementItemQuantity`、`RemoveItem`。容量の確認には `GetMaxInventoryItems`、`IsAtMaxInventoryItems`、`AllowAddInventoryItem` を使用。無人環境で生成した箱から所有者フィールドを取得した。在庫変更の途中で異常終了した場合の照合、電力状態、プレイヤーやトライブ間の利用権限は未検証。 [ASA 在庫ヘッダー](https://github.com/ArkServerApi/AsaApi/blob/2.11/AsaApi/Core/Public/API/ARK/UPrimalInventoryComponent.h) [ASA アイテムヘッダー](https://github.com/ArkServerApi/AsaApi/blob/2.11/AsaApi/Core/Public/API/ARK/UPrimalItem.h)

同じ箱で `ASA_PHASE2_INVENTORY_MIRROR=1` と `ASA_PHASE2_INVENTORY_ID=666419875` を設定し、外部ブリッジを `python -m simulator.phase1 --inventory-database <DB> --inventory-id 666419875` で起動した。`stock` 後の木材 4 個を SQLite へ初回記録し、ブリッジだけを再起動して同じ ASA 起動 ID で連番 1 → 2、数量 4 を照合。その後 ASA を再起動して `clear` を実行し、新しい起動 ID の連番 1 で数量 0 を確認した。同期の方向は ASA から外部台帳。生ログは `%LOCALAPPDATA%/ASA-Civilization-Phase1/logs/mirror-stock.log` と `mirror-restart.log`。

## PoC 11 の MOD 導入

2026-11-25 JST、ASA 98.9 / Steam build 26749470 と AsaApi 2.11。専用サーバーの起動引数 `-mods=947835` で Human_NPCs_ASA を取得した。CurseForge file ID 9610763 の Windows Server 配布がインストールされ、`PrimalGameData_BP_Human_NPCs_ASA` がゲームデータとしてロードされた。導入初回の専用サーバー起動は 23.62 秒（ゲームログの Full Startup）。 [作者の配布ファイル](https://www.curseforge.com/ark-survival-ascended/mods/human_npcs_asa/files/9610763)

対象は `?AltSaveDirectoryName=Phase2HumanNPCs` の The Island、接続プレイヤーなし。従来の無改造セーブは SHA-256 一致を確認した。ゲーム付属の Mods キャッシュと試験セーブはリポジトリ外に維持する。導入ログは `%LOCALAPPDATA%/ASA-Civilization-Phase1/logs/human-npcs-install.ShooterGame.log`。

`ASA_PHASE2_HUMAN_NPC_SURVEY=1` で `plugin/phase2/NpcSurvey.cpp` の読み取り専用の観測を有効にする。サーバーの Ready 後に `APrimalCharacter` を列挙し、クラスのパッケージが `/Human_NPCs_ASA/` に属するアクターの数と、最大 5 体の名前・位置を記録する。最後に配布マニフェストに含まれる男女のベースクラスを解決する。 [クラス列挙の公開宣言](https://github.com/ArkServerApi/AsaApi/blob/2.11/AsaApi/Core/Public/API/ARK/UGameplayStatics.h#L84) [パス取得の公開宣言](https://github.com/ArkServerApi/AsaApi/blob/2.11/AsaApi/Core/Public/API/ARK/UObjectBaseUtility.h#L187)

初回試験では Ready 後のおよそ 0・30・90 秒でロード済みキャラクターを 0・15,619・25,186 体観測した。MOD パッケージのキャラクターは 3 回とも 0 体だった。`/Human_NPCs_ASA/Base_Units/` の `ZKs_Base_Man_BP_C` と `ZKs_Base_Female_BP_C` はいずれも ASA 上で `APrimalCharacter` のクラスとして解決できた。

同じ無人ワールドで 0・30・90・180・300 秒に観測する追試を実施。MOD の個体数は 0・0・0・0・6 体。300 秒時点での全キャラクターは 25,669 体。斧・素手の男性型と剣・槍の女性型を (194000, −85000) cm 付近で観測した。素手の男性型は手動生成試験と同一クラス。自然出現の追試では個体を生成・削除していない。

別の新規ワールド `Phase2HumanNPCTrial` で同じ MOD ファイルの `ZKs_Punch_Man_BP_C` を 1 体生成した。生成 3 秒後に AI コントローラーが取得できず、12 秒の観測中に座標は変化しなかった。名前・型・区画を再照合して削除し、2 秒後に 0 体を確認した。使用した名前は同一起動内の試験対象の識別に限定する。 [生成の公開宣言](https://github.com/ArkServerApi/AsaApi/blob/2.11/AsaApi/Core/Public/API/ARK/UWorld.h#L168)

`Phase2HumanNPCController` では `ASA_PHASE2_HUMAN_NPC_TRIAL=1` を設定。既定 AI クラスを照合し、`SpawnDefaultController` の明示呼び出しでコントローラーが付いたことを確認した。12 秒間の座標は一定で、削除後は 0 体。追試 `Phase2HumanNPCMove` では生成前に目的地の地表を確認した。AI 初期化のログ直後にサーバープロセスが終了し、`AAIController.MoveToLocation` の戻り値は得られなかった。終了理由は不明。試験コードからこの移動呼び出しを外し、生成・AI 初期化・削除を再現した。固定ビルドのキャッシュにある ASA の関数シグネチャは公開 UE 宣言より `bool` が一つ多い。 [ASA の既定コントローラー宣言](https://github.com/ArkServerApi/AsaApi/blob/2.11/AsaApi/Core/Public/API/ARK/APawn.h#L64) [UE の移動 API 宣言](https://dev.epicgames.com/documentation/unreal-engine/API/Runtime/AIModule/AAIController/MoveToLocation?application_version=5.8)

## 残る Phase 2 の実機検証

- PoC 04・05・13。クライアントでの目視、通常建築経路での耐久・衝突・資材消費、別区画や未ロード領域、保存の途中で異常終了した場合の照合。外部シミュレーター上では仮想建設を再生し、占有時の予約解除と再起動後に同じ建設を二重計上しないことを確認した。
- PoC 08・09。所有・陣営の切り替えとプレイヤーごとの利用権限、電力状態とクライアント表示、在庫変更途中の復旧。
- PoC 06・07・11。外見、プレイヤー接近時の挙動、外部からの移動指示と安定 ID による再起動後の照合。移動は現状の外部シミュレーターで論理的に扱う。
- PoC 12。無人の既知区画で土台と収納箱を再起動後に観測できた。プレイヤーの接近・離脱に伴う休眠・ロード範囲の変化は未検証。

### クライアント接続後の観測

新規の The Island `Phase2ClientVerification` を使用。バニラへの接続を先に確認し、次に同じセーブで `ASA_PHASE2_CLIENT_TRIAL=1` を指定してプラグインを起動する。`ClientTrial.cpp` は接続人数、試験区画までの最短水平距離、区画内の構造物の件数と最大 8 件の ID・型・耐久・プレイヤー所有の有無を専用サーバーのログに記録する。距離を取得できるキャラクターがいない場合は `unobserved` と記す。 [プレイヤー位置の参照元](https://github.com/ArkServerApi/AsaApi/blob/2.11/AsaApi/Core/Public/API/ARK/AController.h#L16)

接続前、通常建築の直後、退域、再訪、再起動の順にログと画面を突き合わせる。耐久や ID が観測できても、衝突・資材消費・別のプレイヤーの利用権限は各操作で確認する。構造物が列挙されない場合は、その時点の観測不可として記録する。

Linux の仮想環境は Windows の専用サーバーと DLL の検証には不要。Linux へ Python を移せることを確かめる場合に同じテストを実行する。既存の Linux PC、CI、WSL2、仮想マシンはいずれも候補で、この PC に Linux 環境を追加する前提はない。
