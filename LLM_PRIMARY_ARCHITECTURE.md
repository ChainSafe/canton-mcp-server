# LLM-Primary Architecture for DAML Reason Tool

## Overview

The DAML Reason tool now uses **LLM as the primary analysis method** for authorization extraction, with regex patterns as a fallback for degraded mode.

## Architecture Flow

```
┌─────────────────────────────────────────────────────────────┐
│              validate_daml_business_logic                    │
│                   (DAML Reason Tool)                         │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
                    ┌──────────────────┐
                    │ Step 1: Compile  │
                    │ (DamlCompiler)   │
                    └──────────────────┘
                            │
                            ▼
                    ┌──────────────────┐
                    │ Step 2: Check    │
                    │ Anti-Patterns    │
                    │ (PolicyChecker)  │
                    │ Uses: LLM        │
                    └──────────────────┘
                            │
                            ▼
          ┌─────────────────────────────────────┐
          │ Step 3: Extract Authorization Model │
          │ (AuthorizationValidator)            │
          └─────────────────────────────────────┘
                            │
                ┌───────────┴───────────┐
                │   LLM Available?      │
                └───────────┬───────────┘
                     /              \
                 YES ✅             NO ⚠️
                    ▼                  ▼
        ┌────────────────────┐   ┌──────────────────┐
        │  PRIMARY PATH      │   │ DEGRADED MODE    │
        │                    │   │                  │
        │  Use LLM (Haiku)   │   │  Use Regex       │
        │  Confidence: 0.85+ │   │                  │
        │                    │   │  Simple: 0.8     │
        │  ✅ Reliable       │   │  Complex: 0.5    │
        │  💰 ~$0.001/call   │   │                  │
        │                    │   │  ⚠️  Limited     │
        └────────────────────┘   └──────────────────┘
                    │                      │
                    └──────────┬───────────┘
                               ▼
                    ┌──────────────────────┐
                    │ Confidence >= 0.7?   │
                    └──────────────────────┘
                         /            \
                     YES ✅           NO ⚠️
                        ▼                ▼
            ┌──────────────────┐  ┌─────────────┐
            │ Return Analysis  │  │  DELEGATE   │
            │ valid: true      │  │  valid: false│
            │                  │  │  should_     │
            │ 💰 Charge user   │  │  delegate:   │
            │                  │  │  true        │
            └──────────────────┘  └─────────────┘
```

## Key Changes

### Before (Regex-Primary)
1. Try regex extraction
2. Calculate confidence
3. If low confidence → Try LLM fallback
4. Return result

**Problem**: Regex can't handle complex patterns reliably, leading to false positives/negatives

### After (LLM-Primary)
1. **If LLM available** → Use LLM (primary path)
2. **If LLM unavailable** → Use regex (degraded mode)
3. Check confidence threshold
4. Delegate if uncertain

**Benefit**: LLM handles all DAML complexity reliably; regex only for simple fallback

## Primary Path: LLM with Claude Haiku

**Model**: `claude-3-5-haiku-20241022`

**Why Haiku?**
- ✅ Excellent at structured extraction tasks
- ✅ Fast (~2-3x faster than Sonnet)
- ✅ Cheap (~$0.001 per analysis)
- ✅ Deterministic (temperature=0)
- ✅ Good at parsing code syntax

**Prompt Strategy**:
- Clear task definition
- 3 concrete examples
- Explicit rules for list operations
- Confidence scoring guidance
- JSON-only output format

**Expected Performance**:
- Simple patterns: 1.0 confidence
- List operations (<>, ::): 0.95 confidence  
- Multiple choices: 0.9 confidence
- Complex expressions: 0.8+ confidence

## Degraded Mode: Regex Fallback

**When Used**: LLM unavailable (no ANTHROPIC_API_KEY or ENABLE_LLM_AUTH_EXTRACTION=false)

**Behavior**:
1. Check for complex patterns (`<>`, `::`, `if/then`)
2. If complex: Return confidence 0.5 → **DELEGATE**
3. If simple: Return confidence 0.8 → Pass

**Message to User**: "Enable LLM for full coverage"

## Configuration

### Recommended for Production
```bash
# Enable LLM-primary analysis
ENABLE_LLM_AUTH_EXTRACTION=true

# Set Anthropic API key
ANTHROPIC_API_KEY=sk-ant-...

# Confidence threshold for delegation
LLM_AUTH_CONFIDENCE_THRESHOLD=0.7
```

### Cost-Sensitive Development
```bash
# Disable LLM (degraded mode)
ENABLE_LLM_AUTH_EXTRACTION=false

# Only simple patterns will work
# Complex patterns will delegate
```

## Cost Analysis

### Primary Path (LLM Enabled)

**Typical Analysis**:
- Compilation: Fixed cost
- Anti-Pattern Check (LLM): ~$0.003
- Authorization Extraction (LLM): ~$0.001
- **Total: ~$0.004 + markup**

**Breakdown**:
- Input: ~500 tokens (DAML code)
- Output: ~200 tokens (JSON result)
- Haiku cost: $0.00025/1K in, $0.00125/1K out
- Cost: (500 × 0.00025 + 200 × 0.00125) / 1000 = ~$0.001

### Degraded Mode (LLM Disabled)

**Simple Pattern**:
- Compilation: Fixed cost
- Anti-Pattern Check: Skipped
- Authorization Extraction: Regex (free)
- **Total: Minimal + markup**

**Complex Pattern**:
- Compilation: Fixed cost
- Delegation: No analysis charge
- **Total: Minimal + markup**
- User receives: "Enable LLM for full coverage"

## User Experience

### With LLM Enabled (Recommended)

**Developer submits complex DAML code**:
```daml
template PaymentApproval
  with
    requester: Party
    approvers: [Party]
    observers: [Party]
  where
    signatory requester
    observer approvers <> observers  -- Complex!
```

**Tool response**:
```json
{
  "valid": true,
  "confidence": 0.95,
  "issues": [],
  "authorization_model": {
    "template_name": "PaymentApproval",
    "signatories": ["requester"],
    "observers": ["approvers", "observers"]
  }
}
```

**Cost**: ~$0.004 (Boom! Payment for reliable analysis)

### Without LLM (Degraded Mode)

**Developer submits complex DAML code**:

**Tool response**:
```json
{
  "valid": false,
  "should_delegate": true,
  "confidence": 0.5,
  "issues": [
    "⚠️  ANALYSIS UNCERTAIN (confidence: 0.50)",
    "Reason: Regex extraction in degraded mode with complex patterns"
  ],
  "suggestions": [
    "Enable LLM (ANTHROPIC_API_KEY + ENABLE_LLM_AUTH_EXTRACTION=true) for full coverage"
  ]
}
```

**Cost**: Minimal (no uncertain analysis charged)

## Benefits

### 1. Reliability
- ✅ LLM handles all DAML complexity
- ✅ No infinite pattern matching needed
- ✅ Natural handling of edge cases

### 2. Predictable Costs
- 💰 Primary path always uses LLM
- 💰 Costs are consistent and predictable
- 💰 x402 automatically includes actual cost

### 3. Clear Value Proposition
- 🎯 "We use AI to analyze your code"
- 🎯 Boom! Payment = Boom! Analysis
- 🎯 No hidden complexity

### 4. Graceful Degradation
- ⚠️  Without LLM: Simple patterns still work
- ⚠️  Complex patterns: Clear delegation message
- ⚠️  No false confidence

### 5. Developer Experience
- 👍 High confidence = Reliable results
- 👍 Low confidence = Clear next steps
- 👍 Degraded mode = Clear explanation

## Testing Strategy

### Unit Tests
- ✅ LLM extraction on 20+ patterns
- ✅ Regex degraded mode on simple patterns
- ✅ Delegation on complex patterns without LLM
- ✅ Confidence scoring accuracy

### Integration Tests
- ✅ Full tool flow with LLM
- ✅ Full tool flow without LLM
- ✅ x402 cost calculation

### Real-World Validation
- 📊 Monitor LLM confidence distribution
- 📊 Track delegation rates
- 📊 Measure false positive/negative rates
- 📊 User satisfaction with results

## Future Enhancements

### Optional Sonnet Escalation
If Haiku confidence < 0.85, escalate to Sonnet:
```python
if haiku_confidence < 0.85:
    sonnet_result = extract_with_sonnet(code)
    if sonnet_confidence > haiku_confidence:
        return sonnet_result  # Higher cost, higher confidence
```

### Pattern Caching
Cache LLM extractions for repeated patterns:
```python
cache_key = hash(code)
if cache_key in extraction_cache:
    return extraction_cache[cache_key]
```

### Confidence Calibration
Track accuracy vs. confidence to tune thresholds:
```python
# If 0.95 confidence has 99% accuracy, we're good
# If 0.95 confidence has 80% accuracy, adjust model or prompt
```

## Summary

The LLM-primary architecture provides:
- ✅ **Reliable analysis** for all DAML patterns
- 💰 **Predictable costs** via x402
- ⚡ **Fast results** with Haiku
- 🚫 **No false confidence** in degraded mode
- 👨‍💻 **Clear value** for developers

This aligns perfectly with the x402 payment model: **Boom! Payment = Boom! Reliable Analysis**

