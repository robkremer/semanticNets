'''
A graphical view's mouse, keys and menus (*InputMixin*): one of the parts of
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
from sn.model.model import Relation
from functools import partial
from typing import Optional, Callable, Any
from util.utils import s_SHIFT, bindRightMouse, s_ALT, flattenPairs, s_CMD, s_CTL, normalizeRect, eventEqual, wheelEvents, wheelSteps
from util.platformSupport import MAC, shortcut
from sn.view.graphics.vobjects import VObject
from sn.view.graphics.vrelations import VRelation
from sn.view.graphics.viewBase import KEY_ERASE, KEY_FIND, KEY_ZOOM_IN, KEY_ZOOM_FIT, KEY_ZOOM_NORMAL, KEY_REDO, KEY_COPY_IMAGE, KEY_REMOVE, KEY_VALIDATE, KEY_ZOOM_OUT, KEY_CLEAR_HIGHLIGHTS, KEY_COPY, KEY_PASTE, KEY_REPAINT, KEY_SELECT_ALL, KEY_CUT, KEY_UNDO, VKEY_VALIDATE
from collections import namedtuple
from sn.view.graphics.viewBase import ViewBase
from typing import TYPE_CHECKING
if TYPE_CHECKING:
  from sn.view.graphics.sngView import SNGView

logger:sn.SNLogger = sn.getLogger(__name__)

class InputMixin(ViewBase):
  '''
  What a view (*sn.view.graphics.sngView.SNGView*) does with the mouse and keys:
  its bindings; pressing, dragging and releasing (selecting, the drag-select
  box, panning, Option-drag zooming, grabbing a relation's terminal); the
  elastic line that picks something for a command; the mouse wheel; and the
  view's pop-up menus.
  '''

  # (set up by SNGView.__init__(), which says what they are)
  _eventHandled: Optional[tk.Event]
  _elasticLineChoiceData: SNGView.ElasticLineChoiceData|None
  _selectionBoxInfo: list[Any]|None
  _cursorBeforeTerminal: str
  _scrolling: bool
  _panned: bool
  _panClicked: VObject|None
  _cursorBeforePan: str
  _dragZoom: tuple[int, float, list[float], int, int]|None

  ElasticLineChoiceData:tuple[VObject, int, Callable[[VObject],bool], Callable[[VObject,VObject],Any]] \
            = namedtuple('ElasticLineChoiceData', 'originNode lineID filter callback onEmpty', defaults=(None,))

  def makeBindings(self):
    '''
    Create the bindings for the *Canvas* object.
    '''
    self.canvas.bind("<Enter>", self.onEnter)
    
    # For making relations
    self.canvas.bind("<B1-ButtonRelease>", self.onB1_ButtonRelease)
    self.canvas.bind("<Motion>", self.onMotion)

    # for popup menu
    bindRightMouse(self.canvas, self.onRightMouse)  # lambda e: self.backgroundMenu(e).post(e.x_root, e.y_root))

    # scroll using mouse click-and-drag
    self.canvas.bind("<Button-1>", self.onButton_1)
    self.canvas.bind("<B1-Motion>", self.onB1_Motion)
    # # scroll using two-finger drag
    for sequence in wheelEvents():
      self.canvas.bind(sequence, self.onMouseWheel)
    for sequence in wheelEvents(shift=True):
      self.canvas.bind(sequence, self.onShift_MouseWheel)
    #
    # undo/redo
    self.canvas.bind(KEY_UNDO[0], self.onUndo)
    self.canvas.bind(KEY_REDO[0], self.onRedo)
    
    # cut, copy and paste
    self.canvas.bind(KEY_CUT[0], lambda e: self.onEditKey(e, "cut"))
    self.canvas.bind(KEY_COPY[0], lambda e: self.onEditKey(e, "copy"))
    self.canvas.bind(KEY_PASTE[0], lambda e: self.onEditKey(e, "paste"))
    self.canvas.bind(KEY_COPY_IMAGE[0], lambda e: self.onEditKey(e, "copy image"))
    self.canvas.bind(KEY_SELECT_ALL[0], lambda e: self.onEditKey(e, "select all"))
    for key in KEY_ERASE:
      self.canvas.bind(key, lambda e: self.onDeleteKey(e, fromModel=False))
    for key in KEY_REMOVE:
      self.canvas.bind(key, lambda e: self.onDeleteKey(e, fromModel=True))

    # repaint
    self.canvas.bind(KEY_REPAINT[0], self.repaint)
    for key, action in ((KEY_ZOOM_IN[0], self.zoomIn), (shortcut("plus")[0], self.zoomIn), (KEY_ZOOM_OUT[0], self.zoomOut),
                        (KEY_ZOOM_NORMAL[0], lambda: self.zoomAbout(1.0)), (KEY_ZOOM_FIT[0], self.zoomToFit)):
      self.canvas.bind(key, lambda _e, a=action: a()) # type: ignore[misc]

    # abandon an elastic-line choice (or, if there's none, clear the highlights)
    self.canvas.bind(KEY_CLEAR_HIGHLIGHTS[0], self.cancelElasticLine)

    # find objects by name
    self.canvas.bind(KEY_FIND[0], lambda _e: self.openSearchDialog())

    # validate (debugging)
    self.canvas.bind(KEY_VALIDATE[0], lambda _e: self.onValidateKey())
    if MAC:
      self.canvas.bind("<Option-KeyPress>", self.onOptionKey) # (Option-V by the key, whatever the layout types: see VKEY_VALIDATE)

  def onOptionKey(self, event:tk.Event) -> str|None:
    '''
    An Option key press that no more particular binding took: Option-V (by its
    virtual key code, which Tk on macOS puts in the top byte of *event.keycode*)
    validates the view.

    :returns: "break" if it was Option-V.
    '''
    state = int(event.state)
    if (event.keycode >> 24) & 0xFF == VKEY_VALIDATE and not (s_CMD(state) or s_CTL(state) or s_SHIFT(state)):
      return self.onValidateKey()
    return None

  def onValidateKey(self) -> str:
    '''
    Validate the view (and repaint it, if something's wrong), as the "validate"
    menu item does.

    :returns: "break"
    '''
    self.validate(refresh=True)
    return "break"

  def onEnter(self, _event:tk.Event) -> None:
    '''
    Give this *Canvas* Tk keyboard focus whenever the mouse enters it.

    All of this class's key bindings (KEY_UNDO, KEY_REDO, KEY_REPAINT, ...)
    are bound directly on *self.canvas* -- like any Tk widget-level binding,
    those only fire while the canvas itself holds keyboard focus, and
    nothing else in this window (e.g. clicking into the canvas, as opposed
    to some other widget such as the terminal) ever calls *focus_set()* on
    it. Without this, the canvas can easily end up never holding focus at
    all, so a key like Cmd-Z is delivered nowhere and its binding never
    fires, even though the binding itself is set up correctly. This mirrors
    the equivalent binding in the older, now-superseded *sn.view.graphics.
    view.SNView* (see its own *onEnter()*), which was dropped somewhere
    along the way when this class superseded it.

    :param _event: The Tk *<Enter>* event (unused).
    '''
    self.canvas.focus_set()

  def onUndo(self, event:tk.Event):
    '''
    :param event: The Tk event.
    '''
    self.context.undo()
    self.addEventHandled(event)

  def onRedo(self, event:tk.Event):
    '''
    :param event: The Tk event.
    '''
    self.context.redo()
    self.addEventHandled(event)

  def onMotion(self, event:tk.Event) -> None:
    """
    :param event: *event.x* and *event.y* contain the x,y coordinate of the click.
    :return: None
    
    If there's a _elasticLineChoiceData going on (elastic line), then continue the
    animation. 

    Called on the *<Motion>* event (when the mouse moves with no buttons pressed).
    Note that selection boxes and scrolling are handled by *self.onB1_Motion()*.

    * Check if the event has been handled by a contained widget. If it has been,
      call *self.removeEventHandled()* and return.

    * If *self._makingRelaionFrom* is not *None*, redraw the "making relation" line.
    """
    if self.isEventHandled(event):
      self.removeEventHandled(event)
      return None
    # if self._makingRelationFrom is not None:
    #   self.canvas.coords(self._makingRelationFrom.lineID,
    #         flattenPairs([self.viewToWindow(self._makingRelationFrom.node.centerPt()),
    #                   (self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))]))
    if self._elasticLineChoiceData is not None:
      self._trackElasticLine(event)
      return
    self._updateTerminalCursor(event)

  TERMINAL_CURSOR = "center_ptr"
  "The cursor shown while the pointer is over a relation terminal that can be dragged to a new src/dst."

  def _relationTerminalNear(self, x:float, y:float) -> VRelation|None:
    '''
    :param x: Canvas (window) coordinates.
    :param y: See *x*.
    :returns: An editable relation with a terminal within reach of (x, y) --
      ie: one that a press there would grab (see *VRelation.grabTerminal()*)
      -- or None. Only objects drawn near (x, y) are examined.
    '''
    r = VRelation.TERMINAL_HIT_RADIUS
    items = self.canvas.find_overlapping(x - r, y - r, x + r, y + r)
    if not items:
      return None
    # Match on each object's own *tag* rather than parsing an id out of it: a
    # tag is fixed when the object is created, and loading a view from a file
    # can give the object a different id afterwards.
    byTag = {vo.tag: vo for vo in self._db.values() if vo is not None}
    candidates:dict[int, VRelation] = {}
    for item in items:
      for tag in self.canvas.gettags(item):
        vo = byTag.get(tag)
        if vo is not None:
          if isinstance(vo, VRelation):
            candidates[id(vo)] = vo
          else: # a node: a terminal of its relations may be on its edge
            for rel in vo.relations:
              candidates[id(rel)] = rel
    for rel in candidates.values():
      if rel._endpointsEditable() and rel._terminalAt(x, y) is not None:
        return rel
    return None

  def grabTerminalNear(self, event:tk.Event) -> bool:
    '''
    If a button-1 press is within reach of an editable relation's terminal --
    whatever's under it: the object the relation connects, a context window
    it's drawn in, or the background -- grab that terminal (see
    *VRelation.grabTerminal()*).

    :param event: The Tk event.
    :returns: True iff it did (so the caller shouldn't start its own drag).
    '''
    rel = self._relationTerminalNear(self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))
    return rel is not None and rel.grabTerminal(event)

  HANDLE_CURSORS = {"nw": "top_left_corner", "ne": "top_right_corner",
                    "se": "bottom_right_corner", "sw": "bottom_left_corner"}
  "The cursors shown over a selected object's corner (resize) handles."

  def _handleNear(self, x:float, y:float) -> str|None:
    '''
    The corner of the selected object\'s resize handle at canvas (x, y), or None.
    '''
    from sn.view.graphics.decorators import Selected
    for obj in self.selected:
      sel = obj.decorators.get("selected") if obj.decorators else None
      if isinstance(sel, Selected):
        corner = sel.handleAt(x, y)
        if corner is not None:
          return corner
    return None

  def _updateTerminalCursor(self, event:tk.Event) -> None:
    '''
    Show a corner cursor (*HANDLE_CURSORS*) over a resize handle, or
    *TERMINAL_CURSOR* over a draggable relation terminal, restoring whatever
    cursor was there before (eg: the "hand" a node's *onEnter()* set) when the
    pointer moves off.

    :param event: The Tk event.
    '''
    x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
    corner = self._handleNear(x, y)
    if corner is not None:
      want:str|None = self.HANDLE_CURSORS[corner]
    elif self._relationTerminalNear(x, y) is not None:
      want = self.TERMINAL_CURSOR
    else:
      want = None
    ours = {self.TERMINAL_CURSOR, *self.HANDLE_CURSORS.values()}
    current = str(self.canvas.cget("cursor"))
    if want is not None:
      if current != want:
        if current not in ours:
          self._cursorBeforeTerminal = current # (an item's <Enter>/<Leave> may have changed it meanwhile)
        self.canvas.configure(cursor=want)
    elif current in ours:
      self.canvas.configure(cursor=self._cursorBeforeTerminal or "arrow")

  def _trackElasticLine(self, event:tk.Event) -> None:
    '''
    Stretch the elastic line (see *elasticLineChoice()*) to the cursor.

    :param event: The Tk event.
    '''
    assert self._elasticLineChoiceData is not None
    self.canvas.coords(self._elasticLineChoiceData.lineID,
          flattenPairs([self.viewToWindow(self._elasticLineChoiceData.originNode.centerPt()),
                    (self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))]))

  def onButton_1(self, event):
    """
    :param event: *event.x* and *event.y* contain the x,y coordinate of the click.
    :return: *None*
    
    If the SHIFT or COMMAND key is pressed: start a drag-scroll (panning the
    view -- with COMMAND, over objects too: they leave the press to the
    canvas, see *VObject.onButton_1()*). If the OPTION key is: start a
    drag-zoom (over objects too), up to zoom in, down to zoom out, about
    where it was pressed (see *ZOOM_DRAG*). Otherwise, unselect 
    everything and prepare for a possible selection box animation (if we get a 
    move event).

    Called on the *<Button-1>* event (when the mouse button 1 is pressed).

    * If *self._makeRelationFrom* is not *None*, return.

    * Check if the event has been handled by a contained widget. If it has been,
      call *self.removeEventHandled()* and return.

    * If the shift or command key is pressed start a scroll action and return.

    * If the option key is pressed start a zoom action and return.

    * Otherwise unselect everything and start a selection box action by setting
      up *self._selectionBoxInfo*.
    """
    # ignore if making a relation
    # if self._makingRelationFrom is not None: return
    if self._elasticLineChoiceData is not None: return

    # check of a widget has handled the event
    if self.isEventHandled(event):
      self.removeEventHandled(event)
      return None

    # a relation's terminal, over the background (see grabTerminalNear())
    if not (s_SHIFT(event.state) or s_CMD(event.state) or s_ALT(event.state)) and self.grabTerminalNear(event):
      self.removeEventHandled(event)
      return None

    # option-Button1 down: zoom
    if s_ALT(event.state):
      self._panClicked = None
      self._cursorBeforePan = str(self.canvas.cget("cursor")) or "arrow"
      self.canvas.configure(cursor="sb_v_double_arrow")
      at = self.windowToView(self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))
      self._dragZoom = (event.y, self._scale, at, event.x, event.y)
      return

    # shift- or cmd-Button1 down: scroll (pan the view)
    if s_SHIFT(event.state) or s_CMD(event.state):
      self._scrolling = True
      self._panned = False
      if not s_CMD(event.state): self._panClicked = None # (a Shift-click toggles nothing)
      self._cursorBeforePan = str(self.canvas.cget("cursor")) or "arrow"
      self.canvas.configure(cursor="fleur")
      self.canvas.scan_mark(event.x, event.y)
      return

    # plain Button1 down: multi-select box
    for s in self.selected.copy():  # unselect everything
      s.selected(False)
    # 0:rect, 1:canvas-x, 2:canvas-y, 3:activated
    # (canvasx()/canvasy() already give canvas coordinates -- scrolled and zoomed,
    # like the drawn items -- so no viewToWindow() here: that zoomed it twice)
    x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
    self._selectionBoxInfo = [
        self.canvas.create_rectangle(x, y, x, y, fill="", width=3, outline="blue", dash=(1,6)),
        x,
        y,
        False]

  def onB1_Motion(self, event):
    """
    :param event: *event.x* and *event.y* contain the x,y coordinate of the click.
    :return: None
    
    If we are either drag-scrolling or drag-drawing a multi-selection
    box, continue the action.

    Called on the *<B1-Motion>* event (when the mouse moves with button1 pressed).

    * Check if the event has been handled by a contained widget. If it has been,
      call *self.removeEventHandled()* and return.

    * If *self._scrolling* is not *None*, call *self.scan_dragto()*.

    * If *self._selectionBoxInfo* is not *None*, redraw the elastic selection box,
      using *self._selectionBoxInfo[3]* to note that the selection box is active.
    """
    try:
      # check of a widget has handled the event
      if self.isEventHandled(event):
        self.removeEventHandled(event)
        return None
  
      # an elastic line started by a press-and-drag (eg: grabbing a relation's
      # terminal -- see VRelation.onButton_1()) follows the drag
      if self._elasticLineChoiceData is not None:
        self._trackElasticLine(event)
        return

      # continue zooming: by ZOOM_DRAG for each 100 pixels up, keeping the
      # pressed-on point under where it was pressed
      if self._dragZoom is not None:
        y0, scale0, at, wx, wy = self._dragZoom
        scale = min(self.MAX_ZOOM, max(self.MIN_ZOOM, scale0 * self.ZOOM_DRAG ** ((y0 - event.y) / 100)))
        if abs(scale - self._scale) > 1e-6:
          self.zoom(scale)
          self.resetScrollRegion()
          self._scrollToPut(at, wx, wy)
        return

      # continue scrolling
      if self._scrolling:
        self.canvas.scan_dragto(event.x, event.y, gain=1)
        self._panned = True
        return
  
      # adjust selection box
      if self._selectionBoxInfo is not None:
        self._selectionBoxInfo[3] = True # activated
        bb = normalizeRect([self._selectionBoxInfo[1], self._selectionBoxInfo[2], self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)])
        self.canvas.coords(self._selectionBoxInfo[0], bb)
    except:
      logger.exception("SNView.onB1_Motion()")

  def elasticLineChoice(self, originNode:VObject, 
                        callback:Callable[[VObject, VObject], Any],
                        filter:Callable[[VObject],bool]=lambda x: True, 
                        arrowHeads:int=2, color:str="cyan",
                        onEmpty:Callable[[VObject], Any]|None=None):
    '''
    Animate an elastic line from the *originNode* to the cursor to select an
    object for which *filter* returns True, then call *callback* with the *originNode*
    and the selected object.
    
    :param originNode: The object to root the elastic line one (and used as the first
      parameter to *callback*.
    :param callback: The method to call after a selected selection.
    :param filter: Objects are only selected if *filter(<obj>)* returns True. 
      [Optional, default=always True]
    :param arrowHeads: 0=no arrowheads, 1=arrowhead at the origin, 2=arrowhead
      at the cursor, 3=arrowhead at both ends. For anything larger, just he lowest
      2 bits will be used. [Optional, default=2]
    :param onEmpty: If given, called with *originNode* when the line is dropped
      on empty space (no object at all under the cursor); otherwise that
      abandons the choice, as Escape always does (see *cancelElasticLine()*).
    '''
    assert isinstance(originNode, VObject)
    arrowHeads %= 4 # strip any high bits
    match arrowHeads:
      case 1: arrow = tk.FIRST
      case 2: arrow = tk.LAST
      case 3: arrow = tk.BOTH
      case _: arrow = tk.NONE
    lineID = self.canvas.create_line( #type: ignore[call-overload]
      self.viewToWindow(flattenPairs([originNode.centerPt(), originNode.centerPt()])),
      fill=color, width=3, arrow=arrow)
    self._elasticLineChoiceData = self.ElasticLineChoiceData(originNode, lineID, filter, callback, onEmpty)
    self.canvas.focus_set() # so Escape reaches us (see cancelElasticLine())

  def cancelElasticLine(self, event:tk.Event|None=None) -> None:
    '''
    Abandon an elastic-line choice in progress (bound to Escape) -- or, if there is none, clear the highlights.

    :param event: The Tk event.
    '''
    if self._elasticLineChoiceData is not None:
      self.canvas.delete(self._elasticLineChoiceData.lineID)
      self._elasticLineChoiceData = None
    else:
      self.clearHighlights()

  def clearHighlights(self) -> None:
    'Remove every object\'s highlight glow (see *VObject.highlight()*).'
    for vo in list(self._db.values()):
      if vo is not None and getattr(vo, "decorators", None) is not None:
        vo.highlight(False)

  def onB1_ButtonRelease(self, event:tk.Event) -> None:
    """
    :param event: *event.x* and *event.y* contain the x,y coordinate of the click.
    :return: None
    
    Depending on the context, finish creating a Relation or create a selection
    set from the selection box that just finished.

    * Check if the event has been handled by a contained widget. If it has been,
      call *self.removeEventHandled()* and return.

    * Set *self._scrolling* to *None*.

    * If *self._makingRelaionFrom* is not *None*:

      * Create a link according to the data in the *makeRelationData* structure
        and the *event*'s x,y coordinates

      * set *self._elasticLineChoiceData* to *None*.

    * If *self._selectionBoxInfo* is not *None*: This means we have finished
      drawing a selection box, so

      * deselect everything,

      * select everthing in the selection box, and

      * set *self._selectionBoxInfo* to *None*.
    """
    if self._dragZoom is not None: # a drag-zoom's done
      self._dragZoom = None
      self.canvas.configure(cursor=self._cursorBeforePan)
      self.removeEventHandled(event)
      return None
    if self._scrolling: # a drag-scroll's done; a Cmd-click that never moved toggles what it was on
      self._scrolling = False
      self.canvas.configure(cursor=self._cursorBeforePan)
      clicked, self._panClicked = self._panClicked, None
      if not self._panned and clicked is not None:
        clicked.selected(not clicked.selected(), _multi=True)
      self.removeEventHandled(event)
      return None
    self._panClicked = None
    if self.isEventHandled(event):
      self.removeEventHandled(event)
      return None
    
    # Handle elastic line object selection for making a Relation
    if self._elasticLineChoiceData is not None:
      self.canvas.delete(self._elasticLineChoiceData.lineID)
      # what's actually under the cursor (a small halo, not find("closest"),
      # which always returns *something*, however far away: dropping on empty
      # space must choose nothing)
      cx, cy = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
      ids = self.canvas.find_overlapping(cx - 2, cy - 2, cx + 2, cy + 2)
      typeList:list[VObject] = [n for n in self._db.values() \
                                if (self._elasticLineChoiceData.filter(n) \
                                    if self._elasticLineChoiceData.filter is not None \
                                    else True)] 
      # the topmost one: eg: an object in a context window, not the window
      # (find_overlapping() gives the items bottom to top)
      byTag = {n.tag: n for n in typeList if n is not None}
      item = next((byTag[tag] for _id in reversed(ids) for tag in self.canvas.gettags(_id) if tag in byTag), None)
      self.canvas.delete(self._elasticLineChoiceData.lineID)
      if item is not None:
        self._elasticLineChoiceData.callback(self._elasticLineChoiceData.originNode, item)
      else:
        under = [n for n in self._db.values() if n is not None
                 and any(n.tag in self.canvas.gettags(_id) for _id in ids)]
        if under:
          logger.warning(f'"{under[0].name}" can\'t be chosen here.')
        elif self._elasticLineChoiceData.onEmpty is not None:
          self._elasticLineChoiceData.onEmpty(self._elasticLineChoiceData.originNode)
        else:
          logger.debug("Elastic line choice: nothing under the cursor; cancelled.")
      self._elasticLineChoiceData = None
      return
      
    # Handle a multi-selection box
    if self._selectionBoxInfo is not None:
      bb = self.canvas.coords(self._selectionBoxInfo[0])
      ids = tuple(self.canvas.find("overlapping", bb[0], bb[1], bb[2], bb[3]) if len(bb) == 4 else [])
      for s in self.selected.copy():  # unselect everything
        s.selected(False)
      for _id in ids:
        for n in self.values():  # self.nodes()+self.relations():
          if n is not None and n._shape.id == _id:
            n.selected(True, _multi=True)
      self.canvas.delete(self._selectionBoxInfo[0])
      self._selectionBoxInfo = None

  def onMouseWheel(self, event):
    """
    :param event: *event.delta* contains the scroll offset.
    :return: None
    
    Y-axis scroll.

    Called on the two finger touchpad Y-scroll event.

    * Check if the event has been handled by a contained widget. If it has been,
      call *self.removeEventHandled()* and return.

    * Call *self.canvas.yview_scroll)*.
    """
    if self.isEventHandled(event):
      self.removeEventHandled(event)
      return None
    self.canvas.yview_scroll(self._wheelUnits(event), 'units')

  def onShift_MouseWheel(self, event):
    """
    :param event: *event.delta* contains the scroll offset.
    :return: None
    
    X-axis scroll.

    Called on the two finger touchpad X-scroll event.

    * Check if the event has been handled by a contained widget. If it has been,
      call *self.removeEventHandled()* and return.

    * Call *self.canvas.xview_scroll)*.
    """
    if self.isEventHandled(event):
      self.removeEventHandled(event)
      return None
    self.canvas.xview_scroll(self._wheelUnits(event), 'units')

  @staticmethod
  def _wheelUnits(event:tk.Event) -> int:
    '''
    :returns: How many units a wheel event scrolls the view: on the Mac, its
      *delta* (as it always has); elsewhere, 3 lines a notch, the wheel moved
      up scrolling up (see *util.utils.wheelSteps()*).
    '''
    return int(event.delta) if MAC else -3 * wheelSteps(event)

  def isEventHandled(self, event:tk.Event) -> bool:
    """
    :param event: The event to test.
    :returns: *True* iff *event* is the same physical event most recently
      passed to *addEventHandled()* (and not yet cleared by
      *removeEventHandled()*).

    A canvas item's ``tag_bind`` callback and this canvas widget's own
    ``bind`` callback are dispatched independently by Tk, even for the
    exact same physical click -- returning ``"break"`` from the item's
    callback only suppresses *other item bindings*, not this canvas's own
    separate widget-level binding for the same event. This flag is how a
    contained VObject/item-level handler tells this canvas's own generic
    handler (e.g. *onRightMouse()*) "I already dealt with this one, skip
    your default behaviour."
    """
    return eventEqual(event, self._eventHandled)

  def addEventHandled(self, event:tk.Event) -> None:
    """
    Mark *event* as handled by a contained VObject/item-level callback, so
    this canvas's own separately-dispatched widget-level binding for the
    same event can detect that (via *isEventHandled()*) and skip its
    generic handling.

    :param event: The event that was just handled.
    """
    self._eventHandled = event

  def removeEventHandled(self, event:tk.Event) -> None:
    """
    Clear the "handled" flag. Call this once *isEventHandled()* has been
    consulted (whether or not it returned *True*) so a later, distinct
    event isn't mistaken for an already-handled one.

    :param event: Unused (kept for symmetry with *addEventHandled()* and
      the analogous methods elsewhere, e.g. *SNView*).
    """
    self._eventHandled = None

  def onRightMouse(self, event:tk.Event): # -> Optional[tk.Menu]:
    """
    :param event: *event.x* and *event.y* contain the x,y coordinate of the click.
    :return: None or the result of *self.makeMenu()*.

    Called when the right mouse button is pressed (different for Mac and other OS's).

    * Check if the event has been handled by a contained widget. If it has been,
      call *self.removeEventHandled()* and return *None*.

    * Put up the popup menu (*self.makeMenu()*).
    """
    if self.isEventHandled(event):
      self.removeEventHandled(event)
      return None
    bgMenu = self.makeMenu(event)
    bgMenu.post(event.x_root, event.y_root)
    return "break"

  def makeMenu(self, event:tk.Event) -> tk.Menu:
    """
    :param event: *event.x* and *event.y* contain the x,y coordinate of the click.
      (Only used for the location of a newly created node if that happens.)
    :return: The newly created menu.

    Create the popup menu for a *SNView* window. Does not display the menu,
    only creates it and returns it.
    """
    assert event is not None
    clickAt = self.windowToView(self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))

    def makeShowMenu():
      newMenu = tk.Menu(self.canvas)
      # sort the list of individuals
      nodes = dict()
      nodeNames = []
      for i in self.model.values():
        if not(i.isIndividual() and isinstance(i, Relation)):
          nodes[i.name] = i
          nodeNames.append(i.name)
      nodeNames = sorted(nodeNames)
      # make a menu item for each
      for nn in nodeNames:
        newMenu.add_command(label=nodes[nn].name, command=lambda mo=nodes[nn]: self.makeViewObjectForGraphObject(mo)) #type: ignore[misc]
      return newMenu

    bgMenu:tk.Menu = tk.Menu(self.canvas)

    # A menu command's callback runs on the main/GUI thread, where the
    # blocking builtin input() always raises RuntimeError — inputAsync()
    # returns immediately and delivers the typed line to onResult once the
    # user actually answers.
    # # "new instance" and "new subtype" for nodes menus
    modelEditMenu:tk.Menu = tk.Menu(self.canvas)
    bgMenu.add_cascade(label="model", menu=modelEditMenu)
    if self.isModelEditor():
      self.addNewObjectMenus(modelEditMenu, (clickAt[0], clickAt[1]))
      modelEditMenu.add_separator()
      from sn.model import copying
      modelEditMenu.add_command(label="paste here", command=lambda: self.doPaste(at=(clickAt[0], clickAt[1])),
                                state=tk.NORMAL if copying.clipboard is not None else tk.DISABLED)
      modelEditMenu.add_separator()
    if snPrefs.get("gui/debugMenus", storeDefault=False, storeType=bool):
      modelEditMenu.add_command(label="validate", command=lambda o=self: o.context.view.validate(refresh=True), accelerator=KEY_VALIDATE[1]) #type: ignore[misc]
    modelEditMenu.add_command(label="refresh all caches", command=self.refreshAllCaches)
    
    viewMenu = tk.Menu(self.canvas)
    bgMenu.add_cascade(label="view", menu=viewMenu)
    showMenu = tk.Menu(viewMenu)
    showMenu.add_command(label="all", command=self.context.view.showAllModel)
    showMenu.add_command(label="relations...", command=self.showRelationsOfTypes)
    showMenu.add_command(label="nodes...", command=self.showNodesOfTypes)
    showMenu.add_cascade(label="node", menu=makeShowMenu())
    viewMenu.add_cascade(label="show", menu=showMenu)
    viewMenu.add_cascade(label="hide by category", menu=self._visibilityMenu("hide"))
    viewMenu.add_cascade(label="erase by category", menu=self._visibilityMenu("erase"))
    viewMenu.add_separator()
    viewMenu.add_cascade(label="Zoom", menu=self.makeZoomMenu(viewMenu))
    viewMenu.add_command(label="reset scroll region", command=lambda: self.resetScrollRegion(shrink=True))
    viewMenu.add_cascade(label="layout", menu=self._layoutMenu(viewMenu))
    if snPrefs.get("gui/debugMenus", storeDefault=False, storeType=bool):
      viewMenu.add_command(label="repaint", command=self.repaint, accelerator=KEY_REPAINT[1])
    viewMenu.add_separator()
    viewMenu.add_command(label="float all relations", command=lambda: [r.floating(True) for r in self.context.view.values() if isinstance(r, VRelation)]) # (not relation types: they never float)

    reasonMenu = tk.Menu(self.canvas)
    bgMenu.add_cascade(label="reasoning", menu=reasonMenu)
    reasonMenu.add_command(label="clear highlights", command=self.clearHighlights, accelerator=KEY_CLEAR_HIGHLIGHTS[1])
    viewMenu.add_command(label="find...", command=self.openSearchDialog, accelerator=KEY_FIND[1])
    reasonMenu.add_command(label="reason", command=self.reason)
    reasonMenu.add_command(label="reason silently", command=self.reasonSilently)
    reasonMenu.add_command(label="clear reasoning", command=self.clearReasoning,
                       state=tk.NORMAL if self.reasoning is not None else tk.DISABLED)

    return bgMenu

  def makeZoomMenu(self, superMenu:tk.Menu) -> tk.Menu:
    '''
    The "Zoom" submenu: normal size, zoom in and out (about the middle of the
    window: see *zoomAbout()*), zoom to fit (see *zoomToFit()*), and some
    sizes; with their keys.
    '''
    zoommenu = tk.Menu(superMenu)
    zoommenu.add_command(label="Normal Size", command=lambda: self.zoomAbout(1.0), accelerator=KEY_ZOOM_NORMAL[1])
    zoommenu.add_command(label="Zoom In", command=self.zoomIn, accelerator=KEY_ZOOM_IN[1])
    zoommenu.add_command(label="Zoom Out", command=self.zoomOut, accelerator=KEY_ZOOM_OUT[1])
    zoommenu.add_command(label="Zoom to Fit", command=self.zoomToFit, accelerator=KEY_ZOOM_FIT[1])
    zoommenu.add_separator()
    for percent in (200, 150, 75, 50, 25):
      zoommenu.add_command(label=f"{percent}%", command=partial(self.zoomAbout, percent / 100))
    return zoommenu

  ZOOM_DRAG = 2.0
  "How much an Option-drag zooms in for each 100 pixels up (and out, down)."
