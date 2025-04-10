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
async def list_files(directory: str = ".") -> str:
    """List files in the specified directory."""
    try:
        logger.info(f"Listing files in directory: {directory}")
        full_path = os.path.join(os.path.dirname(__file__), directory)
        if not os.path.exists(full_path):
            return f"Error: Directory {directory} does not exist"
            
        files = os.listdir(full_path)
        file_info = []
        
        for file in files:
            file_path = os.path.join(full_path, file)
            size = os.path.getsize(file_path)
            modified = datetime.fromtimestamp(os.path.getmtime(file_path))
            is_dir = os.path.isdir(file_path)
            
            file_info.append({
                "name": file,
                "type": "directory" if is_dir else "file",
                "size": size,
                "modified": modified.strftime("%Y-%m-%d %H:%M:%S")
            })
        
        return json.dumps(file_info, indent=2)
    except Exception as e:
        logger.error(f"Error listing files: {str(e)}")
        return f"Error listing files: {str(e)}\n{traceback.format_exc()}"

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