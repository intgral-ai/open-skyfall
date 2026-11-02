"""Independent OCCT import inspection. This process constructs no delivered geometry."""

import argparse
import hashlib
import json
import math
import re
import zipfile
from pathlib import Path

from OCP.Bnd import Bnd_Box
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPControl import STEPControl_Reader
from OCP.TopAbs import TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    out = parser.parse_args().directory.resolve()
    path = out / "assembly.step"
    native = json.loads((out / "native-report.json").read_text())
    reader = STEPControl_Reader()
    assert reader.ReadFile(str(path)) == IFSelect_RetDone, "OCCT cannot import STEP"
    assert reader.TransferRoots() > 0, "STEP has no transferable root"
    explorer = TopExp_Explorer(reader.OneShape(), TopAbs_SOLID)
    solids = []
    imported = []
    while explorer.More():
        solid = TopoDS.Solid(explorer.Current())
        imported.append(solid)
        properties = GProp_GProps()
        BRepGProp.VolumeProperties_s(solid, properties)
        box = Bnd_Box()
        BRepBndLib.AddOptimal_s(solid, box, False, False)
        low, high = box.CornerMin(), box.CornerMax()
        solids.append(
            {
                "valid": BRepCheck_Analyzer(solid).IsValid(),
                "volume_mm3": properties.Mass(),
                "bounds": [[low.X(), low.Y(), low.Z()], [high.X(), high.Y(), high.Z()]],
            }
        )
        explorer.Next()
    # Equal-volume screws/clamps may be imported in any order. Match complete
    # placement bounds and volume with a one-to-one assignment, not a volume sort.
    unmatched = set(range(len(solids)))
    matches = {}
    for id, expected in native["placed_metrics"].items():
        candidates = [
            i
            for i in unmatched
            if math.isclose(
                solids[i]["volume_mm3"], expected["volume_mm3"], rel_tol=1e-5, abs_tol=1e-5
            )
            and all(
                abs(x - y) < 1e-5
                for row_a, row_b in zip(solids[i]["bounds"], expected["bounds"])
                for x, y in zip(row_a, row_b)
            )
        ]
        if len(candidates) == 1:
            matches[id] = candidates[0]
            unmatched.remove(candidates[0])
    text = path.read_text()
    names = re.findall(r"MANIFOLD_SOLID_BREP\('([^']*)'", text)
    overlaps = []
    for i, a in enumerate(imported):
        ba = solids[i]["bounds"]
        for j in range(i + 1, len(imported)):
            bb = solids[j]["bounds"]
            if not all(min(ba[1][k], bb[1][k]) - max(ba[0][k], bb[0][k]) > 1e-6 for k in range(3)):
                continue
            common = BRepAlgoAPI_Common(a, imported[j])
            assert common.IsDone(), "Independent body intersection failed"
            properties = GProp_GProps()
            BRepGProp.VolumeProperties_s(common.Shape(), properties)
            if properties.Mass() > 1e-5:
                overlaps.append({"a": i, "b": j, "volume_mm3": properties.Mass()})
    checks = {
        "native_report_passed": native["valid"] is True and all(native["checks"].values()),
        "step_hash_matches_native_execution": hashlib.sha256(path.read_bytes()).hexdigest()
        == native["step_sha256"],
        "occt_body_count": len(solids) == native["physical_occurrence_count"],
        "occt_all_breps_valid": all(s["valid"] and s["volume_mm3"] > 0 for s in solids),
        "occt_unique_placement_and_volume_matches": len(matches) == len(native["placed_metrics"])
        and not unmatched,
        "named_occurrences_preserved": set(names) == set(native["placed_metrics"]),
        "occt_no_body_interference": not overlaps,
        "millimetre_units": "SI_UNIT(.MILLI.,.METRE.)" in text,
    }
    report = {
        "valid": all(checks.values()),
        "checks": checks,
        "reader": "OCCT via OCP; inspection only, no output construction or STEP rewriting",
        "step_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "body_count": len(solids),
        "solids": solids,
        "names": names,
        "overlaps": overlaps,
        "placement_matches": matches,
        "bounds_tolerance_mm": 1e-5,
        "limitations": [
            "Flat STEP bodies, not a nested STEP product assembly",
            "No source measurement of hidden mechanisms or manufacturing fit",
        ],
    }
    (out / "inspection.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"valid": report["valid"], "checks": checks, "body_count": len(solids)}))
    if not report["valid"]:
        raise SystemExit(1)
    with zipfile.ZipFile(out / "project.zip", "w", zipfile.ZIP_DEFLATED) as bundle:
        for item in sorted(out.rglob("*")):
            if item.is_file() and item.name != "project.zip":
                bundle.write(item, item.relative_to(out))


if __name__ == "__main__":
    main()
