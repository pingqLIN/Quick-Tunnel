# Quick Tunnel Review Share

Quick Tunnel Review Share 會建立本機資料夾的暫時性過濾快照，並透過
Cloudflare Quick Tunnel 短時間公開，供程式碼審查使用。來源資料夾不會被
HTTP server 直接提供。

[English authoritative version](README.md)

## 系統需求

Windows：

- PowerShell 7（`pwsh.exe`）
- Python 3
- `cloudflared`
- 選用：`qrencode`，用於在終端顯示 QR code

macOS：

- 使用 Homebrew 的正式支援環境為 macOS 14 以上
- Python 3.9 以上
- `cloudflared`
- 系統內建的 zsh 與 Automator
- 選用：`qrencode`，用於在終端顯示 QR code

Finder Quick Action 安裝方式、功能對照與驗證說明請參閱
[macOS 指南](macos/README.zh-tw.md)。

## 使用方式

```powershell
.\share-codex-review.ps1 "D:\Projects\MyProject"
```

只建立並驗證本機過濾快照、不開啟公開 tunnel：

```powershell
.\share-codex-review.ps1 "D:\Projects\MyProject" -ValidateOnly
```

預設公開時效為 30 分鐘。可用 `-DurationMinutes` 調整，或按 Enter 提前停止。

macOS 使用方式：

~~~zsh
python3 ./macos/share-codex-review.py "/path/to/MyProject"
~~~

只建立並驗證過濾後的快照，不開啟公開 tunnel：

~~~zsh
python3 ./macos/share-codex-review.py "/path/to/MyProject" --validate-only
~~~

## Windows 檔案總管右鍵選單

雙擊 `context-menu-setup.cmd`，選擇 **Install**，再輸入 `INSTALL`。選單只會
安裝到目前 Windows 使用者。Windows 11 可能將它放在「顯示更多選項」。

移除方式：

```powershell
.\manage-context-menu.ps1 -Action Uninstall
```

## macOS Finder Quick Action

安裝目前使用者專用的 Finder Quick Action：

~~~zsh
/bin/zsh ./macos/manage-finder-quick-action.sh install
~~~

在 Finder 選取一個資料夾，再選擇 **快速動作 > Share to Codex Review**。
移除時不會永久刪除安裝檔案，而是移到同層的 `.del` 資料夾，保留復原空間。

## 安全模型

- 將允許的檔案複製到隔離的暫存資料夾。
- 排除常見相依套件、版本控制、環境、憑證與金鑰路徑。
- 開啟 tunnel 前阻擋高可信度的 secret 格式。
- 跳過 reparse point 與超過檔案大小限制的檔案。
- 將來源中的 HTML、SVG、script 與 markup 當成不可執行的純文字提供。
- 加入嚴格的瀏覽器安全標頭並停用快取。
- 本機 origin 只綁定 `127.0.0.1`。
- 除非使用 `-Yes`，否則必須明確輸入 `SHARE`。
- 結束時停止本機 server 與 tunnel，並清除暫存快照。

Secret 掃描採保守策略，無法保證辨識所有憑證或私人資料。分享前仍應檢查
目標資料夾，並使用 `-AdditionalExclude` 排除專案特有的私人路徑。

## Quick Tunnel 生命週期

本機驗證完成並取得明確同意後，才會建立 Quick Tunnel。終端會顯示公開
URL、程序 PID、公開驗證結果與預定到期時間。時效到期後會停止 tunnel、
移除暫存檔；由右鍵選單啟動時，完成提示會保留到使用者確認。Cloudflare
端暫時性的 `500/1101` Quick Tunnel 建立錯誤，最多會以指數退避重試三次；
設定錯誤與 rate limit 回覆不會自動重試。

Cloudflare Quick Tunnel 是未經身分驗證的暫時性開發端點。程序執行期間，
任何取得 URL 的人都能存取過濾後的快照。
