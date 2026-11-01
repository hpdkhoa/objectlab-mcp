"""Step 1 of the meaning plan: meaning on the object.

Every face of the hold mesh gets its part. Contact faces get a role (grip_back, guard, trigger_blade, ...). Each role
has a written definition and a check with numbers; a role that misses its definition stops the run. Each part gets
its material, density, friction, volume and mass, and the gun gets its mass centre. Every number is a record: value,
unit, meaning, of what, kind, source, check.

Frame: the gun's own axes, measured from the mesh. forward runs from the breech to the muzzle along the bore, up runs
from the grip toward the bore, left = up x forward. Positions print in cm along (forward, up, left).
"""

import hashlib
import json
import math
import os
import shutil
import subprocess
from pathlib import Path

from mcp.server.mcpserver.exceptions import ToolError

HERE = Path(__file__).parent
SCRIPT = HERE / "blender" / "label_faces.py"
CONTRACT = "objectlab-meaning/1"

WU = "Wu et al. 2014, 2017 (skin on handle), stored in poselab-mcp docs/recoil_sources.json"
MATERIALS = {
    "steel": {"density_g_cm3": 7.85, "density_source": "carbon steel 7.85 g/cm3 (ASTM A36 data sheet; supplier tables "
              "7.75 to 8.05). Owner accepted 2026-11-01.",
              "friction": 0.30, "friction_source": WU + ". Owner 2026-11-01: \"0.30 for now and can be tuning later "
              "when start the stimulation\"."},
    "phenolic": {"density_g_cm3": 1.40, "density_source": "phenolic moulding compound 1.37 to 1.42 g/cm3 (Plenco "
                 "07523 and 03557, ASTM D792); 1.40 is the middle. M1911A1 WWII stocks are Keyes Fibre phenolic "
                 "(dealer descriptions). Owner accepted 2026-11-01.",
                 "friction": 0.30, "friction_source": WU + ". Same owner decision."},
}
FINISH_MATERIAL = {"parkerized": "steel", "blued": "steel", "plastic": "phenolic"}

# Gun type -> the facts the roles need. The parts are the blueprint's part names. A role takes faces with area > 0
# whose ray along the normal escapes the gun (the outside skin); "ray" widens that, e.g. to a gap of open air.
GUNS = {
    "M1911A1": {
        "mass_kg": 1.253,
        "mass_source": "FM 23-35 p.8: 2.437 lb with empty magazine + 0.325 lb of 7 rounds",
        # parts with their own sourced mass; the other parts share the rest by volume x density
        "part_mass_g": {"magazine": (218.18, "FM 23-35 p.8: loaded magazine 0.481 lb. Owner 2026-11-01: use the "
                                    "sourced magazine mass (the mesh magazine is a solid block)")},
        "barrel": "barrel", "grip": "stocks", "slide": "slide", "frame": "frame", "trigger": "trigger",
        "left_mark": "thumb_safety", "sights": ["sight_rear", "sight_front"],
        "roles": {
            "top": {"parts": ["slide"], "faces": "+up", "above_bore": True,
                    "definition": "the slide's outside faces that face up, above the bore line"},
            "trigger_blade": {"parts": ["trigger"], "faces": "+forward", "ray": ("escapes", "gap"),
                              "definition": "the trigger's faces that face forward into open air, inside the guard "
                              "opening"},
            "grip_back": {"parts": ["housing", "grip_safety"], "faces": "-forward",
                          "definition": "the outside faces of the housing and the grip safety that face back; "
                          "behind the guard, under the slide"},
            "grip_front": {"parts": ["frame"], "faces": "+forward",
                           "definition": "the frame's outside faces that face forward, below the guard opening "
                           "and behind the trigger (the front strap)"},
            "grip_side_l": {"parts": ["stocks"], "faces": "+left",
                            "definition": "the stocks' outside faces that face left"},
            "grip_side_r": {"parts": ["stocks"], "faces": "-left",
                            "definition": "the stocks' outside faces that face right"},
            "thumb_rest": {"parts": ["thumb_safety"], "faces": "+up",
                           "definition": "the thumb safety's outside faces that face up, on the left side"},
            "guard": {"parts": ["frame"], "faces": "cut",
                      "definition": "a closed loop around the trigger: the frame faces cut by the middle plane "
                                    "that lie in front of the opening's rear and below its top"},
        },
        "role_owner": "Owner 2026-11-01: \"Yes, these roles\" (grip_back, grip_front, grip_side_l/r, guard, "
                      "trigger_blade, top, thumb_rest, bore_axis).",
    },
}


# ---------- small vector helpers ----------

def sub(a, b):
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def unit(a):
    n = math.sqrt(dot(a, a))
    return [a[0] / n, a[1] / n, a[2] / n]


def rec(value, unit_, meaning, of, kind, source, check):
    return {"value": value, "unit": unit_, "meaning": meaning, "of": of, "kind": kind, "source": source,
            "check": check}


# ---------- the gun frame ----------

def gun_frame(faces, gun):
    """forward, up, left and the bore line, measured from the barrel and the grip."""
    barrel = [p for f in faces if f["part"] == gun["barrel"] for p in f["v"]]
    grip = [f["c"] for f in faces if f["part"] == gun["grip"]]
    if not barrel or not grip:
        raise ToolError("gun frame: the barrel or the grip part has no faces")
    n = len(barrel)
    mean = [sum(p[i] for p in barrel) / n for i in range(3)]
    # the bore runs along the barrel's longest extent
    spans = [max(p[i] for p in barrel) - min(p[i] for p in barrel) for i in range(3)]
    ax = spans.index(max(spans))
    axis = [1.0 if i == ax else 0.0 for i in range(3)]
    gc = [sum(c[i] for c in grip) / len(grip) for i in range(3)]
    # forward points from the grip side of the barrel to its far end (the muzzle)
    lo = min(p[ax] for p in barrel)
    hi = max(p[ax] for p in barrel)
    if abs(gc[ax] - lo) < abs(gc[ax] - hi):
        forward = axis
    else:
        forward = [-a for a in axis]
    d = sub(mean, gc)
    up = unit(sub(d, [forward[i] * dot(d, forward) for i in range(3)]))
    left = cross(up, forward)
    # bore line: the barrel's centre across the bore
    centre = [mean[i] - forward[i] * dot(mean, forward) for i in range(3)]
    return {"forward": forward, "up": up, "left": left, "bore_point": centre}


def local(p, fr):
    """(forward, up, left) in cm of a point, from the bore line."""
    q = sub(p, fr["bore_point"])
    return [dot(q, fr["forward"]) * 100, dot(q, fr["up"]) * 100, dot(q, fr["left"]) * 100]


def ldir(n, fr):
    return [dot(n, fr["forward"]), dot(n, fr["up"]), dot(n, fr["left"])]


def dominant(n_local):
    """'+forward', '-up', ...: the axis the normal points along most."""
    names = ("forward", "up", "left")
    i = max(range(3), key=lambda k: abs(n_local[k]))
    return ("+" if n_local[i] > 0 else "-") + names[i]


# ---------- the middle-plane cut ----------

def cut_segments(faces, fr):
    """Segments (forward, up) in cm where the faces cross the plane left = 0."""
    segs = []
    for f in faces:
        pts = [local(p, fr) for p in f["v"]]
        hits = []
        for i in range(len(pts)):
            a, b = pts[i - 1], pts[i]
            if (a[2] < 0) != (b[2] < 0):
                t = a[2] / (a[2] - b[2])
                hits.append((a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])))
        for i in range(0, len(hits) - 1, 2):
            segs.append((hits[i], hits[i + 1], f["i"]))
    return segs


def chains(segs, tol=1e-4):
    """Join segments end to end into chains. Returns [(points, closed, face ids)]."""
    def k(p):
        return (round(p[0] / tol), round(p[1] / tol))

    ends = {}
    for j, (a, b, _) in enumerate(segs):
        ends.setdefault(k(a), []).append(j)
        ends.setdefault(k(b), []).append(j)
    used = [False] * len(segs)
    out = []
    for s in range(len(segs)):
        if used[s]:
            continue
        used[s] = True
        a, b, fid = segs[s]
        pts, ids = [a, b], {fid}
        closed = False
        while True:
            nxt = [j for j in ends.get(k(pts[-1]), []) if not used[j]]
            if not nxt:
                break
            j = nxt[0]
            used[j] = True
            a, b, fid = segs[j]
            ids.add(fid)
            pts.append(b if k(a) == k(pts[-1]) else a)
            if k(pts[-1]) == k(pts[0]):
                closed = True
                break
        out.append((pts, closed, ids))
    return out


def area2(pts):
    return abs(sum(pts[i - 1][0] * pts[i][1] - pts[i][0] * pts[i - 1][1] for i in range(len(pts)))) / 2


def inside(pt, poly):
    x, y = pt
    c = False
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i - 1], poly[i]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            c = not c
    return c


# ---------- roles ----------

def summary(sel, fr, of, rule, source):
    """The measured records of one role."""
    area = sum(f["a"] for f in sel)
    c = [sum(f["a"] * f["c"][i] for f in sel) / area for i in range(3)]
    n = unit([sum(f["a"] * f["n"][i] for f in sel) for i in range(3)])
    pts = [local(p, fr) for f in sel for p in f["v"]]
    lo = [min(p[i] for p in pts) for i in range(3)]
    hi = [max(p[i] for p in pts) for i in range(3)]
    return {
        "faces": len(sel),
        "area": rec(round(area * 1e4, 3), "cm2", "contact area of the role", of, "surface", source, rule),
        "centre": rec([round(v, 3) for v in local(c, fr)], "cm (forward, up, left)", "area centre", of, "point",
                      source, rule),
        "normal": rec([round(v, 3) for v in ldir(n, fr)], "unit (forward, up, left)", "area-weighted normal", of,
                      "line", source, rule),
        "bounds": rec([[round(a, 3), round(b, 3)] for a, b in zip(lo, hi)], "cm (forward, up, left)",
                      "extent", of, "surface", source, rule),
        "width": rec(round(hi[2] - lo[2], 3), "cm", "width across the gun (left to right)", of, "line", source,
                     rule),
    }


def label_roles(faces, gun, fr):
    """Pick each role's faces and test it against its definition. Returns (roles, checks)."""
    for f in faces:
        f["L"] = local(f["c"], fr)
        f["dom"] = dominant(ldir(f["n"], fr))
    src = "measured: the hold mesh faces, matched to the blueprint parts"
    picked, checks = {}, []

    def ok(name, passed, numbers, rule):
        checks.append({"check": name, "pass": bool(passed), "numbers": numbers, "rule": rule})

    for name, r in gun["roles"].items():
        if r["faces"] == "cut":
            continue
        rays = r.get("ray", ("escapes",))
        picked[name] = [f for f in faces if f["part"] in r["parts"] and f["a"] > 0 and f["ray"] in rays
                        and f["dom"] == r["faces"] and (not r.get("above_bore") or f["L"][1] > 0)]

    # guard: the opening is the smallest closed loop of the frame's middle cut around the trigger blade
    frame = [f for f in faces if f["part"] == gun["frame"]]
    blade = picked.get("trigger_blade") or []
    hole = None
    if blade:
        tb = summary(blade, fr, "trigger_blade", "", src)["centre"]["value"]
        loops = [(p, ids) for p, closed, ids in chains(cut_segments(frame, fr)) if closed and inside(tb[:2], p)]
        if loops:
            hole = min(loops, key=lambda x: area2(x[0]))
        ok("guard: a closed loop of the frame's middle cut around the trigger blade", hole is not None,
           {"trigger_blade_centre_cm": tb[:2], "closed_loops_around_it": len(loops)},
           gun["roles"]["guard"]["definition"])
    if hole:
        hp = hole[0]
        f_min = min(p[0] for p in hp)
        u_max = max(p[1] for p in hp)
        u_min = min(p[1] for p in hp)
        cut_ids = {fid for _, _, fid in cut_segments(frame, fr)}
        picked["guard"] = [f for f in frame if f["i"] in cut_ids and f["L"][0] >= f_min - 1e-4
                           and f["L"][1] <= u_max + 1e-4]
        opening = {"rear_cm": round(f_min, 3), "top_cm": round(u_max, 3), "bottom_cm": round(u_min, 3),
                   "front_cm": round(max(p[0] for p in hp), 3), "area_cm2": round(area2(hp), 3)}
        # the front strap sits below the opening and behind the trigger
        t_rear = min(f["L"][0] for f in faces if f["part"] == gun["trigger"])
        picked["grip_front"] = [f for f in picked.get("grip_front", []) if f["L"][1] < u_min and f["L"][0] < t_rear]
    else:
        opening = None
        picked["guard"] = []

    roles = {}
    for name, sel in picked.items():
        r = gun["roles"][name]
        ok(f"{name}: has faces", len(sel) > 0, {"faces": len(sel)}, r["definition"])
        if sel:
            roles[name] = {"definition": r["definition"], "parts": r["parts"], **summary(sel, fr, name,
                                                                                          r["definition"], src)}
            for f in sel:
                f["role"] = name

    def cen(name):
        return roles[name]["centre"]["value"] if name in roles else None

    def bnd(name):
        return roles[name]["bounds"]["value"] if name in roles else None

    slide_bottom = min(f["L"][1] for f in faces if f["part"] == gun["slide"])
    if "grip_back" in roles and opening:
        b = bnd("grip_back")
        ok("grip_back: behind the guard opening and under the slide",
           b[0][1] < opening["rear_cm"] and b[1][1] <= slide_bottom + 1e-3,
           {"grip_back_front_cm": b[0][1], "opening_rear_cm": opening["rear_cm"], "grip_back_top_cm": b[1][1],
            "slide_bottom_cm": round(slide_bottom, 3)}, gun["roles"]["grip_back"]["definition"])
        n = roles["grip_back"]["normal"]["value"]
        ok("grip_back: faces back", n[0] < 0, {"normal_forward": n[0], "normal_up": n[1]},
           gun["roles"]["grip_back"]["definition"])
    if "trigger_blade" in roles and opening:
        c = cen("trigger_blade")
        ok("trigger_blade: inside the guard opening", inside(c[:2], hole[0]), {"centre_cm": c[:2], **opening},
           gun["roles"]["trigger_blade"]["definition"])
    if "top" in roles:
        b = bnd("top")
        slide_top = max(local(p, fr)[1] for f in faces if f["part"] == gun["slide"] for p in f["v"])
        ok("top: holds the slide's highest point", abs(b[1][1] - slide_top) < 1e-3,
           {"top_highest_cm": b[1][1], "slide_highest_cm": round(slide_top, 3)}, gun["roles"]["top"]["definition"])
        for s in gun.get("sights", []):
            sf = [local(p, fr)[0] for f in faces if f["part"] == s for p in f["v"]]
            ok(f"top: the {s} stands on it", b[0][0] <= min(sf) and max(sf) <= b[0][1] + 1e-3,
               {"sight_cm": [round(min(sf), 3), round(max(sf), 3)], "top_cm": b[0]},
               gun["roles"]["top"]["definition"])
    for side, sign in (("grip_side_l", 1), ("grip_side_r", -1)):
        if side in roles:
            n = roles[side]["normal"]["value"][2]
            ok(f"{side}: faces {'left' if sign > 0 else 'right'}", n * sign > 0, {"normal_left": n},
               gun["roles"][side]["definition"])
    if "thumb_rest" in roles:
        c = cen("thumb_rest")
        ok("thumb_rest: on the left side", c[2] > 0, {"centre_left_cm": c[2]}, gun["roles"]["thumb_rest"]["definition"])
    return roles, checks, opening


# ---------- parts: material, volume, mass ----------

def part_records(faces, gun, fr):
    parts = {}
    for f in faces:
        parts.setdefault(f["part"], []).append(f)
    out = {}
    raw_total = 0.0
    for name, fs in parts.items():
        finishes = sorted({f["finish"] for f in fs})
        fin = finishes[0].removeprefix("M_") if finishes else None
        mat = FINISH_MATERIAL.get(fin)
        if len(finishes) != 1 or mat is None:
            raise ToolError(f"part {name}: finish {finishes} has no material in FINISH_MATERIAL")
        # divergence theorem on planar faces: volume and its centre (tetrahedra from the origin)
        vol, mom = 0.0, [0.0, 0.0, 0.0]
        edges = {}
        for f in fs:
            w = dot(f["c"], f["n"]) * f["a"] / 3
            vol += w
            for i in range(3):
                mom[i] += w * 0.75 * f["c"][i]
            v = [tuple(round(c, 7) for c in p) for p in f["v"]]
            for i in range(len(v)):
                e = tuple(sorted((v[i - 1], v[i])))
                edges[e] = edges.get(e, 0) + 1
        open_edges = sum(1 for c in edges.values() if c != 2)
        m = MATERIALS[mat]
        raw = vol * 1e6 * m["density_g_cm3"]
        raw_total += raw
        out[name] = {"faces": len(fs), "finish": fin, "material": mat, "_raw_g": raw,
                     "_centre": [mom[i] / vol for i in range(3)] if vol else None,
                     "density": rec(m["density_g_cm3"], "g/cm3", "material density", name, "value",
                                    m["density_source"], "sourced"),
                     "friction": rec(m["friction"], "", "skin friction on this part (lower bound)", name, "value",
                                     m["friction_source"], "to tune in the simulation"),
                     "volume": rec(round(vol * 1e6, 3), "cm3", "closed mesh volume", name, "value",
                                   "measured: hold mesh faces, divergence theorem",
                                   f"open or non-manifold edges: {open_edges} (0 = closed)"),
                     "open_edges": open_edges}
    fixed = {n: v for n, v in gun.get("part_mass_g", {}).items() if n in out}
    raw_rest = raw_total - sum(out[n]["_raw_g"] for n in fixed)
    k = (gun["mass_kg"] * 1000 - sum(g for g, _ in fixed.values())) / raw_rest
    total = [0.0, 0.0, 0.0]
    for name, p in out.items():
        raw = p.pop("_raw_g")
        c = p.pop("_centre")
        if name in fixed:
            g, src = fixed[name]
            p["mass"] = rec(g, "g", "part mass: sourced", name, "value", src, f"volume x density gave {raw:.1f} g")
        else:
            g = raw * k
            p["mass"] = rec(round(g, 2), "g", "part mass: volume x density, scaled so the gun meets its listed mass",
                            name, "value", gun["mass_source"],
                            f"scale {k:.4f}; {raw_total:.1f} g raw for the whole gun")
        for i in range(3):
            total[i] += g * c[i]
    com = [t / (gun["mass_kg"] * 1000) for t in total]
    centre = rec([round(v, 3) for v in local(com, fr)], "cm (forward, up, left)", "mass centre of the gun",
                 "gun", "point", "volume x sourced density per part, scaled to " + gun["mass_source"],
                 "owner 2026-11-01: mesh volume x density scaled to 1.253 kg; sourced part masses kept: "
                 + (", ".join(fixed) or "none"))
    return out, centre, round(raw_total, 1)


# ---------- the run ----------

def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def find_blender(blender: str | None) -> str:
    exe = blender or os.environ.get("OBJECTLAB_BLENDER") or shutil.which("blender")
    if not exe or not Path(exe).exists():
        raise ToolError("label: no Blender. Pass blender= or set OBJECTLAB_BLENDER.")
    return exe


def faces_from_blender(source_blend, rig_blend, mesh, out_dir, blender):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    job = {"source_blend": str(source_blend), "rig_blend": str(rig_blend), "mesh": mesh,
           "out": str(out / "faces.json")}
    jp = out / "label_faces.job.json"
    jp.write_text(json.dumps(job, indent=1), encoding="utf-8")
    r = subprocess.run([find_blender(blender), "-b", "--factory-startup", "-P", str(SCRIPT), "--", str(jp)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    (out / "label_faces.log").write_text(r.stdout + r.stderr, encoding="utf-8")
    if "LABEL_FACES" not in r.stdout:
        raise ToolError(f"label: Blender failed, see {out / 'label_faces.log'}")
    return json.loads((out / "faces.json").read_text(encoding="utf-8"))["faces"]


def build(faces, gun_name):
    """Pure part of Step 1: parts, frame, roles, checks. `faces` as written by label_faces.py."""
    gun = GUNS[gun_name]
    unmatched = [i for i, f in enumerate(faces) if len(f["parts"]) != 1]
    checks = [{"check": "every polygon belongs to exactly one part (G2)", "pass": not unmatched,
               "numbers": {"faces": len(faces), "unmatched_or_shared": len(unmatched),
                           "first": [{"face": i, "centre_m": faces[i]["c"]} for i in unmatched[:5]]},
               "rule": "a polygon with no part stops the run and is reported with its place"}]
    if unmatched:
        return {"status": "FAIL", "checks": checks}
    for i, f in enumerate(faces):
        f["i"] = i
        f["part"] = f["parts"][0]
    fr = gun_frame(faces, gun)
    lm = [f["c"] for f in faces if f["part"] == gun["left_mark"]]
    side = local([sum(c[i] for c in lm) / len(lm) for i in range(3)], fr)[2]
    checks.append({"check": f"frame: the {gun['left_mark']} sits on the left", "pass": side > 0,
                   "numbers": {"left_cm": round(side, 3)}, "rule": "left = up x forward; a 1911 thumb safety is "
                   "on the left side"})
    barrel = [local(p, fr) for f in faces if f["part"] == gun["barrel"] for p in f["v"]]
    off = [sum(p[i] for p in barrel) / len(barrel) for i in (1, 2)]
    roles, rchecks, opening = label_roles(faces, gun, fr)
    checks += rchecks
    parts, centre, raw = part_records(faces, gun, fr)
    bore = {"definition": "the line through the barrel's centre along forward",
            **{"line": rec({"point_m": [round(v, 6) for v in fr["bore_point"]],
                            "direction": fr["forward"]}, "m", "bore axis", gun["barrel"], "line",
                           "measured: barrel vertices", "barrel centre offset from the line (up, left) cm: "
                           f"{[round(v, 4) for v in off]}")}}
    roles["bore_axis"] = bore
    failed = [c for c in checks if not c["pass"]]
    return {
        "contract": CONTRACT, "gun": gun_name, "status": "FAIL" if failed else "PASS",
        "frame": {"forward": fr["forward"], "up": fr["up"], "left": fr["left"],
                  "origin": "the bore line; cm along (forward, up, left)"},
        "roles_owner": gun["role_owner"], "roles": roles, "guard_opening_cm": opening,
        "parts": parts, "mass_centre": centre, "raw_mass_g": raw,
        "role_faces": {f["i"]: f["role"] for f in faces if "role" in f},
        "part_faces": {name: [f["i"] for f in faces if f["part"] == name] for name in parts},
        "checks": checks,
    }


def label(gun: str, source_blend: str, rig_blend: str, mesh: str, out_dir: str, blender: str | None = None,
          force: bool = False) -> dict:
    """Step 1, meaning on the object: every face of the hold mesh gets its part, contact faces get a role checked
    against its definition, each part gets material, density, friction, volume and mass, and the gun its mass centre.

    gun: a name in GUNS (M1911A1). source_blend: the build with one object per part. rig_blend, mesh: the hold mesh.
    out_dir: where meaning.json (the cache) goes. A changed blend makes the cache stale; force relabels anyway.
    Returns the status, the checks with numbers and the role and part records; a FAIL names the check and numbers.
    """
    if gun not in GUNS:
        raise ToolError(f"label: unknown gun {gun!r}. Known: {', '.join(GUNS)}")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    cache = out / "meaning.json"
    facts = json.dumps({"gun": GUNS[gun], "materials": MATERIALS}, sort_keys=True, default=str).encode()
    hashes = {"source_blend": sha(source_blend), "rig_blend": sha(rig_blend),
              "facts": hashlib.sha256(facts).hexdigest()}
    old = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else {}
    if old.get("inputs", {}).get("sha256") == hashes and old.get("contract") == CONTRACT and not force:
        return brief(old, cache, cached=True)
    same_blends = all(old.get("inputs", {}).get("sha256", {}).get(k) == hashes[k] for k in ("source_blend", "rig_blend"))
    if same_blends and (out / "faces.json").exists() and not force:
        faces = json.loads((out / "faces.json").read_text(encoding="utf-8"))["faces"]  # only the facts changed
    else:
        faces = faces_from_blender(source_blend, rig_blend, mesh, out, blender)
    result = build(faces, gun)
    result["inputs"] = {"source_blend": str(source_blend), "rig_blend": str(rig_blend), "mesh": mesh,
                        "sha256": hashes}
    if result["status"] == "PASS":
        cache.write_text(json.dumps(result, indent=1), encoding="utf-8")
    else:
        (out / "meaning.fail.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    return brief(result, cache, cached=False)


def brief(result, cache, cached):
    """What the tool returns: status, failed checks, role and part numbers; face lists stay in the cache file."""
    return {"status": result["status"], "cached": cached, "cache": str(cache),
            "checks": result["checks"],
            "roles": {k: {f: v[f] for f in v if f in ("faces", "area", "centre", "normal", "width", "line")}
                      for k, v in result.get("roles", {}).items()},
            "parts": {k: {"material": v["material"], "volume_cm3": v["volume"]["value"],
                          "mass_g": v["mass"]["value"], "friction": v["friction"]["value"],
                          "open_edges": v["open_edges"]} for k, v in result.get("parts", {}).items()},
            "mass_centre": result.get("mass_centre"), "guard_opening_cm": result.get("guard_opening_cm")}
