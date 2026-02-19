# Resume Generator — Implementation Plan

## Overview
Python desktop GUI application that parses a LaTeX resume file, lets the user select/deselect sections and individual entries, and generates a new `.tex` file + compiled PDF.

**Stack:** Python 3, `customtkinter`, stdlib `re` + `subprocess` only. No heavy LaTeX libs needed.

---

## File Structure

```
resume_generator/
├── main.py        # Entry point
├── models.py      # Dataclasses
├── parser.py      # LaTeX parser
├── assembler.py   # Output builder + pdflatex runner
└── app.py         # customtkinter UI
```

---

## Data Model (`models.py`)

```python
@dataclass
class Entry:
    display_label: str   # clean text for UI tree (e.g. "Backend Dev @ Ground News")
    raw_text: str        # verbatim source lines, preserved for output
    selected: bool = True

@dataclass
class Section:
    name: str            # e.g. "Work Experience"
    section_type: str    # "standard" | "skills"
    raw_header: str      # "\section{...}" line verbatim
    list_prefix: str     # lines between header and first entry
    list_suffix: str     # lines after last entry (before next section)
    entries: list[Entry]
    selected: bool = True

@dataclass
class ResumeDocument:
    preamble: str        # everything up to and including \begin{document}
    header: str          # \begin{center}...\end{center} block
    sections: list[Section]
    trailing: str        # "\end{document}" and any trailing comments
```

**Key design:** `raw_text` on every `Entry` means the assembler concatenates verbatim strings — no LaTeX re-serialization.

---

## Parsing Strategy (`parser.py`)

### Phase 1 — Zone extraction (line-by-line state machine)
| Zone | Start trigger | End trigger |
|------|--------------|-------------|
| `PREAMBLE` | line 1 | line containing `\begin{center}` |
| `HEADER` | `\begin{center}` | line containing `\end{center}` |
| `BODY` | after header | `\end{document}` → goes to `trailing` |

### Phase 2 — Section splitting
Detect `re.search(r'\\section\*?\{', line)` to start a new section. Extract name via `re.search(r'\\section\*?\{([^}]+)\}', line).group(1)`.

### Phase 3 — Entry extraction per section

**Detect type:**
```python
section_type = "standard" if r"\resumeSubHeadingListStart" in section_lines else "skills"
```

**Standard sections (Work Experience, Projects, Education):**
- Entry triggers: lines matching `\resumeSubheading` or `\resumeProjectHeading`
- After trigger, use **brace-group collector** to extract N balanced `{...}` groups across lines (4 for `\resumeSubheading`, 2 for `\resumeProjectHeading`)
- Continue accumulating until matching `\resumeItemListEnd` is found
- Comment lines (`% Ground News`) immediately before a trigger are prepended to `Entry.raw_text`

**Skills section:**
- Entry region: lines between `\resumeItemListStart` and `\resumeItemListEnd`
- Each line matching `\resumeItem{` is one `Entry`; brace-counting handles multi-line items

**Brace-group collector** (handles nested braces like `\textbf{...}` inside args):
```python
def collect_brace_groups(lines, start_line, start_col, n):
    # count { and } depth, collect n top-level groups, may span lines
    ...
```

**`strip_latex` helper** for display labels:
```python
def strip_latex(s):
    s = re.sub(r'\\textbf\{([^}]*)\}', r'\1', s)
    s = re.sub(r'\\textit\{([^}]*)\}', r'\1', s)
    s = re.sub(r'\\href\{[^}]*\}\{([^}]*)\}', r'\1', s)
    s = re.sub(r'\\underline\{([^}]*)\}', r'\1', s)
    return s.strip()
```

Display labels:
- `\resumeSubheading` → `"{title} @ {org}"`
- `\resumeProjectHeading` → `"{project name}"`
- `\resumeItem` (skills) → first ~60 chars of item content

**Structural notes from the actual file:**
- `\resumeSubheading` args span 2 lines after the command (lines 134-136)
- `\resumeProjectHeading` args are on the line after the command (lines 220-221)
- `\setlength\itemsep{...}` appears inside bullet blocks — captured as part of `Entry.raw_text`, never parsed separately
- Skills section has no `\resumeSubHeadingListStart`; uses `\resumeItemListStart` directly
- Trailing `%--------Extra Skills--------` comment absorbed into `doc.trailing`

---

## Output Assembly (`assembler.py`)

```python
def assemble(doc: ResumeDocument) -> str:
    parts = [doc.preamble, doc.header]
    for section in doc.sections:
        if not section.selected:
            continue
        selected = [e for e in section.entries if e.selected]
        parts.append(section.raw_header)
        if selected:
            parts.append(section.list_prefix)
            for entry in selected:
                parts.append(entry.raw_text)
            parts.append(section.list_suffix)
    parts.append(doc.trailing)
    return "".join(parts)
```

**PDF compilation:**
```python
def compile_pdf(tex_path, output_dir) -> tuple[bool, str]:
    # Run pdflatex -interaction=nonstopmode twice (for cross-refs)
    # Returns (success, log_output)
    # Raises FileNotFoundError if pdflatex not on PATH
```

---

## UI Layout (`app.py`)

```
┌─────────────────────────────────────────────────────┐
│ [Open File]  /path/to/resume.tex                    │  ← top bar
├──────────────────────────┬──────────────────────────┤
│ SECTIONS TREE (scrollable│  STATS / PREVIEW         │
│                          │  "12 of 15 entries"      │
│ [x] Work Experience      │                          │
│   [x] Backend Dev @...   │  (list of selected       │
│   [x] Software Dev @...  │   entry labels)          │
│   [ ] Backend Dev @...   │                          │
│                          │                          │
│ [x] Projects             │                          │
│   [x] Image Recog...     │                          │
│   [ ] VGG11...           │                          │
│                          │                          │
│ [x] Skills Portfolio     │                          │
│   [x] Development: ...   │                          │
│   [x] Cloud: ...         │                          │
├──────────────────────────┴──────────────────────────┤
│ Output: [/path/to/output.tex     ] [Browse]         │
│ [x] Compile to PDF   [     Generate     ]           │
│ Status: Ready                                       │
└─────────────────────────────────────────────────────┘
```

**State:** `BooleanVar` per section and per entry, stored in dicts keyed by `(section_idx)` and `(section_idx, entry_idx)`.

**Key event handlers:**
| Event | Behavior |
|-------|----------|
| Open File | `filedialog.askopenfilename` → `parse_file()` → `build_tree()` |
| Section checkbox | Sets all child entry vars to match |
| Entry checkbox | If partially selected, section label dims; if all selected, section checks |
| Browse output | `filedialog.asksaveasfilename(defaultextension=".tex")` |
| Generate | Sync vars → model → `assemble()` → `write_tex()` → optionally `compile_pdf()` in background thread |

**Threading:** `compile_pdf()` runs in `threading.Thread`; result posted back via `app.after(0, callback)`. Generate button disabled during compilation.

---

## `main.py`

```python
import customtkinter as ctk
from app import App

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")
App().mainloop()
```

---

## Edge Cases

| Case | Handling |
|------|----------|
| Args spanning multiple lines | Brace-group collector spans as many lines as needed |
| `\setlength\itemsep` in bullet block | Captured verbatim inside `Entry.raw_text` |
| `pdflatex` not on PATH | Caught `FileNotFoundError`, shown in status label |
| `pdflatex` error | Non-zero returncode → show last 10 log lines in popup |
| All entries in section deselected | Section header still emitted; empty list wrapper prevents LaTeX errors |
| CRLF line endings | `splitlines(keepends=True)` handles both |
| Re-opening a new file | `build_tree()` fully clears and rebuilds; old `doc` replaced |

---

## Verification

1. `pip install customtkinter`
2. Run `python main.py`
3. Open `Winter 2026.tex` via the UI
4. Verify 4 sections appear: Skills Portfolio, Work Experience, Projects and Extracurriculars, Education
5. Verify all entries parse correctly (5 jobs, 6 projects, 1 education, 9 skills)
6. Deselect entries, click Generate, open output `.tex` — confirm omitted entries are absent
7. Enable "Compile to PDF", Generate — verify PDF opens/renders correctly
8. Test round-trip: select ALL entries → output should be functionally identical to source
