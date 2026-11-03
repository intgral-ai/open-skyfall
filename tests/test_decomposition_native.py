import copy
import hashlib
import json
import os
import subprocess
from pathlib import Path

import numpy as np
import pytest
from open_assembly import decomposition_native as native
from open_assembly.decomposition import Plan, _json_bytes, pose_matrix
from open_assembly.native_resources import decomposition as runner


@pytest.fixture
def native_plan():
    return Plan.model_validate(
        {
            "source_sha256": "a" * 64,
            "units": "mm",
            "scale_note": "Original metric fixture.",
            "assumptions": ["Original synthetic concept. Manufacturing remains unchecked."],
            "definitions": [
                {
                    "id": "beam",
                    "shapes": [
                        {"id": "bar", "kind": "box", "dimensions": [12, 4, 3]},
                        {
                            "id": "boss",
                            "kind": "cylinder",
                            "dimensions": [1, 5],
                            "position": [3, 0, 1],
                            "rotation": [31, 27, 13],
                        },
                    ],
                },
                {
                    "id": "tube",
                    "shapes": [
                        {"id": "wall", "kind": "shell", "dimensions": [4, 4, 8, 1]},
                    ],
                },
            ],
            "nodes": [
                {
                    "id": "root",
                    "label": "Original assembly",
                    "evidence": "inferred",
                    "note": "Author proposed assembly.",
                    "rotation": [13, 24, 31],
                },
                {
                    "id": "frame",
                    "label": "Frame",
                    "parent_id": "root",
                    "evidence": "inferred",
                    "note": "Author proposed subassembly.",
                    "position": [5, 10, 3],
                    "rotation": [17, -11, 23],
                },
                {
                    "id": "beamA",
                    "label": "Beam A",
                    "parent_id": "frame",
                    "definition_id": "beam",
                    "evidence": "inferred",
                    "note": "First reusable beam.",
                    "position": [1, 2, 3],
                },
                {
                    "id": "beamB",
                    "label": "Beam B",
                    "parent_id": "frame",
                    "definition_id": "beam",
                    "evidence": "inferred",
                    "note": "Second reusable beam.",
                    "position": [19, 7, 5],
                    "rotation": [8, 17, 43],
                },
                {
                    "id": "tubeA",
                    "label": "Tube",
                    "parent_id": "root",
                    "definition_id": "tube",
                    "evidence": "inferred",
                    "note": "Proposed tube.",
                    "position": [30, 2, 1],
                },
            ],
        }
    )


def binding_for(plan, parts=None):
    parts = parts or [node.id for node in plan.nodes if node.definition_id]
    return {
        "project_id": "native-test",
        "revision": 3,
        "source_sha256": plan.source_sha256,
        "program_sha256": "b" * 64,
        "plan_sha256": hashlib.sha256(_json_bytes(plan.model_dump(mode="json"))).hexdigest(),
        "brief_sha256": None,
        "review_digests": {part: "c" * 64 for part in parts},
        "scope_digest": "d" * 64,
        "part_ids": parts,
    }


@pytest.mark.parametrize("defect", ["source", "plan", "revision", "review", "parts", "missing"])
def test_native_refuses_unbound_build_without_creating_outputs(native_plan, tmp_path, defect):
    binding = binding_for(native_plan)
    if defect == "source":
        binding["source_sha256"] = "f" * 64
    elif defect == "plan":
        binding["plan_sha256"] = "f" * 64
    elif defect == "revision":
        binding["revision"] = True
    elif defect == "review":
        binding["review_digests"].pop("beamB")
    elif defect == "parts":
        binding["part_ids"] = ["beamA"]
    else:
        binding.pop("program_sha256")
    output = tmp_path / "refused"
    with pytest.raises(ValueError):
        native.build_native(native_plan, output, binding=binding)
    assert not output.exists()


def test_relative_units_and_unknown_scope_refuse_before_native_runtime(native_plan, tmp_path):
    relative = native_plan.model_copy(update={"units": "relative"})
    with pytest.raises(ValueError, match="millimetre"):
        native.build_native(relative, tmp_path / "relative", binding=binding_for(relative))
    with pytest.raises(ValueError, match="existing nodes"):
        native.build_native(
            native_plan,
            tmp_path / "unknown",
            binding=binding_for(native_plan),
            node_ids=["missing"],
        )
    assert list(tmp_path.iterdir()) == []


def test_native_runtime_is_operator_owned_and_output_must_be_empty(
    native_plan, tmp_path, monkeypatch
):
    monkeypatch.delenv("OPEN_ASSEMBLY_SMLIB_PYTHON", raising=False)
    with pytest.raises(ValueError, match="OPEN_ASSEMBLY_SMLIB_PYTHON"):
        native.build_native(
            native_plan, tmp_path / "missing-runtime", binding=binding_for(native_plan)
        )
    monkeypatch.setattr(native, "runtime_python", lambda: Path("/operator/python"))
    output = tmp_path / "occupied"
    output.mkdir()
    (output / "valuable.txt").write_text("preserve")
    with pytest.raises(ValueError, match="empty directory"):
        native.build_native(native_plan, output, binding=binding_for(native_plan))
    assert (output / "valuable.txt").read_text() == "preserve"


def test_group_selection_preserves_parent_composition_and_exact_binding(native_plan):
    selected = native._selection(native_plan, ["frame"])
    assert [item["id"] for item in selected] == ["beamA", "beamB"]
    root, frame, beam = native_plan.nodes[:3]
    np.testing.assert_allclose(
        selected[0]["world_transform"],
        pose_matrix(root) @ pose_matrix(frame) @ pose_matrix(beam),
        atol=1e-12,
    )
    assert native._validate_binding(
        native_plan, binding_for(native_plan, ["beamA", "beamB"]), selected
    )
    with pytest.raises(ValueError, match="exact selected"):
        native._validate_binding(native_plan, binding_for(native_plan), selected)


@pytest.mark.parametrize("defect", ["transform", "scope", "definition"])
def test_isolated_runner_refuses_occurrences_outside_bound_plan(native_plan, defect):
    data = {
        "plan": native_plan.model_dump(mode="json"),
        "binding": binding_for(native_plan),
        "occurrences": native._selection(native_plan, None),
    }
    runner.validate_occurrences(data)
    if defect == "transform":
        data["occurrences"][0]["world_transform"][0][3] += 1
    elif defect == "scope":
        data["occurrences"].pop()
    else:
        data["occurrences"][0]["definition_id"] = "tube"
    with pytest.raises(ValueError, match="Native input|differs from the bound Plan"):
        runner.validate_occurrences(data)


def test_failed_process_retains_binding_and_native_diagnostics(native_plan, tmp_path, monkeypatch):
    monkeypatch.setattr(native, "runtime_python", lambda: Path("/operator/python"))

    def fail(command, **kwargs):
        kwargs["stderr"].write(b"controlled native failure\n")
        return subprocess.CompletedProcess(command, 17)

    monkeypatch.setattr(native.subprocess, "run", fail)
    output = tmp_path / "failed"
    binding = binding_for(native_plan)
    with pytest.raises(ValueError, match="exit 17"):
        native.build_native(native_plan, output, binding=binding)
    failure = json.loads((output / "native-failure.json").read_text())
    assert failure["binding"] == binding
    assert failure["status"] == "failed"
    assert failure["manufacturing"] == "UNCHECKED"
    assert (
        output / "definitions/beam/process.stderr.log"
    ).read_text() == "controlled native failure\n"
    assert not (output / "assembly.step").exists()


@pytest.fixture
def smlib_runtime(monkeypatch):
    value = os.environ.get("OPEN_ASSEMBLY_SMLIB_PYTHON")
    if not value:
        pytest.skip("Set OPEN_ASSEMBLY_SMLIB_PYTHON for real isolated smlibpy integration")
    monkeypatch.setenv("OPEN_ASSEMBLY_SMLIB_PYTHON", value)
    return Path(value)


def test_real_native_reuse_parent_rotation_step_and_receipts(native_plan, tmp_path, smlib_runtime):
    binding = binding_for(native_plan)
    output = tmp_path / "native"
    report = native.build_native(native_plan, output, binding=binding)
    assert report["binding"] == binding
    assert set(report["definitions"]) == {"beam", "tube"}
    assert [item["id"] for item in report["occurrences"]] == binding["part_ids"]
    assert report["checks"]["native_validity"]["status"] == "PASS"
    assert report["checks"]["step_exchange"]["status"] == "PASS"
    assert report["checks"]["source_fidelity"]["status"] == "UNCHECKED"
    assert report["checks"]["manufacturing"]["status"] == "UNCHECKED"
    assert report["step_structure"] == "flat_named_bodies"
    assert report["runtime"]["foreign_construction_modules_loaded"] == []
    pids = {definition["runtime"]["pid"] for definition in report["definitions"].values()}
    assert len(pids) == 2 and report["runtime"]["pid"] not in pids
    assert report["definitions"]["tube"]["metrics"]["volume"] == pytest.approx(np.pi * (16 - 9) * 8)
    assert report["definitions"]["beam"]["metrics"]["volume"] > 12 * 4 * 3
    boss = native_plan.definitions[0].shapes[1]
    axis = pose_matrix(boss)[:3, 2]
    radius, height = boss.dimensions
    extent = radius * np.sqrt(1 - axis**2) + height / 2 * np.abs(axis)
    expected_bounds = [
        np.minimum([-6, -2, -1.5], np.asarray(boss.position) - extent),
        np.maximum([6, 2, 1.5], np.asarray(boss.position) + extent),
    ]
    np.testing.assert_allclose(
        report["definitions"]["beam"]["metrics"]["bounds"], expected_bounds, atol=1e-6
    )
    for definition in report["definitions"].values():
        assert definition["binding"] == binding
        assert definition["metrics"]["solid_count"] == 1
        assert definition["runtime"]["binary_sha256"] == report["runtime"]["binary_sha256"]
        assert len(definition["stages"]) >= 3
    preview = json.loads((output / report["preview_path"]).read_text())
    assert preview["binding"] == binding
    assert [part["id"] for part in preview["parts"]] == binding["part_ids"]
    assert all(len(part["triangles"]) for part in preview["parts"])
    assembly = json.loads((output / "assembly.json").read_text())
    assert assembly["physical_tree"] == native_plan.model_dump(mode="json")["nodes"]
    assert assembly["native_mates"] is False
    trace = json.loads((output / "native-trace.json").read_text())
    assert trace["binding"] == binding
    assert trace["step_readback"]["heal"] is False
    assert trace["step_export"]["names"] == sorted(binding["part_ids"])
    assert trace["definition_stages"]["beam"][2]["operation"] == "initialize_definition"
    assert trace["definition_stages"]["beam"][-1]["operation"] == "fuse_definition"
    first, second, assembler = report["processes"]
    assert first["started_monotonic_ns"] < second["finished_monotonic_ns"]
    assert second["started_monotonic_ns"] < first["finished_monotonic_ns"]
    assert assembler["started_monotonic_ns"] >= max(
        first["finished_monotonic_ns"], second["finished_monotonic_ns"]
    )
    assert (
        report["occurrences"][1]["world_transform"] != report["occurrences"][0]["world_transform"]
    )
    for name, digest in report["artifacts"].items():
        assert hashlib.sha256((output / name).read_bytes()).hexdigest() == digest
    stored = json.loads((output / "native-report.json").read_text())
    assert "native-report.json" not in stored["artifacts"]
    assert stored["binding"] == binding
    command = [
        str(smlib_runtime),
        "-I",
        "-B",
        "-c",
        "import json,sys; from smlibpy import read_step; "
        "print(json.dumps({b.name: {'volume':b.volume,'solids':len(b.solids()),"
        "'valid':b.is_valid()} for b in read_step(sys.argv[1],heal=False).bodies}))",
        str(output / "assembly.step"),
    ]
    independent_process = subprocess.run(command, check=True, capture_output=True, text=True)
    measured = json.loads(independent_process.stdout)
    assert set(measured) == set(binding["part_ids"])
    assert all(value["valid"] and value["solids"] == 1 for value in measured.values())
    assert measured["beamA"]["volume"] == pytest.approx(measured["beamB"]["volume"])


def test_real_native_rejects_disconnected_definition(native_plan, tmp_path, smlib_runtime):
    data = copy.deepcopy(native_plan.model_dump(mode="json"))
    data["definitions"][0]["shapes"][1]["position"] = [100, 0, 0]
    disconnected = Plan.model_validate(data)
    output = tmp_path / "disconnected"
    binding = binding_for(disconnected, ["beamA"])
    with pytest.raises(ValueError, match="Native definition failed"):
        native.build_native(disconnected, output, binding=binding, node_ids=["beamA"])
    failure = json.loads((output / "definitions/beam/failure.json").read_text())
    assert failure["binding"] == binding
    assert "connected" in failure["error"]
    assert failure["stages"][-1]["metrics"]["solid_count"] == 2
    assert not (output / "assembly.step").exists()


def test_real_partial_build_exports_only_selected_occurrences(native_plan, tmp_path, smlib_runtime):
    binding = binding_for(native_plan, ["beamA", "beamB"])
    report = native.build_native(
        native_plan, tmp_path / "partial", binding=binding, node_ids=["frame"]
    )
    assert set(report["definitions"]) == {"beam"}
    assert report["checks"]["step_exchange"]["names"] == ["beamA", "beamB"]
    assert report["binding"] == binding


def test_real_sphere_and_tapered_shell_follow_local_poses(native_plan, tmp_path, smlib_runtime):
    data = native_plan.model_dump(mode="json")
    data["definitions"][0]["shapes"] = [
        {
            "id": "ball",
            "kind": "sphere",
            "dimensions": [2],
            "position": [3, -2, 1],
            "rotation": [13, 21, 37],
        },
    ]
    data["definitions"][1]["shapes"][0]["dimensions"] = [5, 3, 8, 1]
    plan = Plan.model_validate(data)
    report = native.build_native(plan, tmp_path / "curved", binding=binding_for(plan))
    sphere = report["definitions"]["beam"]["metrics"]
    assert sphere["volume"] == pytest.approx(4 / 3 * np.pi * 2**3)
    np.testing.assert_allclose(sphere["bounds"], [[1, -4, -1], [5, 0, 3]], atol=1e-6)
    expected_wall_volume = np.pi * 8 / 3 * ((5**2 + 5 * 3 + 3**2) - (4**2 + 4 * 2 + 2**2))
    assert report["definitions"]["tube"]["metrics"]["volume"] == pytest.approx(expected_wall_volume)
