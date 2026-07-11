from __future__ import annotations

from unittest.mock import AsyncMock, patch

import limen.cli.report as cli_report
from limen.cli.main import main as cli_main


def test_report_module_exposes_entrypoint() -> None:
    assert callable(cli_report.run)


def test_report_build_routes_to_report_run_without_db() -> None:
    """`limen report build` should call build_report exactly once and be
    idempotent-safe when the underlying build is skipped (returns None)."""
    mock_pool_cm = AsyncMock()
    mock_pool_cm.__aenter__.return_value = None
    mock_pool_cm.__aexit__.return_value = False

    with (
        patch.object(cli_report, "build_report", new=AsyncMock(return_value=None)) as mock_build,
        patch.object(cli_report, "lifespan_pool", return_value=mock_pool_cm),
        patch.object(cli_report, "run_migrations", new=AsyncMock()),
        patch.object(cli_report.SharedHttpClient, "aclose", new=AsyncMock()),
        patch("limen.cli.main._load_dotenv"),
    ):
        exit_code = cli_main(["report", "build"])

    mock_build.assert_awaited_once()
    assert exit_code == 0
