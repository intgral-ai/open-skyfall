import json

import pytest
from open_assembly.document import (
    AssemblyDocument,
    InputEvidence,
    Occurrence,
    PartDefinition,
    Recipe,
)
from open_assembly.intent import questions, write_intent
from open_assembly.project import ProjectStore


@pytest.fixture
def interview(tmp_path):
    store = ProjectStore(tmp_path / "workspace")
    document = AssemblyDocument(
        input=InputEvidence(name="test", sha256="test", kind="recipe", units="mm"),
        definitions=[
            PartDefinition(
                id="sleeve",
                label="Sleeve",
                recipe=Recipe(
                    kind="sleeve",
                    parameters={"outer_diameter": 12, "inner_diameter": 6, "height": 16},
                ),
            )
        ],
        occurrences=[
            Occurrence(id="first", definition_id="sleeve"),
            Occurrence(
                id="second",
                definition_id="sleeve",
                transform=[[1, 0, 0, 30], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
            ),
        ],
    )
    job = store.create_document(document)
    return store, job, questions(store, job["id"])


def test_manufacturing_answers_require_confirmation(interview):
    store, job, interview = interview
    with pytest.raises(ValueError, match="confirmation"):
        write_intent(store, job["id"], job["revision"], interview["analysis_id"], {}, False)


def test_missing_requirements_do_not_become_defaults(interview):
    store, job, interview = interview
    with pytest.raises(ValueError, match="incomplete"):
        write_intent(
            store,
            job["id"],
            job["revision"],
            interview["analysis_id"],
            {"0": {"part.material": "Aluminium 6061-T6"}},
            True,
        )
    assert store.get(job["id"])["intent"] is None


def test_rebuild_invalidates_old_factory_binding(interview):
    store, job, interview = interview
    store.edit(job["id"], job["revision"], "sleeve", {"height": 18})
    with pytest.raises(ValueError, match="stale"):
        write_intent(store, job["id"], job["revision"], interview["analysis_id"], {}, True)


def test_real_pmi_preserves_repeated_occurrences_and_reports_warnings(interview):
    from specify_core import api

    store, job, interview = interview
    answers = {"0": {"part.material": "Aluminium 6061-T6"}}
    result = write_intent(
        store, job["id"], job["revision"], interview["analysis_id"], answers, True, True
    )
    output = store.artifact(job["id"], result["output"])
    assert output.is_file()
    assert api.parts(output)[0]["instances"] == 2
    assert any("material" in item for item in result["written"])
    if result["warnings"]:
        assert not result["complete"]
        assert result["state"] == "needs_review"
    original_bytes = output.read_bytes()
    repeated = write_intent(
        store, job["id"], job["revision"], interview["analysis_id"], answers, True, True
    )
    assert repeated["output"] == result["output"]
    assert output.read_bytes() == original_bytes
    changed = write_intent(
        store,
        job["id"],
        job["revision"],
        interview["analysis_id"],
        {"0": {"part.material": "Stainless steel 304 (1.4301)"}},
        True,
        True,
    )
    assert changed["output"] != result["output"]
    assert output.read_bytes() == original_bytes
    assert store.artifact(job["id"], changed["output"]).is_file()
    sidecar = next(
        name
        for name in changed["artifacts"]
        if name.startswith("intent-") and not name.startswith("intent-report")
    )
    assert json.loads(store.artifact(job["id"], sidecar).read_text())["confirmed"] is True
