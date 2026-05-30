"""Tests for the RAG (Retrieval-Augmented Generation) module.

All tests use temporary directories — never write to the real project.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from src.rag import (
    RagConfig,
    RagDocument,
    RagIndex,
    chunk_file,
    compute_augmented_tf,
    compute_idf,
    cosine_similarity,
    format_query_results,
    tokenize,
)

# ── Tokenisation ────────────────────────────────────────────────────────────────


class TestTokenize:
    def test_simple_code(self) -> None:
        """Tokenize a simple code snippet.

        Underscores in identifiers are split so that ``hello_world``
        produces ``hello`` and ``world``, aligning with natural language queries.
        """
        tokens = tokenize("def hello_world():\n    return 42")
        assert "def" in tokens
        assert "hello" in tokens
        assert "world" in tokens
        assert "return" in tokens

    def test_empty_string(self) -> None:
        """Empty string returns empty list."""
        assert tokenize("") == []

    def test_short_terms_excluded(self) -> None:
        """Terms shorter than 3 characters are excluded."""
        tokens = tokenize("a an in of to")
        assert all(len(t) >= 3 for t in tokens)

    def test_lowercase_normalization(self) -> None:
        """All tokens are lowercase. Underscores are split."""
        tokens = tokenize("HelloWorld HTTP_API")
        assert "helloworld" in tokens
        assert "http" in tokens
        assert "api" in tokens

    def test_punctuation_filtered(self) -> None:
        """Punctuation is excluded from tokens."""
        tokens = tokenize("a == b and c != d")
        assert all(t.isalpha() or "_" in t for t in tokens)

    def test_natural_language(self) -> None:
        """Natural language text is tokenized correctly."""
        tokens = tokenize("Find the error handling code for database operations")
        assert "find" in tokens
        assert "error" in tokens
        assert "handling" in tokens
        assert "database" in tokens
        assert "operations" in tokens


# ── TF computation ──────────────────────────────────────────────────────────────


class TestComputeAugmentedTf:
    def test_empty_terms(self) -> None:
        """Empty terms returns empty dict."""
        assert compute_augmented_tf([]) == {}

    def test_single_term(self) -> None:
        """Single repeated term has TF = 1.0."""
        terms = ["hello", "hello", "hello"]
        tf = compute_augmented_tf(terms)
        assert tf == {"hello": 1.0}

    def test_multiple_terms(self) -> None:
        """Multiple terms with different frequencies."""
        terms = ["the", "the", "the", "code", "code", "function"]
        tf = compute_augmented_tf(terms)
        # "the" appears 3x, max_freq = 3
        assert tf["the"] == pytest.approx(1.0)  # 0.5 + 0.5 * (3/3)
        assert tf["code"] == pytest.approx(0.5 + 0.5 * (2 / 3))  # noqa: FURB100
        assert tf["function"] == pytest.approx(0.5 + 0.5 * (1 / 3))  # noqa: FURB100


# ── IDF computation ─────────────────────────────────────────────────────────────


class TestComputeIdf:
    def test_empty_documents(self) -> None:
        """Empty document list returns empty dict."""
        assert compute_idf([]) == {}

    def test_single_document(self) -> None:
        """Single document: all terms have IDF = log(2/2) + 1 = 1.0."""
        docs = [
            RagDocument(
                filepath="test.py",
                content="hello world",
                doc_tokens={"hello": 0.5, "world": 0.5},
            )
        ]
        idf = compute_idf(docs)
        assert idf["hello"] == pytest.approx(1.0)
        assert idf["world"] == pytest.approx(1.0)

    def test_multiple_documents(self) -> None:
        """Terms in all documents have lower IDF than rare terms."""
        docs = [
            RagDocument(filepath="a.py", content="common rare_a", doc_tokens={"common": 0.5, "rare_a": 0.5}),
            RagDocument(filepath="b.py", content="common rare_b", doc_tokens={"common": 0.5, "rare_b": 0.5}),
        ]
        idf = compute_idf(docs)
        # "common" appears in 2/2 docs: IDF = log(3/3) + 1 = 1.0
        # "rare_a" appears in 1/2 docs: IDF = log(3/2) + 1 > 1.0
        assert idf["common"] < idf["rare_a"]


# ── Cosine similarity ───────────────────────────────────────────────────────────


class TestCosineSimilarity:
    def test_identical_vectors(self) -> None:
        """Identical vectors have cosine similarity of 1.0."""
        qv = {"hello": 1.0, "world": 0.5}
        dv = {"hello": 1.0, "world": 0.5}
        score = cosine_similarity(qv, dv, idf={"hello": 1.0, "world": 1.0})
        assert score == pytest.approx(1.0, abs=0.001)

    def test_no_overlap(self) -> None:
        """Non-overlapping vectors have cosine similarity of 0.0."""
        qv = {"hello": 1.0}
        dv = {"world": 1.0}
        score = cosine_similarity(qv, dv, idf={"hello": 1.0, "world": 1.0})
        assert score == pytest.approx(0.0)

    def test_empty_query(self) -> None:
        """Empty query vector returns 0.0."""
        assert cosine_similarity({}, {"hello": 1.0}, {"hello": 1.0}) == 0.0

    def test_empty_doc(self) -> None:
        """Empty document vector returns 0.0."""
        assert cosine_similarity({"hello": 1.0}, {}, {"hello": 1.0}) == 0.0

    def test_partial_overlap(self) -> None:
        """Partial overlap gives score between 0 and 1."""
        qv = {"hello": 1.0, "world": 0.0}
        dv = {"hello": 1.0, "python": 0.5}
        score = cosine_similarity(qv, dv, idf={"hello": 1.0, "python": 1.0, "world": 1.0})
        assert 0 < score < 1.0

    def test_idf_weighting(self) -> None:
        """IDF weights affect the similarity score."""
        qv = {"common": 1.0, "rare": 1.0}
        dv = {"common": 1.0, "rare": 1.0}
        # IDF makes "rare" more important
        score = cosine_similarity(qv, dv, idf={"common": 1.0, "rare": 3.0})
        # The rare term contributes more to the score
        assert score > 0


# ── Chunking ────────────────────────────────────────────────────────────────────


class TestChunkFile:
    def test_small_file(self) -> None:
        """File smaller than chunk size produces 1 chunk."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test.py")
            with open(path, "w") as f:
                f.write("line1\nline2\nline3\n")

            chunks = chunk_file(path, "test.py", chunk_size=200)
            assert len(chunks) == 1
            assert chunks[0].start_line == 1
            assert chunks[0].end_line == 3
            assert chunks[0].language == "python"

    def test_large_file(self) -> None:
        """File larger than chunk size produces multiple chunks with overlap."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test.py")
            with open(path, "w") as f:
                for i in range(50):
                    f.write(f"line{i}\n")

            chunks = chunk_file(path, "test.py", chunk_size=10, chunk_overlap=2)
            assert len(chunks) >= 5  # 50 lines / (10-2) = ~7 chunks

    def test_empty_file(self) -> None:
        """Empty file produces no chunks."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "empty.py")
            with open(path, "w") as f:
                f.write("")
            chunks = chunk_file(path, "empty.py")
            assert len(chunks) == 0

    def test_whitespace_only(self) -> None:
        """Whitespace-only file produces no chunks."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "blank.py")
            with open(path, "w") as f:
                f.write("   \n  \n")
            chunks = chunk_file(path, "blank.py")
            assert len(chunks) == 0

    def test_binary_file(self) -> None:
        """Binary file (containing null bytes) is skipped."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "binary.bin")
            with open(path, "wb") as f:
                f.write(b"\x00\x01\x02hello")
            chunks = chunk_file(path, "binary.bin")
            assert len(chunks) == 0

    def test_nonexistent_file(self) -> None:
        """Non-existent file returns empty list."""
        chunks = chunk_file("/nonexistent/path.py", "path.py")
        assert len(chunks) == 0

    def test_language_detection(self) -> None:
        """Language is correctly detected from file extension."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test.rs")
            with open(path, "w") as f:
                f.write("fn main() {\n}\n")
            chunks = chunk_file(path, "test.rs")
            assert len(chunks) == 1
            assert chunks[0].language == "rust"

    def test_large_file_skipped(self) -> None:
        """File exceeding max_file_bytes is skipped."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "big.py")
            with open(path, "w") as f:
                f.write("x\n" * 100000)  # ~200KB
            chunks = chunk_file(path, "big.py", max_file_bytes=1024)
            assert len(chunks) == 0


# ── Query result formatting ────────────────────────────────────────────────────


class TestFormatQueryResults:
    def test_empty_results(self) -> None:
        """Empty results shows a helpful message."""

        result = format_query_results([], "test query")
        assert "No relevant results found" in result
        assert "test query" in result

    def test_single_result(self) -> None:
        """Single result is formatted correctly."""
        from src.rag import QueryResult

        results = [
            QueryResult(
                filepath="src/main.py",
                start_line=10,
                end_line=20,
                content="def hello():\n    pass\n",
                score=0.95,
                language="python",
            )
        ]
        output = format_query_results(results, "hello function")
        assert "src/main.py" in output
        assert "0.95" in output
        assert "10-20" in output


# ── Integration tests ───────────────────────────────────────────────────────────


class TestRagIndexIntegration:
    def _make_index(self, tmp: str, **kwargs: object) -> RagIndex:
        """Create and initialize a RagIndex in a temp directory."""
        config_kwargs: dict[str, object] = {"max_chunks": 1000}
        config_kwargs.update(kwargs)
        config = RagConfig(**config_kwargs)  # type: ignore[arg-type]
        index = RagIndex(config, tmp)
        index.initialize()
        return index

    def test_index_and_query(self) -> None:
        """Build an index, query it, and verify results."""
        with tempfile.TemporaryDirectory() as tmp:
            # Create a Python file
            os.makedirs(os.path.join(tmp, "src"))
            py_path = os.path.join(tmp, "src", "main.py")
            with open(py_path, "w") as f:
                f.write("""def connect_to_database(config):
    \"\"\"Connect to the database with error handling.\"\"\"
    try:
        conn = psycopg2.connect(**config)
        return conn
    except ConnectionError as exc:
        logger.error(f"Failed to connect: {exc}")
        raise
""")

            # Create a README
            md_path = os.path.join(tmp, "README.md")
            with open(md_path, "w") as f:
                f.write("# My Project\n\nThis is a database project.\n")

            # Build index
            index = self._make_index(tmp)
            result = index.index_project(tmp)

            assert result["indexed_files"] >= 1

            # Query for database-related code
            results = index.query("database connection error handling")
            assert len(results) > 0
            assert "src/main.py" in results[0].filepath

            index.close()

    def test_query_empty_index(self) -> None:
        """Query on empty index returns empty list."""
        with tempfile.TemporaryDirectory() as tmp:
            index = self._make_index(tmp)
            results = index.query("anything")
            assert len(results) == 0
            index.close()

    def test_query_no_match(self) -> None:
        """Query with no matching terms returns empty list."""
        with tempfile.TemporaryDirectory() as tmp:
            py_path = os.path.join(tmp, "test.py")
            with open(py_path, "w") as f:
                f.write("x = 42\n")
            index = self._make_index(tmp)
            index.index_file("test.py")
            # Query with completely different vocabulary
            results = index.query("zzzzzxxxxxyyyyy")
            assert len(results) == 0
            index.close()

    def test_file_filter(self) -> None:
        """File filter narrows results."""
        with tempfile.TemporaryDirectory() as tmp:
            # Two files with similar content
            with open(os.path.join(tmp, "a.py"), "w") as f:
                f.write("def database():\n    pass\n")
            with open(os.path.join(tmp, "b.js"), "w") as f:
                f.write("function database() {\n}\n")

            index = self._make_index(tmp)
            index.index_project(tmp)

            # Without filter, both match
            all_results = index.query("database")
            assert len(all_results) >= 2

            # With filter, only .py files match
            py_results = index.query("database", file_filter="**/*.py")
            assert len(py_results) >= 1
            assert all(r.filepath.endswith(".py") for r in py_results)
            index.close()

    def test_incremental_update(self) -> None:
        """Re-indexing detects changed files."""
        with tempfile.TemporaryDirectory() as tmp:
            py_path = os.path.join(tmp, "test.py")
            with open(py_path, "w") as f:
                f.write("def original():\n    pass\n")

            index = self._make_index(tmp)
            first = index.index_project(tmp)
            assert first["indexed_files"] >= 1

            # Re-index without changes — should be skipped
            second = index.index_project(tmp)
            assert second["indexed_files"] < first["indexed_files"]

            # Modify the file
            with open(py_path, "a") as f:
                f.write("\ndef new_function():\n    return 42\n")

            # Re-index — should pick up the change
            index.index_project(tmp)
            # Now the new content should be searchable
            results = index.query("new_function")
            assert len(results) >= 1
            index.close()

    def test_clear_index(self) -> None:
        """Clearing the index removes all data."""
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "test.py"), "w") as f:
                f.write("x = 1\n")
            index = self._make_index(tmp)
            index.index_project(tmp)
            assert len(index.documents) > 0
            index.clear()
            assert len(index.documents) == 0
            index.close()

    def test_persistence(self) -> None:
        """Index survives reload from disk."""
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "test.py"), "w") as f:
                f.write("def persist_me():\n    pass\n")

            # Build and save
            index1 = self._make_index(tmp)
            index1.index_project(tmp)
            results1 = index1.query("persist_me")
            assert len(results1) > 0
            index1.close()

            # Create a new index (simulating restart)
            index2 = self._make_index(tmp)
            results2 = index2.query("persist_me")
            assert len(results2) > 0
            assert results2[0].filepath == "test.py"
            index2.close()

    def test_status(self) -> None:
        """Status output contains expected fields."""
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "test.py"), "w") as f:
                f.write("x = 1\n")
            index = self._make_index(tmp)
            status = index.status()
            assert "Empty" in status  # No documents yet

            index.index_project(tmp)
            status = index.status()
            assert "Ready" in status
            assert "Chunks:" in status
            index.close()

    def test_max_chunks_enforced(self) -> None:
        """Max chunks limit is enforced."""
        with tempfile.TemporaryDirectory() as tmp:
            # Create many files
            for i in range(10):
                with open(os.path.join(tmp, f"file{i}.py"), "w") as f:
                    for j in range(50):
                        f.write(f"def func_{j}():\n    pass\n\n")

            index = self._make_index(tmp, max_chunks=5)
            index.index_project(tmp)
            assert len(index.documents) <= 5
            index.close()


# ── Tool integration tests ─────────────────────────────────────────────────────


class TestRagTools:
    def test_rag_index_tool(self) -> None:
        """Execute rag_index tool via ToolContext."""
        from src.tool_base import ToolContext
        from src.tools.rag_index import rag_index_tool

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            with open(os.path.join(tmp, "test.py"), "w") as f:
                f.write("def hello():\n    pass\n")

            ctx = ToolContext(working_directory=tmp)
            result = rag_index_tool.execute(
                {"mode": "project"},
                ctx,
            )
            assert "Indexing complete" in result
            assert ctx.rag_index is not None

    def test_rag_query_tool(self) -> None:
        """Execute rag_query tool via ToolContext."""
        from src.tool_base import ToolContext
        from src.tools.rag_index import rag_index_tool
        from src.tools.rag_query import rag_query_tool

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            with open(os.path.join(tmp, "test.py"), "w") as f:
                f.write("def database_connect():\n    pass\n")

            ctx = ToolContext(working_directory=tmp)
            rag_index_tool.execute({"mode": "project"}, ctx)

            result = rag_query_tool.execute(
                {"query": "database connect"},
                ctx,
            )
            assert "test.py" in result

    def test_rag_status_tool(self) -> None:
        """Execute rag_status tool via ToolContext."""
        from src.tool_base import ToolContext
        from src.tools.rag_index import rag_index_tool
        from src.tools.rag_status import rag_status_tool

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            with open(os.path.join(tmp, "test.py"), "w") as f:
                f.write("x = 1\n")

            ctx = ToolContext(working_directory=tmp)
            rag_index_tool.execute({"mode": "project"}, ctx)

            result = rag_status_tool.execute({}, ctx)
            assert "Ready" in result
            assert "Chunks:" in result

    def test_rag_query_tool_no_index(self) -> None:
        """rag_query returns helpful message when no index exists."""
        from src.tool_base import ToolContext
        from src.tools.rag_query import rag_query_tool

        with tempfile.TemporaryDirectory() as tmp:
            ctx = ToolContext(working_directory=tmp)
            result = rag_query_tool.execute(
                {"query": "something"},
                ctx,
            )
            assert "RAG index is not available" in result or "empty" in result

    def test_rag_index_tool_clear(self) -> None:
        """rag_index with clear=True clears the index."""
        from src.tool_base import ToolContext
        from src.tools.rag_index import rag_index_tool
        from src.tools.rag_status import rag_status_tool

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            with open(os.path.join(tmp, "test.py"), "w") as f:
                f.write("x = 1\n")

            ctx = ToolContext(working_directory=tmp)
            rag_index_tool.execute({"mode": "project"}, ctx)

            # Clear
            rag_index_tool.execute({"clear": True}, ctx)

            result = rag_status_tool.execute({}, ctx)
            assert "Empty" in result or "No documents" in result
