# ITTOKAI v20.7 LINE通知セットアップ

## 1. 構成
ITTOKAIは業務イベントを最初にアプリ内通知へ保存し、LINE連携済みユーザーにはMessaging APIのPush Messageも送信します。LINE未連携、ブロック、API障害などがあってもITTOKAI内通知と送信履歴は残ります。

通知対象は、契約書の送付・署名完了、職員申請の提出・回付・結果、面会予約、ケア・ドゥ/協賛会社へのショップ注文と注文状態、施設在庫の自動発注候補/自動発注、施設発注・出荷・受領・請求、家族/施設トークです。

## 2. LINE Developers側
1. 同じProvider配下で、LINE Official Account/Messaging APIチャネルとLINE Loginチャネルを用意します。
2. LINE LoginチャネルにLIFFアプリを設定し、ITTOKAIのHTTPS URLをEndpoint URLとして設定します。
3. LIFFでは`openid`を利用できる構成にします。
4. Messaging APIのChannel access tokenを発行します。
5. ITTOKAI利用者が公式アカウントを友だち追加できる導線も用意します。

ITTOKAIの「マイページ > LINE通知を連携」ではLIFF SDKから取得したID tokenをサーバーへ送り、サーバーがLINEのverify endpointで検証して`sub`をITTOKAIユーザーへ紐付けます。クライアントが申告したLINE user IDをそのまま信用しません。

## 3. Render環境変数
`ENV_EXAMPLE.txt`を参照して、少なくとも次を設定します。

- `DATABASE_URL`
- `APP_BASE_URL`
- `LINE_CHANNEL_ACCESS_TOKEN`
- `LINE_LOGIN_CHANNEL_ID`
- `LIFF_ID`
- `LIFF_BASE_URL`
- `NOTIFICATION_CRON_SECRET`

`LINE_MOCK_MODE=1`はテスト専用です。本番では必ず`0`または未設定にします。

## 4. 定期リマインド
契約書期限前・承認待ちの再通知は、アプリを誰も開かなくても動かす必要があります。Render Cron Jobを追加し、Web Serviceと同じ`APP_BASE_URL`と`NOTIFICATION_CRON_SECRET`を設定して、例えば1時間ごとに次を実行します。

`python notification_cron.py`

同一処理の重複送信はイベントキーと再通知間隔で抑止します。通知ルールは`/api/notifications/rules`で管理できます。

## 5. セキュリティ/プライバシー
LINE本文は「確認が必要な書類があります」「新しい注文があります」等の最小限の内容にし、契約内容、介護情報、家族/利用者の詳細は表示しません。詳細は認証後のITTOKAIで確認します。協賛会社の注文APIにも不要な家族・利用者識別情報を返しません。

## 6. 送信状態の意味
ITTOKAIのLINE送信`sent`はMessaging APIへの送信処理が成功した状態です。利用者が公式アカウントをブロックしている場合、通信障害、LINE側障害、端末側設定などにより、実際の端末通知や閲覧までは保証できません。そのためITTOKAI内通知を常に併用します。
