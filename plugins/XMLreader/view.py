'''
XMLreader's front end: turn an XML file into a Semantic Nets model and view,
and open the view in the editor. (The Tools menu's "XML Reader...": see the
plugin's *register()*.)

It asks for the file (see *askForFile()*). For "<name>.<ext>" it makes
"<name>_<ext>.snm" (the model: see *reader*), "<name>_<ext>_ontology.snm" (its
super-model: the types and definitions) and "<name>_<ext>.snv" (a view of
the model: its elements, arranged as they nest -- see *showTypesAndExpand()*
and *arrange()*) in the same folder
-- asking first if they're already there, and replacing them (or, for the
ontology, keeping it, and building the new model on it: see *convert()*) --
and opens the view. (For the plugin's own examples, they're made elsewhere: see *convert()*.)

The plugin's *examples* folder has some to try: books.xml (small: a namespace,
nesting, comments, and elements named by their id or name), and
library25.xml and library200.xml (25 and 200 made-up books: see
*examples/makeLibrary.py*).

Created on Oct 3, 2026 (as a program of its own: a plugin since Oct 17)

.. codeauthor:: Rob Kremer <robkremer@me.com>
'''
from __future__ import annotations
import os
from pathlib import Path
from typing import Any, Sequence
import xml.etree.ElementTree as ET
from tkinter import filedialog, messagebox
from sn.model.model import Model, Node
from sn.view.graphics.guiApp import Application
from sn.view.graphics.sngView import SNGView
from sn.view.graphics.vnodes import VNode
from sn.view.graphics.layout import relationTypes, nodeTypes, _BoxIndex
from sn.view.graphics.relationTable import RelationTable, RelationRow, SHAPES, PULLS, TERMINALS
from .reader import buildModel, outputPaths, PART_OF

TITLE = "XML Reader"

GAP = 40.0
"The room *separateNodes()* leaves in each cell of its grid beyond the biggest node: a node it moves is at least half this from any other."

def askForFile(folder:str|None=None) -> str|None:
  '''
  :param folder: The folder to start in, if any.
  :returns: The XML file the user chose, or None if they cancelled.
  '''
  # (no parent: the editor's main window is hidden -- on macOS, a dialog given
  # it as a parent is shown as a sheet in that small, otherwise hidden window)
  where:dict[str, Any] = {"initialdir": folder} if folder is not None and os.path.isdir(folder) else {}
  path = filedialog.askopenfilename(title="Choose an XML file to make a Semantic Nets model of",
                                    filetypes=[("XML files", "*.xml"), ("All files", "*.*")], **where)
  return path or None

def expandLevels(model:Model) -> int:
  '''
  :param model: A model made by *buildModel()*.
  :returns: How many levels to expand its types by (see *showTypesAndExpand()*):
    fewer for a bigger model, as showing it takes longer.
  '''
  elements = sum(1 for o in model.values() if isinstance(o, Node) and o.isIndividual())
  return 4 if elements <= 100 else 3 if elements <= 500 else 2

def showTypesAndExpand(view:SNGView, model:Model) -> None:
  '''
  Fill the view with the model's elements and their relations (for
  *arrange()* to arrange):

  1. show the model's types -- its ontology's nodes that are directly a kind
     of node: one for each tag (see *buildModel()*) -- and expand each by *expandLevels()*
     levels (as the expand menu's "expand all, n levels"), which brings in
     their individuals;
  2. erase the types (and so the isa links to them): each individual has its
     type's look (see *reader.TypeLooks*), which shows which it is. (They're
     erased as a category, so expanding won't bring them back.)
  3. expand what's left by 2 levels, for anything not in yet.

  Nothing is placed (see *SNGView.localLayout*) meanwhile -- nor the
  relations' labels, as each new one is put between its ends once the
  editor's idle (see *vrelations.VRelation*): what's there then isn't where
  it ends up, and placing thousands of things in a crowded view takes a long
  time.

  :param view: A view of *model*.
  :param model: A model made by *buildModel()*.
  '''
  types = sorted((t for t in nodeTypes(model) if model.NODE in t.getParents()), key=lambda t: t._id) # (as they were made)
  levels = expandLevels(model)
  localLayout, view.localLayout = view.localLayout, None # type: ignore[assignment] # (none while it's laid out)
  try:
    x = 50
    shown = []
    for t in types:
      vo = view.makeViewObjectForGraphObject(t, atPoint=(x, 50))
      shown.append(vo)
      x = vo.boundingBox()[2] + 60
    for vo in shown:
      vo.expand(expand=levels - 1)
    view.context.visibility("types", "erase")
    done:dict[int, int] = {}
    for vo in visibleNodes(view):
      vo.expand(expand=1, _done=done)
    view.canvas.update() # (the relations' labels put between their ends now, while nothing's placed: see above)
  finally:
    view.localLayout = localLayout

def visibleNodes(view:SNGView) -> list[VNode]:
  '''
  :param view: A view.
  :returns: The nodes in it, in order of their types' and then their own names.
  '''
  def key(vo:VNode) -> tuple[str, str]:
    mo = vo.modelObject
    parents = mo.getParents() if mo is not None else []
    return (str(parents[0].name) if parents else "", str(mo.name if mo is not None else ""))
  return sorted((vo for vo in view.values() if isinstance(vo, VNode) and vo._isConnected() and not vo.isHidden()), key=key)

def relationTable(model:Model) -> RelationTable:
  '''
  :param model: A model made by *buildModel()*.
  :returns: The relation table (see *relationTable.RelationTable*) that makes
    trees of how its elements nest: its relation types (has-<tag>,
    xml-has-part, xml-part-of) shape the trees, each element its children's
    parent (the source end -- the destination for xml-part-of).
  '''
  return RelationTable([RelationRow(str(t.name), SHAPES, "destination" if t.name == PART_OF else "source")
                        for t in relationTypes(model) if t is not model.ISA]
                       + [RelationRow(TERMINALS, PULLS)])

def arrange(view:SNGView) -> None:
  '''
  Arrange the view's elements as balloons, as they nest (see
  *balloonLayout.BalloonLayout*, by *relationTable()*): each element with its
  children round it, and so on out to the leaves -- all at once, as one
  undoable command. (Not the animation layout, which was used before: it took
  a long time to settle with a big file, and could leave nodes on top of
  others.)

  :param view: A view of a model made by *buildModel()*, filled by *showTypesAndExpand()*.
  '''
  from sn.view.graphics.balloonLayout import BalloonLayout
  BalloonLayout(view, relations=relationTable(view.model)).arrange(animate=False)

def separateNodes(view:SNGView, gap:float=GAP) -> int:
  '''
  Move each node that's on another to the nearest free cell of a grid that
  nothing's on (see *freeCells()*): the others stay where they are. It's
  quick even with thousands. (*arrange()* leaves nothing on anything else,
  as a rule: this is in case.)

  :param view: A view.
  :param gap: The room in each cell beyond the biggest node: a node moved is at least half of it from any other.
  :returns: How many were moved.
  '''
  nodes = visibleNodes(view)
  moves = freeCells([vo.boundingBox() for vo in nodes], gap)
  for k, (x, y) in moves.items():
    nodes[k].moveTo(x, y, adjustPos=False)
  return len(moves)

def freeCells(boxes:Sequence[Sequence[float]], gap:float=GAP) -> dict[int, tuple[int, int]]:
  '''
  Where to move each box that's on another (see *separateNodes()*): the
  boxes, in order, each stay where they are if they're on none of those
  staying; the rest go in the middle of the cell, of a grid of cells as big
  as the biggest box with *gap* to spare, that nothing staying or moved is
  on, whose middle is nearest theirs. Each box is only compared with those
  near it (see *layout._BoxIndex*).

  :param boxes: [x1, y1, x2, y2].
  :param gap: The room in each cell beyond the biggest box.
  :returns: The new top left of each box that's moved, by its index in *boxes*.
  '''
  if not boxes:
    return {}
  cellW = max(b[2] - b[0] for b in boxes) + gap
  cellH = max(b[3] - b[1] for b in boxes) + gap
  def cellsOf(b:Sequence[float]) -> list[tuple[int, int]]:
    return [(i, j) for i in range(int(b[0] // cellW), int(b[2] // cellW) + 1)
                   for j in range(int(b[1] // cellH), int(b[3] // cellH) + 1)]
  # the boxes that stay, and the cells they're on: each box on one that stays moves
  staying, taken = _BoxIndex(), set()
  moving:list[int] = []
  for k, b in enumerate(boxes):
    if staying.hits(b, 0):
      moving.append(k)
    else:
      staying.add(b)
      taken.update(cellsOf(b))
  # each to the free cell whose middle is nearest its middle, looking out ring by ring (any further
  # out than one that's free is further away, as a cell's at most half a cell from the middle)
  ret:dict[int, tuple[int, int]] = {}
  for k in moving:
    b = boxes[k]
    cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    ci, cj = int(cx // cellW), int(cy // cellH)
    best:tuple[float, int, int]|None = None
    r = 0
    while best is None or (r - 1) * min(cellW, cellH) <= best[0] ** 0.5:
      for i in range(ci - r, ci + r + 1):
        for j in ((cj - r, cj + r) if abs(i - ci) < r else range(cj - r, cj + r + 1)):
          if (i, j) not in taken:
            d = ((i + 0.5) * cellW - cx) ** 2 + ((j + 0.5) * cellH - cy) ** 2
            if best is None or (d, i, j) < best:
              best = (d, i, j)
      r += 1
    assert best is not None
    _, i, j = best
    taken.add((i, j))
    w, h = b[2] - b[0], b[3] - b[1]
    ret[k] = (int((i + 0.5) * cellW - w / 2), int((j + 0.5) * cellH - h / 2)) # (in the middle of it)
  return ret

def convert(app:Application, xmlPath:str, folder:str|None=None) -> bool:
  '''
  Make the model, its ontology, and the view of *xmlPath*, save them, and open the view.

  If they're there already, it asks first: if the ontology is, whether to
  keep it -- and build the new model on it, adding only what's missing (see
  *reader.buildModel()*), so the changes made to it stay -- or replace it
  too; otherwise, whether to replace them.

  :param app: The editor.
  :param xmlPath: The XML file.
  :param folder: Where to make them, if not beside it (see *reader.outputPaths()*):
    eg: for the plugin's own examples, as the plugin's folder is replaced when
    a newer version's installed (see *sn.plugins.installBundled()*).
  :returns: Whether it did.
  '''
  modelPath, viewPath, ontologyPath = outputPaths(xmlPath)
  if folder is not None:
    os.makedirs(folder, exist_ok=True)
    modelPath, viewPath, ontologyPath = (os.path.join(folder, os.path.basename(p)) for p in (modelPath, viewPath, ontologyPath))
  existing = [p for p in (modelPath, viewPath, ontologyPath) if os.path.exists(p)]
  keep = False # (whether to build on the ontology that's there)
  if os.path.exists(ontologyPath):
    answer = messagebox.askyesnocancel(TITLE, "These files are already there:\n\n  " + "\n  ".join(existing)
                                       + f"\n\nKeep the ontology, {os.path.basename(ontologyPath)}, and build the new model on it? "
                                       "Anything you've changed in it (types moved about, rules added, ...) stays: "
                                       "only what's missing is added.\n\n"
                                       "Yes: keep it, and replace the model and view.\nNo: replace them all.",
                                       icon=messagebox.WARNING) # (no parent: see askForFile())
    if answer is None:
      return False
    keep = answer
  elif existing:
    if not messagebox.askokcancel(TITLE, "These files are already there:\n\n  " + "\n  ".join(existing)
                                  + "\n\nReplace them?", icon=messagebox.WARNING):
      return False
  for p in (modelPath,) if keep else (modelPath, ontologyPath): # (its window, if it's open, and the model in memory:
    if not app.replacingModel(p):                                # they'd be added to -- the model first, as it builds on the ontology)
      return False
  ontology:Model|None = None
  if keep: # (as it is in memory, if it is -- eg: its window's open -- changes not saved yet and all)
    try:
      ontology = Model.getDB(Path(ontologyPath).as_uri())
    except Exception as ex:
      messagebox.showerror(TITLE, f"Couldn't read {os.path.basename(ontologyPath)}:\n\n{ex}")
      return False
  for p in existing:
    if not (keep and p == ontologyPath):
      os.remove(p)
  had = len(ontology) if ontology is not None else 0
  try:
    model, ontology = buildModel(xmlPath, modelPath, ontology)
  except ET.ParseError as ex:
    messagebox.showerror(TITLE, f"{os.path.basename(xmlPath)} isn't a well-formed XML file:\n\n{ex}")
    return False
  ontology.save()
  model.save()
  window = app.openWindow(modelPath) # (a new view of a model is made as <model>.snv: viewPath)
  if window is None:
    return False
  view:SNGView = window.view #type: ignore[attr-defined] # (an AppWindow)
  view.context.visibility("system objects", "hide") # (the system model's types: node, relation, ...)
  showTypesAndExpand(view, model)
  arrange(view)
  separateNodes(view)
  view.save()
  made = (f"{os.path.basename(modelPath)} and {os.path.basename(viewPath)}, on {os.path.basename(ontologyPath)} (kept: "
          f"{len(ontology) - had} objects added)," if keep else
          f"{os.path.basename(modelPath)}, {os.path.basename(ontologyPath)} and {os.path.basename(viewPath)}")
  print(f"Made {made} from {os.path.basename(xmlPath)}: {len([o for o in model.values()])} objects (and "
        f"{len([o for o in ontology.values()])} in the ontology), arranged as balloons.")
  return True
