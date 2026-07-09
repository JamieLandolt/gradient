"""Real AI providers backed by a hosted OpenAI-compatible LLM (Alibaba Bailian / Qwen).

These satisfy the same `Protocol`s as the mocks and return the same shapes, so
nothing outside this module changes. The deterministic engines still supply
every grade/prerequisite fact (grounding, FR-3.7.2/3.8.3); this layer only
extracts structure, ranks, schedules, and phrases.

Privacy note (NFR-5.3.4 deviation, accepted for the demo): payloads contain only
public course text and already-computed numeric facts — never a student's name,
email, or id. Extraction/embeddings/search see public course text only.
"""

import json
import time
from collections.abc import Iterator
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from app.config import Settings
from app.domain.planning.models import PrereqNode
from app.providers.interfaces import ExtractedAssessment, ExtractedProfile
from app.providers.prereq_parser import (
    COURSE_CODE_PATTERN,
    PrereqParseError,
    parse_prereq_expression,
)

_RETRY_BACKOFF_S = 0.5
_EXTRACTION_TEMPERATURE = 0.1
_ADVISORY_TEMPERATURE = 0.3


class AIProviderError(RuntimeError):
    """Raised when the hosted model call fails after retries or returns junk."""


# ── HTTP client ──────────────────────────────────────────────────────────────
class OpenAICompatibleClient:
    """One shared httpx client hitting the /chat/completions and /embeddings routes."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._http = httpx.Client(
            base_url=settings.ai_base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {settings.dashscope_api_key}"},
            timeout=settings.ai_request_timeout_s,
            # No keep-alive: the hosted endpoint can close idle pooled connections,
            # which surfaced as intermittent "SSL: UNEXPECTED_EOF" on reuse. A fresh
            # connection per call is robust at our low call volume.
            limits=httpx.Limits(max_keepalive_connections=0),
        )

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        attempts = max(self._settings.ai_max_retries, 0) + 1
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                response = self._http.post(path, json=payload)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt + 1 < attempts:
                    time.sleep(_RETRY_BACKOFF_S * (attempt + 1))
        raise AIProviderError(f"AI request to {path} failed: {last_error}") from last_error

    def chat_json(self, system: str, user: str) -> dict[str, Any]:
        body = self._post(
            "/chat/completions",
            {
                "model": self._settings.ai_chat_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "response_format": {"type": "json_object"},
                "temperature": _EXTRACTION_TEMPERATURE,
            },
        )
        content = _message_content(body)
        try:
            return json.loads(content)
        except (json.JSONDecodeError, TypeError) as exc:
            raise AIProviderError(f"Model did not return valid JSON: {content[:200]}") from exc

    def chat_text(self, system: str, user: str) -> str:
        body = self._post(
            "/chat/completions",
            {
                "model": self._settings.ai_chat_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": _ADVISORY_TEMPERATURE,
            },
        )
        return _message_content(body)

    def chat_text_stream(self, system: str, user: str) -> Iterator[str]:
        """Stream assistant tokens via SSE (OpenAI-compatible `stream: true`).

        Only the initial connection is guarded; once tokens start flowing we do
        not retry (a mid-stream retry would duplicate already-emitted text).
        """
        payload = {
            "model": self._settings.ai_chat_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": _ADVISORY_TEMPERATURE,
            "stream": True,
        }
        try:
            with self._http.stream("POST", "/chat/completions", json=payload) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    token = _sse_token(line)
                    if token:
                        yield token
        except httpx.HTTPError as exc:
            raise AIProviderError(f"AI stream to /chat/completions failed: {exc}") from exc

    def embed(self, text: str) -> list[float]:
        body = self._post(
            "/embeddings",
            {
                "model": self._settings.ai_embedding_model,
                "input": text,
                "dimensions": self._settings.embedding_dim,
            },
        )
        try:
            return list(body["data"][0]["embedding"])
        except (KeyError, IndexError, TypeError) as exc:
            raise AIProviderError("Embedding response was malformed") from exc

    def close(self) -> None:
        self._http.close()


def _sse_token(line: str) -> str | None:
    """Extract the delta content from one SSE line, or None to skip it."""
    if not line or not line.startswith("data:"):
        return None
    data = line[len("data:") :].strip()
    if not data or data == "[DONE]":
        return None
    try:
        chunk = json.loads(data)
        return chunk["choices"][0]["delta"].get("content") or None
    except (json.JSONDecodeError, KeyError, IndexError, TypeError):
        return None


def _message_content(body: dict[str, Any]) -> str:
    try:
        return body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise AIProviderError("Chat response was malformed") from exc


# ── Extraction (FR-3.5.1) ────────────────────────────────────────────────────
_EXTRACTION_SYSTEM = (
    "You extract structured data from a University of Queensland course profile "
    "(ECP). Return ONLY a JSON object with these keys: course_code (e.g. 'COMP3506'), "
    "course_title, units (number), description, version_label (e.g. '2026S2'), "
    "assessments (array of objects with name, weight as a number out of 100, max_mark, "
    "due_date as YYYY-MM-DD or null, hurdle_min_percent as a number or null, "
    "hurdle_description or null), grade_cutoffs (object mapping the grades 7..1 to their "
    "minimum final percentage, or null if not stated), and prerequisite (a single boolean "
    "expression string using course codes joined by 'and'/'or' with parentheses, e.g. "
    "'CSSE2002 and (MATH1061 or MATH1071)', or null). Do not invent values; use null when "
    "the profile does not state something."
)


class _AssessmentReply(BaseModel):
    # Lenient: catalogue pages list "assessment methods" without weights, and the
    # model may return partial/null fields. Weightless items are dropped in extract().
    name: str | None = None
    weight: float | None = None
    max_mark: float | None = None
    due_date: str | None = None
    hurdle_min_percent: float | None = None
    hurdle_description: str | None = None


class _ExtractionReply(BaseModel):
    course_code: str
    course_title: str
    units: float = 2.0
    description: str = ""
    version_label: str = "unknown"
    # Catalogue pages have no assessment section, so the model may return null.
    assessments: list[_AssessmentReply] | None = None
    grade_cutoffs: dict[int, float] | None = None
    prerequisite: str | None = None


class OpenAICompatibleExtractionProvider:
    def __init__(self, client: OpenAICompatibleClient):
        self._client = client

    def extract(self, text: str) -> ExtractedProfile:
        raw = self._client.chat_json(_EXTRACTION_SYSTEM, text)
        try:
            parsed = _ExtractionReply.model_validate(raw)
        except ValidationError as exc:
            raise ValueError(f"Extraction returned an unexpected structure: {exc}") from exc

        code = parsed.course_code.upper().strip()
        if not COURSE_CODE_PATTERN.match(code):
            raise ValueError(f"Extraction returned an invalid course code: {parsed.course_code!r}")

        warnings: list[str] = []
        assessments = tuple(
            ExtractedAssessment(
                name=item.name,
                weight=item.weight,
                max_mark=item.max_mark or 100.0,
                due_date=item.due_date,
                hurdle_min_percent=item.hurdle_min_percent,
                hurdle_description=item.hurdle_description,
            )
            # Keep only genuine weighted items; drop catalogue method-list noise.
            for item in (parsed.assessments or [])
            if item.name and item.weight is not None
        )
        if not assessments:
            warnings.append("No assessment items were recognised")
        else:
            total = sum(item.weight for item in assessments)
            if abs(total - 100.0) > 0.01:
                warnings.append(f"Assessment weights sum to {total:g}, not 100")

        prereq_tree: PrereqNode | None = None
        if parsed.prerequisite:
            try:
                prereq_tree = parse_prereq_expression(parsed.prerequisite)
            except PrereqParseError:
                # Never silently satisfied — keep as a note for manual review.
                prereq_tree = PrereqNode.note(parsed.prerequisite)
                warnings.append(
                    "Prerequisite text could not be fully parsed; flagged for manual check"
                )

        return ExtractedProfile(
            course_code=code,
            course_title=parsed.course_title,
            units=parsed.units,
            description=parsed.description,
            version_label=parsed.version_label,
            assessments=assessments,
            grade_cutoffs=parsed.grade_cutoffs,
            prerequisite_raw=parsed.prerequisite,
            prerequisite_tree=prereq_tree,
            warnings=tuple(warnings),
        )


# ── Recommendations (FR-3.7.x) ───────────────────────────────────────────────
_RECOMMEND_SYSTEM = (
    "You are a university course-recommendation aid. Given a student's interests and a list "
    "of candidate courses (each with a code, title, description, and prereq_status), pick and "
    "rank the best matches. Return ONLY a JSON object {\"recommendations\": [{course_code, "
    "reason, score}]} where reason is one short sentence and score is 0..10. Do not change or "
    "assert prerequisite status — that is provided externally. Only use course codes from the "
    "candidate list."
)


class OpenAICompatibleRecommendationProvider:
    def __init__(self, client: OpenAICompatibleClient):
        self._client = client

    def recommend(
        self,
        candidates: list[dict[str, Any]],
        interests: list[str],
        completed_codes: frozenset[str],
        limit: int,
    ) -> list[dict[str, Any]]:
        available = [c for c in candidates if c["code"] not in completed_codes]
        by_code = {c["code"]: c for c in available}
        payload = {
            "interests": interests,
            "limit": limit,
            "courses": [
                {
                    "code": c["code"],
                    "title": c["title"],
                    "description": c.get("description", ""),
                    "prereq_status": c.get("prereq_status", "not_met"),
                }
                for c in available
            ],
        }
        reply = self._client.chat_json(_RECOMMEND_SYSTEM, json.dumps(payload))
        results: list[dict[str, Any]] = []
        for rank, item in enumerate(reply.get("recommendations", [])[:limit], start=1):
            code = item.get("course_code")
            if code not in by_code:
                continue
            results.append(
                {
                    "course_code": code,
                    "rank": rank,
                    "reason": item.get("reason", ""),
                    # prereq_status ALWAYS from the deterministic engine, never the model:
                    "prereq_status": by_code[code].get("prereq_status", "not_met"),
                    "score": float(item.get("score", 0.0)),
                }
            )
        return results


# ── Study plans (FR-3.8.x) ───────────────────────────────────────────────────
_STUDY_PLAN_SYSTEM = (
    "You build a personalised study schedule. Given a course, a start date, a target grade, "
    "the required average percent (already computed — cite it, do not recompute), and the "
    "remaining assessment items (name, weight, due_date), produce study sessions leading up to "
    "each item. Return ONLY a JSON object {\"sessions\": [{session_date (YYYY-MM-DD), "
    "duration_minutes, focus, assessment_name}]}. Weight heavier and sooner items more. Every "
    "figure you mention must come from the input."
)


class OpenAICompatibleStudyPlanProvider:
    def __init__(self, client: OpenAICompatibleClient):
        self._client = client

    def generate(
        self,
        course_code: str,
        items: list[dict[str, Any]],
        target_grade: int,
        required_average_percent: float | None,
        start_date: str,
    ) -> list[dict[str, Any]]:
        remaining = [item for item in items if item.get("score") is None]
        payload = {
            "course_code": course_code,
            "start_date": start_date,
            "target_grade": target_grade,
            "required_average_percent": required_average_percent,
            "assessments": [
                {"name": i["name"], "weight": i["weight"], "due_date": i.get("due_date")}
                for i in remaining
            ],
        }
        reply = self._client.chat_json(_STUDY_PLAN_SYSTEM, json.dumps(payload))
        sessions: list[dict[str, Any]] = []
        for order, session in enumerate(reply.get("sessions", [])):
            sessions.append(
                {
                    "session_date": session.get("session_date"),
                    "duration_minutes": int(session.get("duration_minutes", 60)),
                    "focus": session.get("focus", ""),
                    "assessment_name": session.get("assessment_name", ""),
                    "sort_order": order,
                }
            )
        return sessions


# ── Assistant (FR-3.9.3) ─────────────────────────────────────────────────────
_ASSISTANT_SYSTEM = (
    "You are Gradient's study assistant. Answer the student's question using ONLY the verified "
    "facts provided (which come from Gradient's deterministic calculators). Never invent grades, "
    "percentages, or prerequisite outcomes. Be concise and end by reminding the student that the "
    "official course profile (ECP) and university records are authoritative."
)


class OpenAICompatibleAssistantProvider:
    def __init__(self, client: OpenAICompatibleClient):
        self._client = client

    def answer(self, question: str, facts: dict[str, Any]) -> str:
        return self._client.chat_text(_ASSISTANT_SYSTEM, _assistant_prompt(question, facts))

    def stream_answer(self, question: str, facts: dict[str, Any]) -> Iterator[str]:
        return self._client.chat_text_stream(
            _ASSISTANT_SYSTEM, _assistant_prompt(question, facts)
        )


def _assistant_prompt(question: str, facts: dict[str, Any]) -> str:
    facts_block = "\n".join(f"- {key}: {value}" for key, value in sorted(facts.items()))
    return (
        f'Student question: "{question.strip()}"\n\n'
        f"Verified facts from Gradient's deterministic calculators:\n{facts_block}"
    )


# ── Embeddings (FR-3.9.1) ────────────────────────────────────────────────────
class OpenAICompatibleEmbeddingProvider:
    def __init__(self, client: OpenAICompatibleClient, model_name: str):
        self._client = client
        self._model_name = model_name

    @property
    def model_name(self) -> str:
        return self._model_name

    def embed(self, text: str) -> list[float]:
        return self._client.embed(text)
