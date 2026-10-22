# LINE設定 v20.7.2
環境変数はv20.7.1と同じ。秘密値の変更は不要。
LIFF_ID=2011515301-9Xriwevd
LINE_LOGIN_CHANNEL_ID=2011515301
LINE_MOCK_MODE=0
LINE_CHANNEL_ACCESS_TOKENとDATABASE_URLは既存値を維持。

更新後の/health: version=20.7.2。
元のユーザーで解除済みの場合、希望するユーザーのマイページからLINE連携を実行する。
有効な連携が残っている場合は先に元ユーザーで解除する。他ユーザーの連携を強制解除する機能はない。
LINE_ACCOUNT_CONFLICTが続く場合は他ユーザーの有効な連携、またはDB一意制約競合を確認する。
SQLiteをRenderの一時領域で使用する場合は、再デプロイ時にデータが保持されないため、必要なデータを先にバックアップする。

ローカル検証: python tests/run_v20_7_2_unlink.py
テストは専用SQLiteを使用。実LINEトークン不要。再実行前にテストDBを削除するか別の専用DBを指定する。
