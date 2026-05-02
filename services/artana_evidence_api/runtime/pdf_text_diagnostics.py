"""PDF text-extraction diagnostics for document ingestion runtime paths."""

from __future__ import annotations

from dataclasses import dataclass

from artana_evidence_api.document_extraction import normalize_text_document
from artana_evidence_api.document_extraction_contracts import DocumentTextExtraction
from artana_evidence_api.types.common import JSONObject
from fastapi import HTTPException, status

_SCANNED_PDF_NO_TEXT_REASON = "scanned_pdf_no_text"
_PARTIAL_PDF_OCR_NEEDED_REASON = "partial_pdf_ocr_needed"
_PDF_NO_PAGES_REASON = "pdf_no_pages"
_PDF_NO_EXTRACTABLE_TEXT_REASON = "pdf_no_extractable_text"
_MAX_PAGE_NUMBERS_IN_MESSAGE = 10


@dataclass(frozen=True, slots=True)
class PdfTextDiagnostic:
    """Actionable diagnostic for a PDF that needs OCR before ingestion."""

    reason_code: str
    message: str
    ocr_required: bool
    page_count: int | None
    pages_without_text: tuple[int, ...] = ()

    def as_detail(self) -> JSONObject:
        detail: JSONObject = {
            "reason_code": self.reason_code,
            "message": self.message,
            "ocr_required": self.ocr_required,
        }
        if self.page_count is not None:
            detail["page_count"] = self.page_count
        if self.pages_without_text:
            detail["pages_without_text"] = list(self.pages_without_text)
        return detail

    def as_metadata(self) -> JSONObject:
        metadata: JSONObject = {
            "pdf_text_extraction_reason_code": self.reason_code,
            "pdf_text_extraction_message": self.message,
            "ocr_required": self.ocr_required,
        }
        if self.pages_without_text:
            metadata["pdf_pages_without_text"] = list(self.pages_without_text)
        return metadata


class PdfTextDiagnosticError(HTTPException):
    """HTTP error carrying a structured PDF text-extraction diagnostic."""

    def __init__(self, diagnostic: PdfTextDiagnostic) -> None:
        self.diagnostic = diagnostic
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=diagnostic.as_detail(),
        )


def _format_pdf_page_numbers(page_numbers: tuple[int, ...]) -> str:
    displayed_page_numbers = page_numbers[:_MAX_PAGE_NUMBERS_IN_MESSAGE]
    displayed = ", ".join(str(page_number) for page_number in displayed_page_numbers)
    remaining_count = len(page_numbers) - len(displayed_page_numbers)
    if remaining_count <= 0:
        return displayed
    return f"{displayed}, and {remaining_count} more"


def pdf_text_diagnostic(extraction: DocumentTextExtraction) -> PdfTextDiagnostic:
    """Build the user-facing diagnostic for one failed PDF text extraction."""
    if extraction.page_count == 0 or extraction.extraction_outcome == "no_pages":
        return PdfTextDiagnostic(
            reason_code=_PDF_NO_PAGES_REASON,
            message="The uploaded PDF contains no pages.",
            ocr_required=False,
            page_count=extraction.page_count,
        )
    if (
        extraction.extraction_outcome == "partial_text_ocr_needed"
        and extraction.pages_without_text
    ):
        return PdfTextDiagnostic(
            reason_code=_PARTIAL_PDF_OCR_NEEDED_REASON,
            message=(
                "The uploaded PDF includes embedded text on some pages, but pages "
                f"{_format_pdf_page_numbers(extraction.pages_without_text)} appear "
                "to be scanned or image-only. OCR is not currently supported by this "
                "service; upload a fully text-based PDF or extract the missing pages "
                "manually."
            ),
            ocr_required=True,
            page_count=extraction.page_count,
            pages_without_text=extraction.pages_without_text,
        )
    if (
        isinstance(extraction.page_count, int)
        and extraction.page_count > 0
        and extraction.extraction_outcome == "no_text_image_likely"
    ):
        return PdfTextDiagnostic(
            reason_code=_SCANNED_PDF_NO_TEXT_REASON,
            message=(
                "The uploaded PDF appears to be scanned or image-only and does not "
                "include embedded text. OCR is not currently supported by this "
                "service; upload a text-based PDF or extract the text manually."
            ),
            ocr_required=True,
            page_count=extraction.page_count,
            pages_without_text=extraction.pages_without_text,
        )
    return PdfTextDiagnostic(
        reason_code=_PDF_NO_EXTRACTABLE_TEXT_REASON,
        message="The uploaded PDF did not contain extractable text.",
        ocr_required=False,
        page_count=extraction.page_count,
    )


def require_extracted_pdf_text(extraction: DocumentTextExtraction) -> str:
    """Return normalized text or raise the PDF OCR-needed diagnostic."""
    normalized_text = normalize_text_document(extraction.text_content)
    if (
        normalized_text == ""
        or extraction.extraction_outcome == "partial_text_ocr_needed"
    ):
        raise PdfTextDiagnosticError(pdf_text_diagnostic(extraction))
    return normalized_text


__all__ = [
    "PdfTextDiagnostic",
    "PdfTextDiagnosticError",
    "pdf_text_diagnostic",
    "require_extracted_pdf_text",
]
