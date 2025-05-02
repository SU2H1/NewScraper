import os
import json
import logging
import sys
import traceback
from typing import Any, Dict, List, Optional
import httpx
from datetime import datetime

# Set up logging
log_file = os.path.join(os.path.dirname(__file__), "mcp_server.log")
logging.basicConfig(
    filename=log_file,
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("mcp_server")

try:
    from mcp.server.fastmcp import FastMCP
    logger.info("Successfully imported MCP modules")
except ImportError as e:
    logger.error(f"Failed to import MCP modules: {str(e)}")
    sys.exit(1)

# Initialize FastMCP server
mcp = FastMCP("newscraper")
logger.info("Initialized FastMCP server")

# [All tool functions remain the same - I'm not showing them here to keep the response shorter]
@mcp.tool()
async def read_file(path: str, encoding: Optional[str] = None) -> str:
    """Read the contents of a file."""
    try:
        logger.info(f"Reading file: {path}")
        full_path = os.path.join(os.path.dirname(__file__), path)
        if not os.path.exists(full_path):
            return f"File not found: No file named \"{path}\""
        
        if os.path.isdir(full_path):
            return f"Cannot read directory: {path} is a directory"
            
        # Handle binary vs text mode based on encoding
        mode = "r" if encoding else "rb"
        kwargs = {"encoding": encoding} if encoding else {}
        
        with open(full_path, mode, **kwargs) as file:
            content = file.read()
            
        # For binary mode, return a base64 encoding
        if not encoding:
            import base64
            return base64.b64encode(content).decode('ascii')
            
        return content
    except Exception as e:
        logger.error(f"Error reading file: {str(e)}")
        return f"Error reading file: {str(e)}\n{traceback.format_exc()}"

# [Other tool functions remain the same]

# Run the server - IMPORTANT CHANGE HERE
if __name__ == "__main__":
    try:
        logger.info("Starting MCP server with transport=stdio")
        # Remove the print statement below:
        # print("MCP Server starting... (transport=stdio)")
        mcp.run(transport='stdio')
    except Exception as e:
        logger.critical(f"Fatal error in MCP server: {str(e)}")
        # We shouldn't print errors directly either, only log them
        logger.error(traceback.format_exc())
        sys.exit(1)