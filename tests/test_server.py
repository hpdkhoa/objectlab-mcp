import asyncio
import importlib

import pytest

from objectlab.actions import call
from objectlab.server import load, mcp
from objectlab.tools import TOOLS


def tools():
    return {t.name: t for t in asyncio.run(mcp.list_tools())}


def test_the_tools_are_the_cut():
    assert sorted(tools()) == sorted(TOOLS) and len(TOOLS) == 7


def test_every_former_tool_is_one_action():
    pairs = [(m, f) for _, spec in TOOLS.values() for m, f, _ in spec]
    former = [p for p in pairs if p[0] != "objectlab.meaning"]
    assert len(pairs) == len(set(pairs)) and len(former) == 57 and len(pairs) == 58
    for m, f in pairs:
        assert callable(getattr(importlib.import_module(m), f))


def test_every_action_is_described_with_its_parameters():
    for name, t in tools().items():
        for _, _, action in TOOLS[name][1]:
            assert f"- {action}(" in t.description
        assert t.input_schema["properties"]["action"]["enum"] == [a for _, _, a in TOOLS[name][1]]


def test_unknown_action_and_bad_arguments_say_what_is_expected():
    name, (_, spec) = next(iter(TOOLS.items()))
    actions = load(spec)
    with pytest.raises(Exception, match="unknown action"):
        call(name, actions, "nope", {})
    with pytest.raises(Exception, match="Expected"):
        call(name, actions, spec[0][2], {"no_such_argument": 1})


def test_a_call_through_mcp_reaches_the_lab_function():
    result = asyncio.run(mcp.call_tool("finish_library", {"action": "list_finishes", "args": {}}))
    assert result
