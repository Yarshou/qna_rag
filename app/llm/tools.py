"""OpenAI-compatible tool definitions for knowledge-base access.

This module owns the *schema* side of the tool contract — the JSON dicts
that are sent to the provider so it knows what functions are available and
how to call them.  The *execution* side lives in
:mod:`app.llm.tool_executor`.

Two tools are exposed:

* ``search_knowledge_base`` — lexical search returning ranked file references.
* ``read_knowledge_file`` — full-content read of a single file by stable ID.
"""

from typing import Any

from app.knowledge import MAX_KNOWLEDGE_FILES_IN_CONTEXT

# Type alias for a single OpenAI function-tool definition dict.
ToolDefinition = dict[str, Any]


def get_knowledge_base_tools() -> list[ToolDefinition]:
    """Return the stable tool definitions exposed to the chat model."""
    return [
        {
            "type": "function",
            "function": {
                "name": "search_knowledge_base",
                "description": "Search the knowledge base for the most relevant files before reading any full file.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query describing the information needed from the knowledge base.",
                        },
                        "limit": {
                            "type": "integer",
                            "description": (
                                "Maximum number of candidate files to return. Use a small value and never request more "
                                f"than {MAX_KNOWLEDGE_FILES_IN_CONTEXT} files for full reading."
                            ),
                            "minimum": 1,
                            "maximum": 10,
                        },
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_knowledge_file",
                "description": "Read one specific knowledge-base file that was selected from search results.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_id": {
                            "type": "string",
                            "description": "Stable identifier of the knowledge-base file to read.",
                        }
                    },
                    "required": ["file_id"],
                    "additionalProperties": False,
                },
            },
        },
    ]
