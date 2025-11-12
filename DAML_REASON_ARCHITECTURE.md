# DAML Reason Tool Architecture

## Business Context

**DAML Reason** is a paid tool (x402) for developers to check DAML code for security and business logic flaws before deployment. Since it's paid, it MUST provide reliable value or refuse to run (and not charge).

## Core Principle: Back Delegation

When the tool cannot provide reliable analysis, it **delegates back** to the calling LLM/user rather than providing low-confidence output and charging for it.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    DAML Reason Tool                         │
│                  (validate_daml_business_logic)             │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                   SafetyChecker (Gate 1)                    │
│  ┌───────────────────────────────────────────────────────┐ │
│  │  Step 1: Compile DAML                                 │ │
│  │  Step 2: Check Anti-Patterns                          │ │
│  │  Step 3: Extract Authorization Model (with confidence)│ │
│  │  Step 4: Decision Point                               │ │
│  │    ├─ Confidence >= 0.7 → Continue                    │ │
│  │    └─ Confidence < 0.7  → DELEGATE                    │ │
│  └───────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                            │
                ┌───────────┴───────────┐
                ▼                       ▼
    ┌──────────────────┐    ┌──────────────────┐
    │ High Confidence  │    │ Low Confidence   │
    │ (>= 0.7)         │    │ (< 0.7)          │
    │                  │    │                  │
    │ ✅ Provide       │    │ ⚠️  Delegate     │
    │    Analysis      │    │    Back to LLM   │
    │                  │    │                  │
    │ 💰 Charge User   │    │ 🚫 Don't Charge  │
    └──────────────────┘    └──────────────────┘
```

## Internal Tools & Decision Logic

### Step 1: Compilation (DamlCompiler)
**Tool**: `DamlCompiler.compile()`
- Compiles DAML code to check for syntax/type errors
- **Decision**: If compilation fails → Block (with errors)
- **Charge**: Yes (we provided definitive error information)

### Step 2: Anti-Pattern Check (PolicyChecker)
**Tool**: `PolicyChecker.check_against_policies()`
- Checks code against canonical anti-patterns using LLM
- **Decision**: If matches anti-pattern → Block (with suggestions)
- **Charge**: Yes (we provided definitive policy violation)
- **Cost**: LLM cost automatically included via x402 dynamic pricing

### Step 3: Authorization Extraction (AuthorizationValidator)
**Tool**: `AuthorizationValidator.extract_auth_model()`
- Attempts to extract authorization model using regex
- Calculates confidence score based on pattern complexity
- Optionally uses LLM fallback if confidence < threshold

**Confidence Calculation**:
- Start at 1.0
- Penalize for complex patterns:
  - List concatenation (`<>`): ×0.6
  - List cons (`::`): ×0.7
  - List field as controller: ×0.65
  - List field as observer: ×0.85

**Decision**:
- Confidence >= 0.7 → Continue with extraction
- Confidence < 0.7 & LLM available → Try LLM fallback
- Confidence < 0.7 & LLM unavailable → **DELEGATE**
- LLM improves confidence → Use LLM result (cost passed through)
- LLM fails → **DELEGATE**

### Step 4: Final Decision
**Tool**: `SafetyChecker.check_pattern_safety()`

**High Confidence Path** (confidence >= 0.7):
- ✅ Return full analysis
- 💰 Charge user via x402
- 📊 Include confidence score in response

**Low Confidence Path** (confidence < 0.7):
- ⚠️  Set `should_delegate = True`
- 📝 Provide delegation reason
- 🚫 Minimal charge (just for compilation/anti-pattern check)
- 💡 Suggest to calling LLM: simplify code or use manual review

## Response Structure

### High Confidence Response
```json
{
  "valid": true,
  "issues": [],
  "suggestions": [],
  "confidence": 0.95,
  "should_delegate": false,
  "authorization_model": { ... }
}
```
**x402 Cost**: Base + LLM (if used) + markup

### Low Confidence Response (Delegation)
```json
{
  "valid": false,
  "issues": [
    "⚠️  ANALYSIS UNCERTAIN (confidence: 0.51)",
    "Reason: Authorization extraction confidence too low (0.51). Uncertain patterns: list concatenation (<>), observer 'observers' (likely list field)"
  ],
  "suggestions": [
    "This code uses complex patterns that require human review or LLM analysis. Consider simplifying the authorization model or using the LLM-enhanced analysis."
  ],
  "confidence": 0.51,
  "should_delegate": true,
  "delegation_reason": "Authorization extraction confidence too low (0.51). Uncertain patterns: list concatenation (<>), observer 'observers' (likely list field)"
}
```
**x402 Cost**: Minimal (compilation + anti-pattern check only, no auth analysis charge)

## Configuration

### Environment Variables
```bash
# Enable LLM-enhanced authorization extraction
ENABLE_LLM_AUTH_EXTRACTION=true

# Confidence threshold for delegation (0.0-1.0)
# Lower = fewer delegations, more false positives
# Higher = more delegations, fewer false positives
LLM_AUTH_CONFIDENCE_THRESHOLD=0.7

# Anthropic API key for LLM fallback
ANTHROPIC_API_KEY=<your-key>
```

### Recommended Settings

**For Production (Balanced)**:
- `LLM_AUTH_CONFIDENCE_THRESHOLD=0.7` (default)
- `ENABLE_LLM_AUTH_EXTRACTION=true`
- Provides good balance between reliability and coverage

**For High Precision (Fewer False Positives)**:
- `LLM_AUTH_CONFIDENCE_THRESHOLD=0.8`
- `ENABLE_LLM_AUTH_EXTRACTION=true`
- More delegations, but very high reliability when it does provide analysis

**For Cost-Sensitive (More False Positives)**:
- `LLM_AUTH_CONFIDENCE_THRESHOLD=0.6`
- `ENABLE_LLM_AUTH_EXTRACTION=false`
- Less delegation, but may provide uncertain analysis

## x402 Pricing Model Alignment

### Dynamic Pricing
The x402 payment model charges based on **actual cost + markup**:

1. **Compilation**: Fixed cost (DAML SDK execution)
2. **Anti-Pattern Check**: Variable (LLM API cost)
3. **Authorization Extraction**:
   - Regex only: Minimal cost
   - LLM fallback: LLM API cost (automatically included)
4. **Markup**: Fixed percentage on top of actual costs

### Cost Transparency
```
Total Cost = (Compilation + Anti-Pattern LLM + Auth Extraction LLM) × Markup
```

When tool delegates:
```
Total Cost = (Compilation + Anti-Pattern LLM) × Markup
             ⬆️ No auth extraction charge
```

### Benefits
- ✅ Users only pay for reliable analysis
- ✅ Complex patterns automatically cost more (LLM usage)
- ✅ Simple patterns stay cheap (regex only)
- ✅ Delegation avoids charging for uncertain analysis

## Reliability Guarantees

### What We Guarantee

1. **High Confidence Analysis** (>= 0.7):
   - Compilation is correct
   - Anti-patterns are correctly identified
   - Authorization model is accurately extracted
   - **Money-back if wrong** (via x402 dispute mechanism)

2. **Low Confidence Delegation** (< 0.7):
   - We're uncertain about authorization model
   - Code may be too complex for our analyzer
   - **No charge for uncertain analysis**
   - Clear explanation of why we're uncertain

### What We Don't Guarantee

- Coverage of all possible DAML patterns (we delegate when uncertain)
- Zero false positives (configurable via threshold)
- Instant analysis (LLM fallback may take longer)

## Developer Experience

### Successful Analysis
```
Developer submits DAML code
  ↓
Tool analyzes with high confidence
  ↓
Developer receives clear results
  ↓
Developer pays for reliable analysis ✅
```

### Delegation Flow
```
Developer submits complex DAML code
  ↓
Tool identifies low confidence
  ↓
Developer receives delegation notice with:
  - Confidence score
  - Uncertain patterns identified
  - Suggestions to simplify code
  ↓
Developer can:
  - Simplify authorization model
  - Use different pattern
  - Request manual review
  ↓
Minimal charge for compilation/anti-pattern check 🚫
```

## Future Improvements

1. **AST-Based Parsing**: Replace regex with DAML AST parser (higher confidence)
2. **Pattern Library**: Learn from successful extractions to improve confidence
3. **Confidence Calibration**: Track accuracy vs. confidence to tune thresholds
4. **User Feedback**: Allow developers to report incorrect delegations
5. **Caching**: Cache LLM extractions for repeated patterns

## Summary

The DAML Reason tool implements a **confidence-based delegation mechanism** that ensures:

1. ✅ **Reliability**: Only provides analysis when confident
2. 💰 **Fair Pricing**: Only charges for reliable analysis
3. 🤖 **LLM Integration**: Uses LLM intelligently (only when needed)
4. 📊 **Transparency**: Clear confidence scores and delegation reasons
5. 👩‍💻 **Developer-Friendly**: Helpful suggestions when delegating

This architecture aligns perfectly with the x402 payment model, where actual processing costs (including LLM) are automatically factored into pricing, and users only pay for value provided.

