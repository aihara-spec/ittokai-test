# ITTOKAI v20.1 修正版

## 修正内容

- 電子書類の「署名PDF」をクリックした際に `ログインが必要です` と表示される問題を修正。
- 「原本PDF」も同じ認証方式で開くよう修正。
- ケア・ドゥ請求書PDFも同じ認証方式へ統一。
- 認証トークンをURLへ付けず、AuthorizationヘッダーでPDFを取得してBlob URLとして表示。
- Service Workerキャッシュをv20.1へ更新し、旧app.jsが残りにくいよう変更。

### 原因
通常のAPI通信はBearerトークンをAuthorizationヘッダーへ付与していたが、PDFボタンだけ `window.open('/api/...')` で直接URLを開いていたため、認証ヘッダーが送信されていなかった。

### 修正後
PDFボタン → 認証付きfetch → PDF取得 → ブラウザ内PDF表示。
