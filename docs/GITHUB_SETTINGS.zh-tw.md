# GitHub 儲存庫設定

英文版為規範性版本：[GITHUB_SETTINGS.md](GITHUB_SETTINGS.md)。

儲存庫內的檔案可定義審查與測試，但不能自行強制 GitHub 端的政策。儲存庫
管理員仍需另外設定下列項目。

## 建議的 `main` ruleset（規則集）

- 合併前必須經過 Pull Request。
- 至少需要一份核准，並要求 Code Owner 審查。
- 出現新的可審查提交後，撤銷舊核准。
- 要求所有對話結案。
- 阻擋強制推送與分支刪除。
- 等各項檢查至少在儲存庫成功執行一次後，再將 `windows`、`macos`、
  `python-3-14` 與 `dependency-review` 設為必要檢查。

GitHub 尚未記錄對應檢查前，不要先選取必要檢查名稱。本機測試結果不等於
遠端強制設定。

## 安全設定

- 保持 dependency graph 啟用。
- 確認公開儲存庫的 secret scanning（機密掃描），並在帳號方案提供該控制時
  啟用儲存庫 push protection（推送防護）。
- 為 Python 啟用 CodeQL default setup（預設設定）。本專案不需要自訂建置，
  因此優先使用預設設定，而不是另外維護儲存庫 workflow（工作流程）。
- 若儲存庫設定提供此功能，要求 GitHub Actions 使用完整 commit SHA（提交識別碼）。

這些操作會改變公開儲存庫的控制面，必須另行取得管理員授權並在 GitHub
上驗證；提交本文件不會自動啟用設定。
