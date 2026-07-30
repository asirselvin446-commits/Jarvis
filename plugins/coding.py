"""
J.A.R.V.I.S. Coding & Software Development Plugin
Provides code inspection, file writing, Python execution, Git tools,
code search, VS Code integration, and LLM-powered code review.
"""

import os
import subprocess
from core.tool_manager import tool
from core.llm_provider import llm_chat


@tool(
    name="read_code_file",
    description="Reads the contents of a local code or text file.",
    parameters={
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Absolute or relative path to the file."
            }
        },
        "required": ["file_path"]
    }
)
def read_code_file(file_path: str) -> str:
    try:
        if not os.path.exists(file_path):
            return f"File '{file_path}' does not exist."
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        return content[:4000] if len(content) > 4000 else content
    except Exception as e:
        return f"Failed to read file: {e}"

@tool(
    name="write_code_file",
    description="Creates or overwrites a local file with the specified content.",
    parameters={
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Target file path."
            },
            "content": {
                "type": "string",
                "description": "The exact content/code to write into the file."
            }
        },
        "required": ["file_path", "content"]
    }
)
def write_code_file(file_path: str, content: str) -> str:
    try:
        dir_name = os.path.dirname(file_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully written to '{file_path}'."
    except Exception as e:
        return f"Failed to write file: {e}"

@tool(
    name="execute_python_script",
    description="Executes a inline Python script or python file in a safe subprocess.",
    parameters={
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Python code block or file path to run."
            }
        },
        "required": ["code"]
    }
)
def execute_python_script(code: str) -> str:
    try:
        if os.path.exists(code) and code.endswith(".py"):
            cmd = ["python", code]
        else:
            cmd = ["python", "-c", code]
        
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        output = res.stdout.strip() or res.stderr.strip() or "Script executed with no output."
        return output[:2000]
    except Exception as e:
        return f"Python execution error: {e}"


# ─── Code Search ─────────────────────────────────────────────────

@tool(
    name="search_code",
    description="Recursively searches for a text pattern in files within a directory. Like grep -r.",
    parameters={
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "The text or regex pattern to search for."
            },
            "directory": {
                "type": "string",
                "description": "Directory to search in (defaults to current directory).",
                "default": "."
            },
            "file_extension": {
                "type": "string",
                "description": "Optional file extension filter (e.g., '.py', '.js').",
                "default": ""
            }
        },
        "required": ["pattern"]
    }
)
def search_code(pattern: str, directory: str = ".", file_extension: str = "") -> str:
    try:
        matches = []
        max_results = 30  # Limit results to avoid flooding

        for root, _, files in os.walk(directory):
            # Skip hidden dirs, __pycache__, node_modules, .git
            if any(skip in root for skip in ["__pycache__", "node_modules", ".git", ".venv", "venv"]):
                continue
            for fname in files:
                if file_extension and not fname.endswith(file_extension):
                    continue
                filepath = os.path.join(root, fname)
                try:
                    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                        for i, line in enumerate(f, 1):
                            if pattern.lower() in line.lower():
                                matches.append(f"{filepath}:{i}: {line.rstrip()}")
                                if len(matches) >= max_results:
                                    break
                except Exception:
                    continue
                if len(matches) >= max_results:
                    break
            if len(matches) >= max_results:
                break

        if not matches:
            return f"No matches found for '{pattern}' in {directory}."

        result = f"Found {len(matches)} match(es):\n" + "\n".join(matches)
        return result[:3000]
    except Exception as e:
        return f"Search failed: {e}"


# ─── Git Tools ───────────────────────────────────────────────────

@tool(
    name="git_status",
    description="Checks the git repository status in a project directory.",
    parameters={
        "type": "object",
        "properties": {
            "project_dir": {
                "type": "string",
                "description": "Directory path of the git repository.",
                "default": "."
            }
        }
    }
)
def git_status(project_dir: str = ".") -> str:
    try:
        res = subprocess.run(
            ["git", "status"],
            cwd=project_dir, capture_output=True, text=True, timeout=10
        )
        return res.stdout.strip() or res.stderr.strip() or "Git status clean."
    except Exception as e:
        return f"Failed to check git status: {e}"


@tool(
    name="git_commit",
    description="Stages all changes and commits with the given message.",
    parameters={
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": "The commit message."
            },
            "project_dir": {
                "type": "string",
                "description": "Directory path of the git repository.",
                "default": "."
            }
        },
        "required": ["message"]
    }
)
def git_commit(message: str, project_dir: str = ".") -> str:
    try:
        # Stage all changes
        add_res = subprocess.run(
            ["git", "add", "-A"],
            cwd=project_dir, capture_output=True, text=True, timeout=10
        )
        if add_res.returncode != 0:
            return f"Git add failed: {add_res.stderr.strip()}"

        # Commit
        commit_res = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=project_dir, capture_output=True, text=True, timeout=10
        )
        output = commit_res.stdout.strip() or commit_res.stderr.strip()
        if commit_res.returncode != 0:
            return f"Git commit failed: {output}"
        return f"Committed: {output}"
    except Exception as e:
        return f"Git commit error: {e}"


@tool(
    name="git_diff",
    description="Shows the current unstaged or staged changes in a git repository.",
    parameters={
        "type": "object",
        "properties": {
            "staged": {
                "type": "boolean",
                "description": "If true, show staged changes (--cached). If false, show unstaged changes.",
                "default": False
            },
            "project_dir": {
                "type": "string",
                "description": "Directory path of the git repository.",
                "default": "."
            }
        }
    }
)
def git_diff(staged: bool = False, project_dir: str = ".") -> str:
    try:
        cmd = ["git", "diff"]
        if staged:
            cmd.append("--cached")

        res = subprocess.run(
            cmd, cwd=project_dir, capture_output=True, text=True, timeout=10
        )
        output = res.stdout.strip()
        if not output:
            return "No changes detected." if not staged else "No staged changes."
        return output[:3000]
    except Exception as e:
        return f"Git diff error: {e}"


# ─── Directory Listing ───────────────────────────────────────────

@tool(
    name="list_directory",
    description="Lists files and folders in a directory. Shows a tree-like structure.",
    parameters={
        "type": "object",
        "properties": {
            "directory": {
                "type": "string",
                "description": "Directory path to list.",
                "default": "."
            },
            "max_depth": {
                "type": "integer",
                "description": "Maximum depth to recurse into subdirectories.",
                "default": 2
            }
        }
    }
)
def list_directory(directory: str = ".", max_depth: int = 2) -> str:
    try:
        if not os.path.isdir(directory):
            return f"'{directory}' is not a valid directory."

        lines = []
        skip_dirs = {"__pycache__", "node_modules", ".git", ".venv", "venv", ".tox", "dist", "build"}

        def _walk(path, prefix, depth):
            if depth > max_depth:
                return
            try:
                entries = sorted(os.listdir(path))
            except PermissionError:
                return

            dirs = [e for e in entries if os.path.isdir(os.path.join(path, e)) and e not in skip_dirs]
            files = [e for e in entries if os.path.isfile(os.path.join(path, e))]

            for f in files:
                lines.append(f"{prefix}{f}")
            for d in dirs:
                lines.append(f"{prefix}{d}/")
                _walk(os.path.join(path, d), prefix + "  ", depth + 1)

        lines.append(f"{os.path.basename(os.path.abspath(directory))}/")
        _walk(directory, "  ", 1)
        result = "\n".join(lines[:200])  # Limit output
        return result if result else "Directory is empty."
    except Exception as e:
        return f"Failed to list directory: {e}"


# ─── VS Code Integration ────────────────────────────────────────

@tool(
    name="open_in_vscode",
    description="Opens a file in VS Code, optionally at a specific line number.",
    parameters={
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to the file to open."
            },
            "line": {
                "type": "integer",
                "description": "Optional line number to jump to.",
                "default": 1
            }
        },
        "required": ["file_path"]
    }
)
def open_in_vscode(file_path: str, line: int = 1) -> str:
    try:
        abs_path = os.path.abspath(file_path)
        if not os.path.exists(abs_path):
            return f"File '{file_path}' does not exist."

        subprocess.Popen(["code", "--goto", f"{abs_path}:{line}"], shell=True)
        return f"Opened '{os.path.basename(file_path)}' in VS Code at line {line}."
    except Exception as e:
        return f"Failed to open in VS Code: {e}"


# ─── LLM Code Review ────────────────────────────────────────────

@tool(
    name="code_review",
    description="Sends a code file to the local LLM for review. Returns improvement suggestions, bugs, and best practice recommendations.",
    parameters={
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to the code file to review."
            }
        },
        "required": ["file_path"]
    }
)
def code_review(file_path: str) -> str:
    try:
        if not os.path.exists(file_path):
            return f"File '{file_path}' does not exist."

        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            code_content = f.read()

        if len(code_content) > 6000:
            code_content = code_content[:6000] + "\n... (truncated)"

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a senior software engineer doing a code review. "
                    "Be concise. List the top 3-5 issues or improvements. "
                    "Focus on: bugs, security, performance, readability. "
                    "Format as a numbered list."
                )
            },
            {
                "role": "user",
                "content": f"Review this code:\n\n```\n{code_content}\n```"
            }
        ]

        result = llm_chat(messages, temperature=0.2, timeout=120)
        review = result.get("content", "No review generated.")
        return review[:3000]
    except Exception as e:
        return f"Code review error: {e}"

