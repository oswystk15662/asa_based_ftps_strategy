# 都市の初期技術と Ragnarok の土地柄

## 初期技術の比較

```sh
python -m benchmarks.compare_city_technologies --ticks 12
```

`configs/city-technology-demo.json` を技術なしと技術ありで実行する。各都市の初期人口は 12 人、在庫は食料 0・木材 12・鉱石 2、資源ノードは 3 種とも容量 12。地図・都市の位置・勢力・巡回順は両方の実行で共通。表示する採集・出荷・到着の数は指定 tick までの累計。必要なら `--scenario` に別のシナリオを渡せる。

`technology` は都市ごとの任意項目。`fishing`、`woodworking`、`mining` は、それぞれ食料・木材・鉱石の担当者あたりの採集上限を 2 倍にする。実際の採集量は資源ノードの残量まで。既存の交易条件で余剰を出荷し、輸送にかかる時間も同じ規則で計算する。

| 都市 | 初期技術 | 得意資源の累計採集 | tick 12 までに到着した輸出 |
|---|---|---:|---|
| Coast | 漁労 | 食料 25 → 45 | Forest に食料 1 |
| Forest | 木工 | 木材 16 → 32 | Coast に木材 1 |
| Mine | 採鉱 | 鉱石 19 → 38 | Coast に鉱石 2 |

技術なしでは出荷・到着ともに 0。技術ありでは Forest から Mine に出荷した木材 4 が、tick 12 時点で輸送中。実験は外部シミュレーターの合成地形で行う。

## Ragnarok Ascended の土地柄案

砂漠の内陸に置く町と、世界開始時の交易は [世界の開始時代とプレイヤーの選択](world_start.md) を参照。

Studio Wildcard が紹介する Ragnarok Ascended の地形をもとにした、このプロジェクト向けの技術・産業案。公式のエングラム一覧や配置座標は、今後 ASA 側で照合する。 [Studio Wildcard のリリース告知](https://survivetheark.com/index.php?/forums/topic/772489-ragnarok-ascended-and-lost-colony-expansion-pass-are-now-live/) [Steam の公式マップ紹介](https://store.steampowered.com/app/3675020/ARK_Ragnarok_Ascended/)

| 地域・地形 | 初期技術・技能案 | 生産・交易を変える効果案 |
|---|---|---|
| Viking Bay の湾岸 | 魚の燻製 | 保存食を内陸へ供給。燃料の木材を輸入する |
| Viking Bay の崖上 | 崖道整備 | 斜面の運搬時間を短縮。湾岸と高台を結ぶ中継地になる |
| Highlands の高原 | 放牧 | 草地から食料と皮を生産。木材や金属工具を購入する |
| Scotland Isles の大草原 | 荷役獣の調教 | 陸路の一便あたり輸送量を増やす。荷役や家畜を周辺へ供給する |
| Alpines の松林 | 製材 | 建築材や橋材を作り、鉱山や湿地の工事へ供給する |
| Alpines の河川沿い | 水車 | 穀物加工の労働を減らす。工具と木材の補修が必要になる |
| Alpines に隣接する湿地 | 高床建築 | 冠水しやすい区画でも倉庫と中継所を維持しやすい。梁材を輸入する |
| Redwoods の巨木林 | 樹上建築 | 樹上倉庫を開放し、地上の障害に強い中継拠点を作る |
| Redwoods の沿岸断崖 | 荷揚げ機 | 海岸から高台に移す荷量を増やす。縄と金具を必要とする |
| Desert Isles の乾燥地 | 貯水・点滴灌漑 | 同じ水量で畑を維持し、余った水を隊商へ供給する |
| Murder Murder Snow の極寒地 | 防寒縫製 | 冬季の作業停止を減らし、防寒具を山間の拠点へ輸出する |
| 氷河洞窟の周辺 | 氷室 | 食料の腐敗を遅らせる。湾岸の漁獲を遠方へ送りやすくする |
| Dragon’s Reach の岩峰 | 岩盤採鉱 | 鉱石を供給し、食料と燃料は周辺都市から仕入れる |
| 遺跡周辺 | 古代工法の復元 | 石材を使う建築の修繕費を下げる。石工を他都市に派遣できる |
