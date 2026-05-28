from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from pgvector.django import VectorField


EMBED_DIM = 512


def _anonymous_id() -> str:
    return f"anon_{uuid.uuid4().hex}"


class ChatSession(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        ARCHIVED = "archived", "Archived"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    anonymous_id = models.CharField(max_length=64, default=_anonymous_id, db_index=True)
    reply_language = models.CharField(max_length=10, default="日本語")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    current_latitude = models.FloatField(null=True, blank=True)
    current_longitude = models.FloatField(null=True, blank=True)
    last_message_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]


class ChatMessage(models.Model):
    class Role(models.TextChoices):
        USER = "user", "User"
        ASSISTANT = "assistant", "Assistant"

    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=16, choices=Role.choices)
    content = models.TextField()
    translated_ko = models.TextField(blank=True)
    category = models.CharField(max_length=32, blank=True)
    keyword = models.CharField(max_length=128, blank=True)
    sources_used = models.JSONField(default=list, blank=True)
    rag_count = models.PositiveIntegerField(default=0)
    places_count = models.PositiveIntegerField(default=0)
    is_fallback = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["session", "created_at"]),
            models.Index(fields=["role", "created_at"]),
        ]


class TravelerProfile(models.Model):
    session = models.OneToOneField(ChatSession, on_delete=models.CASCADE, related_name="traveler_profile")
    budget_level = models.CharField(max_length=32, blank=True)
    interests = models.JSONField(default=list, blank=True)
    personality_type = models.CharField(max_length=32, blank=True)
    home_country = models.CharField(max_length=64, blank=True)
    travel_style = models.CharField(max_length=64, blank=True)
    hotel_booked = models.BooleanField(null=True, blank=True)
    arrival_airport = models.CharField(max_length=64, blank=True)
    arrival_time = models.DateTimeField(null=True, blank=True)
    return_time = models.DateTimeField(null=True, blank=True)
    extra_preferences = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class TravelPlanSnapshot(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="travel_plan_snapshots",
    )
    session_key = models.CharField(max_length=64, blank=True, db_index=True)
    title = models.CharField(max_length=255, blank=True)
    profile = models.JSONField(default=dict, blank=True)
    plan_text = models.TextField(blank=True)
    places = models.JSONField(default=list, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["user", "updated_at"]),
            models.Index(fields=["session_key", "updated_at"]),
        ]


class KnowledgeDocument(models.Model):
    source_type = models.CharField(max_length=32, default="jsonl")
    source_name = models.CharField(max_length=255, db_index=True)
    source_uri = models.CharField(max_length=512, blank=True)
    title = models.CharField(max_length=255, blank=True)
    domain = models.CharField(max_length=64, blank=True)
    category = models.CharField(max_length=32, blank=True)
    area = models.CharField(max_length=64, blank=True)
    language = models.CharField(max_length=16, default="ja")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["source_name", "id"]
        constraints = [
            models.UniqueConstraint(fields=["source_type", "source_name"], name="uniq_knowledge_source"),
        ]


class KnowledgeChunk(models.Model):
    document = models.ForeignKey(KnowledgeDocument, on_delete=models.CASCADE, related_name="chunks")
    external_id = models.CharField(max_length=128)
    chunk_index = models.PositiveIntegerField(default=0)
    question_ja = models.TextField(blank=True)
    answer_ja = models.TextField(blank=True)
    answer_ko = models.TextField(blank=True)
    chunk_text = models.TextField()
    category = models.CharField(max_length=32, blank=True)
    area = models.CharField(max_length=64, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    embedding = VectorField(dimensions=EMBED_DIM, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["document_id", "chunk_index"]
        constraints = [
            models.UniqueConstraint(fields=["document", "external_id"], name="uniq_document_external_id"),
        ]
        indexes = [
            models.Index(fields=["category"]),
            models.Index(fields=["area"]),
            models.Index(fields=["external_id"]),
            models.Index(fields=["document", "chunk_index"]),
        ]

    def to_search_result(self, score: float | None = None) -> dict:
        result = {
            "id": self.external_id,
            "category": self.category,
            "area": self.area,
            "question_ja": self.question_ja,
            "answer_ja": self.answer_ja,
            "answer_ko": self.answer_ko,
        }
        if score is not None:
            result["_score"] = score
        return result


class RetrievalLog(models.Model):
    session = models.ForeignKey(
        ChatSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="retrieval_logs",
    )
    message = models.ForeignKey(
        ChatMessage,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="retrieval_logs",
    )
    query = models.TextField()
    backend = models.CharField(max_length=32)
    category_filter = models.CharField(max_length=32, blank=True)
    area_filter = models.CharField(max_length=64, blank=True)
    top_k = models.PositiveSmallIntegerField(default=5)
    result_chunk_ids = models.JSONField(default=list, blank=True)
    result_scores = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["backend", "created_at"]),
            models.Index(fields=["session", "created_at"]),
        ]
