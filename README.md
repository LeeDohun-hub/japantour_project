# Japan Tour Project

訪韓日本人観光客向けの韓国旅行プランナー兼AIガイドサービスです。ユーザーは8ステップの旅行プランウィザードで航空券、宿泊、交通、訪問地域、予算、旅行スタイルを入力し、システムは日本語中心の旅程・交通・スポット案内を生成します。別画面のAIチャットでは、交通、グルメ、宿泊、観光、航空、イベントに関する質問に回答します。

韓国語 README: [README.md](./README.md)

## 1. プロジェクト概要

| 項目 | 内容 |
| --- | --- |
| プロジェクト名 | Japan Tour Project |
| 対象ユーザー | 韓国旅行を準備する日本人観光客 |
| 目的 | 旅行条件の収集、旅程生成、旅行情報のAI支援 |
| メイン画面 | Django `/` プランウィザード、`/chat/` AIチャット |
| AIパイプライン | 質問分類 → RAG/API検索 → LLM回答生成 |
| 主な言語 | UI・旅程は日本語中心、文書は韓国語/日本語併記 |

## 2. 主な機能

- 8ステップのプランウィザード
- AIチャットによる旅行相談
- RAG検索: ベクトル検索 + BM25 + RRF
- 仁川空港の航空便、空港バス、タクシー、空港鉄道情報
- Naver Maps/Search、Google Placesによる場所検索
- Interpark/NOL、VisitKorea、公演イベント情報の活用
- メールログイン、Google OAuth、LINE OAuth、ゲスト利用

## 3. 技術スタック

| 区分 | 技術 |
| --- | --- |
| Frontend | HTML, CSS, Vanilla JavaScript |
| Backend | Django |
| AI | OpenAI Chat/Embedding API |
| RAG | FAISS または pgvector, BM25, RRF |
| DB | SQLite, PostgreSQL + pgvector |
| External APIs | Naver, Google Places, data.go.kr, VisitKorea, JUSO |
| Legacy UI | Streamlit |

## 4. 実行方法

```powershell
pip install -r requirements.txt
Copy-Item .env.example .env
python backend\manage.py migrate
python backend\manage.py runserver 127.0.0.1:8000
```

- ホーム: http://127.0.0.1:8000/
- AIチャット: http://127.0.0.1:8000/chat/

## 5. 環境変数

| 変数 | 説明 |
| --- | --- |
| `OPENAI_API_KEY` | LLM分類・回答・埋め込み |
| `INCHEONTRANSPORT_API_KEY` | 仁川空港・航空・空港交通 API |
| `NAVER_MAPS_CLIENT_ID` | ブラウザ地図 |
| `NAVER_MAPS_CLIENT_SECRET` | サーバー側ジオコーディング |
| `NAVER_SEARCH_CLIENT_ID` / `NAVER_SEARCH_CLIENT_SECRET` | Naver Local/Blog検索 |
| `GOOGLE_MAPS_API_KEY` | Google Places |
| `DJANGO_SECRET_KEY` | 本番環境の秘密鍵 |

## 6. 文書

| 文書 | 韓国語 | 日本語 |
| --- | --- | --- |
| 要件定義書 | [docs/요건정의서.md](./docs/요건정의서.md) | [docs/要件定義書.md](./docs/要件定義書.md) |
| システム設計概要 | [docs/system-design-overview.md](./docs/system-design-overview.md) | [docs/system-design-overview_jp.md](./docs/system-design-overview_jp.md) |
| 基本設計書 | [docs/기본설계서.md](./docs/기본설계서.md) | [docs/基本設計書.md](./docs/基本設計書.md) |
| 詳細設計書 | [docs/상세설계서.md](./docs/상세설계서.md) | [docs/詳細設計書.md](./docs/詳細設計書.md) |
| `/chat` 評価サマリー (1枚PPT) | [evaluation/reports/chat_corpus_eval_20260624.md](./evaluation/reports/chat_corpus_eval_20260624.md) | [docs/chat_eval_summary_20260624_jp.pptx](./docs/chat_eval_summary_20260624_jp.pptx) |

## 7. テスト

```powershell
python -m unittest
node --check frontend\app.js
node tests\test_plan_map_parser.js
```

## 8. 注意事項

- `.env` と `data/` はGit管理対象外です。
- 公共データAPIはサービスごとに利用申請が必要な場合があります。
- Google Placesは費用が発生するため、明示的に有効化した場合のみ使用します。
- デモ・提出基準はDjango `:8000` です。
