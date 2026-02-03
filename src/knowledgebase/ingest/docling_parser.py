"""Document parsing with Docling for OpenClaw Knowledgebase."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

# Optional import
try:
    from docling.document_converter import DocumentConverter
    from docling.datamodel.base_models import InputFormat
    HAS_DOCLING = True
except ImportError:
    HAS_DOCLING = False


@dataclass
class ParsedDocument:
    """A parsed document."""
    path: str
    title: str | None
    content: str  # Markdown content
    format: str  # pdf, docx, etc.
    metadata: dict = field(default_factory=dict)


# Supported formats without Docling (plain text)
PLAIN_TEXT_FORMATS = {".txt", ".md", ".markdown", ".rst", ".json", ".yaml", ".yml"}

# Formats that need Docling
DOCLING_FORMATS = {".pdf", ".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls", ".html", ".htm"}


def check_docling() -> tuple[bool, str]:
    """Check if Docling is available."""
    if HAS_DOCLING:
        return True, "Docling available"
    return False, "Docling not installed. Install with: pip install docling"


def get_supported_formats() -> set[str]:
    """Get all supported file formats."""
    formats = set(PLAIN_TEXT_FORMATS)
    if HAS_DOCLING:
        formats.update(DOCLING_FORMATS)
    return formats


def parse_plain_text(path: Path) -> ParsedDocument:
    """Parse a plain text file."""
    content = path.read_text(encoding="utf-8", errors="ignore")
    
    # Try to extract title from first line (for markdown)
    title = None
    lines = content.split("\n")
    if lines and lines[0].startswith("# "):
        title = lines[0][2:].strip()
    
    return ParsedDocument(
        path=str(path),
        title=title or path.stem,
        content=content,
        format=path.suffix.lower().lstrip("."),
        metadata={
            "size_bytes": path.stat().st_size,
            "filename": path.name,
        },
    )


def parse_with_docling(path: Path) -> ParsedDocument | None:
    """Parse a document using Docling."""
    if not HAS_DOCLING:
        return None
    
    try:
        converter = DocumentConverter()
        result = converter.convert(str(path))
        
        # Export to markdown
        content = result.document.export_to_markdown()
        
        # Get metadata
        metadata = {
            "filename": path.name,
            "size_bytes": path.stat().st_size,
        }
        
        # Try to get title from document metadata
        title = None
        if hasattr(result.document, "title") and result.document.title:
            title = result.document.title
        
        return ParsedDocument(
            path=str(path),
            title=title or path.stem,
            content=content,
            format=path.suffix.lower().lstrip("."),
            metadata=metadata,
        )
        
    except Exception as e:
        return None


def parse_document(path: str | Path) -> ParsedDocument | None:
    """
    Parse a document file.
    
    Supports:
    - Plain text: .txt, .md, .rst, .json, .yaml
    - With Docling: .pdf, .docx, .pptx, .xlsx, .html
    
    Args:
        path: Path to document
        
    Returns:
        ParsedDocument or None on error
    """
    path = Path(path)
    
    if not path.exists():
        return None
    
    suffix = path.suffix.lower()
    
    # Plain text formats
    if suffix in PLAIN_TEXT_FORMATS:
        try:
            return parse_plain_text(path)
        except Exception:
            return None
    
    # Docling formats
    if suffix in DOCLING_FORMATS:
        if not HAS_DOCLING:
            return None
        return parse_with_docling(path)
    
    return None


def parse_directory(
    directory: str | Path,
    recursive: bool = True,
    extensions: set[str] | None = None,
) -> Iterator[ParsedDocument]:
    """
    Parse all documents in a directory.
    
    Args:
        directory: Directory path
        recursive: Search subdirectories
        extensions: File extensions to include (default: all supported)
        
    Yields:
        ParsedDocument objects
    """
    directory = Path(directory)
    
    if not directory.is_dir():
        return
    
    extensions = extensions or get_supported_formats()
    
    # Normalize extensions
    extensions = {ext.lower().lstrip(".") for ext in extensions}
    
    pattern = "**/*" if recursive else "*"
    
    for path in directory.glob(pattern):
        if path.is_file():
            suffix = path.suffix.lower().lstrip(".")
            if suffix in extensions:
                doc = parse_document(path)
                if doc:
                    yield doc


def estimate_parse_time(path: str | Path) -> float:
    """Estimate parsing time in seconds based on file size and type."""
    path = Path(path)
    if not path.exists():
        return 0
    
    size_mb = path.stat().st_size / (1024 * 1024)
    suffix = path.suffix.lower()
    
    # Base estimates (seconds per MB)
    if suffix in PLAIN_TEXT_FORMATS:
        return size_mb * 0.1  # Very fast
    elif suffix == ".pdf":
        return size_mb * 2.0  # PDFs take longer
    elif suffix in {".docx", ".doc"}:
        return size_mb * 1.0
    elif suffix in {".pptx", ".ppt"}:
        return size_mb * 1.5
    elif suffix in {".xlsx", ".xls"}:
        return size_mb * 1.0
    else:
        return size_mb * 0.5
