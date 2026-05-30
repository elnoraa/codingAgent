"""RAG (Retrieval-Augmented Generation) engine for the Coding Agent.

Provides semantic code search across the project codebase using pure-Python
TF-IDF with SQLite persistence. Zero additional dependencies beyond stdlib.
"""

from __future__ import annotations

import math
import os
import re
import sqlite3
import time
from dataclasses import dataclass
from typing import Any

# ── Configuration ──────────────────────────────────────────────────────────────


@dataclass
class RagConfig:
    """Configuration for the RAG index."""

    enabled: bool = True
    chunk_size: int = 200
    """Lines per chunk."""
    chunk_overlap: int = 20
    """Overlap between consecutive chunks (in lines)."""
    max_chunks: int = 5000
    """Safety limit — maximum number of chunks to keep in the index."""
    max_results: int = 10
    """Default number of results for a query."""
    min_score: float = 0.05
    """Minimum cosine-similarity score to include a result."""
    index_dir: str = ".rag_index"
    """Directory inside the project root where the SQLite DB is stored."""
    include_patterns: tuple[str, ...] = (
        "**/*.py",
        "**/*.js",
        "**/*.ts",
        "**/*.jsx",
        "**/*.tsx",
        "**/*.md",
        "**/*.txt",
        "**/*.json",
        "**/*.yaml",
        "**/*.yml",
        "**/*.toml",
        "**/*.cfg",
        "**/*.ini",
        "**/*.html",
        "**/*.css",
        "**/*.rs",
        "**/*.go",
        "**/*.java",
        "**/*.cpp",
        "**/*.c",
        "**/*.h",
        "**/*.rb",
        "**/*.php",
        "**/*.swift",
        "**/*.kt",
        "**/*.sql",
    )
    exclude_patterns: tuple[str, ...] = (
        "**/node_modules/**",
        "**/.git/**",
        "**/__pycache__/**",
        "**/.venv/**",
        "**/venv/**",
        "**/env/**",
        "**/dist/**",
        "**/build/**",
        "**/.tox/**",
        "**/*.min.js",
        "**/*.min.css",
        "**/*.pyc",
        "**/*.pyo",
        "**/sessions/**",
        "**/plans/**",
        "**/.rag_index/**",
    )


# ── Data types ─────────────────────────────────────────────────────────────────


@dataclass
class RagDocument:
    """A single indexed chunk from a file."""

    id: int | None = None
    filepath: str = ""
    content: str = ""
    start_line: int = 0
    end_line: int = 0
    language: str = ""
    doc_tokens: dict[str, float] | None = None
    """Pre-computed augmented TF vector (term → normalized frequency)."""


@dataclass
class QueryResult:
    """A single search result from a RAG query."""

    filepath: str
    start_line: int
    end_line: int
    content: str
    score: float
    language: str


# ── Language detection ─────────────────────────────────────────────────────────

_EXTENSION_LANG_MAP: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".md": "markdown",
    ".txt": "text",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".cfg": "config",
    ".ini": "ini",
    ".html": "html",
    ".css": "css",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".cpp": "cpp",
    ".c": "c",
    ".h": "c",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
    ".sql": "sql",
}


def _detect_language(filepath: str) -> str:
    """Detect programming language from file extension."""
    _, ext = os.path.splitext(filepath)
    return _EXTENSION_LANG_MAP.get(ext.lower(), "")


# ── Tokenisation ───────────────────────────────────────────────────────────────

_TOKEN_PATTERN = re.compile(r"[a-zA-Z_]\w{2,}")


def tokenize(text: str) -> list[str]:
    """Split text into lowercase alphanumeric terms (min 3 chars).

    Also splits on underscores to better align code identifiers
    with natural language queries. For example, ``database_connect``
    becomes ``['database', 'connect']``.
    """
    # First replace underscores with spaces to split compound identifiers
    text_with_spaces = text.replace("_", " ")
    return [m.group().lower() for m in _TOKEN_PATTERN.finditer(text_with_spaces)]


# ── TF-IDF helpers ─────────────────────────────────────────────────────────────


def compute_augmented_tf(terms: list[str]) -> dict[str, float]:
    """Compute augmented term frequency for a list of terms.

    TF(t,d) = 0.5 + 0.5 * (freq(t,d) / max_freq_in_doc)

    This smooths the raw count (``augmented frequency``) so that
    longer documents are not unfairly favoured.
    """
    if not terms:
        return {}

    counts: dict[str, int] = {}
    for t in terms:
        counts[t] = counts.get(t, 0) + 1

    max_freq = max(counts.values())
    if max_freq == 0:
        return {}

    return {t: 0.5 + 0.5 * (c / max_freq) for t, c in counts.items()}


def compute_idf(documents: list[RagDocument]) -> dict[str, float]:
    """Compute inverse document frequency across all documents.

    IDF(t) = log((N + 1) / (df(t) + 1)) + 1

    The ``+1`` smoothing prevents division-by-zero and ensures
    IDF is always >= 1.
    """
    n = len(documents)
    if n == 0:
        return {}

    doc_freq: dict[str, int] = {}
    for doc in documents:
        if doc.doc_tokens:
            for term in doc.doc_tokens:
                doc_freq[term] = doc_freq.get(term, 0) + 1

    return {term: math.log((n + 1) / (df + 1)) + 1 for term, df in doc_freq.items()}


def cosine_similarity(
    query_vec: dict[str, float],
    doc_vec: dict[str, float],
    idf: dict[str, float],
) -> float:
    """Compute cosine similarity between a query TF-IDF vector and a document vector.

    cos(q,d) = sum(q_i * d_i) / (sqrt(sum(q_i^2)) * sqrt(sum(d_i^2)))
    """
    if not query_vec or not doc_vec:
        return 0.0

    # Dot product (only overlapping terms contribute)
    dot = 0.0
    for term, qw in query_vec.items():
        dw = doc_vec.get(term, 0.0) * idf.get(term, 1.0)
        dot += qw * dw

    if dot == 0.0:
        return 0.0

    # Query norm
    q_norm = math.sqrt(sum(w * w for w in query_vec.values()))
    if q_norm == 0.0:
        return 0.0

    # Document norm (applying IDF weights)
    d_norm = 0.0
    for t, w in doc_vec.items():
        iw = idf.get(t, 1.0)
        d_norm += (w * iw) ** 2
    d_norm = math.sqrt(d_norm)

    if d_norm == 0.0:
        return 0.0

    return dot / (q_norm * d_norm)


# ── Chunking ───────────────────────────────────────────────────────────────────

# Patterns at which we prefer to split chunks
_SMART_SPLIT_PATTERNS = re.compile(
    r"^\s*(?:"
    r"(?:async\s+)?def\s+|"  # Python functions
    r"class\s+|"  # classes
    r"pub\s+(?:fn|struct|enum|trait|impl|mod|unsafe|async|const|static)\s+|"  # Rust
    r"fn\s+|"  # Rust/Go functions
    r"func\s+|"  # Go functions
    r"export\s+(?:function|class|const|let|var|default|async)\s+|"  # JS/TS exports
    r"function\s+|"  # JS functions
    r"impl\s+\w+\s+(?:for\s+|)"  # Rust impl blocks
    r"import\s+|"  # import statements
    r"from\s+\S+\s+import\s+|"  # Python imports
    r"def\s+|"  # Python def (catch-all)
    r"@\w+|"  # decorators
    r")",
    re.MULTILINE,
)


def chunk_file(
    abs_path: str,
    rel_path: str,
    *,
    chunk_size: int = 200,
    chunk_overlap: int = 20,
    max_file_bytes: int = 1_048_576,  # 1 MB
) -> list[RagDocument]:
    """Split a source file into semantically-aware chunks.

    Parameters
    ----------
    abs_path:
        Absolute path to the file on disk.
    rel_path:
        Relative (project-root) path for storage.
    chunk_size:
        Maximum lines per chunk.
    chunk_overlap:
        Overlap between consecutive chunks.
    max_file_bytes:
        Maximum file size to process. Larger files are skipped.

    Returns
    -------
    list[RagDocument]
        A list of chunks (empty if the file is binary, too large, or empty).
    """
    # Check file exists and is under size limit
    if not os.path.isfile(abs_path):
        return []

    try:
        size = os.path.getsize(abs_path)
        if size > max_file_bytes:
            return []
    except OSError:
        return []

    # Read file content
    try:
        with open(abs_path, encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError:
        return []

    if not content.strip():
        return []

    # Skip binary files (null byte detection)
    if "\x00" in content:
        return []

    lines = content.splitlines(keepends=True)
    total_lines = len(lines)
    language = _detect_language(rel_path)

    if total_lines == 0:
        return []

    if total_lines <= chunk_size:
        # Single chunk
        text = "".join(lines)
        return [
            RagDocument(
                filepath=rel_path,
                content=text,
                start_line=1,
                end_line=total_lines,
                language=language,
            )
        ]

    # Multiple chunks with smart split points
    chunks: list[RagDocument] = []
    start = 0

    while start < total_lines:
        end = min(start + chunk_size, total_lines)

        # Try to find a smart split point near the end of this chunk
        smart_end = _find_smart_split(lines, start, end)
        if smart_end is not None:
            end = smart_end

        # Extract chunk content
        chunk_lines = lines[start:end]
        text = "".join(chunk_lines)

        chunks.append(
            RagDocument(
                filepath=rel_path,
                content=text,
                start_line=start + 1,
                end_line=end,
                language=language,
            )
        )

        # Advance: move forward by (chunk_size - overlap)
        step = chunk_size - chunk_overlap
        if step <= 0:
            step = 1  # safeguard against infinite loop

        start += step

    return chunks


def _find_smart_split(lines: list[str], start: int, end_hint: int) -> int | None:
    """Try to find a good split point near the end of a chunk.

    Looks backward from ``end_hint`` for a line matching a smart split
    pattern (function/class definition, blank line, etc.).
    """
    # Search from end_hint backward to the middle of the chunk
    search_start = max(start, end_hint - 40)
    best = None

    for i in range(end_hint - 1, search_start - 1, -1):
        if i >= len(lines):
            continue
        line = lines[i]

        # Smart split pattern match
        if _SMART_SPLIT_PATTERNS.match(line):
            return i  # Take the first (closest to end) match

        # Blank line (good split point)
        if best is None and line.strip() == "":
            best = i + 1  # Split AFTER the blank line

    return best


# ── RagIndex ───────────────────────────────────────────────────────────────────


class RagIndex:
    """Main RAG index — build, query, and persist a TF-IDF search index.

    Usage::

        index = RagIndex(RagConfig(), working_directory)
        index.initialize()
        index.index_project()
        results = index.query("database connection error handling")
    """

    def __init__(
        self,
        config: RagConfig | None = None,
        working_directory: str | None = None,
    ) -> None:
        self.config = config or RagConfig()
        self.working_directory = working_directory or os.getcwd()
        self.documents: list[RagDocument] = []
        self.vocabulary: dict[str, int] = {}
        self.idf: dict[str, float] = {}
        self._db: sqlite3.Connection | None = None
        self._initialized = False
        self._last_indexed: float = 0.0

    # ── Initialization ─────────────────────────────────────────────────────

    def initialize(self) -> None:
        """Open/create the SQLite DB and load any existing index into memory."""
        if self._initialized:
            return
        db_dir = os.path.join(self.working_directory, self.config.index_dir)
        os.makedirs(db_dir, exist_ok=True)

        db_path = os.path.join(db_dir, "chunks.db")
        self._db = sqlite3.connect(db_path)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._create_tables()

        # Load existing documents
        self.documents = self._load_all_documents()

        if self.documents:
            self._build_index()
            self._last_indexed = self._get_last_indexed_time()

        self._initialized = True

    def close(self) -> None:
        """Close the SQLite database connection."""
        if self._db is not None:
            import contextlib

            with contextlib.suppress(Exception):
                self._db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            with contextlib.suppress(Exception):
                self._db.close()
            self._db = None

    def __del__(self) -> None:
        """Ensure the database connection is closed on garbage collection."""
        self.close()

    def _create_tables(self) -> None:
        """Create the chunks table if it does not exist."""
        if self._db is None:
            return
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS chunks (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                filepath    TEXT NOT NULL,
                content     TEXT NOT NULL,
                start_line  INTEGER NOT NULL,
                end_line    INTEGER NOT NULL,
                language    TEXT NOT NULL DEFAULT '',
                file_mtime  REAL NOT NULL,
                indexed_at  REAL NOT NULL
            )
            """
        )
        self._db.execute("CREATE INDEX IF NOT EXISTS idx_chunks_filepath ON chunks(filepath)")
        self._db.commit()

    def _load_all_documents(self) -> list[RagDocument]:
        """Load all chunk records from SQLite into memory."""
        if self._db is None:
            return []
        rows = self._db.execute(
            "SELECT id, filepath, content, start_line, end_line, language FROM chunks ORDER BY filepath, start_line"
        ).fetchall()
        return [
            RagDocument(
                id=row[0],
                filepath=row[1],
                content=row[2],
                start_line=row[3],
                end_line=row[4],
                language=row[5],
            )
            for row in rows
        ]

    def _get_last_indexed_time(self) -> float:
        """Get the most recent ``indexed_at`` timestamp from the DB."""
        if self._db is None:
            return 0.0
        row = self._db.execute("SELECT MAX(indexed_at) FROM chunks").fetchone()
        return row[0] if row and row[0] else 0.0

    # ── TF-IDF index building ─────────────────────────────────────────────

    def _build_index(self) -> None:
        """Build vocabulary and TF-IDF vectors for all loaded documents."""
        # Step 1: Tokenize and compute TF for each document
        for doc in self.documents:
            terms = tokenize(doc.content)
            doc.doc_tokens = compute_augmented_tf(terms)

        # Step 2: Build vocabulary from all terms
        self.vocabulary = {}
        for doc in self.documents:
            if doc.doc_tokens:
                for term in doc.doc_tokens:
                    if term not in self.vocabulary:
                        self.vocabulary[term] = len(self.vocabulary)

        # Step 3: Compute IDF across all documents
        self.idf = compute_idf(self.documents)

    # ── Indexing files ─────────────────────────────────────────────────────

    def index_file(self, rel_path: str) -> int:
        """Index a single file by its project-relative path.

        Returns the number of chunks added (0 if skipped).
        """
        abs_path = os.path.join(self.working_directory, rel_path)
        return self._index_abs_path(abs_path, rel_path)

    def _index_abs_path(self, abs_path: str, rel_path: str) -> int:
        """Index a single file by absolute path. Internal helper."""
        if not os.path.isfile(abs_path):
            return 0

        # Check mtime for incremental update
        try:
            mtime = os.path.getmtime(abs_path)
        except OSError:
            return 0

        if self._db is not None:
            existing = self._db.execute(
                "SELECT MAX(file_mtime) FROM chunks WHERE filepath = ?",
                (rel_path,),
            ).fetchone()
            if existing and existing[0] is not None and mtime <= existing[0]:
                return 0  # Already up-to-date

        # Chunk the file
        chunks = chunk_file(
            abs_path,
            rel_path,
            chunk_size=self.config.chunk_size,
            chunk_overlap=self.config.chunk_overlap,
        )
        if not chunks:
            return 0

        # Remove old chunks for this file
        if self._db is not None:
            self._db.execute("DELETE FROM chunks WHERE filepath = ?", (rel_path,))
            self._db.commit()

        # Enforce max_chunks limit
        self._enforce_max_chunks(len(chunks))

        # Insert new chunks into DB
        if self._db is not None:
            now = time.time()
            self._db.executemany(
                "INSERT INTO chunks (filepath, content, start_line, end_line, "
                "language, file_mtime, indexed_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        c.filepath,
                        c.content,
                        c.start_line,
                        c.end_line,
                        c.language,
                        mtime,
                        now,
                    )
                    for c in chunks
                ],
            )
            self._db.commit()

        # Reload and rebuild index
        self.documents = self._load_all_documents()
        self._build_index()
        self._last_indexed = time.time()

        return len(chunks)

    def _enforce_max_chunks(self, incoming: int) -> None:
        """Remove oldest chunks if adding new ones would exceed max_chunks."""
        if self._db is None:
            return
        current = self._db.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        if current + incoming > self.config.max_chunks:
            to_delete = (current + incoming) - self.config.max_chunks
            self._db.execute(
                "DELETE FROM chunks WHERE id IN (SELECT id FROM chunks ORDER BY indexed_at ASC LIMIT ?)",
                (to_delete,),
            )
            self._db.commit()

    # ── Project-wide indexing ──────────────────────────────────────────────

    def index_project(self, directory: str | None = None) -> dict[str, Any]:
        """Index all matching files in a directory tree.

        Returns a dict with indexing statistics.
        """
        root = directory or self.working_directory

        if not os.path.isdir(root):
            return {"error": f"Directory not found: {root}"}

        # We'll use a simple recursive walk instead of glob
        # to keep zero dependencies
        files_to_index: list[tuple[str, str]] = []
        for dirpath, _dirnames, filenames in os.walk(root):
            for fname in filenames:
                abs_path = os.path.join(dirpath, fname)
                rel_path = os.path.relpath(abs_path, self.working_directory)

                # Normalise path separators to forward slash
                rel_path = rel_path.replace("\\", "/")

                if self._is_excluded(rel_path):
                    continue
                if not self._is_included(rel_path):
                    continue

                files_to_index.append((abs_path, rel_path))

        total_chunks = 0
        indexed_files = 0
        skipped_files = 0

        for abs_path, rel_path in files_to_index:
            chunks_added = self._index_abs_path(abs_path, rel_path)
            if chunks_added > 0:
                total_chunks += chunks_added
                indexed_files += 1
            else:
                skipped_files += 1

        # Clean up stale chunks for files that no longer exist
        self._remove_stale_chunks()

        duration = time.time() - self._last_indexed if self._last_indexed else 0

        return {
            "indexed_files": indexed_files,
            "skipped_files": skipped_files,
            "total_chunks": total_chunks,
            "total_documents": len(self.documents),
            "duration_seconds": round(duration, 2),
        }

    def _is_included(self, rel_path: str) -> bool:
        """Check if a relative path matches at least one include pattern."""
        return any(self._glob_match(rel_path, pattern) for pattern in self.config.include_patterns)

    def _is_excluded(self, rel_path: str) -> bool:
        """Check if a relative path matches any exclude pattern."""
        return any(self._glob_match(rel_path, pattern) for pattern in self.config.exclude_patterns)

    @staticmethod
    def _glob_match(path: str, pattern: str) -> bool:
        """Simple glob matching supporting ``**``, ``*``, and ``?``.

        This is a minimal implementation that avoids a dependency on
        ``glob`` or ``fnmatch`` with full ``**`` support.
        """
        # Convert glob pattern to regex
        regex_parts: list[str] = []
        i = 0
        while i < len(pattern):
            c = pattern[i]
            if c == "*" and i + 1 < len(pattern) and pattern[i + 1] == "*":
                # ** matches everything
                if i + 2 < len(pattern) and pattern[i + 2] == "/":
                    regex_parts.append("(?:.+/)?")
                    i += 3
                else:
                    regex_parts.append(".*")
                    i += 2
            elif c == "*":
                regex_parts.append("[^/]*")
                i += 1
            elif c == "?":
                regex_parts.append("[^/]")
                i += 1
            elif c in ".^$+{}[]\\|()":
                regex_parts.append("\\" + c)
                i += 1
            else:
                regex_parts.append(c)
                i += 1

        # Anchor to full string match
        regex = "^" + "".join(regex_parts) + "$"
        return bool(re.search(regex, path))

    def _remove_stale_chunks(self) -> None:
        """Remove chunks for files that no longer exist on disk."""
        if self._db is None:
            return
        # Get all unique filepaths in the index
        rows = self._db.execute("SELECT DISTINCT filepath FROM chunks").fetchall()
        for (filepath,) in rows:
            abs_path = os.path.join(self.working_directory, filepath)
            if not os.path.isfile(abs_path):
                self._db.execute("DELETE FROM chunks WHERE filepath = ?", (filepath,))
        self._db.commit()

    # ── Querying ───────────────────────────────────────────────────────────

    def query(
        self,
        text: str,
        top_k: int | None = None,
        min_score: float | None = None,
        file_filter: str | None = None,
    ) -> list[QueryResult]:
        """Semantically search the index using natural language.

        Parameters
        ----------
        text:
            The natural language query.
        top_k:
            Maximum results to return (default: config.max_results).
        min_score:
            Minimum similarity threshold (default: config.min_score).
        file_filter:
            Optional glob pattern to filter results by file path.

        Returns
        -------
        list[QueryResult]
            Matches sorted by relevance (highest score first).
        """
        if not self._initialized:
            return self._not_initialized_response()

        if not self.documents:
            return []

        top_k = top_k or self.config.max_results
        min_score = min_score or self.config.min_score

        if not text.strip():
            return []

        # Tokenize query and compute TF vector
        query_terms = tokenize(text)
        query_tf = compute_augmented_tf(query_terms)

        # Compute query TF-IDF vector
        query_vec: dict[str, float] = {}
        for term, tf in query_tf.items():
            if term in self.idf:
                query_vec[term] = tf * self.idf[term]

        if not query_vec:
            return []

        # Build file filter regex
        filter_re: re.Pattern[str] | None = None
        if file_filter:
            filter_re = re.compile(self._glob_to_regex(file_filter), re.IGNORECASE)

        # Score all documents
        results: list[QueryResult] = []
        for doc in self.documents:
            if not doc.doc_tokens:
                continue

            # Apply file filter
            if filter_re and not filter_re.search(doc.filepath):
                continue

            score = cosine_similarity(query_vec, doc.doc_tokens, self.idf)
            if score >= min_score:
                results.append(
                    QueryResult(
                        filepath=doc.filepath,
                        start_line=doc.start_line,
                        end_line=doc.end_line,
                        content=doc.content[:500],
                        score=round(score, 4),
                        language=doc.language,
                    )
                )

        # Sort by score descending
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    @staticmethod
    def _glob_to_regex(pattern: str) -> str:
        """Convert a simple glob pattern to a regex string."""
        parts: list[str] = []
        i = 0
        while i < len(pattern):
            c = pattern[i]
            if c == "*" and i + 1 < len(pattern) and pattern[i + 1] == "*":
                if i + 2 < len(pattern) and pattern[i + 2] == "/":
                    parts.append("(?:.+/)?")
                    i += 3
                else:
                    parts.append(".*")
                    i += 2
            elif c == "*":
                parts.append("[^/]*")
                i += 1
            elif c == "?":
                parts.append("[^/]")
                i += 1
            elif c in ".^$+{}[]\\|()":
                parts.append("\\" + c)
                i += 1
            else:
                parts.append(c)
                i += 1
        return "^" + "".join(parts) + "$"

    def _not_initialized_response(self) -> list[QueryResult]:
        """Return an empty list — caller should check the status message."""
        return []

    # ── Status ─────────────────────────────────────────────────────────────

    def status(self) -> str:
        """Return a human-readable status string."""
        if not self._initialized:
            return "RAG index not initialized."

        if not self.documents:
            lines = [
                "RAG Index Status",
                "\u2500" * 40,
                "  Status:       Empty (no documents indexed)",
                "  Run /rag index or use the rag_index tool to build the index.",
            ]
            return "\n".join(lines)

        # Count unique files and languages
        unique_files = len(set(d.filepath for d in self.documents))
        languages = sorted(set(d.language for d in self.documents if d.language))

        last_time = ""
        if self._last_indexed:
            last_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self._last_indexed))

        config = self.config
        lines = [
            "RAG Index Status",
            "\u2500" * 40,
            "  Status:       Ready",
            f"  Chunks:       {len(self.documents):,}",
            f"  Files:        {unique_files:,}",
            f"  Languages:    {', '.join(languages) if languages else 'none'}",
            f"  Vocabulary:   {len(self.vocabulary):,} terms",
            f"  Last indexed: {last_time}",
            "",
            "  Config:",
            f"    Chunk size:   {config.chunk_size} lines",
            f"    Overlap:      {config.chunk_overlap} lines",
            f"    Max results:  {config.max_results}",
            f"    Max chunks:   {config.max_chunks:,}",
        ]
        return "\n".join(lines)

    # ── Clear ──────────────────────────────────────────────────────────────

    def clear(self) -> None:
        """Clear the entire index (both DB and memory)."""
        if self._db is not None:
            self._db.execute("DELETE FROM chunks")
            self._db.commit()
        self.documents.clear()
        self.vocabulary.clear()
        self.idf.clear()
        self._last_indexed = 0.0

    # ── Context manager support ────────────────────────────────────────────

    def __enter__(self) -> RagIndex:
        """Context manager entry."""
        if not self._initialized:
            self.initialize()
        return self

    def __exit__(self, *args: object) -> None:
        """Context manager exit — close the database connection."""
        self.close()


# ── Formatting helper for tools ────────────────────────────────────────────────


def format_query_results(results: list[QueryResult], query: str) -> str:
    """Format query results into a human-readable string."""
    if not results:
        return f'No relevant results found for "{query}".\nTry a different query, or use rag_index to index more files.'

    lines = [
        f'Found {len(results)} relevant result{"s" if len(results) != 1 else ""} for "{query}":',
        "",
    ]

    for i, r in enumerate(results, 1):
        lines.append(f"{i}. [{r.score:.2f}] {r.filepath} (lines {r.start_line}-{r.end_line})")
        lines.append(f"   Language: {r.language} | Score: {r.score}")
        lines.append("   ```" + r.language)
        # Add content, try to fit within reasonable display
        content = r.content
        if len(content) > 400:
            content = content[:400] + "\n   ..."
        lines.append(content)
        lines.append("   ```")
        lines.append("")

    return "\n".join(lines)
