import json
from pathlib import Path

from limen.report.archive import prune_archive, write_build


def test_write_build_is_immutable_and_updates_pointer(tmp_path: Path) -> None:
    root = tmp_path / "report"
    manifest = {
        "valuation_time": "2026-07-11T08:00:00Z",
        "assessment_sha256": "abc",
        "clusters": [{"cluster_id": 0, "cell_ids": ["a"]}],
    }
    d1 = write_build(
        root, build_id="2026-07-11T0800Z", html="<html>v1</html>", assets={}, manifest=manifest
    )
    _d2 = write_build(
        root,
        build_id="2026-07-11T0900Z",
        html="<html>v2</html>",
        assets={},
        manifest={**manifest, "assessment_sha256": "def"},
    )
    assert (d1 / "index.html").read_text() == "<html>v1</html>"
    assert json.loads((d1 / "manifest.json").read_text())["assessment_sha256"] == "abc"
    assert "2026-07-11T0900Z" in (root / "index.html").read_text()
    idx = json.loads((root / "archive" / "index.json").read_text())
    assert len(idx["builds"]) == 2


def test_prune_keeps_manifests_but_trims_old_html(tmp_path: Path) -> None:
    root = tmp_path / "report"
    for i in range(5):
        write_build(
            root,
            build_id=f"b{i}",
            html="<html></html>",
            assets={},
            manifest={"assessment_sha256": str(i), "clusters": []},
        )
    prune_archive(root, keep=2)
    remaining_html = {p.parent.name for p in (root / "archive").glob("b*/index.html")}
    remaining_manifest = list((root / "archive").glob("b*/manifest.json"))
    assert remaining_html == {"b3", "b4"}
    assert len(remaining_manifest) == 5


def test_prune_keep_zero_trims_all_html_but_keeps_manifests(tmp_path: Path) -> None:
    root = tmp_path / "report"
    for i in range(3):
        write_build(
            root,
            build_id=f"b{i}",
            html="<html></html>",
            assets={},
            manifest={"assessment_sha256": str(i), "clusters": []},
        )
    prune_archive(root, keep=0)
    assert list((root / "archive").glob("b*/index.html")) == []
    assert len(list((root / "archive").glob("b*/manifest.json"))) == 3
