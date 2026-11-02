"""
Drag-and-drop GUI for landmark_convert.py (Windows + Linux).

Drop landmark files / folders onto the window (or onto the app icon), pick the target
format, hit Convert. Meshes are auto-found by basename unless one is picked.
"""
import os
import sys
import queue
import threading
import traceback
import contextlib
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import landmark_convert as lc

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    HAVE_DND = True
except ImportError:  # still usable via the Add buttons
    HAVE_DND = False


class QueueWriter:
    """File-like object that forwards print() output to the GUI thread."""
    def __init__(self, q: queue.Queue):
        self.q = q

    def write(self, s):
        if s:
            self.q.put(s)

    def flush(self):
        pass


class App:
    def __init__(self, root: tk.Tk, initial_paths):
        self.root = root
        self.files: list = []
        self.log_q: queue.Queue = queue.Queue()
        self.worker = None

        root.title("Landmark Converter")
        root.minsize(640, 520)

        pad = {"padx": 8, "pady": 4}
        main = ttk.Frame(root, padding=8)
        main.pack(fill="both", expand=True)

        # --- input list / drop zone ---
        ttk.Label(main, text="Landmark files  (.ljson  .mrk.json  .txt  .xml  .csv)"
                  + ("  — drag & drop here" if HAVE_DND else "")).pack(anchor="w")
        list_frame = ttk.Frame(main)
        list_frame.pack(fill="both", expand=True)
        self.listbox = tk.Listbox(list_frame, height=8, selectmode="extended")
        self.listbox.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        sb.pack(side="right", fill="y")
        self.listbox.config(yscrollcommand=sb.set)
        if HAVE_DND:
            for w in (self.listbox, root):
                w.drop_target_register(DND_FILES)
                w.dnd_bind("<<Drop>>", self.on_drop)

        btns = ttk.Frame(main)
        btns.pack(fill="x", pady=(4, 8))
        ttk.Button(btns, text="Add files…", command=self.add_files).pack(side="left")
        ttk.Button(btns, text="Add folder…", command=self.add_folder).pack(side="left", padx=4)
        ttk.Button(btns, text="Remove selected", command=self.remove_selected).pack(side="left")
        ttk.Button(btns, text="Clear", command=self.clear).pack(side="left", padx=4)

        # --- options ---
        opts = ttk.LabelFrame(main, text="Options", padding=6)
        opts.pack(fill="x")
        opts.columnconfigure(1, weight=1)

        ttk.Label(opts, text="Convert to").grid(row=0, column=0, sticky="w", **pad)
        self.target_labels = {lc.DISPLAY_NAME[t]: t for t in lc.TARGETS}
        self.target_var = tk.StringVar(value=lc.DISPLAY_NAME["wrap3d_bary_txt"])
        ttk.Combobox(opts, textvariable=self.target_var, values=list(self.target_labels),
                     state="readonly").grid(row=0, column=1, columnspan=2, sticky="ew", **pad)

        ttk.Label(opts, text="Barycentric").grid(row=1, column=0, sticky="w", **pad)
        self.conv_var = tk.StringVar(value="standard")
        conv_frame = ttk.Frame(opts)
        conv_frame.grid(row=1, column=1, columnspan=2, sticky="w", **pad)
        for key, text in lc.BARY_CONVENTIONS.items():
            ttk.Radiobutton(conv_frame, text=text, value=key, variable=self.conv_var).pack(anchor="w")

        self.mesh_var = tk.StringVar()
        self.template_var = tk.StringVar()
        self.outdir_var = tk.StringVar()
        self._path_row(opts, 2, "Mesh", self.mesh_var, self.pick_mesh,
                       "blank = auto-find <same name>.obj/.ply/.stl next to each file")
        self._path_row(opts, 4, "LJSON template", self.template_var, self.pick_template,
                       "groups + connectivity when writing .ljson from bary / other formats")
        self._path_row(opts, 6, "Output folder", self.outdir_var, self.pick_outdir,
                       "blank = next to each input file")

        # --- run + log ---
        run_row = ttk.Frame(main)
        run_row.pack(fill="x", pady=8)
        self.run_btn = ttk.Button(run_row, text="Convert", command=self.run)
        self.run_btn.pack(side="left")
        self.progress = ttk.Progressbar(run_row, mode="indeterminate")
        self.progress.pack(side="left", fill="x", expand=True, padx=8)

        self.log = tk.Text(main, height=12, wrap="word", state="disabled")
        self.log.pack(fill="both", expand=True)

        if not HAVE_DND:
            self.write_log("(tkinterdnd2 not installed — drag & drop disabled, use the Add buttons)\n")
        self.add_paths(initial_paths)
        self.root.after(100, self.drain_log)

    def _path_row(self, parent, row, label, var, cmd, hint):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=8, pady=(4, 0))
        ttk.Entry(parent, textvariable=var).grid(row=row, column=1, sticky="ew", padx=8, pady=(4, 0))
        ttk.Button(parent, text="…", width=3, command=cmd).grid(row=row, column=2, padx=4, pady=(4, 0))
        ttk.Label(parent, text=hint, foreground="gray").grid(row=row + 1, column=1, sticky="w", padx=8)

    # --- file list ---
    def add_paths(self, paths):
        for p in paths:
            try:
                found = lc.expand_inputs([p], "*")  # folders: every landmark-type file inside
            except FileNotFoundError:
                self.write_log(f"Not found: {p}\n")
                continue
            if not found:
                self.write_log(f"Skipped (not a landmark file): {p}\n")
            for f in found:
                if f not in self.files:
                    self.files.append(f)
                    self.listbox.insert("end", f)

    def on_drop(self, event):
        self.add_paths(self.root.tk.splitlist(event.data))

    def add_files(self):
        paths = filedialog.askopenfilenames(title="Landmark files", filetypes=[
            ("Landmark files", "*.ljson *.json *.txt *.xml *.csv"), ("All files", "*.*")])
        self.add_paths(paths)

    def add_folder(self):
        d = filedialog.askdirectory(title="Folder of landmark files")
        if d:
            self.add_paths([d])

    def remove_selected(self):
        for i in reversed(self.listbox.curselection()):
            self.listbox.delete(i)
            del self.files[i]

    def clear(self):
        self.listbox.delete(0, "end")
        self.files.clear()

    def pick_mesh(self):
        p = filedialog.askopenfilename(title="Mesh", filetypes=[
            ("Meshes", "*.obj *.ply *.stl *.off *.glb *.gltf"), ("All files", "*.*")])
        if p:
            self.mesh_var.set(p)

    def pick_template(self):
        p = filedialog.askopenfilename(title="LJSON template", filetypes=[("LJSON", "*.ljson")])
        if p:
            self.template_var.set(p)

    def pick_outdir(self):
        d = filedialog.askdirectory(title="Output folder")
        if d:
            self.outdir_var.set(d)

    # --- logging ---
    def write_log(self, s):
        self.log.config(state="normal")
        self.log.insert("end", s)
        self.log.see("end")
        self.log.config(state="disabled")

    def drain_log(self):
        while not self.log_q.empty():
            self.write_log(self.log_q.get_nowait())
        if self.worker is not None and not self.worker.is_alive():
            self.worker = None
            self.progress.stop()
            self.run_btn.config(state="normal")
        self.root.after(100, self.drain_log)

    # --- run ---
    def equivalent_cmd(self, target, mesh, template, out_dir, conv):
        """The CLI command that does the same thing, recorded in run_command.txt."""
        parts = ["landmark_convert.py", *self.files, "--to", target, "--bary-convention", conv]
        if mesh:
            parts += ["--mesh", mesh]
        if template:
            parts += ["--template", template]
        if out_dir:
            parts += ["--out-dir", out_dir]
        return "[gui] " + " ".join(lc.quote_arg(p) for p in parts)

    def run(self):
        if not self.files:
            messagebox.showinfo("Landmark Converter", "Add some landmark files first.")
            return
        target = self.target_labels[self.target_var.get()]
        mesh = self.mesh_var.get().strip() or None
        template = self.template_var.get().strip() or None
        out_dir = self.outdir_var.get().strip() or None
        conv = self.conv_var.get()
        cmd = self.equivalent_cmd(target, mesh, template, out_dir, conv)
        files = list(self.files)

        def work():
            with contextlib.redirect_stdout(QueueWriter(self.log_q)):
                try:
                    lc.convert_many(files, target, mesh=mesh, out_dir=out_dir, template=template,
                                    convention=conv, provenance_cmd=cmd)
                except Exception:
                    print(traceback.format_exc())

        self.write_log("\n" + "-" * 60 + "\n")
        self.run_btn.config(state="disabled")
        self.progress.start(10)
        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()


def main():
    root = TkinterDnD.Tk() if HAVE_DND else tk.Tk()
    App(root, sys.argv[1:])  # files dropped onto the app icon / passed on the command line
    root.mainloop()


if __name__ == "__main__":
    main()
