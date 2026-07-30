"""
J.A.R.V.I.S. Notion Integration Plugin
Create, read, and update Notion pages and databases.

Setup:
1. Create an integration at https://www.notion.so/my-integrations
2. Copy the Internal Integration Token
3. Set environment variable: JARVIS_NOTION_TOKEN=secret_xxx
4. Share your Notion pages/databases with the integration
"""

import os
import json
import requests
from core.tool_manager import tool

NOTION_TOKEN = os.environ.get("JARVIS_NOTION_TOKEN", "")
NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def _notion_headers() -> dict:
    return {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION
    }


def _check_token() -> str | None:
    if not NOTION_TOKEN:
        return ("Notion not configured. Set environment variable:\n"
                "  JARVIS_NOTION_TOKEN=secret_xxx\n"
                "Get your token from https://www.notion.so/my-integrations")
    return None


@tool(
    name="notion_search",
    description="Searches Notion for pages and databases matching a query.",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query to find in Notion."
            }
        },
        "required": ["query"]
    }
)
def notion_search(query: str) -> str:
    err = _check_token()
    if err:
        return err

    try:
        resp = requests.post(
            f"{NOTION_API}/search",
            headers=_notion_headers(),
            json={"query": query, "page_size": 10},
            timeout=15
        )
        if resp.status_code != 200:
            return f"Notion API error: {resp.status_code} {resp.text[:200]}"

        results = resp.json().get("results", [])
        if not results:
            return f"No Notion pages found matching '{query}'."

        lines = []
        for item in results:
            obj_type = item.get("object", "unknown")
            if obj_type == "page":
                title_parts = item.get("properties", {}).get("title", {}).get("title", [])
                if not title_parts:
                    # Try Name property
                    for prop_name, prop_data in item.get("properties", {}).items():
                        if prop_data.get("type") == "title":
                            title_parts = prop_data.get("title", [])
                            break
                title = "".join(t.get("plain_text", "") for t in title_parts) or "(Untitled)"
                url = item.get("url", "")
                lines.append(f"  📄 {title}\n     {url}")
            elif obj_type == "database":
                title_parts = item.get("title", [])
                title = "".join(t.get("plain_text", "") for t in title_parts) or "(Untitled DB)"
                lines.append(f"  📊 {title}")

        return f"Found {len(results)} result(s):\n" + "\n".join(lines)

    except Exception as e:
        return f"Notion search failed: {e}"


@tool(
    name="notion_create_page",
    description="Creates a new page in a Notion database or as a child of another page.",
    parameters={
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Title of the new page."
            },
            "content": {
                "type": "string",
                "description": "Text content for the page body.",
                "default": ""
            },
            "parent_page_id": {
                "type": "string",
                "description": "ID of the parent page (without dashes). Leave empty to search by title.",
                "default": ""
            }
        },
        "required": ["title"]
    }
)
def notion_create_page(title: str, content: str = "", parent_page_id: str = "") -> str:
    err = _check_token()
    if err:
        return err

    try:
        # If no parent specified, create as a top-level page
        if parent_page_id:
            parent = {"page_id": parent_page_id}
        else:
            # Search for a workspace page to use as parent
            resp = requests.post(
                f"{NOTION_API}/search",
                headers=_notion_headers(),
                json={"filter": {"property": "object", "value": "page"}, "page_size": 1},
                timeout=10
            )
            results = resp.json().get("results", [])
            if results:
                parent = {"page_id": results[0]["id"]}
            else:
                return "No parent page found. Share a page with your Notion integration first."

        # Build the page
        body = {
            "parent": parent,
            "properties": {
                "title": {
                    "title": [{"text": {"content": title}}]
                }
            }
        }

        # Add content blocks if provided
        if content:
            body["children"] = [
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": content}}]
                    }
                }
            ]

        resp = requests.post(
            f"{NOTION_API}/pages",
            headers=_notion_headers(),
            json=body,
            timeout=15
        )

        if resp.status_code == 200:
            page_url = resp.json().get("url", "")
            return f"Created Notion page: '{title}'. URL: {page_url}"
        else:
            return f"Failed to create page: {resp.status_code} {resp.text[:200]}"

    except Exception as e:
        return f"Notion page creation failed: {e}"


@tool(
    name="notion_read_page",
    description="Reads the content of a Notion page by searching for it by title.",
    parameters={
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Title of the page to read."
            }
        },
        "required": ["title"]
    }
)
def notion_read_page(title: str) -> str:
    err = _check_token()
    if err:
        return err

    try:
        # Search for the page
        resp = requests.post(
            f"{NOTION_API}/search",
            headers=_notion_headers(),
            json={"query": title, "page_size": 1},
            timeout=10
        )
        results = resp.json().get("results", [])
        if not results:
            return f"No Notion page found matching '{title}'."

        page_id = results[0]["id"]

        # Get page blocks (content)
        blocks_resp = requests.get(
            f"{NOTION_API}/blocks/{page_id}/children",
            headers=_notion_headers(),
            timeout=10
        )

        if blocks_resp.status_code != 200:
            return f"Failed to read page content: {blocks_resp.status_code}"

        blocks = blocks_resp.json().get("results", [])
        content_parts = []
        for block in blocks:
            block_type = block.get("type", "")
            if block_type in ("paragraph", "heading_1", "heading_2", "heading_3",
                              "bulleted_list_item", "numbered_list_item", "to_do"):
                rich_text = block.get(block_type, {}).get("rich_text", [])
                text = "".join(rt.get("plain_text", "") for rt in rich_text)
                if text:
                    content_parts.append(text)

        if not content_parts:
            return f"Page '{title}' exists but has no text content."

        return f"Content of '{title}':\n\n" + "\n".join(content_parts)

    except Exception as e:
        return f"Failed to read Notion page: {e}"
