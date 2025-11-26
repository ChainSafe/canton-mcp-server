# DAML Tools Server-Side Dependency Analysis

## Summary

Both DAML tools (`daml_automater` and `daml_reason`) had server-side dependencies that are incompatible with a multi-tenant MCP server architecture.

---

## ✅ DAML Automater Tool - **FIXED**

### Problem
Required server-side DAML SDK and Docker for:
- Spinning up Canton containers
- Building DAML projects
- Running tests
- Managing environments

### Solution
Refactored to return **instructions** instead of executing operations. Now acts as an **advisor**, not an **executor**.

### Status: ✅ **COMPLETE**
- No server-side dependencies
- Returns rich instructions with commands
- Compatible with multi-tenant architecture

---

## ⚠️ DAML Reason Tool - **SERVER-SIDE DEPENDENCY FOUND**

### Current Architecture

```
DamlReasonTool (line 112)
    └─> SafetyChecker (line 211)
            └─> compiler property (line 92-97 in safety_checker.py)
                    └─> DamlCompiler.__init__ (line 44-71 in daml_compiler_integration.py)
                            └─> shutil.which("daml") - LINE 63
                                    └─> Raises DamlCompilerError if not found
```

### The Problem

**Location:** `src/canton_mcp_server/daml/daml_compiler_integration.py:62-66`

```python
# Verify daml command exists
if not shutil.which(self.daml_command):
    raise DamlCompilerError(
        f"DAML compiler not found. Please install DAML SDK: {self.daml_command}"
    )
```

**When It Fails:**
- When `SafetyChecker.check_pattern_safety()` is called (line 211 in daml_reason_tool.py)
- Which accesses `self.compiler` property
- Which lazily initializes `DamlCompiler`
- Which checks for `daml` CLI in PATH
- **Boom!** 💥 Server doesn't have DAML SDK

**Error Message:**
```
ERROR | Tool execution error: DAML compiler not found. Please install DAML SDK: daml
```

This is exactly what you saw in the production logs!

### Current Flow in DAML Reason Tool

```python
# Line 210-214 in daml_reason_tool.py
safety_result = await self.safety_checker.check_pattern_safety(
    daml_code, 
    module_name=module_name
)
```

This triggers:
1. **Compilation** (requires DAML SDK) ❌
2. **Authorization extraction** (LLM-based) ✅
3. **Pattern matching** (semantic search) ✅
4. **Anti-pattern detection** (regex-based) ✅

Only step #1 requires server-side DAML SDK!

---

## Recommended Solutions for DAML Reason Tool

### Option 1: Skip Compilation Entirely (Recommended for Production)

**Rationale:**
- 75% of the tool's value doesn't require compilation
- LLM-based authorization extraction works without compilation
- Semantic pattern matching works without compilation
- Anti-pattern detection works without compilation

**Implementation:**
Make compilation optional in `SafetyChecker`:

```python
# In safety_checker.py
@property
def compiler(self) -> Optional[DamlCompiler]:
    """Lazy initialization of DAML compiler (if available)."""
    if self._compiler is None:
        try:
            self._compiler = DamlCompiler(sdk_version=self._sdk_version)
        except DamlCompilerError as e:
            logger.warning(f"DAML compiler not available: {e}")
            logger.info("Continuing without compilation - using LLM analysis only")
            return None
    return self._compiler

async def check_pattern_safety(self, code: str, module_name: str = "Main") -> SafetyCheckResult:
    # Try compilation if compiler available
    if self.compiler:
        try:
            compilation_result = await self.compiler.compile(code, module_name)
        except DamlCompilerError:
            logger.warning("Compilation failed, continuing with LLM analysis")
            compilation_result = None
    else:
        logger.info("Skipping compilation (compiler not available)")
        compilation_result = None
    
    # Continue with LLM-based analysis...
```

**Pros:**
- ✅ Works immediately on multi-tenant servers
- ✅ Still provides valuable analysis
- ✅ No code changes to DAML Reason Tool itself
- ✅ Graceful degradation

**Cons:**
- ⚠️ No compile-time error detection
- ⚠️ No type safety verification from compiler

---

### Option 2: Add Environment Variable to Disable Compilation

**Implementation:**

```python
# In env.py
ENABLE_DAML_COMPILATION = get_env_bool("ENABLE_DAML_COMPILATION", False)

# In safety_checker.py
@property
def compiler(self) -> Optional[DamlCompiler]:
    if not get_env_bool("ENABLE_DAML_COMPILATION", False):
        return None
    
    if self._compiler is None:
        self._compiler = DamlCompiler(sdk_version=self._sdk_version)
    return self._compiler
```

**Production .env.canton:**
```bash
ENABLE_DAML_COMPILATION=false
```

**Local development (with DAML SDK):**
```bash
ENABLE_DAML_COMPILATION=true
```

**Pros:**
- ✅ Simple configuration
- ✅ Can enable for testing locally
- ✅ Clear intent

**Cons:**
- ⚠️ Requires configuration change

---

### Option 3: Client-Side Compilation Delegation (Future)

Similar to DAML Automater, return a prompt:

**Flow:**
1. User sends DAML code
2. Server responds: "Please compile this locally and send back the errors"
3. User runs `daml build` locally
4. User sends compilation errors back
5. Server analyzes errors and provides recommendations

**Pros:**
- ✅ Full compilation validation
- ✅ No server-side dependencies
- ✅ Best of both worlds

**Cons:**
- ⚠️ More complex interaction model
- ⚠️ Requires protocol changes
- ⚠️ User must have DAML SDK

---

## Immediate Action Items

### For DAML Reason Tool

**Quick Fix (Deploy Today):**
```python
# In safety_checker.py, line 92-97
@property
def compiler(self) -> Optional[DamlCompiler]:
    """Lazy initialization of DAML compiler (optional)."""
    if self._compiler is None:
        try:
            self._compiler = DamlCompiler(sdk_version=self._sdk_version)
        except DamlCompilerError:
            logger.warning("DAML compiler not available - using LLM analysis only")
            return None
    return self._compiler
```

Then update `check_pattern_safety` to handle `None` compiler gracefully.

**Long-term (Next Sprint):**
- Add `ENABLE_DAML_COMPILATION` environment variable
- Document the trade-offs
- Consider client-side compilation delegation

---

## Why This Matters

### Multi-Tenant MCP Server Requirements
1. **No environment-specific dependencies** (no DAML SDK, Docker, etc.)
2. **Stateless operation** (no local file system manipulation)
3. **Scalable architecture** (can run in containers, serverless, etc.)
4. **Delegate heavy lifting to clients** (who have the actual dev environments)

### Current State
| Component | Server-Side Deps | Status |
|-----------|-----------------|--------|
| DAML Automater | ❌ None | ✅ Fixed |
| DAML Reason (compilation) | ⚠️ DAML SDK | ❌ Needs fix |
| DAML Reason (LLM analysis) | ✅ API calls only | ✅ Works |
| DAML Reason (pattern matching) | ✅ ChromaDB | ✅ Works |

---

## Testing Checklist

After implementing Option 1 (recommended):

```bash
# 1. Verify server starts without DAML SDK
docker compose up --build

# 2. Test DAML Reason without code (pattern search only)
# Should work: Returns pattern recommendations

# 3. Test DAML Reason with code
# Should work: Returns LLM analysis + patterns
# Should NOT crash: Gracefully skips compilation

# 4. Check logs for warnings
# Should see: "DAML compiler not available - using LLM analysis only"

# 5. Test DAML Automater
# Should work: Returns instructions for all actions
```

---

## Conclusion

**DAML Automater:** ✅ **COMPLETE** - Fully converted to advisor mode

**DAML Reason:** ⚠️ **ACTION REQUIRED** - Needs compilation to be made optional

**Recommended Next Step:** Implement Option 1 (skip compilation entirely) for immediate production fix.


