# VARION — Known Issues & Fixes

## 2026-04-21 · `agent/report.py` SyntaxError on Python 3.13

### Symptom
Running `.\drift.bat eval` crashes at import time:

```
File "agent/report.py", line 213
    f"{'N/A' if c['prev'] is None else f'{c[\"prev\"]:.4f}'}</td>"
                                             ^
SyntaxError: unexpected character after line continuation character
```

### Root cause
The `metric_rows` join used **nested f-strings with backslash-escaped quotes**, e.g.
`f'{c[\"prev\"]:.4f}'` inside an outer f-string.

- This pattern was proposed for PEP 701 (Python 3.12+ formal f-string grammar).
- CPython's tokenizer still rejects backslashes inside f-string expression parts across **3.12 / 3.13 / 3.14**. It parses as a string continuation, producing the misleading `line continuation character` error.

### Fix
Replaced the inline comprehension inside `"".join(...)` with an explicit helper `_fmt_row(c)` that precomputes `prev_s`, `curr_s`, `delta_s`, and `dcolor` as plain variables, then interpolates them in a flat f-string — no nested quotes, no backslashes inside expressions.

**File:** `agent/report.py` (around line 210)

### Quick verification
```powershell
python -c "import ast; ast.parse(open('agent/report.py').read()); print('OK')"
```

### Takeaway
Do **not** use `\"` inside an f-string expression part. Either:
- Use single quotes inside the expression (`c['prev']`), OR
- Precompute the formatted value in a regular assignment before the f-string.

---

## 2026-04-21 · `agent/report.py` TypeError: `len()` on `NoneType`

### Symptom
After eval completes, report generation crashes:

```
File "agent/report.py", line 112, in _metric_section
    short = (reason[:120] + "…") if len(reason) > 120 else reason
TypeError: object of type 'NoneType' has no len()
```

### Root cause
`cc.get("reason", "")` returns the default `""` only when the key is missing.
If the Copilot Studio Eval API returns `{"reason": null}` (JSON null → Python `None`), `dict.get` returns `None`, and `len(None)` fails.

### Fix
Changed `cc.get("reason", "")` to `cc.get("reason") or ""` in `agent/report.py` line 98 — coalesces both missing-key and explicit-null to empty string.

### Takeaway
When the backend may send `null` for optional fields, use `(d.get(k) or default)` instead of `d.get(k, default)`.

