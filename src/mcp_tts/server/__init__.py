"""
MCP Server package for Text-to-Speech.

Exposes TTS functionality as MCP tools and resources that can be
used by LLMs via the Model Context Protocol.
"""

from mcp.server import FastMCP

# Create MCP server instance (shared across tools and resources)
mcp = FastMCP(name="MCP TTS Server")

# Import tool and resource registrations so @mcp.tool() decorators execute
from mcp_tts.server import tools as _tools  # noqa: F401, E402
from mcp_tts.server import resources as _resources  # noqa: F401, E402


def run_server() -> None:
    """Lazy wrapper — avoids importing lifecycle at package-init time.

    When ``python -m mcp_tts.server.lifecycle`` is used, ``runpy`` first
    imports this package.  If we eagerly import ``lifecycle`` here it
    ends up in ``sys.modules`` before ``runpy`` can execute it, which
    triggers a ``RuntimeWarning``.
    """
    from mcp_tts.server.lifecycle import run_server as _run  # noqa: E402

    _run()


__all__ = ["mcp", "run_server"]
