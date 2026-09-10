# AI-Generated Math Challenges Specification

**Phase 4.2 — AI-Generated Math Challenges**  
**SmartWake AI** — Personalized Adaptive Smart Alarm Clock  
**Package:** `backend.app.services.genai`

---

## 1. Executive Summary & Purpose

Phase 4.2 establishes the foundation for **AI-Generated Math Challenges** within SmartWake AI.

While Phase 2.7 provides rule-based procedural arithmetic generation, Phase 4.2 enables Generative AI to produce varied, engaging, and themed wake-up mathematics problems while enforcing a **zero-trust trust boundary**:
- GenAI is treated as an **untrusted content generator**.
- The backend independently and deterministically calculates the authoritative `expected_answer` using a restricted Python Abstract Syntax Tree (AST) evaluator without `eval()` or `exec()`.
- If the model proposes an answer that conflicts with the calculated answer, or if the expression conflicts with structured operands, the challenge is **rejected immediately**.

```
Authoritative Challenge Type: "math"
+
Authoritative Concrete Difficulty: "easy" | "medium" | "hard" (from Phase 3 ML)
+
Safe Generation Context: SafePersonalizationContext (sanitized, zero PII)
+
Math Generation Constraints: MathGenerationConstraints (numerical/AST bounds, allowed ops)
       ↓
MathPromptBuilder (Structured provider prompt with JSON schema)
       ↓
GenAIService / Active Provider (MockGenAIProvider in tests)
       ↓
MathChallengePayload (Structured question, expression, operands)
       ↓
MathAnswerValidator (Restricted AST evaluator, bounds checking, exact division)
       ↓
ChallengeContentValidator (Framework validation: immutability, payload size, forbidden terms)
       ↓
ValidatedChallengeContent (Internal validated domain model with authoritative expected_answer)
```

---

## 2. Phase 4.2 Architectural Boundaries

To preserve stability across the wake session lifecycle, the following boundaries are strictly enforced:

1. **No Runtime Hijacking:** `ChallengeExecutionService` and wake session alarm lifecycles are **not modified**.
2. **Procedural Generator Preservation:** `_generate_math()` in `challenge_generation_service.py` is **untouched**. It continues servicing current wake alarms.
3. **Completion Verification Independence:** `verify_math()` in `challenge_verification_service.py` is **untouched**. Phase 4.2 outputs answers compatible with its existing contract.
4. **Scope Isolation:** Only **Math** challenges are implemented. Memory, Tongue Twister, Dance, and Push-ups remain untouched.
5. **Runtime Contract Decoupling:** `RuntimeChallengeResponse` is **not modified**. Future Phase 4.7 will adapt `ValidatedChallengeContent.content_payload` into `RuntimeChallengeResponse.generated_content`.
6. **Zero Database Impact:** Zero ORM models, zero migrations, zero writes to `smartwake.db`.
7. **Zero New Dependencies:** Zero packages added to `requirements.txt`.

---

## 3. Separation of Responsibilities Across Phases

| Phase / Engine | Core Question Answered | Authoritative Output |
|---|---|---|
| **Phase 3 ML (`AdaptiveDecisionEngine`)** | *"How difficult should the math challenge be?"* | Concrete difficulty: `easy`, `medium`, or `hard`. |
| **Phase 4.2 GenAI (`MathChallengeGenerator`)** | *"What math content should be generated at that already-selected difficulty?"* | `ValidatedChallengeContent` with independently calculated `expected_answer`. |
| **Phase 2.8 Verification (`verify_math`)** | *"Did the user actually solve it correctly during the alarm?"* | `ChallengeVerificationResult` (`is_successful`, score). |

---

## 4. Math Generation Constraints & Difficulty Tiers

The mathematical bounds strictly mirror the operational parameters established in Phase 2.7.3 and Phase 2.6 catalog seeds, augmented with deterministic numerical safety limits:

| Parameter | Easy Tier | Medium Tier | Hard Tier |
|---|---|---|---|
| **Allowed Operations** | Addition (`+`), Subtraction (`-`) | Addition, Subtraction, Multiplication (`*`), Division (`/`) | Addition, Subtraction, Multiplication, Division, Parentheses, Mixed |
| **Banned Operations** | Multiplication, Division, Exponents, Modulo, Bitwise | Exponents, Modulo, Bitwise | Exponents, Modulo, Bitwise |
| **Arithmetic Steps** | Exactly 1 operation (`a op b`) | 1 or 2 operations (e.g. `a * b` or `a * b + c`) | 2 or 3 operations (e.g. `(a + b) * c` or `a * b - c / d`) |
| **Max Expression Length** | 20 characters | 35 characters | 50 characters |
| **Max AST Depth** | 2 | 3 | 4 |
| **Max AST Node Count** | 3 nodes | 7 nodes | 15 nodes |
| **Operand Bounds** | `[1, 15]` (subtraction: `a >= b`) | `[2, 25]` (mult clamped to `[2, 12]`, div dividend max 144) | `[2, 50]` (mult clamped to `[2, 15]`, div dividend max 225) |
| **Max Operand Absolute Value** | 15 | 144 (for division dividend; 25 otherwise) | 225 (for division dividend; 50 otherwise) |
| **Max Intermediate Result (abs)** | **30** | **200** | **1000** |
| **Final Result Bounds** | Integer in `[0, 30]` | Integer in `[0, 150]` | Integer in `[-50, 500]` |
| **Division Rules** | Not allowed | Divisor `[2, 12]`, exact integer quotient | Divisor `[2, 15]`, exact integer quotient at every division step |
| **Default Question Count** | 3 questions (min 1, max 3) | 4 questions (min 2, max 4) | 5 questions (min 2, max 6) |
| **Default Time Limit** | 20 seconds | 35 seconds | 50 seconds |
| **Allow Parentheses** | False | False | True |

---

## 5. Structured Output Contracts

### 5.1 MathQuestionItem Schema
```json
{
  "question_id": 1,
  "question": "What is 14 × 4?",
  "expression": "14 * 4",
  "operation": "multiplication",
  "operands": [14, 4],
  "proposed_answer": 56
}
```

### 5.2 MathChallengePayload Schema
```json
{
  "question_count": 2,
  "questions": [
    {
      "question_id": 1,
      "question": "What is 14 × 4?",
      "expression": "14 * 4",
      "operation": "multiplication",
      "operands": [14, 4],
      "proposed_answer": 56
    },
    {
      "question_id": 2,
      "question": "What is 72 ÷ 8?",
      "expression": "72 / 8",
      "operation": "division",
      "operands": [72, 8],
      "proposed_answer": 9
    }
  ],
  "time_limit_seconds": 35
}
```

---

## 6. Zero-Trust Answer Validation Architecture

### 6.1 SafeArithmeticEvaluator
The evaluator eliminates code injection and dynamic execution by adhering to strict constraints:
1. **Zero Execution Functions:** `eval()`, `exec()`, `compile()`, dynamic `__import__`, and subprocess calls are strictly banned.
2. **Pure AST Whitelist:**
   - Container: `ast.Expression`
   - Operations: `ast.BinOp`, `ast.UnaryOp`
   - Allowed Operators: `ast.Add`, `ast.Sub`, `ast.Mult`, `ast.Div`, `ast.FloorDiv`, `ast.UAdd`, `ast.USub`
   - Literals: `ast.Constant` (strictly `int`, excluding `bool`, `float`, and `str`)
3. **Explicit Node Rejection:** All other AST node types (`ast.Call`, `ast.Name`, `ast.Attribute`, `ast.Pow`, `ast.Mod`, `ast.BitOr`, `ast.BitAnd`, `ast.Lambda`, etc.) trigger immediate rejection.

### 6.2 Sequential Verification Pipeline
```
GenAI structured operands
       ↓
1. Validate supplied operands (count, type, bounds)
       ↓
2. Parse expression with restricted AST (check length, depth, node count)
       ↓
3. Extract expression constants in expression order
       ↓
4. Compare expression constants with supplied operands (rejects [17, 6] vs "17 * 5")
       ↓
5. Validate declared operation against AST operators and tier constraints
       ↓
6. Safely compute result, checking intermediate bounds at EVERY step
       ↓
7. Enforce exact integer division (divisor != 0, dividend % divisor == 0)
       ↓
8. Validate final result bounds ([min_result, max_result])
       ↓
9. Sanity check question text numeric tokens (if present, match operands)
       ↓
10. Validate LLM proposed_answer (if present, must match computed result)
```

### 6.3 Resource & Numerical Safety
To prevent resource exhaustion from large integer operations (even without disallowed operators), limits are enforced **during** calculation:
- `abs(intermediate_result) <= max_intermediate_abs` checked after each node evaluation.
- `len(expression) <= max_expression_length` checked before AST parsing.
- `ast_depth <= max_ast_depth` and `node_count <= max_ast_node_count` checked before evaluation.

---

## 7. Question-Text Sanity Checking

Question text is treated solely as a **user-facing presentation layer**, not as an authoritative mathematical specification:
- Using `re.findall(r'\b\d+\b', question)`, numeric tokens are extracted.
- **If numbers are found:** They must match `supplied_operands`. For instance, `"What is 17 × 6?"` with operands `[17, 5]` is rejected.
- **If numbers are absent:** (e.g., `"Evaluate the arithmetic equation:"`), the challenge is **not** rejected.
- Natural-language parsing of arbitrary word problems is intentionally avoided in Phase 4.2.

---

## 8. Exception Hierarchy

Provider failures are clearly separated from mathematical validation failures, allowing future Phase 4.6 fallback handling to respond appropriately:

```
SmartWakeException
└── GenAIError
    ├── GenAIConfigurationError
    ├── GenAIProviderUnavailableError
    ├── GenAITimeoutError
    ├── GenAIRateLimitError
    ├── GenAIValidationError
    │   └── ChallengeContentValidationError
    │       └── MathEvaluationError  (Arithmetic bounds, div/0, operand mismatch, AST limits)
    │
    └── MathChallengeGenerationError  (Pipeline coordination, prompt construction, dispatch failure)
```

- **`MathEvaluationError`:** Raised when generated math violates arithmetic rules, operand consistency, intermediate bounds, or exact division.
- **`MathChallengeGenerationError`:** Raised for provider dispatch or internal coordination faults.

---

## 9. Personalization Integration

`MathPromptBuilder` consumes `SafePersonalizationContext`:
- **`desired_duration_seconds`:** Calibrates `target_question_count` within difficulty bounds (e.g. `<= 15s` selects minimum questions; `>= 45s` selects maximum questions). It **never alters the authoritative difficulty tier**.
- **`preferred_theme`:** Contextualizes problem presentation.
- **`language`:** Sets presentation language (default `"en"`).
- **Identity Privacy Guarantee:** `user_id`, `email`, `name`, `phone`, `session_id`, and `alarm_id` are strictly forbidden and never sent to providers.

---

## 10. Future Phase 4.7 Runtime Adapter Roadmap

In Phase 4.2:
- Output: `ValidatedChallengeContent(challenge_type="math", content_payload={...}, expected_answer=...)`.

In Phase 4.7:
- An adapter will translate:
  `ValidatedChallengeContent.content_payload` → adapter → `RuntimeChallengeResponse.generated_content`.
- The existing runtime generator (`_generate_math`) and `RuntimeChallengeResponse` remain unmodified.

---

## 11. Security Considerations & Known Limitations

1. **Zero Dynamic Code Execution:** All expressions are evaluated via AST walking. No `eval` or `exec` is present in the codebase.
2. **Denial of Service Prevention:** AST depth, node count, string length, and intermediate calculation sizes are strictly bounded.
3. **Zero PII Exposure:** Context sanitization guarantees no database identity reaches GenAI models.
4. **Known Limitation:** Word problems with embedded English numbers (e.g., "seventeen plus six") are not parsed for numeric tokens by the regex check; the structured operands remain the authoritative representation.
