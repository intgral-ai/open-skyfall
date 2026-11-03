import hashlib
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
BRIEF = """Design proposal: a compact bench comparator for checking a flat coupon.
Use a 240 x 150 x 12 mm bed on four separate feet. Two 170 mm long, 8 mm
diameter guide rods run along X at Y = +/-27 mm and Z = 27 mm. Four bored
saddles support the rods. A 60 x 76 x 6 mm carriage runs on four sleeve
bushings and carries a separate 24 x 30 x 12 mm coupon. Its top is Z = 51 mm.
A rear-left 12 mm diameter post supports an L arm and a 50 mm diameter
front-facing comparator dial. Put the dial center at X = 25, Y = -7,
Z = 125 mm, with a vertical contact tip touching the coupon at Z = 51 mm.
Include individual bed fasteners, rail saddles, rail end stops, sleeve
bushings, clamp knobs, dial enclosure pieces, plunger, contact ball and
travel datum. Reuse physically identical screws, feet, saddles and bushings.
This is an original proposed design example, not an inferred manufacturer
BOM or a recovered instrument mechanism. Use millimeters and a right-handed
Z-up frame, with the bed bottom at Z = 0 and positive Y toward the rear.
All unlisted dimensions, joint details and purchased-part envelopes are
design choices. Threads, tapped and clearance holes in solid recipient
plates, dial gearing, calibration, engraved graduations, lubrication,
retention details, chamfers, fits, tolerances, loads and factory processes
need engineering review. The drawn dial ticks are graphics, not extra parts.
Native validity and STEP exchange must be checked independently. Production
manufacturability and source fidelity are not established by this example.
"""


def draw_source():
    image = Image.new("RGB", (1600, 1200), "#f7f5ef")
    draw = ImageDraw.Draw(image)
    ink, muted, metal, dark, accent = "#263b3b", "#627371", "#cbd4ce", "#657b79", "#a97643"
    title = ImageFont.load_default(size=35)
    font = ImageFont.load_default(size=22)
    small = ImageFont.load_default(size=18)

    def text(x, y, words, face=font, color=ink):
        draw.text((x, y), words, fill=color, font=face)

    front = True

    def point(x, y):
        return (90 + (x - 90) * 0.8, 215 + (y - 93) * 0.8) if front else (x, y)

    def rect(bounds, fill=metal, width=2):
        bounds = (*point(*bounds[:2]), *point(*bounds[2:]))
        draw.rectangle(bounds, fill=fill, outline=ink, width=width)

    def circle(x, y, r, fill=metal, width=2):
        x, y = point(x, y)
        r = r * 0.8 if front else r
        draw.ellipse((x - r, y - r, x + r, y + r), fill=fill, outline=ink, width=width)

    def dimension(x0, y0, x1, y1, label):
        x0, y0 = point(x0, y0)
        x1, y1 = point(x1, y1)
        draw.line((x0, y0, x1, y1), fill=muted, width=2)
        for x, y in [(x0, y0), (x1, y1)]:
            draw.line((x - 5, y - 7, x + 5, y + 7), fill=muted, width=2)
        text((x0 + x1) / 2 - 25, (y0 + y1) / 2 - 27, label, small)

    text(55, 35, "BENCH COMPARATOR / ORIGINAL DESIGN PROPOSAL", title)
    text(
        55,
        86,
        "Synthetic orthographic source. All dimensions in mm. No manufacturer BOM is claimed.",
        small,
    )
    text(90, 145, "FRONT / LOOKING TOWARD +Y", small)
    rect((90, 537, 810, 573), dark)
    for x in [150, 750]:
        rect((x - 24, 573, x + 24, 603), dark)
        circle(x, 542, 7, "#b5c3bd")
    rect((137, 483, 233, 537))
    rect((168, 93, 204, 483))
    rect((216, 154, 525, 184), dark)
    rect((507, 154, 543, 191), dark)
    rect((155, 141, 217, 195), dark)
    circle(145, 170, 15, accent)
    for x in [195, 705]:
        rect((x - 35, 513, x + 35, 537))
        circle(x, 492, 24, dark)
        circle(x, 492, 12, "#dce1da")
    rect((195, 480, 705, 504), "#9baaa5")
    for x in [387, 543]:
        rect((x - 21, 474, x + 21, 510), dark)
    rect((435, 456, 615, 474))
    rect((489, 420, 561, 456), accent)
    circle(525, 198, 75, dark, 3)
    circle(525, 198, 66, "#f3f0e6", 2)
    for i in range(12):
        a = i * math.pi / 6
        draw.line(
            (
                *point(525 + 58 * math.sin(a), 198 - 58 * math.cos(a)),
                *point(525 + 64 * math.sin(a), 198 - 64 * math.cos(a)),
            ),
            fill=ink,
            width=2,
        )
    draw.line((*point(525, 208), *point(525, 151)), fill=accent, width=4)
    circle(525, 198, 6, accent)
    rect((513, 273, 537, 339), dark)
    rect((520, 315, 530, 405), "#9baaa5")
    circle(525, 411, 9, accent)
    rect((516, 105, 534, 123), accent)
    rect((627, 501, 681, 537), dark)
    rect((645, 441, 663, 501), accent)
    dimension(90, 635, 810, 635, "240")
    dimension(840, 537, 840, 573, "12")
    text(90, 670, "Bed 240 x 150 x 12. Four feet. Rods diameter 8 x 170.", small)
    text(90, 699, "Dial diameter 50. Center Z125. Coupon top Z51.", small)

    front = False
    text(960, 145, "TOP / LOOKING DOWN -Z", small)
    rect((945, 210, 1545, 585), "#e2e6dd")
    for x in [995, 1495]:
        for y in [260, 535]:
            circle(x, y, 20, dark)
            circle(x, y, 8, "#dce1da")
    for y in [330, 465]:
        rect((1032, y - 10, 1457, y + 10), "#93a7a0")
        for x in [1032, 1457]:
            rect((x - 30, y - 28, x + 30, y + 28), dark)
            circle(x, y + 20 if y > 400 else y - 20, 7, "#ced8d0")
    for x in [1005, 1485]:
        rect((x - 15, 310, x + 15, 485), dark)
        circle(x, 397, 8)
    rect((1232, 302, 1382, 492))
    for x in [1260, 1354]:
        for y in [330, 465]:
            rect((x - 17, y - 15, x + 17, y + 15), dark)
    rect((1277, 360, 1337, 435), accent)
    circle(1307, 509, 15, accent)
    circle(1025, 292, 40, dark)
    circle(1025, 292, 15, "#ced8d0")
    rect((1050, 277, 1307, 307), dark)
    rect((1292, 307, 1322, 387), dark)
    rect((1245, 387, 1370, 422), dark)
    rect((1392, 367, 1437, 427), dark)
    circle(1415, 410, 7, "#dce1da")
    circle(1415, 385, 8, accent)
    dimension(945, 650, 1545, 650, "240")
    dimension(1570, 210, 1570, 585, "150")
    text(945, 690, "Rod centers Y +/-27, Z27. Carriage 60 x 76 x 6.", small)
    text(945, 719, "Post diameter 12. L arm carries front-facing dial.", small)

    draw.line((55, 775, 1545, 775), fill="#bdc9c0", width=2)
    text(55, 805, "PHYSICAL DESIGN INTENT", font)
    text(
        55,
        847,
        "Six groups: bed, twin guides, sliding carriage, column and arm, indicator, travel datum.",
        small,
    )
    text(
        55,
        882,
        "Separate screws, feet, bored saddles, sleeve bushings, collars, bezel, face, pointer and contact.",
        small,
    )
    text(
        55,
        917,
        "Interior gearing is unknown and omitted. Dial ticks above are graphic marks, never extra components.",
        small,
    )
    text(55, 970, "ENGINEERING REVIEW STILL REQUIRED", font, accent)
    text(
        55,
        1012,
        "All unspecified dimensions and interfaces are proposed. Threads and recipient holes are omitted.",
        small,
    )
    text(
        55,
        1047,
        "Fits, tolerances, retention, materials, calibration, stiffness, loads and factory processes are unconfirmed.",
        small,
    )
    text(
        55,
        1110,
        "Original independently drafted source. Repository MIT license. Not derived from build_preview.",
        small,
    )
    image.save(HERE / "reference.png", optimize=False)


def shape(id_, kind, dimensions, position=(0, 0, 0), rotation=(0, 0, 0)):
    return dict(
        id=id_,
        kind=kind,
        dimensions=list(dimensions),
        position=list(position),
        rotation=list(rotation),
    )


def make_plan(source_hash):
    definitions, nodes, bases, parameters, shape_bases, node_bases = [], [], {}, {}, {}, {}

    def basis(id_, why, kind="assumed", observations=()):
        bases[id_] = dict(kind=kind, observations=list(observations), why=why)
        return id_

    frame = basis(
        "frame",
        "Chosen right-handed Z-up millimeter frame. Bed bottom is Z0; +Y points rearward. Zero Euler rotations and zero local offsets are authoring conventions.",
    )
    scale = basis(
        "metric",
        "The original designed brief and drawing explicitly use millimeters. This scale is a proposed design requirement, not a measured physical product.",
        "observed",
        ["source-title"],
    )
    group_basis = basis(
        "physical-groups",
        "These six proposed subassemblies organize real modeled occurrences; they are not an inferred manufacturer assembly sequence.",
    )

    def definition(id_, shapes, material, process, notes, critical):
        definitions.append(
            dict(
                id=id_,
                shapes=shapes,
                manufacturing=dict(
                    process=process, material=material, notes=notes, critical_features=critical
                ),
            )
        )
        choice = basis(
            f"{id_}-design",
            f"Proposed {id_.replace('-', ' ')} dimensions and primitive recipe from the original design brief. Unspecified details are chosen envelopes; manufacturing notes identify missing interfaces.",
        )
        for item in shapes:
            shape_bases[f"{id_}/{item['id']}"] = choice
            for field in ["dimensions", "position", "rotation"]:
                for i in range(len(item[field])):
                    parameters[f"shape/{id_}/{item['id']}/{field}/{i}"] = (
                        choice if field == "dimensions" or item[field][i] else frame
                    )

    def node(
        id_, label, parent, position=(0, 0, 0), definition_id=None, rotation=(0, 0, 0), note=None
    ):
        note = (
            note
            or "Proposed physical occurrence. Exact dimensions and interfaces require human engineering review; this is not recovered manufacturer detail."
        )
        nodes.append(
            dict(
                id=id_,
                label=label,
                parent_id=parent,
                definition_id=definition_id,
                position=list(position),
                rotation=list(rotation),
                evidence="inferred",
                note=note,
            )
        )
        place = basis(
            f"{id_}-placement",
            f"Proposed local placement of {label.lower()} in {parent or 'the world frame'}. This is an assembled design pose; display explosion never changes it.",
        )
        node_bases[id_] = dict(
            part=f"{definition_id}-design" if definition_id else group_basis, placement=place
        )
        for field, values in [("position", position), ("rotation", rotation)]:
            for i, value in enumerate(values):
                parameters[f"node/{id_}/{field}/{i}"] = place if value else frame

    definition(
        "bed",
        [shape("plate", "box", [240, 150, 12])],
        "Proposed ground steel",
        "machining",
        [
            "Datum faces, mounting and tapped holes are not modeled.",
            "Confirm flatness, stiffness, finish and corrosion protection.",
        ],
        ["Top measuring datum", "Foot and guide mounting hole patterns"],
    )
    definition(
        "foot",
        [shape("pad", "cylinder", [8, 10])],
        "Proposed elastomer",
        "purchased",
        ["Purchased pad envelope only; attachment thread and compression are unspecified."],
        ["Support height and attachment"],
    )
    definition(
        "m4-screw",
        [shape("shank", "cylinder", [2, 12]), shape("head", "cylinder", [4, 4], [0, 0, 7])],
        "Proposed steel",
        "purchased",
        [
            "One-piece connected screw envelope; thread, drive recess and standard are unspecified.",
            "Recipient clearance or tapped holes are omitted; penetrating shanks do not prove a usable joint.",
        ],
        ["Thread engagement", "Head bearing face", "Tool access"],
    )
    definition(
        "guide-rod",
        [shape("rod", "cylinder", [4, 170])],
        "Proposed ground steel",
        "purchased",
        ["Ground rod envelope; straightness, hardness and finish need specification."],
        ["Sliding diameter and straightness"],
    )
    definition(
        "saddle",
        [
            shape("foot", "box", [24, 22, 8]),
            shape("bore", "shell", [8, 8, 12, 3.75], [0, 0, 11], [0, 90, 0]),
        ],
        "Proposed aluminum",
        "machining",
        [
            "Bore is represented with a shell; its outer wall intersects the mounting pad to make one solid.",
            "Clamp split, fixing hole and rod retention are omitted.",
        ],
        ["8.5 mm proposed bore", "Rod center 11 mm above pad center", "Mounting face"],
    )
    definition(
        "end-stop",
        [shape("stop", "box", [12, 70, 16])],
        "Proposed aluminum",
        "machining",
        ["Stop mounting hole, cushioning and permissible impact load are unspecified."],
        ["Travel clearance", "Stop contact faces"],
    )
    definition(
        "carriage",
        [shape("plate", "box", [60, 76, 6])],
        "Proposed aluminum",
        "machining",
        [
            "Bushing attachment, handle and coupon mounting holes are omitted.",
            "Confirm rigidity and parallelism to the guide bores.",
        ],
        ["Bushing support faces", "Coupon seating datum"],
    )
    definition(
        "bushing",
        [shape("sleeve", "shell", [6, 6, 14, 1.7])],
        "Proposed bearing bronze",
        "purchased",
        [
            "8.6 mm bore is a proposed preview clearance, not an approved running fit.",
            "Lubrication, retention and actual bearing specification are unresolved.",
        ],
        ["Bore fit", "Coaxial alignment", "Retention"],
    )
    definition(
        "carriage-handle",
        [shape("shaft", "cylinder", [2.5, 9]), shape("grip", "sphere", [6], [0, 0, 7])],
        "Proposed polymer and insert envelope",
        "purchased",
        ["A connected one-piece envelope; insert, thread and grip attachment require detail."],
        ["Hand clearance", "Carriage attachment"],
    )
    definition(
        "coupon",
        [shape("sample", "box", [24, 30, 12])],
        "Proposed steel sample",
        "machining",
        [
            "Designed test subject, not a calibrated gauge block.",
            "Contact finish, thickness tolerance and seating need confirmation.",
        ],
        ["Top contact face at Z51", "Bottom seating face"],
    )
    definition(
        "pedestal",
        [shape("body", "cylinder", [16, 18])],
        "Proposed steel",
        "machining",
        [
            "Post socket and mounting holes are omitted; post meets the top face as a proposed interface."
        ],
        ["Post attachment", "Bed mounting datum"],
    )
    definition(
        "post",
        [shape("shaft", "cylinder", [6, 130])],
        "Proposed ground steel",
        "machining",
        ["End threads, pedestal fit and height retention require design."],
        ["Column straightness", "Collar sliding fit"],
    )
    definition(
        "post-collar",
        [shape("bore", "shell", [10, 10, 18, 3.7])],
        "Proposed aluminum",
        "machining",
        [
            "12.6 mm proposed bore preserves a visible post clearance.",
            "Clamp split, cross-hole and arm attachment are omitted.",
        ],
        ["Post fit and clamping", "Arm interface"],
    )
    definition(
        "arm",
        [
            shape("beam", "box", [103, 12, 10], [61.5, 0, 0]),
            shape("finger", "box", [12, 38, 10], [107, -19, 0]),
        ],
        "Proposed aluminum",
        "machining",
        [
            "Two overlapping orthogonal prisms fuse as one L-shaped arm.",
            "Collar and indicator mounts, fastener holes and bending analysis are omitted.",
        ],
        ["Post collar connection", "Indicator back mounting face", "Bending stiffness"],
    )
    definition(
        "clamp-knob",
        [shape("screw", "cylinder", [2, 10]), shape("grip", "cylinder", [6, 6], [0, 0, 7])],
        "Proposed steel",
        "purchased",
        ["One-piece knob envelope. Threads, knurling and tapped recipient holes are omitted."],
        ["Clamp force", "Thread engagement", "Finger access"],
    )
    definition(
        "dial-housing",
        [shape("cup-wall", "shell", [25, 25, 14, 2])],
        "Proposed aluminum",
        "purchased",
        [
            "Purchased dial exterior envelope; internal comparator mechanism is unknown and omitted.",
            "Stem port, bezel retention, sealing and back mount are unresolved.",
        ],
        ["Back mounting face", "Stem entry", "Bezel seat"],
    )
    definition(
        "dial-back",
        [shape("cap", "cylinder", [25, 4])],
        "Proposed aluminum",
        "purchased",
        ["Back cap envelope; closure screws, seal and arm interface need definition."],
        ["Housing closure", "Arm contact"],
    )
    definition(
        "dial-bezel",
        [shape("rim", "shell", [25.8, 25.8, 3, 2.5])],
        "Proposed aluminum",
        "purchased",
        ["Bored bezel envelope. Threads, locking and glass retention are omitted."],
        ["Housing fit", "Face clearance"],
    )
    definition(
        "dial-face",
        [shape("disc", "cylinder", [22.8, 1.4])],
        "Proposed coated metal",
        "purchased",
        [
            "Separate face disc, not a precision dial calibration.",
            "Graduations, center hole and retention are omitted; source ticks are graphics.",
        ],
        ["Pointer clearance", "Calibration and graduation"],
    )
    definition(
        "dial-pointer",
        [shape("hub", "cylinder", [2, 0.6]), shape("needle", "box", [1.1, 19, 0.6], [0, 7, 0])],
        "Proposed aluminum",
        "purchased",
        [
            "Overlapping hub and needle fuse into one solid.",
            "Spindle bore, balance and calibration are unspecified.",
        ],
        ["Spindle fit", "Face clearance"],
    )
    definition(
        "stem-sleeve",
        [shape("bore", "shell", [4, 4, 22, 1])],
        "Proposed steel",
        "purchased",
        ["Bored stem envelope; guides, spring and seal are not modeled."],
        ["Plunger running fit", "Housing connection"],
    )
    definition(
        "plunger",
        [shape("shaft", "cylinder", [1.5, 30])],
        "Proposed ground steel",
        "purchased",
        [
            "Exposed contact plunger envelope; internal actuation and end attachment are unspecified."
        ],
        ["Stroke and guidance", "Contact attachment"],
    )
    definition(
        "contact-ball",
        [shape("contact", "sphere", [3])],
        "Proposed carbide",
        "purchased",
        [
            "Spherical tip envelope; stem attachment is represented by overlap only.",
            "Confirm contact stress, radius and replaceable attachment.",
        ],
        ["Coupon contact", "Plunger attachment"],
    )
    definition(
        "dial-crown",
        [shape("crown", "cylinder", [3, 6])],
        "Proposed steel",
        "purchased",
        ["External lift/control envelope; function, seal and housing thread remain proposed."],
        ["Housing interface", "Control travel"],
    )
    definition(
        "datum-block",
        [shape("block", "box", [18, 24, 12])],
        "Proposed steel",
        "machining",
        ["Travel-datum block envelope. Mounting and pin holes are omitted."],
        ["Bed seating face", "Pin alignment"],
    )
    definition(
        "datum-pin",
        [shape("pin", "cylinder", [3, 20])],
        "Proposed ground steel",
        "purchased",
        [
            "Proposed locating pin. Press fit and retention are unconfirmed.",
            "Travel stop contact occurs only after carriage translation; the saved pose is a stationary inspection pose.",
        ],
        ["Locating fit", "Stop clearance"],
    )

    node(
        "inspection-rig",
        "Bench comparator / proposed design",
        None,
        note="Original designed fixture. Fifty physical occurrences in six subassemblies. No approvals, recovered BOM, calibration or native validity are claimed.",
    )
    groups = [
        ("bed-group", "Bed and leveling feet"),
        ("guides-group", "Twin guides and travel stops"),
        ("carriage-group", "Sliding coupon carriage"),
        ("stand-group", "Column and cantilever arm"),
        ("indicator-group", "Comparator exterior and contact"),
        ("datum-group", "Travel datum"),
    ]
    for id_, label in groups:
        node(id_, label, "inspection-rig")
    node("bed-plate", "Ground bed plate", "bed-group", [0, 0, 6], "bed")
    for x, side in [(-100, "left"), (100, "right")]:
        for y, depth in [(-55, "front"), (55, "rear")]:
            node(
                f"foot-{depth}-{side}",
                f"{depth.title()} {side} foot",
                "bed-group",
                [x, y, -5],
                "foot",
            )
            node(
                f"foot-screw-{depth}-{side}",
                f"{depth.title()} {side} foot screw",
                "bed-group",
                [x, y, 5],
                "m4-screw",
            )
    for y, side in [(-27, "front"), (27, "rear")]:
        node(
            f"rail-{side}",
            f"{side.title()} guide rod",
            "guides-group",
            [0, y, 27],
            "guide-rod",
            [0, 90, 0],
        )
        for x, end in [(-85, "left"), (85, "right")]:
            node(
                f"saddle-{side}-{end}",
                f"{side.title()} {end} bored saddle",
                "guides-group",
                [x, y, 16],
                "saddle",
            )
            node(
                f"saddle-screw-{side}-{end}",
                f"{side.title()} {end} saddle screw",
                "guides-group",
                [x, y + (-8 if y < 0 else 8), 19],
                "m4-screw",
            )
    for x, side in [(-102, "left"), (102, "right")]:
        node(f"stop-{side}", f"{side.title()} end stop", "guides-group", [x, 0, 20], "end-stop")
        node(
            f"stop-screw-{side}",
            f"{side.title()} stop screw",
            "guides-group",
            [x, 0, 27],
            "m4-screw",
        )
    node("carriage-plate", "Carriage plate", "carriage-group", [25, 0, 36], "carriage")
    for x, end in [(6, "left"), (44, "right")]:
        for y, side in [(-27, "front"), (27, "rear")]:
            node(
                f"bushing-{side}-{end}",
                f"{side.title()} {end} sleeve bushing",
                "carriage-group",
                [x, y, 27],
                "bushing",
                [0, 90, 0],
            )
    node(
        "carriage-handle",
        "Carriage hand grip",
        "carriage-group",
        [44, -42, 36],
        "carriage-handle",
        [90, 0, 0],
    )
    node("test-coupon", "Inspection coupon", "carriage-group", [25, 0, 45], "coupon")
    node("post-pedestal", "Column pedestal", "stand-group", [-88, 42, 21], "pedestal")
    node("column-post", "Ground column post", "stand-group", [-88, 42, 95], "post")
    node("post-collar", "Bored column collar", "stand-group", [-88, 42, 135], "post-collar")
    node("cantilever-arm", "One-piece L arm", "stand-group", [-88, 42, 135], "arm")
    node(
        "column-clamp-knob",
        "Column height clamp knob",
        "stand-group",
        [-88, 30, 135],
        "clamp-knob",
        [90, 0, 0],
    )
    node(
        "indicator-clamp-knob",
        "Indicator arm clamp knob",
        "stand-group",
        [19, 22, 143],
        "clamp-knob",
    )
    for x, side in [(-100, "left"), (-76, "right")]:
        node(
            f"pedestal-screw-{side}",
            f"{side.title()} pedestal screw",
            "stand-group",
            [x, 42, 24],
            "m4-screw",
        )
    for id_, label, definition_id, position in [
        ("dial-housing", "Bored dial housing", "dial-housing", [25, -7, 125]),
        ("dial-back", "Dial rear cover", "dial-back", [25, 2, 125]),
        ("dial-bezel", "Separate bored bezel", "dial-bezel", [25, -15.5, 125]),
        ("dial-face", "Plain dial face", "dial-face", [25, -15.8, 125]),
        ("dial-pointer", "Pointer with integral hub", "dial-pointer", [25, -16.8, 125]),
    ]:
        node(id_, label, "indicator-group", position, definition_id, [90, 0, 0])
    node("stem-sleeve", "Bored indicator stem", "indicator-group", [25, -7, 89], "stem-sleeve")
    node("contact-plunger", "Contact plunger", "indicator-group", [25, -7, 71], "plunger")
    node(
        "contact-ball", "Spherical coupon contact", "indicator-group", [25, -7, 54], "contact-ball"
    )
    node("dial-crown", "Dial lift crown", "indicator-group", [25, -7, 153], "dial-crown")
    node("travel-datum-block", "Travel datum block", "datum-group", [68, 0, 18], "datum-block")
    node("travel-datum-pin", "Ground travel datum pin", "datum-group", [68, -5, 34], "datum-pin")
    node("travel-datum-screw", "Travel datum fixing screw", "datum-group", [68, 7, 25], "m4-screw")

    observations = [
        dict(
            id="source-title",
            region=[0.03, 0.02, 0.97, 0.1],
            statement="The original source identifies an invented bench-comparator design proposal with millimeter dimensions and no manufacturer BOM claim.",
        ),
        dict(
            id="front-view",
            region=[0.05, 0.12, 0.55, 0.53],
            statement="The front view shows a bed, feet, left column and L arm, round front-facing dial, vertical contact and separate coupon on a rail carriage.",
        ),
        dict(
            id="top-view",
            region=[0.58, 0.12, 0.99, 0.57],
            statement="The top view shows twin guides, four saddles, end stops, a rectangular carriage, rear-left post and right-side travel datum.",
        ),
        dict(
            id="front-dimensions",
            region=[0.05, 0.53, 0.54, 0.61],
            statement="The source states bed 240 x 150 x 12 mm, four feet, rods diameter 8 x 170, dial diameter 50, dial center Z125 and coupon top Z51.",
        ),
        dict(
            id="top-dimensions",
            region=[0.58, 0.57, 0.98, 0.62],
            statement="The source states rod centers Y +/-27 and Z27, carriage 60 x 76 x 6 and post diameter 12.",
        ),
        dict(
            id="design-limits",
            region=[0.03, 0.65, 0.97, 0.95],
            statement="The source calls the subassemblies proposed, omits internal gearing and threads or recipient holes, and leaves fits, tolerances, materials, calibration and factory processes unconfirmed.",
        ),
    ]
    plan = dict(
        schema_version=2,
        source_sha256=source_hash,
        units="mm",
        scale_note="Millimeters are explicit designed requirements in the original source and literal brief. No scale is inferred from preview pixels.",
        assumptions=[
            "Original proposed inspection instrument, not a recovered manufacturer BOM, calibrated comparator or approved factory design.",
            "All local dimensions, poses and primitive recipes beyond the explicit source callouts are chosen design assumptions. The complete v2 basis map documents these choices without asserting source truth.",
            "Screws are connected one-piece head/shank envelopes. Threads and recipient holes are omitted, so overlap at a fastened interface is an unresolved manufacturing feature, not joint validation.",
            "Saddles, bushings, collar, bezel, housing and stem have modeled bores. Running and clamping clearances are proposed, not toleranced fits.",
            "Dial gearing, spring, spindle, glass, graduations, seals, retainers, drive recesses and lubrication are omitted. The face marks in the original drawing are graphics rather than physical parts.",
            "Parts that touch or overlap do not establish fastener engagement, detachable joints, collision-free travel, stiffness or calibration. One stationary inspection pose is proposed.",
            "Manufacturing notes per definition are proposals only. Actual material, process, finish, datum scheme, tolerances, loads and factory acceptance require responsible human review.",
        ],
        definitions=definitions,
        nodes=nodes,
        explanation=dict(
            observations=observations,
            bases=bases,
            parameters=parameters,
            shapes=shape_bases,
            nodes=node_bases,
            scale=scale,
        ),
    )
    return plan


def main():
    draw_source()
    (HERE / "brief.txt").write_text(BRIEF, encoding="utf-8")
    source_hash = hashlib.sha256((HERE / "reference.png").read_bytes()).hexdigest()
    plan = make_plan(source_hash)
    parts = [
        dict(id=n["id"], label=n["label"], parent_id=n["parent_id"], description=n["note"])
        for n in plan["nodes"]
    ]
    proposal = dict(
        summary="Original bench comparator design proposal with 50 physical occurrences in six subassemblies. Review this scheme before creating geometry.",
        parts=parts,
        unknowns=plan["assumptions"],
        manufacturing_notes=[
            "Every definition carries proposed process, material, interface notes and critical features. None is factory-confirmed.",
            "Review omitted threads, recipient holes, purchased dial internals, fits, retention and calibration before any production decision.",
        ],
    )
    for name, content in [("proposal.json", proposal), ("plan.json", plan)]:
        (HERE / name).write_text(json.dumps(content, indent=2) + "\n", encoding="utf-8")
    count = sum(n["definition_id"] is not None for n in plan["nodes"])
    assert count == 50 and len(plan["nodes"]) == 57 and len(plan["definitions"]) <= 32
    print(
        f"Wrote original source, literal brief, proposal and v2 plan: {count} occurrences, {len(plan['definitions'])} definitions, {len(plan['nodes'])} nodes."
    )
    print(f"Source SHA256 {source_hash}")


if __name__ == "__main__":
    main()
