# objectlab-mcp

Object Lab: Names every part of an object, measures it from sources, builds it, and gives it a finish.

7 tools replace 57. Each tool takes `action` and `args`, and calls the existing lab function
unchanged. Merged from: weaponlab-mcp (Blueprint Lab), modellab-mcp, coatinglab-mcp. One new action,
`object_part` `label`, builds Step 1 (meaning on the object). Plan steps: 1 of
[the labs plan](https://github.com/hpdkhoa/poselab-mcp/blob/main/docs/MEANING_PLAN.md).

| Tool | Actions |
|---|---|
| `object_source` | add, scan, page, text, specs, fact_add, figure_add |
| `object_trace` | grid, calibrate, frame, align, trace, measure, photomap |
| `object_part` | new, part, hole, mark, views, loft, follow_part, shape_across, round_corners, bevel, feature, round, label |
| `object_build` | build, to_gunkit, build_gun, build_gun_clips |
| `object_read` | parts_list, numbers, read, check, render, showcase, list_builds, read_build, compare_to_reference, list_platforms, describe_params, list_presets, list_attachments, list_references |
| `finish_library` | list_finishes, read_finish, check_library, check_finish, list_wear_levels, list_templates, engine_params |
| `finish_apply` | spec_for_modellab, describe_model, validate_spec, bake, check_coating, render_variants |

## Step 1: label

`label` gives every face of a hold mesh its part, by exact vertex match with the build that has one object per
part. A face with no part stops the run. Contact faces get a role (`grip_back`, `grip_front`, `grip_side_l`,
`grip_side_r`, `guard`, `trigger_blade`, `top`, `thumb_rest`, `bore_axis`, and the line `line_b`). Each role has a written definition and a
check with numbers, and a failed check stops the run. Each part gets material, density, friction, volume and mass; a part with a sourced mass keeps it. The
gun gets its mass centre. The result goes to `meaning.json`, which a changed blend or changed gun facts make stale. Blender runs headless:
pass `blender=` or set `OBJECTLAB_BLENDER`.

## Install

```bash
pip install "objectlab-mcp @ git+https://github.com/hpdkhoa/objectlab-mcp.git"
claude mcp add --scope user objectlab -- objectlab-mcp
```

## Test

```bash
pip install -e ".[test]" && pytest
```

MIT license.
