"""Document loading utilities for RAG system."""

import os
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

try:
    from PyPDF2 import PdfReader
except ImportError:
    PdfReader = None


class Document:
    """Represents a loaded document with content and metadata."""

    def __init__(
        self,
        content: str,
        metadata: Dict,
        source_path: Optional[str] = None
    ):
        self.content = content
        self.metadata = metadata
        self.source_path = source_path

    def __repr__(self):
        return f"Document(title={self.metadata.get('title', 'Unknown')}, chars={len(self.content)})"


class DocumentLoader:
    """Loads documents from various file formats."""

    SUPPORTED_EXTENSIONS = {'.pdf', '.txt', '.md', '.json'}

    def __init__(self):
        """Initialize the document loader."""
        if PdfReader is None:
            print("Warning: PyPDF2 not installed. PDF loading will be disabled.")

    def load_file(self, file_path: str) -> Optional[Document]:
        """Load a single file and return a Document object.

        Args:
            file_path: Path to the file to load.

        Returns:
            Document object or None if loading failed.
        """
        path = Path(file_path)

        if not path.exists():
            print(f"File not found: {file_path}")
            return None

        ext = path.suffix.lower()

        if ext not in self.SUPPORTED_EXTENSIONS:
            print(f"Unsupported file type: {ext}")
            return None

        try:
            if ext == '.pdf':
                return self._load_pdf(path)
            elif ext in {'.txt', '.md'}:
                return self._load_text(path)
            elif ext == '.json':
                return self._load_text(path)
        except Exception as e:
            print(f"Error loading {file_path}: {e}")
            return None

    def load_directory(
        self,
        directory_path: str,
        recursive: bool = True
    ) -> List[Document]:
        """Load all supported documents from a directory.

        Args:
            directory_path: Path to the directory.
            recursive: Whether to search subdirectories.

        Returns:
            List of Document objects.
        """
        documents = []
        path = Path(directory_path)

        if not path.exists():
            print(f"Directory not found: {directory_path}")
            return documents

        pattern = '**/*' if recursive else '*'

        for file_path in path.glob(pattern):
            if file_path.is_file() and file_path.suffix.lower() in self.SUPPORTED_EXTENSIONS:
                doc = self.load_file(str(file_path))
                if doc:
                    documents.append(doc)

        print(f"Loaded {len(documents)} documents from {directory_path}")
        return documents

    def _load_pdf(self, path: Path) -> Optional[Document]:
        """Load a PDF file.

        Args:
            path: Path to the PDF file.

        Returns:
            Document object or None.
        """
        if PdfReader is None:
            print("PyPDF2 not installed. Cannot load PDF files.")
            return None

        reader = PdfReader(str(path))

        # Extract text from all pages
        text_parts = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                text_parts.append(text)

        content = '\n\n'.join(text_parts)

        # Extract metadata
        metadata = {
            'title': path.stem,
            'source': str(path),
            'file_type': 'pdf',
            'page_count': len(reader.pages),
            'loaded_at': datetime.now().isoformat()
        }

        # Try to get PDF metadata
        if reader.metadata:
            if reader.metadata.title:
                metadata['title'] = reader.metadata.title
            if reader.metadata.author:
                metadata['author'] = reader.metadata.author

        return Document(content=content, metadata=metadata, source_path=str(path))

    def _load_text(self, path: Path) -> Optional[Document]:
        """Load a text or markdown file.

        Args:
            path: Path to the text file.

        Returns:
            Document object or None.
        """
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()

        metadata = {
            'title': path.stem,
            'source': str(path),
            'file_type': path.suffix.lower().strip('.'),
            'loaded_at': datetime.now().isoformat()
        }

        # Try to extract title from markdown
        if path.suffix.lower() == '.md':
            lines = content.split('\n')
            for line in lines:
                if line.startswith('# '):
                    metadata['title'] = line[2:].strip()
                    break

        return Document(content=content, metadata=metadata, source_path=str(path))


def create_document_from_text(
    content: str,
    title: str,
    source: str,
    doc_type: str = 'text',
    extra_metadata: Optional[Dict] = None
) -> Document:
    """Create a Document object from raw text.

    Args:
        content: The document content.
        title: Document title.
        source: Source URL or description.
        doc_type: Type of document (e.g., 'guideline', 'research', 'educational').
        extra_metadata: Additional metadata to include.

    Returns:
        Document object.
    """
    metadata = {
        'title': title,
        'source': source,
        'file_type': doc_type,
        'loaded_at': datetime.now().isoformat()
    }

    if extra_metadata:
        metadata.update(extra_metadata)

    return Document(content=content, metadata=metadata)
