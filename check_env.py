import os
from pathlib import Path
from dotenv import load_dotenv

# Try to load .env.canton
env_path = Path(".env.canton")
if env_path.exists():
    print("✓ Found .env.canton")
    load_dotenv(env_path)
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if key:
        print(f"✓ ANTHROPIC_API_KEY is set (length: {len(key)} chars)")
        print(f"  Starts with: {key[:10]}..." if len(key) > 10 else f"  Full: {key}")
    else:
        print("✗ ANTHROPIC_API_KEY is empty or not set")
    
    # Check other relevant vars
    print(f"\nENABLE_LLM_AUTH_EXTRACTION: {os.getenv('ENABLE_LLM_AUTH_EXTRACTION', 'not set')}")
else:
    print("✗ .env.canton not found")
