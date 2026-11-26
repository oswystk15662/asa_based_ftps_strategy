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

試験の起動ごとに `ASA_PHASE2_FOUNDATION_POC` に `place`、`place-unsaved`、`verify`、`remove`、`verify-empty` のいずれかを指定する。`place-unsaved` は明示保存前の異常終了を再現するための操作。`verify` と `remove` は実際のログの ID を `ASA_PHASE2_FOUNDATION_ID` に設定する。起動設定とログの取り扱いは [Phase 1](phase1.md) と同じ。保存・照合は試験用アクターの範囲。上表で使った getter は通常建築した土台でも 0 を返したため、後続試験では耐久フィールドを直接読み取った。 [ASA 耐久取得の公開宣言](https://github.com/ArkServerApi/AsaApi/blob/2.11/AsaApi/Core/Public/API/ARK/APrimalTargetableActor.h#L94-L98)

2026-11-26 JST、同じ固定ビルド・MOD なしの新規試験セーブで耐久の観測を `HealthField()` と `MaxHealthField()` に変更して再計測した。非接続時に土台を 1 個生成し、ID `1286338937`、耐久 15,000／15,000、所有プレイヤー ID 0 を確認した。同じ ID・耐久・所有状態を保存後の再起動でも読み取れた。中央の Visibility トレースは `LandscapeStreamingProxy`（Z −14421.93 cm）まで到達し、土台に当たらなかった。マップ外の照会は `unobserved`。歩行時の衝突は別途確認が必要。 [ASA 耐久フィールドの公開宣言](https://github.com/ArkServerApi/AsaApi/blob/2.11/AsaApi/Core/Public/API/ARK/APrimalTargetableActor.h#L27-L29)

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

2026-11-26 JST の異常終了試験では、新規の `Phase2Inventory` を用意し、`stock-unsaved` で空の箱に木材 7 個を追加した。減量と明示的な `SaveWorld` を行う前に、SQLite で 7 個を観測して検証サーバープロセスを強制終了した。最初の試行では再起動後も同じ箱に 7 個が残った。空を前提とする確認は拒否され、台帳には新しい起動 ID と 7 個が記録された。この試行では明示保存の有無だけでゲーム側の永続化は判断できなかった。

別の新規セーブで同じ異常終了を再現した。箱 ID `1687928449` は再起動後も木材 7 個を保持し、空を要求する `stock` の再実行が拒否された。外部 SQLite を維持したまま、箱を作成した直後の空のワールドバックアップに戻した。同じ箱 ID から木材 0 個を読み取り、SQLite が新しい起動 ID の観測に追従した。旧起動 ID の hello を実ブリッジに送ると HTTP 409 となり、現在の台帳は 0 個のままだった。その後の `stock` で 4 個を記録し、さらに再起動しても同じ箱と台帳の数量は 4 個だった。生ログは `%LOCALAPPDATA%/ASA-Civilization-Phase1/logs/phase2-followup-20261126-130525/`。

同日の外部ブリッジ単体試験では、SQLite の書き込みロック中に在庫観測が HTTP 503 となり、連番 0 と空の台帳を維持した。ロック解除後に同じ観測を 2 回送ると、連番 1 と木材 4 個が 1 件だけ記録された。

## PoC 11 の MOD 導入

2026-11-25 JST、ASA 98.9 / Steam build 26749470 と AsaApi 2.11。専用サーバーの起動引数 `-mods=947835` で Human_NPCs_ASA を取得した。CurseForge file ID 9610763 の Windows Server 配布がインストールされ、`PrimalGameData_BP_Human_NPCs_ASA` がゲームデータとしてロードされた。導入初回の専用サーバー起動は 23.62 秒（ゲームログの Full Startup）。 [作者の配布ファイル](https://www.curseforge.com/ark-survival-ascended/mods/human_npcs_asa/files/9610763)

対象は `?AltSaveDirectoryName=Phase2HumanNPCs` の The Island、接続プレイヤーなし。従来の無改造セーブは SHA-256 一致を確認した。ゲーム付属の Mods キャッシュと試験セーブはリポジトリ外に維持する。導入ログは `%LOCALAPPDATA%/ASA-Civilization-Phase1/logs/human-npcs-install.ShooterGame.log`。

`ASA_PHASE2_HUMAN_NPC_SURVEY=1` で `plugin/phase2/NpcSurvey.cpp` の読み取り専用の観測を有効にする。サーバーの Ready 後に `APrimalCharacter` を列挙し、クラスのパッケージが `/Human_NPCs_ASA/` に属するアクターの数と、最大 5 体の名前・位置を記録する。最後に配布マニフェストに含まれる男女のベースクラスを解決する。 [クラス列挙の公開宣言](https://github.com/ArkServerApi/AsaApi/blob/2.11/AsaApi/Core/Public/API/ARK/UGameplayStatics.h#L84) [パス取得の公開宣言](https://github.com/ArkServerApi/AsaApi/blob/2.11/AsaApi/Core/Public/API/ARK/UObjectBaseUtility.h#L187)

初回試験では Ready 後のおよそ 0・30・90 秒でロード済みキャラクターを 0・15,619・25,186 体観測した。MOD パッケージのキャラクターは 3 回とも 0 体だった。`/Human_NPCs_ASA/Base_Units/` の `ZKs_Base_Man_BP_C` と `ZKs_Base_Female_BP_C` はいずれも ASA 上で `APrimalCharacter` のクラスとして解決できた。

同じ無人ワールドで 0・30・90・180・300 秒に観測する追試を実施。MOD の個体数は 0・0・0・0・6 体。300 秒時点での全キャラクターは 25,669 体。斧・素手の男性型と剣・槍の女性型を (194000, −85000) cm 付近で観測した。素手の男性型は手動生成試験と同一クラス。自然出現の追試では個体を生成・削除していない。

別の新規ワールド `Phase2HumanNPCTrial` で同じ MOD ファイルの `ZKs_Punch_Man_BP_C` を 1 体生成した。生成 3 秒後に AI コントローラーが取得できず、12 秒の観測中に座標は変化しなかった。名前・型・区画を再照合して削除し、2 秒後に 0 体を確認した。使用した名前は同一起動内の試験対象の識別に限定する。 [生成の公開宣言](https://github.com/ArkServerApi/AsaApi/blob/2.11/AsaApi/Core/Public/API/ARK/UWorld.h#L168)

`Phase2HumanNPCController` では `ASA_PHASE2_HUMAN_NPC_TRIAL=1` を設定。既定 AI クラスを照合し、`SpawnDefaultController` の明示呼び出しでコントローラーが付いたことを確認した。12 秒間の座標は一定で、削除後は 0 体。追試 `Phase2HumanNPCMove` では生成前に目的地の地表を確認した。AI 初期化のログ直後にサーバープロセスが終了し、`AAIController.MoveToLocation` の戻り値は得られなかった。終了理由は不明。試験コードからこの移動呼び出しを外し、生成・AI 初期化・削除を再現した。固定ビルドのキャッシュにある ASA の関数シグネチャは公開 UE 宣言より `bool` が一つ多い。 [ASA の既定コントローラー宣言](https://github.com/ArkServerApi/AsaApi/blob/2.11/AsaApi/Core/Public/API/ARK/APawn.h#L64) [UE の移動 API 宣言](https://dev.epicgames.com/documentation/unreal-engine/API/Runtime/AIModule/AAIController/MoveToLocation?application_version=5.8)

2026-11-26 JST、同じ ASA 98.9 / build 26749470・AsaApi 2.11（`bd376a0422291b0b1bf15a0b7868e7e275605da9`）・Human_NPCs_ASA の Windows Server file ID 9610763 で、無人の新規 `Phase2HumanNPCPersistence` を使用した。`ASA_PHASE2_HUMAN_NPC_PERSISTENCE=save` で素手の男性型を 1 体生成し、`DinoID1` と `DinoID2` を連結した非ゼロ ID `1088778715205065493` を取得してから同期保存した。検証サーバーを停止し、同じ環境変数に ID を指定して再起動すると、ロード済みの同型 1 体がその ID と試験区画に一致した。再起動後の照合には起動時のアクター名を使用しない。外部からの移動と、別区画へ移動した個体の追跡は未確認。 [ASA の個体 ID フィールド](https://github.com/ArkServerApi/AsaApi/blob/2.11/AsaApi/Core/Public/API/ARK/APrimalDinoCharacter.h#L199-L200)

### ローカル起動からの NPC 移動指示

2026-11-26 JST、同じ固定サーバーと MOD 版で、新規の無人ワールド `Phase2HumanNPCReflectedMove` を使った。ローカル起動時に `ASA_PHASE2_HUMAN_NPC_TRIAL=move` を指定し、試験用の素手の男性型 1 体を生成。AI コントローラーを取得できない場合は対象の休眠を解除し、移動先は試験区画内の乾いた地面から選んだ。UE のリフレクションで `MoveToLocation` の引数を設定し、ゲームスレッドで実行した。外部シミュレーターの HTTP ブリッジには読み取り専用の契約を使った。 [UE の移動 API 宣言](https://dev.epicgames.com/documentation/unreal-engine/API/Runtime/AIModule/AAIController/MoveToLocation?application_version=5.8)

最初の試行は AI コントローラーを取得できず、その次は地表の事前検査に通らず、移動要求を送らずに停止した。移動先候補を区画内の 3 m 先の 4 点にした試行では、要求を受理したことを示す `2` が返り、NPC の座標が変化した。12 秒後の水平距離は目的地から 255.45 cm で、設定した許容半径は 80 cm。試験用 NPC の削除後に残存 0 体を確認した。 [UE の移動要求の戻り値](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/PathFollowingRequestResult?application_version=5.4)

新規ワールドを再作成し、同じ 3 m の移動要求を 250 ms 間隔で追試した。要求は再び受理され、最初の約 3 秒の観測で目的地の水平 22.76 cm まで接近した。約 12 秒後は 886.93 cm まで離れたため、到着後の停止は成立しなかった。離れた原因、障害物がある経路、到達不能時の報告は未確認。試験用 NPC を削除して 0 体を確認し、サーバーを終了した。生ログは `%LOCALAPPDATA%/ASA-Civilization-Phase1/logs/phase2-followup-20261126-141721/` と `phase2-followup-20261126-141932/`。

### 平坦な区画での停止と到達不能な目標

2026-11-26 JST、同じ固定ビルドと Human_NPCs_ASA file ID 9610763 で、野生環境の使い捨て `Phase2HumanNPCReflectedMove` を試行ごとに新規作成した。試験区画 `(107449, 211985)` cm と周囲の乾いた地表を使い、NPC の型、管理用の名前、非ゼロの個体 ID、区画内にいることを照合した。

- `ASA_PHASE2_HUMAN_NPC_TRIAL=move-stop`。水平 80 cm を停止指示の発行条件とした。最初の試行ではネイティブの経路状態照会と停止を組み合わせた箇所で、専用サーバーだけが `EXCEPTION_ACCESS_VIOLATION` で終了した。どちらの呼び出しで終了したかは未確定。再試行では UE のリフレクションを使い、目標から 46.08 cm で `StopMovement` が戻ることを確認した。観測終了時の水平距離は 1,527.67 cm。停止指示を一度発行しても、その後の位置は維持されなかった。 [UE の停止 API](https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Runtime/AIModule/AAIController/StopMovement?application_version=5.5)
- `ASA_PHASE2_HUMAN_NPC_TRIAL=move-unreachable`。地表から 100 m 上に目標を指定し、ナビゲーションへの投影を有効にして部分経路を無効にした。`MoveToLocation` の戻り値は `2` だった。終了時の高さの差は 98.91 m で、元の指定点には到達しなかった。この試験では地上の障害物で完全に経路をふさいだケースは扱っていない。
- `ASA_PHASE2_HUMAN_NPC_TRIAL=move-unprojected`。同じ空中目標への投影を無効にしても `2` が返った。最後に取得できた座標は目標より 99.18 m 低く、その後は管理区画の照合で試験を中断した。試験サーバーを停止し、この試行のワールドを別名で保管した。生ログは `%LOCALAPPDATA%/ASA-Civilization-Phase1/logs/phase2-followup-20261126-144052/`。

停止試験の再試行と投影を有効にした単体試験では、NPC を削除して残存 0 体を確認した。Windows は再起動せず、既存セーブの SHA-256 は一致した。生ログは `%LOCALAPPDATA%/ASA-Civilization-Phase1/logs/phase2-followup-20261126-143256/` と `phase2-followup-20261126-143511/`。

`ASA_PHASE2_HUMAN_NPC_TRIAL=move-pair` では、同じ無人サーバーで管理 NPC を 2 体生成した。最初の候補は斜度が 5° を超えたため、既に測定済みの平坦な区画の西側へスポーン位置を移した。再試行では別々の個体 ID を照合し、1 回のゲームスレッド処理で、一方に地上の目標、もう一方に地上 100 m の目標を指定した。両者の要求が受理され、指定した X・Y への最接近はそれぞれ 17.43 cm と 29.98 cm。空中目標の高さへの到達はこの同時試験では判定していない。終了後は両方を削除し、0 体を確認した。生ログは `%LOCALAPPDATA%/ASA-Civilization-Phase1/logs/phase2-followup-20261126-144052/`。 [ASA の関数検索](https://github.com/ArkServerApi/AsaApi/blob/2.11/AsaApi/Core/Public/API/ARK/UClass.h#L70) [ASA の ProcessEvent 宣言](https://github.com/ArkServerApi/AsaApi/blob/2.11/AsaApi/Core/Public/API/ARK/UObject.h#L68)

## 残る Phase 2 の実機検証

- PoC 04・05・13。通常建築の原料消費と設置後の歩行・衝突、無人生成した土台のクライアント表示、別区画や未ロード領域、保存の途中で異常終了した場合の照合が残る。通常 UI で設置した木の土台の表示・建築アイテム消費・再起動後の残存は確認した。外部シミュレーター上では仮想建設を再生し、占有時の予約解除と再起動後に同じ建設を二重計上しないことを確認した。
- PoC 08・09。所有・陣営の切り替え、独立したアカウントの同時接続とトライブ間の権限、電力設備と文明シミュレーターの接続が残る。別サバイバーを順に接続した施錠済みの箱の操作、倉庫の一部変更後の復旧、発電機 1 台・照明 1 台の給電は確認した。
- PoC 06・07・11。外見とプレイヤー接近時の挙動、到着後の停止維持、地上の経路がふさがれた場合、外部シミュレーターからの移動指示、別区画へ移動した個体の追跡が残る。試験では一時的に目標へ到達し、リフレクション経由の停止要求も戻った。空中の到達不能な目標にも要求受理が返るため、完了判定には元の目標座標との照合が必要。
- PoC 12。ハイバネーションを有効にした試験で、遠隔の土台が列挙できなくなり、接近時に同じ ID で復帰することを確認した。全構造物タイプ・区画での条件と遠隔での更新は未確認。

## 外部シミュレーターの再起動照合

2026-11-26 JST、Windows と Python 3.12.11 で `estuary-demo.json` と `established-world-demo.json` を各 128 tick 実行。33、66、98 tick の完了後に詳細更新対象を変更した。連続実行の状態とイベント列を、途中で SQLite を閉じて開き直した実行と比較した。両方とも完全に一致し、同じ建設コマンド ID の二重確定はなかった。これは外部シミュレーターでの結果。

| シナリオ | イベント | 建設確定 | 発送 | 到着 |
|---|---:|---:|---:|---:|
| 河口の集落 | 1,546 | 3 | 74 | 71 |
| 既存都市 | 1,901 | 1 | 106 | 102 |

河口の集落では別途、tick 4 のイベント挿入時に Python 子プロセスを強制終了した。再起動すると状態とイベントは tick 3 まで戻り、そのまま tick 32 まで再生した状態と全 514 イベントが連続実行と一致した。

## クライアント接続後の観測

新規の The Island `Phase2ClientVerification` を使用。バニラへの接続を先に確認し、次に同じセーブで `ASA_PHASE2_CLIENT_TRIAL=1` を指定してプラグインを起動する。`ClientTrial.cpp` は接続人数、試験区画までの最短水平距離、区画内の構造物の件数と最大 8 件の ID・型・耐久・プレイヤー所有の有無を専用サーバーのログに記録する。距離を取得できるキャラクターがいない場合は `unobserved` と記す。 [プレイヤー位置の参照元](https://github.com/ArkServerApi/AsaApi/blob/2.11/AsaApi/Core/Public/API/ARK/AController.h#L16)

接続前、通常建築の直後、退域、再訪、再起動の順にログと画面を突き合わせる。耐久や ID が観測できても、衝突・資材消費・別のプレイヤーの利用権限は各操作で確認する。構造物が列挙されない場合は、その時点の観測不可として記録する。

2026-11-26 JST の実機試験では、ASA 98.9 のバニラ専用サーバーが 16.11 秒で起動し、UDP 17777 が `127.0.0.1` のみにバインドされた。Steam クライアント build 26821536 は 11:51:04 に `ArkAscended_BE.exe` として起動した。指定引数には `-NoBattlEye` が含まれていた。Windows のダンプ時刻は 11:51:22 で、停止コードは `0x139`（第1引数 `3`）。クライアント接続は未確認。この回は AsaApi と MOD をロードしていない。再起動後に検証プロセスは残っておらず、既存セーブの SHA-256 は一致した。 [Microsoft のバグチェック解説](https://learn.microsoft.com/en-us/windows-hardware/drivers/debugger/bug-check-0x139--kernel-security-check-failure)

ユーザーがローカルにコピーしたダンプを Windows の DbgEng で解析し、停止時のカーネルスタックに BattlEye の `BEDaisy.sys` を確認した。実行ファイルとスタックが BattlEye 経路で一致するため、再試験前に調べる第一候補とする。メモリ破損が起きた箇所までは特定できていない。Steam のローカル起動設定には非公式サーバー向けの BattlEye なし起動項目があり、再試験では選択した起動モードと実行ファイルを照合する。調査中はクライアントとサーバーを起動していない。 [BattlEye のドライバー名の公開資料](https://www.battleye.com/support/faq/)

同日 12:24 JST に Steam の BattlEye なし起動項目を選び、クライアント単体を試験した。Steam ログ上の実行ファイルは `ArkAscended.exe`、画面表示は ASA 98.15（CL 842240）。タイトル画面からメインメニューに進み、起動約 69 秒後に終了コード 0 で終了した。試験中に Windows の起動時刻は変わらなかった。Steam の起動項目は試験前の設定に戻した。専用サーバーとの同時起動と接続は未確認。

同日 12:31 JST から、Windows のデスクトップ 1 で BattlEye なしの ASA 98.15 クライアントと ASA 98.9（サーバー build 26749470）のバニラ専用サーバーを同時起動した。サーバーのゲーム用 UDP 17777 が `127.0.0.1` に限ってバインドされることを起動ごとに確認した。最初のサーバープロセスは `EXCEPTION_ACCESS_VIOLATION` で終了し、コンソール起動オプションを外して再起動すると正常起動した。クライアントの直結はパスワード付き構成で認証拒否を受け、ループバック限定でパスワードを空にした試行では接続処理中にコミット余裕が約 1.2 GiB まで低下したため試験クライアントを停止した。Windows の起動時刻に変化はなかった。

メモリ条件を変えた追試として、先の独立ワールドを退避し、同じ試験名で新規ワールドを作成した。`DinoCountMultiplier=0.001` を使用したところ、クライアント起動前のサーバーのプライベートメモリは約 10.0 GiB から約 8.0 GiB に下がった。両値は各試行の起動後の点測定。

同日 12:43–12:53 JST に SOLIDWORKS と Fusion を閉じた状態で、野生生物を抑えた検証ワールドを使用した。Steam 版クライアント ASA 98.15（build 26821536、CL 842240）をデスクトップ 1 で BattlEye なしの `ArkAscended.exe` として起動した。ASA 98.9（build 26749470）のバニラ専用サーバーで接続パスワードを空にし、`open 127.0.0.1:17777` で接続した。The Island でキャラクターを作成し、南部エリア 1 から地上に入れた。同時起動中のコミット余裕は約 7.9 GiB 以上（3 秒間隔の計測）。Windows の起動時刻は変わらなかった。パスワード付きの直結は 12:31 の試行で認証拒否を受けており、成功する入力方法は未確認。

同じセーブを AsaApi 2.11（`bd376a0422291b0b1bf15a0b7868e7e275605da9`）と観測プラグインで起動すると、同じキャラクターで地上へ再接続でき、ログの接続人数は 0 から 1 に変わった。MOD は 0 件。試験用アイテムは管理コマンドで支給し、設置は通常のホットバー操作で行った。障害物がある位置では設置できず、空いた位置では木の土台 1 個を消費した。区画内の土台は `Floor_Wood_SM_New_C`、ID `1952552443`、プレイヤー所有として記録された。ゲーム画面では耐久 15,000／15,000 を確認した。`GetHealth()` と `GetMaxHealth()` を使ったサーバーログは 0／0 だった。保存後に再起動すると接続者 0 人で同じ ID が観測され、再接続した画面でも土台と耐久表示を確認した。

観測を `APrimalTargetableActor::HealthField()` と `MaxHealthField()` に変更し、Windows 用 Release DLL を再ビルドして同じセーブを起動した。接続者 0 人で同じ土台 ID の耐久が 15,000／15,000 と記録され、再起動前に確認したゲーム画面と一致した。 [ASA 耐久フィールドの公開宣言](https://github.com/ArkServerApi/AsaApi/blob/2.11/AsaApi/Core/Public/API/ARK/APrimalTargetableActor.h#L27-L29)

同日 13:00 JST に、新規 `Phase2GameSmoke` で MOD なしのバニラ専用サーバーを再確認した。`Full Startup` は 14.21 秒で、ゲーム用 UDP 17777 は `127.0.0.1` のみ。今回はサーバー単体で起動し、ワールド入場・通常建築は上記のクライアント試験の結果を使用した。

### 遠隔観測と給電

同日 13:32 JST から、検証セーブを複製して ASA 98.15 の BattlEye なしクライアントと ASA 98.9 の専用サーバーをデスクトップ 1 で使用した。野生生物は `DinoCountMultiplier=0.001` に抑えた。試験区画から水平 1.21 m、887.38 m、1.21 m の順で移動し、木の土台 ID `1952552443` をサーバーで読み取った。3 地点とも同じ ID、耐久 15,000／15,000 で、再訪時はクライアントにも表示された。退域後に `LastStructureStasisTime` の表示値が変わり、再訪後もその値を観測した。この回のサーバーログでは `StructureHibernation=OFF` だった。休眠時刻とアクター列挙を別々に扱い、遠隔区画での生成・更新は行っていない。 [ASA の休眠時刻フィールド](https://github.com/ArkServerApi/AsaApi/blob/2.11/AsaApi/Core/Public/API/ARK/APrimalStructure.h#L120)

同じ複製ワールドに発電機と照明を通常の建築操作で設置した。発電機は燃料なしと表示され、ガソリン 1 個を入れると起動できた。照明を点灯させ、検証ワールドの時刻を夜にして周囲が照らされることを確認した。照明を操作せずに発電機だけを停止すると、同じ照明が消灯した。

プラグインを更新してサーバーを再起動し、同じ照明 ID `25992525` を再観測した。再起動後の停止中、発電機の起動後、再停止後で `APrimalStructureItemContainer::bIsPowered` が `false → true → false` と変化した。木の土台では給電値を `unobserved` とした。観測値は検証サーバーのログに記録した。生ログは `%LOCALAPPDATA%/ASA-Civilization-Phase1/phase2-client-followup-remote/`。 [ASA の給電状態フィールド](https://github.com/ArkServerApi/AsaApi/blob/2.11/AsaApi/Core/Public/API/ARK/APrimalStructureItemContainer.h#L166)

### 構造物が列挙できない状態

2026-11-26 JST、検証セーブを再度複製し、固定サーバー実行ファイルに含まれる起動引数候補 `-structurehibernation` を指定した。ASA 98.9 / build 26749470、AsaApi 2.11（`bd376a0422291b0b1bf15a0b7868e7e275605da9`）、MOD なし。起動ログの `Param=1 Manager=1` と、構造物 2 件がハイバネーションに入ることを確認した。土台 ID `1952552443` は起動時の処理前に列挙でき、処理後に一覧から消えた。プレイヤーが試験区画の約 1.21 m に接続すると同じ ID・耐久で再び列挙できた。同一起動で 887.38 m へ退域した試行では休眠時刻が更新されたが、土台は一覧に残った。

別の起動でも、試験区画から約 2.13 km 離れたサバイバーが接続している間は同じ土台を列挙できなかった。試験区画に近づくと再び同じ ID を読み取れた。区画内の収納箱は遠隔のまま列挙できた。列挙の可否は、距離に加えて構造物ごとの状態と起動時の処理に左右された。

### 所有者と別サバイバーの収納箱アクセス

同じ複製ワールドで `ForceAllStructureLocking=True` を設定した。所有者が小型収納箱 ID `1071692263` を設置し、「施錠」の表示がある状態でインベントリを開いて木材 1 個を入れた。所有者の試験用プロフィールを退避してサーバーを再起動し、同じ Steam アカウントで別サバイバーを作成した。試験位置へ移動した後、切断して管理操作を有効にせず再接続した。同じ箱のインベントリは通常の使用・インベントリ操作で開かなかった。プラグインは箱の所有者と接続中のサバイバーの一致を `owner_connected=true → false` と記録した。独立したアカウントの同時利用とトライブ権限は未確認。生ログは `%LOCALAPPDATA%/ASA-Civilization-Phase1/phase2-client-visibility-permissions/`。

サーバー上に複数配置した管理 NPC は、移動や衝突の試験に使える。ASA のクライアント認証とトライブ権限の試験には、それぞれログイン済みのプレイヤーが必要。UE の `SpawnPlayerController` はコントローラーを生成する処理で、固有 ID と接続を確立するログイン処理は別にある。 [UE のプレイヤーログイン](https://dev.epicgames.com/documentation/unreal-engine/API/Runtime/Engine/AGameModeBase/Login)

Linux の仮想環境は Windows の専用サーバーと DLL の検証には不要。Linux へ Python を移せることを確かめる場合に同じテストを実行する。既存の Linux PC、CI、WSL2、仮想マシンはいずれも候補で、この PC に Linux 環境を追加する前提はない。
