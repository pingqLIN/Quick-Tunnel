# Quick Tunnel Review Share macOS 版

這是 Windows PowerShell 工作流程的 macOS 對應版本。它會建立同樣的過濾
快照，把可能執行的原始碼格式當成不可執行內容提供，且只有在使用者明確
確認後，才開啟有時效限制的 Cloudflare Quick Tunnel。

[English authoritative version](README.md)

## 支援環境

- 使用
  [Homebrew 正式支援的相依套件環境](https://docs.brew.sh/Installation)
  時，需為 macOS 14 Sonoma 以上
- Python 3.9 以上
- `cloudflared`
- 系統內建的 zsh、Terminal、Finder 與 Automator
- 選用：`qrencode`，用於在終端顯示 QR code

[Cloudflare 的 macOS 下載說明](https://developers.cloudflare.com/tunnel/downloads/)
以 Homebrew 作為標準安裝方式：

~~~zsh
brew install python cloudflared
brew install qrencode
~~~

第二行為選用項目。安裝相依套件會變更電腦環境，因此本專案不會自動執行。

## 分享前先驗證

執行完整的本機快照與安全 server 流程，但不建立公開 tunnel：

~~~zsh
python3 ./macos/share-codex-review.py "/path/to/project" \
  --validate-only \
  --no-qr-code
~~~

## 從 Terminal 分享

~~~zsh
python3 ./macos/share-codex-review.py "/path/to/project"
~~~

程式會先顯示公開分享警告，並要求輸入完全相同的 `SHARE`，才會啟動
`cloudflared`。預設時效為 30 分鐘，也可按 Return 提前停止。

常用選項：

| 用途 | 選項 |
| --- | --- |
| 調整時效 | `--duration-minutes 10` |
| 指定本機連接埠 | `--port 8080` |
| 限制複製檔案大小 | `--max-file-size-mb 25` |
| 新增 wildcard 排除規則 | `--additional-exclude "private/*"` |
| 停用 QR code | `--no-qr-code` |
| 略過 `SHARE` 輸入 | `--yes` |
| 調整 retry 次數 | `--quick-tunnel-attempts 3` |
| 調整 retry 基礎等待時間 | `--quick-tunnel-retry-base-seconds 5` |

`--yes` 會略過互動確認並開啟公開端點，只應用在已經核准的工作流程。

## Finder Quick Action

安裝目前使用者專用的 runtime 與 Quick Action：

~~~zsh
/bin/zsh ./macos/manage-finder-quick-action.sh install
~~~

安裝程式會要求輸入完全相同的 `INSTALL`，並把 runtime 複製到：

~~~text
~/Library/Application Support/QuickTunnelReviewShare
~~~

Automator workflow 會安裝到：

~~~text
~/Library/Services/Share to Codex Review.workflow
~~~

在其他 Mac 安裝前，先執行不會修改系統的相容性檢查：

~~~zsh
/bin/zsh ./macos/manage-finder-quick-action.sh doctor
~~~

這項檢查會確認 macOS、Python 3.9 以上版本、必要的系統工具、兩個 workflow
property list 與 Python 進入點。安裝程式會在該 macOS 版本提供 Services
registry 輔助工具時更新並驗證註冊；若這個私有工具不存在或行為已變更，仍
交由 Finder 正常探索，並回報註冊尚未確認，不會把已正確複製的安裝誤判成
損壞。

在 Finder 選取一個資料夾，再選擇 **快速動作 > Share to Codex Review**。
程式會開啟 Terminal 視窗，讓公開警告、URL、retry 診斷、剩餘時效與清理
結果保持可見。

第一次使用時，macOS 可能會詢問是否允許 Finder 控制 Terminal，以及是否
允許 Python 接受區域網路連線。前者供 Finder 啟動 Terminal，後者供僅綁定
loopback 的本機預覽；這些權限都不會略過公開 tunnel 前必須輸入的 `SHARE`。

如果找不到此動作，請前往 **系統設定 > 隱私權與安全性 > 延伸功能 >
Finder** 啟用。[Apple Quick Action 指南](https://support.apple.com/guide/automator/use-quick-action-workflows-aut73234890a/mac)
說明 Finder Quick Action 必須接收檔案型輸入，因此本 workflow 只接受單一
資料夾，遇到檔案或多選時會停止。Finder 沒有與 Windows 資料夾空白處選單
完全相同的 Automator 介面，因此必須先選取資料夾本身再執行。

查看安裝狀態：

~~~zsh
/bin/zsh ./macos/manage-finder-quick-action.sh status
~~~

移除整合：

~~~zsh
/bin/zsh ./macos/manage-finder-quick-action.sh uninstall
~~~

移除時必須輸入完全相同的 `REMOVE`。Workflow 與 runtime 會移到同層的
`.del` 資料夾，並附加時間戳記，保留復原空間。
解除安裝不會重設 macOS 的隱私權決定。如果不再使用此整合，請另外前往
系統設定撤銷 Finder 控制 Terminal 或 Python 區域網路權限。

## 功能對照

| Windows 行為 | macOS 對應方式 | 狀態 |
| --- | --- | --- |
| 建立過濾後的暫存副本 | Python inventory 與 staging directory | 已實作 |
| 排除 VCS、相依套件、憑證與金鑰 | 相同名稱與 wildcard 規則 | 已實作 |
| 防止 reparse point 穿透 | 不跟隨或複製 symlink | 已實作 |
| 高可信度 secret 掃描 | 相同的憑證 pattern 類別 | 已實作 |
| 不可執行的原始碼內容 | 共用 `safe-review-server.py` | 已實作 |
| 僅限 loopback 的本機 origin | 只綁定 `127.0.0.1` | 已實作 |
| 公開前明確確認 | 必須輸入 `SHARE` | 已實作 |
| 隔離的 Quick Tunnel 設定 | 使用暫時性空白 config | 已實作 |
| 暫時性 500/1101 retry | 有上限的指數退避 | 已實作 |
| 429／設定錯誤不 retry | 組合式失敗訊號判斷 | 已實作 |
| 公開 URL 驗證 | 檢查 HTTP 200、content type 與 marker | 已實作 |
| QR code 輸出 | 選用 `qrencode` 整合 | 已實作 |
| Return 或時效結束 | Terminal Return 鍵或 timeout | 已實作 |
| 子程序與暫存檔清理 | 由 `finally` 保證清理 | 已實作 |
| Explorer 右鍵選單 | Finder Automator Quick Action | 已實作等價功能 |
| 安裝／狀態／移除 | 目前使用者專用的 Finder 整合管理器 | 已實作 |

## 安全界線

- 不會直接提供來源資料夾。
- 會排除 symlink、常見 secret 檔案、VCS 資料、相依套件與過大檔案；任何
  server 啟動前，會針對實際 staged bytes 執行 secret 掃描。
- 只會提供隔離後的副本。
- HTML、SVG、JavaScript 與其他可能執行的原始碼，會由共用安全 server
  以不可執行的 `text/plain` 提供。
- 停用瀏覽器快取，並加入嚴格的安全標頭。
- 本機 server 只綁定 `127.0.0.1`。
- Quick Tunnel 未提供身分驗證。程序停止前，任何取得 URL 的人都能存取
  過濾後的快照。
- 公開驗證會從同一台 Mac 發出。VM 或 NAT 政策可能讓這台 Mac 無法連回
  自己的 `trycloudflare.com` URL，即使外部 client 可以正常存取。若
  self-check 出現警告，仍應從預定的外部 client 驗證後再使用該 URL。
- Secret 掃描採保守策略，不能證明資料夾內完全沒有私人資訊。分享前仍應
  人工檢查，並加入專案特有的排除規則。

## 開發驗證

跨平台核心測試：

~~~zsh
python3 -m unittest discover -s macos/tests -v
~~~

在沒有既有 Quick Tunnel 整合的乾淨 macOS 使用者環境，可執行受控的
可重複性檢查。它會跑完 static check、unit test，以及兩輪完整的
安裝、狀態、安裝位元組比對與解除安裝：

~~~zsh
/bin/zsh ./macos/tests/run-repeatability-tests.zsh
~~~

腳本發現既有或不完整安裝時會拒絕覆寫；測試移除的檔案會保留在附有時間戳
的 `.del` 資料夾。通過只代表執行測試的那一台 Mac 可重複，不能當成尚未
測試之 macOS 版本、CPU 架構或受管理裝置政策的證據。

2026-07-19 的原生 VM 證據使用 macOS 15.7.7 x86_64、Python 3.9.6、
`cloudflared` 2026.6.1 與 `qrencode` 4.1.1。外部 host 對過濾後的公開 URL
取得 HTTP 200 與 review marker；QR 產生、自動到期與程序清理都通過。該 VM
受 NAT 路徑限制，無法從 VM 內連回自己的公開 URL，因此同一台 Mac 的
self-check 正確保留為警告，而沒有誤報為已驗證。

在 macOS 另外執行：

~~~zsh
/bin/zsh -n macos/share-codex-review.command
/bin/zsh -n macos/launch-from-finder.sh
/bin/zsh -n macos/manage-finder-quick-action.sh
/bin/zsh -n macos/finder-quick-action-setup.command
plutil -lint \
  "macos/templates/Share to Codex Review.workflow/Contents/Info.plist"
plutil -lint \
  "macos/templates/Share to Codex Review.workflow/Contents/document.wflow"
/bin/zsh -n macos/tests/run-repeatability-tests.zsh
~~~

接著安裝 Quick Action，先從 Finder 執行 `--validate-only` 等級的本機驗證，
確認無誤後才核准真正的公開 tunnel。
