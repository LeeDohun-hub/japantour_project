from __future__ import annotations

import io
from pathlib import Path
import sys

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from tour_api.models import KnowledgeChunk, KnowledgeDocument

PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from src.chain.vector_store import JSONL_PATH, build_chunk_text, embed_texts, load_jsonl_records


class Command(BaseCommand):
    help = "tour_knowledge.jsonl 을 PostgreSQL/SQLite DB의 KnowledgeChunk 로 적재합니다."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--path", type=str, default=str(JSONL_PATH), help="입력 JSONL 경로")
        parser.add_argument("--rebuild", action="store_true", help="기존 청크를 삭제 후 다시 적재")
        parser.add_argument("--skip-embeddings", action="store_true", help="임베딩 생성 생략")
        parser.add_argument("--batch-size", type=int, default=100, help="임베딩 배치 크기")

    def handle(self, *args, **options) -> None:
        input_path = Path(options["path"]).resolve()
        if not input_path.exists():
            raise CommandError(f"JSONL 파일이 없습니다: {input_path}")

        records = load_jsonl_records(input_path)
        if not records:
            raise CommandError(f"적재할 레코드가 없습니다: {input_path}")

        document_defaults = {
            "title": "Japan Tour Knowledge Base",
            "source_uri": str(input_path),
            "domain": "tour_knowledge",
            "language": "ja",
            "metadata": {"path": str(input_path)},
        }
        document, _ = KnowledgeDocument.objects.update_or_create(
            source_type="jsonl",
            source_name=input_path.name,
            defaults=document_defaults,
        )

        if options["rebuild"]:
            deleted, _ = KnowledgeChunk.objects.filter(document=document).delete()
            self.stdout.write(self.style.WARNING(f"[REBUILD] 기존 청크 삭제: {deleted}건"))
            existing_chunks: dict[str, KnowledgeChunk] = {}
        else:
            existing_chunks = {
                chunk.external_id: chunk
                for chunk in KnowledgeChunk.objects.filter(document=document)
            }

        embed_queue: list[tuple[int, str]] = []
        created_count = 0
        updated_count = 0

        with transaction.atomic():
            for idx, record in enumerate(records):
                external_id = str(record.get("id") or idx)
                chunk_text = build_chunk_text(record)
                existing = existing_chunks.get(external_id)
                needs_embedding = existing is None or existing.chunk_text != chunk_text or existing.embedding is None

                defaults = {
                    "chunk_index": idx,
                    "question_ja": record.get("question_ja", "") or "",
                    "answer_ja": record.get("answer_ja", "") or "",
                    "answer_ko": record.get("answer_ko", "") or "",
                    "chunk_text": chunk_text,
                    "category": record.get("category", "") or "",
                    "area": record.get("area", "") or "",
                    "metadata": {
                        "source_record_id": external_id,
                    },
                }
                chunk, created = KnowledgeChunk.objects.update_or_create(
                    document=document,
                    external_id=external_id,
                    defaults=defaults,
                )
                if created:
                    created_count += 1
                else:
                    updated_count += 1
                if not options["skip_embeddings"] and needs_embedding:
                    embed_queue.append((chunk.id, chunk_text))

        self.stdout.write(
            self.style.SUCCESS(
                f"[IMPORT] document={document.source_name}  created={created_count}  updated={updated_count}"
            )
        )

        if options["skip_embeddings"]:
            self.stdout.write(self.style.WARNING("[SKIP] 임베딩 생성은 생략했습니다."))
            return

        batch_size = max(1, int(options["batch_size"]))
        total = len(embed_queue)
        if total == 0:
            self.stdout.write(self.style.SUCCESS("[DONE] 새로 생성하거나 갱신할 임베딩이 없습니다."))
            return

        self.stdout.write(f"[EMBED] {total}건 임베딩 생성 시작")

        for offset in range(0, total, batch_size):
            batch = embed_queue[offset : offset + batch_size]
            batch_ids = [chunk_id for chunk_id, _ in batch]
            batch_texts = [text for _, text in batch]
            vectors = embed_texts(batch_texts)
            chunks = list(KnowledgeChunk.objects.filter(id__in=batch_ids))
            chunk_by_id = {chunk.id: chunk for chunk in chunks}
            for chunk_id, vector in zip(batch_ids, vectors):
                chunk_by_id[chunk_id].embedding = vector
            KnowledgeChunk.objects.bulk_update(chunks, ["embedding"], batch_size=batch_size)
            done = min(offset + batch_size, total)
            self.stdout.write(f"  - {done}/{total}건 완료")

        self.stdout.write(self.style.SUCCESS("[DONE] JSONL -> DB 적재 및 임베딩 저장 완료"))
