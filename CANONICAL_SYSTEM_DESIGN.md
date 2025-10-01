# Canonical System Design

## Security Model

### Core Principle
**Zero Trust Canonical Knowledge**: All canonical patterns, rules, and documentation must be cryptographically verified before use. Unverified content is rejected.

### Threat Model
1. **Compromised Source Files** - Attacker modifies local canonical pattern files
2. **Man-in-the-Middle** - Attacker intercepts and modifies canonical resources in transit
3. **Supply Chain Attack** - Compromised dependencies inject malicious patterns
4. **Insider Threat** - Rogue maintainer publishes malicious patterns

### Defense Strategy
- **Content Hashing**: SHA-256 hash of every canonical resource
- **Blockchain Registry**: Immutable record of authoritative hashes
- **Verification-First**: Tools MUST verify before using any canonical knowledge
- **Audit Trail**: Log every canonical resource used with verified hash
- **Fail-Secure**: Reject operations if verification fails

---

## Resource Structure

### MCP Resource Format

Each canonical resource follows this structure:

```json
{
  "uri": "canton://canonical/pattern/simple-transfer/v1.0",
  "name": "Simple Transfer Pattern",
  "mimeType": "application/vnd.canton.pattern+yaml",
  "content": "...",
  "metadata": {
    "version": "1.0.0",
    "contentHash": "sha256:a1b2c3d4...",
    "publishedDate": "2024-01-15T00:00:00Z",
    "blockchainRegistry": {
      "chain": "canton-registry",
      "contractId": "0x...",
      "blockNumber": 12345
    },
    "author": "Digital Asset",
    "category": "pattern",
    "tags": ["transfer", "authorization", "basic"]
  }
}
```

### Resource Categories

#### 1. Patterns (`canton://canonical/pattern/{name}/v{version}`)
Canonical DAML patterns that represent best practices.

Example:
- `canton://canonical/pattern/simple-transfer/v1.0`
- `canton://canonical/pattern/multi-party-approval/v1.0`
- `canton://canonical/pattern/state-machine/v1.0`

#### 2. Anti-Patterns (`canton://canonical/anti-pattern/{name}/v{version}`)
Known problematic patterns that should be detected and flagged.

Example:
- `canton://canonical/anti-pattern/missing-signatory/v1.0`
- `canton://canonical/anti-pattern/unauthorized-controller/v1.0`

#### 3. Rules (`canton://canonical/rule/{name}/v{version}`)
Validation rules that define invariants and constraints.

Example:
- `canton://canonical/rule/authorization-invariants/v1.0`
- `canton://canonical/rule/safety-checks/v1.0`

#### 4. Documentation (`canton://canonical/doc/{name}/v{version}`)
Authoritative documentation and explanations.

---

## Content Format

### Pattern Resource YAML

```yaml
id: simple-transfer
version: "1.0.0"
category: pattern
name: Simple Transfer Pattern
description: |
  Basic pattern for transferring ownership of an asset or obligation
  from one party to another with proper authorization.

security_level: basic

daml_template: |
  template Transfer
    with
      owner: Party
      asset: Asset
    where
      signatory owner
      
      choice TransferOwnership : ContractId Transfer
        with
          newOwner: Party
        controller owner
        do
          create this with owner = newOwner

authorization_requirements:
  - id: REQ-AUTH-001
    rule: "Controller must be signatory or have explicit authorization"
    satisfied: true
    explanation: "owner is signatory and controller"
  
  - id: REQ-AUTH-002
    rule: "All state modifications must be authorized"
    satisfied: true
    explanation: "Only owner can modify ownership"

when_to_use:
  - "Simple ownership transfers"
  - "Unilateral actions by asset owner"
  - "No multi-party approval required"

when_not_to_use:
  - "Multi-party approval needed"
  - "Complex state transitions"
  - "Time-locked or conditional transfers"

related_patterns:
  - "multi-party-approval"
  - "delegation-custody"

security_considerations:
  - "Ensure owner is signatory"
  - "Validate asset state before transfer"
  - "Consider observer disclosure for transparency"

test_cases:
  - description: "Valid transfer"
    passes: true
    code: |
      alice transfers to bob
      
  - description: "Unauthorized transfer"
    passes: false
    expected_error: "not a stakeholder"
    code: |
      bob attempts to transfer alice's asset

references:
  - name: "DAML Authorization Patterns"
    url: "https://docs.daml.com/patterns/authorization.html"
  - name: "Canton Security Best Practices"
    url: "https://docs.daml.com/canton/security.html"
```

### Anti-Pattern Resource YAML

```yaml
id: missing-signatory
version: "1.0.0"
category: anti-pattern
name: Missing Signatory
severity: critical
description: |
  Template defined with no signatory. This is a critical error that
  will prevent contract creation and represents a fundamental
  misunderstanding of DAML authorization.

problematic_code: |
  template BadContract
    with
      party1: Party
      party2: Party
    where
      observer party1, party2
      -- ERROR: No signatory!

why_problematic: |
  Every DAML template MUST have at least one signatory. Signatories
  are the parties who authorize the creation of a contract and are
  obligated by it. Without signatories, the contract cannot be created.

detection_pattern:
  - "Template definition with no 'signatory' clause"
  - "Only 'observer' clauses present"

correct_alternative: |
  template GoodContract
    with
      party1: Party
      party2: Party
    where
      signatory party1  -- or both parties
      observer party2

impact:
  - type: "correctness"
    severity: "critical"
    description: "Contract creation will fail"
  
  - type: "security"
    severity: "critical"
    description: "No authorization model"

remediation:
  - "Add at least one signatory"
  - "Determine which party should authorize contract creation"
  - "Review DAML authorization documentation"

references:
  - name: "DAML Signatories"
    url: "https://docs.daml.com/daml/reference/templates.html#signatories"
```

### Rule Resource YAML

```yaml
id: authorization-invariants
version: "1.0.0"
category: rule
name: Authorization Invariants
description: |
  Fundamental authorization rules that MUST hold for all DAML contracts.

rules:
  - id: AUTH-001
    name: "Signatory Required"
    severity: critical
    description: "Every template must have at least one signatory"
    validation: |
      for each template:
        assert exists signatory clause
        assert len(signatories) >= 1
    
  - id: AUTH-002
    name: "Controller Authorization"
    severity: critical
    description: "Choice controllers must be signatories or have explicit authorization"
    validation: |
      for each choice:
        controller_parties = get_controllers(choice)
        signatories = get_signatories(template)
        observers = get_observers(template)
        
        for controller in controller_parties:
          assert (controller in signatories) OR
                 (controller in observers AND has_explicit_authorization(controller))
    
  - id: AUTH-003
    name: "Observer Justification"
    severity: warning
    description: "Observers should be justified - avoid over-disclosure"
    validation: |
      for each template:
        observers = get_observers(template)
        if len(observers) > 3:
          warn("High number of observers - verify disclosure is necessary")
  
  - id: AUTH-004
    name: "Agreement for Multi-Party"
    severity: warning
    description: "Multi-signatory contracts should have agreement clause"
    validation: |
      for each template:
        signatories = get_signatories(template)
        if len(signatories) > 1 AND not has_agreement_clause(template):
          warn("Multi-signatory contract should have agreement clause")

enforcement: mandatory

exceptions:
  - rule_id: AUTH-003
    condition: "Regulatory requirements mandate disclosure"
    justification: "Compliance with transparency regulations"
```

---

## Hash Verification System

### Verification Flow

```python
def verify_and_load_canonical_resource(uri: str) -> CanonicalResource:
    """
    Securely load and verify a canonical resource.
    
    Args:
        uri: Canonical resource URI
        
    Returns:
        Verified canonical resource
        
    Raises:
        SecurityError: If verification fails
    """
    # 1. Fetch resource content
    content = fetch_resource(uri)
    
    # 2. Compute content hash
    computed_hash = sha256(content)
    
    # 3. Get authoritative hash from blockchain
    authoritative_hash = query_blockchain_registry(uri)
    
    # 4. Verify hash matches
    if computed_hash != authoritative_hash:
        log_security_event(
            event="HASH_MISMATCH",
            uri=uri,
            computed=computed_hash,
            expected=authoritative_hash
        )
        raise SecurityError(f"Hash verification failed for {uri}")
    
    # 5. Log verified usage
    log_audit_trail(
        action="VERIFIED_LOAD",
        uri=uri,
        hash=computed_hash,
        timestamp=now()
    )
    
    # 6. Parse and return
    return parse_canonical_resource(content)
```

### Blockchain Registry Contract

```solidity
// Simplified example - actual implementation would be more robust
contract CanonicalRegistry {
    struct ResourceRecord {
        string uri;
        bytes32 contentHash;
        uint256 publishedBlock;
        address publisher;
        bool active;
    }
    
    mapping(string => ResourceRecord) public registry;
    
    event ResourcePublished(
        string indexed uri,
        bytes32 contentHash,
        uint256 blockNumber
    );
    
    function publishResource(
        string memory uri,
        bytes32 contentHash
    ) public onlyAuthorized {
        require(!registry[uri].active, "URI already registered");
        
        registry[uri] = ResourceRecord({
            uri: uri,
            contentHash: contentHash,
            publishedBlock: block.number,
            publisher: msg.sender,
            active: true
        });
        
        emit ResourcePublished(uri, contentHash, block.number);
    }
    
    function verifyHash(
        string memory uri,
        bytes32 computedHash
    ) public view returns (bool) {
        ResourceRecord memory record = registry[uri];
        return record.active && record.contentHash == computedHash;
    }
}
```

---

## Tool Integration

### Updated Tool Signature

```python
@app.tool()
def validate_daml_business_logic(
    business_intent: str,
    daml_code: str,
    security_requirements: List[str] = None
) -> Dict[str, Any]:
    """
    Validate DAML code against canonical authorization patterns.
    
    All validation uses cryptographically verified canonical resources.
    """
    try:
        # Load and verify canonical rules
        auth_rules = verify_and_load_canonical_resource(
            "canton://canonical/rule/authorization-invariants/v1.0"
        )
        safety_rules = verify_and_load_canonical_resource(
            "canton://canonical/rule/safety-checks/v1.0"
        )
        
        # Load canonical patterns for comparison
        patterns = load_verified_patterns([
            "simple-transfer",
            "multi-party-approval",
            # ... more patterns
        ])
        
        # Load known anti-patterns
        anti_patterns = load_verified_anti_patterns()
        
        # Perform validation
        issues = validate_against_rules(daml_code, auth_rules, safety_rules)
        suggestions = suggest_patterns(business_intent, patterns)
        anti_pattern_matches = detect_anti_patterns(daml_code, anti_patterns)
        
        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "suggestions": suggestions,
            "anti_patterns_detected": anti_pattern_matches,
            "verified_resources_used": [
                auth_rules.get_verification_info(),
                safety_rules.get_verification_info(),
                # ...
            ]
        }
        
    except SecurityError as e:
        # Verification failed - fail secure
        return {
            "error": "SECURITY_ERROR",
            "message": "Failed to verify canonical resources",
            "details": str(e),
            "safe_mode": True
        }
```

---

## Implementation Phases

### Phase 1: Resource Structure (Week 1)
- [ ] Define YAML schemas for patterns, anti-patterns, rules
- [ ] Create initial canonical resources
- [ ] Set up MCP resource serving
- [ ] Implement content hashing

### Phase 2: Verification System (Week 2)
- [ ] Design blockchain registry contract
- [ ] Implement hash verification in server
- [ ] Add audit logging
- [ ] Create fail-secure error handling

### Phase 3: Tool Integration (Week 3)
- [ ] Update validation tools to use verified resources
- [ ] Implement pattern matching engine
- [ ] Add anti-pattern detection
- [ ] Create comprehensive test suite

### Phase 4: Deployment (Week 4)
- [ ] Deploy blockchain registry
- [ ] Publish initial canonical resources
- [ ] Document verification process
- [ ] Create governance model for updates

---

## Governance Model

### Publishing New Canonical Resources

1. **Proposal**: Submit resource with justification
2. **Review**: Technical review by committee
3. **Testing**: Validate against test suite
4. **Approval**: Multi-signature approval required
5. **Publishing**: Hash recorded on blockchain
6. **Distribution**: Resource made available via MCP

### Updating Resources

- New versions get new URIs with version increment
- Old versions remain accessible for backwards compatibility
- Deprecation timeline announced in advance
- Tools can specify minimum/maximum version requirements

### Security Updates

- Critical fixes get expedited review process
- Immediate publication with security advisory
- All tools must update within 30 days
- Auto-notification to all registered servers

---

## Open Questions

1. **Which blockchain?** 
   - Canton network itself (dogfooding)
   - Ethereum mainnet (established, expensive)
   - Polygon/L2 (cheaper, still secure)
   - Private Canton network (more control, less decentralization)

2. **Governance structure?**
   - Who can publish canonical resources?
   - How are disputes resolved?
   - What's the approval process?

3. **Versioning strategy?**
   - Semantic versioning?
   - Breaking vs non-breaking changes?
   - Backwards compatibility requirements?

4. **Performance considerations?**
   - Cache verified resources locally?
   - How often to re-verify?
   - Offline mode with pre-verified bundle?

