from enum import Enum


class LLMProvider(str, Enum):
    GROQ = "groq"
    AZURE = "azure"