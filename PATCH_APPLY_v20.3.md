# v20.2 → v20.3 差し替え手順

1. ZIPを展開。
2. GitHub `aihara-spec / ittokai-test` を開く。
3. `Add file` → `Upload files`。
4. パッチ内のファイルを、フォルダ構成を保ったまま上書き。
5. Commit message: `ITTOKAI v20.3 stability update`
6. Renderで自動デプロイ、または `Manual Deploy` → `Deploy latest commit`。
7. `/health` で `version: 20.3` を確認。
8. ブラウザで `https://ittokai-test.onrender.com/?v=20.3` を開き、初回のみ `Ctrl + Shift + R`。

## 最低限の確認

- 施設管理者 → トーク → 家族選択 → トーク画面へ入る
- 家族から送信 → 施設側へ自動反映
- 施設から返信 → 家族側へ自動反映
- 電子書類の送付・署名が再ログインなしで反映
- 中間管理職・施設管理者の申請承認
- 面会予約
- ケア・ドゥ発注 → 出荷 → 検品 → 請求
