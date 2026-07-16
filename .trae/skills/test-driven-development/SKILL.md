---
name: "test-driven-development"
description: "Unified TDD skill with three input modes — from spec, from task, or from description. Enforces test-first development using repository patterns, with proptest guidance and backpressure integration. Invoke when user wants to practice test-driven development or write tests first."
---

# Test-Driven Development

## Overview

One skill for all TDD workflows. Enforces test-first development using existing repository patterns. Three input modes handle different entry points — specs, task files, or ad-hoc descriptions — but the core cycle is always RED → GREEN → REFACTOR.

## Input Modes

Detect the input type and follow the corresponding mode:

### Mode A: From Spec (`.spec.md`)

Use when the input references a `.spec.md` file with Given/When/Then acceptance criteria.

1. **Locate and parse** the spec file — extract all Given/When/Then triples

2. **Generate one test stub per criterion** with `todo!()` bodies:
```
/// Spec: <spec-file> — Criterion #<N>
/// Given <given text>
/// When <when text>
/// Then <then text>
#[test]
fn <spec_name>_criterion_<N>_<slug>() {
    todo!("Implement: <then text>");
}
```

3. **Verify stubs compile** but fail: `cargo test --no-run -p <crate>`

4. Proceed to the [TDD Cycle](#tdd-cycle) to make stubs pass

### Mode B: From Task (`.code-task.md`)

Use when the input references a `.code-task.md` file or a specific implementation task.

1. **Read the task** and identify acceptance criteria or requirements

2. **Discover patterns** (see [Pattern Discovery](#pattern-discovery))

3. **Design test scenarios** covering normal operation, edge cases, and error conditions

4. **Write failing tests** for all requirements before any implementation

5. Proceed to the [TDD Cycle](#tdd-cycle)

### Mode C: From Description

Use for ad-hoc tasks without a spec or task file.

1. **Clarify requirements** from the description

2. **Discover patterns** (see [Pattern Discovery](#pattern-discovery))

3. **Write failing tests** targeting the described behavior

4. Proceed to the [TDD Cycle](#tdd-cycle)

## Pattern Discovery

Before writing tests, discover existing conventions:

```bash
rg --files -g "crates/*/tests/*.rs"
rg -n "#\[cfg\(test\)\]" crates/
```

Read 2-3 relevant test files near the target code. Mirror:

- Test module layout, naming, and assertion style
- Fixture helpers and test utilities
- Use of `tempfile`, scenarios, or harnesses

## TDD Cycle

### 1) RED — Failing Tests

- Write tests for the exact behavior required
- Run tests to confirm failure **for the right reason**
- If tests pass without implementation, the test is wrong

### 2) GREEN — Minimal Implementation

- Write the minimum code to make tests pass
- No extra features or refactoring during this step

### 3) REFACTOR — Clean Up

- Improve implementation and tests while keeping tests green
- Align with surrounding codebase conventions
- Re-run tests after every change

## Proptest Guidance

Use `proptest` only when ALL of:

- Function is pure (no I/O, no time, no globals)
- Deterministic output for given input
- Non-trivial input space or edge cases

```rust
proptest! {
    #[test]
    fn round_trip(input in "[a-z0-9]{0,32}") {
        let encoded = encode(input.as_str());
        let decoded = decode(&encoded).expect("should decode");
        prop_assert_eq!(decoded, input);
    }
}
```

Don't introduce proptest as a new dependency without strong justification.

## Backpressure Integration

Include coverage evidence in completion events:

```bash
ralph emit "build.done" "tests: pass, lint: pass, typecheck: pass, audit: pass, coverage: pass (82%)"
```

Run `cargo tarpaulin --out Html --output-dir coverage --skip-clean` when feasible. If coverage cannot be run, state why and include targeted test evidence instead.

## Test Location Rules

- Spec maps to a single module → inline `#[cfg(test)]` tests
- Spec spans multiple modules → integration test in `crates/<crate>/tests/`
- CLI behavior → `crates/ralph-cli/tests/`
- Follow existing patterns in the target crate

## Anti-Patterns

- Writing implementation before tests
- Generating tests that pass without implementation
- Copying tests from other crates without adapting to local patterns
- Adding proptest when a simple example test suffices
- Emitting completion events without coverage evidence

## Workflow Examples

### New Feature with Spec

```bash
# 1. Read the spec file
# 2. Generate test stubs for each Given/When/Then criterion
# 3. Verify stubs fail (RED)
# 4. Implement minimum code (GREEN)
# 5. Refactor and clean up (REFACTOR)
# 6. Run full test suite
```

### Bug Fix

```bash
# 1. Write a failing test that reproduces the bug
# 2. Run test to confirm failure
# 3. Fix the implementation
# 4. Run test to confirm fix
# 5. Refactor if needed
```

### Ad-hoc Task

```bash
# 1. Clarify requirements from description
# 2. Identify test scenarios
# 3. Write failing tests
# 4. Implement
# 5. Verify all tests pass
```

## Key Principles

1. **Test-First**: Write tests before implementation
2. **Fail Fast**: Ensure tests fail before writing code
3. **Minimal Implementation**: Only write enough code to pass tests
4. **Continuous Refinement**: Keep improving while tests stay green
5. **Pattern Alignment**: Follow existing project conventions

## Benefits

- **Confidence**: Code is proven to work as expected
- **Design**: Tests drive cleaner, more modular design
- **Documentation**: Tests serve as living documentation
- **Refactoring**: Safety net for code improvements
- **Debugging**: Faster bug identification and resolution
