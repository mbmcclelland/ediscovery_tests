"""
Tests for the OCR Usage Report workflow.

This mirrors the Edge-recorded UI flow:
  1. Log in
  2. Navigate to Status -> OCR Usage Report
  3. Set start date = 2026-01-01, end date = 2026-03-23
  4. Click "Download Report"

API equivalents (from browser network capture):
  - POST /realmManager/getOCRUsageStatistics   -> inline JSON data
  - POST /realmManager/getOCRUsageStatisticsUrl -> download URL for CSV/report

Browser sends:
  - Authorization: <raw sessionToken>
  - Body: { contextHandle, systemScope, filters, startIndex, count }
  - Filter format: FROM_DATE/EQUALS/epoch_ms, TO_DATE/no-operator/epoch_ms
"""

import datetime
import pytest

from helpers.api_client import APIError


# --------------------------------------------------------------- helpers

def _epoch_ms(year: int, month: int, day: int) -> int:
    """Convert a date to epoch milliseconds (UTC midnight)."""
    dt = datetime.datetime(year, month, day, tzinfo=datetime.timezone.utc)
    return int(dt.timestamp() * 1000)


def _ocr_filters(start_epoch_ms: int, end_epoch_ms: int) -> list[dict]:
    """
    Build OCR usage filters matching the browser's actual format.
    FROM_DATE uses operator=EQUALS, TO_DATE omits operator.
    Values are integers (not strings).
    """
    return [
        {
            "attribute": "FROM_DATE",
            "operator": "EQUALS",
            "value": start_epoch_ms,
        },
        {
            "attribute": "TO_DATE",
            "value": end_epoch_ms,
        },
    ]


# ------------------------------------------------------------ test class

@pytest.mark.ocr
@pytest.mark.smoke
class TestOCRUsageReport:
    """
    Happy-path tests for the OCR Usage Report.
    Matches the recorded workflow: Jan 1 - Jan 31, 2026.
    """

    START = _epoch_ms(2026, 1, 1)
    END = _epoch_ms(2026, 1, 31)

    def test_get_ocr_statistics_success(self, api):
        """getOCRUsageStatistics returns data with date filters."""
        data = api.post(
            "realmManager/getOCRUsageStatistics",
            extra_body={
                "filters": _ocr_filters(self.START, self.END),
                "startIndex": 0,
                "count": 0,
            },
        )
        # This endpoint may not return status field on success
        assert "numOCRDocuments" in data or data.get("status") != "FAILURE"

    def test_ocr_statistics_contains_totals(self, api):
        """Response includes aggregate OCR document and page counts."""
        data = api.post(
            "realmManager/getOCRUsageStatistics",
            extra_body={
                "filters": _ocr_filters(self.START, self.END),
                "startIndex": 0,
                "count": 0,
            },
        )
        assert "numOCRDocuments" in data
        assert "numOCRPages" in data
        assert isinstance(data["numOCRDocuments"], int)
        assert isinstance(data["numOCRPages"], int)

    def test_ocr_statistics_contains_language_counts(self, api):
        """Response includes per-language OCR counts (CJK, Arabic, Thai, Hebrew)."""
        data = api.post(
            "realmManager/getOCRUsageStatistics",
            extra_body={
                "filters": _ocr_filters(self.START, self.END),
                "startIndex": 0,
                "count": 0,
            },
        )
        for lang in ["CJK", "Arabic", "Thai", "Hebrew"]:
            assert f"num{lang}OCRDocuments" in data, f"Missing num{lang}OCRDocuments"
            assert f"num{lang}OCRPages" in data, f"Missing num{lang}OCRPages"

    def test_ocr_statistics_has_usage_data_array(self, api):
        """Response includes the detailed ocrUsageData array."""
        data = api.post(
            "realmManager/getOCRUsageStatistics",
            extra_body={
                "filters": _ocr_filters(self.START, self.END),
                "startIndex": 0,
                "count": 0,
            },
        )
        assert "ocrUsageData" in data
        assert isinstance(data["ocrUsageData"], list)

    def test_ocr_usage_dto_structure(self, api):
        """Each item in ocrUsageData has the expected OcrUsageDto fields."""
        data = api.post(
            "realmManager/getOCRUsageStatistics",
            extra_body={
                "filters": _ocr_filters(self.START, self.END),
                "startIndex": 0,
                "count": 0,
            },
        )
        for item in data.get("ocrUsageData", []):
            assert "orgName" in item
            assert "numOCRDocuments" in item
            assert "numOCRPages" in item
            break  # Just validate the first item

    def test_get_ocr_statistics_url_returns_download_link(self, api):
        """
        getOCRUsageStatisticsUrl returns a URL for the downloadable report.
        This is the API equivalent of clicking "Download Report" in the UI.
        """
        data = api.post(
            "realmManager/getOCRUsageStatisticsUrl",
            extra_body={
                "filters": _ocr_filters(self.START, self.END),
                "startIndex": 0,
                "count": 0,
            },
        )
        assert "url" in data
        assert data["url"], "Download URL should not be empty"

    def test_ocr_report_with_org_filter(self, api):
        """Filter OCR stats by organization name."""
        org_name = api.cfg.organization
        if not org_name:
            pytest.skip("No DR_ORGANIZATION configured; skipping org filter test")

        filters = _ocr_filters(self.START, self.END) + [
            {
                "attribute": "ORG",
                "operator": "EQUALS",
                "value": org_name,
            },
        ]
        data = api.post(
            "realmManager/getOCRUsageStatistics",
            extra_body={"filters": filters, "startIndex": 0, "count": 0},
        )
        assert "numOCRDocuments" in data

    def test_ocr_statistics_with_pagination(self, api):
        """Request a specific page of results using startIndex and count."""
        data = api.post(
            "realmManager/getOCRUsageStatistics",
            extra_body={
                "filters": _ocr_filters(self.START, self.END),
                "startIndex": 0,
                "count": 10,
            },
        )
        assert "totalCount" in data


@pytest.mark.ocr
class TestOCRUsageReportDateRanges:
    """Test various date range scenarios."""

    def test_full_year_range(self, api):
        """Full-year query (2025) returns data."""
        data = api.post(
            "realmManager/getOCRUsageStatistics",
            extra_body={
                "filters": _ocr_filters(
                    _epoch_ms(2025, 1, 1),
                    _epoch_ms(2025, 12, 31),
                ),
                "startIndex": 0,
                "count": 0,
            },
        )
        assert "numOCRDocuments" in data

    def test_single_day_range(self, api):
        """Single-day query returns data."""
        data = api.post(
            "realmManager/getOCRUsageStatistics",
            extra_body={
                "filters": _ocr_filters(
                    _epoch_ms(2026, 1, 15),
                    _epoch_ms(2026, 1, 16),
                ),
                "startIndex": 0,
                "count": 0,
            },
        )
        assert "numOCRDocuments" in data

    def test_no_filters_returns_all(self, api):
        """Query with no date filters returns all available data."""
        data = api.post(
            "realmManager/getOCRUsageStatistics",
            extra_body={"filters": [], "startIndex": 0, "count": 0},
        )
        assert "numOCRDocuments" in data
