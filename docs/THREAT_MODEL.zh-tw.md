# 威脅模型

[英文權威版本](THREAT_MODEL.md)

## 用途與範圍

Quick Tunnel Review Share 讓審查者暫時存取本機資料夾的過濾副本。它適用於
經人工核准、短時間提供的低敏感度內容，不是具身分驗證的協作平台、完整的
DLP（資料外洩防護）系統，也不適合傳輸高敏感度資料。

## 資料流程與信任邊界

1. CLI 盤點選取的來源資料夾，不跟隨已排除的重新解析點（reparse point）或
   符號連結（symlink）。
2. 每個允許的檔案會複製到新建立的暫存根目錄；來源與暫存內容的雜湊必須
   相符。
3. 機密掃描會檢查實際的暫存位元組。
4. 安全伺服器只在 `127.0.0.1` 提供暫存根目錄。
5. 本機驗證與明確核准完成後，`cloudflared` 才會透過未經身分驗證的 Quick
   Tunnel 公開回送介面（loopback）伺服器。
6. 正常結束或可處理的失敗發生時，子程序會停止，暫存根目錄也會移除。

來源資料夾絕不會成為 HTTP 文件根目錄。產生的公開 URL 屬於持有即授權的
能力憑證（bearer capability）：程序執行期間，任何取得 URL 的人都能
讀取暫存快照。

## 安全保證

- 預設排除常見的 VCS、相依套件、環境設定、憑證、金鑰與雲端設定路徑。
- 不會複製重新解析點（reparse point）或符號連結（symlink）。
- 超過設定複製上限的檔案會排除。
- 內容雜湊可偵測檔案清冊與暫存之間相同長度的內容變動。
- 高可信度機密比對成功時，會在本機伺服器啟動前中止。
- 本機伺服器只綁定 `127.0.0.1`；其 CLI 會拒絕非回送介面的綁定地址。
- HTML、SVG、JavaScript、CSS、命令檔與其他已辨識文字格式都會以
  `text/plain` 提供；未知格式使用 `application/octet-stream`。
- 回應會使用 `no-store`、限制嚴格的 Content Security Policy、`nosniff`、
  同源資源政策（same-origin resource policy）與不傳送來源資訊政策（no-referrer policy）。
- 公開模式預設要求輸入完全相符的 `SHARE`；只有已核准的呼叫端明確使用
  `-Yes` 或 `--yes` 時才會略過。

## 已知限制

- 機密掃描只涵蓋設定的文字副檔名與 2 MiB 以下的檔案；預設複製上限是
  25 MiB。二進位檔案、較大的文字檔、組織自訂格式與未知的憑證模式
  可能不會被掃描。
- 掃描成功不代表快照內沒有私人或受規範資料。仍須人工檢查資料夾並加入
  專案特有的排除規則。
- 遠端以不可執行內容顯示，不代表下載後執行檔案是安全的。
- Quick Tunnel URL 沒有密碼或身分檢查；URL 外洩就會失去傳輸機密性。
- 正常結束與可處理失敗可以保證清理。強制終止程序、關閉主機或作業系統
  當機，可能留下暫存資料夾，必須透過經核准的復原流程處理。
- `-Yes` 與 `--yes` 會略過互動確認，但本身不代表已取得授權。

高敏感度內容應改用 Cloudflare Access 保護的具名通道（named tunnel），或其他經組織
核准且具身分驗證的傳輸方式。這類基礎設施不在本儲存庫範圍內。

## 機器可讀輸出

Windows `-Json` 與 macOS `--json` 會把 NDJSON（逐行 JSON）紀錄寫到標準輸出。
結構版本 1 在兩個平台使用相同欄位：

| 欄位 | 意義 |
| --- | --- |
| `schema_version` | 整數結構版本，目前為 `1`。 |
| `event` | `validated`、`public_ready`、`error` 或 `cleanup`。 |
| `mode` | `validate_only` 或 `public`。 |
| `public_url` | 公開審查 URL；尚未建立時為 `null`。 |
| `expires_at` | UTC ISO 8601 到期時間；不適用時為 `null`。 |
| `server_pid` | 本機安全伺服器 PID；不適用時為 `null`。 |
| `tunnel_pid` | `cloudflared` PID；不適用時為 `null`。 |
| `staging_root` | 供生命週期稽核使用的明確本機暫存路徑。 |
| `error` | 已遮蔽敏感資訊的錯誤摘要；成功時為 `null`。 |

`staging_root` 會透露本機路徑，只有呼叫端明確選擇 JSON 模式時才會出現。
收到 `cleanup` 事件時，該路徑通常已不存在。JSON 公開模式也要求 `-Yes` 或
`--yes`，避免標準輸出被互動提示阻塞。

## 殘餘風險檢查清單

分享前應確認選取的資料夾，使用 `-AdditionalExclude` 或
`--additional-exclude` 排除專案特有的私人路徑，先執行僅驗證模式，取得
明確核准後再公開，透過合適管道傳送 URL，並在審查完成後立即停止程序。
