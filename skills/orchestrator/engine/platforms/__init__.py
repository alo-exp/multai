from .claude_ai import ClaudeAI  # pragma: no cover
from .chatgpt import ChatGPT  # pragma: no cover
from .copilot import Copilot  # pragma: no cover
from .perplexity import Perplexity  # pragma: no cover
from .grok import Grok  # pragma: no cover
from .deepseek import DeepSeek  # pragma: no cover
from .gemini import Gemini  # pragma: no cover

ALL_PLATFORMS = {  # pragma: no cover
    'claude_ai': ClaudeAI,
    'chatgpt': ChatGPT,
    'copilot': Copilot,
    'perplexity': Perplexity,
    'grok': Grok,
    'deepseek': DeepSeek,
    'gemini': Gemini,
}
