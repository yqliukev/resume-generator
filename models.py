from dataclasses import dataclass, field


@dataclass
class Entry:
    ''' Entry within a section, e.g. "Backend Developer @ Ground News". '''
    display_label: str   # clean text for UI tree (e.g. "Backend Dev @ Ground News")
    raw_text: str        # verbatim source lines, preserved for output
    selected: bool = True


@dataclass
class Section:
    ''' Document section, e.g. "Work Experience". '''
    name: str            # e.g. "Work Experience"
    section_type: str    # "standard" | "skills"
    raw_header: str      # "\section{...}" line verbatim (may include preceding comment)
    list_prefix: str     # lines between header and first entry
    list_suffix: str     # lines after last entry (before next section)
    entries: list = field(default_factory=list)
    selected: bool = True


@dataclass
class ResumeDocument:
    preamble: str           # everything up to (not including) \begin{center}
    header: str             # \begin{center}...\end{center} block (inclusive)
    sections: list = field(default_factory=list)
    trailing: str = ""      # \end{document} and any trailing content
