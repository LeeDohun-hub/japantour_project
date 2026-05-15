"""벡터 검색 스토어.

지원 백엔드:
- FAISS (기존 로컬 인덱스)
- PostgreSQL + pgvector (Django ORM 기반)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
BACKEND_ROOT = PROJECT_ROOT / "backend"
JSONL_PATH = PROJECT_ROOT / "data" / "processed" / "tour_knowledge.jsonl"
INDEX_DIR = PROJECT_ROOT / "data" / "vector"
INDEX_PATH = INDEX_DIR / "tour_knowledge.faiss"
META_PATH = INDEX_DIR / "tour_knowledge_meta.json"

EMBED_MODEL = "text-embedding-3-small"
EMBED_DIM = 512
BATCH_SIZE = 500
CATEGORY_BUFFER = 8


def load_jsonl_records(path: Path = JSONL_PATH) -> list[dict]:
    records: list[dict] = []
    if not path.exists():
        return records

    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return records


def build_chunk_text(record: dict) -> str:
    return (
        f"{record.get('question_ja', '')} {record.get('answer_ja', '')}"
    ).strip() or " "


def embed_texts(texts: list[str]) -> list[list[float]]:
    from openai import OpenAI

    client = OpenAI()
    response = client.embeddings.create(
        model=EMBED_MODEL,
        input=[text if text.strip() else " " for text in texts],
        dimensions=EMBED_DIM,
    )
    return [item.embedding for item in response.data]


def _normalize_backend(backend: str | None) -> str:
    value = (backend or os.environ.get("VECTOR_BACKEND", "faiss")).strip().lower()
    return value if value in {"faiss", "pgvector"} else "faiss"


def _ensure_django() -> None:
    try:
        from django.apps import apps
        if apps.ready:
            return
    except Exception:
        pass

    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    import django

    django.setup()


class BaseVectorStore:
    backend_name = "base"

    def is_ready(self) -> bool:
        raise NotImplementedError

    def search(
        self,
        query: str,
        category: str = "",
        area: str = "",
        top_k: int = 5,
    ) -> list[dict]:
        raise NotImplementedError


class FaissVectorStore(BaseVectorStore):
    """FAISS + OpenAI 임베딩 기반 의미(시맨틱) 검색 스토어."""

    backend_name = "faiss"

    def __init__(self) -> None:
        self._index = None
        self._meta: list[dict] | None = None
        self._loaded = False

    def _try_load(self) -> bool:
        if self._loaded:
            return True
        if not INDEX_PATH.exists() or not META_PATH.exists():
            return False
        try:
            import faiss  # type: ignore

            self._index = faiss.read_index(str(INDEX_PATH))
            with open(META_PATH, encoding="utf-8") as f:
                self._meta = json.load(f)
            self._loaded = True
            return True
        except Exception:
            return False

    def is_ready(self) -> bool:
        return self._try_load()

    def build(self, force: bool = False) -> None:
        try:
            import faiss  # type: ignore
            import numpy as np
        except ImportError as e:
            print(f"[ERROR] 필요한 패키지 없음: {e}")
            print("  pip install faiss-cpu numpy openai")
            sys.exit(1)

        if not force and INDEX_PATH.exists() and META_PATH.exists():
            print(f"[INFO] 인덱스가 이미 존재합니다: {INDEX_PATH}")
            print("[INFO] 재빌드하려면 --force 옵션을 사용하세요.")
            return

        if not JSONL_PATH.exists():
            print(f"[ERROR] JSONL 파일 없음: {JSONL_PATH}")
            print("[INFO] python extract_tour_knowledge.py && python tour_preprocess.py 를 먼저 실행하세요.")
            sys.exit(1)

        INDEX_DIR.mkdir(parents=True, exist_ok=True)
        records = load_jsonl_records()
        n = len(records)
        print(f"[INFO] {n:,}건 로드 완료")

        texts = [build_chunk_text(record) for record in records]

        avg_tokens = 100
        est_tokens = n * avg_tokens
        est_cost = est_tokens / 1_000_000 * 0.02
        print(f"[INFO] 임베딩 시작 — 모델: {EMBED_MODEL}, 차원: {EMBED_DIM}")
        print(f"[INFO] 예상 토큰: ~{est_tokens:,}, 예상 비용: ~${est_cost:.3f}")
        print()

        all_embeddings: list[list[float]] = []
        batches = (n + BATCH_SIZE - 1) // BATCH_SIZE

        for batch_i, start in enumerate(range(0, n, BATCH_SIZE), 1):
            batch_texts = texts[start : start + BATCH_SIZE]
            all_embeddings.extend(embed_texts(batch_texts))
            done = min(start + BATCH_SIZE, n)
            pct = done * 100 // max(n, 1)
            print(f"  배치 {batch_i}/{batches} — {done:,}/{n:,}건 ({pct}%)")

        print()

        vectors = np.array(all_embeddings, dtype=np.float32)
        faiss.normalize_L2(vectors)

        index = faiss.IndexFlatIP(EMBED_DIM)
        index.add(vectors)

        faiss.write_index(index, str(INDEX_PATH))
        with open(META_PATH, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False)

        size_mb = INDEX_PATH.stat().st_size / 1_048_576
        print(f"[INFO] 인덱스 저장: {INDEX_PATH} ({size_mb:.1f} MB)")
        print(f"[INFO] 메타 저장:   {META_PATH}")
        print(f"[INFO] 벡터 수: {index.ntotal:,}  차원: {EMBED_DIM}")

    def search(
        self,
        query: str,
        category: str = "",
        area: str = "",
        top_k: int = 5,
    ) -> list[dict]:
        if not self._try_load():
            return []

        try:
            import faiss  # type: ignore
            import numpy as np
        except ImportError:
            return []

        q_vec = np.array(embed_texts([query if query.strip() else " "]), dtype=np.float32)
        faiss.normalize_L2(q_vec)

        has_filter = bool(category or area)
        search_k = min(top_k * CATEGORY_BUFFER if has_filter else top_k * 2, self._index.ntotal)
        distances, indices = self._index.search(q_vec, search_k)

        results: list[dict] = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx < 0 or len(results) >= top_k:
                break
            record = self._meta[idx]
            if category and record.get("category") != category:
                continue
            if area and record.get("area") != area:
                continue
            results.append({**record, "_score": float(dist)})

        return results


class PgVectorStore(BaseVectorStore):
    backend_name = "pgvector"

    def is_ready(self) -> bool:
        try:
            _ensure_django()
            from django.db import connection
            from django.db.utils import OperationalError, ProgrammingError
            from tour_api.models import KnowledgeChunk

            if connection.vendor != "postgresql":
                return False
            return KnowledgeChunk.objects.exclude(embedding__isnull=True).exists()
        except (OperationalError, ProgrammingError, ImportError):
            return False
        except Exception:
            return False

    def search(
        self,
        query: str,
        category: str = "",
        area: str = "",
        top_k: int = 5,
    ) -> list[dict]:
        try:
            _ensure_django()
            from django.db import connection
            from pgvector.django import CosineDistance
            from tour_api.models import KnowledgeChunk

            if connection.vendor != "postgresql":
                return []

            query_embedding = embed_texts([query if query.strip() else " "])[0]
            queryset = KnowledgeChunk.objects.exclude(embedding__isnull=True)
            if category:
                queryset = queryset.filter(category=category)
            if area:
                queryset = queryset.filter(area=area)

            queryset = queryset.annotate(distance=CosineDistance("embedding", query_embedding)).order_by("distance")[:top_k]

            results: list[dict] = []
            for chunk in queryset:
                score = 1.0 - float(getattr(chunk, "distance", 0.0))
                results.append(chunk.to_search_result(score=score))
            return results
        except Exception:
            return []


VectorStore = FaissVectorStore

_instances: dict[str, BaseVectorStore] = {}


def get_vector_store(backend: str | None = None) -> BaseVectorStore:
    selected = _normalize_backend(backend)
    if selected not in _instances:
        if selected == "pgvector":
            _instances[selected] = PgVectorStore()
        else:
            _instances[selected] = FaissVectorStore()
    return _instances[selected]


def _print_results(results: list[dict], query: str, category: str, area: str, backend: str) -> None:
    print(f"\nbackend={backend!r}  query={query!r}  category={category!r}  area={area!r}")
    print(f"결과 {len(results)}건:\n")
    for i, record in enumerate(results, 1):
        score = record.get("_score", 0.0)
        print(f"[{i}] score={score:.3f}  cat={record.get('category', '')}  area={record.get('area', '')}")
        print(f"  Q: {(record.get('question_ja') or '')[:80]}")
        print(f"  A: {(record.get('answer_ja') or '')[:80]}")
        print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="벡터 인덱스/검색 관리")
    parser.add_argument("--build", action="store_true", help="FAISS 인덱스 빌드")
    parser.add_argument("--force", action="store_true", help="기존 인덱스 덮어쓰기")
    parser.add_argument("--test", type=str, metavar="QUERY", help="테스트 검색 쿼리")
    parser.add_argument("--backend", type=str, default=os.environ.get("VECTOR_BACKEND", "faiss"), help="faiss | pgvector")
    parser.add_argument("--category", type=str, default="", help="카테고리 필터")
    parser.add_argument("--area", type=str, default="", help="지역 필터 (예: Seoul)")
    parser.add_argument("--top-k", type=int, default=5, help="반환 결과 수")
    args = parser.parse_args()

    backend = _normalize_backend(args.backend)
    store = get_vector_store(backend)

    if args.build:
        if backend != "faiss":
            print("[ERROR] --build 는 FAISS 백엔드에서만 지원합니다.")
            sys.exit(1)
        assert isinstance(store, FaissVectorStore)
        store.build(force=args.force)

    if args.test:
        if not store.is_ready():
            print(f"[ERROR] {backend} 백엔드가 준비되지 않았습니다.")
            sys.exit(1)
        _print_results(
            store.search(args.test, category=args.category, area=args.area, top_k=args.top_k),
            query=args.test,
            category=args.category,
            area=args.area,
            backend=backend,
        )
