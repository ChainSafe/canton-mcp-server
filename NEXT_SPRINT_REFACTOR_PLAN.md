# Next Sprint: Refactor to User-Delegated 2-Tool Model

## Philosophy Shift

**Current Model (Enforcement):**
- Try to intercept and block unsafe operations
- AI is responsible for using tools correctly
- Complex enforcement infrastructure required
- Constant cat-and-mouse with prompt injection

**New Model (Delegation):**
- User explicitly delegates DAML tasks to specialized tools
- Tools are the "source of truth" that users consult
- Simple, clean tool boundaries
- If user bypasses tools, that's their choice (and responsibility)

---

## The Two Tools

### 1. **DAML REASONING** (The Thinking Tool)

**Purpose:** Analysis, validation, and architectural guidance

**What it does:**
- Validates DAML code through Gate 1
- Analyzes authorization patterns
- Explains why code is safe/unsafe
- Suggests canonical patterns from library
- Provides architectural recommendations
- Debugs authorization failures

**What it DOESN'T do:**
- Write files
- Execute code
- Make changes to codebase

**User Experience:**
```
User: "I want to create a multi-party transfer contract"
  ↓
User calls: daml_reasoning(intent="multi-party transfer", requirements=[...])
  ↓
Tool returns:
- Recommended pattern from canonical library
- Security analysis
- Implementation guidance
- Example code (validated)
```

**Implementation:**
- Combines: validate_daml_business_logic + recommend_canonical_resources + debug_authorization_failure
- Returns rich analysis objects
- No side effects

---

### 2. **DAML AUTOMATION** (The Execution Tool)

**Purpose:** Safe, validated automation of DAML workflows

**What it does:**
- Writes validated DAML files to disk
- Compiles DAML code
- Runs tests
- Deploys to Canton ledger
- Generates boilerplate

**What it DOESN'T do:**
- Skip validation
- Make architectural decisions
- Override safety checks

**User Experience:**
```
User: "Implement the pattern we just discussed"
  ↓
User calls: daml_automation(
    action="write_validated_code",
    code=<validated_code_from_reasoning>,
    validation_token=<token_from_reasoning>
)
  ↓
Tool:
- Verifies token
- Writes file
- Runs compilation
- Returns result
```

**Implementation:**
- Combines: File writing + compilation + deployment
- Requires validation token from DAML_REASONING
- Server-side state tracking
- Audit logging

---

## The Workflow

### Typical User Flow

```
┌─────────────────────────────────────────────┐
│ 1. User has a DAML requirement              │
└────────────────┬────────────────────────────┘
                 ↓
┌─────────────────────────────────────────────┐
│ 2. User: "Call daml_reasoning to analyze"  │
│    - Describes what they want               │
│    - Gets recommendations                   │
│    - Receives validated code + token        │
└────────────────┬────────────────────────────┘
                 ↓
┌─────────────────────────────────────────────┐
│ 3. User reviews reasoning output            │
│    - Reads explanation                      │
│    - Understands security implications      │
│    - Decides to proceed                     │
└────────────────┬────────────────────────────┘
                 ↓
┌─────────────────────────────────────────────┐
│ 4. User: "Call daml_automation to write"   │
│    - Passes code + token                    │
│    - Tool verifies and executes             │
│    - File written safely                    │
└─────────────────────────────────────────────┘
```

### Key Points

1. **Explicit Delegation:** User actively chooses to use the tools
2. **Two-Step Process:** Think first (reasoning), act second (automation)
3. **User in Control:** User can review reasoning before automation
4. **Clear Boundaries:** Reasoning doesn't write, automation doesn't think

---

## Why This Works Better

### 1. **Clearer Mental Model**

**Before:**
- "The AI should validate DAML... but how do we enforce it?"
- "What if user tricks the AI?"
- "Do we block writes? How?"

**After:**
- "User calls daml_reasoning when they want expert analysis"
- "User calls daml_automation when they want safe execution"
- "If they don't call the tools, that's on them"

### 2. **Better User Experience**

**Before:**
```
User: "Create a transfer contract"
AI: "Let me validate this first..."
[AI tries to be responsible, might get confused]
```

**After:**
```
User: "Use daml_reasoning to design a transfer contract"
Tool: [Returns comprehensive analysis]
User: "Now use daml_automation to implement it"
Tool: [Safely executes]
```

### 3. **Simpler Implementation**

**Before:**
- Intercept write operations
- Track validation state everywhere
- Handle edge cases (what if user edits after validation?)
- Build enforcement infrastructure

**After:**
- Two clean tools with clear responsibilities
- Token-based workflow (simple state)
- No interception needed
- Enforcement only at automation boundaries

### 4. **Trust Model**

**Before:**
- "We must protect users from themselves"
- "AI must be the responsible parent"
- Adversarial relationship

**After:**
- "We provide expert tools users can trust"
- "Users delegate to specialists"
- Collaborative relationship

---

## Implementation Plan

### Phase 1: Create the Two New Tools

**Tool 1: `daml_reasoning`**
```python
@register_tool
class DamlReasoningTool(Tool):
    """
    DAML Reasoning Engine
    
    Expert analysis and guidance for DAML smart contracts.
    Validates, recommends patterns, and provides security analysis.
    """
    
    async def execute(self, ctx):
        intent = ctx.params.intent
        code = ctx.params.code  # Optional
        requirements = ctx.params.requirements
        
        # 1. Search canonical patterns
        patterns = await self.search_patterns(intent, requirements)
        
        # 2. If code provided, validate it
        if code:
            validation = await self.validate(code, intent)
            token = self.issue_token(code) if validation.passed else None
        
        # 3. Return comprehensive analysis
        return ReasoningResult(
            recommended_patterns=patterns,
            validation=validation,
            security_analysis=analysis,
            implementation_guide=guide,
            validation_token=token,  # For automation
            next_steps=["Call daml_automation with this token"]
        )
```

**Tool 2: `daml_automation`**
```python
@register_tool
class DamlAutomationTool(Tool):
    """
    DAML Automation Engine
    
    Safe execution of validated DAML operations.
    Writes files, compiles code, runs tests, deploys contracts.
    """
    
    async def execute(self, ctx):
        action = ctx.params.action  # write_file, compile, test, deploy
        code = ctx.params.code
        token = ctx.params.validation_token
        
        # 1. Verify token
        if not self.verify_token(token, code):
            raise ValidationError("Invalid or expired token. Call daml_reasoning first.")
        
        # 2. Execute requested action
        if action == "write_file":
            result = await self.write_validated_file(code, ctx.params.path)
        elif action == "compile":
            result = await self.compile_daml(code)
        elif action == "deploy":
            result = await self.deploy_to_canton(code)
        
        # 3. Log and return
        self.audit_log(action, token, result)
        return AutomationResult(success=True, details=result)
```

### Phase 2: Deprecate Old Tools

Mark as deprecated:
- `validate_daml_business_logic` → Use `daml_reasoning`
- `recommend_canonical_resources` → Use `daml_reasoning`
- `debug_authorization_failure` → Use `daml_reasoning`
- `suggest_authorization_pattern` → Use `daml_reasoning`

### Phase 3: Update MCP Prompts

```python
Prompt(
    name="daml-workflow",
    description=(
        "For DAML development, use this two-step workflow:\n"
        "1. Call 'daml_reasoning' to analyze and validate your approach\n"
        "2. Call 'daml_automation' to safely execute the validated plan\n\n"
        "Example:\n"
        "User: 'I need a multi-party approval contract'\n"
        "You: daml_reasoning(intent='multi-party approval', requirements=[...])\n"
        "→ Review reasoning output with user\n"
        "You: daml_automation(action='write_file', code=..., token=...)\n\n"
        "Never skip step 1. Always get reasoning before automation."
    )
)
```

### Phase 4: Update Documentation

- Rewrite GATE1_USAGE_GUIDE.md for new model
- Add examples of reasoning → automation workflow
- Update README with new tool descriptions

---

## Benefits Summary

| Aspect | Old Model | New Model |
|--------|-----------|-----------|
| **Complexity** | High (enforcement) | Low (delegation) |
| **User Control** | Implicit (AI decides) | Explicit (user chooses) |
| **Security** | Hoped-for (via guidance) | Structural (via tokens) |
| **Maintenance** | Constant updates | Stable boundaries |
| **UX** | Confusing (AI seems to argue) | Clear (user delegates) |
| **Trust** | Adversarial | Collaborative |

---

## Migration Strategy

1. **Soft Launch:** Add new tools alongside old ones
2. **Prompt Updates:** Guide users toward new workflow
3. **Deprecation Warnings:** Old tools warn about upcoming removal
4. **Documentation:** Heavy emphasis on new workflow
5. **Hard Cutover:** Remove old tools after transition period

---

## Success Metrics

How we'll know this works:

1. **User Adoption:** % of users calling reasoning → automation
2. **Token Usage:** Automation calls always have valid tokens
3. **Support Requests:** Fewer "why did validation fail?" questions
4. **Code Quality:** Same or better DAML safety metrics
5. **Developer Satisfaction:** Clearer, more predictable workflow

---

## Open Questions

1. Should daml_reasoning return multiple pattern options or just the best one?
2. How long should validation tokens be valid? (Proposal: 5 minutes)
3. Should daml_automation support "force" mode for experienced users?
4. Do we need a "daml_review" tool for auditing existing code?
5. How do we handle iterative development (code → validate → edit → validate → ...)?

---

## Timeline

**Sprint 1 (Next):**
- Implement daml_reasoning tool
- Implement daml_automation tool
- Add token system
- Update MCP prompts

**Sprint 2:**
- Deprecate old tools
- Update all documentation
- Add migration guide
- Community communication

**Sprint 3:**
- Monitor adoption
- Gather feedback
- Refine workflows
- Remove old tools

---

## Conclusion

This refactor transforms Canton MCP from an **enforcement system** (complex, adversarial) to a **delegation system** (simple, collaborative). Users explicitly choose to use expert tools, and those tools have clear, bounded responsibilities.

**The user becomes the orchestrator, not the subject of enforcement.**

