# ITTOKAI v20.3 Integrated

ITTOKAIを「家族連絡アプリ」から、家族・職員・施設・株式会社ケア・ドゥ・既存業務ソフトをつなぐ統合業務プラットフォームへ拡張した実装版です。

## 実装済み

- 7ロールRBAC: 家族 / 一般職員 / 中間管理職（チーフ・リーダー・マネージャー） / 施設管理者 / 法人本部 / ケア・ドゥ / 外部協賛企業
- 家族↔施設チャット / 既読
- お知らせ
- 電子書類 v2: 送付、閲覧、同意、手書き署名、署名済PDF、ハッシュ、監査ログ
- 職員申請: 有給 / 残業 / 勤務変更、2段階承認、差戻し・履歴
- 面会予約: 施設別・曜日別・時間枠、容量、予約・取消、施設側ルール設定
- ケア・ドゥ: 商品、施設別価格、在庫、安全在庫、発注候補、発注、受注、出荷、納品、請求、3点照合
- CSV連携: ほのぼの / クロノス / 弥生
- CSV一括登録: 施設、職員、利用者・家族、ケア・ドゥ商品、施設在庫・価格
- LINE Messaging API用通知アダプタ（アクセストークン設定時）
- 監査ログ
- PWA / スマホホーム画面追加
- PostgreSQL(Supabase)対応。DATABASE_URL未設定時はSQLiteテストDB


## v20.3 品質改善

- 施設管理者で家族を選択してもトーク画面へ移行しない不具合を修正
- 一般職員・中間管理職にも施設内家族トークを追加
- トークの自動同期（家族↔施設）を追加し、再ログイン不要で反映
- 電子書類・職員申請・面会・発注/納品/請求・お知らせを画面表示中に自動同期
- 他施設書類・他部署申請・家族トーク等の権限越境を追加防止
- 面会予約の過去日・締切・人数上限・サーバー側終了時刻検証を追加
- 発注数量、商品、注文状態、検品数量、請求重複をサーバー側で検証
- PDFアップロード時にPDF形式を検証
- PWAキャッシュをv20.3へ更新

### 自動試験

- API/業務シナリオ: 175サイクル / 1,326アサーション PASS
- UIロール試験: 7ロール / 102画面遷移 / トーク遷移 PASS
- 想定規模データ: 50施設 / 職員1,000 / 家族2,000 / 協賛企業100 の生成・読込確認
- 規模データ上でbootstrap 350回連続読込 PASS（ローカルSQLiteで平均約5.9ms。実本番性能を保証する数値ではありません）

## テストアカウント

- 家族: `family@ittokai.local` / `demo1234`
- 一般職員: `staff@ittokai.local` / `staff1234`
- 中間管理職: `manager@ittokai.local` / `manager1234`
- 施設管理者: `admin@ittokai.local` / `admin1234`
- 法人本部: `hq@ittokai.local` / `hq1234`
- ケア・ドゥ: `caredo@ittokai.local` / `caredo1234`
- 外部協賛企業: `sponsor@ittokai.local` / `sponsor1234`

## Windowsで起動

`1_START_LOCAL.bat` をダブルクリック。

または:

```bash
pip install -r requirements.txt
python server.py
```

ブラウザ: http://localhost:8000

## Render

Build Command:

```text
pip install -r requirements.txt
```

Start Command:

```text
python server.py
```

Health Check: `/health`

## Supabase/PostgreSQL

RenderのEnvironmentに `DATABASE_URL` を設定するとPostgreSQLへ切り替わります。
詳細は `SUPABASE_SETUP.md` を参照してください。

## 既存ソフト連携

今回の版では、製品・契約・バージョン差の影響を受けにくいよう、最初にCSVアダプタを実装しています。

- ほのぼの: 利用者・施設・契約/請求関連のCSV/API接続口
- クロノス: 承認済み有給・残業・勤務変更のCSV出力
- 弥生: ケア・ドゥ請求・売上・会計連携用CSV出力

実際のAPI自動連携は、各製品の契約プラン・API仕様・CSVレイアウト確定後にアダプタを差し替えます。

## 本番前の必須事項

1. Supabase/PostgreSQLへ移行
2. 管理者MFA
3. 正式なプライバシーポリシー・利用規約
4. バックアップ・復元テスト
5. LINE公式アカウントMessaging API設定
6. 本人確認・重要契約の電子契約方式を法務/顧問と確定
7. ほのぼの・クロノス・弥生の実CSV/API仕様確定
8. デフォルトパスワード変更
9. 実データ投入前に権限テスト
