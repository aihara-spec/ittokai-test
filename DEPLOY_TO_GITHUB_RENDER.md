# GitHub / Render 反映手順

## 1. GitHub

1. このZIPを展開。
2. GitHubの `aihara-spec / ittokai-test` を開く。
3. Code > Add file > Upload files。
4. このフォルダの中身をアップロード。
5. Commit message: `ITTOKAI v20.3 stability update`。
6. Commit changes。

## 2. Render

GitHub連携でAuto-DeployがONなら自動でデプロイされます。

手動の場合:

1. Render > `ittokai-test`
2. Manual Deploy
3. Deploy latest commit
4. `/health` が `{"ok":true,"version":"20.3"...}` なら成功

## 3. Supabaseを使う場合

Render > Environment に `DATABASE_URL` を登録し再デプロイします。詳細は `SUPABASE_SETUP.md`。

## 4. LINE LIFF

Render URLが変わらなければLIFF Endpoint URLの変更は不要です。
URLが変わった場合だけLINE Developers > ITTOKAI > LIFF > Endpoint URLを更新してください。

## v20.7 LINE通知を有効にする場合
Render > ittokai-test > Environment で `LINE_CHANNEL_ACCESS_TOKEN`, `LINE_LOGIN_CHANNEL_ID`, `NOTIFICATION_CRON_SECRET` を設定してください。`APP_BASE_URL`, `LIFF_ID`, `LIFF_BASE_URL` は `render.yaml` にテスト環境の値を記載しています。詳細は `LINE_SETUP.md` を参照してください。

期限前/承認待ちの再通知をアプリを開かず実行するには、Render Cron Jobを作成し、同じ `APP_BASE_URL` と `NOTIFICATION_CRON_SECRET` を設定して `python notification_cron.py` を定期実行します。
