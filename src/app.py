import os
import tkinter
from tkinter import filedialog, messagebox

import customtkinter as ctk

from models import (
    SourceFile,
    LinkLibrary,
    merge_source_document,
    default_link_library_path
)
from parser import parse_file
from persistence_v2 import (
    load_link_library,
    save_link_library,
    update_library_source_file,
)


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Resume Generator")
        self.geometry("960x680")
        self.minsize(720, 520)

        self.doc = None
        self.file_path: str | None = None
        self.link_library = None
        self.library_path: str | None = None

        # State maps: keyed by section index / (section_idx, entry_idx)
        self.section_vars: dict[int, tkinter.IntVar] = {}
        self.entry_vars: dict[tuple, tkinter.IntVar] = {}
        self.version_vars: dict[tuple, tkinter.StringVar] = {}

        # Keep references so GC doesn't collect them
        self._section_cb_refs: list = []
        self._entry_cb_refs: list[list] = []
        self._version_radio_refs: list = []

        self._pending_warnings: list[str] = []

        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # ── Top bar ──────────────────────────────────────────────────
        top = ctk.CTkFrame(self, corner_radius=0)
        top.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))

        top.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(
            top, text="Upload File", width=150, command=self._choose_upload_target
        ).grid(row=0, column=0, padx=(8, 8), pady=6, sticky="w")

        self.refresh_btn = ctk.CTkButton(
            top, text="↻", width=42, command=self._refresh_source_file, state="disabled"
        )
        self.refresh_btn.grid(row=0, column=1, padx=(0, 8), pady=6, sticky="w")

        self.file_label = ctk.CTkLabel(top, text="Source: none", anchor="w")
        self.file_label.grid(row=1, column=0, columnspan=2, sticky="ew", padx=8, pady=(0, 2))

        self.library_label = ctk.CTkLabel(top, text="Library: none", anchor="w")
        self.library_label.grid(row=2, column=0, columnspan=2, sticky="ew", padx=8, pady=(0, 6))

        # ── Main content (left tree | right preview) ─────────────────
        content = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        content.grid(row=1, column=0, sticky="nsew", padx=8, pady=4)
        content.grid_columnconfigure(0, weight=55)
        content.grid_columnconfigure(1, weight=45)
        content.grid_rowconfigure(0, weight=1)

        # Left: scrollable section/entry tree
        self.tree_frame = ctk.CTkScrollableFrame(
            content, label_text="Sections & Entries", label_font=ctk.CTkFont(weight="bold")
        )
        self.tree_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        self.tree_frame.grid_columnconfigure(0, weight=1)

        # Right: stats + preview
        right = ctk.CTkFrame(content)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)

        self.stats_label = ctk.CTkLabel(
            right, text="Open a .tex file to begin",
            font=ctk.CTkFont(size=13, weight="bold"), anchor="w"
        )
        self.stats_label.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))

        self.preview_frame = ctk.CTkScrollableFrame(
            right, label_text="Selected entries", label_font=ctk.CTkFont(weight="bold")
        )
        self.preview_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self.preview_frame.grid_columnconfigure(0, weight=1)

        # ── Bottom bar ────────────────────────────────────────────────
        bottom = ctk.CTkFrame(self, corner_radius=0)
        bottom.grid(row=2, column=0, sticky="ew", padx=8, pady=(4, 8))
        bottom.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(bottom, text="Output folder:").grid(
            row=0, column=0, padx=(10, 6), pady=(8, 4), sticky="w"
        )
        self.output_dir_entry = ctk.CTkEntry(bottom, placeholder_text="/path/to/output/folder")
        self.output_dir_entry.grid(row=0, column=1, sticky="ew", padx=4, pady=(8, 4))
        ctk.CTkButton(bottom, text="Browse", width=90, command=self._browse_output_dir).grid(
            row=0, column=2, padx=(4, 10), pady=(8, 4)
        )

        ctk.CTkLabel(bottom, text="Output file name:").grid(
            row=1, column=0, padx=(10, 6), pady=4, sticky="w"
        )
        self.output_name_entry = ctk.CTkEntry(bottom, placeholder_text="generated.tex")
        self.output_name_entry.grid(row=1, column=1, sticky="ew", padx=4, pady=4)

        self.generate_pdf_var = tkinter.IntVar(value=0)
        ctk.CTkCheckBox(
            bottom,
            text="Generate PDF",
            variable=self.generate_pdf_var,
        ).grid(row=2, column=0, columnspan=2, padx=(10, 4), pady=(4, 0), sticky="w")

        self.update_links_btn = ctk.CTkButton(
            bottom, text="Update Links", width=120,
            command=self._update_links, state="disabled"
        )
        self.update_links_btn.grid(row=3, column=0, padx=(10, 4), pady=(8, 4), sticky="w")

        self.generate_btn = ctk.CTkButton(
            bottom, text="Generate", width=110,
            command=self._generate, state="disabled"
        )
        self.generate_btn.grid(row=3, column=1, padx=(4, 10), pady=(8, 4), sticky="w")

        self.status_label = ctk.CTkLabel(
            bottom, text="Status: Ready", anchor="w",
            font=ctk.CTkFont(size=12)
        )
        self.status_label.grid(
            row=4, column=0, columnspan=3, sticky="ew", padx=10, pady=(0, 8)
        )

    # ------------------------------------------------------------------
    # File open
    # ------------------------------------------------------------------

    def _choose_upload_target(self):
        popup = ctk.CTkToplevel(self)
        popup.title("Choose upload type")
        popup.geometry("360x170")
        popup.resizable(False, False)
        popup.transient(self)
        popup.grab_set()

        popup.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            popup,
            text="Choose File Type",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, padx=20, pady=(20, 10), sticky="w")

        button_row = ctk.CTkFrame(popup, fg_color="transparent")
        button_row.grid(row=1, column=0, padx=20, pady=(8, 8), sticky="ew")
        button_row.grid_columnconfigure(0, weight=1)
        button_row.grid_columnconfigure(1, weight=1)

        def choose_source():
            popup.destroy()
            self.after(0, self._open_source_file)

        def choose_library():
            popup.destroy()
            self.after(0, self._open_link_library)

        ctk.CTkButton(
            button_row,
            text="Source File",
            command=choose_source,
        ).grid(row=0, column=0, padx=(0, 8), sticky="ew")

        ctk.CTkButton(
            button_row,
            text="Link Library",
            command=choose_library,
        ).grid(row=0, column=1, padx=(8, 0), sticky="ew")

        ctk.CTkButton(
            popup,
            text="Cancel",
            width=90,
            command=popup.destroy,
        ).grid(row=2, column=0, padx=20, pady=(4, 16), sticky="e")

        popup.bind("<Escape>", lambda _event: popup.destroy())

    def _load_source_file(self, path: str, *, reset_output_fields: bool):
        self._set_status("Parsing source file…")
        try:
            parsed_source = parse_file(path)
        except Exception as exc:
            messagebox.showerror("Parse error", str(exc))
            self._set_status(f"Error: {exc}")
            return False

        self._pending_warnings = list(getattr(parsed_source, "parse_warnings", []))
        source_path = os.path.abspath(path)
        keep_library = self.link_library is not None and self.link_library.source_path == source_path
        if keep_library:
            self.doc = merge_source_document(parsed_source, self.link_library.source_file)
        else:
            self.doc = parsed_source
            self.link_library = None
            self.library_path = None

        self.file_path = source_path
        self.file_label.configure(text=f"Source: {source_path}")
        if keep_library and self.library_path:
            self.library_label.configure(text=f"Library: {self.library_path}")
        else:
            self.library_label.configure(text="Library: none")

        if reset_output_fields:
            self._set_default_output_fields(source_path)

        self._build_tree()
        self._set_controls_enabled(True)
        self.refresh_btn.configure(state="normal")
        return True

    def _open_source_file(self):
        path = filedialog.askopenfilename(
            title="Open LaTeX Source File",
            filetypes=[("LaTeX files", "*.tex"), ("All files", "*.*")],
        )
        if not path:
            return

        if not self._load_source_file(path, reset_output_fields=True):
            return
        self._announce_load("Source loaded")

    def _refresh_source_file(self):
        if not self.file_path:
            messagebox.showwarning("No source file", "Please upload a source file first.")
            return

        if not self._load_source_file(self.file_path, reset_output_fields=False):
            return

        self._announce_load("Source refreshed")

    def _open_link_library(self):
        path = filedialog.askopenfilename(
            title="Open Link Library",
            filetypes=[("Link libraries", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return

        self._set_status("Loading link library…")
        try:
            library = load_link_library(path)
        except Exception as exc:
            messagebox.showerror("Library error", str(exc))
            self._set_status(f"Error: {exc}")
            return

        source_path = library.source_path or library.source_file.path
        loaded_source: SourceFile | None = None
        self._pending_warnings = []
        if source_path and os.path.exists(source_path):
            try:
                parsed_source = parse_file(source_path)
                self._pending_warnings = list(getattr(parsed_source, "parse_warnings", []))
                loaded_source = merge_source_document(parsed_source, library.source_file)
            except Exception:
                loaded_source = None
                self._pending_warnings = []

        if loaded_source is None:
            loaded_source = SourceFile.from_dict(library.source_file.to_dict()) or library.source_file

        self.link_library = library
        self.library_path = os.path.abspath(path)
        self.doc = loaded_source
        if source_path:
            self.file_path = self.doc.path or os.path.abspath(source_path)
        else:
            self.file_path = self.doc.path or None

        if self.file_path:
            self.file_label.configure(text=f"Source: {self.file_path}")
        else:
            self.file_label.configure(text="Source: unavailable")
        self.library_label.configure(text=f"Library: {self.library_path}")

        self._set_default_output_fields(source_path)

        self._build_tree()
        self._set_controls_enabled(True)
        self._announce_load("Link library loaded")

    # ------------------------------------------------------------------
    # Tree building
    # ------------------------------------------------------------------

    def _build_tree(self):
        # Clear old widgets
        for widget in self.tree_frame.winfo_children():
            widget.destroy()
        self.section_vars.clear()
        self.entry_vars.clear()
        self.version_vars.clear()
        self._section_cb_refs.clear()
        self._entry_cb_refs.clear()
        self._version_radio_refs.clear()

        if not self.doc:
            return

        SECTION_FONT = ctk.CTkFont(size=13, weight="bold")
        ENTRY_FONT = ctk.CTkFont(size=12)
        VERSION_FONT = ctk.CTkFont(size=11)
        VERSION_COLOR = "#5AB0F0"  # distinct accent so versions read differently

        row = 0
        for si, section in enumerate(self.doc.sections):
            self._section_cb_refs.append(None)
            self._entry_cb_refs.append([])

            # Section row
            sec_var = tkinter.IntVar(value=1 if section.selected else 0)
            self.section_vars[si] = sec_var

            sec_cb = ctk.CTkCheckBox(
                self.tree_frame,
                text=section.name,
                variable=sec_var,
                font=SECTION_FONT,
                command=lambda i=si: self._on_section_toggle(i),
            )
            sec_cb.grid(
                row=row, column=0, sticky="w",
                padx=8, pady=(10 if si > 0 else 4, 2)
            )
            self._section_cb_refs[si] = sec_cb
            row += 1

            # Entry rows (indented)
            for ei, entry in enumerate(section.entries):
                entry_var = tkinter.IntVar(value=1 if entry.selected else 0)
                self.entry_vars[(si, ei)] = entry_var

                label = entry.display_label
                if len(label) > 52:
                    label = label[:50] + "…"

                ent_cb = ctk.CTkCheckBox(
                    self.tree_frame,
                    text=label,
                    variable=entry_var,
                    font=ENTRY_FONT,
                    command=lambda i=si, j=ei: self._on_entry_toggle(i, j),
                )
                ent_cb.grid(
                    row=row, column=0, sticky="w",
                    padx=(30, 8), pady=1
                )
                self._entry_cb_refs[si].append(ent_cb)
                row += 1

                # Version radios (only when an item has more than one version)
                if len(entry.versions) > 1:
                    version_var = tkinter.StringVar(
                        value=entry.resolve_active_version_id()
                    )
                    self.version_vars[(si, ei)] = version_var

                    for version in entry.versions:
                        radio_label = self._version_radio_label(entry, version)
                        radio = ctk.CTkRadioButton(
                            self.tree_frame,
                            text=radio_label,
                            variable=version_var,
                            value=version.version_id,
                            font=VERSION_FONT,
                            text_color=VERSION_COLOR,
                            radiobutton_width=16,
                            radiobutton_height=16,
                            command=lambda i=si, j=ei: self._on_version_change(i, j),
                        )
                        radio.grid(
                            row=row, column=0, sticky="w",
                            padx=(56, 8), pady=(0, 1)
                        )
                        self._version_radio_refs.append(radio)
                        row += 1

        self._update_preview()

    @staticmethod
    def _version_radio_label(entry, version) -> str:
        title = version.display_label
        if len(title) > 44:
            title = title[:42] + "…"
        if version.display_label and version.display_label != entry.display_label:
            return f"{version.version_id} — {title}"
        return version.version_id

    # ------------------------------------------------------------------
    # Checkbox event handlers
    # ------------------------------------------------------------------

    def _on_section_toggle(self, si: int):
        val = self.section_vars[si].get()
        # Cascade to all child entries
        n_entries = len(self.doc.sections[si].entries)
        for ei in range(n_entries):
            self.entry_vars[(si, ei)].set(val)
        self._update_preview()

    def _on_entry_toggle(self, si: int, _ei: int):
        n_entries = len(self.doc.sections[si].entries)
        selected_count = sum(
            self.entry_vars[(si, j)].get() for j in range(n_entries)
        )
        # Update section checkbox: checked if any entry is selected
        if selected_count == 0:
            self.section_vars[si].set(0)
        else:
            self.section_vars[si].set(1)
        self._update_preview()

    def _on_version_change(self, _si: int, _ei: int):
        # Choosing a version does not change include/exclude state.
        self._update_preview()

    # ------------------------------------------------------------------
    # Preview panel
    # ------------------------------------------------------------------

    def _update_preview(self):
        for w in self.preview_frame.winfo_children():
            w.destroy()

        if not self.doc:
            return

        total = 0
        selected = 0
        row = 0

        for si, section in enumerate(self.doc.sections):
            sec_selected = bool(self.section_vars.get(si, tkinter.IntVar()).get())
            entries = section.entries

            for ei, entry in enumerate(entries):
                total += 1
                entry_on = bool(self.entry_vars.get((si, ei), tkinter.IntVar()).get())
                if sec_selected and entry_on:
                    selected += 1
                    text = f"[{section.name}]  {entry.display_label[:55]}"
                    if len(entry.versions) > 1:
                        version_var = self.version_vars.get((si, ei))
                        active_id = (
                            version_var.get() if version_var is not None
                            else entry.resolve_active_version_id()
                        )
                        text += f"  [{active_id}]"
                    sec_label = ctk.CTkLabel(
                        self.preview_frame,
                        text=text,
                        anchor="w",
                        font=ctk.CTkFont(size=11),
                        wraplength=320,
                    )
                    sec_label.grid(row=row, column=0, sticky="ew", padx=6, pady=1)
                    row += 1

        self.stats_label.configure(
            text=f"{selected} of {total} entries selected"
        )

    # ------------------------------------------------------------------
    # Generate / update
    # ------------------------------------------------------------------

    def _set_controls_enabled(self, enabled: bool):
        state = "normal" if enabled else "disabled"
        self.refresh_btn.configure(state=state if self.file_path else "disabled")
        self.update_links_btn.configure(state=state)
        self.generate_btn.configure(state=state)

    def _set_default_output_fields(self, source_path: str | None):
        if source_path:
            source_dir = os.path.dirname(source_path)
            source_name = os.path.splitext(os.path.basename(source_path))[0]
        else:
            source_dir = os.getcwd()
            source_name = "generated"

        self.output_dir_entry.delete(0, "end")
        self.output_dir_entry.insert(0, source_dir)

        self.output_name_entry.delete(0, "end")
        self.output_name_entry.insert(0, f"{source_name}.tex")

    def _browse_output_dir(self):
        initial_dir = self.output_dir_entry.get().strip() or (
            os.path.dirname(self.file_path) if self.file_path else os.getcwd()
        )
        path = filedialog.askdirectory(
            title="Select output folder",
            initialdir=initial_dir,
        )
        if path:
            self.output_dir_entry.delete(0, "end")
            self.output_dir_entry.insert(0, path)

    def _sync_model(self):
        """Push UI checkbox states back into the document model."""
        if not self.doc:
            return
        for si, section in enumerate(self.doc.sections):
            section.selected = bool(self.section_vars.get(si, tkinter.IntVar(value=1)).get())
            for ei, entry in enumerate(section.entries):
                entry.selected = bool(
                    self.entry_vars.get((si, ei), tkinter.IntVar(value=1)).get()
                )
                version_var = self.version_vars.get((si, ei))
                if version_var is not None:
                    entry.active_version_id = version_var.get()

    def _ensure_library(self) -> LinkLibrary | None:
        if not self.doc:
            return None
        if self.link_library is None:
            self.link_library = LinkLibrary.empty_for_source(self.doc)
            self.library_path = default_link_library_path(self.doc.path)
        return self.link_library

    def _update_links(self):
        if not self.doc:
            messagebox.showwarning("No source file", "Please upload a source file first.")
            return

        self._sync_model()
        library = self._ensure_library()
        if library is None:
            return

        try:
            update_library_source_file(library, self.doc)
        except Exception as exc:
            messagebox.showerror("Update error", str(exc))
            self._set_status(f"Error: {exc}")
            return

        saved_path = save_link_library(library, self.library_path)
        self.library_path = saved_path
        self.link_library = library
        self.library_label.configure(text=f"Library: {saved_path}")
        self._set_status(f"Links updated: {saved_path}")

    def _generate(self):
        if not self.doc:
            messagebox.showwarning("No source file", "Please upload a source file first.")
            return

        self._sync_model()
        library = self._ensure_library()
        if library is None:
            return

        try:
            update_library_source_file(library, self.doc)
        except Exception as exc:
            messagebox.showerror("Update error", str(exc))
            self._set_status(f"Error: {exc}")
            return

        output_dir = self.output_dir_entry.get().strip()
        output_name = self.output_name_entry.get().strip()
        generate_pdf = bool(self.generate_pdf_var.get())

        if not output_dir:
            messagebox.showwarning("No output folder", "Please choose an output folder.")
            return
        if not output_name:
            messagebox.showwarning("No output file name", "Please choose an output file name.")
            return
        if os.path.basename(output_name) != output_name:
            messagebox.showwarning("Invalid file name", "Output file name must not include folder separators.")
            return
        if not output_name.lower().endswith(".tex"):
            output_name += ".tex"
        if not os.path.isdir(output_dir):
            messagebox.showwarning("Invalid output folder", "The selected output folder does not exist.")
            return

        output_path = os.path.join(output_dir, output_name)
        try:
            generated_file = library.create_generated_file(output_path, generate_pdf=generate_pdf)
        except Exception as exc:
            messagebox.showerror("Write error", str(exc))
            self._set_status(f"Error: {exc}")
            return
        library.add_generated_file(generated_file)

        saved_path = save_link_library(library, self.library_path)
        self.library_path = saved_path
        self.link_library = library
        self.library_label.configure(text=f"Library: {saved_path}")
        if generate_pdf and generated_file.pdf_path:
            self._set_status(f"Generated: {output_path} and {generated_file.pdf_path}")
        else:
            self._set_status(f"Generated: {output_path}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_status(self, msg: str):
        self.status_label.configure(text=f"Status: {msg}")

    def _announce_load(self, default_msg: str):
        if self._pending_warnings:
            count = len(self._pending_warnings)
            self._set_status(
                f"{default_msg} ({count} version warning(s)): {self._pending_warnings[0]}"
            )
        else:
            self._set_status(default_msg)
