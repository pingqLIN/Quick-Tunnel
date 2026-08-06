# Agent 與程序執行器整合

[英文權威版本](AGENT_INTEGRATION.md)

Agent 整合應使用 CLI 進入點，不要使用 Explorer 或 Finder Quick Action。
Quick Action 依賴互動式桌面狀態，不是可攜式無介面入口。

## 必要的兩階段流程

階段 1 只執行本機前置檢查，不建立公開通道：

```powershell
pwsh -NoLogo -NoProfile -File ./share-codex-review.ps1 `
  "D:\Project" -ValidateOnly -NoQrCode -Json
```

```zsh
python3 ./macos/share-codex-review.py "/path/to/project" \
  --validate-only --no-qr-code --json
```

執行器必須確認結束代碼為 `0`，收到 `validated`，之後也收到 `cleanup`。
接著必須另行取得未經身分驗證公開暴露的明確核准。

階段 2 只有在核准後才能執行：

```powershell
pwsh -NoLogo -NoProfile -File ./share-codex-review.ps1 `
  "D:\Project" -Yes -NoQrCode -Json
```

```zsh
python3 ./macos/share-codex-review.py "/path/to/project" \
  --yes --no-qr-code --json
```

請逐行讀取標準輸出的 NDJSON 紀錄。`public_ready` 會在程序仍執行時提供 URL；
執行器應保持程序連線、設定有上限的時效，並以後續 `cleanup` 作為生命週期
結束。收到 `error` 或非零結束代碼都代表失敗。不得因命令含有 `--yes` 就
推定已核准；授權必須來自外層的治理工作流程。

## 整合限制

- 不得把原始碼、暫存路徑、日誌或機密傳到無關服務。
- 有 JSON 模式時，不要剖析給人閱讀的輸出。
- 不得在不必要的時間內持續記錄或保存公開 URL。
- CI（持續整合）不得建立真實 Quick Tunnel。
- VM／NAT 環境的同一台主機公開驗證失敗，不代表外部 URL 一定無法連線。
- 高敏感度內容不得使用 Quick Tunnel；應改用具身分驗證且經組織核准的傳輸
  方式。

完整安全界線與 NDJSON 結構請參閱[威脅模型](THREAT_MODEL.zh-tw.md)。
