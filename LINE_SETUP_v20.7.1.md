# LINE設定 v20.7.1

## Render環境変数
```
LIFF_ID=2011515301-9Xriwevd
LINE_LOGIN_CHANNEL_ID=2011515301
LINE_MOCK_MODE=0
APP_BASE_URL=https://ittokai-test.onrender.com
LIFF_BASE_URL=https://liff.line.me/2011515301-9Xriwevd
```
LINE_CHANNEL_ACCESS_TOKENはRenderの秘密環境変数へ設定する。コードやZIPに実値を保存しない。
DATABASE_URLは既存の永続PostgreSQL接続先を維持する。Renderの一時ファイルシステム上のSQLiteでは再デプロイ時の保存保持を保証できない。
LINE LoginとMessaging APIチャネルは同じプロバイダーに置き、同じユーザーIDが使われる構成にする。

## LINE Developers
LIFFのEndpoint URLは https://ittokai-test.onrender.com/ とし、openidスコープを有効にする。redirectUriは同じURL配下の ?view=me を使用する。
設定確認後、Renderへコードを反映してデプロイし、ブラウザーを強制再読込する。

## 受入確認
7ロールそれぞれで、ITTOKAIへログイン→マイページ→LINE通知を連携→LINEログイン→戻り時に連携済み→再読込→再ログイン→連携状態保持→解除→未連携→同じLINEで再連携を確認。
別のITTOKAIユーザーで同じLINEを使うとLINE_ACCOUNT_CONFLICTを返す。解除しても別ユーザーへ自動移管しない。
管理画面で対象ユーザーと原因コードを確認する。

- LINE_AUTH_FAILED: トークン検証失敗。openid、Channel ID、期限、認証キャンセル、ネットワークを確認。
- LINE_ACCOUNT_CONFLICT: 別ユーザーが所有するLINE ID。一意制約の競合を含む。
- LINE_SAVE_FAILED: LINE検証済みだがDB保存失敗。DB接続・制約・サーバーログを確認。LINE認証成功を連携保存成功と扱わない。
- LINKED / UNLINKED: 最後の連携操作成功／解除。

契約書、トーク、申請承認、面会、ケア・ドゥ注文、協賛ギフト、施設在庫・自動発注について、LINE通知から該当画面への遷移を実機で確認する。未連携・送信エラーでもアプリ内通知を確認し、管理画面から失敗分を再送する。

## ローカルテスト
Python 3.12で確認。依存関係はrequirements.txtとhttpxを導入。
```
python tests/run_v20_7_1_repeated.py
node tests/run_v20_7_1_callback.cjs
```
テストは専用SQLiteを使用する。LINE認証検証・HTTP送信はモックとHTTPクライアント差し替えで行い、実アクセストークンは不要。
Windowsでローカル通信の制限によりTestClientが停止する場合は、ローカル通信を許可した環境で実行する。

公式仕様:
- https://developers.line.biz/en/docs/liff/developing-liff-apps/
- https://developers.line.biz/en/reference/liff/
- https://developers.line.biz/en/reference/line-login/#verify-id-token
