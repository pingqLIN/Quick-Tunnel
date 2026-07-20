# 變更紀錄

[英文權威版本](CHANGELOG.md)

本文件記錄專案的重要變更。目前尚未發布帶有 Git 標籤的版本。

## 尚未發布

### 新增

- Windows `-Json` 與 macOS `--json` 的版本化 NDJSON 生命週期輸出。
- Windows 回歸測試，涵蓋排除規則、編碼容錯、讀取失敗時安全中止、暫存
  位元組掃描、來源變動、重新解析點（reparse point）穿透、取消、清理與 JSON 契約。
- 共用安全伺服器的 HTTP 測試，涵蓋不可執行 MIME、安全標頭、未知二進位
  內容與路徑限制。
- 在 Windows、macOS 與目前 Python 版本執行的 GitHub Actions 檢查。
- Pull Request 與 GitHub Issue 範本、相依項目審查，以及固定 GitHub Actions
  版本的 Dependabot 更新設定。
- 治理、安全政策、威脅模型與 Agent 整合文件。
- 獨立的測試、發布政策與 GitHub 設定文件。
- Finder 設定介面可直接執行既有且不會修改系統的 `doctor` 檢查。
- MIT 授權與 SPDX 識別碼 `MIT`。

### 調整

- Windows 與 macOS 暫存流程會計算來源內容雜湊，並在提供快照前拒絕
  相同長度的內容變動。
- Windows 會掃描已完成雜湊驗證的暫存位元組；無法檢查候選檔案時採安全
  中止，不會略過掃描。
- `.cmd` 檔案會以不可執行的純文字提供，`.log` 也納入機密掃描副檔名。
- 共用安全伺服器現在會在 CLI 邊界拒絕非回送介面的綁定地址。
- Windows 現在要求 Python 3.9 以上版本。

## 2026-07-18

- 新增 macOS CLI、Finder Quick Action、可復原的安裝程式、測試，以及英文與
  繁體中文文件。

## 2026-07-16

- 新增 Windows 過濾快照、本機安全伺服器、Cloudflare Quick Tunnel 工作
  流程、檔案總管右鍵選單、重試診斷與核心文件。
