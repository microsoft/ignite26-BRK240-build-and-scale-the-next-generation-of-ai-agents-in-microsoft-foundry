"""Machine-readable error envelope shared by REST (HTTP status) and MCP (isError + JSON text)."""

from __future__ import annotations

from typing import Any


class DealSystemError(Exception):
    def __init__(self, code: str, http_status: int, message: str, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.http_status = http_status
        self.message = message
        self.details = details

    def to_dict(self) -> dict[str, Any]:
        return {"error": {"code": self.code, "http_status": self.http_status, "message": self.message, **self.details}}


def requires_human_approval(message: str, **details: Any) -> DealSystemError:
    return DealSystemError("REQUIRES_HUMAN_APPROVAL", 403, message, next_action="request_approval", **details)


def unauthenticated() -> DealSystemError:
    return DealSystemError("UNAUTHENTICATED", 401, "Missing or invalid x-api-key header.")


def forbidden(message: str, **details: Any) -> DealSystemError:
    return DealSystemError("FORBIDDEN", 403, message, **details)


def not_found(kind: str, ident: str) -> DealSystemError:
    code = "DEAL_NOT_FOUND" if kind == "deal" else "APPROVAL_NOT_FOUND"
    return DealSystemError(code, 404, f"{kind} {ident!r} not found")


def invalid_argument(message: str) -> DealSystemError:
    return DealSystemError("INVALID_ARGUMENT", 422, message)


def invalid_state(message: str, **details: Any) -> DealSystemError:
    return DealSystemError("INVALID_STATE", 409, message, **details)


def invalid_terms(message: str) -> DealSystemError:
    return DealSystemError("INVALID_TERMS", 422, message)
