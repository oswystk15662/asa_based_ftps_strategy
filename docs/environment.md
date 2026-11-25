# 環境調査と構成比較

2026-11-24 JST。Windows の読み取り専用調査。空き容量・メモリは測定時点の値。ネットワークの個別アドレスと認証情報は記録対象外。

| 項目 | 結果と確認元 |
|---|---|
| OS | Windows 11 Pro 25H2、10.0.26200.9974。CIM と CurrentVersion レジストリ |
| CPU | Intel Core Ultra 9 185H、16 物理コア・22 論理コア。Win32_Processor |
| GPU | GeForce RTX 4070 Laptop GPU、8,188 MiB VRAM（nvidia-smi）。サーバー単体とクライアント同時起動を別々に測る |
| RAM | 32 GiB（16 GiB × 2、5600 MT/s 相当の報告値）。OS 可視 31.67 GiB、調査時の空き 5.27 GiB。CIM |
| ストレージ | Samsung MZVL21T0HDLU-00BT7 SSD、NVMe、物理約 953.9 GiB（1.024 TB）。C: NTFS 933.54 GiB、空き 244.09 GiB。ドライブ文字なしの NTFS 領域 18.90/1.00 GiB、空き各 0.68/0.09 GiB。Storage cmdlet |
| ネットワーク | Wi-Fi 7 対応アダプターが接続、リンク速度 650 Mbps、IPv4/IPv6、IPv4 既定経路あり。Tailscale トンネル稼働、IPv4/IPv6、IPv4 既定経路なし。Bluetooth PAN 切断。物理 LAN の接続と遠隔 PC への到達性は未確認 |
| 仮想化 | Windows ハイパーバイザー検出、VBS 稼働。Win32_Processor の firmware flag は False を返すが、稼働中のハイパーバイザー下で BIOS 設定の断定には使わない |
| Steam / SteamCMD | Steam インストール済み・実行中。SteamCMD は PATH・標準/候補ディレクトリで未検出 |
| ASA クライアント | Steam ログ上 11/09 アンインストール。app 2399830 のマニフェストと実行ファイルを検出せず。旧フォルダーに約 279 MiB の残存ファイルとローカルセーブあり。ローカル ASA 実行版は特定不可 |
| ASA 専用サーバー | app 2430930 のマニフェスト、通常の Steam ライブラリと候補位置、起動プロセスで検出せず。ローカル版は未確認 |
| MOD / AsaApi | 設定の ActiveMods は空、ActiveMapMod=0。ModsUserData の残存は確認したが有効 MOD は確認できず。調査した Win64 ディレクトリにフレームワークやローダーを検出せず |
| Microsoft 開発環境 | VS Community 2022 17.14.37012.4、MSVC 14.44.35207（v143）、Windows SDK 10.0.26100.0。vswhere・ディレクトリ。有効な v145 は未確認 |
| CMake / Ninja / Git | 4.4.3 / 1.13.2 / 2.49.0.windows.1 |
| Python | uv 管理の CPython 3.12.11 / 3.11.16 / 3.10.18 が存在。PATH の python.exe は WindowsApps エイリアス。開発では明示的に uv のインストール済みランタイムを選ぶ |
| WSL2 / Docker | wsl.exe あり。wsl --list --verbose は未導入案内と終了コード 1。ディストリビューション利用不可。Docker CLI、Desktop の標準位置とサービスに検出なし |
| SSH / Tailscale | OpenSSH クライアント 9.5p2。sshd サービスを検出せず。Tailscale 1.104.7、サービス稼働。遠隔ログインや公開設定は調査対象外 |

探索範囲は Steam 登録ライブラリ、PATH、アプリ登録、代表的な候補ディレクトリ。任意のディレクトリに置かれた未登録コピーの有無は未確認。

## 容量見積もり

- Steam 配布メタデータを集計した SteamDB の参考値は Windows・英語・DLC 除外で約 11.47 GiB 展開、8.76 GiB 転送。配布版・マップによって変動するため導入承認時に再照会する。クライアントの Steam 公称要件は SSD に 180 GB（約 168 GiB）以上。過去にこの PC で更新時の空き不足が発生した。 [サーバーのデポ集計](https://steamdb.info/app/2430930/depots/) [ASA Steam ストア](https://store.steampowered.com/app/2399830/ARK_Survival_Ascended/)
- サーバーだけの PoC は 40–60 GiB を確保する計画。内訳の目安は本体 12、更新・検証または退避 12–24、セーブとログ 5–10、ビルド・依存 3–5 GiB、残りは予備。C: の追加物理容量は 0 GiB。
- クライアント同居は下限目安 208–228 GiB（168 + 40–60）。現状との差は 16–36 GiB で、クライアントの DLC・更新作業領域は別途変動。クライアント導入時には実容量を確認し、暫定運用予算を 260–300 GiB とすると現状から約 16–56 GiB の空き確保が必要。追加 SSD の購入は現時点で不要。
- DevKit は初期予算から除外。公式導入ガイドの推奨は SSD に 1.2–1.5 TB の空き。現在の C: との差はおよそ 0.94–1.24 TB。Changelog には容量削減履歴もあるため、導入を検討する場合は選択ビルドの配布サイズと更新領域を Launcher で確認する。 [導入ガイド](https://devkit.studiowildcard.com/getting-started/installing-the-devkit) [Changelog](https://devkit.studiowildcard.com/changelog)

## A / B / C

| 構成 | 互換性・ディスク | RAM・計算負荷 | 遅延・開発効率 |
|---|---|---|---|
| A 同一 Windows | サーバー DLL をネイティブ実行。全同居で暫定 260–300 GiB、サーバー先行は 40–60 GiB | クライアントとサーバーが CPU・メモリ・SSD を共有。実測時空き 5.27 GiB のため、まずクライアントなしで基準測定 | ループバック。単一ホストでデバッグとログ突合が容易 |
| B Windows でゲームとサーバー、Linux で演算 | Windows 側に依然クライアント・サーバーの容量が必要。Linux 側は Python・SQLite・ログ・バックアップ暫定 5–10 GiB | シミュレーター CPU と DB 書込みを移せるが、クライアントとサーバーの競合が残る | LAN RTT・ジッター・切断を実測。認証と二台分の配備が必要 |
| C 三役分離 | クライアント SSD 公称 180 GB 以上＋更新領域。Windows サーバー 40–60 GiB、演算 5–10 GiB の暫定枠 | ゲームの負荷と描画が分離。電源・運用コストが増える | ゲーム通信と橋渡し通信を別計測。再現性維持にはホストごとの版記録が必要 |

推奨は A をサーバー先行で開始。測定で外部演算の競合が大きければ B、描画との競合が支配的なら C を検討する。RAM は OS コミット・ページング・プロセスごとの増分で判定する。別 PC の OS、CPU、RAM、SSD 容量と空き、Python、空きポート、LAN/Tailscale の RTT と接続形態、利用許可は未調査。
