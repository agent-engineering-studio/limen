"""The CLI introduction names every supported hazard."""

import pytest

from limen.cli.main import _build_parser, main


def test_parser_help_names_all_three_hazards() -> None:
    parser = _build_parser()
    description = parser.description or ""
    for hazard in ("landslide", "flood", "wildfire"):
        assert hazard in description.lower()
        assert hazard in parser.format_help().lower()


def test_main_help_exits_successfully_with_all_three_hazards(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    output = capsys.readouterr().out.lower()
    assert "limen — landslide, flood and wildfire risk monitoring cli" in " ".join(output.split())
