# Gate 1: DAML Security Validation Guide

## ⚠️ CRITICAL INSTRUCTION FOR AI ASSISTANTS

**ALWAYS validate DAML code through Gate 1 BEFORE writing any files.**

Gate 1 is a security enforcement layer that prevents unsafe authorization patterns from being created in the first place. This is not optional - it's a mandatory safety check.

## The Gate 1 Workflow

### 1. User Requests DAML Code
User: "Create a transfer contract for assets"

### 2. Generate & Validate FIRST (Before Writing!)
```
AI: Let me validate this pattern through Gate 1...
→ Call validate_daml_business_logic(businessIntent, damlCode, securityRequirements)
```

### 3. Check Result
- ✅ **If valid=true**: Safe to write to filesystem
- ❌ **If valid=false**: BLOCK creation, explain why, suggest safe alternatives

### 4. Never Write Unsafe Code
If Gate 1 blocks the pattern, you MUST:
1. Inform the user why it was blocked
2. Explain the security risks
3. Suggest safe canonical alternatives
4. Offer to create a safe version instead

## Gate 1 Detection Layers

Gate 1 performs multiple security checks:

### Layer 1: DAML Compilation
- Syntax validation
- Type checking
- **Authorization model validation** (controllers must be authorized)

### Layer 2: Canonical Anti-Pattern Matching
- Checks against known dangerous patterns
- If matched: **BLOCKED with policy reasoning**
- Provides `safe_alternatives` suggestions

### Layer 3: Authorization Validation
- Signatories correctly defined
- Controllers are authorized (signatory or observer)
- No unauthorized state changes

## Common Anti-Patterns That Gate 1 Blocks

### ❌ Missing Signatory
```daml
template BadContract
  with
    owner: Party
  where
    observer owner  -- ❌ No signatory!
```
**Why blocked**: Every contract MUST have at least one signatory who authorizes its creation.

### ❌ Unauthorized Controller
```daml
template Asset
  with
    owner: Party
    randomParty: Party
  where
    signatory owner
    
    choice Transfer : ()
      controller randomParty  -- ❌ Not a signatory or observer!
      do return ()
```
**Why blocked**: `randomParty` has no authorization relationship to the contract.

### ❌ Anyone Can Transfer (Pull-Based Transfer)
```daml
template Asset
  with
    owner: Party
  where
    signatory owner
    
    choice StealAsset : ContractId Asset
      with
        thief: Party
      controller thief  -- ❌ Unauthorized party can steal assets!
      do create this with owner = thief
```
**Why blocked**: Creates a critical security vulnerability where any party can steal assets.

## Safe Canonical Patterns

### ✅ Owner-Controlled Transfer
```daml
template Asset
  with
    owner: Party
  where
    signatory owner
    
    choice Transfer : ContractId Asset
      with
        newOwner: Party
      controller owner  -- ✅ Only owner can transfer
      do create this with owner = newOwner
```

### ✅ Two-Step Transfer (Propose/Accept)
```daml
template Asset
  with
    owner: Party
  where
    signatory owner
    
    choice ProposeTransfer : ContractId TransferProposal
      with
        newOwner: Party
      controller owner
      do
        create TransferProposal with
          asset = this
          proposedOwner = newOwner

template TransferProposal
  with
    asset: Asset
    proposedOwner: Party
  where
    signatory asset.owner
    observer proposedOwner
    
    choice Accept : ContractId Asset
      controller proposedOwner
      do create asset with owner = proposedOwner
    
    choice Reject : ()
      controller proposedOwner
      do return ()
```

## Using the Tools

### validate_daml_business_logic
**When to call**: BEFORE writing any DAML file

```json
{
  "businessIntent": "Create an IOU where owner can transfer to another party",
  "damlCode": "module SimpleIou where\n\ntemplate Iou...",
  "securityRequirements": ["Owner controls transfers", "Amount must be positive"]
}
```

**Response fields**:
- `valid`: true/false - whether code passes all checks
- `blocked_by_policy`: true if canonical anti-pattern matched
- `anti_pattern_matched`: name of matched anti-pattern
- `safe_alternatives`: list of suggested safe patterns
- `issues`: list of problems found
- `suggestions`: list of improvements

### recommend_canonical_resources
**When to call**: Before designing new patterns

Search 30k+ verified DAML patterns from the official SDK:
```json
{
  "useCase": "asset_management",
  "description": "Need a transfer pattern with approval workflow",
  "securityLevel": "enhanced",
  "complexityLevel": "intermediate"
}
```

### suggest_authorization_pattern
**When to call**: Need authorization design guidance

```json
{
  "workflowDescription": "Multi-party approval with threshold (2 of 3)",
  "securityLevel": "enhanced",
  "constraints": ["Prevent self-approval", "Track approvers", "Gas-efficient"]
}
```

## AI Assistant Checklist

When a user asks for DAML code:

- [ ] **DO**: Call `validate_daml_business_logic` FIRST
- [ ] **DO**: Check the `valid` field in the response
- [ ] **DO**: If `blocked_by_policy=true`, explain why and suggest alternatives
- [ ] **DO**: Only write files if validation passes
- [ ] **DO**: Search canonical resources first with `recommend_canonical_resources`
- [ ] **DON'T**: Write DAML files without validation
- [ ] **DON'T**: Bypass Gate 1 checks
- [ ] **DON'T**: Create unsafe patterns even if user requests them

## Example: Correct Gate 1 Usage

**User Request**: "Write me a contract where anyone can transfer ownership"

**Correct AI Response**:
```
Let me validate this pattern through Gate 1 first...

[Calls validate_daml_business_logic]

🛑 GATE 1 BLOCKED: Cannot create this contract.

Why: This pattern allows unauthorized parties to transfer assets without 
the owner's permission, creating a critical security vulnerability.

Gate 1 Finding: Authorization model invalid - controller is not authorized.

Safe Alternative: Here's an owner-controlled transfer pattern...
[Shows safe code]

Would you like me to create the safe version instead?
```

## Resources

- 📚 **Canonical Resources**: 30k+ verified DAML patterns from official SDK
- 🔒 **Anti-Patterns**: Known dangerous patterns that Gate 1 blocks
- ✅ **Safe Patterns**: Tested, production-ready authorization patterns
- 📖 **DAML Docs**: Authorization guide and best practices

## Questions?

Gate 1 is designed to prevent security vulnerabilities before they're created. 
If you think a pattern was incorrectly blocked, please review the policy 
reasoning and consider if there's a safer alternative approach.

**Remember**: Gate 1 is your ally, not an obstacle. It saves you from creating 
vulnerable contracts that could be exploited in production.

