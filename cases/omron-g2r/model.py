"""G2R-1-S + P2RF-05-E. Native smlibpy geometry, millimetres, +Z up.

The datasheet is an envelope/interface drawing, not a manufacturing drawing.
Internal mechanism and undimensioned moulding details are explicitly illustrative.
"""

from dataclasses import dataclass, field

from smlibpy import Axis, Box, Cylinder


@dataclass
class Definition:
    id: str
    label: str
    shape: object
    color: str
    opacity: float = 1.0
    states: list = field(default_factory=list)


@dataclass
class Occurrence:
    id: str
    definition_id: str
    group: str
    position: tuple
    explode: tuple
    label: str


def block(x, y, z, center):
    return Box(x, y, z).translate(center)


def vertical_hole(radius, height, center):
    return Cylinder(radius, height).translate(center)


def build():
    definitions = {}
    occurrences = []

    def define(id, label, shape, color, opacity=1.0, states=None):
        definitions[id] = Definition(
            id, label, shape.named(id).colored(color), color, opacity, states or []
        )

    def place(id, definition_id, group, position=(0, 0, 0), explode=(0, 0, 0), label=None):
        occurrences.append(
            Occurrence(
                id,
                definition_id,
                group,
                position,
                explode,
                label or definitions[definition_id].label,
            )
        )

    # Socket axes: width X=16, length Y=85.5; drawing rear mounting plane Z=0.
    # Central seating plane Z=25.5 is inferred from the 61 mm installed envelope.
    blank = block(16, 85.5, 11.5, (0, 0, 5.75))
    socket = blank + block(16, 44, 14, (0, 0, 18.5))
    for y0, y1, height in [
        (-42.75, -32, 29),
        (-32, -22, 38),
        (22, 28, 34),
        (28, 35, 41),
        (35, 42.75, 48),
    ]:
        socket = socket + block(16, y1 - y0, height - 11.4, (0, (y0 + y1) / 2, (height + 11.4) / 2))
    socket_states = [("Moulded stepped blank", socket)]
    socket = socket - block(18, 35.5, 4.2, (0, 0, 1.9))
    # Surface mounting axes are dimensioned 39.5 +/-0.1 mm apart on page 8.
    for y, diameter in [(19.75, 3.2), (-19.75, 3.5)]:
        socket = socket - vertical_hole(diameter / 2, 60, (0, y, 25))
    socket_states.append(("DIN recess and mounting holes", socket))
    terminals = [(-37.4, 29), (-27.2, 38), (24.5, 34), (31.5, 41), (38.8, 48)]
    for y, height in terminals:
        socket = socket - block(7.2, 7.6, 8.6, (0, y, height - 4.1))
        socket = socket - block(10, 3.5, 3.2, (0, y, height - 5.2))
    socket_states.append(("Five terminal access wells", socket))
    # Three contact blades at 5.2 mm pitch and two coil blades at 7.5 mm spacing.
    pins = [(0, -10.4), (0, -5.2), (0, 0), (-3.75, 12.3), (3.75, 12.3)]
    for index, (x, y) in enumerate(pins):
        socket = socket - block(5.15 if index < 3 else 1.65, 0.9, 7, (x, y, 22.2))
    # Clearance for the illustrative external retaining spring.
    socket = socket - block(14.8, 1.5, 3, (0, -15.6, 24.5))
    socket_states.append(("Relay pin interfaces", socket))
    define("socket_body", "P2RF-05-E moulded body", socket, "#d6d2c8", states=socket_states)
    place("socket_body_1", "socket_body", "socket", explode=(0, 0, -8))

    clamp = block(6, 6, 3, (0, 0, 0)) - vertical_hole(1.9, 5, (0, 0, 0))
    define("terminal_clamp", "Terminal clamp (simplified)", clamp, "#b49455")
    screw = Cylinder(2.7, 2).translate(0, 0, -1)
    screw = screw + Cylinder(1.75, 5.2).translate(0, 0, -4.5)
    screw = screw - block(6, 0.85, 1, (0, 0, -0.25))
    define("terminal_screw", "M3.5 screw (unthreaded demo)", screw, "#858b90")
    for i, (y, height) in enumerate(terminals, 1):
        place(
            f"terminal_clamp_{i}",
            "terminal_clamp",
            "socket",
            (0, y, height - 4),
            (0, (-1 if y < 0 else 1) * 12, 10),
            f"Terminal clamp {i}",
        )
        place(
            f"terminal_screw_{i}",
            "terminal_screw",
            "socket",
            (0, y, height - 0.2),
            (0, (-1 if y < 0 else 1) * 18, 20),
            f"Terminal screw {i}",
        )

    rail_clip = block(11, 9, 1.4, (0, -11, 1.1))
    rail_clip = rail_clip + block(11, 1.5, 2.5, (0, -15.2, 1.75))
    define("rail_clip", "DIN retaining slider (illustrative)", rail_clip, "#6e7379")
    place("rail_clip_1", "rail_clip", "socket", explode=(0, -20, -7))
    retainer = block(14.4, 0.6, 0.7, (0, -15.6, 24.6))
    for x in [-6.8, 6.8]:
        retainer = retainer + block(0.8, 0.6, 18, (x, -15.6, 33.5))
    retainer = retainer + block(14.4, 0.6, 0.8, (0, -15.6, 42.4))
    define("retainer", "Relay retaining spring (illustrative)", retainer, "#9a9da0")
    place("retainer_1", "retainer", "socket", explode=(0, -28, 8))

    # Relay definitions use their own seating plane Z=0; native placement is +25.5.
    relay_origin = (0, 0, 25.5)
    base = block(13, 29, 3.5, (0, 0, 1.75))
    base_blank = base
    for i, (x, y) in enumerate(pins):
        base = base - block(5.05 if i < 3 else 1.55, 0.8, 5, (x, y, 1.75))
    define(
        "relay_base",
        "G2R insulating base",
        base,
        "#30383d",
        states=[("Base blank", base_blank), ("Five blade slots", base)],
    )
    place("relay_base_1", "relay_base", "relay", relay_origin, (0, 0, 12))
    for i, (y, tip) in enumerate([(-10.4, 20), (-5.2, 18), (0, 16)], 1):
        blade = block(4.75, 0.5, 8.7, (0, y, -0.65))
        blade = blade + block(3.4, 0.5, tip - 3.4, (0, y, (tip + 3.4) / 2))
        drill = Cylinder(0.65, 1.5).rotate(Axis.X, 90).translate(0, y, -2.5)
        blade = blade - drill
        define(f"contact_lead_{i}", f"Contact blade {i} + spring (illustrative)", blade, "#bd9560")
        place(
            f"contact_lead_{i}_1",
            f"contact_lead_{i}",
            "relay",
            relay_origin,
            ((i - 2) * 16, -20, 20),
        )
    coil_pin = block(1.2, 0.5, 9, (0, 0, -0.5))
    define("coil_pin", "Coil terminal blade", coil_pin, "#aaaeb1")
    for i, (x, y) in enumerate(pins[3:], 1):
        place(
            f"coil_pin_{i}",
            "coil_pin",
            "relay",
            (x, y, 25.5),
            (x * 4, 16, 20),
            f"Coil terminal {i}",
        )

    # Illustrative internals: no manufacturer mechanical dimensions are claimed.
    bobbin = Cylinder(2.1, 20.1).translate(0, 6.5, 15.1)
    for z in [4.8, 25.1]:
        bobbin = bobbin + Cylinder(4.6, 1).translate(0, 6.5, z)
    bobbin = bobbin - Cylinder(1.8, 24).translate(0, 6.5, 15)
    define("bobbin", "Coil bobbin (illustrative)", bobbin, "#e5d6ac")
    place("bobbin_1", "bobbin", "relay", relay_origin, (-18, 10, 24))
    winding = Cylinder(4.25, 18.9) - Cylinder(2.2, 20)
    winding = winding.translate(0, 6.5, 15)
    define("winding", "Coil winding envelope (illustrative)", winding, "#b46f3c")
    place("winding_1", "winding", "relay", relay_origin, (-28, 10, 27))
    core = Cylinder(1.65, 22).translate(0, 6.5, 15)
    define("core", "Magnetic core (illustrative)", core, "#676e75")
    place("core_1", "core", "relay", relay_origin, (0, 10, 35))
    yoke = block(0.5, 10, 23.2, (5.05, 6.5, 15.1))
    yoke = yoke + block(7.1, 10, 0.5, (1.75, 6.5, 3.75))
    yoke = yoke + block(7.1, 10, 0.7, (1.75, 6.5, 26.35))
    define("yoke", "Magnetic yoke (illustrative)", yoke, "#747b81")
    place("yoke_1", "yoke", "relay", relay_origin, (22, 10, 30))
    armature = block(3.6, 22, 0.65, (0, 0, 27.2))
    define("armature", "Armature bridge (illustrative)", armature, "#a0a6aa")
    place("armature_1", "armature", "relay", relay_origin, (0, -10, 40))
    indicator = block(2, 2, 1.6, (0, -8, 28.4))
    define("indicator", "Mechanical indicator (illustrative)", indicator, "#ab584b")
    place("indicator_1", "indicator", "relay", relay_origin, (0, -15, 45))

    cover_blank = block(13, 29, 31.8, (0, 0, 19.4))
    cover = cover_blank - block(11.4, 27.4, 32, (0, 0, 18.6))
    define(
        "cover",
        "Transparent relay cover",
        cover,
        "#b9cbd3",
        0.18,
        [("Cover blank", cover_blank), ("Open-bottom shell", cover)],
    )
    place("cover_1", "cover", "relay", relay_origin, (0, 0, 64))
    nameplate = block(12.6, 28.6, 0.2, (0, 0, 35.4))
    define("nameplate", "Relay nameplate", nameplate, "#e9e7de")
    place("nameplate_1", "nameplate", "relay", relay_origin, (0, 0, 76))
    return definitions, occurrences
