# Supabase移行手順

## 1. Supabaseでプロジェクトを作成

ステージング用プロジェクトを1つ作成します。リージョンは利用者に近い地域を選びます。

## 2. 接続文字列を取得

Project Settings > Database からPostgreSQL接続文字列を取得します。

ITTOKAIでは次の形式を利用します。

```text
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/postgres
```

Supabaseが `postgresql://` 形式で表示する場合でもアプリ側でpsycopg形式へ変換します。

## 3. Renderに登録

Render > ittokai-test > Environment に `DATABASE_URL` を追加して再デプロイします。

初回起動時、SQLAlchemyが必要テーブルを作成し、空DBの場合はテスト用初期データを投入します。

## 4. 本番化時

- テストユーザーを削除
- `IMPORT_DEFAULT_PASSWORD` を強い初期パスワードへ変更
- DBバックアップ設定
- StorageへのPDF/画像移行
- Row Level SecurityはSupabaseを直接クライアントから利用する場合のみ、アプリRBACと二重化して設定

## 5. 規模目安

50施設・職員1000名・家族2000名・協賛企業100社はPostgreSQLでは小〜中規模です。DB自体より、PDF保管量、通知量、同時アクセス、監査ログ保持期間がコストに影響します。
