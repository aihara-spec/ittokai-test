# ITTOKAI v20.7.1 Integrated

ベース: https://github.com/aihara-spec/ittokai-test
コミット: 16273c8da6febcbeb88c44ebbf94dc362610524e (v20.7 Integrated)
作成日: 2026-10-21 (Asia/Tokyo)

## 修正
- 外部ブラウザーでLINEログイン後に戻った際、LIFF初期化とID Tokenのサーバー送信が再開されない不具合を修正。
- 連携開始ユーザーと開始時刻をsessionStorageに記録。15分経過またはユーザー変更で停止。ID TokenやITTOKAIセッショントークンをURLへ追加しない。
- 保存成功後にbootstrapを取り直し、マイページを即更新。認証・保存エラーを画面に残す。
- LINE Loginのverifyエンドポイントへ設定Channel IDを送信。検証応答のsub/aud/iss/expも確認。
- 既存LineAccountLinkのユーザー・LINE ID一意制約を維持。競合、同時更新時のIntegrityError、保存失敗でロールバックし、原因コードを返す。
- 解除したLINE IDも旧所有者の行に予約し、別ユーザーへの自動移管を拒否。同じ所有者の再連携は可能。アカウント移管は管理者の本人確認を伴う別作業。
- 連携試行の診断テーブルline_link_attemptsを追加。保存失敗は別トランザクションで記録。DB全体が停止した場合もサーバーログへユーザーID・原因コードを記録し、トークンは記録しない。
- 管理画面にアカウント単位の連携済み／未連携／認証済み保存失敗／送信失敗と原因コードを表示。施設管理者は自施設、法人本部は全体。
- 既存解除API・通知outbox・アプリ内通知・Deep Link・再送を継承。サービスワーカーのキャッシュを更新。

## 確認
TEST_RESULT_v20.7.1*.json、REPEATED_TEST_RESULT_v20.7.1.json、tests/round_*.logを参照。
追加UI試験はSDKとAPIを差し替えたNode VM試験。実ブラウザーでのLINE認証往復、Renderデプロイ、PostgreSQL実機移行、実LINE送信は未実施。
APIの受付成功は端末到達や閲覧の保証ではなく、ブロックされてもLINE APIが成功応答を返す場合があるため、ブロックを断定表示しない。

## 配布
ZIPにはソース・テスト・設定例・ドキュメントを収録。Git管理情報、DB、秘密設定、テスト実行時データ、Pythonキャッシュは除外。
デプロイ前に既存DBをバックアップ。既存DBへの変更は診断テーブル追加であり、既存の連携行・通知行は保持する。
