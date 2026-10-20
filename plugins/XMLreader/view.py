'''
XMLreader's front end: turn an XML file into a Semantic Nets model and view,
and open the view in the editor. (The Tools menu's "XML Reader...": see the
plugin's *register()*.)

It's a dialog (see *ReaderDialog*): the XML file, and the three files made
from it -- for "<name>.<ext>", by default, "<name>_<ext>.snm" (the model: see
*reader*), "<name>_<ext>.snv" (a view of the model: its types, each with its
elements round it -- see *showTypesExpanded()*) and
"<name>_<ext>_ontology.snm" (the model's super-model: the types and
definitions), in the same folder (see *defaultPaths()*). Any of them can be
put somewhere else; and the ontology can be one that's there already --
eg: one shared by several XML files of the same kind -- a file, or a URL (on
the web, say). Then the model's built on it, and what it hasn't (eg: types
for tags it hasn't seen) is added to it -- or, if it can't be changed (eg:
it's on the web), put in the model. "Go" makes them (see *convert()*), asking
first if the model and view are there already, and replacing them, and opens
the view. (For a big file -- more than *MAX_SHOWN* elements -- the view
shows just the types, to be expanded as they're wanted: see *showTypes()*.)

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
from dataclasses import dataclass
from typing import Any, Callable, Sequence
import xml.etree.ElementTree as ET
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from util.utils import fixURL, ownDialog
from sn.model.model import IsaIndividual, Model, Node
from sn.view.graphics.guiApp import Application
from sn.view.graphics.sngView import SNGView
from sn.view.graphics.vnodes import VNode
from sn.view.graphics.layout import relationTypes, nodeTypes, _BoxIndex
from sn.view.graphics.relationTable import RelationTable, RelationRow, SHAPES, PULLS, IGNORED, TERMINALS
from .reader import buildModel, canChange, isRemote, localPath, ontologyPath, outputPaths, HAS_PART, PART_OF, REFERS_TO

TITLE = "XML Reader"

MAX_SHOWN = 2000
'''The most elements a view's made showing (see *convert()*): a model with
more shows just its types, to be expanded (see *showTypes()*). (A view of
1000 elements takes a few seconds to make; of 10,000, minutes.)'''

GAP = 40.0
"The room *separateNodes()* leaves in each cell of its grid beyond the biggest node: a node it moves is at least half this from any other."

def defaultPaths(xmlPath:str, folder:str|None=None) -> tuple[str, str, str]:
  '''
  :param xmlPath: An XML file.
  :param folder: Where to make its files, if not beside it: eg: for the
    plugin's own examples, as the plugin's folder is replaced when a newer
    version's installed (see *sn.plugins.installBundled()*).
  :returns: The model, view and ontology files made from it, by default (see *reader.outputPaths()*).
  '''
  paths = outputPaths(xmlPath)
  if folder is None:
    return paths
  model, view, ontology = (os.path.join(folder, os.path.basename(p)) for p in paths)
  return model, view, ontology

def elementCount(model:Model) -> int:
  '''
  :param model: A model made by *buildModel()*.
  :returns: How many elements it has (its individual nodes).
  '''
  return sum(1 for o in model.values() if isinstance(o, Node) and o.isIndividual())

def expandLevels(model:Model) -> int:
  '''
  :param model: A model made by *buildModel()*.
  :returns: How many levels to expand its types by (see *showTypesAndExpand()*):
    fewer for a bigger model, as showing it takes longer.
  '''
  elements = elementCount(model)
  return 4 if elements <= 100 else 3 if elements <= 500 else 2

def showTypes(view:SNGView, model:Model, arrange:bool=True) -> None:
  '''
  Fill the view with just the model's node types -- its ontology's (the
  tags' types, their subtypes, and any added to it), and its own (eg: ones
  its ontology couldn't be given: see *reader.buildModel()*) -- arranged as
  a tree, by isa, growing down (see *treeLayout.TreeLayout*): for a model too
  big to show all at once (see *MAX_SHOWN*). Each type can be expanded to
  bring in its elements, as they're wanted. (The types are still in the
  ontology: they're only shown here.)

  :param view: A view of *model*.
  :param model: A model made by *buildModel()*.
  :param arrange: Whether to arrange them (as a tree): if not, they're all in one place.
  '''
  from sn.view.graphics.treeLayout import TreeLayout
  localLayout, view.localLayout = view.localLayout, None # type: ignore[assignment] # (none: the tree layout places them)
  try:
    types = sorted(nodeTypes(model), key=lambda t: (t.model is model, t._id)) # (as they were made)
    for t in types:
      view.makeViewObjectForGraphObject(t, atPoint=(50, 50))
    shown = {id(t) for t in types}
    for t in types: # (the isa links between them, for the tree)
      for r, parent in t._getOutgoing(lambda r: isinstance(r, IsaIndividual)):
        if id(parent) in shown:
          view.makeViewObjectForGraphObject(r)
  finally:
    view.localLayout = localLayout
  if arrange:
    TreeLayout(view, relation="isa", direction="down", others="rows").arrange(animate=False) # (those with no subtypes in rows, after the trees)

def showTypesExpanded(view:SNGView, model:Model) -> None:
  '''
  Fill the view with the model's node types (as *showTypes()*) and their
  elements -- each type expanded one level, by isa -- arranged as balloons by
  isa (see *balloonLayout.BalloonLayout*): each type with its subtypes and
  elements round it. For a model small enough to show all at once (see
  *MAX_SHOWN*): the types organize it, and its elements can be expanded to
  bring in how they nest and refer to one another.

  Nothing is placed meanwhile (see *showTypesAndExpand()*).

  :param view: A view of *model*.
  :param model: A model made by *buildModel()*.
  '''
  from sn.view.graphics.balloonLayout import BalloonLayout
  showTypes(view, model, arrange=False)
  types = [vo for vo in view.values() if isinstance(vo, VNode) and vo.modelObject is not None and not vo.modelObject.isIndividual()]
  localLayout, view.localLayout = view.localLayout, None # type: ignore[assignment] # (none while it's laid out)
  try:
    done:dict[int, int] = {}
    for vo in types: # (just by isa: not the relation types whose range they are)
      vo.expand(filter=lambda _vn, r: isinstance(r, IsaIndividual), _done=done)
    view.canvas.update() # (the relations' labels put between their ends now, while nothing's placed)
  finally:
    view.localLayout = localLayout
  BalloonLayout(view, relations=RelationTable([RelationRow("isa", SHAPES, "destination"), RelationRow(TERMINALS, IGNORED)])) \
    .arrange(animate=False)

def showTypesAndExpand(view:SNGView, model:Model) -> None:
  '''
  Fill the view with the model's elements and their relations, without their
  types (for *arrange()* to arrange, as they nest: eg: for the User Guide's
  pictures of the hubs layout):

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
    trees of how its elements nest: a row for each of the general relation
    types, which stands for its kinds -- *HAS_PART* (has-<tag> and
    has-<holder>) and *PART_OF* shape the trees, each element its children's
    parent (the source end of xml-has-part, the destination of xml-part-of);
    *REFERS_TO* (the references) pulls what they relate together -- and one
    for any other relation type that none of them stands for (eg: in an
    ontology made before there were these), shaping the trees.
  '''
  general = {HAS_PART: RelationRow(HAS_PART, SHAPES, "source"), PART_OF: RelationRow(PART_OF, SHAPES, "destination"),
             REFERS_TO: RelationRow(REFERS_TO, PULLS)}
  types = [t for t in relationTypes(model) if t is not model.ISA]
  rows = [general[str(t.name)] for t in types if str(t.name) in general]
  rows += [RelationRow(str(t.name), SHAPES, "source") for t in types
           if not any(str(s.name) in general for s in [t, *t.getSupers()])]
  return RelationTable(rows + [RelationRow(TERMINALS, PULLS)])

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

@dataclass
class Files:
  '''What to read, and what to make of it (see *ReaderDialog* and *convert()*).'''
  xml:str
  "The XML file."
  model:str
  "The model's file (.snm)."
  view:str
  "The view's file (.snv)."
  ontology:str
  '''The ontology's file or URL: one that's there is built on (and added to,
  if it can be changed: see *reader.canChange()*), unless *replaceOntology*;
  otherwise it's made.'''
  replaceOntology:bool = False
  "Whether to make the ontology afresh, if it's there (a file here)."

def ontologyState(ref:str) -> str:
  '''
  :param ref: An ontology's file or URL (see *Files.ontology*).
  :returns: What'd be done with it: "web" (it's on the web: it's read, if
    it's there, and can't be changed), "new" (there's no such file: it's
    made), "there" (it's there, and can be changed), "locked" (it's there,
    and can't be: eg: it's read-only) or "" (*ref* is empty).
  '''
  ref = ref.strip()
  if not ref:
    return ""
  path = localPath(ref)
  if path is None:
    return "web"
  if not os.path.exists(path):
    return "new"
  return "there" if canChange(path) else "locked"

def convert(app:Application, files:Files, parent:tk.Misc|None=None) -> bool:
  '''
  Make the model and view of *files.xml*, on its ontology (made, or one
  that's there: see *Files.ontology*), save them, and open the view. If the
  model or view are there already (or the ontology, if it's to be made
  afresh), it asks first, and replaces them.

  :param app: The editor.
  :param files: What to read, and what to make of it.
  :param parent: The window any messages are about (eg: the dialog), if any.
  :returns: Whether it did.
  '''
  # (no parent, if none's given: the editor's main window is hidden -- on macOS,
  # a dialog given it as a parent is shown as a sheet in that small, otherwise hidden window)
  where:dict[str, Any] = {"parent": parent} if parent is not None else {}
  def error(message:str) -> bool:
    messagebox.showerror(TITLE, message, **where)
    return False
  xmlPath = os.path.abspath(os.path.expanduser(files.xml.strip()))
  modelPath = os.path.abspath(os.path.expanduser(files.model.strip()))
  viewPath = os.path.abspath(os.path.expanduser(files.view.strip()))
  ontologyRef = files.ontology.strip()
  state = ontologyState(ontologyRef)
  ontologyFile = localPath(ontologyRef) if ontologyRef else None
  if not os.path.isfile(xmlPath):
    return error(f"There's no such file as {xmlPath}.")
  if not modelPath.endswith(".snm") or not viewPath.endswith(".snv"):
    return error("The model's file must end in .snm, and the view's in .snv.")
  if not state:
    return error("Which ontology? Give its file (one that's there, or one to make), or its URL.")
  if ontologyFile is not None and not ontologyFile.endswith(".snm"):
    return error("The ontology's file must end in .snm.")
  if ontologyFile is not None and os.path.realpath(ontologyFile) == os.path.realpath(modelPath):
    return error("The model and its ontology can't be the same file.")
  replaceOntology = files.replaceOntology and state in ("there", "locked")
  existing = [p for p in (modelPath, viewPath) if os.path.exists(p)] + ([ontologyFile] if replaceOntology and ontologyFile else [])
  if existing:
    warning = ("\n\nThe ontology's made afresh: anything you've changed in it is lost, and other models built on it lose their types."
               if replaceOntology else "")
    if not messagebox.askokcancel(TITLE, "These files are already there:\n\n  " + "\n  ".join(existing)
                                  + warning + "\n\nReplace them?", icon=messagebox.WARNING, **where):
      return False
  for folder in {os.path.dirname(p) for p in (modelPath, viewPath, ontologyFile) if p is not None}:
    os.makedirs(folder, exist_ok=True) # (first: a file in a folder that isn't there has no URL, to look for its model in memory by)
  for p in [modelPath] + ([ontologyFile] if replaceOntology and ontologyFile else []): # (its window, if it's open, and the model
    if not app.replacingModel(p):                                                       # in memory: they'd be added to -- the model first, as it builds on the ontology)
      return False
  ontology:Model|str
  if state == "new" or replaceOntology:
    assert ontologyFile is not None
    ontology = ontologyFile
  else: # (as it is in memory, if it is -- eg: its window's open -- changes not saved yet and all)
    try:
      ontology = Model.getDB(Path(ontologyFile).as_uri() if ontologyFile is not None else ontologyRef)
    except Exception as ex:
      return error(f"Couldn't read the ontology, {ontologyRef}:\n\n{ex}")
  for p in existing:
    os.remove(p)
  had = len(ontology) if isinstance(ontology, Model) else 0
  extend = state != "web" and canChange(ontologyRef)
  found:list[str] = []
  try:
    model, ontology = buildModel(xmlPath, modelPath, ontology, extend, found)
  except ET.ParseError as ex:
    return error(f"{os.path.basename(xmlPath)} isn't a well-formed XML file:\n\n{ex}")
  if not ontology.writeLocked() and extend and ontology.isDirty(): # (not one there already, if nothing's added to it)
    ontology.save()
  model.save()
  view = SNGView(fixURL(viewPath, None, replaceExt=None, mode="w")[0], model=model, mode="w") # (where it was asked for: not necessarily beside the model)
  window = app.openWindow(view)
  if window is None:
    return False
  view.context.visibility("system objects", "hide") # (the system model's types: node, relation, ...)
  elements = elementCount(model)
  if elements > MAX_SHOWN:
    showTypes(view, model)
    shown = f"too many to show at once (more than {MAX_SHOWN}): the view shows their types, to expand as you need them"
  else:
    showTypesExpanded(view, model)
    separateNodes(view)
    shown = "with their types, arranged as balloons round them"
  view.save()
  name = os.path.basename
  how = ("made" if state == "new" or replaceOntology else
         f"{len(ontology) - had} objects added" if extend else "kept as it is: what it hadn't is in the model")
  print(f"Made {name(modelPath)} and {name(viewPath)} from {name(xmlPath)}, on {name(ontology.url)} ({how}): "
        f"{len(model)} objects (and {len(ontology)} in the ontology); {elements} elements, {shown}.\n"
        f"Its tags: {found[0]}.")
  return True

class ReaderDialog(tk.Toplevel):
  '''
  The front end: the XML file to read; the model, view and ontology files to
  make of it (each with "Choose..."), which follow the XML file (see
  *defaultPaths()*) -- the view and ontology following the model -- until
  they're changed by hand (the ontology may start as one chosen by hand
  before: eg: one shared by XML files of the same kind); what's done with the ontology (made, or built on,
  and added to if it can be: see *ontologyState()*), and, if it's there,
  whether to replace it; and "Go" (see *convert()*) -- which, when it's
  done, closes it.
  '''
  def __init__(self, app:Application, xmlPath:str|None=None, folder:str|None=None,
               defaults:Callable[[str], tuple[str, str, str]]=defaultPaths, ontology:str|None=None,
               onChosen:Callable[[str], None]|None=None, onGo:Callable[[Files, bool], None]|None=None,
               onClose:Callable[[], None]|None=None):
    '''
    :param app: The editor.
    :param xmlPath: The XML file to start with, if any.
    :param folder: The folder to choose an XML file in, at first.
    :param defaults: The model, view and ontology files for an XML file (see *defaultPaths()*).
    :param ontology: The ontology to start with, as if given by hand (eg: the
      one given last time: see *onGo*), if any; else it follows the model.
    :param onChosen: Told the XML file chosen with "Choose..." (eg: to start there next time).
    :param onGo: Told the files, once "Go"'s made them, and whether the
      ontology was given by hand (eg: to offer it next time), rather than
      following the model.
    :param onClose: Called when it's closed: by "Go" (when the view's opened) or "Cancel".
    '''
    super().__init__(app)
    ownDialog(self, app) # (over the editor's window, if one's on screen -- not full screen: see ownDialog())
    self.app, self.folder, self.defaults, self.onChosen, self.onGo, self.onClose = app, folder, defaults, onChosen, onGo, onClose
    self.title(TITLE)
    self.vars = {k: tk.StringVar(value="") for k in ("xml", "model", "view", "ontology")}
    self.following = {"model": True, "view": True, "ontology": True}
    "Which files follow the one they're made from (see *setDefaults()*): until they're changed by hand."
    self._setting = False
    self.replaceOntology = tk.BooleanVar(value=False)
    self.ontologyNote = tk.StringVar(value="")
    pad:dict[str, Any] = dict(padx=6, pady=3)

    frame = ttk.Frame(self, padding=10)
    frame.pack(fill=tk.BOTH, expand=True)
    frame.columnconfigure(1, weight=1)
    rows = (("xml", "XML file:", self.chooseXML), ("model", "Model:", self.chooseModel),
            ("view", "View:", self.chooseView), ("ontology", "Ontology:", self.chooseOntology))
    self.entries:dict[str, ttk.Entry] = {}
    for row, (key, label, choose) in enumerate(rows):
      r = row + 1 if key == "ontology" else row # (a line between the files made and the ontology)
      ttk.Label(frame, text=label).grid(row=r, column=0, sticky=tk.W, **pad)
      self.entries[key] = e = ttk.Entry(frame, textvariable=self.vars[key], width=64)
      e.grid(row=r, column=1, sticky=tk.EW, **pad)
      ttk.Button(frame, text="Choose...", command=choose).grid(row=r, column=2, **pad)
      self.vars[key].trace_add("write", lambda *_a, key=key: self.changed(key))
    ttk.Separator(frame).grid(row=3, column=0, columnspan=3, sticky=tk.EW, pady=6)
    ttk.Label(frame, text="A file (one that's there, eg: shared by XML files of the same kind; or one to make), or a URL.",
              foreground="gray40", wraplength=520).grid(row=5, column=1, columnspan=2, sticky=tk.W, padx=6)
    ttk.Label(frame, textvariable=self.ontologyNote, wraplength=520).grid(row=6, column=1, columnspan=2, sticky=tk.W, **pad)
    self.replaceButton = ttk.Checkbutton(frame, text="Replace it: make it afresh (anything changed in it is lost, "
                                         "and other models built on it lose their types)", variable=self.replaceOntology,
                                         command=self.updateOntologyNote)
    self.replaceButton.grid(row=7, column=1, columnspan=2, sticky=tk.W, **pad)

    bottom = ttk.Frame(frame)
    bottom.grid(row=8, column=0, columnspan=3, sticky=tk.EW, pady=(10, 0))
    self.goButton = ttk.Button(bottom, text="Go", command=self.go, default="active")
    self.goButton.pack(side=tk.RIGHT, padx=6)
    ttk.Button(bottom, text="Cancel", command=self.cancel).pack(side=tk.RIGHT, padx=6)
    self.bind("<Return>", lambda _e: self.go())
    self.bind("<Escape>", lambda _e: self.cancel())
    self.protocol("WM_DELETE_WINDOW", self.cancel)

    if ontology:
      self.vars["ontology"].set(ontology) # (by hand: see changed())
    if xmlPath:
      self.vars["xml"].set(xmlPath)
    self.refresh()
    self.lift()
    self.focus_force()

  def set(self, key:str, value:str) -> None:
    '''Set a file, as if by the program (so it still follows the one it's made from: see *following*).'''
    if self.vars[key].get() == value: # (not again: it'd set those that follow it again, and so on)
      return
    self._setting = True
    try:
      self.vars[key].set(value)
    finally:
      self._setting = False

  def changed(self, key:str) -> None:
    '''
    A file's changed: by hand (unless *set()* did it), it's no longer
    following -- or, if it's been emptied, it is again; and those that follow
    it are set from it (see *setDefaults()*).
    '''
    value = self.vars[key].get().strip()
    if key in self.following and not self._setting:
      self.following[key] = not value
      if not value:
        self.setDefaults()
    if key == "xml" or key == "model":
      self.setDefaults()
    self.refresh()

  def setDefaults(self) -> None:
    '''Set the files that are following from the ones they follow: the model from the XML file; the view and ontology from the model.'''
    xml = self.vars["xml"].get().strip()
    if not xml:
      return
    model, view, ontology = self.defaults(os.path.abspath(os.path.expanduser(xml)))
    if self.following["model"]:
      self.set("model", model)
    model = self.vars["model"].get().strip()
    if model:
      model = os.path.abspath(os.path.expanduser(model))
      if self.following["view"]:
        self.set("view", os.path.splitext(model)[0] + ".snv")
      if self.following["ontology"]:
        self.set("ontology", ontologyPath(model))

  def updateOntologyNote(self) -> None:
    '''Say what'd be done with the ontology; "Replace it" only for one that's there.'''
    state = ontologyState(self.vars["ontology"].get())
    replace = self.replaceOntology.get() and state in ("there", "locked")
    self.ontologyNote.set("It's made afresh, in place of the one that's there." if replace else {
      "": "",
      "new": "There's no such file: it's made.",
      "there": "It's there: the model's built on it, and what it hasn't (eg: types for new tags) is added to it.",
      "locked": "It's there, but can't be changed: the model's built on it, and what it hasn't (eg: types for new tags) "
                "goes in the model.",
      "web": "It's on the web, so it can't be changed: the model's built on it, and what it hasn't (eg: types for new "
             "tags) goes in the model.",
    }[state])
    self.replaceButton.state(["!disabled"] if state in ("there", "locked") else ["disabled"])

  def refresh(self) -> None:
    '''What's said about the ontology, and Go: only with all the files given.'''
    self.updateOntologyNote()
    self.goButton.state(["!disabled"] if all(v.get().strip() for v in self.vars.values()) else ["disabled"])

  def choose(self, key:str, path:str) -> None:
    if path:
      self.vars[key].set(path) # (by hand: see changed())

  def startIn(self, key:str) -> dict[str, Any]:
    '''The folder to choose a file in: where the file is, or else the folder given (see *__init__()*).'''
    value = self.vars[key].get().strip()
    path = localPath(value) if value else None
    folder = os.path.dirname(path) if path else self.folder
    return {"initialdir": folder} if folder and os.path.isdir(folder) else {}

  def chooseXML(self) -> None:
    path = filedialog.askopenfilename(parent=self, title="Choose an XML file to make a Semantic Nets model of",
                                      filetypes=[("XML files", "*.xml"), ("All files", "*.*")], **self.startIn("xml"))
    if path:
      self.choose("xml", path)
      if self.onChosen is not None:
        self.onChosen(path)

  def chooseSave(self, key:str, what:str, ext:str) -> None:
    current = self.vars[key].get().strip()
    self.choose(key, filedialog.asksaveasfilename(parent=self, title=f"The {what}'s file", defaultextension=ext,
                                                  initialfile=os.path.basename(current) if current else "",
                                                  filetypes=[(f"{what.capitalize()} files", f"*{ext}")], **self.startIn(key)))

  def chooseModel(self) -> None:
    self.chooseSave("model", "model", ".snm")

  def chooseView(self) -> None:
    self.chooseSave("view", "view", ".snv")

  def chooseOntology(self) -> None:
    self.choose("ontology", filedialog.askopenfilename(parent=self, title="Choose an ontology to build on",
                                                       filetypes=[("Model files", "*.snm"), ("All files", "*.*")],
                                                       **self.startIn("ontology")))

  def files(self) -> Files:
    '''The files given.'''
    v = {k: var.get().strip() for k, var in self.vars.items()}
    return Files(v["xml"], v["model"], v["view"], v["ontology"], self.replaceOntology.get())

  def go(self) -> None:
    '''Make the model and view (see *convert()*); close, if that's done.'''
    if not all(v.get().strip() for v in self.vars.values()):
      return
    self.goButton.state(["disabled"])
    self.configure(cursor="watch")
    self.update_idletasks()
    files = self.files()
    try:
      done = convert(self.app, files, parent=self)
    finally:
      if self.winfo_exists():
        self.configure(cursor="")
        self.refresh()
    if done:
      if self.onGo is not None:
        self.onGo(files, not self.following["ontology"])
      self.close()

  def cancel(self) -> None:
    self.close()

  def close(self) -> None:
    self.destroy()
    if self.onClose is not None:
      self.onClose()
