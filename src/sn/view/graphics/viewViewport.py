'''
A graphical view's zooming, scrolling and painting (*ViewportMixin*): one of
the parts of *sn.view.graphics.sngView.SNGView* (see *viewBase*).

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
import os
import sn
from typing import Iterable
from util.utils import expandRect
from sn.view.graphics.vrelations import VRelation
from sn.view.graphics import progress
from sn.view.graphics.viewBase import ViewBase

logger:sn.SNLogger = sn.getLogger(__name__)

class ViewportMixin(ViewBase):
  '''
  How a view (*sn.view.graphics.sngView.SNGView*) is seen: zooming (and the
  font size that goes with it), scrolling, converting between window and view
  coordinates, and painting -- now, or soon, and once everything's been read.
  '''

  # (set up by SNGView.__init__(), which says what they are)
  _fontFace: str
  _fontSize: float
  _drawVersion: int

  ZOOM_STEP = 1.25
  "How much \"Zoom In\" zooms in (and \"Zoom Out\", out)."

  MIN_ZOOM, MAX_ZOOM = 0.05, 8.0
  "The least and most the view zooms to."

  ZOOM_FIT_MARGIN = 20
  "Screen pixels left around everything by \"Zoom to Fit\"."

  def fontSize(self) -> int:
    '''
    :returns: The size of the view's text at its zoom: at least 1 (a size of 0
      is Tk's default size: big, at a small zoom).
    '''
    return max(1, int(self._fontSize * self._scale))

  def zoomIn(self) -> None:
    "Zoom in a step (*ZOOM_STEP*), about the middle of the window."
    self.zoomAbout(self._scale * self.ZOOM_STEP)

  def zoomOut(self) -> None:
    "Zoom out a step (*ZOOM_STEP*), about the middle of the window."
    self.zoomAbout(self._scale / self.ZOOM_STEP)

  def _windowCentre(self) -> tuple[float, float]:
    ":returns: The point (view units) at the middle of the window."
    c = self.canvas
    return tuple(self.windowToView(c.canvasx(c.winfo_width() / 2), c.canvasy(c.winfo_height() / 2))) #type: ignore[return-value]

  def _centreOn(self, x:float, y:float) -> None:
    '''
    Scroll so the point (*x*, *y*) (view units) is at the middle of the window
    (as near as the scroll region allows).
    '''
    c = self.canvas
    wx, wy = self.viewToWindow(x, y)
    sr = [float(v) for v in self.scrollRegion]
    if sr[2] > sr[0]:
      c.xview_moveto(max(0.0, (wx - c.winfo_width() / 2 - sr[0]) / (sr[2] - sr[0])))
    if sr[3] > sr[1]:
      c.yview_moveto(max(0.0, (wy - c.winfo_height() / 2 - sr[1]) / (sr[3] - sr[1])))

  def _scrollToPut(self, at:list[float], wx:float, wy:float) -> None:
    '''
    Scroll so the point *at* (view units) is at (*wx*, *wy*) in the window
    (as near as the scroll region allows).
    '''
    c = self.canvas
    x, y = self.viewToWindow(*at)
    sr = [float(v) for v in self.scrollRegion]
    if sr[2] > sr[0]:
      c.xview_moveto(max(0.0, (x - wx - sr[0]) / (sr[2] - sr[0])))
    if sr[3] > sr[1]:
      c.yview_moveto(max(0.0, (y - wy - sr[1]) / (sr[3] - sr[1])))

  def zoomAbout(self, scale:float, centre:tuple[float, float]|None=None) -> None:
    '''
    Zoom to *scale* (kept between *MIN_ZOOM* and *MAX_ZOOM*) with the same
    point at the middle of the window (not the view's top left, as *zoom()*
    alone does: so things don't jump away).

    :param scale: The zoom: 1 is normal size.
    :param centre: The point (view units) to have at the middle of the window,
      if not the one there now.
    '''
    x, y = centre if centre is not None else self._windowCentre()
    self.zoom(min(self.MAX_ZOOM, max(self.MIN_ZOOM, scale)))
    self.resetScrollRegion()
    self._centreOn(x, y)

  def zoomToFit(self) -> None:
    '''
    "Zoom to Fit": zoom so everything shown fits in the window (with
    *ZOOM_FIT_MARGIN* around it), in the middle of it.
    '''
    c = self.canvas
    bb = c.bbox("all")
    if bb is None:
      return
    x1, y1, x2, y2 = self.windowToView(*bb)
    w, h = max(1, c.winfo_width() - 2 * self.ZOOM_FIT_MARGIN), max(1, c.winfo_height() - 2 * self.ZOOM_FIT_MARGIN)
    scale = min(w / max(1.0, x2 - x1), h / max(1.0, y2 - y1))
    self.zoomAbout(scale, ((x1 + x2) / 2, (y1 + y2) / 2))

  def zoom(self, scale:float=1.0, delta=False):
    """
    :param scale: the absolute scale, where 1.0 is "no scaling", unless *delta* is true, in which
            case, multiplier for the current scale (so numbers like 0.9 and 1.1 make sense).
    :param delta: True to do relative scaling, False to do absolute scaling.
    """
    oldScale = self._scale
    if delta:
      self._scale *= scale
    else:
      self._scale = scale
    self.canvas.scale("all", 0, 0, self._scale / oldScale, self._scale / oldScale)
    for child_widget in self.canvas.find_withtag("text"):
      self.canvas.itemconfigure(child_widget, font=(self._fontFace, self.fontSize()))
    try:
      bb = list(self.canvas.bbox("all"))
    except:
      bb = [0, 0, 0, 0]
    bb = [bb[0] - 800, bb[1] - 600, bb[2] + 800, bb[3] + 600] # (the canvas extends every way: coordinates may be negative)
    self.scrollRegion = tuple(bb) # (what resetScrollRegion() grows from -- in canvas units, which zooming changes)
    self.canvas.configure(scrollregion=bb) #type: ignore[call-overload]
    bar = self.__dict__.get("_reasoningToolbar") # (it shows the zoom)
    if bar is not None:
      bar.refreshZoom()

  def _viewportState(self) -> str:
    '''
    :returns: What's saved with the view about what's shown in its window (see
      *_restoreViewport()*): its zoom, and the point at its top left, in view
      units (as the view's objects are placed): eg: "zoom=0.8;x=120.0;y=-40.0".
    '''
    try:
      x, y = self.windowToView(self.canvas.canvasx(0), self.canvas.canvasy(0))
    except Exception: # (no window)
      return ""
    return f"zoom={float(self._scale)!r};x={float(x)!r};y={float(y)!r}"

  def _restoreViewport(self) -> None:
    '''
    Once a read view is built: zoom it as it was saved, and scroll it so the
    same point is at its top left (see *_viewportState()*).
    '''
    text = self.__dict__.pop("_pendingViewport", None)
    if not text:
      return
    try:
      state = dict(kv.split("=", 1) for kv in text.split(";") if "=" in kv)
      scale = float(state.get("zoom", 1.0))
      if scale > 0 and abs(scale - self._scale) > 1e-9:
        self.zoom(scale) # (rescales what's drawn: no need to draw it all again)
      self.resetScrollRegion()
      if "x" in state and "y" in state:
        x, y = self.viewToWindow(float(state["x"]), float(state["y"]))
        sr = [float(c) for c in self.scrollRegion]
        if sr[2] > sr[0]:
          self.canvas.xview_moveto(max(0.0, (x - sr[0]) / (sr[2] - sr[0])))
        if sr[3] > sr[1]:
          self.canvas.yview_moveto(max(0.0, (y - sr[1]) / (sr[3] - sr[1])))
    except Exception:
      logger.exception(f"{self.url}: couldn't restore the zoom and scrolling ({text})")

  def viewToWindow(self, *args) -> list[float]:
    """
    :param args: Either a single list argument or multiple float parameters. In either case there
          must be an even number of items, taken as x,y pairs. Since scaling is x:y equal, this "even"
          limitation is relaxed here.
    :return: A list converted coordinates where the evens are x coordinates and the odds are y coordinates
          converted from view to window coordinates.
    """
    if len(args) == 1 and isinstance(args[0], Iterable):
      args = args[0] # type: ignore[assignment]
    ret = []
    for n in args:
      ret.append(n * self._scale)
    return ret

  def windowToView(self, *args) -> list[float]:
    """
    :param args: Either a single list argument or multiple float parameters. In either case there
          must be an even number of items, taken as x,y pairs. Since scaling is x:y equal, this "even"
          limitation is relaxed here.
    :return: A list converted coordinates where the evens are x coordinates and the odds are y coordinates
          converted from window to view coordinates.
    """
    if len(args) == 1 and isinstance(args[0], Iterable):
      args = args[0] # type: ignore[assignment]
    ret = []
    for n in args:
      ret.append(n / self._scale)
    return ret

  def freshPaint(self):
    'Increments self._drawVersion so that graphic options can know whether to update of not.'''
    self._drawVersion += 1

  def repaintSoon(self) -> None:
    '''
    Repaint the whole view (see *repaint()*) once things are idle -- once, however
    many times this is called before then: eg: the moves of a whole run of the
    animation layout, recorded (or undone) as one command, each of which would
    otherwise repaint everything.
    '''
    if self.__dict__.get("_repaintPending"):
      return
    if not self.canvas:
      self.repaint()
      return
    self._repaintPending = True
    def go() -> None:
      self._repaintPending = False
      if not getattr(self, "_closed", False):
        self.repaint()
    self.canvas.after_idle(go)

  def _drawAllAfterRead(self) -> None:
    '''
    Once a read view is built: draw everything -- nodes first, then
    relations, so each relation is drawn once its ends are where (and the
    size) they'll be. The objects' own first drawings, queued as they were
    made, were put off till now (see *VObject._firstDraw()*): each was a
    redrawing of all of a node's relations as it was fitted to its text, and
    then this drew them all again.
    '''
    self.__dict__.pop("_firstDrawsDeferred", None)
    self.freshPaint()
    objects = [o for o in self.context.view.values() if o is not None]
    with progress.task(f'Drawing "{os.path.basename(self.url.partition("://")[2]) or self.url}"...', len(objects)):
      done = 0
      for relations in (False, True):
        for obj in objects:
          if isinstance(obj, VRelation) == relations:
            obj.draw()
            done += 1
            if done % 100 == 0:
              progress.step(done)
    for obj in objects: # (now they're drawn: their own first drawings, whenever they come, are skipped -- see VObject._firstDraw())
      obj.__dict__["_drawnWithView"] = True
      obj.__dict__["_firstDrawPending"] = False
      if obj._isConnected():
        obj.makeBindings()

  def refreshAllCaches(self) -> None:
    '''
    Refresh every object's cache of its model object's visual attributes (see
    *vobjects.Cache.refresh()*), and repaint the view, so it shows them.
    '''
    for obj in self.context.view.values():
      if obj is not None:
        obj.cache.refresh()
    self.repaint()

  def repaint(self, event=None):
    '''
    :param event: The Tk event.
    '''
    self.freshPaint()
    for obj in self.context.view.values():
      if obj is not None:
        obj.draw()

  def resetScrollRegion(self, shrink:bool=False) -> None:
    '''
    Recompute the canvas's scroll region from the current extent of
    everything actually drawn on it, and apply it -- to *self.scrollRegion*
    itself (what *VObject.moveTo()*/*boundingBox()* clamp positions
    against -- see their docstrings) as well as to the canvas widget's own
    ``scrollregion`` configuration option.

    :param shrink: [default=False] Normally the region only grows (see below);
      True fits it to the drawing even if that makes it smaller -- for an
      explicit user request, when the view jumping to fit is expected.

    Called by *VObject.draw()* whenever a *VObject*'s bounding box no longer
    fits inside the existing region -- e.g. after it's been dragged past the
    SE edge -- so the canvas grows to keep the object reachable/visible.

    :note: Nothing's caught here: *self.canvas.bbox("all")* is *None* while
      nothing's drawn, which is checked for (``expandRect(None, 100)`` would
      raise *TypeError*); anything else is a real fault, and masking it would
      leave the region silently not grown (eg: when dragging past the edge).
      *self.scrollRegion* is kept in step with the canvas's, as *moveTo()*'s
      clamp compares against it.
    '''
    bb = self.canvas.bbox("all")
    if bb is None:  # nothing drawn yet -- nothing to size the region to
      return
    bb = tuple(expandRect(bb, 100)) #type: ignore[assignment] #mypy is fussy!
    # Only ever grow: shrinking the region can pull it out from under the
    # current view, and Tk then shifts the view to fit -- which makes the
    # whole drawing appear to jump (eg: mid-drag).
    sr = self.scrollRegion
    if shrink:
      bb = tuple(bb) #type: ignore[assignment] #mypy is fussy!
    else:
      bb = (min(bb[0], sr[0]), min(bb[1], sr[1]), max(bb[2], sr[2]), max(bb[3], sr[3]))
    if bb != tuple(sr):
      self.scrollRegion = bb
      self.canvas.configure(scrollregion=bb)
