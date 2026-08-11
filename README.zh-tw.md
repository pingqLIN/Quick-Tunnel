# Quick Tunnel Review Share

建立本機資料夾的暫時性過濾快照，並透過 Cloudflare Quick Tunnel 短時間公開，
供程式碼審查使用。來源資料夾不會被 HTTP 伺服器直接提供。

[English version](README.md)

![Quick-Tunnel 鼴鼠吉祥物在私人 Mole HQ 中，引導審查膠囊穿過發光的暫時審查隧道。](docs/assets/readme/quick-tunnel-review-share-mole-mascot-banner.jpg)

> 先在本機篩選，再以明確同意安全分享，專注於快速審查。

[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)](#系統需求)
[![License MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Event schema v1](https://img.shields.io/badge/Event%20schema-v1-65a30d)](docs/THREAT_MODEL.zh-tw.md#機器可讀輸出)

---

## 目錄

- [專案狀態](#專案狀態)
- [系統需求](#系統需求)
- [Cloudflare / cloudflared 安裝與使用](#cloudflare--cloudflared-安裝與使用)
- [具身分驗證的分享模式評估](#具身分驗證的分享模式評估)
- [分享前注意事項](#分享前注意事項)
- [快速開始](#快速開始)
- [使用方式](#使用方式)
  - [Windows](#windows)
  - [macOS](#macos)
- [桌面整合](#桌面整合)
  - [Windows 檔案總管右鍵選單](#windows-檔案總管右鍵選單)
  - [macOS Finder Quick Action](#macos-finder-quick-action)
- [機器可讀生命週期](#機器可讀生命週期)
- [安全模型](#安全模型)
- [Quick Tunnel 生命週期](#quick-tunnel-生命週期)
- [開發驗證](#開發驗證)
- [文件索引](#文件索引)
- [授權](#授權)

---

## 專案狀態

目前尚未建立標籤版本。在第一個正式版本前，`main` 的最新提交是支援線；
發布或分享候選版本前，請確認確切修訂版本與 GitHub Actions 檢查結果。

---

## 系統需求

| 元件 | 文件支援範圍 | 程式實際檢查 | 已測試證據 |
| --- | --- | --- | --- |
| Windows | PowerShell 7；Python 3.9 以上 | `#requires` 與執行期 Python 檢查 | 2026-07-19 使用 PowerShell 7.6.3、Python 3.14.6 |
| macOS | macOS 14 以上 Homebrew 路徑；Python 3.9 以上 | 包裝程式與 Finder 的 `doctor` 檢查 Python 3.9 以上 | 2026-07-19 使用 macOS 15.7.7 x86_64、Python 3.9.6 |
| `cloudflared` | 仍在 Cloudflare 一年支援期限內的版本 | 確認執行檔存在；Finder doctor 也會回報版本 | macOS VM 使用 2026.6.1，Windows 使用 2026.7.1 |
| `qrencode` | 選用 | 不會強制要求 | macOS VM 使用 4.1.1 |

本專案不會虛構固定的 `cloudflared` 最低版本。Cloudflare 公布的版本支援期為
一年；程式只強制檢查實際使用的 CLI 能力。請讓 `cloudflared` 保持在支援
期限內。Finder 路徑另外需要系統內建的 zsh、Terminal、Finder、Automator、
AppleScript 與 `plutil`。

Finder Quick Action 安裝方式、功能對照與驗證說明請參閱
[macOS 指南](macos/README.zh-tw.md)。

---

## Cloudflare / cloudflared 安裝與使用

Quick Tunnel 透過 Cloudflare 的 `cloudflared` 用戶端，將本機審查伺服器連到
Cloudflare。專案預設使用 **Quick Tunnels / TryCloudflare**：`cloudflared` 會建立
隨機的 `*.trycloudflare.com` 網址，再把流量轉送到本機 HTTP 伺服器；這個模式
不需要先把自己的網域加入 Cloudflare DNS。

Cloudflare 官方資料：

- [`cloudflared` 下載與安裝](https://developers.cloudflare.com/tunnel/downloads/)
- [Quick Tunnels / TryCloudflare](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/)
- [建立受管理的 Cloudflare Tunnel](https://developers.cloudflare.com/tunnel/setup/)

### 安裝 `cloudflared`

**Windows（PowerShell）**

Cloudflare 官方下載頁提供 Windows 執行檔與 MSI。若要以指令安裝，可透過
Windows Package Manager 安裝已發布的 `Cloudflare.cloudflared` 套件：

```powershell
winget install --id Cloudflare.cloudflared --exact --source winget
cloudflared --version
```

若沒有 WinGet，或 WinGet 套件版本落後於 Cloudflare 當前版本，請改用上方
Cloudflare 官方下載頁提供的 MSI／執行檔。Cloudflare 也特別註明 Windows 的
`cloudflared` 不會自動更新，需要自行維護版本。

**macOS**

```zsh
brew install cloudflared
cloudflared --version
```

Cloudflare 官方文件以 Homebrew 作為 macOS 的標準安裝方式。

### 最小化 Quick Tunnel 手動測試

如果本機已有 Web server 在 `8080` 埠運作，Cloudflare 官方文件的最小測試為：

```text
cloudflared tunnel --url http://localhost:8080
```

`cloudflared` 會輸出暫時性的 `https://<random>.trycloudflare.com` 公開網址。
Quick Tunnel 定位為測試與開發用途；Cloudflare 目前限制最多 200 個同時進行中的
請求，而且不支援 Server-Sent Events（SSE）。除非來源端應用程式自行加入
驗證層，否則 Quick Tunnel 網址本身是公開且未驗證身分的。

---

## 具身分驗證的分享模式評估

目前 Quick Tunnel 流程維持短時效、**未經身分驗證**。TryCloudflare Quick Tunnel
本身沒有「共用靜態密碼」功能，因此若要做密碼保護，應把它視為獨立的驗證層，
而不是 Cloudflare Tunnel 的單一參數。

| 模式 | Cloudflare 帳號／網域 | 人員驗證 | 機器／Agent 驗證 | 建議 |
| --- | --- | --- | --- | --- |
| 現有 Quick Tunnel | 不需要 | 無 | 無 | 保留為低敏感度、短時審查的零設定預設模式 |
| Quick Tunnel + 本機密碼閘門 | 不需要 | 由本機審查伺服器處理共用密碼 | 若實作可透過 HTTP 驗證 header／cookie | 只有在真的需要「共用密碼」時採用的相容方案 |
| Managed Tunnel + Cloudflare Access | 公開 hostname 需要 Cloudflare 上的有效網域 | Cloudflare 帳號、IdP 或 Email One-Time PIN | Cloudflare Access service token | **建議的受保護模式** |

若要採 Cloudflare 原生保護機制，建議使用 **Managed Tunnel + Cloudflare Access**
保護 self-hosted application。Access 會在請求到達來源端之前先套用驗證政策，
可使用身分供應商登入與 Email One-Time PIN。自動化審查器則可使用 Access
**service token**（`CF-Access-Client-Id` 與 `CF-Access-Client-Secret`），避免互動式登入。

Cloudflare 官方資料：

- [使用 Cloudflare Access 發布 self-hosted application](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/self-hosted-public-app/)
- [One-Time PIN 登入](https://developers.cloudflare.com/cloudflare-one/integrations/identity-providers/one-time-pin/)
- [Service tokens](https://developers.cloudflare.com/cloudflare-one/access-controls/service-credentials/service-tokens/)
- [Coding Agent 驗證](https://developers.cloudflare.com/cloudflare-one/access-controls/authenticate-agents/)

**實作建議：** 保留 Quick Tunnel 為預設，再新增明確的驗證模式，例如
`Quick`、`Password`、`Access`。`Password` 應由本機 safe server 執行，而且密碼
不得進入 command-line arguments、log、JSON event 或公開 URL。`Access` 則應改走
named／managed tunnel 與 Cloudflare Access policy；service-token secret 同樣不得
出現在專案輸出或暫存審查內容中。

---

## 分享前注意事項

> [!WARNING]
> Quick Tunnel 端點**未經身分驗證且只會暫時存在**。程序執行期間，任何取得
> 產生網址的人都能存取過濾後的快照。本專案不適合處理憑證、受法規管制的資料
> 或其他高敏感度內容。

開啟公開通道前，請依序執行：

1. 仔細檢查目標資料夾內容。
2. 先執行 `-ValidateOnly`，在本機驗證過濾後的快照。
3. 使用 `-AdditionalExclude` 排除專案特有的私人路徑。
4. `-Yes` 只能用在已核准的工作流程。

請參閱[分享與篩選矩陣](docs/SHARING_MATRIX.zh-tw.md)，了解預設篩選能保護
與不能保護的範圍。

---

## 快速開始

**Windows** — 分享資料夾 30 分鐘：

```powershell
.\share-codex-review.ps1 "D:\Projects\MyProject"
```

**macOS** — 分享資料夾 30 分鐘：

```zsh
python3 ./macos/share-codex-review.py "/path/to/MyProject"
```

只驗證本機過濾快照，不開啟公開通道：

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

預設公開時效為 30 分鐘。可用 `-DurationMinutes` 調整，或按 **Enter** 提前停止。

| 用途 | 選項 |
| --- | --- |
| 調整時效 | `-DurationMinutes 10` |
| 指定本機連接埠 | `-Port 8080` |
| 限制複製檔案大小 | `-MaxFileSizeMB 25` |
| 新增萬用字元排除規則 | `-AdditionalExclude "private/*"` |
| 停用 QR 碼 | `-NoQrCode` |
| 略過 `SHARE` 輸入 | `-Yes` |
| 調整重試次數 | `-QuickTunnelAttempts 3` |
| 調整重試基礎等待時間 | `-QuickTunnelRetryBaseSeconds 5` |
| 輸出版本化 NDJSON | `-Json` |

> [!CAUTION]
> `-Yes` 會略過互動確認並建立未經身分驗證的公開端點，只能用在已核准的工作流程。

### macOS

```zsh
python3 ./macos/share-codex-review.py "/path/to/MyProject"
```

只驗證過濾後的快照，不開啟公開通道：

```zsh
python3 ./macos/share-codex-review.py "/path/to/MyProject" --validate-only
```

<p align="center">
  <img src="docs/assets/readme/quick-tunnel-outdoor-tunnel-gate.jpg" width="880" alt="Quick-Tunnel 鼴鼠吉祥物從戶外暫時通道入口抵達外部世界。" />
</p>

---

## 桌面整合

### Windows 檔案總管右鍵選單

雙擊 `context-menu-setup.cmd`，選擇 **Install**，再輸入 `INSTALL`。選單只會
安裝到目前 Windows 使用者。Windows 11 可能將它放在「顯示更多選項」。安裝
後的選單名稱為 **Make Q-Tunnel**。

![Windows 檔案總管右鍵選單中的 Make Q-Tunnel 選項](docs/assets/readme/make-q-tunnel-context-menu.png)

移除方式：

```powershell
.\manage-context-menu.ps1 -Action Uninstall
```

### macOS Finder Quick Action

安裝目前使用者專用的 Finder Quick Action：

```zsh
/bin/zsh ./macos/manage-finder-quick-action.sh install
```

請先執行不會修改系統的相容性與版本檢查，或從
`finder-quick-action-setup.command` 選擇 **Run doctor**：

```zsh
/bin/zsh ./macos/manage-finder-quick-action.sh doctor
```

在 Finder 選取一個資料夾，再選擇 **快速動作 > Make Q-Tunnel**。
移除時不會永久刪除安裝檔案，而是移到同層的 `.del` 資料夾，保留復原空間。

---

## 機器可讀生命週期

Windows 使用 `-Json`，macOS 使用 `--json`，可取得版本化 NDJSON 生命週期事件。

| 模式 | 輸出事件 |
| --- | --- |
| 僅驗證 | `validated`、`cleanup` |
| 公開模式 | `public_ready`（URL 有效時）、`cleanup` |
| 錯誤 | `error`（非零結束代碼） |

JSON 公開模式要求 `-Yes` 或 `--yes`，避免標準輸出被互動提示阻塞。

**版本 1 欄位：** `schema_version`、`event`、`mode`、`public_url`、`expires_at`、
`server_pid`、`tunnel_pid`、`staging_root`、`error`。

明確選擇 JSON 代表允許顯示本機 `staging_root`；仍不應把該欄位轉送到無關服務。
詳情請參閱 [Agent 整合契約](docs/AGENT_INTEGRATION.zh-tw.md)。

---

## 安全模型

- 將允許的檔案複製到隔離的暫存資料夾。
- 排除常見相依套件、版本控制、環境、憑證與金鑰路徑。
- 開啟通道前阻擋高可信度的機密格式。
- 跳過重新解析點（reparse point）與超過檔案大小限制的檔案。
- 將來源中的 HTML、SVG、指令碼與標記內容當成不可執行的純文字提供。
- 加入嚴格的瀏覽器安全標頭並停用快取。
- 本機來源伺服器只綁定 `127.0.0.1`。
- 除非使用 `-Yes`，否則必須明確輸入 `SHARE`。
- 結束時停止本機伺服器與通道，並清除暫存快照。

**限制說明：** 機密掃描採保守策略，無法保證辨識所有憑證或私人資料。
掃描只涵蓋設定的文字副檔名與 2 MiB 以下的暫存檔案；較大或未知格式的檔案
只要仍低於另一個複製上限，依然可能被複製。遠端以不可執行內容顯示，也不
代表下載後執行檔案是安全的。

正常結束與可處理失敗可以保證清理。強制終止程序、關閉主機或作業系統
當機，可能留下暫存檔案。復原方式與殘餘風險請參閱
[威脅模型](docs/THREAT_MODEL.zh-tw.md)。

---

## Quick Tunnel 生命週期

本機驗證完成並取得明確同意後，才會建立 Quick Tunnel。終端會顯示公開
URL、程序 PID、公開驗證結果與預定到期時間。時效到期後會停止通道、
移除暫存檔；由右鍵選單啟動時，完成提示會保留到使用者確認。

Cloudflare 端暫時性的 `500/1101` Quick Tunnel 建立錯誤，最多會以指數退避
重試三次；設定錯誤與速率限制回覆不會自動重試。

<p align="center">
  <img src="docs/assets/readme/quick-tunnel-private-home-visit.jpg" width="880" alt="Quick-Tunnel 鼴鼠吉祥物在私人基地中迎接由暫時通道前來拜訪的朋友。" />
</p>

> [!NOTE]
> Cloudflare Quick Tunnel 是未經身分驗證的暫時性開發端點。程序執行期間，
> 任何取得 URL 的人都能存取過濾後的快照。

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

GitHub Actions 會執行 Windows 測試、macOS Python 與原生語法檢查、共用安全
伺服器測試，以及 Python 3.14 相容性工作。CI 不會建立公開通道，也不會安裝
桌面整合。

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

Quick Tunnel Review Share 採用 [MIT License](LICENSE)
（`SPDX-License-Identifier: MIT`）。
