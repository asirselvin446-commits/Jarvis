from core.tool_manager import tool
from core.memory import get_memory_manager

# Helper to get the shared, process-wide memory manager.
# (Previously constructed a fresh MemoryManager() on every tool call, opening
# a new SQLite connection + ChromaDB client each time.)
def _get_memory():
    return get_memory_manager()

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

@tool(
    name="remember_fact",
    description="Saves a key fact, learning, or preference to Jarvis's long-term semantic vector memory.",
    parameters={
        "type": "object",
        "properties": {
            "fact": {
                "type": "string",
                "description": "The piece of information to remember (e.g. 'The user likes their coffee black')."
            }
        },
        "required": ["fact"]
    }
)
def remember_fact(fact: str) -> dict:
    try:
        mem = _get_memory()
        mem.add_learning(fact)
        return {"result": f"Committed to semantic memory: '{fact}'", "verified_success": True}
    except Exception as e:
        return {"result": f"Failed to remember fact: {e}", "verified_success": False}

@tool(
    name="recall_fact",
    description="Queries Jarvis's long-term semantic vector memory to retrieve previously learned facts.",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The question or topic you want to remember (e.g. 'How does the user like their coffee?')."
            }
        },
        "required": ["query"]
    }
)
def recall_fact(query: str) -> dict:
    try:
        mem = _get_memory()
        results = mem.retrieve_relevant_learnings(query, n_results=3)
        if not results:
            return {"result": "No relevant memories found.", "verified_success": True}
        return {"result": "Found these semantic memories:\n" + "\n".join(f"- {r}" for r in results), "verified_success": True}
    except Exception as e:
        return {"result": f"Failed to recall fact: {e}", "verified_success": False}


# ─── Local RAG Tools ──────────────────────────────────────────────

_rag_indexer = None

def _get_rag():
    global _rag_indexer
    if _rag_indexer is None:
        from core.rag_indexer import RAGIndexer
        _rag_indexer = RAGIndexer(_get_memory())
    return _rag_indexer


@tool(
    name="index_directory",
    description="Indexes all supported files in a directory into Jarvis's local document memory for future semantic search. Use this before searching documents.",
    parameters={
        "type": "object",
        "properties": {
            "directory_path": {
                "type": "string",
                "description": "Absolute path to the directory to index (e.g. 'C:\\Users\\asus\\Documents')."
            },
            "recursive": {
                "type": "boolean",
                "description": "Whether to index subdirectories recursively. Defaults to true."
            }
        },
        "required": ["directory_path"]
    }
)
def index_directory(directory_path: str, recursive: bool = True) -> dict:
    try:
        rag = _get_rag()
        stats = rag.index_directory(directory_path, recursive=recursive)
        if "error" in stats:
            return {"result": stats["error"], "verified_success": False}
        return {
            "result": f"Indexing complete. Indexed {stats['indexed']} files, skipped {stats['skipped']}, errors {stats['errors']}.",
            "verified_success": True
        }
    except Exception as e:
        return {"result": f"Failed to index directory: {e}", "verified_success": False}


@tool(
    name="search_local_documents",
    description="Semantically searches Jarvis's indexed local documents for relevant information. Index a directory first before searching.",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The natural language question or topic to search for."
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results to return. Defaults to 5."
            }
        },
        "required": ["query"]
    }
)
def search_local_documents(query: str, max_results: int = 5) -> dict:
    try:
        rag = _get_rag()
        hits = rag.search(query, n_results=max_results)
        if not hits:
            return {"result": "No relevant documents found. Try indexing a directory first.", "verified_success": True}

        lines = []
        for i, hit in enumerate(hits, 1):
            lines.append(f"[{i}] Source: {hit['source']} (score: {hit['score']})")
            lines.append(f"    {hit['text'][:300]}...")
            lines.append("")

        return {"result": "Found relevant documents:\n" + "\n".join(lines), "verified_success": True}
    except Exception as e:
        return {"result": f"Failed to search documents: {e}", "verified_success": False}
