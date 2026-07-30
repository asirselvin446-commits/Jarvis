from core.tool_manager import tool
from core.memory import MemoryManager

# Helper to get memory manager
def _get_memory():
    return MemoryManager()

@tool(
    name="store_knowledge",
    description="Store a permanent fact or relationship in the knowledge graph. Use this to remember user preferences, relationships, or important facts (e.g. subject='User', predicate='likes', object='VS Code').",
    parameters={
        "type": "object",
        "properties": {
            "subject": {
                "type": "string",
                "description": "The subject of the fact (e.g. 'User', 'Jarvis', 'Project X')"
            },
            "predicate": {
                "type": "string",
                "description": "The relationship (e.g. 'likes', 'is working on', 'is located in')"
            },
            "object": {
                "type": "string",
                "description": "The object of the fact (e.g. 'Python', 'New Website', 'New York')"
            }
        },
        "required": ["subject", "predicate", "object"]
    }
)
def store_knowledge(subject: str, predicate: str, object: str) -> dict:
    try:
        mem = _get_memory()
        mem.add_triplet(subject, predicate, object)
        return {"result": f"Successfully stored knowledge: {subject} {predicate} {object}", "verified_success": True}
    except Exception as e:
        return {"result": f"Failed to store knowledge: {str(e)}", "verified_success": False}

@tool(
    name="query_knowledge",
    description="Query the knowledge graph for facts about a specific entity (e.g. 'User', 'Project X').",
    parameters={
        "type": "object",
        "properties": {
            "entity": {
                "type": "string",
                "description": "The entity to look up (e.g. 'User')"
            }
        },
        "required": ["entity"]
    }
)
def query_knowledge(entity: str) -> dict:
    try:
        mem = _get_memory()
        triplets = mem.get_triplets(entity)
        if not triplets:
            return {"result": f"No facts found for entity '{entity}'.", "verified_success": True}
        
        facts = [f"{t['subject']} {t['predicate']} {t['object']}" for t in triplets]
        return {"result": "Found facts:\n" + "\n".join(facts), "verified_success": True}
    except Exception as e:
        return {"result": f"Failed to query knowledge: {str(e)}", "verified_success": False}
