from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from googleapiclient.discovery import Resource, build
from googleapiclient.errors import HttpError
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from gcli.auth import load_credentials

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _is_retryable(exc: BaseException) -> bool:
    if not isinstance(exc, HttpError):
        return False
    status = getattr(exc.resp, "status", None)
    return status in RETRYABLE_STATUS


class GmailClient:
    def __init__(self, service: Resource) -> None:
        self.service = service

    @classmethod
    def from_credentials_dir(cls, credentials_dir: Path) -> GmailClient:
        creds = load_credentials(credentials_dir)
        service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        return cls(service)

    @retry(
        reraise=True,
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=16),
        retry=retry_if_exception(_is_retryable),
    )
    def _list_messages(
        self,
        query: str,
        page_token: str | None,
        max_results: int,
    ) -> dict[str, Any]:
        return (
            self.service.users()
            .messages()
            .list(userId="me", q=query, pageToken=page_token, maxResults=max_results)
            .execute()
        )

    @retry(
        reraise=True,
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=16),
        retry=retry_if_exception(_is_retryable),
    )
    def _get_message(self, message_id: str) -> dict[str, Any]:
        return (
            self.service.users()
            .messages()
            .get(
                userId="me",
                id=message_id,
                format="full",
            )
            .execute()
        )

    @retry(
        reraise=True,
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=16),
        retry=retry_if_exception(_is_retryable),
    )
    def _list_labels(self) -> dict[str, Any]:
        return self.service.users().labels().list(userId="me").execute()

    @retry(
        reraise=True,
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=16),
        retry=retry_if_exception(_is_retryable),
    )
    def _create_label(self, name: str) -> dict[str, Any]:
        return (
            self.service.users()
            .labels()
            .create(
                userId="me",
                body={
                    "name": name,
                    "labelListVisibility": "labelShow",
                    "messageListVisibility": "show",
                },
            )
            .execute()
        )

    def list_label_names(self) -> set[str]:
        labels = self._list_labels().get("labels", [])
        return {label.get("name", "") for label in labels}

    def ensure_nested_label(self, label_name: str) -> list[str]:
        existing = self.list_label_names()
        created: list[str] = []
        current: list[str] = []
        for segment in label_name.split("/"):
            current.append(segment)
            candidate = "/".join(current)
            if candidate in existing:
                continue
            self._create_label(candidate)
            existing.add(candidate)
            created.append(candidate)
        return created

    def search_messages(self, query: str, max_results: int) -> list[dict[str, str]]:
        results: list[dict[str, str]] = []
        page_token: str | None = None

        while len(results) < max_results:
            batch_size = min(500, max_results - len(results))
            response = self._list_messages(
                query=query,
                page_token=page_token,
                max_results=batch_size,
            )
            messages = response.get("messages", [])
            for message in messages:
                full = self._get_message(message["id"])
                headers = full.get("payload", {}).get("headers", [])
                results.append(
                    {
                        "id": full.get("id", ""),
                        "from": _header(headers, "From"),
                        "to": _header(headers, "To"),
                        "cc": _header(headers, "Cc"),
                        "bcc": _header(headers, "Bcc"),
                        "subject": _header(headers, "Subject"),
                        "date": _header(headers, "Date"),
                        "snippet": full.get("snippet", ""),
                        "body": _extract_body_text(full.get("payload", {})),
                    }
                )
                if len(results) >= max_results:
                    break
            page_token = response.get("nextPageToken")
            if not page_token:
                break

        return results


def _header(headers: list[dict[str, str]], name: str) -> str:
    lowered = name.lower()
    for header in headers:
        if header.get("name", "").lower() == lowered:
            return header.get("value", "")
    return ""


def _decode_body_data(data: str) -> str:
    if not data:
        return ""
    padding = "=" * (-len(data) % 4)
    try:
        return base64.urlsafe_b64decode(data + padding).decode("utf-8", errors="ignore")
    except (ValueError, TypeError):
        return ""


def _extract_body_text(payload: dict[str, Any]) -> str:
    parts = payload.get("parts", [])
    if parts:
        for part in parts:
            body = _extract_body_text(part)
            if body:
                return body

    mime_type = payload.get("mimeType", "")
    data = payload.get("body", {}).get("data", "")
    if mime_type.startswith("text/plain"):
        return _decode_body_data(data)
    if not parts:
        return _decode_body_data(data)
    return ""
