import json

import pytest

from objectlab import meaning as M


def test_chains_close_a_square_and_find_a_point_inside():
    sq = [(0, 0), (1, 0), (1, 1), (0, 1)]
    segs = [(sq[i - 1], sq[i], i) for i in range(4)]
    (pts, closed, ids), = M.chains(segs)
    assert closed and ids == {0, 1, 2, 3}
    assert M.inside((0.5, 0.5), pts) and not M.inside((1.5, 0.5), pts)
    assert M.area2(pts[:-1]) == pytest.approx(1.0)


def test_an_open_chain_is_not_closed():
    (pts, closed, _), = M.chains([((0, 0), (1, 0), 0), ((1, 0), (1, 1), 1)])
    assert not closed and len(pts) == 3


def test_dominant_names_the_axis_and_its_sign():
    assert M.dominant([0.1, -0.9, 0.2]) == "-up"
    assert M.dominant([0.0, 0.3, 0.95]) == "+left"


def quad(part, pts, n, finish="M_parkerized", ray="escapes"):
    c = [sum(p[i] for p in pts) / 4 for i in range(3)]
    return {"parts": [part], "finish": finish, "c": c, "n": n, "a": 1e-4, "ray": ray, "gap_m": None, "v": pts}


def test_a_face_with_no_part_stops_the_run_with_its_place():
    f = quad("frame", [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], [0, 0, 1])
    f["parts"] = []
    r = M.build([f], "M1911A1")
    assert r["status"] == "FAIL"
    assert r["checks"][0]["numbers"]["unmatched_or_shared"] == 1
    assert r["checks"][0]["numbers"]["first"][0]["centre_m"] == f["c"]


def test_a_face_shared_by_two_parts_stops_the_run():
    f = quad("frame", [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], [0, 0, 1])
    f["parts"] = ["frame", "slide"]
    assert M.build([f], "M1911A1")["status"] == "FAIL"


def test_the_gun_frame_points_forward_away_from_the_grip():
    # barrel along -y from y=0 to y=-0.1, grip below and behind at y=+0.05
    barrel = quad("barrel", [[-0.01, 0, -0.01], [0.01, 0, -0.01], [0.01, -0.1, 0.01], [-0.01, -0.1, 0.01]],
                  [0, 0, 1], "M_blued")
    grip = quad("stocks", [[0, 0.04, -0.06], [0, 0.06, -0.06], [0, 0.06, -0.04], [0, 0.04, -0.04]], [1, 0, 0],
                "M_plastic")
    for f in (barrel, grip):
        f["part"] = f["parts"][0]
    fr = M.gun_frame([barrel, grip], M.GUNS["M1911A1"])
    assert fr["forward"] == [0.0, -1.0, 0.0]
    assert fr["up"][2] == pytest.approx(1.0, abs=1e-9)
    assert fr["left"] == pytest.approx([1.0, 0.0, 0.0])  # left = up x forward


def test_every_material_has_its_sources():
    for m in M.MATERIALS.values():
        assert m["density_source"] and m["friction_source"] and m["friction"] == 0.30
    assert set(M.FINISH_MATERIAL.values()) <= set(M.MATERIALS)


def test_a_fresh_cache_skips_blender_and_a_changed_blend_relabels(tmp_path, monkeypatch):
    src, rig = tmp_path / "src.blend", tmp_path / "rig.blend"
    src.write_bytes(b"a")
    rig.write_bytes(b"b")
    calls = []

    def fake_faces(*a):
        calls.append(a)
        return []

    monkeypatch.setattr(M, "faces_from_blender", fake_faces)
    monkeypatch.setattr(M, "build", lambda faces, gun: {"contract": M.CONTRACT, "status": "PASS", "checks": []})
    M.label("M1911A1", str(src), str(rig), "Mesh", str(tmp_path / "out"))
    assert json.loads((tmp_path / "out" / "meaning.json").read_text())["inputs"]["sha256"]
    assert M.label("M1911A1", str(src), str(rig), "Mesh", str(tmp_path / "out"))["cached"] is True
    rig.write_bytes(b"changed")
    assert M.label("M1911A1", str(src), str(rig), "Mesh", str(tmp_path / "out"))["cached"] is False
    assert len(calls) == 2


def test_changed_gun_facts_relabel_from_the_saved_faces(tmp_path, monkeypatch):
    src, rig = tmp_path / "src.blend", tmp_path / "rig.blend"
    src.write_bytes(b"a")
    rig.write_bytes(b"b")
    calls = []

    def fake_faces(*a):
        calls.append(a)
        (tmp_path / "out" / "faces.json").write_text(json.dumps({"faces": []}))
        return []

    monkeypatch.setattr(M, "faces_from_blender", fake_faces)
    monkeypatch.setattr(M, "build", lambda faces, gun: {"contract": M.CONTRACT, "status": "PASS", "checks": []})
    M.label("M1911A1", str(src), str(rig), "Mesh", str(tmp_path / "out"))
    monkeypatch.setitem(M.GUNS["M1911A1"], "mass_kg", 1.3)
    assert M.label("M1911A1", str(src), str(rig), "Mesh", str(tmp_path / "out"))["cached"] is False
    assert len(calls) == 1  # Blender ran once; the second label read faces.json


def test_a_sourced_part_mass_is_kept_and_the_rest_meets_the_listed_mass():
    def box(part, x0, finish):
        # a closed 1 cm cube at x0 (m), six outward quads
        s, out = 0.01, []
        for ax in range(3):
            for sign in (-1, 1):
                n = [0, 0, 0]
                n[ax] = sign
                c = [x0 + s / 2, s / 2, s / 2]
                c[ax] += sign * s / 2
                out.append({"part": part, "finish": finish, "c": c, "n": n, "a": s * s, "v": [c] * 4})
        return out
    faces = box("magazine", 0.0, "M_blued") + box("frame", 0.05, "M_parkerized")
    fr = {"forward": [1, 0, 0], "up": [0, 0, 1], "left": [0, 1, 0], "bore_point": [0, 0, 0]}
    parts, centre, _ = M.part_records(faces, M.GUNS["M1911A1"], fr)
    assert parts["magazine"]["mass"]["value"] == 218.18
    assert parts["frame"]["mass"]["value"] == pytest.approx(1253 - 218.18, abs=0.01)


def test_ring_middle_and_its_opening_at_that_height():
    sq = [(0, 0), (4, 0), (4, 2), (0, 2)]
    assert M.poly_centroid(sq) == pytest.approx((2.0, 1.0))
    assert M.crossings(sq, 1, 1.0) == pytest.approx([0.0, 4.0])  # the opening along forward at up = 1
    assert M.crossings(sq, 0, 3.0) == pytest.approx([0.0, 2.0])  # bottom and top at forward = 3
