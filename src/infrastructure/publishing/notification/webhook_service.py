"""
Webhook notification service for releases.
"""

import logging

import httpx

from src.type_definitions.common import JSONObject

logger = logging.getLogger(__name__)


class WebhookService:
    """Service for sending webhook notifications."""

    def __init__(self, timeout: int = 10):
        """
        Initialize webhook service.

        Args:
            timeout: Request timeout in seconds
        """
        self.timeout = timeout

    async def send_webhook(
        self,
        url: str,
        payload: JSONObject,
        headers: dict[str, str] | None = None,
    ) -> bool:
        """
        Send webhook notification.

        Args:
            url: Webhook URL
            payload: Payload dictionary
            headers: Optional custom headers

        Returns:
            True if sent successfully, False otherwise
        """
        try:
            request_headers = {"Content-Type": "application/json"}
            if headers:
                request_headers.update(headers)

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers=request_headers,
                )
                response.raise_for_status()

        except Exception:
            logger.exception("Failed to send webhook to %s", url)
            return False
        else:
            logger.info("Webhook sent successfully to %s", url)
            return True

    async def send_release_webhook(
        self,
        webhook_urls: list[str],
        version: str,
        doi: str,
        release_notes: str | None = None,
        metadata: JSONObject | None = None,
    ) -> dict[str, bool]:
        """
        Send release notification webhooks.

        Args:
            webhook_urls: List of webhook URLs
            version: Release version
            doi: DOI for the release
            release_notes: Optional release notes
            metadata: Optional additional metadata

        Returns:
            Dictionary mapping webhook URLs to success status
        """
        payload: JSONObject = {
            "event": "release.published",
            "package": "Artana Resource Library",
            "version": version,
            "doi": doi,
            "doi_url": f"https://doi.org/{doi}",
            "release_notes": release_notes,
            "metadata": metadata or {},
        }

        results: dict[str, bool] = {}
        for url in webhook_urls:
            success = await self.send_webhook(url, payload)
            results[url] = success

        return results
