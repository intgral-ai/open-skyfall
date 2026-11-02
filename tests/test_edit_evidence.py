from copy import deepcopy

from open_assembly.fixtures import create_demo
from open_assembly.project import ProjectStore


def test_deliberate_edit_retains_historical_fit_without_claiming_current_fit(tmp_path):
    source = create_demo(tmp_path / "fixture")
    store = ProjectStore(tmp_path / "workspace")
    initial = store.create(source["input"], "mm")
    definition = initial["document"]["definitions"][0]
    original_recipe = deepcopy(definition["recipe"])
    original_fit = deepcopy(definition["evidence"]["fit"])
    edited = store.edit(
        initial["id"],
        initial["revision"],
        definition["id"],
        {"height": original_recipe["parameters"]["height"] * 1.05},
    )
    assert edited["state"] == "ready"
    evidence = edited["document"]["definitions"][0]["evidence"]
    assert "fit" not in evidence
    assert evidence["reconstruction_fit"]["recipe"] == original_recipe
    assert evidence["reconstruction_fit"]["metrics"] == original_fit
    assert evidence["reconstruction_fit"]["revision"] == initial["revision"]
    current = next(p for p in edited["validation"]["parts"] if p["id"] == definition["id"])
    assert current["fit"] is None
