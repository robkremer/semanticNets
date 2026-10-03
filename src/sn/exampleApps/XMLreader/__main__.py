'''
An example application built on Semantic Nets: turn an XML file into a
Semantic Nets model and view, and open the view in the editor.

  python3.14 -m sn.exampleApps.XMLreader [file.xml]

With no file named, it asks for one. For "<name>.<ext>" it makes
"<name>_<ext>.snm" (the model: see *reader*) and "<name>_<ext>.snv" (a view of
it: its elements, arranged -- see *showTypesAndExpand()*) in the same folder
-- asking first if they're already there, and replacing them -- and opens the
view.

The *examples* folder here has some to try: books.xml (small: a namespace,
nesting, comments, and elements named by their id or name), and
library25.xml and library200.xml (25 and 200 made-up books: see
*examples/makeLibrary.py*).

Created on Oct 3, 2026

.. codeauthor:: Rob Kremer <robkremer@me.com>
'''
from __future__ import annotations
import sn # (first: it sets up logging -- see sn/__init__.py)
import math
import os
import sys
from typing import Callable
import xml.etree.ElementTree as ET
from tkinter import filedialog, messagebox
from sn.model.model import Model, Node
from sn.view.graphics.guiApp import Application
from sn.view.graphics.sngView import SNGView
from sn.view.graphics.vnodes import VNode
from util.utils import overlaps
from sn.exampleApps.XMLreader.reader import buildModel, outputPaths

TITLE = "XML Reader"

def askForFile(app:Application) -> str|None:
  '''
  :param app: The editor.
  :type app: Application
  :returns: The XML file the user chose, or None if they cancelled.
  :rtype: str | None
  '''
  # (no parent: the editor's main window is hidden -- on macOS, a dialog given
  # it as a parent is shown as a sheet in that small, otherwise hidden window)
  path = filedialog.askopenfilename(title="Choose an XML file to make a Semantic Nets model of",
                                    filetypes=[("XML files", "*.xml"), ("All files", "*.*")])
  return path or None

def expandLevels(model:Model) -> int:
  '''
  :param model: A model made by *buildModel()*.
  :type model: Model
  :returns: How many levels to expand its types by (see *showTypesAndExpand()*):
    fewer for a bigger model, as showing it takes longer.
  :rtype: int
  '''
  elements = sum(1 for o in model.values() if isinstance(o, Node) and o.isIndividual())
  return 4 if elements <= 100 else 3 if elements <= 500 else 2

def showTypesAndExpand(view:SNGView, model:Model) -> None:
  '''
  Fill the view with the model's elements and their relations, and start the
  animation layout arranging them:

  1. show the model's types -- its nodes that are directly a kind of node: one
     for each tag (see *buildModel()*) -- and expand each by *expandLevels()*
     levels (as the expand menu's "expand all, n levels"), which brings in
     their individuals;
  2. erase the types (and so the isa links to them): each individual has its
     type's look (see *reader.TypeLooks*), which shows which it is. (They're
     erased as a category, so expanding won't bring them back.)
  3. expand what's left by 2 levels, for anything not in yet;
  4. spread the nodes out, grouped by type, so that none start on top of
     another; and
  5. start the animation layout (see *startLayout()*). (When it settles,
     *convert()* moves any nodes it left on top of others: see
     *separateNodes()*.)

  Nothing is placed (see *SNGView.localLayout*) during 1-3: what's there then
  isn't where it ends up, and placing things in a crowded view takes a long time.

  :param view: A view of *model*.
  :type view: SNGView
  :param model: A model made by *buildModel()*.
  :type model: Model
  '''
  types = [o for o in model.values() if isinstance(o, Node) and not o.isIndividual() and model.NODE in o.getParents()]
  levels = expandLevels(model)
  localLayout, view.localLayout = view.localLayout, None
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
    spreadOut(view)
  finally:
    view.localLayout = localLayout

def visibleNodes(view:SNGView) -> list[VNode]:
  '''
  :param view: A view.
  :type view: SNGView
  :returns: The nodes in it, in order of their types' and then their own names.
  :rtype: list[VNode]
  '''
  def key(vo:VNode) -> tuple[str, str]:
    mo = vo.modelObject
    parents = mo.getParents() if mo is not None else []
    return (str(parents[0].name) if parents else "", str(mo.name if mo is not None else ""))
  return sorted((vo for vo in view.values() if isinstance(vo, VNode) and vo._isConnected() and not vo.isHidden()), key=key)

def spreadOut(view:SNGView) -> None:
  '''
  Put the view's nodes on a square-ish grid, in the order of *visibleNodes()*
  (so grouped by type), with room between them: a start for the animation
  layout with nothing on top of anything else.

  :param view: A view.
  :type view: SNGView
  '''
  nodes = visibleNodes(view)
  if not nodes:
    return
  boxes = [vo.boundingBox() for vo in nodes]
  cellW = max(b[2] - b[0] for b in boxes) + 80
  cellH = max(b[3] - b[1] for b in boxes) + 80
  columns = max(1, int(math.ceil(math.sqrt(len(nodes)))))
  for i, vo in enumerate(nodes):
    vo.moveTo(50 + (i % columns) * cellW, 50 + (i // columns) * cellH, adjustPos=False)

def separateNodes(view:SNGView) -> int:
  '''
  Move each node that overlaps another to the nearest free place (as the local
  layout does with a dropped node: see *SNGView.localLayout*). The animation
  layout pulls related nodes together, and can leave some on top of others.

  :param view: A view.
  :type view: SNGView
  :returns: How many were moved.
  :rtype: int
  '''
  if view.localLayout is None:
    return 0
  nodes = visibleNodes(view)
  moved = 0
  for vo in nodes:
    bb = vo.boundingBox()
    if any(other is not vo and overlaps(bb, other.boundingBox()) for other in nodes):
      view.localLayout(vo)
      moved += 1
  return moved

def startLayout(view:SNGView, whenSettled:Callable[[], None]|None=None) -> None:
  '''
  Start the view's animation layout (as its menu's "start"), and call
  *whenSettled* when it has settled and stopped.

  :param view: A view.
  :type view: SNGView
  :param whenSettled: What to do then: eg: save the view.
  :type whenSettled: Callable[[], None] | None
  '''
  layout = view.animationLayout()
  layout()
  def poll() -> None:
    if layout.active:
      view.canvas.after(500, poll)
    elif whenSettled is not None:
      whenSettled()
  view.canvas.after(500, poll)

def convert(app:Application, xmlPath:str) -> bool:
  '''
  Make the model and view of *xmlPath*, save them, and open the view.

  :param app: The editor.
  :type app: Application
  :param xmlPath: The XML file.
  :type xmlPath: str
  :returns: Whether it did.
  :rtype: bool
  '''
  modelPath, viewPath = outputPaths(xmlPath)
  existing = [p for p in (modelPath, viewPath) if os.path.exists(p)]
  if existing:
    if not messagebox.askokcancel(TITLE, "These files are already there:\n\n  " + "\n  ".join(existing)
                                  + "\n\nReplace them?", icon=messagebox.WARNING): # (no parent: see askForFile())
      return False
    for p in existing:
      os.remove(p)
  try:
    model = buildModel(xmlPath, modelPath)
  except ET.ParseError as ex:
    messagebox.showerror(TITLE, f"{os.path.basename(xmlPath)} isn't a well-formed XML file:\n\n{ex}")
    return False
  model.save()
  window = app.openWindow(modelPath) # (a new view of a model is made as <model>.snv: viewPath)
  if window is None:
    return False
  view:SNGView = window.view #type: ignore[attr-defined] # (an AppWindow)
  view.context.visibility("system objects", "hide") # (the system model's types: node, relation, ...)
  showTypesAndExpand(view, model)
  view.save()
  print(f"Made {os.path.basename(modelPath)} and {os.path.basename(viewPath)} from {os.path.basename(xmlPath)}: "
        f"{len([o for o in model.values()])} objects. Arranging them (the animation layout)...")
  def settled() -> None:
    if view._closed: # (its window was closed meanwhile: it was offered for saving then)
      return
    separateNodes(view)
    view.save()
    print(f"Arranged, and saved {os.path.basename(viewPath)}.")
  startLayout(view, settled)
  return True

def main() -> None:
  app = Application()
  def start() -> None:
    xmlPath = sys.argv[1] if len(sys.argv) > 1 else askForFile(app)
    if xmlPath is None or not convert(app, xmlPath):
      if not app.windows:
        app.quit()
  app.after(300, start)
  app.run()

if __name__ == "__main__":
  main()
