'''
An example application built on Semantic Nets: a top-level analysis of a
Python program -- its packages, modules, classes, functions, methods, doc
strings and imports -- as a Semantic Nets model and view, opened in the editor.

  python3.14 -m sn.exampleApps.pythonParser [file.py|folder ...] [--depth N] [--libraries] [--imports none|given|all] [--go]

It shows a dialog (see *ParserDialog*) listing the files to analyse -- those
named on the command line to start with: a folder stands for all the .py
files in and below it -- with how many levels of imports to follow from them,
whether to analyse the standard library and installed packages too, and
which imports to show in the view; and a "Go" button. (With --go, it
goes straight away, without the dialog.)

It makes a model of the files and the modules they import, as far out as
asked (see *parser*), built on the ontology pythonOntology.snm (here, in this
folder), and a view of it showing the packages and modules, and the
contains-module and has-subpackage relations between them -- a tree, laid out
left to right -- and the imports asked for (see
*showPackages()*). The rest of the model (classes, functions, ...) is there
to be brought into the view (eg: a module's "expand").

The model is named after the files' main module -- the best guess at it: see
*parser.guessMain()* -- with "_py" (eg: "XMLreader_py.snm" and
"XMLreader_py.snv"), next to it (see *parser.outputPaths()*), asking first if
they're already there, and replacing them. (Use "save as" to keep it
somewhere else.)

Created on Oct 10, 2026

.. codeauthor:: Rob Kremer <robkremer@me.com>
'''
from __future__ import annotations
import sn # (first: it sets up logging -- see sn/__init__.py)
import argparse
import os
from dataclasses import dataclass
from typing import Any, Callable
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from util.utils import ownDialog
from sn.model.model import Model, Node, Relation
from sn.view.graphics.guiApp import Application
from sn.view.graphics.sngView import SNGView
from sn.view.graphics.treeLayout import TreeLayout
from sn.exampleApps.pythonParser.parser import buildModel, guessMain, ontologyTypes, outputPaths, readModules

TITLE = "Python Parser"

MAX_DEPTH = 20
"The most levels of imports the dialog offers to follow."

MARGIN = 40
"Where the view's objects are put before they're arranged."

@dataclass
class Options:
  '''What to analyse, and show (see *ParserDialog*).'''
  depth:int = 1
  "How many levels of imports to follow from the files given (see *parser.readModules()*)."
  libraries:bool = False
  "Whether to analyse modules in the standard library and installed packages too."
  showImports:str = "given"
  '''Which imports to show in the view: "none", "given" (those of the files
  given), or "all" (see *showPackages()*).'''

def packagesAndModules(model:Model) -> tuple[list[Node], list[Relation], list[Relation]]:
  '''
  :param model: A model made by *parser.buildModel()*.
  :type model: Model
  :returns: Its packages and modules; the relations between them that are
    kinds of *includes* (contains-module and has-subpackage); and the imports
    relations between them.
  :rtype: tuple[list[Node], list[Relation], list[Relation]]
  '''
  T = ontologyTypes(model)
  mine = [o for o in model.values() if o.model is model and o.isIndividual()]
  nodes = [o for o in mine if isinstance(o, Node) and o.isa(T["module"])] # (a package is a module too)
  ids = {id(o) for o in nodes}
  between = [r for r in mine if isinstance(r, Relation) and id(r.src) in ids and id(r.dst) in ids]
  return nodes, [r for r in between if r.isa(T["includes"])], [r for r in between if T["imports"] in r.getParents()]

def showPackages(view:SNGView, model:Model, showImports:str="given") -> None:
  '''
  Show the model's packages and modules, and the contains-module and
  has-subpackage relations between them, arranged as trees, left to right, by
  the tree layout (see *treeLayout.TreeLayout*), following "includes" (which
  those are kinds of); and below them, in rows, the modules and packages in
  no package with nothing in them (eg: the standard library's os and sys).
  The imports relations *showImports* says are shown too (their labels
  floating: midway): "none", "given" (those of the files given: at import
  depth 0), or "all". The tree layout is then the view's dynamic layout (see
  *SNGView.setDynamicLayout()*): it keeps the trees arranged -- eg: expanding
  a module opens its tree up for the classes and functions it defines.

  Nothing is placed by the view (see *SNGView.localLayout*) as they're shown:
  the tree layout places everything.

  :param view: A view of *model*.
  :type view: SNGView
  :param model: A model made by *parser.buildModel()*.
  :type model: Model
  :param showImports: Which imports to show: "none", "given" or "all".
  :type showImports: str
  '''
  nodes, includes, imports = packagesAndModules(model)
  localLayout, view.localLayout = view.localLayout, None #type: ignore[assignment] # (None: none, for now)
  try:
    for o in nodes:
      view.makeViewObjectForGraphObject(o, atPoint=(MARGIN, MARGIN))
    for r in includes:
      view.makeViewObjectForGraphObject(r)
    for r in imports:
      if showImports == "all" or (showImports == "given" and r.src.get("import-depth", -1) == 0): #type: ignore[union-attr]
        view.makeViewObjectForGraphObject(r)
  finally:
    view.localLayout = localLayout
  tree = dict(relation=ontologyTypes(model)["includes"], parentEnd="source", direction="right")
  TreeLayout(view, others="rows", **tree).arrange(animate=False)
  view.setDynamicLayout(TreeLayout(view, **tree)) # (kept arranged: expanding a module opens the tree up for what it defines)

def convert(app:Application, paths:list[str], options:Options, parent:tk.Misc|None=None,
            progress:Callable[[str], None]|None=None) -> bool:
  '''
  Make the model and view of the Python files *paths* (and what they import,
  as far as *options* says), save them, and open the view.

  :param app: The editor.
  :type app: Application
  :param paths: The files (and folders: see *parser.pythonFiles()*).
  :type paths: list[str]
  :param options: What to analyse, and show.
  :type options: Options
  :param parent: The window any messages are about (eg: the dialog), if any.
  :type parent: tk.Misc | None
  :param progress: Told about each module as it's analysed, if given (see *parser.readModules()*).
  :type progress: Callable[[str], None] | None
  :returns: Whether it did.
  :rtype: bool
  '''
  # (no parent, if none's given: the editor's main window is hidden -- on macOS,
  # a dialog given it as a parent is shown as a sheet in that small, otherwise hidden window)
  where:dict[str, Any] = {"parent": parent} if parent is not None else {}
  modules = readModules(paths, options.depth, options.libraries, progress)
  if not any(m.depth == 0 for m in modules):
    messagebox.showerror(TITLE, "There are no Python files there.", **where)
    return False
  main = guessMain(modules)
  modelPath, viewPath = outputPaths(main)
  existing = [p for p in (modelPath, viewPath) if os.path.exists(p)]
  if existing:
    if not messagebox.askokcancel(TITLE, "These files are already there:\n\n  " + "\n  ".join(existing)
                                  + "\n\nReplace them?", icon=messagebox.WARNING, **where):
      return False
    for p in existing:
      os.remove(p)
  model = buildModel(modelPath, modules)
  model.save()
  window = app.openWindow(modelPath) # (a new view of a model is made as <model>.snv: viewPath)
  if window is None:
    return False
  view:SNGView = window.view #type: ignore[attr-defined] # (an AppWindow)
  showPackages(view, model, options.showImports)
  view.save()
  given = sum(1 for m in modules if m.depth == 0)
  analysed = sum(1 for m in modules if m.analysed)
  print(f"Made {os.path.basename(modelPath)} and {os.path.basename(viewPath)} from {given} Python file(s) "
        f"(the main one taken to be {main.name}), analysing {analysed} module(s) in all, "
        f"of {len(modules)} found: {len(list(model.values()))} objects.")
  unreadable = [m for m in modules if m.error is not None]
  if unreadable:
    print("These couldn't be read (they're in the model, but empty):\n  "
          + "\n  ".join(f"{m.path}: {m.error}" for m in unreadable))
  return True

class ParserDialog(tk.Toplevel):
  '''
  The front end: the Python files and folders to analyse (added with "Add
  files...", "Add folder...", and taken out with "Remove" and "Clear"); how
  many levels of imports to follow from them; whether to analyse the
  standard library and installed packages too; which imports to show in the
  view (none, those of the files given, or all); and "Go" (see *convert()*) -- which, when it's done, closes it.
  '''
  def __init__(self, app:Application, paths:list[str], options:Options,
               onClose:Callable[[], None]|None=None):
    '''
    :param app: The editor.
    :type app: Application
    :param paths: The files and folders to start with.
    :type paths: list[str]
    :param options: The options to start with.
    :type options: Options
    :param onClose: Called when it's closed: by "Go" (when the view's opened) or "Cancel".
    :type onClose: Callable[[], None] | None
    '''
    super().__init__(app)
    ownDialog(self, app) # (over the editor's window, if one's on screen -- not full screen: see ownDialog())
    self.app, self.onClose = app, onClose
    self.title(TITLE)
    self.paths:list[str] = []
    self.depth = tk.StringVar(value=str(options.depth))
    self.libraries = tk.BooleanVar(value=options.libraries)
    self.showImports = tk.StringVar(value=options.showImports)
    self.status = tk.StringVar(value="")
    pad:dict[str, Any] = dict(padx=6, pady=3)

    frame = ttk.Frame(self, padding=10)
    frame.pack(fill=tk.BOTH, expand=True)
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(1, weight=1)
    ttk.Label(frame, text="Python files and folders to analyse:").grid(row=0, column=0, columnspan=2, sticky=tk.W, **pad)
    listFrame = ttk.Frame(frame)
    listFrame.grid(row=1, column=0, sticky=tk.NSEW, **pad)
    self.list = tk.Listbox(listFrame, height=10, width=70, selectmode=tk.EXTENDED, activestyle="none")
    scroll = ttk.Scrollbar(listFrame, orient=tk.VERTICAL, command=self.list.yview)
    self.list.configure(yscrollcommand=scroll.set)
    self.list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scroll.pack(side=tk.RIGHT, fill=tk.Y)
    self.list.bind("<Delete>", lambda _e: self.remove())
    self.list.bind("<BackSpace>", lambda _e: self.remove())
    buttons = ttk.Frame(frame)
    buttons.grid(row=1, column=1, sticky=tk.N, **pad)
    for text, command in (("Add files...", self.addFiles), ("Add folder...", self.addFolder),
                          ("Remove", self.remove), ("Clear", self.clear)):
      ttk.Button(buttons, text=text, command=command).pack(fill=tk.X, pady=2)

    ttk.Separator(frame).grid(row=2, column=0, columnspan=2, sticky=tk.EW, pady=8)
    depthRow = ttk.Frame(frame)
    depthRow.grid(row=3, column=0, columnspan=2, sticky=tk.W, **pad)
    ttk.Label(depthRow, text="Follow imports:").pack(side=tk.LEFT)
    ttk.Spinbox(depthRow, from_=0, to=MAX_DEPTH, textvariable=self.depth, width=4).pack(side=tk.LEFT, padx=6)
    ttk.Label(depthRow, text="levels").pack(side=tk.LEFT)
    ttk.Label(frame, text="0: just these files (what they import is shown, but not analysed); 1: what they "
                          "import too; 2: what that imports; ...", foreground="gray40", wraplength=520) \
      .grid(row=4, column=0, columnspan=2, sticky=tk.W, padx=24)
    ttk.Checkbutton(frame, text="Analyse the standard library and installed packages too",
                    variable=self.libraries).grid(row=5, column=0, columnspan=2, sticky=tk.W, **pad)
    importsRow = ttk.Frame(frame)
    importsRow.grid(row=6, column=0, columnspan=2, sticky=tk.W, **pad)
    ttk.Label(importsRow, text="Show imports in the view:").pack(side=tk.LEFT)
    for value, text in (("none", "none"), ("given", "those of these files"), ("all", "all")):
      ttk.Radiobutton(importsRow, text=text, value=value, variable=self.showImports).pack(side=tk.LEFT, padx=6)

    bottom = ttk.Frame(frame)
    bottom.grid(row=7, column=0, columnspan=2, sticky=tk.EW, pady=(10, 0))
    ttk.Label(bottom, textvariable=self.status, foreground="gray40").pack(side=tk.LEFT, padx=6)
    self.goButton = ttk.Button(bottom, text="Go", command=self.go, default="active")
    self.goButton.pack(side=tk.RIGHT, padx=6)
    ttk.Button(bottom, text="Cancel", command=self.cancel).pack(side=tk.RIGHT, padx=6)
    self.bind("<Return>", lambda _e: self.go())
    self.bind("<Escape>", lambda _e: self.cancel())
    self.protocol("WM_DELETE_WINDOW", self.cancel)

    self.add(paths)
    self.lift()
    self.focus_force()

  def add(self, paths:list[str]) -> None:
    '''
    :param paths: Files or folders to add to the list (each once).
    :type paths: list[str]
    '''
    for p in paths:
      p = os.path.abspath(p)
      if p not in self.paths:
        self.paths.append(p)
        self.list.insert(tk.END, p + (os.sep if os.path.isdir(p) else ""))
    self.updateGo()

  def addFiles(self) -> None:
    self.add(list(filedialog.askopenfilenames(parent=self, title="Choose Python files to analyse",
                                              filetypes=[("Python files", "*.py"), ("All files", "*.*")]) or []))

  def addFolder(self) -> None:
    folder = filedialog.askdirectory(parent=self, title="Choose a folder: all the Python files in and below it",
                                     mustexist=True)
    if folder:
      self.add([folder])

  def remove(self) -> None:
    '''Take the selected files and folders out of the list.'''
    for i in sorted(self.list.curselection(), reverse=True):
      self.list.delete(i)
      del self.paths[i]
    self.updateGo()

  def clear(self) -> None:
    self.list.delete(0, tk.END)
    self.paths.clear()
    self.updateGo()

  def updateGo(self) -> None:
    "Go only with something to go on."
    self.goButton.state(["!disabled"] if self.paths else ["disabled"])

  def options(self) -> Options|None:
    '''
    :returns: The options chosen, or None (having said why) if the depth isn't a number from 0 to *MAX_DEPTH*.
    :rtype: Options | None
    '''
    try:
      depth = int(self.depth.get())
      if not 0 <= depth <= MAX_DEPTH:
        raise ValueError
    except ValueError:
      messagebox.showerror(TITLE, f"The levels of imports to follow must be a number from 0 to {MAX_DEPTH}.", parent=self)
      return None
    return Options(depth, self.libraries.get(), self.showImports.get())

  def go(self) -> None:
    '''Make the model and view (see *convert()*); close, if that's done.'''
    options = self.options()
    if not self.paths or options is None:
      return
    def progress(name:str) -> None:
      self.status.set(f"Reading {name}...")
      self.update_idletasks()
    self.goButton.state(["disabled"])
    self.configure(cursor="watch")
    self.update_idletasks()
    try:
      done = convert(self.app, list(self.paths), options, parent=self, progress=progress)
    finally:
      if self.winfo_exists():
        self.configure(cursor="")
        self.status.set("")
        self.updateGo()
    if done:
      self.close()

  def cancel(self) -> None:
    self.close()

  def close(self) -> None:
    self.destroy()
    if self.onClose is not None:
      self.onClose()

def main() -> None:
  args = argparse.ArgumentParser(prog="python3.14 -m sn.exampleApps.pythonParser",
                                 description="Make a Semantic Nets model and view of a Python program.")
  args.add_argument("paths", nargs="*", help="Python files, and folders (all the .py files in and below them).")
  args.add_argument("--depth", type=int, default=Options.depth, help="How many levels of imports to follow (default: %(default)s).")
  args.add_argument("--libraries", action="store_true", help="Analyse the standard library and installed packages too.")
  args.add_argument("--imports", choices=("none", "given", "all"), default=Options.showImports,
                    help="Which imports to show in the view: those of the files given, by default.")
  args.add_argument("--go", action="store_true", help="Go straight away, without the dialog (needs paths).")
  a = args.parse_args()
  options = Options(a.depth, a.libraries, a.imports)
  app = Application()
  def closed() -> None:
    if not app.windows:
      app.quit()
  def start() -> None:
    if a.go and a.paths:
      if not convert(app, a.paths, options):
        closed()
    else:
      ParserDialog(app, a.paths, options, onClose=closed)
  app.after(300, start)
  app.run()

if __name__ == "__main__":
  main()
