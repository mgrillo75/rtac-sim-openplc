# Pull Request Review Checklist

This document standardizes the review process for OpenPLC Runtime pull requests. Use this checklist to ensure code quality, prevent technical debt, and avoid runtime errors.

## Quick Checklist

Before approving any PR, verify:

- [ ] Pre-commit hooks pass (`pre-commit run --all-files`)
- [ ] All tests pass (`pytest tests/`)
- [ ] No compiler warnings with strict flags
- [ ] Memory management is correct (no leaks)
- [ ] Thread safety verified (mutex usage correct)
- [ ] Security considerations addressed
- [ ] Platform compatibility maintained

---

## 1. Code Style and Formatting

### C/C++ Code
- [ ] 4-space indentation, no tabs
- [ ] 100-character line limit
- [ ] `snake_case` for functions and variables
- [ ] `snake_case_t` for type definitions
- [ ] `UPPER_CASE` for macros and constants
- [ ] Allman brace style for functions
- [ ] Clang-Format validates: `clang-format --style=file --dry-run -Werror *.c *.h`

### Python Code
- [ ] Black formatter passes
- [ ] isort import ordering correct
- [ ] Ruff linter passes
- [ ] Type hints on function signatures
- [ ] 100-character line limit
- [ ] Double quotes for strings

### General
- [ ] No emojis in code, comments, or documentation
- [ ] No trailing whitespace
- [ ] Files end with newline
- [ ] No files larger than 500KB

---

## 2. Architecture and Design

### Dual-Process Architecture
- [ ] Changes respect process boundaries (Python REST API vs C/C++ Runtime)
- [ ] IPC protocol compatibility maintained (`/run/runtime/plc_runtime.socket`)
- [ ] Socket message format unchanged or versioned properly
- [ ] Log socket protocol compatible (`/run/runtime/log_runtime.socket`)

### State Machine Integrity
```
EMPTY -> INIT -> RUNNING <-> STOPPED -> ERROR
```
- [ ] State transitions are atomic (mutex held)
- [ ] No invalid state transitions introduced
- [ ] State changes logged appropriately
- [ ] Error states handled with recovery path

### Plugin System
- [ ] Plugin interface contract maintained (`init`, `start_loop`, `stop_loop`, `cycle_start`, `cycle_end`, `cleanup`)
- [ ] `plugins.conf` format compatible
- [ ] Dynamic loading error handling present (`dlopen`/`dlsym` checks)
- [ ] Plugin cleanup called on errors
- [ ] No resource leaks when plugins fail to load

---

## 3. Memory Management

### C/C++ Memory
- [ ] Every `malloc()`/`calloc()` has corresponding `free()`
- [ ] Memory freed in error paths (early returns)
- [ ] Pointers set to `NULL` after `free()`
- [ ] `calloc()` preferred over `malloc()` (zeroed memory)
- [ ] No buffer overflows: `strncpy()`, `snprintf()` used with correct sizes
- [ ] String buffers null-terminated after `strncpy()`

### Dynamic Loading
- [ ] `dlopen()` result checked for NULL
- [ ] `dlsym()` errors handled
- [ ] `dlclose()` called on cleanup
- [ ] Error messages include `dlerror()`

### Python Memory
- [ ] Context managers (`with`) used for files/sockets
- [ ] Large buffers explicitly cleaned up
- [ ] No circular references preventing GC
- [ ] Thread-safe data structures where needed

---

## 4. Thread Safety and Concurrency

### Mutex Usage
- [ ] Lock/unlock pairs are symmetric (no double-lock)
- [ ] No potential deadlocks (consistent lock ordering)
- [ ] Priority inheritance used for real-time mutexes on Linux
- [ ] Graceful fallback for non-Linux platforms

### Critical Sections
- [ ] `state_mutex` held during PLC state changes
- [ ] `buffer_mutex` held during image table access
- [ ] Minimal time spent holding locks
- [ ] No blocking operations while holding mutex

### Thread Lifecycle
- [ ] Threads properly joined on shutdown
- [ ] No thread leaks (count remains deterministic)
- [ ] Thread-local storage cleaned up
- [ ] Signal handlers are async-signal-safe

### Real-Time Considerations (Linux)
- [ ] `SCHED_FIFO` scheduling preserved for PLC thread
- [ ] `mlockall()` called to prevent page faults
- [ ] No dynamic memory allocation in scan cycle
- [ ] Deterministic timing maintained

---

## 5. Error Handling

### C Error Patterns
- [ ] Return codes checked (0 = success, -1 = failure)
- [ ] `log_error()` called with context on failures
- [ ] No uninitialized variables
- [ ] All heap allocations checked for NULL
- [ ] Error paths clean up resources

### Python Error Patterns
- [ ] Specific exceptions caught (not bare `except:`)
- [ ] Exceptions logged with context: `logger.error("msg", exc_info=True)`
- [ ] JSON parsing uses `json.JSONDecodeError`
- [ ] Socket errors caught: `socket.error`, `OSError`
- [ ] No swallowing exceptions without logging

### Graceful Degradation
- [ ] Platform-specific features have fallbacks
- [ ] Missing optional dependencies handled
- [ ] Network timeouts don't crash the system
- [ ] Plugin failures don't crash the runtime

---

## 6. Security

### Input Validation
- [ ] All user input validated before use
- [ ] Buffer bounds checked before access
- [ ] Socket commands validated against whitelist
- [ ] Debug frame sizes checked: `MAX_DEBUG_FRAME - 7`
- [ ] Variable indices bounds-checked

### File Operations
- [ ] Path traversal prevented (validate against base directory)
- [ ] Disallowed extensions rejected: `.exe`, `.dll`, `.sh`, `.bat`, `.js`, `.vbs`, `.scr`
- [ ] ZIP extraction uses `safe_extract()`
- [ ] Compression ratio checked (zip bomb prevention)
- [ ] File size limits enforced (10MB per file, 50MB total)

### Authentication
- [ ] Protected endpoints use `@jwt_required()`
- [ ] Token expiration handled
- [ ] Tokens blacklisted on logout
- [ ] No secrets in version control

### Password Handling
- [ ] PBKDF2-SHA256 with 600,000 iterations
- [ ] Cryptographic pepper applied
- [ ] Passwords never logged
- [ ] Constant-time comparison used

### Network Security
- [ ] Hostname validation prevents injection
- [ ] IP addresses parsed via standard library
- [ ] TLS certificates validated (or self-signed with warning)
- [ ] Socket permissions restrict access

### Plugin Security
- [ ] Plugins use journal API (not direct buffer access)
- [ ] Plugin configuration validated
- [ ] No arbitrary code execution paths

---

## 7. Performance

### Scan Cycle
- [ ] No regressions in cycle timing (~50ms default)
- [ ] No blocking I/O in scan cycle thread
- [ ] Journal buffer entries within limit (1024 max)
- [ ] Mutex contention minimized

### Memory
- [ ] No unnecessary allocations in hot paths
- [ ] Buffer sizes appropriate
- [ ] Circular log buffer size reasonable (2MB)

### Network
- [ ] Socket timeouts appropriate (1.0s default)
- [ ] WebSocket debug overhead acceptable
- [ ] No busy-waiting loops

---

## 8. Testing

### Test Coverage
- [ ] New features have tests
- [ ] Bug fixes include regression tests
- [ ] Edge cases tested
- [ ] Error paths tested

### Test Quality
- [ ] Tests use proper mocking (`@patch`)
- [ ] Fixtures clean up state (`reset_globals()`)
- [ ] No test interdependencies
- [ ] Tests are deterministic

### Running Tests
```bash
sudo bash scripts/setup-tests-env.sh
pytest tests/
```

---

## 9. Build System

### CMake
- [ ] New source files added to `CMakeLists.txt`
- [ ] Include paths correct
- [ ] Link dependencies specified
- [ ] Compiles without warnings: `-Wall -Werror -Wextra`

### Compiler Flags
Required flags preserved:
```
-Wall -Werror -Wextra -fstack-protector-strong
-D_FORTIFY_SOURCE=2 -O2 -Werror=format-security -fPIC -fPIE
```

### CI/CD
- [ ] GitHub workflows pass
- [ ] Docker image builds for all platforms (amd64, arm64, arm/v7)
- [ ] Pre-commit hooks configured

---

## 10. Platform Compatibility

### Linux (Full Support)
- [ ] Real-time scheduling works (`SCHED_FIFO`)
- [ ] Memory locking works (`mlockall`)
- [ ] Priority inheritance enabled

### Windows/Cygwin/MSYS2 (Graceful Fallback)
- [ ] Compiles without real-time features
- [ ] Warning suppression for Python header conflicts
- [ ] No priority inheritance (falls back to regular mutex)

### Docker
- [ ] Capabilities documented: `--cap-add=SYS_NICE --cap-add=SYS_RESOURCE`
- [ ] Multi-arch build works

### ARM (arm64, arm/v7)
- [ ] Cross-compilation works
- [ ] No x86-specific code

---

## 11. Documentation

### Code Documentation
- [ ] Complex logic has comments explaining "why"
- [ ] Public APIs have docstrings
- [ ] Magic numbers explained or named

### Project Documentation
- [ ] `CLAUDE.md` updated if architecture changes
- [ ] `README.md` updated for user-facing changes
- [ ] API changes documented

---

## 12. Backward Compatibility

### Protocol Compatibility
- [ ] Unix socket command protocol unchanged
- [ ] WebSocket debug protocol unchanged
- [ ] REST API endpoints backward compatible

### Configuration
- [ ] `plugins.conf` format unchanged
- [ ] Environment variables unchanged
- [ ] Database schema migrations provided if needed

### Plugin API
- [ ] Plugin function signatures unchanged
- [ ] Image table access patterns unchanged
- [ ] Journal API unchanged

---

## Review Categories by Change Type

### Bug Fixes
Focus on:
- Root cause identified
- Fix addresses root cause (not symptoms)
- Regression test added
- No side effects introduced

### New Features
Focus on:
- Architecture fits existing patterns
- Error handling comprehensive
- Tests cover happy path and edge cases
- Documentation updated

### Refactoring
Focus on:
- Behavior unchanged (tests pass)
- No performance regression
- Code cleaner/more maintainable
- No unnecessary changes bundled

### Security Fixes
Focus on:
- Vulnerability fully addressed
- No new attack vectors
- Regression test prevents reintroduction
- Coordinated disclosure if needed

### Performance Improvements
Focus on:
- Benchmark results provided
- No correctness regressions
- Edge cases still handled
- Memory usage acceptable

---

## Common Issues to Watch For

### Memory Leaks
```c
// BAD: Leak on error
char *buf = malloc(size);
if (condition) {
    return -1;  // buf leaked
}

// GOOD: Free before return
char *buf = malloc(size);
if (condition) {
    free(buf);
    return -1;
}
```

### Race Conditions
```c
// BAD: Check-then-act race
if (state == RUNNING) {
    // Another thread could change state here
    do_something();
}

// GOOD: Hold mutex
pthread_mutex_lock(&state_mutex);
if (state == RUNNING) {
    do_something();
}
pthread_mutex_unlock(&state_mutex);
```

### Buffer Overflows
```c
// BAD: No bounds check
strcpy(dest, src);

// GOOD: Bounded copy
strncpy(dest, src, sizeof(dest) - 1);
dest[sizeof(dest) - 1] = '\0';
```

### Exception Swallowing
```python
# BAD: Silent failure
try:
    do_something()
except Exception:
    pass

# GOOD: Log the error
try:
    do_something()
except SpecificError as e:
    logger.error("Operation failed: %s", e)
    raise
```

### Path Traversal
```python
# BAD: Trusts user input
path = os.path.join(base_dir, user_input)

# GOOD: Validate path
path = os.path.join(base_dir, user_input)
if not os.path.realpath(path).startswith(os.path.realpath(base_dir)):
    raise ValueError("Invalid path")
```

---

## Technical Debt Indicators

Watch for these patterns that indicate growing technical debt:

1. **Copy-pasted code** - Should be refactored to shared function
2. **Magic numbers** - Should be named constants
3. **TODO/FIXME comments** - Should have associated issues
4. **Disabled tests** - Should be fixed or removed
5. **Suppressed warnings** - Should be investigated
6. **Platform-specific #ifdefs proliferating** - Consider abstraction layer
7. **Growing function length** - Should be split
8. **Deep nesting** - Should be flattened
9. **Tight coupling** - Should use interfaces/callbacks
10. **Missing error handling** - Should be added

---

## File Reference

| Component | Location |
|-----------|----------|
| PLC Runtime Core | `core/src/plc_app/` |
| REST API Server | `webserver/` |
| Plugin System | `core/src/drivers/` |
| Build Configuration | `CMakeLists.txt` |
| Code Style (C) | `.clang-format` |
| Code Style (Python) | `pyproject.toml` |
| Pre-commit Config | `.pre-commit-config.yaml` |
| Tests | `tests/pytest/` |
| Documentation | `docs/` |
| CI/CD Workflows | `.github/workflows/` |

---

## Post-Review Actions

After completing the review, always communicate findings directly on the PR.

### Step 1: Create Review Document

Save detailed review to `docs/pr-reviews/PR_<NUMBER>_REVIEW.md`:

```markdown
# PR #<NUMBER> Review: <PR Title>

**Reviewer:** <Name>
**Date:** <YYYY-MM-DD>
**Author:** @<username>

## Summary
<Brief description of what the PR does>

## Quick Checklist
| Check | Status | Notes |
|-------|--------|-------|
| Pre-commit hooks pass | :white_check_mark: / :x: | ... |
...

## Issues Found
### Critical
### Major
### Minor

## Final Assessment
:white_check_mark: **APPROVE** / :x: **REQUEST CHANGES**
```

### Step 2: Post Summary Comment on PR

Add an overall review comment:

```bash
gh pr review <PR_NUMBER> --comment --body "## PR Review Summary

<Assessment summary>

**Overall:** :white_check_mark: **APPROVED** / :x: **CHANGES REQUESTED**

See full review: \`docs/pr-reviews/PR_<NUMBER>_REVIEW.md\`"
```

### Step 3: Post Issues as PR Comment

**Always** add a separate comment listing all issues found with file locations and suggestions:

```bash
gh pr comment <PR_NUMBER> --body "### Issues Found (<Severity>)

---

**1. <Issue Title>**
- **File:** \`path/to/file.py:<line>\`
- **Issue:** <Description>
- **Suggestion:**
\`\`\`python
<code suggestion>
\`\`\`

---

**2. <Issue Title>**
...

---

Full review: \`docs/pr-reviews/PR_<NUMBER>_REVIEW.md\`"
```

### Comment Format Guidelines

1. **Be specific**: Always include file path and line number
2. **Be constructive**: Provide code suggestions when possible
3. **Categorize severity**: Critical, Major, Minor, or Suggestion
4. **Indicate blocking status**: Clearly state if issues block merge
5. **Reference documentation**: Link to the full review document

### Example Comment Structure

```markdown
### Minor Issues Found (Non-blocking)

These are suggestions for future improvement - not blocking merge.

---

**1. Duplicate constant definition**
- **File:** `core/src/module.py:22`
- **Issue:** `CONSTANT` is also defined in `other_module.py:54`
- **Suggestion:** Import from a single location:
\`\`\`python
from .other_module import CONSTANT
\`\`\`

---

**2. Type hint could be more precise**
- **File:** `core/src/utils.py:199`
- **Function:** `some_function`
- **Suggestion:** Use `tuple[int, int]` instead of `tuple`:
\`\`\`python
def some_function(arg: int) -> tuple[int, int]:
\`\`\`

---

Full review: `docs/pr-reviews/PR_123_REVIEW.md`
```

### Why Post Comments on PR?

1. **Visibility**: Authors see feedback immediately in GitHub notifications
2. **Traceability**: Comments are linked to the PR permanently
3. **Discussion**: Authors can reply and discuss specific issues
4. **History**: Future reviewers can see past feedback patterns
5. **Accountability**: Clear record of what was reviewed and approved
