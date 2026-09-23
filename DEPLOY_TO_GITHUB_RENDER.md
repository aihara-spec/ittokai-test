# GitHub / Render 反映手順

## 1. GitHub

1. このZIPを展開。
2. GitHubの `aihara-spec / ittokai-test` を開く。
3. Code > Add file > Upload files。
4. このフォルダの中身をアップロード。
5. Commit message: `ITTOKAI v20 integrated`。
6. Commit changes。

## 2. Render

GitHub連携でAuto-DeployがONなら自動でデプロイされます。

手動の場合:

1. Render > `ittokai-test`
2. Manual Deploy
3. Deploy latest commit
4. `/health` が `{"ok":true,"version":"20.1"...}` なら成功

## 3. Supabaseを使う場合

Render > Environment に `DATABASE_URL` を登録し再デプロイします。詳細は `SUPABASE_SETUP.md`。

## 4. LINE LIFF

Render URLが変わらなければLIFF Endpoint URLの変更は不要です。
URLが変わった場合だけLINE Developers > ITTOKAI > LIFF > Endpoint URLを更新してください。
