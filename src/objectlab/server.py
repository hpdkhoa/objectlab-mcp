"""Object Lab: Names every part of an object, measures it from sources, builds it, and gives it a finish.

7 tools, each an action tool over the existing lab functions (57 former tools).
Merged from: weaponlab-mcp (Blueprint Lab), modellab-mcp, coatinglab-mcp.
"""

import importlib

from mcp.server.mcpserver import MCPServer

from .actions import add_action_tool
from .tools import TOOLS

mcp = MCPServer(
    "objectlab",
    instructions="Names every part of an object, measures it from sources, builds it, and gives it a finish. Each tool takes `action` and that action's `args`; the tool description lists them.",
)


def load(spec):
    return {action: getattr(importlib.import_module(module), fn) for module, fn, action in spec}


for _name, (_summary, _spec) in TOOLS.items():
    add_action_tool(mcp, _name, _summary, load(_spec))


def main():
    mcp.run()


if __name__ == "__main__":
    main()
