#!/usr/bin/env python3
"""
Create a test Canton party key file for authentication testing.
This generates a new Ed25519 keypair and creates a properly formatted key file.
"""

import json
import base64
import hashlib
import sys
import os

try:
    from nacl.signing import SigningKey
except ImportError:
    print("ERROR: PyNaCl not installed")
    print("Install with: pip install pynacl")
    sys.exit(1)

def create_test_key(party_name="test-auth-user", output_dir=None):
    """Create a test Canton party key file"""

    # Generate a new Ed25519 keypair
    signing_key = SigningKey.generate()
    private_key_bytes = bytes(signing_key)
    public_key_bytes = bytes(signing_key.verify_key)

    # Compute fingerprint (1220 + SHA256 hex)
    computed_hash = hashlib.sha256(public_key_bytes).hexdigest()
    fingerprint = "1220" + computed_hash

    # Create party ID
    party_id = f"{party_name}::{fingerprint}"

    # Create key file data
    key_data = {
        "partyId": party_id,
        "privateKey": base64.b64encode(private_key_bytes).decode('ascii'),
        "publicKey": base64.b64encode(public_key_bytes).decode('ascii'),
        "fingerprint": fingerprint
    }

    # Determine output directory
    if output_dir is None:
        output_dir = os.path.expanduser("~/.canton")

    # Create directory if needed
    os.makedirs(output_dir, exist_ok=True)

    # Save to file
    key_file = os.path.join(output_dir, f"{party_name}-key.json")
    with open(key_file, 'w') as f:
        json.dump(key_data, f, indent=2)

    print(f"✅ Created test party key: {key_file}")
    print(f"")
    print(f"📋 Party ID: {party_id}")
    print(f"🔑 Public Key: {key_data['publicKey'][:50]}...")
    print(f"")
    print(f"To use in tests:")
    print(f"  export CANTON_PARTY_ID='{party_id}'")
    print(f"  export CANTON_KEY_FILE='{key_file}'")
    print(f"  ./test-challenge-auth.sh")

    return key_file, party_id

if __name__ == "__main__":
    party_name = sys.argv[1] if len(sys.argv) > 1 else "test-auth-user"
    create_test_key(party_name)
