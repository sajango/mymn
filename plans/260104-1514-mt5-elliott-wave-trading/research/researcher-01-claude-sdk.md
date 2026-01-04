# Claude SDK Research Report
**Date**: 2026-01-04 | **Task**: Python Automation for Trading Analysis

---

## 1. SDK Availability & Installation

**Status**: ✅ **Anthropic Python SDK (v0.34.0+)**
- **Package**: `anthropic` (not `claude-code-sdk`)
- **Installation**: `pip install anthropic`
- Claude Code is IDE integration; API uses standard Anthropic SDK
- Works with Claude 3.5 Sonnet, Opus 4.5, Haiku models

**Key Point**: Claude Code (IDE tool) ≠ Claude API SDK (Python library)

---

## 2. Headless Automation Support

**Status**: ✅ **Full Support**
- No GUI required; pure Python async/sync API
- Suitable for scheduled tasks, cron jobs, background workers
- Credentials via environment variables

```python
from anthropic import Anthropic

client = Anthropic()  # Uses ANTHROPIC_API_KEY env var
response = client.messages.create(
    model="claude-opus-4-5-20251101",
    max_tokens=4096,
    messages=[{"role": "user", "content": "Analyze this data..."}]
)
```

---

## 3. Authentication

**Method**: API Key
- **Env Variable**: `ANTHROPIC_API_KEY` (required)
- **No OAuth/WebAuthn**: Direct API key authentication
- Single API endpoint for all subscription tiers

```python
import os
from anthropic import Anthropic

client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
```

---

## 4. File Handling (CSV Context)

**Status**: ⚠️ **Manual Implementation Required**
- No built-in file upload endpoint
- CSV data passed as text in message content

```python
with open("data.csv", "r") as f:
    csv_content = f.read()

response = client.messages.create(
    model="claude-opus-4-5-20251101",
    max_tokens=4096,
    system="You are an Elliott Wave analyst...",
    messages=[{
        "role": "user",
        "content": f"Analyze these CSV files:\n\nH4:\n{csv_h4}\n\nH1:\n{csv_h1}"
    }]
)
```

---

## 5. Response Parsing (JSON Extraction)

**Status**: ✅ **Manual parsing**

```python
import json
import re

text = response.content[0].text

# Extract JSON block
json_match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
if json_match:
    data = json.loads(json_match.group(1))
else:
    # Fallback: find first { to last }
    json_str = text[text.find('{'):text.rfind('}')+1]
    data = json.loads(json_str)
```

---

## 6. Rate Limits (Opus Model)

**Token-based pricing**:
- Input: $3/1M tokens
- Output: $15/1M tokens (Opus 4.5)
- No documented strict rate limit; fair use policy
- ~10 req/min safe margin at 10K tokens/request

---

## 7. Error Handling

**SDK Exceptions**:
- `anthropic.APIStatusError`: HTTP errors (401, 429, 500+)
- `anthropic.RateLimitError`: 429 Too Many Requests
- `anthropic.APIConnectionError`: Network/timeout

```python
from anthropic import Anthropic, RateLimitError, APIConnectionError
import time

def call_claude_with_retry(client, messages, max_retries=3):
    for attempt in range(max_retries):
        try:
            return client.messages.create(
                model="claude-opus-4-5-20251101",
                max_tokens=4096,
                messages=messages
            )
        except RateLimitError:
            wait = 2 ** attempt
            time.sleep(wait)
        except APIConnectionError as e:
            if attempt == max_retries - 1:
                raise
            time.sleep(1)
    raise Exception("Max retries exceeded")
```

---

## Key Findings

| Aspect | Status | Notes |
|--------|--------|-------|
| **Python SDK** | ✅ | `anthropic` package |
| **Headless** | ✅ | Full async/sync, no UI |
| **Auth** | ✅ | API key via env var |
| **CSV Input** | ⚠️ | Manual text inclusion |
| **JSON Output** | ✅ | Manual parsing |
| **Rate Limits** | ✅ | Token-based |
| **Error Handling** | ✅ | 3 exception types |

---

## Unresolved Questions

1. Does Claude Max subscription provide different API access than standard?
2. What is the precise definition of "fair use" rate limiting?
3. Token limits per request for Opus model?
