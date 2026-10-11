'''
An example application built on Semantic Nets: a top-level analysis of a
Python program -- its packages, modules, classes, functions, methods, doc
strings and imports -- as a Semantic Nets model and view, opened in the editor.

  python3.14 -m sn.exampleApps.pythonParser [file.py|folder ...]

With no files named, it asks for some (one or more .py files: a folder named
on the command line stands for all the .py files in and below it). It makes a
model of them (see *parser*), built on the ontology pythonOntology.snm (here,
in this folder), and a view of it showing just the packages and modules, and
the contains-module relations between them: a tree, laid out left to right
(see *showPackages()*). The rest of the model is there to be brought into the
view (eg: a module's "expand").

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
import os
import sys
from tkinter import filedialog, messagebox
from sn.model.model import Model, Node, Relation, GraphObject
from sn.view.graphics.guiApp import Application
from sn.view.graphics.sngView import SNGView
from sn.view.graphics.vobjects import VObject
from sn.view.graphics.decorators import WrappingText
from sn.exampleApps.pythonParser.parser import buildModel, guessMain, ontologyTypes, outputPaths, readModules

TITLE = "Python Parser"

MARGIN = 40
"How far in from the view's top left the tree starts."

COLUMN_GAP = 170
"The space between one level of the tree and the next: room for the relations' labels."

ROW_GAP = 20
"The space between one leaf of the tree and the next."

LABEL_GAP = 12
"The space between a relation's label and what it goes to."

ROOT_GAP = 30
"The extra space between one tree and the next (eg: two top-level packages)."

def askForFiles() -> list[str]:
  '''
  :returns: The Python files the user chose (none if they cancelled).
  :rtype: list[str]
  '''
  # (no parent: the editor's main window is hidden -- on macOS, a dialog given
  # it as a parent is shown as a sheet in that small, otherwise hidden window)
  paths = filedialog.askopenfilenames(title="Choose the Python files to make a Semantic Nets model of",
                                      filetypes=[("Python files", "*.py"), ("All files", "*.*")])
  return list(paths or [])

def packageTree(model:Model) -> tuple[list[GraphObject], dict[GraphObject, list[GraphObject]], list[Relation]]:
  '''
  :param model: A model made by *parser.buildModel()*.
  :type model: Model
  :returns: Its packages and modules as a forest: the roots (those in no
    package); each one's packages and modules (packages first, then by name);
    and the contains-module relations.
  :rtype: tuple[list[GraphObject], dict[GraphObject, list[GraphObject]], list[Relation]]
  '''
  T = ontologyTypes(model)
  mine = [o for o in model.values() if o.model is model and o.isIndividual()]
  nodes = [o for o in mine if isinstance(o, Node) and o.isa(T["module"])] # (a package is a module too)
  contains = [r for r in mine if isinstance(r, Relation) and T["contains-module"] in r.getParents()
              and r.src is not None and r.dst is not None]
  def key(o:GraphObject) -> tuple[bool, str]:
    return (not o.isa(T["package"]), str(o.name).lower())
  children:dict[GraphObject, list[GraphObject]] = {o: [] for o in nodes}
  contained:set[GraphObject] = set()
  for r in contains:
    children.setdefault(r.src, []).append(r.dst) #type: ignore[arg-type]
    contained.add(r.dst) #type: ignore[arg-type]
  for kids in children.values():
    kids.sort(key=key)
  roots:list[GraphObject] = sorted((o for o in nodes if o not in contained), key=key)
  return roots, children, contains

def fitted(vo:VObject) -> VObject:
  '''
  :param vo: A node or relation just put in a view.
  :type vo: VObject
  :returns: It, sized to its name now (as it would be when it's first drawn:
    see *WrappingText.fitOwner()*), so it can be placed by its size.
  :rtype: VObject
  '''
  text = vo.decorators.get("text")
  if isinstance(text, WrappingText):
    text.fitOwner()
  return vo

def showPackages(view:SNGView, model:Model) -> None:
  '''
  Show the model's packages and modules, and the contains-module relations
  between them, as a tree (or several: one for each top-level package, and each
  module in none), laid out left to right: each level of packages in a column,
  each package level with the middle of what it contains, and the modules down
  the right. Each relation's label is fixed (not floating) on the straight line
  between its ends, just before what it goes to: so the labels line up, and the
  lines stay straight.

  Nothing is placed by the view (see *SNGView.localLayout*) meanwhile: this
  places everything itself.

  :param view: A view of *model*.
  :type view: SNGView
  :param model: A model made by *parser.buildModel()*.
  :type model: Model
  '''
  roots, children, contains = packageTree(model)
  localLayout, view.localLayout = view.localLayout, None #type: ignore[assignment] # (None: none, for now)
  try:
    shown = {o: fitted(view.makeViewObjectForGraphObject(o, atPoint=(MARGIN, MARGIN))) for o in children}
    size = {o: (vo.boundingBox()[2] - vo.boundingBox()[0], vo.boundingBox()[3] - vo.boundingBox()[1])
            for o, vo in shown.items()}
    # the columns: as wide as the widest thing in them
    widths:list[float] = []
    def measure(o:GraphObject, depth:int, seen:set[GraphObject]) -> None:
      if len(widths) <= depth:
        widths.append(0)
      widths[depth] = max(widths[depth], size[o][0])
      for k in children[o]:
        if k not in seen: # (a model edited by hand may have a cycle)
          measure(k, depth + 1, seen | {k})
    for r in roots:
      measure(r, 0, {r})
    columns = [float(MARGIN)]
    for w in widths[:-1]:
      columns.append(columns[-1] + w + COLUMN_GAP)
    # the rows: each leaf below the last; each package level with the middle of its contents
    nextY = float(MARGIN)
    placed:set[GraphObject] = set()
    def place(o:GraphObject, depth:int) -> float:
      nonlocal nextY
      placed.add(o)
      w, h = size[o]
      kids = [k for k in children[o] if k not in placed]
      if kids:
        centres = [place(k, depth + 1) for k in kids]
        centre = (centres[0] + centres[-1]) / 2
        nextY = max(nextY, centre + h / 2 + ROW_GAP)
      else:
        centre = nextY + h / 2
        nextY += h + ROW_GAP
      shown[o].moveTo(columns[depth], centre - h / 2, adjustPos=False)
      return centre
    for r in roots:
      place(r, 0)
      if children[r]: # (not between modules in no package)
        nextY += ROOT_GAP
    # the relations: each one's label anchored on the straight line between its ends (so the line stays
    # straight), just before what it goes to (so they line up in a column)
    for r in contains:
      vr = fitted(view.makeViewObjectForGraphObject(r))
      vr.floating(False) #type: ignore[attr-defined] # (a VRelation)
      bb = vr.boundingBox()
      (sx, sy), (dx, dy) = shown[r.src].centerPt(), shown[r.dst].centerPt() #type: ignore[index]
      x = shown[r.dst].boundingBox()[0] - LABEL_GAP - (bb[2] - bb[0]) / 2 #type: ignore[index]
      y = sy + (dy - sy) * (x - sx) / (dx - sx) if dx != sx else (sy + dy) / 2
      vr.moveToCenterOn(x, y, adjustPos=False)
  finally:
    view.localLayout = localLayout

def convert(app:Application, paths:list[str]) -> bool:
  '''
  Make the model and view of the Python files *paths*, save them, and open the view.

  :param app: The editor.
  :type app: Application
  :param paths: The files (and folders: see *parser.pythonFiles()*).
  :type paths: list[str]
  :returns: Whether it did.
  :rtype: bool
  '''
  modules = readModules(paths)
  if not modules:
    messagebox.showerror(TITLE, "There are no Python files there.") # (no parent: see askForFiles())
    return False
  main = guessMain(modules)
  modelPath, viewPath = outputPaths(main)
  existing = [p for p in (modelPath, viewPath) if os.path.exists(p)]
  if existing:
    if not messagebox.askokcancel(TITLE, "These files are already there:\n\n  " + "\n  ".join(existing)
                                  + "\n\nReplace them?", icon=messagebox.WARNING):
      return False
    for p in existing:
      os.remove(p)
  model = buildModel(paths, modelPath, modules)
  model.save()
  window = app.openWindow(modelPath) # (a new view of a model is made as <model>.snv: viewPath)
  if window is None:
    return False
  view:SNGView = window.view #type: ignore[attr-defined] # (an AppWindow)
  showPackages(view, model)
  view.save()
  unreadable = [m for m in modules if m.error is not None]
  print(f"Made {os.path.basename(modelPath)} and {os.path.basename(viewPath)} from {len(modules)} Python file(s) "
        f"(the main one taken to be {main.name}): {len(list(model.values()))} objects.")
  if unreadable:
    print("These couldn't be read (they're in the model, but empty):\n  "
          + "\n  ".join(f"{m.path}: {m.error}" for m in unreadable))
  return True

def main() -> None:
  app = Application()
  def start() -> None:
    paths = sys.argv[1:] or askForFiles()
    if not paths or not convert(app, paths):
      if not app.windows:
        app.quit()
  app.after(300, start)
  app.run()

if __name__ == "__main__":
  main()
