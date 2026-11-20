"""Tool lockdown: make our own tools the ONLY tools the agent can use.

The Agent SDK ships Claude Code's built-in tools (Bash, Write, Edit, WebFetch, ...).
`allowed_tools` only AUTO-APPROVES tools; it does not remove the others. For a
personal assistant that must not touch the filesystem or shell, we layer three
independent defenses:

  1. tools=[]            -> the SDK passes `--tools ""`: no built-in tools are offered to the model
  2. disallowed_tools    -> explicit deny list as a backstop if (1) ever changes behaviour
  3. permission_mode     -> "dontAsk": anything not pre-approved is denied, never prompted
     + setting_sources=[] and strict_mcp_config -> no user/project settings, hooks, or MCP
       servers from this machine's Claude Code config leak into the assistant

(1)'s effect on the real binary is confirmed by the live check (see README); this module
only builds the configuration.
"""

from __future__ import annotations

from typing import Any

# Built-in Claude Code tools we never want the assistant to have.
BUILTIN_TOOLS: tuple[str, ...] = (
    "Bash",
    "BashOutput",
    "KillShell",
    "Read",
    "Write",
    "Edit",
    "MultiEdit",
    "NotebookEdit",
    "Glob",
    "Grep",
    "WebFetch",
    "WebSearch",
    "Agent",  # subagent tool (older docs call it "Task")
    "Task",
    "Skill",
    "AskUserQuestion",
    "TodoWrite",
    "TaskCreate",
    "TaskUpdate",
    "ToolSearch",
)


def mcp_tool_name(server_name: str, tool_name: str) -> str:
    """SDK naming convention for in-process MCP tools: mcp__<server>__<tool>."""
    return f"mcp__{server_name}__{tool_name}"


def lockdown_options(server_name: str, tool_names: list[str]) -> dict[str, Any]:
    """ClaudeAgentOptions keyword arguments that restrict the agent to `tool_names`."""
    return {
        "tools": [],
        "allowed_tools": [mcp_tool_name(server_name, n) for n in tool_names],
        "disallowed_tools": list(BUILTIN_TOOLS),
        "permission_mode": "dontAsk",
        "setting_sources": [],
        "strict_mcp_config": True,
    }
