# 參與 Quick Tunnel Review Share 開發

[英文權威版本](CONTRIBUTING.md)

感謝你協助改善 Quick Tunnel Review Share。英文文件是權威版本；重要的操作
文件如有變更，也應同步更新繁體中文 `.zh-tw.md` 參考文件。

## 提交變更前

- 必須維持來源資料夾的安全界線：只能提供過濾後的暫存快照。
- 不得把真實憑證、私人 URL、瀏覽器 Cookie、正式環境資料寫入原始碼、測試資料、
  GitHub Issue 或日誌。
- 公開分享必須保留完全相符的 `SHARE` 確認；只有已核准的工作流程可以明確
  使用 `-Yes` 或 `--yes`。
- 自動化測試不得建立真實的 Quick Tunnel。
- 疑似漏洞應依 [SECURITY.zh-tw.md](SECURITY.zh-tw.md) 的私人通報流程處理，
  不要公開建立 GitHub Issue。

## 本機驗證

Windows 需要 PowerShell 7 與 Python 3.9 以上版本：

```powershell
./windows/tests/test-share-codex-review.ps1
python -m unittest discover -s tests -v
```

macOS 需要 Python 3.9 以上版本：

```zsh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s macos/tests -v
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
zsh -n macos/share-codex-review.command
zsh -n macos/launch-from-finder.sh
zsh -n macos/manage-finder-quick-action.sh
zsh -n macos/finder-quick-action-setup.command
zsh -n macos/tests/run-repeatability-tests.zsh
plutil -lint \
  "macos/templates/Share to Codex Review.workflow/Contents/Info.plist"
plutil -lint \
  "macos/templates/Share to Codex Review.workflow/Contents/document.wflow"
```

Finder 可重複性測試會變更目前使用者的 Library，因此有獨立確認關卡，不會
納入預設 CI（持續整合）工作流程。

## Pull Request

請說明行為變更、安全影響、回復方式與實際完成的驗證。Pull Request 範本
會一致記錄這些檢查。使用者可見的變更應更新
[CHANGELOG.zh-tw.md](CHANGELOG.zh-tw.md)。如果變更排除規則、機密
掃描、暫存、公開確認、JSON 事件、清理機制或安全伺服器標頭，必須同步
更新相關測試與[威脅模型](docs/THREAT_MODEL.zh-tw.md)。

合併前，Windows 與 macOS 的 CI 都必須通過。本機測試成功不能取代實際的
GitHub Actions 結果。

完整命令與證據適用邊界請參閱[測試與驗證](docs/TESTING.zh-tw.md)。
