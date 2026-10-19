"""Optional embedding providers."""

from tensemem.providers.embed.base import Embedder
from tensemem.providers.embed.fake import FakeEmbedder
from tensemem.providers.embed.fastembed import FastEmbedProvider
from tensemem.providers.embed.openai import OpenAIEmbedder

__all__ = ["Embedder", "FakeEmbedder", "FastEmbedProvider", "OpenAIEmbedder"]
