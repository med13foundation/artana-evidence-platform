"""
Password hashing utilities for Artana Resource Library.

Provides secure password hashing with truncation prevention and strength validation.
"""

import hashlib
import re
import secrets
import string

import bcrypt

from src.domain.services.security.password_hasher import PasswordHasherService
from src.type_definitions.security import HashInfo, PasswordAnalysis


class PasswordHasher(PasswordHasherService):
    """
    Secure password hashing with bcrypt and truncation prevention.

    Features:
    - bcrypt hashing with 12 rounds (default)
    - Automatic pre-hashing for passwords > 72 bytes
    - Password strength validation
    - Secure random password generation
    """

    def __init__(self) -> None:
        # Password policy configuration
        self.min_length = 8
        self.max_length = 128  # Reasonable limit to prevent DoS
        # Analysis thresholds
        self.length_strong = 12
        self.length_medium = 8
        self.score_strong = 4
        self.bcrypt_max_bytes = 72

    def hash_password(self, plain_password: str) -> str:
        """
        Securely hash a password with truncation prevention.

        This method automatically handles long passwords by pre-hashing them
        with SHA256 before passing to bcrypt, preventing truncation attacks.

        Args:
            plain_password: The plain text password

        Returns:
            Hashed password string (bcrypt format)

        Raises:
            ValueError: If password violates policy or hashing fails
        """
        self._validate_password_policy(plain_password)

        try:
            # Handle long passwords by pre-hashing to prevent truncation
            password_to_hash = plain_password
            if len(plain_password.encode("utf-8")) > self.bcrypt_max_bytes:
                # Pre-hash long passwords with SHA256
                password_to_hash = hashlib.sha256(
                    plain_password.encode("utf-8"),
                ).hexdigest()

            # Ensure password is not longer than 72 bytes (bcrypt limit)
            password_bytes = password_to_hash.encode("utf-8")
            if len(password_bytes) > self.bcrypt_max_bytes:
                password_to_hash = password_bytes[: self.bcrypt_max_bytes].decode(
                    "utf-8",
                    errors="ignore",
                )

            # Hash with bcrypt (12 rounds)
            salt = bcrypt.gensalt(rounds=12)
            hashed_bytes = bcrypt.hashpw(password_to_hash.encode("utf-8"), salt)
            return hashed_bytes.decode("utf-8")

        except Exception as exc:
            message = f"Password hashing failed: {exc!s}"
            raise ValueError(message) from exc

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """
        Verify a password against its hash.

        Args:
            plain_password: Plain text password to verify
            hashed_password: Previously hashed password

        Returns:
            True if password matches hash, False otherwise

        Raises:
            ValueError: If inputs are invalid
        """
        if not plain_password or not hashed_password:
            return False

        try:
            # Handle verification with pre-hashed passwords
            password_to_verify = plain_password
            if len(plain_password.encode("utf-8")) > self.bcrypt_max_bytes:
                # Pre-hash long passwords with SHA256 for verification
                password_to_verify = hashlib.sha256(
                    plain_password.encode("utf-8"),
                ).hexdigest()

            # Ensure password is not longer than 72 bytes (bcrypt limit)
            password_bytes = password_to_verify.encode("utf-8")
            if len(password_bytes) > self.bcrypt_max_bytes:
                password_to_verify = password_bytes[:72].decode(
                    "utf-8",
                    errors="ignore",
                )

            return bcrypt.checkpw(
                password_to_verify.encode("utf-8"),
                hashed_password.encode("utf-8"),
            )
        except Exception:  # noqa: BLE001 - every error implies invalid password
            # Every runtime error during verification yields an invalid result
            return False

    def is_password_strong(self, password: str) -> bool:
        """
        Check if password meets strength requirements.

        Args:
            password: Password to check

        Returns:
            True if password is strong enough
        """
        try:
            self._validate_password_policy(password)
        except ValueError:
            return False
        else:
            return True

    def generate_secure_password(self, length: int = 16) -> str:
        """
        Generate a cryptographically secure random password.

        Args:
            length: Desired password length (default: 16)

        Returns:
            Secure random password string

        Raises:
            ValueError: If length is invalid
        """
        if length < self.min_length or length > self.max_length:
            length = 16  # Default fallback

        # Generate password with mix of character types
        chars = string.ascii_letters + string.digits + string.punctuation
        return "".join(secrets.choice(chars) for _ in range(length))

    def get_hash_info(self, hashed_password: str) -> HashInfo:
        """
        Get information about a password hash.

        Args:
            hashed_password: The hashed password

        Returns:
            Dictionary with hash information or error details
        """
        try:
            # Check if it's a valid bcrypt hash
            if hashed_password.startswith(("$2b$", "$2a$")):
                result: HashInfo = {
                    "scheme": "bcrypt",
                    "needs_update": False,  # Could implement version checking
                    "is_valid": True,
                }
            else:
                result = {
                    "scheme": "unknown",
                    "needs_update": False,
                    "is_valid": False,
                    "error": "Not a bcrypt hash",
                }
        except Exception as exc:  # noqa: BLE001 - conservative handling
            return {
                "scheme": None,
                "needs_update": False,
                "is_valid": False,
                "error": str(exc),
            }
        else:
            return result

    def _validate_password_policy(self, password: str) -> None:
        """
        Validate password against security policy.

        Args:
            password: Password to validate

        Raises:
            ValueError: If password violates policy
        """
        if not password:
            message = "Password cannot be empty"
            raise ValueError(message)

        if len(password) < self.min_length:
            message = f"Password must be at least {self.min_length} characters long"
            raise ValueError(message)

        if len(password) > self.max_length:
            message = f"Password cannot exceed {self.max_length} characters"
            raise ValueError(message)

        # Check for basic complexity (configurable)
        if not re.search(r"[A-Za-z]", password):
            message = "Password must contain at least one letter"
            raise ValueError(message)

        if not re.search(r"[0-9]", password):
            message = "Password must contain at least one number"
            raise ValueError(message)

        # Additional checks can be added here:
        # - No common passwords
        # - No sequential characters
        # - Dictionary word checks
        # - Personal information checks

    def check_password_complexity(  # noqa: C901, PLR0912
        self,
        password: str,
    ) -> PasswordAnalysis:
        """
        Detailed password complexity analysis.

        Args:
            password: Password to analyze

        Returns:
            Dictionary with complexity metrics
        """
        analysis: PasswordAnalysis = {
            "length": len(password),
            "has_lowercase": bool(re.search(r"[a-z]", password)),
            "has_uppercase": bool(re.search(r"[A-Z]", password)),
            "has_digit": bool(re.search(r"[0-9]", password)),
            "has_special": bool(re.search(r"[^A-Za-z0-9]", password)),
            "is_strong": False,
            "score": 0,
            "issues": [],
        }

        # Length scoring
        if analysis["length"] >= self.length_strong:
            analysis["score"] += 2
        elif analysis["length"] >= self.length_medium:
            analysis["score"] += 1

        # Character variety scoring
        if analysis["has_lowercase"]:
            analysis["score"] += 1
        if analysis["has_uppercase"]:
            analysis["score"] += 1
        if analysis["has_digit"]:
            analysis["score"] += 1
        if analysis["has_special"]:
            analysis["score"] += 1

        # Issue detection
        if analysis["length"] < self.min_length:
            analysis["issues"].append(
                f"Too short (minimum {self.min_length} characters)",
            )

        if not analysis["has_lowercase"]:
            analysis["issues"].append("Missing lowercase letter")

        if not analysis["has_uppercase"]:
            analysis["issues"].append("Missing uppercase letter")

        if not analysis["has_digit"]:
            analysis["issues"].append("Missing number")

        if not analysis["has_special"]:
            analysis["issues"].append("Missing special character")

        # Sequential character check
        if re.search(r"(012|123|234|345|456|567|678|789|890)", password):
            analysis["issues"].append("Contains sequential numbers")
            analysis["score"] -= 1

        if re.search(
            r"(abc|bcd|cde|def|efg|fgh|ghi|hij|ijk|jkl|klm|lmn|mno|nop|opq|pqr|qrs|rst|stu|tuv|uvw|vwx|wxy|xyz)",
            password.lower(),
        ):
            analysis["issues"].append("Contains sequential letters")
            analysis["score"] -= 1

        # Strength determination
        analysis["is_strong"] = (
            analysis["score"] >= self.score_strong and len(analysis["issues"]) == 0
        )

        return analysis
