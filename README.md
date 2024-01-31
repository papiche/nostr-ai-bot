# nostr-ai-bot
A Python AI (ollama) connected to Nostr

Configure with environment variables:

```bash
OLLAMA_MODEL="dolphin-mixtral" \
PRIVATE_KEY="nsec..." python3 main.py
```

You can also set relays with RELAYS environment variable.

If you don't have private key, run python3 main.py and one will be
created for you and printed. You can grab the nsec then and use it
as private key.
