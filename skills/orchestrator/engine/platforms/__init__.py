from .claude_ai import ClaudeAI
from .chatgpt import ChatGPT
from .copilot import Copilot
from .perplexity import Perplexity
from .grok import Grok
from .deepseek import DeepSeek
from .gemini import Gemini

ALL_PLATFORMS = {
    'claude_ai': ClaudeAI,
    'chatgpt': ChatGPT,
    'copilot': Copilot,
    'perplexity': Perplexity,
    'grok': Grok,
    'deepseek': DeepSeek,
    'gemini': Gemini,
}
