"""File extension to programming language mapping.

Maps file extensions (including the leading dot) to human-readable
language identifiers. Used by the scanner to classify discovered files.
"""

from __future__ import annotations

# Extension (lowercase, with dot) -> language name.
_EXTENSION_MAP: dict[str, str] = {
    # Python
    ".py": "Python",
    ".pyi": "Python",
    # Java
    ".java": "Java",
    # Scala
    ".scala": "Scala",
    # Kotlin
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    # C#
    ".cs": "C#",
    ".csx": "C#",
    # C++
    ".cpp": "C++",
    ".cxx": "C++",
    ".cc": "C++",
    ".hpp": "C++",
    ".hxx": "C++",
    ".h": "C++",
    # Rust
    ".rs": "Rust",
    # Go
    ".go": "Go",
    # JavaScript
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    # TypeScript
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".mts": "TypeScript",
    ".cts": "TypeScript",
    # YAML
    ".yaml": "YAML",
    ".yml": "YAML",
    # JSON
    ".json": "JSON",
    # TOML
    ".toml": "TOML",
    # Markdown
    ".md": "Markdown",
    ".markdown": "Markdown",
    ".mdx": "Markdown",
    # SQL
    ".sql": "SQL",
    # Shell
    ".sh": "Shell",
    ".bash": "Shell",
    ".zsh": "Shell",
    ".fish": "Shell",
    ".bashrc": "Shell",
    ".bash_profile": "Shell",
    ".zshrc": "Shell",
    # Dockerfile
    "dockerfile": "Dockerfile",
    ".dockerfile": "Dockerfile",
    ".Dockerfile": "Dockerfile",
    ".docker": "Dockerfile",
}


def detect_language(extension: str) -> str:
    """Detect a programming language from a file extension.

    The extension should include the leading dot and will be lowercased
    for lookup. Files with unrecognized extensions are classified as
    ``"Unknown"``.

    Args:
        extension: File extension (e.g. ``".py"`` or ``"py"``).

    Returns:
        A human-readable language name.
    """
    key = extension.lower().lstrip(".")
    # Direct lookup first (already has dot).
    if extension in _EXTENSION_MAP:
        return _EXTENSION_MAP[extension]
    # Try without the dot.
    if key in _EXTENSION_MAP:
        return _EXTENSION_MAP[key]
    return "Unknown"
