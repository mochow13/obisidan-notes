## Booking.com Claude Code

```json
{
  "apiKeyHelper": "bk auth:issue-token || (bk auth:login > /dev/null 2>&1 && bk auth:issue-token)",
  "env": {
    "ANTHROPIC_BASE_URL": "https://gen-ai.prod.booking.com/anthropic/claude_code/",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "ml-asset:static-model/claude-sonnet-4-5",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "ml-asset:static-model/claude-haiku-4-5",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "ml-asset:static-model/claude-opus-4-5"
  },
  "companyAnnouncements": [
    "Welcome to Claude Code at Booking.com! For tips and troubleshooting, see https://u.booking.com/claudecode."
  ]
}
```
