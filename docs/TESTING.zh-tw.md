# 測試與驗證

英文版為規範性版本：[TESTING.md](TESTING.md)。

本文件將可重複執行的測試命令與歷史環境證據分開。歷史通過紀錄只適用於
當時受測的修訂版本，不能證明之後的工作目錄、作業系統版本或 runner（執行器）映像
仍會通過。

## 本機檢查

Windows 需使用 PowerShell 7，以及 Python 3.9 或更新版本：

```powershell
./windows/tests/test-share-codex-review.ps1
python -m unittest discover -s tests -v
python -m py_compile safe-review-server.py macos/share-codex-review.py `
  macos/tests/test_share_codex_review.py tests/test_safe_review_server.py
```

macOS 需使用 Python 3.9 或更新版本：

```zsh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s macos/tests -v
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
zsh -n macos/share-codex-review.command
zsh -n macos/launch-from-finder.sh
zsh -n macos/manage-finder-quick-action.sh
zsh -n macos/finder-quick-action-setup.command
zsh -n macos/tests/run-repeatability-tests.zsh
plutil -lint "macos/templates/Share to Codex Review.workflow/Contents/Info.plist"
plutil -lint "macos/templates/Share to Codex Review.workflow/Contents/document.wflow"
```

Finder 重複性測試會安裝與移除目前使用者的整合項目，只能在機器變更已獲
核准後執行。測試會拒絕覆寫既有或不完整的安裝，移除內容則保留在相鄰的
`.del` 目錄中，以便復原。

## 持續整合

`ci.yml` 會執行 Windows 迴歸測試、macOS Python、shell 與屬性清單
檢查、共用安全伺服器測試，以及目前 Python 相容性工作。
`dependency-review.yml` 會檢查 Pull Request 的相依項目變更。本機通過不能
取代同一筆提交版本的實際 GitHub Actions 結果。

CI 不會開啟公開通道，也不會執行 Finder 安裝循環。

## 原生 macOS 歷史證據

已發布的提交版本 `dcb3dc8` 曾在 2026-07-19 使用 macOS 15.7.7 x86_64、
Python 3.9.6、`cloudflared` 2026.6.1 與 `qrencode` 4.1.1 驗證。外部主機
存取過濾後的公開網址時得到 HTTP 200 與檢閱標記；QR 產生、自動到期與
清理皆通過。該 VM 因 NAT 路徑無法存取自己的公開網址，因此同一台 Mac
上的自我檢查仍正確維持為警告。

這份證據早於目前尚未提交的候選變更。在 macOS 上對完全相同的候選修訂
版本完成測試前，這批變更的原生 macOS 驗證狀態仍是未知。
