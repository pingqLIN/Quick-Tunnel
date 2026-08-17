# Quick Tunnel Review Share

將電腦上的指定資料夾先在本機依規則進行篩選，並檢查可能含有的敏感內容，產生隔離的暫存快照；再透過 Cloudflare Quick Tunnel 在有限時間內公開，供程式碼審查使用。原始資料夾不會直接由 HTTP 伺服器對外提供。

[English version](README.md)

![Quick-Tunnel 鼴鼠吉祥物在私有的 Mole HQ 中，引導審查膠囊穿越發光的暫時審查通道。](docs/assets/readme/quick-tunnel-review-share-mole-mascot-banner.jpg)

> 先在本機篩選，確認內容後再分享；只在需要的時間內開放審查。

[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)](#系統需求)
[![License MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Event schema v1](https://img.shields.io/badge/Event%20schema-v1-65a30d)](docs/THREAT_MODEL.zh-tw.md#機器可讀輸出)

---

## 目錄

- [專案狀態](#專案狀態)
- [系統需求](#系統需求)
- [Cloudflare / cloudflared 安裝與使用](#cloudflare--cloudflared-安裝與使用)
- [受保護存取](#受保護存取)
- [分享前注意事項](#分享前注意事項)
- [快速開始](#快速開始)
- [使用方式](#使用方式)
  - [Windows](#windows)
  - [macOS](#macos)
- [桌面整合](#桌面整合)
  - [Windows 檔案總管右鍵選單](#windows-檔案總管右鍵選單)
  - [macOS Finder Quick Action](#macos-finder-quick-action)
- [機器可讀的生命週期事件](#機器可讀的生命週期事件)
- [安全模型](#安全模型)
- [Quick Tunnel 生命週期](#quick-tunnel-生命週期)
- [開發驗證](#開發驗證)
- [文件索引](#文件索引)
- [授權](#授權)

---

## 專案狀態

目前尚未發布任何標籤版本（tagged release）。在第一個正式版本發布前，以 `main` 分支的最新提交作為目前的支援基準。

準備發布或分享候選版本前，請先確認實際使用的修訂版本，以及 GitHub Actions 的檢查結果。

---

## 系統需求

| 元件 | 文件宣告支援 | 程式實際檢查 | 已測試環境 |
| --- | --- | --- | --- |
| Windows | PowerShell 7；Python 3.9 以上 | `#requires` 與執行期 Python 檢查 | 2026-07-19：PowerShell 7.6.3、Python 3.14.6 |
| macOS | macOS 14 以上；依 Homebrew 預設安裝路徑；Python 3.9 以上 | 包裝程式與 Finder `doctor` 會檢查 Python 3.9 以上 | 2026-07-19：macOS 15.7.7 x86_64、Python 3.9.6 |
| `cloudflared` | 仍在 Cloudflare 一年支援週期內的版本 | 確認執行檔存在；Finder `doctor` 也會回報版本 | macOS VM：2026.6.1；Windows：2026.7.1 |
| `qrencode` | 選用 | 不強制要求 | macOS VM：4.1.1 |

`cloudflared` 必須能透過 `PATH` 直接執行，並建議維持在 Cloudflare 仍提供支援的版本。

若使用 Finder Quick Action，系統還需要內建的 zsh、Terminal、Finder、Automator、AppleScript 與 `plutil`。

Finder Quick Action 的安裝方式、功能對照與驗證說明，請參閱 [macOS 指南](macos/README.zh-tw.md)。

---

## Cloudflare / cloudflared 安裝與使用

Quick Tunnel 透過 Cloudflare 的 `cloudflared` 用戶端，將本機提供審查內容的 HTTP 伺服器連接到 Cloudflare。

本專案預設使用 **Quick Tunnels / TryCloudflare**：`cloudflared` 會建立一個隨機的 `*.trycloudflare.com` 網址，再將該網址收到的流量轉送至本機 HTTP 伺服器。使用這個模式時，不需要事先將自己的網域加入 Cloudflare DNS。

Cloudflare 官方資料：

- [`cloudflared` 下載與安裝](https://developers.cloudflare.com/tunnel/downloads/)
- [Quick Tunnels / TryCloudflare](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/)
- [建立受管理的 Cloudflare Tunnel](https://developers.cloudflare.com/tunnel/setup/)

### 安裝 `cloudflared`

**Windows（PowerShell）**

Cloudflare 官方下載頁同時提供 Windows 可執行檔與 MSI 安裝程式。若偏好使用命令列安裝，可透過 Windows Package Manager 安裝已發布的 `Cloudflare.cloudflared` 套件：

```powershell
winget install --id Cloudflare.cloudflared --exact --source winget
cloudflared --version
```

如果系統沒有 WinGet，或 WinGet 提供的套件版本落後於 Cloudflare 最新版本，請改用上方 Cloudflare 官方下載頁提供的 MSI 或執行檔。

Cloudflare 也特別註明，Windows 版 `cloudflared` 不會自動更新，因此需要自行維護版本。

**macOS**

```zsh
brew install cloudflared
cloudflared --version
```

Cloudflare 官方文件以 Homebrew 作為 macOS 的標準安裝方式。

### 最小化 Quick Tunnel 手動測試

如果本機已有 Web server 在 `8080` 連接埠運作，可使用 Cloudflare 官方文件中的最小測試方式：

```text
cloudflared tunnel --url http://localhost:8080
```

`cloudflared` 會輸出一個暫時性的 `https://<random>.trycloudflare.com` 公開網址。

Quick Tunnel 的定位是測試與開發用途。Cloudflare 目前限制最多 200 個同時處理中的請求，且不支援 Server-Sent Events（SSE）。

如果來源端應用程式沒有自行加入驗證層，Quick Tunnel 產生的網址本身就是公開、且不需要身分驗證的端點。

---

## 受保護存取

本專案採用的 Quick Tunnel 模式本身**沒有身分驗證**，也不提供共用密碼功能。

只要通道仍在運作，任何取得暫時網址的人都能存取已發布的快照。

如果需要存取控制，請改用 **Managed Cloudflare Tunnel + Cloudflare Access**。

對外公開的 hostname 需要使用由 Cloudflare 管理的網域。一般使用者可以透過已設定的身分供應商（IdP）或 Email One-Time PIN 驗證；自動化審查工具則可使用 Cloudflare Access **service token**（`CF-Access-Client-Id` 與 `CF-Access-Client-Secret`）。

同時，Access application 必須設定允許該 token 的 **Service Auth** policy。

| 模式 | 驗證方式 | 所需條件 | 適用情境 |
| --- | --- | --- | --- |
| Quick Tunnel | 無 | `cloudflared` | 短時間、低敏感度的審查 |
| Managed Tunnel + Cloudflare Access | 一般使用者：IdP／Email One-Time PIN；自動化工具：service token | Cloudflare 管理的網域、Managed Tunnel、Access application 與 policy | 需要身分驗證與存取控制的審查 |

Cloudflare 官方資料：

- [使用 Cloudflare Access 發布 self-hosted application](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/self-hosted-public-app/)
- [One-Time PIN 登入](https://developers.cloudflare.com/cloudflare-one/integrations/identity-providers/one-time-pin/)
- [Service tokens](https://developers.cloudflare.com/cloudflare-one/access-controls/service-credentials/service-tokens/)
- [Coding Agent 驗證](https://developers.cloudflare.com/cloudflare-one/access-controls/authenticate-agents/)

本專案目前不支援在本機端加上共用密碼閘門。

---

## 分享前注意事項

> [!WARNING]
> Quick Tunnel 端點**沒有身分驗證，而且只會暫時存在**。在程序執行期間，任何取得該網址的人都能存取篩選後的快照。
>
> 本專案不適合用來分享登入憑證、受法規管制的資料，或其他高度敏感內容。

開啟公開通道前，建議依序完成：

1. 仔細檢查準備分享的資料夾內容。
2. 先執行 `-ValidateOnly`，在本機檢查篩選結果與產生的快照。
3. 使用 `-AdditionalExclude`，排除專案特有的敏感或私人路徑。
4. `-Yes` 僅應用於事先核准、且已理解公開風險的工作流程。

請參閱[分享與篩選矩陣](docs/SHARING_MATRIX.zh-tw.md)，了解預設篩選規則能保護哪些內容，以及哪些範圍不在保護之內。

---

## 快速開始

**Windows** — 暫時分享資料夾 30 分鐘：

```powershell
.\share-codex-review.ps1 "D:\Projects\MyProject"
```

**macOS** — 暫時分享資料夾 30 分鐘：

```zsh
python3 ./macos/share-codex-review.py "/path/to/MyProject"
```

如果只要在本機建立並驗證篩選後的快照，不開啟公開通道：

```powershell
# Windows
.\share-codex-review.ps1 "D:\Projects\MyProject" -ValidateOnly
```

```zsh
# macOS
python3 ./macos/share-codex-review.py "/path/to/MyProject" --validate-only
```

---

## 使用方式

### Windows

公開時間預設為 30 分鐘。可透過 `-DurationMinutes` 調整，或按 **Enter** 提前結束。

| 用途 | 選項 |
| --- | --- |
| 調整公開時間 | `-DurationMinutes 10` |
| 指定本機連接埠 | `-Port 8080` |
| 設定可複製的單一檔案大小上限 | `-MaxFileSizeMB 25` |
| 新增萬用字元排除規則 | `-AdditionalExclude "private/*"` |
| 停用 QR Code | `-NoQrCode` |
| 略過 `SHARE` 確認 | `-Yes` |
| 設定 Quick Tunnel 重試次數 | `-QuickTunnelAttempts 3` |
| 設定重試的基礎等待時間 | `-QuickTunnelRetryBaseSeconds 5` |
| 輸出具版本資訊的 NDJSON | `-Json` |

> [!CAUTION]
> `-Yes` 會略過互動式確認，直接建立不需身分驗證的公開端點。僅應用於事先核准的工作流程。

### macOS

```zsh
python3 ./macos/share-codex-review.py "/path/to/MyProject"
```

如果只要驗證篩選後的快照，不開啟公開通道：

```zsh
python3 ./macos/share-codex-review.py "/path/to/MyProject" --validate-only
```

<p align="center">
  <img src="docs/assets/readme/quick-tunnel-outdoor-tunnel-gate.jpg" width="880" alt="Quick-Tunnel 鼴鼠吉祥物穿過戶外的暫時通道入口，抵達外部世界。" />
</p>

---

## 桌面整合

### Windows 檔案總管右鍵選單

雙擊 `context-menu-setup.cmd`，選擇 **Install**，再輸入 `INSTALL` 完成安裝。

此選單項目只會安裝到目前登入的 Windows 使用者帳號。Windows 11 上可能會收在「顯示更多選項」中。

安裝後的選單名稱為 **Make Q-Tunnel**。

![Windows 檔案總管右鍵選單中的 Make Q-Tunnel 選項](docs/assets/readme/make-q-tunnel-context-menu.png)

移除方式：

```powershell
.\manage-context-menu.ps1 -Action Uninstall
```

### macOS Finder Quick Action

安裝僅供目前使用者使用的 Finder Quick Action：

```zsh
/bin/zsh ./macos/manage-finder-quick-action.sh install
```

建議先執行不會修改系統的相容性與版本檢查；也可以從 `finder-quick-action-setup.command` 選擇 **Run doctor**：

```zsh
/bin/zsh ./macos/manage-finder-quick-action.sh doctor
```

在 Finder 中選取一個資料夾，再選擇 **快速動作 > Make Q-Tunnel**。

移除時不會永久刪除相關安裝檔，而是將它們移到同層的 `.del` 資料夾，方便日後復原。

---

## 機器可讀的生命週期事件

Windows 使用 `-Json`，macOS 使用 `--json`，程式就會輸出具版本資訊的 NDJSON 生命週期事件，供自動化工具解析。

| 模式 | 輸出的事件 |
| --- | --- |
| 僅驗證 | `validated`、`cleanup` |
| 公開模式 | `public_ready`（URL 有效期間）、`cleanup` |
| 發生錯誤 | `error`（非零結束代碼） |

JSON 公開模式必須搭配 `-Yes` 或 `--yes`，避免標準輸出（stdout）因互動式提示等待輸入而阻塞。

**版本 1 欄位：** `schema_version`、`event`、`mode`、`public_url`、`expires_at`、`server_pid`、`tunnel_pid`、`staging_root`、`error`。

啟用 JSON 輸出時，本機的 `staging_root` 路徑會出現在輸出內容中。除非整合需求確實需要，請勿將這個欄位轉送給無關的外部服務。

詳細規格請參閱 [Agent 整合契約](docs/AGENT_INTEGRATION.zh-tw.md)。

---

## 安全模型

- 只將通過篩選規則的檔案複製到隔離的暫存目錄。
- 預設排除常見的相依套件、版本控制、環境設定、憑證與金鑰路徑。
- 建立公開通道前，攔截高辨識度的機密資訊格式。
- 略過重新解析點（reparse point），以及超過設定大小上限的檔案。
- 快照中的 HTML、SVG、指令碼與其他標記內容，只會以不可執行的純文字形式提供。
- 加入嚴格的瀏覽器安全標頭，並停用快取。
- 本機來源伺服器只綁定至 `127.0.0.1`。
- 除非使用 `-Yes`，否則必須明確輸入 `SHARE` 才會公開。
- 程序結束時會停止本機伺服器與通道，並清除暫存快照。

**限制說明：**

機密資訊掃描採保守策略，無法保證找出所有憑證、敏感資料或私人資料。

掃描範圍只涵蓋已設定的文字副檔名，而且暫存後的檔案大小不得超過 2 MiB。較大的檔案或未知格式即使沒有經過這項內容掃描，只要仍低於另一項獨立設定的檔案複製大小上限，仍可能被複製進快照。

遠端以不可執行的形式呈現內容，也不代表將檔案下載後執行就是安全的。

正常結束，以及程式能夠處理的失敗情況，都會執行清理流程。若程序被強制終止、主機被關閉，或作業系統發生當機，則可能留下暫存檔案。

復原方法與殘餘風險，請參閱[威脅模型](docs/THREAT_MODEL.zh-tw.md)。

---

## Quick Tunnel 生命週期

只有在本機驗證完成，而且使用者明確同意分享後，才會建立 Quick Tunnel。

終端機會顯示公開 URL、程序 PID、公開端點驗證結果，以及預定到期時間。

公開時間到期後，程式會停止通道並移除暫存檔案。若由右鍵選單啟動，完成訊息會保留在視窗中，直到使用者確認。

如果 Cloudflare 端暫時發生 `500/1101` Quick Tunnel 建立錯誤，程式最多會自動重試三次，並採用指數退避（exponential backoff）。設定錯誤或速率限制（rate limit）回應則不會自動重試。

<p align="center">
  <img src="docs/assets/readme/quick-tunnel-private-home-visit.jpg" width="880" alt="Quick-Tunnel 鼴鼠吉祥物在私有基地中，迎接經由暫時通道前來拜訪的朋友。" />
</p>

> [!NOTE]
> Cloudflare Quick Tunnel 是不含身分驗證的暫時性開發端點。在程序執行期間，任何取得該 URL 的人都能存取篩選後的快照。

---

## 開發驗證

**Windows：**

```powershell
./windows/tests/test-share-codex-review.ps1
python -m unittest discover -s tests -v
```

**macOS：**

```zsh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s macos/tests -v
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

GitHub Actions 會執行 Windows 測試套件、macOS Python 測試與原生語法檢查、共用安全伺服器測試，以及 Python 3.14 相容性測試。

CI 不會建立公開通道，也不會安裝桌面整合功能。

---

## 文件索引

| 資源 | 連結 |
| --- | --- |
| 文件索引 | [docs/README.zh-tw.md](docs/README.zh-tw.md) |
| 威脅模型 | [docs/THREAT_MODEL.zh-tw.md](docs/THREAT_MODEL.zh-tw.md) |
| 分享與篩選矩陣 | [docs/SHARING_MATRIX.zh-tw.md](docs/SHARING_MATRIX.zh-tw.md) |
| Agent 整合契約 | [docs/AGENT_INTEGRATION.zh-tw.md](docs/AGENT_INTEGRATION.zh-tw.md) |
| macOS 指南 | [macos/README.zh-tw.md](macos/README.zh-tw.md) |
| 安全政策 | [SECURITY.zh-tw.md](SECURITY.zh-tw.md) |
| 參與開發 | [CONTRIBUTING.zh-tw.md](CONTRIBUTING.zh-tw.md) |
| 變更紀錄 | [CHANGELOG.zh-tw.md](CHANGELOG.zh-tw.md) |

---

## 授權

Quick Tunnel Review Share 採用 [MIT License](LICENSE) 授權（`SPDX-License-Identifier: MIT`）。
