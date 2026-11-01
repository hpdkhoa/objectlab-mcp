"""Blender side of Step 1: give every face of the hold mesh its part, its finish and whether a hand can reach it.

Run: blender -b --factory-startup -P label_faces.py -- job.json
The job names the source blend (one object per part), the rig blend and its mesh, and the output file. A face gets
its part by matching its exact vertex set to a face of the source blend. Exposed means a ray from the face along its
normal leaves the gun without hitting it.
"""

import json
import sys

import bpy
from mathutils.bvhtree import BVHTree

ROUND = 6  # metres to 1 micrometre: the rig is a join of the source objects, so vertices are equal, not close
LIFT = 1e-5  # metres the ray starts above its own face


def key(points):
    return tuple(sorted(tuple(round(c, ROUND) for c in p) for p in points))


def world_faces(obj):
    mw = obj.matrix_world
    vs = [mw @ v.co for v in obj.data.vertices]
    return vs, [[vs[i] for i in p.vertices] for p in obj.data.polygons]


job = json.load(open(sys.argv[sys.argv.index("--") + 1], encoding="utf-8"))

bpy.ops.wm.open_mainfile(filepath=job["source_blend"])
part_of = {}
for o in bpy.data.objects:
    if o.type == "MESH":
        for pts in world_faces(o)[1]:
            part_of.setdefault(key(pts), set()).add(o.name)

bpy.ops.wm.open_mainfile(filepath=job["rig_blend"])
obj = bpy.data.objects[job["mesh"]]
me = obj.data
vs, polys = world_faces(obj)
tree = BVHTree.FromPolygons([tuple(v) for v in vs], [tuple(p.vertices) for p in me.polygons])
rot = obj.matrix_world.to_3x3()
finish = [(m.get("finish") or m.name) if m else None for m in me.materials]

faces = []
for p, pts in zip(me.polygons, polys):
    owners = sorted(part_of.get(key(pts), ()))
    c = sum(pts, pts[0] * 0) / len(pts)
    n = (rot @ p.normal).normalized()
    hit, hit_n, _, dist = tree.ray_cast(c + n * LIFT, n)
    ray = "escapes" if hit is None else ("gap" if hit_n.dot(n) < 0 else "covered")  # tree is in world space
    faces.append({"parts": owners, "finish": finish[p.material_index], "c": list(c), "n": list(n),
                  "a": p.area, "ray": ray, "gap_m": None if hit is None else dist + LIFT,
                  "v": [list(q) for q in pts]})

json.dump({"mesh": job["mesh"], "faces": faces}, open(job["out"], "w", encoding="utf-8"))
print("LABEL_FACES", len(faces))
