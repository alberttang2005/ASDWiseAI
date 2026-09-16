"""RAG Engine using ChromaDB for clinical evidence retrieval."""

import os
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dotenv import load_dotenv

try:
    import chromadb
    from chromadb.config import Settings
except ImportError:
    chromadb = None

try:
    import tiktoken
except ImportError:
    tiktoken = None

from openai import OpenAI

from utils.document_loader import Document, DocumentLoader

load_dotenv()


class TextChunker:
    """Splits text into overlapping chunks based on token count."""

    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 50,
        encoding_name: str = "cl100k_base"
    ):
        """Initialize the text chunker.

        Args:
            chunk_size: Maximum tokens per chunk.
            chunk_overlap: Number of overlapping tokens between chunks.
            encoding_name: Tiktoken encoding name.
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

        if tiktoken:
            self.encoding = tiktoken.get_encoding(encoding_name)
        else:
            self.encoding = None
            print("Warning: tiktoken not installed. Using character-based chunking.")

    def count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        if self.encoding:
            return len(self.encoding.encode(text))
        # Fallback: estimate ~4 chars per token
        return len(text) // 4

    def chunk_text(self, text: str) -> List[str]:
        """Split text into overlapping chunks.

        Args:
            text: The text to chunk.

        Returns:
            List of text chunks.
        """
        if not text.strip():
            return []

        # Split into paragraphs first
        paragraphs = text.split('\n\n')
        paragraphs = [p.strip() for p in paragraphs if p.strip()]

        chunks = []
        current_chunk = []
        current_tokens = 0

        for para in paragraphs:
            para_tokens = self.count_tokens(para)

            # If single paragraph exceeds chunk size, split it further
            if para_tokens > self.chunk_size:
                # Flush current chunk first
                if current_chunk:
                    chunks.append('\n\n'.join(current_chunk))
                    current_chunk = []
                    current_tokens = 0

                # Split paragraph by sentences
                sentences = self._split_sentences(para)
                for sent in sentences:
                    sent_tokens = self.count_tokens(sent)
                    if current_tokens + sent_tokens > self.chunk_size:
                        if current_chunk:
                            chunks.append(' '.join(current_chunk))
                        # Keep overlap
                        overlap_text = ' '.join(current_chunk[-2:]) if len(current_chunk) >= 2 else ''
                        current_chunk = [overlap_text] if overlap_text else []
                        current_tokens = self.count_tokens(overlap_text) if overlap_text else 0
                    current_chunk.append(sent)
                    current_tokens += sent_tokens
            else:
                # Check if adding this paragraph exceeds limit
                if current_tokens + para_tokens > self.chunk_size:
                    if current_chunk:
                        chunks.append('\n\n'.join(current_chunk))
                    # Keep last paragraph for overlap
                    overlap = current_chunk[-1] if current_chunk else ''
                    current_chunk = [overlap, para] if overlap else [para]
                    current_tokens = self.count_tokens('\n\n'.join(current_chunk))
                else:
                    current_chunk.append(para)
                    current_tokens += para_tokens

        # Don't forget the last chunk
        if current_chunk:
            chunks.append('\n\n'.join(current_chunk))

        return chunks

    def _split_sentences(self, text: str) -> List[str]:
        """Split text into sentences."""
        import re
        sentences = re.split(r'(?<=[.!?])\s+', text)
        return [s.strip() for s in sentences if s.strip()]


class RAGEngine:
    """RAG engine using ChromaDB and OpenAI embeddings."""

    def __init__(
        self,
        persist_directory: Optional[str] = None,
        collection_name: str = "asdwise_clinical",
        embedding_model: str = "text-embedding-3-small"
    ):
        """Initialize the RAG engine.

        Args:
            persist_directory: Directory to persist ChromaDB data.
            collection_name: Name of the ChromaDB collection.
            embedding_model: OpenAI embedding model to use.
        """
        if chromadb is None:
            raise ImportError("chromadb is required. Install with: pip install chromadb")

        self.embedding_model = embedding_model
        self.collection_name = collection_name

        # Initialize OpenAI client for embeddings
        self.openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        # Initialize ChromaDB
        if persist_directory:
            self.persist_directory = persist_directory
            self.chroma_client = chromadb.PersistentClient(path=persist_directory)
        else:
            self.chroma_client = chromadb.Client()

        # Get or create collection
        self.collection = self.chroma_client.get_or_create_collection(
            name=collection_name,
            metadata={"description": "ASDWise clinical evidence for RAG"}
        )

        # Initialize chunker
        self.chunker = TextChunker()

        # Document loader
        self.loader = DocumentLoader()

    def _get_embedding(self, text: str) -> List[float]:
        """Get embedding for a text using OpenAI.

        Args:
            text: Text to embed.

        Returns:
            Embedding vector.
        """
        response = self.openai_client.embeddings.create(
            model=self.embedding_model,
            input=text
        )
        return response.data[0].embedding

    def _get_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Get embeddings for multiple texts.

        Args:
            texts: List of texts to embed.

        Returns:
            List of embedding vectors.
        """
        response = self.openai_client.embeddings.create(
            model=self.embedding_model,
            input=texts
        )
        return [item.embedding for item in response.data]

    def add_document(self, document: Document) -> int:
        """Add a document to the index.

        Args:
            document: Document to add.

        Returns:
            Number of chunks added.
        """
        chunks = self.chunker.chunk_text(document.content)

        if not chunks:
            return 0

        # Prepare data for ChromaDB
        ids = []
        documents = []
        metadatas = []

        source = document.metadata.get('source', 'unknown')
        title = document.metadata.get('title', 'Untitled')

        for i, chunk in enumerate(chunks):
            chunk_id = f"{source}_{i}"
            ids.append(chunk_id)
            documents.append(chunk)
            metadatas.append({
                **document.metadata,
                'chunk_index': i,
                'total_chunks': len(chunks)
            })

        # Get embeddings
        embeddings = self._get_embeddings_batch(documents)

        # Add to collection
        self.collection.add(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas
        )

        print(f"Added {len(chunks)} chunks from '{title}'")
        return len(chunks)

    def add_documents(self, documents: List[Document]) -> int:
        """Add multiple documents to the index.

        Args:
            documents: List of documents to add.

        Returns:
            Total number of chunks added.
        """
        total_chunks = 0
        for doc in documents:
            total_chunks += self.add_document(doc)
        return total_chunks

    def add_from_directory(self, directory_path: str, recursive: bool = True) -> int:
        """Load and add all documents from a directory.

        Args:
            directory_path: Path to the directory.
            recursive: Whether to search subdirectories.

        Returns:
            Total number of chunks added.
        """
        documents = self.loader.load_directory(directory_path, recursive)
        return self.add_documents(documents)

    def retrieve(
        self,
        query: str,
        k: int = 5,
        threshold: float = 0.0
    ) -> List[Dict]:
        """Retrieve relevant chunks for a query.

        Args:
            query: The search query.
            k: Number of results to return.
            threshold: Minimum similarity score (0-1, higher = more similar).

        Returns:
            List of results with content, metadata, and score.
        """
        if self.collection.count() == 0:
            return []

        # Get query embedding
        query_embedding = self._get_embedding(query)

        # Search
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=k,
            include=['documents', 'metadatas', 'distances']
        )

        # Format results
        formatted_results = []
        if results['documents'] and results['documents'][0]:
            for i, doc in enumerate(results['documents'][0]):
                # ChromaDB returns L2 distance, convert to similarity
                distance = results['distances'][0][i] if results['distances'] else 0
                # Approximate similarity (lower distance = higher similarity)
                similarity = 1 / (1 + distance)

                if similarity >= threshold:
                    formatted_results.append({
                        'content': doc,
                        'metadata': results['metadatas'][0][i] if results['metadatas'] else {},
                        'similarity': similarity
                    })

        return formatted_results

    def format_context(self, results: List[Dict], max_tokens: int = 2000) -> str:
        """Format retrieved results as context for the LLM.

        Args:
            results: List of retrieval results.
            max_tokens: Maximum tokens for context.

        Returns:
            Formatted context string.
        """
        if not results:
            return "No relevant clinical evidence found in the knowledge base."

        context_parts = []
        total_tokens = 0

        for i, result in enumerate(results, 1):
            source = result['metadata'].get('title', 'Unknown Source')
            content = result['content']

            entry = f"**Source {i}: {source}**\n{content}\n"
            entry_tokens = self.chunker.count_tokens(entry)

            if total_tokens + entry_tokens > max_tokens:
                break

            context_parts.append(entry)
            total_tokens += entry_tokens

        return '\n---\n'.join(context_parts)

    def get_stats(self) -> Dict:
        """Get statistics about the index.

        Returns:
            Dictionary with index statistics.
        """
        return {
            'collection_name': self.collection_name,
            'total_chunks': self.collection.count(),
            'embedding_model': self.embedding_model
        }

    def clear_index(self):
        """Clear all documents from the index."""
        self.chroma_client.delete_collection(self.collection_name)
        self.collection = self.chroma_client.get_or_create_collection(
            name=self.collection_name,
            metadata={"description": "ASDWise clinical evidence for RAG"}
        )
        print(f"Cleared collection: {self.collection_name}")


# Singleton instance for easy access
_rag_engine: Optional[RAGEngine] = None


def get_rag_engine(
    persist_directory: Optional[str] = None,
    collection_name: str = "asdwise_clinical"
) -> RAGEngine:
    """Get or create the RAG engine singleton.

    Args:
        persist_directory: Directory to persist ChromaDB data.
        collection_name: Name of the ChromaDB collection.

    Returns:
        RAGEngine instance.
    """
    global _rag_engine

    if _rag_engine is None:
        if persist_directory is None:
            # Default to src/data/chroma_db
            persist_directory = str(
                Path(__file__).parent.parent / "data" / "chroma_db"
            )

        _rag_engine = RAGEngine(
            persist_directory=persist_directory,
            collection_name=collection_name
        )

    return _rag_engine
