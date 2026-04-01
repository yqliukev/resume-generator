import os
import threading
import tkinter
from tkinter import filedialog, messagebox

import customtkinter as ctk

from parser import parse_file
from assembler import assemble, write_tex, compile_pdf


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Resume Generator")
        self.geometry("960x680")
        self.minsize(720, 520)

        self.doc = None
        self.file_path: str | None = None

        # State maps: keyed by section index / (section_idx, entry_idx)
        self.section_vars: dict[int, tkinter.IntVar] = {}
        self.entry_vars: dict[tuple, tkinter.IntVar] = {}

        # Keep references so GC doesn't collect them
        self._section_cb_refs: list = []
        self._entry_cb_refs: list[list] = []

        self._generating = False
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

        ctk.CTkButton(
            top, text="Open File", width=110, command=self._open_file
        ).pack(side="left", padx=(8, 8), pady=6)

        self.file_label = ctk.CTkLabel(top, text="No file open", anchor="w")
        self.file_label.pack(side="left", fill="x", expand=True, padx=(0, 8))

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

        ctk.CTkLabel(bottom, text="Output:").grid(
            row=0, column=0, padx=(10, 6), pady=6, sticky="w"
        )
        self.output_entry = ctk.CTkEntry(
            bottom, placeholder_text="/path/to/output.tex"
        )
        self.output_entry.grid(row=0, column=1, sticky="ew", padx=4, pady=6)
        ctk.CTkButton(
            bottom, text="Browse", width=90, command=self._browse_output
        ).grid(row=0, column=2, padx=(4, 10), pady=6)

        self.compile_var = tkinter.IntVar(value=0)
        ctk.CTkCheckBox(
            bottom, text="Compile to PDF", variable=self.compile_var
        ).grid(row=1, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 4))

        self.generate_btn = ctk.CTkButton(
            bottom, text="Generate", width=110,
            command=self._generate, state="disabled"
        )
        self.generate_btn.grid(row=1, column=2, padx=(4, 10), pady=(0, 4))

        self.status_label = ctk.CTkLabel(
            bottom, text="Status: Ready", anchor="w",
            font=ctk.CTkFont(size=12)
        )
        self.status_label.grid(
            row=2, column=0, columnspan=3, sticky="ew", padx=10, pady=(0, 8)
        )

    # ------------------------------------------------------------------
    # File open
    # ------------------------------------------------------------------

    def _open_file(self):
        path = filedialog.askopenfilename(
            title="Open LaTeX Resume",
            filetypes=[("LaTeX files", "*.tex"), ("All files", "*.*")],
        )
        if not path:
            return
        self._set_status("Parsing…")
        try:
            self.doc = parse_file(path)
        except Exception as exc:
            messagebox.showerror("Parse error", str(exc))
            self._set_status(f"Error: {exc}")
            return

        self.file_path = path
        self.file_label.configure(text=path)

        # Default output path beside the source file
        base = os.path.splitext(path)[0]
        self.output_entry.delete(0, "end")
        self.output_entry.insert(0, base + "_output.tex")

        self._build_tree()
        self.generate_btn.configure(state="normal")
        self._set_status("Ready")

    # ------------------------------------------------------------------
    # Tree building
    # ------------------------------------------------------------------

    def _build_tree(self):
        # Clear old widgets
        for widget in self.tree_frame.winfo_children():
            widget.destroy()
        self.section_vars.clear()
        self.entry_vars.clear()
        self._section_cb_refs.clear()
        self._entry_cb_refs.clear()

        if not self.doc:
            return

        SECTION_FONT = ctk.CTkFont(size=13, weight="bold")
        ENTRY_FONT = ctk.CTkFont(size=12)

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
                row=si * 100, column=0, sticky="w",
                padx=8, pady=(10 if si > 0 else 4, 2)
            )
            self._section_cb_refs[si] = sec_cb

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
                    row=si * 100 + ei + 1, column=0, sticky="w",
                    padx=(30, 8), pady=1
                )
                self._entry_cb_refs[si].append(ent_cb)

        self._update_preview()

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
                    sec_label = ctk.CTkLabel(
                        self.preview_frame,
                        text=f"[{section.name}]  {entry.display_label[:55]}",
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
    # Browse output path
    # ------------------------------------------------------------------

    def _browse_output(self):
        path = filedialog.asksaveasfilename(
            title="Save output as",
            defaultextension=".tex",
            filetypes=[("LaTeX files", "*.tex"), ("All files", "*.*")],
            initialfile=os.path.basename(self.output_entry.get()) or "output.tex",
        )
        if path:
            self.output_entry.delete(0, "end")
            self.output_entry.insert(0, path)

    # ------------------------------------------------------------------
    # Generate
    # ------------------------------------------------------------------

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

    def _generate(self):
        if not self.doc or self._generating:
            return

        output_path = self.output_entry.get().strip()
        if not output_path:
            messagebox.showwarning("No output path", "Please specify an output .tex file path.")
            return

        self._sync_model()
        tex_content = assemble(self.doc)

        try:
            write_tex(tex_content, output_path)
        except Exception as exc:
            messagebox.showerror("Write error", str(exc))
            self._set_status(f"Error: {exc}")
            return

        if not self.compile_var.get():
            self._set_status(f"Written: {output_path}")
            return

        # Compile in background thread
        self._generating = True
        self.generate_btn.configure(state="disabled", text="Compiling…")
        self._set_status("Compiling PDF…")

        output_dir = os.path.dirname(os.path.abspath(output_path))

        def _worker():
            try:
                success, log = compile_pdf(os.path.abspath(output_path), output_dir)
            except FileNotFoundError:
                self.after(0, lambda: self._on_compile_done(
                    False, "pdflatex not found on PATH.\nInstall TeX Live or MiKTeX."
                ))
                return
            self.after(0, lambda: self._on_compile_done(success, log))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_compile_done(self, success: bool, log: str):
        self._generating = False
        self.generate_btn.configure(state="normal", text="Generate")

        if success:
            self._set_status("PDF compiled successfully.")
        else:
            self._set_status("Compilation failed — see details.")
            messagebox.showerror(
                "pdflatex error",
                "Compilation failed. Last output:\n\n" + log[-2000:],
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_status(self, msg: str):
        self.status_label.configure(text=f"Status: {msg}")
