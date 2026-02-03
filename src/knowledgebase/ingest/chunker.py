"""Text chunking utilities for OpenClaw Knowledgebase."""

import re
from dataclasses import dataclass
from typing import Iterator

from knowledgebase.config import get_config


@dataclass
class TextChunk:
    """A chunk of text with metadata."""
    content: str
    chunk_number: int
    start_char: int
    end_char: int
    metadata: dict | None = None


def chunk_text(
    text: str,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    separator: str = "\n\n",
) -> list[TextChunk]:
    """
    Split text into overlapping chunks.
    
    Args:
        text: Text to split
        chunk_size: Max characters per chunk (default from config)
        chunk_overlap: Overlap between chunks (default from config)
        separator: Preferred split point (paragraphs by default)
        
    Returns:
        List of TextChunk objects
    """
    config = get_config()
    chunk_size = chunk_size or config.chunk_size
    chunk_overlap = chunk_overlap or config.chunk_overlap
    
    if not text or not text.strip():
        return []
    
    # Clean up text
    text = text.strip()
    
    # If text is shorter than chunk_size, return as single chunk
    if len(text) <= chunk_size:
        return [TextChunk(
            content=text,
            chunk_number=0,
            start_char=0,
            end_char=len(text),
        )]
    
    chunks = []
    start = 0
    chunk_num = 0
    
    while start < len(text):
        # Calculate end position
        end = start + chunk_size
        
        # If we're not at the end, try to find a good break point
        if end < len(text):
            # Look for separator in the last part of the chunk
            search_start = max(start, end - chunk_overlap)
            search_text = text[search_start:end]
            
            # Try to find paragraph break
            last_sep = search_text.rfind(separator)
            if last_sep != -1:
                end = search_start + last_sep + len(separator)
            else:
                # Try sentence break
                for pattern in [". ", ".\n", "! ", "!\n", "? ", "?\n"]:
                    last_sep = search_text.rfind(pattern)
                    if last_sep != -1:
                        end = search_start + last_sep + len(pattern)
                        break
                else:
                    # Try word break
                    last_space = search_text.rfind(" ")
                    if last_space != -1:
                        end = search_start + last_space + 1
        else:
            end = len(text)
        
        # Extract chunk
        chunk_text_content = text[start:end].strip()
        
        if chunk_text_content:
            chunks.append(TextChunk(
                content=chunk_text_content,
                chunk_number=chunk_num,
                start_char=start,
                end_char=end,
            ))
            chunk_num += 1
        
        # Move start position with overlap
        start = end - chunk_overlap if end < len(text) else end
    
    return chunks


def chunk_markdown(
    markdown: str,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    preserve_headers: bool = True,
) -> list[TextChunk]:
    """
    Split markdown into chunks, respecting headers and structure.
    
    Args:
        markdown: Markdown text to split
        chunk_size: Max characters per chunk
        chunk_overlap: Overlap between chunks
        preserve_headers: Include parent headers in each chunk
        
    Returns:
        List of TextChunk objects with header metadata
    """
    config = get_config()
    chunk_size = chunk_size or config.chunk_size
    chunk_overlap = chunk_overlap or config.chunk_overlap
    
    if not markdown or not markdown.strip():
        return []
    
    # Split by headers
    header_pattern = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)
    
    sections = []
    current_headers = {}  # level -> header text
    last_end = 0
    
    for match in header_pattern.finditer(markdown):
        # Save content before this header
        if last_end < match.start():
            content = markdown[last_end:match.start()].strip()
            if content:
                sections.append({
                    "headers": dict(current_headers),
                    "content": content,
                    "start": last_end,
                })
        
        # Update headers
        level = len(match.group(1))
        header_text = match.group(2)
        
        # Clear lower-level headers
        for l in list(current_headers.keys()):
            if l >= level:
                del current_headers[l]
        
        current_headers[level] = header_text
        last_end = match.end()
    
    # Don't forget content after last header
    if last_end < len(markdown):
        content = markdown[last_end:].strip()
        if content:
            sections.append({
                "headers": dict(current_headers),
                "content": content,
                "start": last_end,
            })
    
    # Now chunk each section
    chunks = []
    chunk_num = 0
    
    for section in sections:
        # Build header prefix if preserving
        header_prefix = ""
        if preserve_headers and section["headers"]:
            header_lines = []
            for level in sorted(section["headers"].keys()):
                header_lines.append(f"{'#' * level} {section['headers'][level]}")
            header_prefix = "\n".join(header_lines) + "\n\n"
        
        content = section["content"]
        
        # Adjust chunk size for header prefix
        effective_chunk_size = chunk_size - len(header_prefix)
        
        if len(content) <= effective_chunk_size:
            # Single chunk for this section
            chunks.append(TextChunk(
                content=header_prefix + content if preserve_headers else content,
                chunk_number=chunk_num,
                start_char=section["start"],
                end_char=section["start"] + len(content),
                metadata={"headers": section["headers"]} if section["headers"] else None,
            ))
            chunk_num += 1
        else:
            # Split section into multiple chunks
            section_chunks = chunk_text(
                content,
                chunk_size=effective_chunk_size,
                chunk_overlap=chunk_overlap,
            )
            
            for sc in section_chunks:
                chunks.append(TextChunk(
                    content=header_prefix + sc.content if preserve_headers else sc.content,
                    chunk_number=chunk_num,
                    start_char=section["start"] + sc.start_char,
                    end_char=section["start"] + sc.end_char,
                    metadata={"headers": section["headers"]} if section["headers"] else None,
                ))
                chunk_num += 1
    
    return chunks


def estimate_chunks(text_length: int, chunk_size: int | None = None, chunk_overlap: int | None = None) -> int:
    """Estimate number of chunks for a given text length."""
    config = get_config()
    chunk_size = chunk_size or config.chunk_size
    chunk_overlap = chunk_overlap or config.chunk_overlap
    
    if text_length <= chunk_size:
        return 1
    
    effective_step = chunk_size - chunk_overlap
    return max(1, (text_length - chunk_overlap) // effective_step + 1)
