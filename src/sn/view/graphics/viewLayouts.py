'''
A graphical view's layouts (*LayoutsMixin*): one of the parts of
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
from functools import partial
from typing import Any, cast, TYPE_CHECKING
from sn.view.graphics.vobjects import VObject
from sn.view.graphics.vrelations import VRelation
from sn.view.graphics.layout import relationTypes, relationNamed, LayoutHeuristic, intoRect, gatherShifts, STATIC, DYNAMIC, FindFree, ANIMATED, layoutsFor, NoLayout, finishTween
from util.commandParser import CompositeCommandMgr
from sn.view.graphics.viewBase import ViewBase
if TYPE_CHECKING:
  from sn.view.graphics.sngView import SNGView
  from sn.view.graphics.layoutPanel import LayoutSplit

logger:sn.SNLogger = sn.getLogger(__name__)

class LayoutsMixin(ViewBase):
  '''
  How a view (*sn.view.graphics.sngView.SNGView*) is laid out (see
  *sn.view.graphics.layout*): its dynamic layout, arranging it with a static one
  ("arrange now", "keep arranged"), the animation layout and its settings, the
  layout panel, the layouts' last parameters (all saved with the view), and
  gathering what's strayed far away.
  '''

  ANIMATION_SETTINGS = ("flowStrength", "e", "k", "heat", "cooling", "leaps")
  "The animation layout's numeric settings saved with the view (see *_animationState()*)."

  def _animationState(self) -> str:
    '''
    :returns: What's saved with the view about its animation layout: its
      settings -- eg:
      "direction=down;follows=isa;labels=1;flowStrength=6.0;e=1000.0;k=0.005;heat=6.0;cooling=0.7;leaps=0.05".
    '''
    layout = self.animationLayout()
    parts = {"direction": layout.flowDirection or "none",
             "follows": (layout.flowRelation or self.model.ISA).name,
             "labels": "1" if layout.placeLabels else "0"}
    parts.update({k: repr(float(getattr(layout, k))) for k in self.ANIMATION_SETTINGS})
    return ";".join(f"{k}={v}" for k, v in parts.items())

  def _restoreAnimationState(self) -> None:
    '''
    Once a read view is built: put its saved animation layout settings back
    (see *_animationState()*) -- and, for a view saved with the animation
    toolbar the layout panel replaced showing ("toolbar=1"), and no layout
    panel state, show the panel's "animate" page.
    '''
    text = self.__dict__.pop("_pendingAnimation", None)
    if not text:
      return
    try:
      state = dict(kv.split("=", 1) for kv in text.split(";") if "=" in kv)
      layout = self.animationLayout()
      direction = state.get("direction", "none")
      layout.flowDirection = None if direction == "none" else direction
      follows = state.get("follows")
      if follows and follows != self.model.ISA.name:
        layout.flowRelation = relationNamed(self.model, follows)
      for k in self.ANIMATION_SETTINGS:
        if k in state:
          setattr(layout, k, float(state[k]))
      layout.placeLabels = state.get("labels", "1") != "0"
      if state.get("toolbar") == "1" and "_pendingLayoutPanel" not in self.__dict__:
        self.__dict__["_pendingLayoutPanel"] = f"shown=1;page={ANIMATED}"
    except Exception:
      logger.exception(f"{self.name}: couldn't restore its animation settings ({text!r})")

  def setAnimationSetting(self, attr:str, value:Any) -> None:
    '''
    Change one of the animation layout's settings (eg: from the layout panel or
    the menu) -- marking the view changed, as they're saved with it.

    :param attr: The layout's attribute, eg: "flowDirection" or "heat".
    :param value: Its new value.
    '''
    layout = self.animationLayout()
    if getattr(layout, attr, None) != value:
      setattr(layout, attr, value)
      self.setDirty()

  def _layoutPanelShown(self) -> tk.BooleanVar:
    '''
    :returns: Whether this view's layout panel is shown -- what "View | Layout panel" shows (and sets).
    '''
    var = self.__dict__.get("_layoutPanelVar")
    if var is None:
      var = self._layoutPanelVar = tk.BooleanVar(self.canvas, value=False)
    return var

  def _onLayoutPanelItem(self) -> None:
    'The "View | Layout panel" item was chosen: its check mark is already set; show or hide accordingly.'
    self.showLayoutPanel(self._layoutPanelShown().get())

  def toggleLayoutPanel(self) -> None:
    'Show the layout panel if it\'s hidden, or hide it if it\'s shown.'
    self.showLayoutPanel(not self._layoutPanelShown().get())

  def showLayoutPanel(self, show:bool=True, category:str|None=None, name:str|None=None) -> None:
    '''
    Show (or hide) the layout panel (see *layoutPanel*) at the right of this
    view's window, beside the canvas (see *layoutSplit()*): while it's hidden,
    a narrow strip is there instead, which opens it.

    :param show: True to show it; False to hide it.
    :param category: The kind of layout to show (of *layout.CATEGORIES*), if not the one it shows.
    :param name: The layout to show, of that kind (see *layoutPanel.LayoutPanel.show()*).

    In a window that isn't shown (eg: one being read, or a hidden one, as in
    tests), the panel is made only once it is (see *_showPanelWhenMapped()*):
    Tk on macOS keeps redrawing a never-shown window with ttk widgets in its
    split, at idle, so *update()* wouldn't return.
    '''
    from sn.view.graphics.layoutPanel import LayoutPanel
    split = self.layoutSplit()
    panel:LayoutPanel|None = self.__dict__.get("_layoutPanel")
    if show and panel is None and not split.winfo_ismapped():
      self._showPanelWhenMapped(category, name)
    elif show:
      if panel is None:
        panel = self._layoutPanel = LayoutPanel(split, cast("SNGView", self))
        saved = self.__dict__.pop("_unbuiltLayoutPanel", None) # (read with the view: see _restoreLayoutPanel())
        if saved:
          panel.setSavedState(dict(kv.split("=", 1) for kv in saved.split(";") if "=" in kv))
      split.showPanel(panel)
      if category is not None:
        panel.show(category, name)
      panel.startPolling()
    elif panel is not None:
      panel.stopPolling()
      split.hidePanel()
    if self._layoutPanelShown().get() != show:
      self._layoutPanelShown().set(show)
      self.setDirty() # (saved with the view)

  def _showPanelWhenMapped(self, category:str|None, name:str|None) -> None:
    '''
    Make and show the layout panel once its window's shown (see
    *showLayoutPanel()*) -- if it's still to be shown then.

    :param category: As for *showLayoutPanel()*.
    :param name: As for *showLayoutPanel()*.
    '''
    split = self.layoutSplit()
    self._panelPage = (category, name) # (the latest asked for)
    if self.__dict__.get("_panelMapBinding"):
      return
    def mapped(_event:tk.Event) -> None:
      split.unbind("<Map>", self.__dict__.pop("_panelMapBinding"))
      page = self.__dict__.pop("_panelPage")
      if self._layoutPanelShown().get():
        self.showLayoutPanel(True, *page)
    self._panelMapBinding = split.bind("<Map>", mapped, add="+")

  def layoutSplit(self) -> LayoutSplit:
    '''
    :returns: The split between the canvas and the layout panel (or the strip
      that opens it): see *layoutPanel.LayoutSplit*. Made (replacing the
      canvas's pane) when the view's window is.
    '''
    from sn.view.graphics.layoutPanel import LayoutSplit
    split = self.__dict__.get("_layoutSplit")
    if split is None:
      split = self._layoutSplit = LayoutSplit(cast("SNGView", self))
    return split

  def _layoutPanelState(self) -> str:
    '''
    :returns: What's saved with the view about its layout panel: whether it's
      shown, and what *layoutPanel.LayoutPanel.savedState()* says (if it's been
      made) -- eg: "shown=1;page=static;static=tree;width=340".
    '''
    panel = self.__dict__.get("_layoutPanel")
    shown = "shown=" + ("1" if self._layoutPanelShown().get() else "0")
    if panel is None: # (as it was read, if it's never been made -- shown or not, as it is now)
      return ";".join([shown, *(kv for kv in self.__dict__.get("_unbuiltLayoutPanel", "").split(";") if kv and not kv.startswith("shown="))])
    return shown + ";" + panel.savedState()

  def _restoreLayoutPanel(self) -> None:
    '''
    Once a read view is built: show its layout panel as it was saved (see
    *_layoutPanelState()*), if it was shown. What it was showing is put back
    when it's made: now, or when it's first shown.
    '''
    text = self.__dict__.pop("_pendingLayoutPanel", None)
    if not text:
      return
    try:
      self._unbuiltLayoutPanel = text
      if "shown=1" in text.split(";"):
        self.showLayoutPanel(True)
    except Exception:
      logger.exception(f"{self.name}: couldn't restore its layout panel ({text!r})")

  def _pinRelationTypes(self) -> None:
    '''
    Once a read view is drawn: pin the relation types that float (from a view
    saved before they always had a place of their own, as nodes do: see
    *VRelation.floating()*) where they're drawn, so nothing moves.
    '''
    for obj in self.context.view.values():
      if isinstance(obj, VRelation) and obj.modelObject is not None and obj.modelObject.isType():
        obj._floatingAnchor = False

  def animationLayout(self) -> Any:
    '''
    :returns: This view's animation layout (see *animatedLayouts.FieldsLayout_threaded*), made if need be.
    :rtype: FieldsLayout_threaded
    '''
    from sn.view.graphics.animatedLayouts import FieldsLayout_threaded
    layout = self.__dict__.get("_animationLayout")
    if layout is None:
      layout = self._animationLayout = FieldsLayout_threaded(cast("SNGView", self))
    return layout

  def _animationLayoutMenu(self, parent:tk.Menu) -> tk.Menu:
    '''
    The "animation layout" submenu: start/stop it, and its current: the direction
    it flows in (or none), its strength, and the relation type it lines up
    (dsts upstream of srcs: eg: "isa" flowing down gives a class diagram).

    :param parent: The menu it's a submenu of.
    :returns: The submenu.
    '''
    from sn.view.graphics.animatedLayouts import FLOW_DIRECTIONS
    layout = self.animationLayout()
    menu = tk.Menu(parent)
    menu.add_command(label="stop" if layout.active else "start", command=self.toggleAnimationLayout)
    menu.add_command(label="settings...", command=lambda: self.showLayoutPanel(True, ANIMATED))
    menu.add_separator()
    self._flowVars = getattr(self, "_flowVars", {}) # (keep the variables alive)
    direction = tk.StringVar(value=layout.flowDirection or "none")
    self._flowVars["direction"] = direction
    dirMenu = tk.Menu(menu)
    for name in ["none", *FLOW_DIRECTIONS]:
      dirMenu.add_radiobutton(label=name, variable=direction, value=name,
                              command=lambda n=name: self.setAnimationSetting("flowDirection", None if n == "none" else n)) # type: ignore[misc]
    menu.add_cascade(label="current direction", menu=dirMenu)
    strength = tk.DoubleVar(value=layout.flowStrength)
    self._flowVars["strength"] = strength
    strMenu = tk.Menu(menu)
    for label, value in (("weak", 3.0), ("medium", 6.0), ("strong", 10.0)):
      strMenu.add_radiobutton(label=label, variable=strength, value=value,
                              command=lambda v=value: self.setAnimationSetting("flowStrength", v)) # type: ignore[misc]
    menu.add_cascade(label="current strength", menu=strMenu)
    relation = tk.StringVar(value=(layout.flowRelation or self.model.ISA).name)
    self._flowVars["relation"] = relation
    relMenu = tk.Menu(menu)
    types = relationTypes(self.model) # (its super-models' too: eg: an ontology's)
    for t in types:
      relMenu.add_radiobutton(label=t.name, variable=relation, value=t.name,
                              command=lambda t=t: self.setAnimationSetting("flowRelation", None if t is self.model.ISA else t)) # type: ignore[misc]
    menu.add_cascade(label="current follows", menu=relMenu)
    return menu

  def toggleAnimationLayout(self) -> None:
    '''
    Start (or, if it's running, stop) the animation layout: objects
    repel one another and relations pull them together, until things settle
    (see *animatedLayouts.FieldsLayout*). The whole run is one undoable command.
    A dynamic layout that arranges things itself (eg: a tree) would undo what
    it does, so the view's dynamic layout becomes "avoid overlaps" first.
    '''
    layout = self.animationLayout()
    if layout.active:
      layout.kill()
      return
    if not isinstance(self.localLayout, (FindFree, NoLayout)):
      logger.info(f'The animation layout: the dynamic layout is now "{FindFree.NAME}" (it was "{self.localLayout.NAME}").')
      self.setDynamicLayout(FindFree(self))
    layout(autoOff=True)

  def _layoutMenu(self, parent:tk.Menu) -> tk.Menu:
    '''
    The "layout" submenu: the layouts, by kind (see *layout.CATEGORIES*):
    "arrange now" (static: done at once, as one undoable command), "keep
    arranged" (dynamic: one at a time: the view's *localLayout*), and
    "animate" (see *_animationLayoutMenu()*). A layout with parameters opens
    its page in the layout panel (see *showLayoutPanel()*), to set them and
    arrange or use it there; one without is done (or used) straight away.

    :param parent: The menu it's a submenu of.
    :returns: The submenu.
    '''
    menu = tk.Menu(parent)
    menu.add_command(label="layout panel...", command=lambda: self.showLayoutPanel(True))
    menu.add_separator()
    arrange = tk.Menu(menu)
    for cls in layoutsFor(STATIC):
      asks = any(STATIC in p.categories for p in cls.PARAMETERS)
      arrange.add_command(label=cls.NAME + ("..." if asks else ""),
                          command=partial(self.showLayoutPanel, True, STATIC, cls.NAME) if asks else partial(self.arrangeWith, cls))
    menu.add_cascade(label="arrange now", menu=arrange)
    keep = tk.Menu(menu)
    current = tk.StringVar(value=self.localLayout.NAME)
    self._layoutVar = current # (keep it alive)
    for cls in layoutsFor(DYNAMIC):
      asks = any(DYNAMIC in p.categories for p in cls.PARAMETERS)
      keep.add_radiobutton(label=cls.NAME + ("..." if asks else ""), variable=current, value=cls.NAME,
                           command=partial(self._keepArrangedItem, cls) if asks else partial(self.keepArrangedWith, cls))
    menu.add_cascade(label="keep arranged", menu=keep)
    menu.add_cascade(label="animate", menu=self._animationLayoutMenu(menu))
    return menu

  def lastLayoutParameters(self, cls:type[LayoutHeuristic]) -> dict[str, Any]|None:
    '''
    :param cls: A kind of layout.
    :returns: The parameters it was last used with in this view (see
      *rememberLayoutParameters()*: saved with the view) -- or, if it hasn't
      been, those it's being used with as its dynamic layout -- if any: what
      its dialog starts with.
    '''
    remembered = self.__dict__.setdefault("_layoutParameters", {}).get(cls.NAME)
    if remembered is not None:
      return dict(remembered)
    if isinstance(self.localLayout, cls):
      return self.localLayout.parameters()
    return None

  def rememberLayoutParameters(self, layout:LayoutHeuristic, category:str=STATIC) -> None:
    '''
    Remember the parameters *layout* is used with in this view, for its kind
    of layout (see *lastLayoutParameters()*), whether chosen in its dialog or
    given by a program (eg: pythonParser's tree layout, following
    "includes"). Saved with the view. Only those that matter for how it's
    used (*category*: see *layout.LayoutParameter.categories*) are changed:
    eg: keeping a tree arranged leaves what "arrange now" does with the nodes
    in no tree as it was.

    :param layout: A layout of this view, being used.
    :param category: How it's used: *STATIC* or *DYNAMIC*.
    '''
    if not layout.PARAMETERS:
      return
    remembered = self.__dict__.setdefault("_layoutParameters", {})
    params = dict(remembered.get(layout.NAME) or layout.parameters())
    params.update({p.name: layout.params.get(p.name) for p in layout.PARAMETERS if category in p.categories})
    remembered[layout.NAME] = params

  def _layoutParametersState(self) -> str:
    '''
    :returns: What's saved with the view of the layouts' last parameters (see
      *rememberLayoutParameters()*): each as *layout.LayoutHeuristic.encodeParameters()*
      says, separated by "|".
    '''
    from sn.view.graphics.layout import LAYOUTS
    return "|".join(LAYOUTS[name].encodeParameters(params) for name, params in self.__dict__.get("_layoutParameters", {}).items()
                    if name in LAYOUTS)

  def _restoreLayoutParameters(self, text:str) -> None:
    '''
    Put back the layouts' last parameters saved with the view (see *_layoutParametersState()*).

    :param text: What was saved.
    '''
    remembered = self.__dict__.setdefault("_layoutParameters", {})
    for part in text.split("|"):
      decoded = LayoutHeuristic.decodeParameters(part) if part.strip() else None
      if decoded is not None:
        cls, kwargs, _ = decoded
        remembered[cls.NAME] = {p.name: kwargs.get(p.name, p.default) for p in cls.PARAMETERS} # (a relation by its name)

  def arrangeWith(self, cls:type[LayoutHeuristic]) -> None:
    '''
    "arrange now": arrange the view with a static layout, once (asking for its
    parameters, if it has any), as one undoable command.

    :param cls: The kind of layout.
    '''
    kwargs = cls.askParameters(self, STATIC, self.lastLayoutParameters(cls), parent=self.window)
    if kwargs is None:
      return
    cls(self, **kwargs).arrange() # (it remembers them: see layout.LayoutHeuristic.arrange())

  def _keepArrangedItem(self, cls:type[LayoutHeuristic]) -> None:
    '''
    A "keep arranged" item for a layout with parameters was chosen: open its
    page in the layout panel, to set them and use it there. Its check mark
    stays on the view's dynamic layout till then.

    :param cls: The kind of layout.
    '''
    if getattr(self, "_layoutVar", None) is not None:
      self._layoutVar.set(self.localLayout.NAME)
    self.showLayoutPanel(True, DYNAMIC, cls.NAME)

  def keepArrangedWith(self, cls:type[LayoutHeuristic]) -> None:
    '''
    "keep arranged": make a kind of layout the view's dynamic layout (asking for
    its parameters, if it has any).

    :param cls: The kind of layout.
    '''
    kwargs = cls.askParameters(self, DYNAMIC, self.lastLayoutParameters(cls), parent=self.window)
    if kwargs is None: # (cancelled: the menu shows the one there still is)
      if getattr(self, "_layoutVar", None) is not None:
        self._layoutVar.set(self.localLayout.NAME)
      return
    self.setDynamicLayout(cls(self, **kwargs)) # (it remembers them)

  def setDynamicLayout(self, layout:LayoutHeuristic) -> None:
    '''
    Make *layout* the view's dynamic layout (*localLayout*), and let it arrange
    things as it would keep them (see *layout.LayoutHeuristic.activate()*).
    Saved with the view.

    :param layout: A dynamic layout of this view.
    '''
    finishTween(self)
    self.__dict__.pop("_pendingLayout", None) # (set before a read view's saved one was put back: this one wins)
    self.localLayout = layout
    self.rememberLayoutParameters(layout, DYNAMIC)
    if getattr(self, "_layoutVar", None) is not None:
      self._layoutVar.set(layout.NAME)
    self.setDirty()
    layout.activate()

  def _restoreLayoutState(self) -> None:
    '''
    Once a read view is built: put back the dynamic layout it was saved with
    (see *layout.LayoutHeuristic.state()*), without arranging anything: it's
    as it was saved.
    '''
    text = self.__dict__.pop("_pendingLayout", None)
    if not text:
      return
    try:
      layout = LayoutHeuristic.fromState(self, text)
      if layout is None:
        logger.warning(f'{self.url}: there\'s no layout "{text.split(";")[0]}": using "{self.localLayout.NAME}".')
        return
      self.localLayout = layout
    except Exception:
      logger.exception(f"{self.url}: couldn't restore the dynamic layout ({text})")

  def gatherNodes(self) -> None:
    '''
    Herd outlying objects -- eg: ones some layout bug has flung far from
    their companions -- back toward the main pack, as a single undoable
    command. See *layout.gatherShifts()* for the (per-axis) heuristic.

    Floating relations aren't moved directly: they re-centre themselves on
    their (moved) nodes. What's in a context window moves with it, and is put
    in its pane if it isn't there (see *containmentHomes()*).
    '''
    homes = self.containmentHomes()
    parents:dict[VObject, VObject] = {vo: w for vo, (w, _) in homes.items()}
    for w in self.contextWindows():
      for vo in w.windowContents():
        parents.setdefault(vo, w)
    floats = lambda o: isinstance(o, VRelation) and o.floating()
    objs = [o for o in self.context.view.values()
            if o is not None and o._isConnected() and not o.isHidden() and not floats(o) and o not in parents]
    boxes = [o.boundingBox() for o in objs]
    shifts:dict[VObject, tuple[float, float]] = {o: d for o, d in zip(objs, gatherShifts(boxes))}
    def shift(vo:VObject, depth:int=0) -> tuple[float, float]: # (its window's, and into its pane)
      if vo in shifts:
        return shifts[vo]
      w = parents.get(vo)
      dx, dy = shift(w, depth + 1) if w is not None and depth < len(parents) else (0.0, 0.0)
      if vo in homes:
        win, pane = homes[vo]
        x1, y1, x2, y2 = vo.boundingBox()
        ex, ey = intoRect([x1 + dx, y1 + dy, x2 + dx, y2 + dy], [c + d for c, d in zip(self.homeRect(win, pane), (dx, dy, dx, dy))],
                          margin=10.0, topMargin=22.0 if len(win.panes()) > 1 else 10.0)
        dx, dy = dx + ex, dy + ey
      shifts[vo] = (dx, dy)
      return dx, dy
    moves = []
    for o in [*objs, *[vo for vo in parents if vo._isConnected() and not floats(vo)]]:
      dx, dy = shift(o)
      if dx or dy:
        bb = o.boundingBox()
        moves.append((o, bb, dx, dy))
    if not moves:
      logger.info("gatherNodes(): nothing to gather.")
      return
    with CompositeCommandMgr(self.context):
      for o, bb, dx, dy in moves: # (windows don't carry their contents: they have moves of their own)
        self.context.move(o, bb[0] + dx, bb[1] + dy, _oldPos=bb, adjustPos=False, _carry=False)
    self.resetScrollRegion(shrink=True)
    logger.info(f"gatherNodes(): moved {len(moves)} of {len(objs) + len(parents)} objects.")
