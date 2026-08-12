# 下書きファイルのフォーマット

`output/drafts/` には、Claudeが生成した商品紹介の下書きを1商品1ファイルで保存します。
`scripts/update_posting_log.py` がこのフォーマットのフロントマターを読み取って
`output/posting_log.xlsx` を更新するため、崩さないでください。

## ファイル名
`<商品スラッグ>_YYYYMMDD.md`（例: `ベビーカーA_20260812.md`）

## フォーマット
```
---
product_name: 商品名
product_url: https://item.rakuten.co.jp/xxxx/
created_date: 2026-08-12
rakuten_room_posted: false
instagram_posted: false
x_posted: false
---

## 楽天ROOM 紹介文
（本文）

## Instagram キャプション
（本文）
#PR #ハッシュタグ

## X 投稿文
（本文）
#PR #ハッシュタグ
```

- `rakuten_room_posted` / `instagram_posted` / `x_posted` は、実際にそのSNSへ投稿したら
  手動で `true` に書き換えてください。
- `#PR` などのアフィリエイト表記は、ステマ規制（景品表示法）対応のため必ず本文に含めてください。
