"""Phase 5: issues and the quality profile are saved in the project file under "quality"."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pytest.importorskip("PyQt6")

from localizelarge.mqm.scoring import RAW  # noqa: E402
from localizelarge.quality.model import make_issue  # noqa: E402
from localizelarge.quality.profile import QualityProfile  # noqa: E402
from localizelarge.quality.project_store import quality_of, to_saved  # noqa: E402


@pytest.fixture(scope="module")
def app_module():
    from PyQt6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    saved = sys.stdout, sys.stderr
    import Supervertaler
    app_module._wrappers = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = saved
    return Supervertaler


def make_project(S):
    segments = [S.Segment(id=1, source="Page 5", target="Page 6"),
                S.Segment(id=2, source="Save", target="Enregistrer")]
    return S.Project(name="Demo", source_lang="en", target_lang="fr", segments=segments)


def test_a_project_without_quality_data_saves_no_quality_key(app_module):
    project = make_project(app_module)
    assert "quality" not in project.to_dict()
    quality_of(project)                               # looking at it changes nothing
    assert "quality" not in project.to_dict()


def test_issues_and_profile_round_trip_through_the_project_file(app_module, tmp_path):
    S = app_module
    project = make_project(S)
    quality = quality_of(project)
    issue = quality.issues.add(make_issue(
        project.segments[0], origin="human", rule_id="mqm", category="accuracy/mistranslation",
        severity="major", message="Wrong number", start=5, end=6, comment="see source",
        suggestion="5", author="Tester"))
    quality.profile.name = "Client X"
    quality.profile.scoring.model = RAW
    quality.profile.scoring.weights = {"accuracy": 2.0}
    quality.profile.checks = {"qa.length": {"enabled": False}}

    data = project.to_dict()
    assert set(data["quality"]) == {"issues", "profile"}
    assert data["quality"]["issues"][0]["id"] == issue.id

    path = tmp_path / "demo.llproj"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    loaded = S.Project.from_dict(json.loads(path.read_text(encoding="utf-8")))
    again = quality_of(loaded)
    assert again.issues.all() == [issue]
    assert again.profile.to_dict() == quality.profile.to_dict()
    assert again.profile.scoring.weight("accuracy/omission") == 2.0
    # Saved again without anyone touching the quality data: still there.
    assert S.Project.from_dict(loaded.to_dict()).to_dict()["quality"] == data["quality"]


def test_a_loaded_project_keeps_quality_data_it_never_looked_at(app_module):
    S = app_module
    data = make_project(S).to_dict()
    data["quality"] = {"issues": [], "profile": {"name": "Kept"}}
    loaded = S.Project.from_dict(data)
    assert loaded.to_dict()["quality"] == data["quality"]
    assert to_saved(loaded) == data["quality"]


def test_unreadable_quality_data_does_not_stop_a_project_from_loading(app_module):
    S = app_module
    data = make_project(S).to_dict()
    data["quality"] = {"issues": [{"bad": True}, "nonsense"], "profile": {"scoring": {"model": "?"}}}
    quality = quality_of(S.Project.from_dict(data))
    assert quality.issues.all() == []
    assert quality.profile.to_dict() == QualityProfile().to_dict()
