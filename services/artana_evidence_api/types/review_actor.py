"""The identity of whoever decided a proposal, review item, or approval.

A review decision without an actor is an assertion nobody is accountable for.
The service authenticates a user on every decision route, so the identity is
always available at the moment of the decision -- this type exists to carry it
from that request down into the durable record instead of dropping it.

Deliberately a value object with no behavior: it is stored on records, returned
on responses, and never used to make an authorization choice.  Authorization
happens in the request dependency; this is the receipt.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

_MAX_EMAIL_LENGTH = 320


class ReviewActor(BaseModel):
    """One accountable identity attached to a recorded review decision."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    user_id: str = Field(min_length=1, max_length=64)
    email: str = Field(min_length=1, max_length=_MAX_EMAIL_LENGTH)

    @classmethod
    def from_stored(
        cls,
        *,
        user_id: str | None,
        email: str | None,
    ) -> ReviewActor | None:
        """Rebuild an actor from persisted columns, or None when unattributed.

        Rows written before decisions carried an actor have both columns NULL,
        and a half-written pair is meaningless, so anything short of both parts
        reads back as no attribution rather than as a partial identity.
        """
        if user_id is None or email is None:
            return None
        normalized_user_id = user_id.strip()
        normalized_email = email.strip()
        if normalized_user_id == "" or normalized_email == "":
            return None
        return cls(user_id=normalized_user_id, email=normalized_email)


__all__ = ["ReviewActor"]
