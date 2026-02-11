"""
Tools registry for SSH MCP Server - manages registration of all MCP tools.

Uses auto-discovery to find and register all tool modules.
Tool modules follow the tools_*.py naming convention with a
register_*_tools(mcp, pool) function.
"""

import importlib
import logging
import pkgutil
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ToolsRegistry:
    """Manages registration of all MCP tools.

    Discovers tools_*.py modules and calls their register_*_tools() function.
    """

    def __init__(self, server: Any) -> None:
        self.server = server
        self.mcp = server.mcp
        self.pool = server.pool
        self._modules_registered = False
        self._discovered_modules = self._discover_tool_modules()

    def _discover_tool_modules(self) -> list[str]:
        """Discover tool module names without importing them."""
        discovered = []
        package_path = Path(__file__).parent

        for module_info in pkgutil.iter_modules([str(package_path)]):
            module_name = module_info.name
            if module_name.startswith("tools_"):
                discovered.append(module_name)

        logger.debug(f"Discovered {len(discovered)} tool modules")
        return discovered

    def register_all_tools(self) -> None:
        """Register all tools with the MCP server."""
        if self._modules_registered:
            logger.debug("Tools already registered, skipping")
            return

        registered_count = 0

        for module_name in self._discovered_modules:
            try:
                module = importlib.import_module(f".{module_name}", "ssh_mcp.tools")

                # Find the register function (convention: register_*_tools)
                register_func = None
                for attr_name in dir(module):
                    if attr_name.startswith("register_") and attr_name.endswith(
                        "_tools"
                    ):
                        register_func = getattr(module, attr_name)
                        break

                if register_func:
                    register_func(self.mcp, self.pool)
                    registered_count += 1
                    logger.debug(f"Registered tools from {module_name}")
                else:
                    logger.warning(
                        f"Module {module_name} has no register_*_tools function"
                    )

            except Exception as e:
                logger.error(f"Failed to register tools from {module_name}: {e}")
                raise

        self._modules_registered = True
        logger.info(f"Auto-discovery registered tools from {registered_count} modules")
