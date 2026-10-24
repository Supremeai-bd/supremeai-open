import asyncio
from enum import StrEnum
from typing import Any

from pydantic import BaseModel


class MCPToolName(StrEnum):
    """Standard MCP tool names as per Master Plan specification"""

    BROWSER_NAVIGATE = "browser_navigate"
    BROWSER_CLICK = "browser_click"
    BROWSER_TYPE = "browser_type"
    BROWSER_SCREENSHOT = "browser_screenshot"
    BROWSER_FILE_UPLOAD = "browser_file_upload"
    BROWSER_SELECT_OPTION = "browser_select_option"
    BROWSER_GET_TEXT = "browser_get_text"
    BROWSER_WAIT_FOR = "browser_wait_for"
    BROWSER_EVALUATE = "browser_evaluate"


class MCPTool(BaseModel):
    """MCP Tool definition schema"""

    name: MCPToolName
    description: str
    parameters: dict[str, Any]  # JSON Schema compatible
    returns: str


# ✅ Complete MCP Tool Registry per Master Plan
MCP_BROWSER_TOOLS: list[MCPTool] = [
    MCPTool(
        name=MCPToolName.BROWSER_NAVIGATE,
        description="Navigate to a URL and wait for network idle",
        parameters={
            "url": {"type": "string", "description": "Target URL to navigate to"},
            "timeout": {
                "type": "number",
                "description": "Max wait time in ms (default: 30000)",
                "optional": True,
            },
            "wait_until": {
                "type": "string",
                "enum": ["load", "domcontentloaded", "networkidle"],
                "optional": True,
            },
        },
        returns="{'status': 'ok'|'error', 'url': 'string', 'title': 'string'}",
    ),
    MCPTool(
        name=MCPToolName.BROWSER_CLICK,
        description="Click on an element using CSS selector, text content, or coordinates",
        parameters={
            "target": {
                "type": "string",
                "description": "CSS selector, text content, or description",
            },
            "method": {
                "type": "string",
                "enum": ["selector", "text", "coordinate", "semantic"],
                "default": "selector",
            },
            "x": {
                "type": "number",
                "description": "X coordinate (if method=coordinate)",
                "optional": True,
            },
            "y": {
                "type": "number",
                "description": "Y coordinate (if method=coordinate)",
                "optional": True,
            },
        },
        returns="{'status': 'clicked'|'not_found', 'element': 'string'}",
    ),
    MCPTool(
        name=MCPToolName.BROWSER_TYPE,
        description="Type text into input field or textarea",
        parameters={
            "selector": {"type": "string", "description": "CSS selector for the input element"},
            "text": {"type": "string", "description": "Text to type"},
            "clear_first": {
                "type": "boolean",
                "description": "Clear existing text before typing",
                "default": True,
            },
            "delay_ms": {
                "type": "number",
                "description": "Typing delay between keystrokes (human-like)",
                "optional": True,
            },
        },
        returns="{'status': 'typed', 'selector': 'string'}",
    ),
    MCPTool(
        name=MCPToolName.BROWSER_SCREENSHOT,
        description="Capture screenshot of current page or element",
        parameters={
            "full_page": {
                "type": "boolean",
                "description": "Capture full scrolling page",
                "default": False,
            },
            "selector": {
                "type": "string",
                "description": "CSS selector for element screenshot",
                "optional": True,
            },
            "format": {"type": "string", "enum": ["png", "jpeg"], "default": "png"},
            "quality": {"type": "number", "description": "JPEG quality 0-100", "optional": True},
        },
        returns="{'status': 'ok', 'screenshot_base64': 'string', 'width': int, 'height': int}",
    ),
    MCPTool(
        name=MCPToolName.BROWSER_FILE_UPLOAD,
        description="Upload file through file input element",
        parameters={
            "selector": {"type": "string", "description": "CSS selector for file input"},
            "file_path": {"type": "string", "description": "Path to file on server"},
            "multiple": {
                "type": "boolean",
                "description": "Allow multiple files",
                "default": False,
            },
        },
        returns="{'status': 'uploaded', 'files': ['string']}",
    ),
]


async def execute_mcp_tool(tool_name: str, params: dict) -> dict:
    """
    Execute an MCP tool by routing to appropriate Playwright method.
    This is the main entry point for AI agents using MCP protocol.
    """
    from tools.browser.playwright_browser_agent import PlaywrightBrowserAgent

    agent = PlaywrightBrowserAgent()

    if tool_name == MCPToolName.BROWSER_NAVIGATE.value:
        return await agent.navigate(params["url"])

    elif tool_name == MCPToolName.BROWSER_CLICK.value:
        return await agent.click_target(params["target"], params.get("url"))

    elif tool_name == MCPToolName.BROWSER_TYPE.value:
        return await agent.type_text(params["selector"], params["text"], params.get("url"))

    elif tool_name == MCPToolName.BROWSER_SCREENSHOT.value:
        target_url = params.get("url", "about:blank")
        return await asyncio.to_thread(agent.screenshot, target_url)

    elif tool_name == MCPToolName.BROWSER_FILE_UPLOAD.value:
        # ✅ NEW: File upload implementation
        return await agent.upload_file(params["selector"], params["file_path"])

    else:
        raise ValueError(f"Unknown MCP tool: {tool_name}")
