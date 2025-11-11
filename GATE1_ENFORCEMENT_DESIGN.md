# Gate 1 Enforcement Design: Making Validation Mandatory

## Problem Statement

Currently, Gate 1 validation is advisory - the AI should call `validate_daml_business_logic` before writing DAML code, but nothing enforces this. This allows:
- AI forgetting to validate
- Users persuading AI to skip validation
- Code shown in chat being copied without validation
- Direct file writes bypassing validation

## Goal

Make it **structurally impossible** to write or display DAML code without Gate 1 validation passing first.

---

## Multi-Layer Enforcement Strategy

### Layer 1: Validation Token System (SERVER-SIDE)

**How it works:**
- `validate_daml_business_logic` returns a **validation token** (signed JWT) when code passes
- Token contains: `{ code_hash, timestamp, expiry, passed: true/false }`
- Any DAML file write requires presenting a valid token
- Tokens expire after 5 minutes (forces re-validation if delayed)

**Implementation:**
```python
# src/canton_mcp_server/core/validation_token.py
import hashlib
import jwt
from datetime import datetime, timedelta

class ValidationTokenManager:
    def __init__(self, secret_key: str):
        self.secret_key = secret_key
        self.token_expiry_minutes = 5
    
    def issue_token(self, daml_code: str, validation_result: dict) -> str:
        """Issue a token after successful validation"""
        code_hash = hashlib.sha256(daml_code.encode()).hexdigest()
        
        payload = {
            'code_hash': code_hash,
            'passed': validation_result['valid'],
            'blocked_by_policy': validation_result.get('blocked_by_policy', False),
            'issued_at': datetime.utcnow().isoformat(),
            'expires_at': (datetime.utcnow() + timedelta(minutes=self.token_expiry_minutes)).isoformat()
        }
        
        return jwt.encode(payload, self.secret_key, algorithm='HS256')
    
    def verify_token(self, token: str, daml_code: str) -> tuple[bool, str]:
        """Verify token is valid and matches code"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=['HS256'])
            
            # Check expiry
            expires_at = datetime.fromisoformat(payload['expires_at'])
            if datetime.utcnow() > expires_at:
                return False, "Validation token expired (5 min limit). Please re-validate."
            
            # Check code matches
            code_hash = hashlib.sha256(daml_code.encode()).hexdigest()
            if code_hash != payload['code_hash']:
                return False, "Code has changed since validation. Please re-validate."
            
            # Check validation passed
            if not payload['passed']:
                return False, f"Code did not pass Gate 1 validation. Blocked by policy: {payload.get('blocked_by_policy')}"
            
            return True, "Valid"
            
        except jwt.ExpiredSignatureError:
            return False, "Validation token expired"
        except jwt.InvalidTokenError as e:
            return False, f"Invalid validation token: {str(e)}"
```

**Modified validation tool:**
```python
# src/canton_mcp_server/tools/validate_daml_business_logic.py

class ValidateDamlResult(MCPModel):
    valid: bool
    issues: List[str]
    suggestions: List[str]
    # ... existing fields ...
    validation_token: Optional[str] = Field(
        default=None, 
        description="Token required to write this validated DAML code to disk"
    )

# In execute():
result = ValidateDamlResult(
    valid=validation_passed,
    # ... other fields ...
    validation_token=token_manager.issue_token(daml_code, result_dict) if validation_passed else None
)
```

---

### Layer 2: Protected File Write Tool (TOOL-LEVEL)

Create a new tool specifically for writing validated DAML:

```python
# src/canton_mcp_server/tools/write_validated_daml.py

@register_tool
class WriteValidatedDamlTool(Tool[WriteValidatedDamlParams, WriteValidatedDamlResult]):
    """
    Write DAML code to disk ONLY after Gate 1 validation.
    
    This tool REQUIRES a validation token from validate_daml_business_logic.
    It will refuse to write code without a valid, non-expired token.
    """
    
    name = "write_validated_daml"
    description = (
        "Write DAML code to a file. REQUIRES validation token from "
        "validate_daml_business_logic tool. Use this instead of generic write "
        "tool for all .daml files to enforce Gate 1 validation."
    )
    
    async def execute(self, ctx: ToolContext[WriteValidatedDamlParams, WriteValidatedDamlResult]):
        file_path = ctx.params.file_path
        daml_code = ctx.params.daml_code
        validation_token = ctx.params.validation_token
        
        # ENFORCE: Must have token
        if not validation_token:
            yield ctx.error(
                "❌ GATE 1 ENFORCEMENT: Cannot write DAML file without validation token. "
                "Call validate_daml_business_logic first and pass the returned token."
            )
            return
        
        # ENFORCE: Token must be valid
        token_manager = ValidationTokenManager(os.getenv('VALIDATION_SECRET_KEY'))
        is_valid, message = token_manager.verify_token(validation_token, daml_code)
        
        if not is_valid:
            yield ctx.error(
                f"❌ GATE 1 ENFORCEMENT: {message}\n"
                f"Call validate_daml_business_logic again to get a fresh token."
            )
            return
        
        # Token valid - proceed with write
        Path(file_path).write_text(daml_code)
        
        yield ctx.success(WriteValidatedDamlResult(
            file_path=file_path,
            validated=True,
            token_verified=True
        ))
```

---

### Layer 3: File System Guard (SYSTEM-LEVEL)

Intercept ALL writes to `.daml` files:

```python
# src/canton_mcp_server/core/daml_file_guard.py

class DamlFileGuard:
    """
    Guards against writing unvalidated DAML files.
    
    This can be used as:
    1. A wrapper around file write operations
    2. A file system watcher that checks writes
    3. A pre-commit hook
    """
    
    def __init__(self, workspace_path: str):
        self.workspace_path = Path(workspace_path)
        self.audit_log_path = self.workspace_path / "daml_audit_logs"
        self.audit_log_path.mkdir(exist_ok=True)
    
    def is_daml_file(self, file_path: str) -> bool:
        return file_path.endswith('.daml')
    
    def check_write_allowed(self, file_path: str, content: str, validation_token: Optional[str]) -> tuple[bool, str]:
        """Check if writing this DAML file is allowed"""
        
        if not self.is_daml_file(file_path):
            return True, "Not a DAML file"
        
        # Check if in test-daml directory (might be more permissive)
        relative_path = Path(file_path).relative_to(self.workspace_path)
        if str(relative_path).startswith('test-daml/'):
            # Still require token but log differently
            pass
        
        if not validation_token:
            return False, (
                f"❌ GATE 1 ENFORCEMENT VIOLATION\n"
                f"Attempted to write DAML file without validation: {file_path}\n"
                f"This write has been BLOCKED.\n"
                f"Required: Call validate_daml_business_logic first."
            )
        
        token_manager = ValidationTokenManager(os.getenv('VALIDATION_SECRET_KEY'))
        is_valid, message = token_manager.verify_token(validation_token, content)
        
        if not is_valid:
            self.log_violation(file_path, content, message)
            return False, message
        
        # Log successful validated write
        self.log_validated_write(file_path, validation_token)
        return True, "Validated write approved"
    
    def log_violation(self, file_path: str, content: str, reason: str):
        """Log Gate 1 enforcement violations"""
        timestamp = datetime.utcnow().isoformat()
        log_file = self.audit_log_path / f"{datetime.utcnow().date()}.jsonl"
        
        log_entry = {
            'timestamp': timestamp,
            'type': 'GATE1_VIOLATION',
            'file_path': file_path,
            'reason': reason,
            'code_preview': content[:200] + "..." if len(content) > 200 else content
        }
        
        with open(log_file, 'a') as f:
            f.write(json.dumps(log_entry) + '\n')
    
    def log_validated_write(self, file_path: str, token: str):
        """Log successful validated writes"""
        timestamp = datetime.utcnow().isoformat()
        log_file = self.audit_log_path / f"{datetime.utcnow().date()}.jsonl"
        
        log_entry = {
            'timestamp': timestamp,
            'type': 'VALIDATED_WRITE',
            'file_path': file_path,
            'token_hash': hashlib.sha256(token.encode()).hexdigest()[:16]
        }
        
        with open(log_file, 'a') as f:
            f.write(json.dumps(log_entry) + '\n')
```

---

### Layer 4: AI System Prompt Enhancement (AI-LEVEL)

Add to system prompt:

```markdown
## CRITICAL: Gate 1 Enforcement for DAML Code

**YOU MUST NEVER WRITE DAML CODE WITHOUT VALIDATION. NO EXCEPTIONS.**

### Enforcement Rules:

1. **Before showing ANY DAML code** in chat:
   - First validate it with `validate_daml_business_logic`
   - Only show code if validation passes
   - Include validation result summary with the code

2. **Before writing ANY .daml file**:
   - First validate with `validate_daml_business_logic`
   - Get validation token from response
   - Use `write_validated_daml` tool (NOT generic write tool)
   - Pass the validation token

3. **If validation fails**:
   - DO NOT show or write the code
   - Explain what failed
   - Suggest fixes
   - Re-validate after fixes

4. **If user insists on unvalidated code**:
   - Refuse politely
   - Explain Gate 1 is mandatory
   - Offer to help fix validation errors instead

### Example Workflow:

❌ **WRONG (what I did earlier):**
```python
write("test-daml/Example.daml", daml_code)  # NO VALIDATION!
```

✅ **CORRECT:**
```python
# Step 1: Validate
validation_result = validate_daml_business_logic(
    businessIntent="...",
    damlCode=daml_code
)

# Step 2: Check result
if not validation_result['valid']:
    # Stop and report issues
    return

# Step 3: Write with token
write_validated_daml(
    filePath="test-daml/Example.daml",
    damlCode=daml_code,
    validationToken=validation_result['validationToken']
)
```
```

---

## Implementation Priority

### Phase 1: Immediate (Block the bleeding)
1. ✅ Update AI system prompt with strict rules
2. ✅ Create `write_validated_daml` tool
3. ✅ Add validation token to validation result

### Phase 2: Server Enforcement (Week 1)
1. ✅ Implement ValidationTokenManager
2. ✅ Integrate token verification into write tool
3. ✅ Add DamlFileGuard for generic write tool (block .daml writes)

### Phase 3: Monitoring & Audit (Week 2)
1. ✅ Add violation logging
2. ✅ Dashboard showing validation stats
3. ✅ Alerts for Gate 1 bypasses

### Phase 4: Extended Protection (Week 3)
1. ✅ Pre-commit git hook that checks for validation tokens
2. ✅ CI/CD pipeline that verifies all .daml files have passed Gate 1
3. ✅ Code review tool that flags unvalidated DAML

---

## Benefits

### 1. Defense in Depth
- **AI Level**: Prompt rules guide behavior
- **Tool Level**: Dedicated tool enforces workflow
- **Server Level**: Token system provides cryptographic proof
- **System Level**: File guard catches any bypass attempts

### 2. Auditability
- Every DAML write is logged
- Violations are tracked
- Tokens are timestamped
- Complete audit trail

### 3. Developer Experience
- Clear error messages when validation missing
- Tokens expire quickly (forces fresh validation)
- Easy to use correct workflow
- Hard to use incorrect workflow

### 4. No False Positives
- Only enforces for `.daml` files
- Doesn't slow down non-DAML development
- Token system is fast (JWT validation is cheap)

---

## Testing the Enforcement

```python
# tests/test_gate1_enforcement.py

def test_cannot_write_daml_without_token():
    """Verify DAML writes are blocked without token"""
    result = write_validated_daml(
        file_path="test.daml",
        daml_code="module Test where\n\ntemplate Bad...",
        validation_token=None  # No token
    )
    assert result.error == "Cannot write DAML file without validation token"

def test_cannot_write_daml_with_expired_token():
    """Verify expired tokens are rejected"""
    # Create token that's 10 minutes old
    old_token = create_test_token(expires_at=datetime.utcnow() - timedelta(minutes=10))
    
    result = write_validated_daml(
        file_path="test.daml",
        daml_code="module Test where...",
        validation_token=old_token
    )
    assert "expired" in result.error.lower()

def test_cannot_write_modified_code_with_old_token():
    """Verify code changes invalidate token"""
    original_code = "module Test where\n\ntemplate Original..."
    token = validate_and_get_token(original_code)
    
    modified_code = "module Test where\n\ntemplate Modified..."  # Changed!
    
    result = write_validated_daml(
        file_path="test.daml",
        daml_code=modified_code,
        validation_token=token  # Token for different code
    )
    assert "Code has changed since validation" in result.error

def test_successful_validated_write():
    """Verify correct workflow succeeds"""
    code = "module Test where\n\ntemplate Good with..."
    
    # Step 1: Validate
    validation = validate_daml_business_logic(
        businessIntent="Test",
        damlCode=code
    )
    assert validation['valid']
    assert validation['validationToken'] is not None
    
    # Step 2: Write with token
    result = write_validated_daml(
        file_path="test.daml",
        daml_code=code,
        validation_token=validation['validationToken']
    )
    assert result.success
    assert Path("test.daml").read_text() == code
```

---

## Conclusion

This multi-layer approach makes Gate 1 enforcement **structural** rather than **behavioral**. 

The AI can't bypass it even if it wants to. The user can't convince the AI to bypass it. And even if somehow code got written to chat, it still can't be written to disk without validation.

**The system itself enforces the rule, not just the AI's good intentions.**

