'''
Editing in a graphical view (*EditingMixin*): one of the parts of
*sn.view.graphics.sngView.SNGView* (see *viewBase*).

Created on Oct 18, 2026 (from sngView.py)

.. codeauthor:: Rob Kremer <robkremer@me.com>
'''
#################################################################################
# (c) Copyright 2024-2026, Rob Kremer, MIT open source license.                 #
#                                                                               #
# Permission is hereby granted, free of charge, to any person obtaining a copy  #
# of this software and associated documentation files (the "Software"), to deal #
# in the Software without restriction, including without limitation the rights  #
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell     #
# copies of the Software, and to permit persons to whom the Software is         #
# furnished to do so, subject to the following conditions:                      #
#                                                                               #
# The above copyright notice and this permission notice shall be included in all#
# copies or substantial portions of the Software.                               #
#                                                                               #
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR    #
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,      #
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE   #
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER        #
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, #
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE #
# SOFTWARE.                                                                     #
#################################################################################
from __future__ import annotations
import tkinter as tk
import sn
from sn import snPrefs
from sn.model.constraints import WHERE
from sn.model.model import Node, Relation, SN_URL, IsaIndividual, GraphObject, Model
from typing import Optional, cast, Any, Callable, Iterable, TYPE_CHECKING
from util.attributeEditor import applyEditAttrsBox
from sn.view.graphics.vobjects import VObject
from sn.view.graphics.vrelations import VRelation
from sn.view.graphics.layout import Direction
from util.commandParser import CompositeCommandMgr
from math import sqrt
from sn.view.graphics.viewCommands import keptWith, _ContainCreated, ViewDoList
from sn.view.graphics.viewBase import ViewBase
if TYPE_CHECKING:
  from sn.view.graphics.sngView import SNGView

logger:sn.SNLogger = sn.getLogger(__name__)

class EditingMixin(ViewBase):
  '''
  Editing in a view (*sn.view.graphics.sngView.SNGView*): making new objects
  and relations (and where they go, and naming them), cut, copy and paste,
  copying a picture, erasing from the view or removing from the model,
  showing all of the model, and searching it.
  '''

  def addNewObjectMenus(self, menu:tk.Menu, at:tuple[float, float], into:tuple[VObject, str]|None=None) -> None:
    '''
    Add the "new instance of Node", "new subtype of Node", "new instance of
    Relation" and "new subtype of Relation" cascades to *menu*: each with a
    submenu per model (this view's, its super-models, then sn) of its types.
    What's made is put at *at* (see *_newObjectLocation()*) -- and, with
    *into*, contained in that context window's pane (one undo for both): eg:
    the menu on a rule's window, to edit it in place.

    :param at: Where the menu was asked for (view coords).
    :param into: (a context window, the name of one of its panes: see *VObject.panes()*), or None.
    '''
    self._newAt = None
    def make(t:GraphObject, individual:bool, ptype:type) -> None:
      if ptype is Node: # (put where the menu was asked for: see _newObjectLocation())
        self._newAt = (int(at[0]), int(at[1]), t)
      new = self.context.new_node if ptype is Node else self.context.new_relation
      if into is None:
        new(t, name="", individual=individual, type=not individual) # type: ignore[arg-type]
        return
      win, pane = into
      with CompositeCommandMgr(self.context) as mgr:
        new(t, name="", individual=individual, type=not individual) # type: ignore[arg-type]
        if mgr.commands and win.modelObject is not None:
          mgr._addCommand(_ContainCreated(self.model, self._paneType(pane), win.modelObject, mgr.commands[-1]))
    def typesMenu(individual:bool, ptype:type) -> tk.Menu:
      ret = tk.Menu(self.canvas)
      # this model's types, then its super-models' (nearest first), then sn's
      implicit = self.model.implicitSuperDBs()
      supers = [db for db in self.model.allSuperDBs() if isinstance(db, Model) and not any(db is i for i in implicit)]
      for v in [self.model, *supers, Model.AllDBs[SN_URL]]:
        assert isinstance(v, Model)
        m = tk.Menu(self.canvas)
        for t in sorted((o for o in v.values() if isinstance(o, ptype) and o.isType()), key=lambda o: o.name):
          m.add_command(label=t.name, command=lambda t=t: make(t, individual, ptype)) #type: ignore[misc]
        ret.add_cascade(label=v.name, menu=m)
      return ret
    menu.add_cascade(label="new instance of Node", menu=typesMenu(True, Node))
    menu.add_cascade(label="new subtype of Node", menu=typesMenu(False, Node))
    menu.add_cascade(label="new instance of Relation", menu=typesMenu(True, Relation))
    menu.add_cascade(label="new subtype of Relation", menu=typesMenu(False, Relation))

  _newAt:tuple[int, int, GraphObject]|None = None
  '''
  Where the background menu that's making a node was asked for (view coords),
  and the type it's making one of, until it's made (see *makeMenu()*, *_newObjectLocation()*).
  '''

  def _placeNew(self, vo:VObject, under:VObject|None) -> None:
    '''
    Move a newly made view object to the nearest free place (see *FindFree*):
    below *under* (its supertype), if that's given -- or wherever the view's
    dynamic layout puts it -- and then let that layout adjust the rest (see
    *ViewDoList.adjustAgain()*).
    '''
    if not vo._isConnected() or vo.isHidden():
      return
    if vo._shape is None or vo._shape.id is None: # (not drawn yet: it'd be invisible to the search)
      self.freshPaint()
      vo.draw()
    if under is not None and not under._isConnected():
      under = None
    c = self.canvas
    seen = list(self.windowToView(c.canvasx(0), c.canvasy(0), c.canvasx(c.winfo_width()), c.canvasy(c.winfo_height())))
    cx, cy = vo.centerPt()
    within = seen if c.winfo_width() > 1 and seen[0] <= cx <= seen[2] and seen[1] <= cy <= seen[3] else None # (on screen: kept there)
    self.localLayout(vo, referenceNode=under, direction=Direction.SUB if under is not None else Direction.NEAREST, within=within)
    if isinstance(self.context.doList, ViewDoList): # (the layout keeps it arranged with the rest, now it's here)
      self.context.doList.adjustAgain()

  def _selectedModelObjects(self, orAll:bool=False) -> list[GraphObject]:
    '''
    :param orAll: If nothing's selected, everything shown instead (as "select
      all" would select: see *selectAll()*).
    :returns: The model objects of what's selected, in the order they're drawn
      (top to bottom, left to right).
    '''
    chosen = self.selected if self.selected or not orAll else self._shownObjects()
    vos = sorted((vo for vo in chosen if vo._isConnected() and vo.modelObject is not None),
                 key=lambda vo: (vo.boundingBox()[1], vo.boundingBox()[0]))
    return [vo.modelObject for vo in vos] #type: ignore[misc]

  def _shownObjects(self) -> list[VObject]:
    ":returns: What's shown: what *selectAll()* selects (not what's hidden)."
    return [vo for vo in self.values() if vo is not None and vo._isConnected() and not vo.isHidden()]

  def _geometryOf(self, objects:Iterable[GraphObject]) -> dict[int, dict[str, Any]]:
    '''
    :param objects: Model objects.
    :returns: How this view shows each of *objects* that it shows (by *id()*
      of the object): what *showPasted()* needs to show a copy of it the same
      way (see *copying.Clip.geometry*).
    '''
    ret:dict[int, dict[str, Any]] = {}
    for mo in objects:
      vo = self.findViewObjectForGraphObject(mo)
      if vo is None or not vo._isConnected():
        continue
      g:dict[str, Any] = {"bb": [int(v) for v in vo.boundingBox()], "userSized": vo.userSized,
                          "filtered": self.isFiltered(mo) and not vo.categoryExempt} # (hidden by its category: so is the copy)
      if isinstance(vo, VRelation):
        g["floating"] = vo.floating()
      if getattr(vo, "collapsed", False):
        g["collapsed"], g["expandedHeight"] = True, getattr(vo, "expandedHeight", None)
      ret[id(mo)] = g
    return ret

  def doCopy(self, cut:bool=False) -> None:
    '''
    Copy what's selected -- or, if nothing is, everything shown -- to the
    clipboard (see *ModelContext.copy()*), with how this view shows it, so a
    paste shows the copies the same way (see *showPasted()*). With *cut*,
    remove it from the model too (undoably) -- only what's selected: not
    everything, just because nothing is.
    '''
    from sn.model import copying
    objs = self._selectedModelObjects(orAll=not cut)
    if not objs:
      logger.warning("Nothing is selected to cut." if cut else "There's nothing to copy.")
      return
    geometry = self._geometryOf(copying.closure(objs)) # (now: once it's cut, it's not shown)
    try:
      msg = self.context.cut(objs) if cut else self.context.copy(objs)
    except Exception as ex:
      logger.error(f"Can't {'cut' if cut else 'copy'}: {ex}")
      return
    clip = copying.clipboard
    if clip is not None:
      clip.geometry = {i: geometry[id(e.original)] for i, e in enumerate(clip.entries) if id(e.original) in geometry}
      clip.viewURL = self.url
    if msg:
      print(msg)

  def doPaste(self, at:tuple[float, float]|None=None) -> None:
    '''
    Paste what was last cut or copied (see *ModelContext.paste()*), and show
    it (see *showPasted()*).

    :param at: Where to put it (view coords: the top left of what's pasted), or
      None to put it where it was (or beside it, if that's taken).
    '''
    try:
      if at is None:
        self.context.paste()
      else:
        self.context.paste(x=int(at[0]), y=int(at[1]))
    except Exception as ex:
      logger.error(f"Can't paste: {ex}")

  def _editAction(self, action:str) -> None:
    '''
    "Edit | Cut", "Copy", "Paste" or "Select All" in the menu bar: for the
    terminal's text, if that has the keyboard focus, else for the canvas.
    ("Copy as picture" is always the canvas's: see *doCopyImage()*.)

    :param action: "cut", "copy", "paste", "select all" or "copy image".
    '''
    w = self.canvas.focus_get()
    if action == "copy image":
      self.doCopyImage()
    elif isinstance(w, (tk.Text, tk.Entry)):
      w.event_generate("<<SelectAll>>" if action == "select all" else f"<<{action.capitalize()}>>")
    elif action == "select all":
      self.selectAll()
    elif action == "paste":
      self.doPaste()
    else:
      self.doCopy(cut=action == "cut")

  def selectAll(self) -> None:
    '''
    Select everything that's shown: not what's hidden (eg: a hidden category,
    or what's in a collapsed window).
    '''
    for vo in self._shownObjects():
      if not vo.selected():
        vo.selected(True, _multi=True)

  def onEditKey(self, event:tk.Event, action:str) -> str:
    '''
    Cmd-X, Cmd-C, Cmd-V or Cmd-A on the canvas (see *_editAction()*).

    :param action: "cut", "copy", "paste", "select all" or "copy image".
    :returns: "break": it's been dealt with.
    '''
    self._editAction(action)
    self.addEventHandled(event)
    return "break"

  def pictureObjects(self) -> list[VObject]:
    '''
    :returns: What a picture of the selection shows (see *doCopyImage()*):
      what's selected, what's in any selected context windows (at any depth),
      and the relations between any of those -- as far as they're shown; or,
      if nothing's selected, everything shown.
    '''
    if not self.selected:
      return self._shownObjects()
    ret:list[VObject] = []
    def add(vo:VObject) -> None:
      if vo in ret or not vo._isConnected() or vo.isHidden():
        return
      ret.append(vo)
      for c in vo.carriedContents():
        add(c)
    for vo in self.selected:
      add(vo)
    more = True
    while more: # (relations between them -- and between those)
      more = False
      for vo in self.values():
        if isinstance(vo, VRelation) and vo not in ret and vo.src in ret and vo.dst in ret and vo._isConnected() and not vo.isHidden():
          ret.append(vo)
          more = True
    return ret

  def doCopyImage(self) -> None:
    '''
    Put a picture of what's selected -- or, if nothing is, of everything
    shown -- (see *pictureObjects()*), as it's drawn (but without the
    selection's handles), on the system clipboard, as a PNG: to paste into
    another program (see *imageExport*).
    '''
    from sn.view.graphics.imageExport import copyImage
    vos = self.pictureObjects()
    if not vos:
      logger.warning("There's nothing to copy as a picture.")
      return
    selected = list(self.selected)
    for vo in selected:
      vo.selected(False)
    try:
      self.canvas.update_idletasks()
      tags = {vo.tag for vo in vos}
      items = [i for i in self.canvas.find_all() if tags.intersection(self.canvas.gettags(i))]
      w, h = copyImage(self.canvas, items)
      print(f"Copied a picture of {len(vos)} object{'' if len(vos) == 1 else 's'} ({w}\u00d7{h}), to paste into another program.")
    except Exception as ex:
      logger.error(f"Can't copy a picture: {ex}")
    finally:
      for vo in selected:
        if vo._isConnected():
          vo.selected(True, _multi=True)

  def onDeleteKey(self, event:tk.Event, fromModel:bool) -> str:
    '''
    Delete: erase what's selected from the view (see *doErase()*); Shift-Delete:
    remove it from the model (see *doRemove()*), after asking.

    :returns: "break"
    '''
    vos = [vo for vo in self.selected if vo._isConnected()]
    if not vos:
      return "break"
    if fromModel:
      self.doRemove(vos, confirm=True)
    else:
      self.doErase(vos)
    return "break"

  def doErase(self, vos:list[VObject]) -> None:
    '''
    Erase *vos* from this view (the model keeps their objects): one undo.
    '''
    vos = [vo for vo in vos if vo._isConnected()]
    if not vos:
      return
    try:
      self.context.erase(vos[0], others=vos[1:])
    except Exception as ex:
      logger.error(f"Can't erase: {ex}")

  def doEraseOthers(self, keep:list[VObject]) -> None:
    '''
    Erase everything but *keep* from this view (the model keeps their
    objects): one undo. Also kept are what *keep* needs to make sense (see
    *keptWith()*): the relations among the kept objects, the ends of the kept
    relations, and the context windows the kept objects are in. For working
    on a small part of a big view.
    '''
    from sn.view.graphics.vrelations import VRelation
    keep = [vo for vo in keep if vo._isConnected()]
    if not keep:
      return
    everything = [vo for vo in self.values() if vo is not None and vo._isConnected()]
    kept = {id(vo) for vo in keptWith(keep, everything,
                                      lambda vo: (vo.src, vo.dst) if isinstance(vo, VRelation) else None,
                                      lambda vo: vo.windowContents())}
    for vo in [vo for vo in self.selected if id(vo) not in kept]: # (out of the selection: else erasing one erases them all)
      vo.selected(False)
    # (the relations first: erasing a node takes its relations with it, so they'd be undone with it rather than on their own)
    self.doErase([vo for vo in everything if id(vo) not in kept and isinstance(vo, VRelation)] +
                 [vo for vo in everything if id(vo) not in kept and not isinstance(vo, VRelation)])

  def doRemove(self, vos:list[VObject], confirm:bool=False) -> None:
    '''
    Remove the model objects of *vos* from the model -- and so from every view
    of it: one undo. What can't be removed here is left, with a message: what
    the reasoner inferred (mark it asserted first), and what's in another
    model, or a write-locked one, or is a system object.

    :param confirm: Ask first (eg: for a key press, which is easily made by mistake).
    '''
    from tkinter import messagebox
    if not self.isModelEditor():
      logger.warning(f"Nothing's removed. {self.lockedReason()}")
      return
    mos:list[GraphObject] = []
    skipped:list[str] = []
    for vo in vos:
      mo = vo.modelObject
      if mo is None or any(mo is m for m in mos):
        continue
      if vo.isInferred() or mo.model is not self.model or mo.model.writeLocked() or vo._systemLocked():
        skipped.append(mo.name or type(mo).__name__)
      else:
        mos.append(mo)
    if skipped:
      logger.warning(f'Not removed (inferred, system, or in another model): {", ".join(skipped)}.')
    if not mos:
      return
    if confirm:
      what = f'"{mos[0].name}"' if len(mos) == 1 and mos[0].name else f"{len(mos)} objects"
      if not messagebox.askokcancel("Remove from model",
                                    f'Remove {what} from the model "{self.model.name}" -- and so from every view of it?\n\n(Undo puts {"it" if len(mos) == 1 else "them"} back.)',
                                    parent=self.canvas.winfo_toplevel()):
        return
    try:
      with CompositeCommandMgr(self.context):
        for mo in mos:
          self.context.remove(mo)
    except Exception as ex:
      logger.error(f"Can't remove: {ex}")

  PASTE_GAP = 40
  "The space (view units) left between pasted objects and what's beside them (see *_pasteOffset()*)."

  def _pasteOffset(self, boxes:list[list[int]], at:tuple[int, int]|None) -> tuple[int, int]:
    '''
    :param boxes: Where the pasted objects were (their bounding boxes).
    :param at: Where the top left of them all is to go, or None.
    :returns: How far to move them from where they were: to *at*; else not at
      all, if nothing's there now (eg: they were cut, or copied from another
      view); else the least distance to the right or down to where nothing is.
    '''
    if not boxes:
      return 0, 0
    x1, y1 = min(b[0] for b in boxes), min(b[1] for b in boxes)
    x2, y2 = max(b[2] for b in boxes), max(b[3] for b in boxes)
    if at is not None:
      return int(at[0] - x1), int(at[1] - y1)
    others = [vo.boundingBox() for vo in self.values() if vo is not None and vo._isConnected() and not vo.isHidden()]
    def free(dx:int, dy:int) -> bool: # (with room around it -- except where it was: what's near that was near it)
      g = self.PASTE_GAP // 2 if (dx, dy) != (0, 0) else 0
      return not any(b[0] < x2 + dx + g and x1 + dx - g < b[2] and b[1] < y2 + dy + g and y1 + dy - g < b[3] for b in others)
    w, h = int(x2 - x1) + self.PASTE_GAP, int(y2 - y1) + self.PASTE_GAP
    for k in range(50):
      for d in ((0, 0),) if k == 0 else ((k * w, 0), (0, k * h)):
        if free(*d):
          return d
    return w, 0

  def showPasted(self, clip:Any, made:list[GraphObject], at:tuple[int, int]|None=None) -> None:
    '''
    Show the objects just pasted (by *SNGContext.paste()*) as the view they were
    copied from showed them (see *copying.Clip.geometry*): the same sizes and
    layout -- a pasted rule's window with its contents in place -- moved
    together (see *_pasteOffset()*). What wasn't shown there (eg: an erased isa
    link) is shown, or not, as any new object is (see *update()*), but without
    asking for its name. Then what was asked to be copied is selected, so it
    can be dragged away at once.

    :param clip: What was pasted (a *copying.Clip*).
    :type clip: copying.Clip
    :param made: The new objects, by entry of *clip* (see *copying.pasteInto()*).
    :param at: Where to put the top left of them all (view coords), or None.
    '''
    from sn.view.graphics.vnodes import VNode
    pending = self.__dict__.setdefault("_pasting", {}) # (for update(): see there)
    for mo in made:
      pending[id(mo)] = mo
    dx, dy = self._pasteOffset([g["bb"] for g in clip.geometry.values()], at)
    shown:dict[int, VObject] = {}
    for i in sorted(range(len(made)), key=lambda i: clip.entries[i].kind != "node"): # (nodes first: they're relations' ends)
      mo, g = made[i], clip.geometry.get(i)
      if g is None:
        continue
      x1, y1, x2, y2 = g["bb"][0] + dx, g["bb"][1] + dy, g["bb"][2] + dx, g["bb"][3] + dy
      vo = self.findViewObjectForGraphObject(mo)
      if vo is None and isinstance(mo, Relation):
        vo = VRelation(cast("SNGView", self), mo, x=x1, y=y1, x1=x2, y1=y2, floating=g.get("floating"))
      elif vo is None:
        vo = VNode(cast("SNGView", self), mo, x=x1, y=y1, x1=x2, y1=y2)
      else: # (made already: an end of a relation shown before it)
        vo.boundingBox([x1, y1, x2, y2])
        if isinstance(vo, VRelation) and "floating" in g:
          vo._floatingAnchor = g["floating"]
      vo.userSized = g.get("userSized", False)
      if g.get("collapsed"):
        vo.collapsed, vo.expandedHeight = True, g.get("expandedHeight")
      if not g.get("filtered"):
        self._exemptIfFiltered(vo)
      shown[i] = vo
    def select() -> None:
      for s in self.selected.copy():
        s.selected(False)
      boxes = []
      for i in clip.selected:
        vo = shown.get(i)
        if vo is not None and vo._isConnected() and not vo.isHidden():
          vo.selected(True, _multi=True)
          boxes.append(vo.boundingBox())
      if boxes:
        self.scrollToShow([min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)])
    if self.canvas:
      self.canvas.after_idle(select)

  def scrollToShow(self, box:list[float], margin:int=20) -> None:
    '''
    Scroll the canvas, if need be, so that *box* is in sight -- the least it
    takes (as much of it as fits, from its top left).

    :param box: A rectangle, in view coords.
    :param margin: Room to leave around it (canvas pixels).
    '''
    c = self.canvas
    self.resetScrollRegion()
    x1, y1, x2, y2 = self.viewToWindow(*box)
    left, top = c.canvasx(0), c.canvasy(0)
    right, bottom = left + c.winfo_width(), top + c.winfo_height()
    sr = self.scrollRegion
    def start(lo:float, hi:float, a:float, b:float, size:float) -> float|None: # (where the visible lo..hi should start, to show a..b)
      if lo <= a and b <= hi:
        return None
      return a - margin if a < lo or b - a + 2 * margin > size else b + margin - size
    if (x := start(left, right, x1, x2, right - left)) is not None:
      c.xview_moveto(max(0.0, (x - sr[0]) / max(1, sr[2] - sr[0])))
    if (y := start(top, bottom, y1, y2, bottom - top)) is not None:
      c.yview_moveto(max(0.0, (y - sr[1]) / max(1, sr[3] - sr[1])))

  def findAGoodLocation(self, mObject:GraphObject) -> tuple[int,int]:
    '''
    :returns: Where to start looking for a place for a new view object for
      *mObject* (see *_newObjectLocation()*).
    '''
    x, y, _ = self._newObjectLocation(mObject)
    return x, y

  def _newObjectLocation(self, mObject:GraphObject) -> tuple[int, int, "VObject|None"]:
    '''
    Where to start looking for a place for a new view object for *mObject*
    (the nearest free place to it is used: see *makeViewObjectForGraphObject()*):
    where the background menu making it was asked for, if it was; else just
    below its (first) supertype, if that's shown; else at the cursor.

    :returns: (x, y, and the supertype's view object, if it's below that).
    '''
    if self._newAt is not None and mObject.isa(self._newAt[2]): # (once: see makeMenu())
      x, y, _ = self._newAt
      self._newAt = None
      return x, y, None
    mParents = mObject.getParents()
    mParent = mParents[0] if len(mParents) > 0 else None
    vParent = self.findViewObjectForGraphObject(mParent) if mParent is not None else None
    if vParent is None or vParent.isHidden() or vParent.isContextWindow():
      x, y = self.cursorViewPoint()
      return x, y, None
    bb = vParent.boundingBox()
    return int(bb[0]), int(bb[3] + self.NEW_BELOW_GAP), vParent

  NEW_BELOW_GAP = 40
  "How far below its supertype (view units) a new object is put (see *_newObjectLocation()*)."

  def cursorViewPoint(self) -> tuple[int, int]:
    '''
    :returns: The graphics cursor's position in view coordinates (ie: allowing
      for the canvas's scroll position and the zoom). If the cursor isn't over
      the canvas (eg: the command came from the text terminal), the top-left
      of the visible part of the canvas instead, so the result is on screen.
      (0, 0) if there's no canvas.
    '''
    if not self.canvas:
      return 0, 0
    c = self.canvas
    # pointer position relative to the canvas widget
    wx = c.winfo_pointerx() - c.winfo_rootx()
    wy = c.winfo_pointery() - c.winfo_rooty()
    if not (0 <= wx < c.winfo_width() and 0 <= wy < c.winfo_height()):
      wx, wy = 20, 20
    x, y = self.windowToView(c.canvasx(wx), c.canvasy(wy))
    return int(x), int(y)

  def _attachDanglingEnds(self, vo:VObject) -> None:
    '''
    *vo* has just been added to the view: relations already here whose own
    endpoint is *vo*'s model object, but which were left dangling because it
    wasn't shown (eg: top -- see *VRelation._resolveEnd()* -- or an erased
    object), attach to it.
    '''
    from sn.view.graphics.vrelations import VRelation
    if not vo._isConnected() or vo.modelObject is None: # (gone again meanwhile)
      return
    for r in list(self._db.values()):
      # skip anything not fully constructed (a relation that's still being made
      # resolves its own ends)
      if not isinstance(r, VRelation) or r is vo or r.modelObject is None or not r._isConnected() \
         or not hasattr(r, "_floatingAnchor") or not hasattr(r, "_drawVersion"):
        continue
      try:
        changed = False
        rel = cast(Relation, r.modelObject)
        for end in ("src", "dst"):
          own = rel.localSrc if end == "src" else rel.localDst
          if own is vo.modelObject and getattr(r, end) is None:
            setattr(r, end, vo)
            changed = True
        if changed:
          self.freshPaint()
          r.draw()
      except Exception:
        logger.exception(f"_attachDanglingEnds(): attaching {r} to {vo}:")

  def showAllModel(self):
    x:int = 10
    y:int = 10
    minSize = snPrefs.get('gui/NodeMinSize', storeDefault=30, storeType=int)
    assert isinstance(minSize, (int,float))
    sizex:int = int(minSize)
    aspectRatio = snPrefs.get('gui/NodeAspectRatio', storeDefault=1.5, storeType=float)
    assert isinstance(aspectRatio, (int,float))
    sizey:int = int(sizex * float(aspectRatio))
    grid = (sizex * 2, sizey * 2)
    numNodes = len(self.model) - len(self)
    gridCount = int(sqrt(numNodes)) if numNodes>0 else 0
    blockSize = gridCount * grid[1] + y
    def nextPoint() -> tuple[int, int]:
      nonlocal x, y
      p = (x, y)
      if y < blockSize:
        y += grid[1]
      else:
        x += grid[0]
        y = 10
      return p
    # what's made along the way (eg: a relation's end from a super-model) goes on the grid too: not to the
    # nearest free place (see _placeNew()), a search that's very slow in a crowded big view
    self.__dict__["_nextGridPoint"] = nextPoint
    try:
      for mnode in self.model.values():
        if self.isFiltered(mnode):
          continue
        vObj = self.findViewObjectForGraphObject(mnode)
        if vObj is None:
          n = self.makeViewObjectForGraphObject(mnode, atPoint=nextPoint())
          self.localLayout(n)
    finally:
      del self.__dict__["_nextGridPoint"]

  def search(self, pattern:str, wholeWord:bool=False, matchCase:bool=False, regex:bool=False,
             wholeModel:bool=False, superModels:bool=False,
             confirm:Callable[[int], bool]|None=None) -> tuple[list[VObject], int]:
    '''
    Highlight the nodes and relations in the view whose names match *pattern*
    (see *sn.model.model.nameMatcher()*) -- not isa links, nor those not drawn
    just now (see *VObject.isHidden()*) -- replacing any earlier highlights,
    and scroll to show them. With *wholeModel*, those in the model (and, with
    *superModels*, its super-models) that aren't in the view are shown first
    (one undoable command: see *represent()*), even if they're in a hidden or
    erased category; and so are any of those in the view in such a category.

    :param pattern: What to look for in names.
    :param wholeWord: See *nameMatcher()*.
    :param matchCase: See *nameMatcher()*.
    :param regex: See *nameMatcher()*.
    :param wholeModel: Look in the model too, and show what's found.
    :param superModels: With *wholeModel*: in its super-models too.
    :param confirm: With *wholeModel*: asked, with how many objects would be
      shown, whether to show them (eg: there are a lot); None: they are.
    :returns: The view objects highlighted, and how many were shown.
    :raises re.error: If *regex* and *pattern* isn't a good regular expression.
    '''
    from sn.model.model import nameMatcher
    matches = nameMatcher(pattern, wholeWord=wholeWord, matchCase=matchCase, regex=regex)
    found:list[GraphObject] = []
    brought = 0
    if wholeModel:
      found = self.model.search(pattern, wholeWord=wholeWord, matchCase=matchCase, regex=regex, superModels=superModels)
      shown = self._shownModelObjects()
      missing = sorted((o for o in found if id(o) not in shown), key=lambda o: isinstance(o, Relation)) # (nodes first)
      if missing and (confirm is None or confirm(len(missing))):
        self.context.represent(missing)
        brought = len(missing)
    self.clearHighlights()
    ret:list[VObject] = []
    for vo in list(self.values()):
      mo = vo.modelObject if vo is not None else None
      if mo is None or isinstance(mo, IsaIndividual) or not vo._isConnected() or not matches(str(mo.name)):
        continue
      if wholeModel and vo.isHidden():
        self._exemptIfFiltered(vo)
      if not vo.isHidden():
        vo.highlight(True)
        ret.append(vo)
    if ret and self.canvas:
      def show() -> None: # (once anything just shown is placed: see makeViewObjectForGraphObject())
        boxes = [vo.boundingBox() for vo in ret if vo._isConnected()]
        if boxes:
          self.scrollToShow([min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)])
      self.canvas.after_idle(show)
    return ret, brought

  def openSearchDialog(self) -> None:
    '''
    "Edit | Find...": open this view's search dialog (see
    *sn.view.graphics.searchDialog.SearchDialog*), or bring it to the front.
    '''
    from sn.view.graphics.searchDialog import SearchDialog
    d = self.__dict__.get("_searchDialog")
    if d is not None and d.winfo_exists():
      d.bringToFront()
    else:
      self.__dict__["_searchDialog"] = SearchDialog(cast("SNGView", self))

  def makeRelationFrom(self, node:VObject, typ:Optional[Relation]=None):
    '''
    :param node: [VObject]
    '''
    assert isinstance(node, VObject)
    
    def callback(originNode:VObject, selNode:VObject, typ):
      if selNode is not None:
        logger.debug(f"making relation from {originNode} to {selNode} of type {typ}.")
        self.makeRelation(originNode, selNode, typ)
      else:
        logger.debug("Relation's toNode must match the being a node/relation with the from Node.")
      
    
    if typ is None or (isinstance(typ, Relation) and typ.isType()):
      # Dropped on empty space: a relation with no destination of its own -- it
      # inherits its type's range ("John -has-> <some phone>"). Not for isa:
      # an isa link needs both ends.
      onEmpty = None if typ is None or typ is self.model.ISA else \
        (lambda orig, typ=typ: self.makeRelation(orig, None, typ))
      self.elasticLineChoice(node, 
                             callback=lambda orig, sel, typ=typ: callback(orig, sel, typ), #type: ignore[misc]
                             arrowHeads=2, color="blue", onEmpty=onEmpty)
    else:
      if not isinstance(typ, Relation):
        raise TypeError(f'SNView.makeRelationFrom(): "typ" argument must be a model Relation; got object of class {type(typ).__name__}.')
      else:
        raise TypeError(f'SNView.makeRelationFrom(): "typ" argument "{typ.name}" must be type, not an individual;.')

  def makeRelation(self, fromNode:VObject, toNode:VObject|None, typ:Relation):
    '''
    Make an individual relation of type *typ* from *fromNode* to *toNode* --
    or, if *toNode* is None, with no destination of its own (so it inherits
    *typ*'s range: it's drawn to that, faded, or dangling if that's top).
    '''
    assert isinstance(fromNode, VObject)
    assert toNode is None or isinstance(toNode, VObject)
    # Relations may connect nodes and relations in any combination (eg: a rule
    # -antecedent-> a relation) -- except isa links: a node isa a relation (or
    # vice versa) is an error.
    if toNode is not None and typ is self.model.ISA and isinstance(fromNode, VRelation) != isinstance(toNode, VRelation):
      logger.error("An isa link must be between two nodes or two relations.")
      return
    if typ and not isinstance(typ, Relation):
      logger.error(f'Relation typ {typ["label"]} must be a relation.', level='error')
      return
    for end in (fromNode, toNode): # (the reasoner's: see GraphObject.inferred)
      if end is not None and end.isInferred():
        logger.error(f'"{end.name}" is inferred: mark it as asserted to relate it.')
        return
    try:
      with CompositeCommandMgr(self.context) as mgr: # (one undo, with any containment it lands in)
        self.context.new_relation([typ], individual=True, destination=None if toNode is None else toNode.modelObject,
                                  source=fromNode.modelObject, model=self.model)
        if toNode is not None and mgr.commands:
          self._containNewRelation(mgr, mgr.commands[-1], typ, fromNode, toNode)
    except Exception:
      logger.exception("SNView.makeRelation():")

  def _askName(self, mo:GraphObject) -> None:
    '''
    Ask for a new object's name (and anything else about it), in the
    attribute editor -- unless it's gone (eg: undone).
    '''
    if getattr(self, "_closed", False) or not mo._isConnected():
      return
    applyEditAttrsBox(self.canvas, mo, title=mo.name, editKey="name")
    # a variable's name may be typed with constraints: "?p :where: alive" (see sn.model.constraints)
    if WHERE in mo.name:
      self._applyWhere(mo)
