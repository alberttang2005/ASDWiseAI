"""Lazy exports keep deterministic helpers independent of AI/RAG startup."""
from importlib import import_module
_EXPORTS = {
 'OpenAIClient': ('utils.openai_client','OpenAIClient'),
 'MCHATScorer': ('utils.mchat_scorer','MCHATScorer'),
 'ConversationManager': ('utils.conversation','ConversationManager'),
 'RAGEngine': ('utils.rag_engine','RAGEngine'),
 'get_rag_engine': ('utils.rag_engine','get_rag_engine'),
 'Document': ('utils.document_loader','Document'),
 'DocumentLoader': ('utils.document_loader','DocumentLoader'),
}
__all__ = ['OpenAIClient','MCHATScorer','ConversationManager']
def __getattr__(name):
 if name not in _EXPORTS:raise AttributeError(name)
 module,attribute=_EXPORTS[name]
 value=getattr(import_module(module),attribute)
 globals()[name]=value
 return value
