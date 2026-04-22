from __future__ import annotations

from typing import Protocol


class PasswordHasherService(Protocol):
    """Protocol for password hashing utilities used in application layer."""

    def hash_password(self, plain_password: str) -> str:
        """Create a secure hash from a plain text password."""

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify that a plain text password matches the stored hash."""

    def is_password_strong(self, password: str) -> bool:
        """Determine whether the password satisfies strength requirements."""

    def generate_secure_password(self, length: int = 16) -> str:
        """Generate a secure random password of the given length."""
