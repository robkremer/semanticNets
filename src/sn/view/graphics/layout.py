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
'''
Layout heuristics: ways of arranging a view's objects. There are three kinds
(see *CATEGORIES*), and a heuristic may be more than one:

  - **static** (*STATIC*): chosen, and done all at once, as one undoable
    command (see *LayoutHeuristic.arrange()*): eg: *TreeLayout* (in
    *treeLayout*), "gather nodes".
  - **dynamic** (*DYNAMIC*): the view's current one (*SNGView.localLayout*:
    one at a time) keeps things arranged as they change: it places what's
    made or dropped (see *LayoutHeuristic.placeNode()*), and after each
    command that changes the view, adjusts the rest (see
    *LayoutHeuristic.adjust()*), as part of the same undoable command: eg:
    *FindFree* ("avoid overlaps": the default), *TreeLayout*, *NoLayout*.
  - **animated** (*ANIMATED*): runs in the background until things settle:
    eg: *animatedLayouts.FieldsLayout*.

Each heuristic declares the parameters its constructor takes (see
*LayoutParameter*): a program can construct one with them directly (eg:
``TreeLayout(view, relation=r, direction="down").arrange()``), and the view's
menus ask for them with a dialog made from them (see
*LayoutHeuristic.askParameters()*). Heuristics are listed by name in *LAYOUTS*
(see *registerLayout()*), which the view's "layout" menu is made from.

Their moves are made by *LayoutMoves*: one undoable command, animated
(tweened: see *tween()*) when it's first done.

  .. inheritance-diagram::
        Direction
        FindFree
        NoLayout
        GatherLayout
        LayoutHeuristic
      :parts: 3
      :private-bases:

Created on Feb 15, 2025

.. codeauthor:: Rob Kremer <robkremer@me.com>

---------------
'''

import sn
import logging
from abc import ABC
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional, override, Iterable
from sn.view.graphics.vnodes import VNode
from sn.view.graphics.vobjects import VObject
from sn.view.graphics.vrelations import VRelation
from util.utils import Point, expandRect
from util.command import Command
from sn.model.model import GraphObject, Model, Node, Relation
from util.utils import removeDuplicates

logger:sn.SNLogger = sn.getLogger(__name__)

LABEL_PLACEMENT_PREF = "gui/optimization/aggressiveLabelPlacement"
"The preference for how hard *FindFree* looks for a free spot for a relation's label: see *labelPlacementLevel()*."

LABEL_PLACEMENT_DEFAULT = sn.PREFS[LABEL_PLACEMENT_PREF][1]

def labelPlacementLevel() -> int:
  '''
  :returns: The *LABEL_PLACEMENT_PREF* preference, from 0 to 10: how far
    *FindFree* looks for a free spot for a relation's label. 0: it doesn't (the
    label stays where it's made, midway between the relation's ends); else up
    to *level* squared rings out from there (10: 100, as for nodes). The time
    taken grows with the square of that, so a lot in a crowded view, as when
    showing a big model.
  :rtype: int
  '''
  level = sn.snPrefs.get(LABEL_PLACEMENT_PREF, storeDefault=LABEL_PLACEMENT_DEFAULT, storeType=int) # (its note: see sn.PREFS)
  if not isinstance(level, (int, float, str)):
    return LABEL_PLACEMENT_DEFAULT
  try:
    return min(10, max(0, int(level)))
  except ValueError:
    return LABEL_PLACEMENT_DEFAULT

class Direction(Enum):
  UNSPECIFIED = 0
  SUB = 1
  SUPER = 2
  LATERAL = 3
  NEAREST = 4
  
def depth(obj:GraphObject) -> int:
  '''
  :param obj:
  :type obj: GraphObject
  :return: the isa-depth of *obj*.
  :rtype: int
  '''
  i:int = -1
  p = [obj]
  while len(p) > 0:
    q = []
    for pp in p:
      q += list(p[0].getParents())
    p = removeDuplicates(q)
    i += 1
  return i
  
  
STATIC, DYNAMIC, ANIMATED = "static", "dynamic", "animated"
CATEGORIES = (STATIC, DYNAMIC, ANIMATED)
"The kinds of layout heuristic: see the module doc."

@dataclass(frozen=True)
class LayoutParameter:
  '''
  A parameter of a layout heuristic: a keyword argument of its constructor,
  asked for by its dialog (see *LayoutHeuristic.askParameters()*) and saved
  with the view (see *LayoutHeuristic.state()*).
  '''
  name:str
  "The keyword argument's name."
  label:str
  "What the dialog calls it."
  kind:str
  '''"relation" (a relation type: a *Relation*, or its name), "choice" (one
  of *choices*), "int" or "bool".'''
  default:Any = None
  "Its value if none's given (a relation's name, for a relation)."
  choices:tuple[str, ...] = ()
  "For a choice: what it may be."
  note:str = ""
  "Said under it in the dialog, if anything."
  categories:tuple[str, ...] = (STATIC, DYNAMIC)
  "The kinds of use it matters for: the dialog for the others doesn't ask for it."

LAYOUTS:dict[str, type["LayoutHeuristic"]] = {}
"The layout heuristics, by name (see *registerLayout()*): the view's \"layout\" menu lists them."

def registerLayout[T: type["LayoutHeuristic"]](cls:T) -> T:
  '''
  A class decorator: list the layout heuristic *cls* in *LAYOUTS*, by its *NAME*.

  :param cls:
  :type cls: type[LayoutHeuristic]
  :returns: *cls*.
  :rtype: type[LayoutHeuristic]
  '''
  LAYOUTS[cls.NAME] = cls
  return cls

def layoutsFor(category:str) -> list[type["LayoutHeuristic"]]:
  '''
  :param category: One of *CATEGORIES*.
  :type category: str
  :returns: The layout heuristics (in *LAYOUTS*) of that kind, in the order they were registered.
  :rtype: list[type[LayoutHeuristic]]
  '''
  return [c for c in LAYOUTS.values() if category in c.CATEGORIES]

def relationTypes(model:Model) -> list[Relation]:
  '''
  :param model: A model.
  :type model: Model
  :returns: The relation types a layout can follow: isa, then the model's
    own and its super-models' (eg: an ontology it's built on: *values()* has
    only its own), but not the system's or the base rules' (see
    *Model.implicitSuperDBs()*), by name.
  :rtype: list[Relation]
  '''
  implicit = model.implicitSuperDBs()
  models = [model] + [db for db in model.allSuperDBs() if isinstance(db, Model) and not any(db is i for i in implicit)]
  seen:set[int] = set()
  ret:list[Relation] = []
  for m in models:
    if id(m) in seen:
      continue
    seen.add(id(m))
    ret += [r for r in m.values() if isinstance(r, Relation) and r.isType() and r.model is m
            and r is not model.ISA and not r.isSystemObject()]
  return [model.ISA] + sorted(ret, key=lambda r: str(r.name).lower())

def relationNamed(model:Model, name:str) -> Relation|None:
  '''
  :param model: A model.
  :type model: Model
  :param name: A relation type's name.
  :type name: str
  :returns: The first of *relationTypes()* with that name, if any.
  :rtype: Relation | None
  '''
  return next((r for r in relationTypes(model) if r.name == name), None)

class LayoutHeuristic(ABC):
  '''
  A way of arranging a view's objects: static, dynamic, animated, or more
  than one of those (see the module doc and *CATEGORIES*). A subclass says
  which (*CATEGORIES*), what it's called (*NAME*), and the parameters its
  constructor takes (*PARAMETERS*); and implements what its kinds need:

    - static: *targets()* (where to move things; *arrange()* moves them), or
      *arrange()* itself;
    - dynamic: *placeNode()* (where something new, or dropped, goes) and
      *adjust()* (what to move after a command); and *activate()*, if it
      arranges things when it's made the view's dynamic layout.
  '''
  NAME:str = ""
  "What it's called: in *LAYOUTS*, the menus, and the view's file."
  CATEGORIES:tuple[str, ...] = ()
  "The kinds of layout it is: of *CATEGORIES*."
  PARAMETERS:tuple[LayoutParameter, ...] = ()
  "The keyword arguments its constructor takes (besides the view)."

  def __init__(self, view, **kwargs):
    '''
    :param view: The view it arranges.
    :type view: SNGView
    :param kwargs: Its parameters (see *PARAMETERS*): those not given are their defaults.
    :raises TypeError: if a keyword isn't one of its parameters.
    '''
    from sn.view.graphics.sngView import SNGView
    assert isinstance(view, SNGView)
    self.view = view
    names = {p.name for p in self.PARAMETERS}
    unknown = set(kwargs) - names
    if unknown:
      raise TypeError(f'{type(self).__name__}: unknown parameter(s): {", ".join(sorted(unknown))}.')
    self.params:dict[str, Any] = {}
    "Its parameters' values (see *PARAMETERS*): relations as *Relation*s."
    for p in self.PARAMETERS:
      v = kwargs.get(p.name, p.default)
      if p.kind == "relation" and isinstance(v, str):
        name = v
        v = relationNamed(view.model, name)
        if v is None:
          logger.warning(f'{type(self).__name__}: there\'s no relation type "{name}" in {view.model.name} '
                         f'or its super-models: its {p.name} is the default.')
      self.params[p.name] = v

  # ---- parameters -------------------------------------------------------------

  @classmethod
  def askParameters(cls, view, category:str, current:dict[str, Any]|None=None, parent=None) -> dict[str, Any]|None:
    '''
    Ask the user for this kind of layout's parameters (those that matter for
    *category*: see *LayoutParameter.categories*), with a dialog made from
    *PARAMETERS* (see *layoutDialog.LayoutDialog*) -- or, if it has none,
    don't.

    :param view: The view it's for.
    :type view: SNGView
    :param category: How it'll be used: *STATIC* or *DYNAMIC*.
    :type category: str
    :param current: The values to start with, if not the defaults.
    :type current: dict[str, Any] | None
    :param parent: The window the dialog's over.
    :returns: The keyword arguments for its constructor, or None if the user cancelled.
    :rtype: dict[str, Any] | None
    '''
    asked = [p for p in cls.PARAMETERS if category in p.categories]
    values = {p.name: (current or {}).get(p.name, p.default) for p in cls.PARAMETERS}
    if not asked:
      return values
    from sn.view.graphics.layoutDialog import LayoutDialog
    title = f"{'arrange now' if category == STATIC else 'keep arranged'}: {cls.NAME}"
    d = LayoutDialog(parent if parent is not None else view.window, title, cls, asked, values, view)
    return d.result

  @classmethod
  def parameterChanged(cls, view, name:str, values:dict[str, Any]) -> dict[str, Any]:
    '''
    Called by the dialog when the user changes a parameter: eg: to change
    another to suit it. By default, nothing does.

    :param view: The view it's for.
    :type view: SNGView
    :param name: The parameter changed.
    :type name: str
    :param values: All the parameters' values, now.
    :type values: dict[str, Any]
    :returns: The values to show.
    :rtype: dict[str, Any]
    '''
    return values

  def parameters(self) -> dict[str, Any]:
    '''
    :returns: Its parameters' values: as keyword arguments for its constructor.
    :rtype: dict[str, Any]
    '''
    return dict(self.params)

  # ---- saving it with the view ---------------------------------------------------

  def state(self) -> str:
    '''
    :returns: What's saved with the view about it, as its dynamic layout (see
      *fromState()*): its name, parameters, and anything else it keeps (see
      *extraState()*): eg: "name=tree;relation=includes;direction=right;pins=12,40".
    :rtype: str
    '''
    return self.encodeParameters(self.params, self.extraState())

  @classmethod
  def encodeParameters(cls, params:dict[str, Any], extra:dict[str, str]={}) -> str:
    '''
    :param params: Values of its parameters (see *PARAMETERS*): a relation as a
      *Relation* or its name.
    :type params: dict[str, Any]
    :param extra: Anything else to say (see *extraState()*).
    :type extra: dict[str, str]
    :returns: Them as text: its name, then each parameter's value (see
      *decodeParameters()*): eg: "name=tree;relation=includes;direction=right".
    :rtype: str
    '''
    parts = {"name": cls.NAME}
    for p in cls.PARAMETERS:
      v = params.get(p.name)
      if v is None:
        continue
      parts[p.name] = str(getattr(v, "name", v)) if p.kind == "relation" else ("1" if v else "0") if p.kind == "bool" else str(v)
    parts.update(extra)
    return ";".join(f"{k}={v}" for k, v in parts.items())

  @staticmethod
  def decodeParameters(text:str) -> "tuple[type[LayoutHeuristic], dict[str, Any], dict[str, str]]|None":
    '''
    :param text: What *encodeParameters()* made.
    :type text: str
    :returns: The kind of layout it's of, its parameters' values (keyword
      arguments for its constructor: a relation by its name), and everything
      said (eg: for *restoreExtraState()*) -- or None if there's no such layout.
    :rtype: tuple[type[LayoutHeuristic], dict[str, Any], dict[str, str]] | None
    '''
    state = dict(kv.split("=", 1) for kv in text.split(";") if "=" in kv)
    cls = LAYOUTS.get(state.get("name", ""))
    if cls is None:
      return None
    kwargs:dict[str, Any] = {}
    for p in cls.PARAMETERS:
      if p.name in state:
        v = state[p.name]
        try:
          kwargs[p.name] = int(v) if p.kind == "int" else (v == "1") if p.kind == "bool" else v
        except ValueError: # (not a number: the default, then)
          pass
    return cls, kwargs, state

  def extraState(self) -> dict[str, str]:
    '''
    :returns: Anything else it keeps that's saved with the view (see *state()*):
      none, by default. (Values mustn't contain ";" or "=".)
    :rtype: dict[str, str]
    '''
    return {}

  def restoreExtraState(self, state:dict[str, str]) -> None:
    '''
    Put back what *extraState()* saved.

    :param state: What was saved (and the parameters).
    :type state: dict[str, str]
    '''
    pass

  @staticmethod
  def fromState(view, text:str) -> "LayoutHeuristic|None":
    '''
    :param view: A view, being read.
    :type view: SNGView
    :param text: What *state()* saved.
    :type text: str
    :returns: The layout it describes -- or None if there's no such layout.
    :rtype: LayoutHeuristic | None
    '''
    decoded = LayoutHeuristic.decodeParameters(text)
    if decoded is None:
      return None
    cls, kwargs, state = decoded
    ret = cls(view, **kwargs)
    ret.restoreExtraState(state)
    return ret

  # ---- static ---------------------------------------------------------------------

  def targets(self) -> dict[VObject, tuple[float, float]]:
    '''
    :returns: Where to move things to arrange the view (their top left
      corners): only what's to move. None, by default.
    :rtype: dict[VObject, tuple[float, float]]
    '''
    return {}

  def arrange(self, animate:bool=True) -> "LayoutMoves|None":
    '''
    Arrange the view (see *targets()*), as one undoable command.

    :param animate: Whether to move things smoothly (see *tween()*), rather than at once.
    :type animate: bool
    :returns: The command, or None if nothing moved.
    :rtype: LayoutMoves | None
    '''
    remember = getattr(self.view, "rememberLayoutParameters", None)
    if remember is not None: # (offered next time: see SNGView.lastLayoutParameters())
      remember(self, STATIC)
    cmd = LayoutMoves(self.view, f"arrange: {self.NAME}", self.targets(), animate=animate)
    self.arranged(cmd)
    if cmd.isEmpty():
      return None
    self.view.context.doList.do(cmd)
    return cmd

  def arranged(self, cmd:"LayoutMoves") -> None:
    '''
    Called by *arrange()* with the command it's about to do: eg: to add to
    what it undoes (see *LayoutMoves.also*). Nothing, by default.

    :param cmd:
    :type cmd: LayoutMoves
    '''
    pass

  def placeAll(self) -> None:
    "As *arrange()*."
    self.arrange()

  # ---- dynamic --------------------------------------------------------------------

  def _setDirection(self, node:VObject, referenceNode:Optional[VObject], loc:Optional[Point]=None):
    '''
    :param node:
    :type node: VObject
    :param referenceNode:
    :type referenceNode: Optional[VObject]
    :param loc:
    :type loc: Optional[Point]
    :returns:
    :rtype:
    '''
    if loc is not None:
      return Direction.NEAREST
    if referenceNode is None: # and loc is None
      return Direction.LATERAL
    else: #referenceNode is not None and loc is None
      if node.modelObject.isa(referenceNode.modelObject):
        return Direction.SUB
      elif referenceNode:
        return Direction.SUPER
    
  def findOverlapping(self, rect:list[int], exclude:list[int]=[]) -> list[int]:
    '''
    :param rect:
    :type rect: list[int]
    :param exclude:
    :type exclude: list[int]
    :return: The (possible zero-length) list of 'vis/shape'-tagged tk.Canvas object ids
        that overlap with bounding box of *node*.
    :rtype: list[int]
    '''
    overlapping = self.view.intersectTag(self.view.canvas.find_overlapping(*rect), 'vis/shape', exclude)
    return overlapping
    
  def __call__(self, node:Optional[VObject]=None, **kwargs):
    '''
    Place *node* (see *placeNode()*) -- or, if it's None, everything (see *placeAll()*).

    :param node:
    :type node: Optional[VObject]
    :param kwargs: For *placeNode()*.
    '''
    if node is not None:
      self.placeNode(node, **kwargs)
    else:
      self.placeAll()

  def placeNode(self, node:VObject,
                referenceNode:Optional[VObject]=None,
                direction:Direction=Direction.UNSPECIFIED,
                loc:Optional[Point]=None, **kwargs) -> Point|tuple[float, float]:
    '''
    As the view's dynamic layout: put *node* -- just made (eg: below
    *referenceNode*, its supertype), or dropped -- somewhere suitable. By
    default, it stays where it is.

    :param node:
    :type node: VObject
    :param referenceNode: What it's to go near, if anything.
    :type referenceNode: Optional[VObject]
    :param direction: Which way from *referenceNode*.
    :type direction: Direction
    :param loc: Where to start looking, if not where it is.
    :type loc: Optional[Point]
    :param kwargs: Eg: "aggressive", "within" (see *FindFree.placeNode()*).
    :returns: Where it's put (its top left).
    :rtype: Point | tuple[float, float]
    '''
    bb = node.boundingBox()
    return bb[0], bb[1]

  def activate(self) -> None:
    '''
    Called when it's made the view's dynamic layout (see
    *SNGView.setDynamicLayout()*): eg: to arrange things as it would keep them.
    Nothing, by default.
    '''
    pass

  def adjust(self, command:Command) -> "LayoutMoves|None":
    '''
    As the view's dynamic layout: called after each command that changed the
    view (see *sngView.ViewDoList*), to say what else to move. The command
    returned is done, and undone with *command*, as one.

    :param command: The command just done.
    :type command: Command
    :returns: What to move (not done yet), or None for nothing (the default).
    :rtype: LayoutMoves | None
    '''
    return None

LayoutHieristic = LayoutHeuristic

def fitToText(vo:VObject) -> VObject:
  '''
  :param vo: A node or relation (its label) in a view: eg: just made.
  :type vo: VObject
  :returns: It, sized to its text now -- as it would be when it's next drawn
    (see *decorators.WrappingText.fitOwner()*) -- so a layout can place it by its size.
  :rtype: VObject
  '''
  from sn.view.graphics.decorators import WrappingText
  if vo._shape is None or vo._shape.id is None: # (not drawn yet: its shape -- and so the room for its text -- isn't set up)
    vo.view.freshPaint()
    vo.draw()
  text = vo.decorators.get("text")
  if isinstance(text, WrappingText):
    text.fitOwner()
  return vo

def layoutSize(vo:VObject) -> tuple[float, float]:
  '''
  :param vo: A node or relation (its label) in a view.
  :type vo: VObject
  :returns: Its (width, height) as it'll be when it's moved: fitted to its
    text (see *fitToText()*), and at least the minimums a box is held to when
    it's set (see *VObject.boundingBox()*: "vis/minSize", and *VObject.minHeight()*)
    -- which a box first fitted to a little text may be smaller than.
  :rtype: tuple[float, float]
  '''
  bb = fitToText(vo).boundingBox()
  w, h = bb[2] - bb[0], bb[3] - bb[1]
  try:
    return max(w, float(vo.cache["vis/minSize"])), max(h, float(vo.minHeight()))
  except Exception: # (eg: no such attribute)
    return w, h
"The old (misspelled) name."

@registerLayout
class NoLayout(LayoutHeuristic):
  '''
  The dynamic layout that does nothing: things stay where they're made or dropped.
  '''
  NAME = "none"
  CATEGORIES = (DYNAMIC,)

@registerLayout
class GatherLayout(LayoutHeuristic):
  '''
  Herd outlying objects back to the main pack (see *SNGView.gatherNodes()*).
  '''
  NAME = "gather nodes"
  CATEGORIES = (STATIC,)

  @override
  def arrange(self, animate:bool=True) -> "LayoutMoves|None":
    self.view.gatherNodes()
    return None

# ---- moving things ------------------------------------------------------------------

TWEEN_STEPS = 8
"How many steps a tweened move takes (see *tween()*)."

TWEEN_INTERVAL = 25
"Milliseconds between a tweened move's steps."

TWEEN_MAX = 400
"The most objects moved smoothly: more are moved at once (it'd be slow)."

def _settled(view) -> None:
  '''
  A layout's moves are done: repaint the view once things are idle (see
  *SNGView.repaintSoon()*) and then grow its scroll region to take in
  everything (see *SNGView.resetScrollRegion()*) -- or what's been moved off
  past its edge can't be scrolled to.

  :param view:
  :type view: SNGView
  '''
  view.repaintSoon()
  if getattr(view, "canvas", None):
    view.canvas.after_idle(view.resetScrollRegion) # (after the repaint: its after_idle was asked for first)

class _Tween:
  '''
  A tweened move under way (see *tween()*).
  '''
  def __init__(self, view, moves:list[tuple[VObject, tuple[float, float], tuple[float, float]]]):
    self.view = view
    self.moves = moves
    self.step = 0
    self.job = view.canvas.after(TWEEN_INTERVAL, self.next)

  def next(self) -> None:
    self.step += 1
    if self.step >= TWEEN_STEPS:
      self.finish()
      return
    t = self.step / TWEEN_STEPS
    t = t * t * (3 - 2 * t) # (eased: slow, fast, slow)
    for vo, (x0, y0), (x1, y1) in self.moves:
      if vo._isConnected():
        vo.moveTo(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, adjustPos=False, carry=False)
    self.job = self.view.canvas.after(TWEEN_INTERVAL, self.next)

  def finish(self) -> None:
    '''Put everything where it's going, now.'''
    try:
      self.view.canvas.after_cancel(self.job)
    except Exception:
      pass
    if self.view.__dict__.get("_tween") is self:
      self.view._tween = None
    for vo, _, (x1, y1) in self.moves:
      if vo._isConnected():
        vo.moveTo(x1, y1, adjustPos=False, carry=False)
    _settled(self.view)

def finishTween(view) -> None:
  '''
  Finish the view's tweened move, if one's under way (see *tween()*): eg:
  before anything else is done, undone or saved.

  :param view:
  :type view: SNGView
  '''
  t = view.__dict__.get("_tween")
  if t is not None:
    t.finish()

def tween(view, moves:list[tuple[VObject, tuple[float, float], tuple[float, float]]]) -> None:
  '''
  Move things smoothly, from where they are to where they're going, over
  *TWEEN_STEPS* steps -- in the view's event loop, not in the background: a
  tweened move under way is finished (see *finishTween()*) before anything
  else is done to the view. (At once if there are more than *TWEEN_MAX*, or
  there's no window.)

  :param view:
  :type view: SNGView
  :param moves: (object, from, to): top left corners.
  :type moves: list[tuple[VObject, tuple[float, float], tuple[float, float]]]
  '''
  finishTween(view)
  if not moves:
    return
  if not getattr(view, "canvas", None) or len(moves) > TWEEN_MAX:
    for vo, _, (x1, y1) in moves:
      vo.moveTo(x1, y1, adjustPos=False, carry=False)
    _settled(view)
    return
  view._tween = _Tween(view, moves)

class LayoutMoves(Command):
  '''
  A layout's moves, as one undoable command: tweened (see *tween()*) when
  first done, if asked; at once when redone or undone. A relation's label it
  moves is pinned (no longer floats between its ends) -- and floats again
  when it's undone, if it did before.
  '''
  isLayout = True
  "So the view's dynamic layout doesn't adjust after it (see *sngView.ViewDoList*)."

  def __init__(self, view, name:str, targets:dict[VObject, tuple[float, float]], animate:bool=True):
    '''
    :param view:
    :type view: SNGView
    :param name: What the undo menu calls it.
    :type name: str
    :param targets: Where things go (their top left corners): those already there are left out.
    :type targets: dict[VObject, tuple[float, float]]
    :param animate: Whether to move them smoothly when it's first done.
    :type animate: bool
    '''
    super().__init__(name)
    self.view = view
    self.animate = animate
    self.first = True
    self.moves:list[tuple[VObject, tuple[float, float], tuple[float, float], bool|None]] = []
    "(object, from, to, whether it floated: for a relation's label)"
    for vo, (x, y) in targets.items():
      bb = vo.boundingBox()
      if abs(bb[0] - x) >= 0.5 or abs(bb[1] - y) >= 0.5:
        self.moves.append((vo, (bb[0], bb[1]), (x, y), vo.floating() if isinstance(vo, VRelation) else None))
    self.also:list[tuple[Any, Any]] = []
    '''Other things it does and undoes: (do, undo) pairs of callables: eg: a
    layout's own state (see *TreeLayout*'s pins).'''

  def isEmpty(self) -> bool:
    ":returns: Whether it does nothing."
    return not self.moves and not self.also

  @override
  def do(self) -> None:
    super().do()
    finishTween(self.view)
    for do, _ in self.also:
      do()
    for vo, _, _, floated in self.moves:
      if floated is not None:
        vo._floatingAnchor = False #type: ignore[attr-defined] # (directly: not recentred between its ends first)
    if self.first and self.animate:
      tween(self.view, [(vo, a, b) for vo, a, b, _ in self.moves if vo._isConnected()])
    else:
      for vo, _, (x, y), _ in self.moves:
        if vo._isConnected():
          vo.moveTo(x, y, adjustPos=False, carry=False)
      _settled(self.view)
    self.first = False

  @override
  def undo(self) -> None:
    super().undo()
    finishTween(self.view)
    for vo, (x, y), _, floated in reversed(self.moves):
      if vo._isConnected():
        vo.moveTo(x, y, adjustPos=False, carry=False)
        if floated is not None:
          vo.floating(floated) #type: ignore[attr-defined]
    for _, undo in reversed(self.also):
      undo()
    _settled(self.view)

  @override
  def delete(self) -> None:
    super().delete()
    self.moves, self.also = [], []

UNBOUNDED = 10**9
"A limit (view units) that's no limit: objects may be placed anywhere, at negative coordinates too."

@registerLayout
class FindFree(LayoutHeuristic):
  '''
  "avoid overlaps": the default dynamic layout. What's made, or dropped, is
  put in the nearest free place (see *placeNode()*): where it doesn't overlap
  anything else. Nothing else moves.
  '''
  NAME = "avoid overlaps"
  CATEGORIES = (DYNAMIC,)

  def __init__(self, view, **kwargs):
    '''
    :param view:
    :type view: SNGView
    '''
    super().__init__(view, **kwargs)
    self.quanta = 10
    'Used when searching for non-overlapping space'
    self.expandFactor_relations = 5
    self.expandFactor_nodes = 15
    'Clear space (view units) a node wants around it (relation labels: *expandFactor_relations*).'
    self.topMargin = 30
    'Where the isa levels start, for an aggressive placement (see *placeNode()*).'
    self.limit = [-UNBOUNDED, -UNBOUNDED, UNBOUNDED, UNBOUNDED]
    'Where objects may be placed: anywhere (coordinates may be negative).'
    self.isaLevelSpacing = 120
    
  @override
  def placeNode(self, node:VObject, 
                referenceNode:Optional[VObject]=None, 
                direction:Direction=Direction.UNSPECIFIED, 
                loc:Optional[Point]=None,
                aggressive:bool=False, 
                within:Optional[list[float]]=None,
                **kwargs) -> Point:
    '''
    :param node:
    :type node: VObject
    :param within: Where it may be put (x1, y1, x2, y2: view coords), if not anywhere: eg: the visible part of the view.
    :type within: Optional[list[float]]
    :param referenceNode:
    :type referenceNode: Optional[VObject]
    :param direction:
    :type direction: Direction
    :param loc:
    :type loc: Optional[Point]
    :param aggressive:
    :type aggressive: bool
    :param kwargs:
    :type kwargs:
    :returns:
    :rtype: Point
    '''
    from sn.view.graphics.vrelations import VRelation
    expandFactor = self.expandFactor_relations \
          if node.modelObject is not None and node.modelObject.isIndividual() and isinstance(node, VRelation) \
          else self.expandFactor_nodes
    
    if direction == Direction.UNSPECIFIED:
      if loc is not None:
        direction = Direction.NEAREST
      # elif isinstance(node, VIsa):
      #   if referenceNode is not None and node.modelObject.to == referenceNode.modelObject:
      #     direction = Direction.SUPER
      #   else:
      #     direction = Direction.SUB
      elif referenceNode is not None:
        if node.modelObject.isa(referenceNode.modelObject):
          direction = Direction.SUB
        elif referenceNode.modelObject.isa(node.modelObject):
          direction = Direction.SUPER
        else:
          direction = Direction.LATERAL
      else:
        direction = Direction.LATERAL
        
    #direction = Direction.NEAREST # Get rid of this!!!! 
    assert direction != Direction.UNSPECIFIED   
        
    maxRings = 100 # (how far out to look for a free spot: see LABEL_PLACEMENT_PREF)
    if isinstance(node, VRelation):
      level = labelPlacementLevel()
      if level == 0: # (labels stay where they're made: midway between their ends)
        bb = node.boundingBox()
        return bb[0], bb[1]
      maxRings = level * level

    def place(rect:list[int], 
              expandFactor:int, 
              quanta:int=self.quanta, 
              limit:list[int]=self.limit, 
              exclude=[]) -> tuple[int, int]|None:
      assert len(rect) == 4
      rect = [int(i) for i in rect]
      assert len(limit) == 4
      limit = [int(i) for i in limit]
      w = rect[2] - rect[0]
      h = rect[3] - rect[1]
      assert w>0
      assert h>0
      
      for dist in range(0, maxRings): # the width/height of the rectangular scan
        yStart   = max(limit[1], rect[1]-dist*quanta)
        yEnd     = min(limit[3], rect[1]+dist*quanta)
        for y in range(yStart, yEnd+1, quanta):
          xStart = max(limit[0], rect[0]-dist*quanta)
          xEnd   = min(limit[2], rect[0]+dist*quanta)
          # the ring's perimeter: all of its top and bottom rows, just the ends of the others
          xIncr  = quanta if y==yStart or y==yEnd else max(1, xEnd-xStart)
          for x in range(xStart, xEnd+1, xIncr):
            r = [x, y, x+w, y+h]
            overlapping = self.findOverlapping(expandRect(r, expandFactor), exclude)
            if len(overlapping) == 0:
              return x,y
      return None # (nowhere free within maxRings)
      
    rect = node.boundingBox()
    if loc is not None:
      rect = [loc.x, loc.y, loc.x+rect[2]-rect[0], loc.y+rect[3]-rect[1]]
    # ignore our own shape and our own relations' label shapes (canvas item ids --
    # not rel._id, the view object's id, a different numbering altogether)
    exclude = [node._shape.id] + [rel._shape.id for rel in node.relations if rel._shape is not None and rel._shape.id is not None]
    
    leftLimit, topLimit, rightLimit, bottomLimit = self.limit
    if within is not None: # (room for its whole box)
      w, h = rect[2] - rect[0], rect[3] - rect[1]
      leftLimit, topLimit = max(leftLimit, within[0]), max(topLimit, within[1])
      rightLimit, bottomLimit = min(rightLimit, within[2] - w), min(bottomLimit, within[3] - h)
    
    if direction == Direction.NEAREST:
      pass
      
    elif direction == Direction.SUB:
      if referenceNode is not None:
        topLimit = referenceNode.boundingBox()[3]+expandFactor* \
           (2 if node.__class__ is referenceNode.__class__ else 1)
          
      else:
        topLimit = rect[1]
      
    elif direction == Direction.SUPER:
      h = rect[3] - rect[1]
      if referenceNode is not None:
        bottomLimit = referenceNode.boundingBox()[1]-expandFactor
      else:
        bottomLimit = rect[1]-h-expandFactor
      
    elif direction == Direction.LATERAL:
      if referenceNode is not None:
        leftLimit = referenceNode.boundingBox()[2]+expandFactor
      else:
        leftLimit = rect[0]
        
    if node.modelObject is not None and (node.modelObject.isType() or isinstance(node, Node)) and aggressive:
      topLimit = max(topLimit, self.isaLevelSpacing*depth(node.modelObject)+self.topMargin)
      
    # what a context contains (a relation's label too), dropped in its pane, stays in it (see SNGView.containmentHomes())
    if node.modelObject is not None:
      win, pane = self.view.containmentHomes([node]).get(node, (None, ""))
      cx, cy = node.centerPt()
      px1, py1, px2, py2 = self.view.homeRect(win, pane) if win is not None else (0, 0, -1, -1)
      if px1 <= cx <= px2 and py1 <= cy <= py2:
        w, h = rect[2] - rect[0], rect[3] - rect[1]
        inside = [max(leftLimit, px1 + expandFactor), max(topLimit, py1 + expandFactor),
                  min(rightLimit, px2 - expandFactor - w), min(bottomLimit, py2 - expandFactor - h)]
        if inside[0] <= inside[2] and inside[1] <= inside[3]:
          leftLimit, topLimit, rightLimit, bottomLimit = inside

    finalLimit = [int(i) for i in [leftLimit, topLimit, rightLimit, bottomLimit]]
    pt = place(rect, expandFactor=expandFactor, exclude=exclude, limit=finalLimit)
    if pt is None: # (nowhere free close enough: it stays where it is)
      bb = node.boundingBox()
      return bb[0], bb[1]
    
    # if pt[0]!=rect[0] or pt[1]!=rect[1]:
    #   logger.debug(f'Node "{node.modelObject.name}:{node.modelObject._id}" moving in direction {direction}, limit={finalLimit} to {pt}, ref={referenceNode}.')
    
    node.moveTo(*pt, adjustPos=False)
    
    return pt
    
      
      
              
  @override
  def placeAll(self):
    pass # (not a static layout)


def intoRect(box:list[float], rect:list[float], margin:float=0.0, topMargin:float|None=None) -> tuple[float, float]:
  '''
  How far to move *box* to put it inside *rect*, *margin* in from its edges
  (*topMargin* from its top, if given) -- the least move that does it; centred
  in an axis it's too big for.

  :param box: [x1, y1, x2, y2].
  :type box: list[float]
  :param rect: [x1, y1, x2, y2].
  :type rect: list[float]
  :param margin: The space to leave inside *rect*'s edges.
  :type margin: float
  :param topMargin: The space to leave at its top (default: *margin*).
  :type topMargin: float | None
  :returns: (dx, dy).
  :rtype: tuple[float, float]
  '''
  ret = []
  for k, before in ((0, margin), (1, margin if topMargin is None else topMargin)):
    lo, hi = rect[k] + before, rect[k + 2] - margin
    b1, b2 = box[k], box[k + 2]
    if b2 - b1 > hi - lo:
      ret.append((lo + hi) / 2 - (b1 + b2) / 2)
    elif b1 < lo:
      ret.append(lo - b1)
    elif b2 > hi:
      ret.append(hi - b2)
    else:
      ret.append(0.0)
  return ret[0], ret[1]

# ---- Gathering outliers ------------------------------------------------------

def _median(values:list[float]) -> float:
  '''
  :param values:
  :type values: list[float]
  :returns:
  :rtype: float
  '''
  if not values:
    return 0.0
  s = sorted(values)
  n = len(s)
  return s[n//2] if n % 2 else (s[n//2 - 1] + s[n//2]) / 2

def gatherAxisShifts(intervals:list[tuple[float, float]], *,
                     gapFactor:float=6.0, minGap:float=300.0) -> list[float]:
  '''
  One axis of :py:func:`gatherShifts`: how far to shift each interval so that
  no group of intervals is stranded far from the main pack.

  The intervals are swept in order of their low ends, keeping track of the
  furthest high end so far; wherever the next interval starts more than
  *maxGap* beyond that, a new *run* begins. The run with the most intervals
  is the pack and stays put. Every oversized gap is shrunk to *targetGap*,
  and everything beyond it (away from the pack) shifts toward the pack by the
  amount removed -- so a stranded group keeps its internal arrangement.

  The thresholds come from the drawing itself: with *S* the median interval
  length and *G* the typical gap between consecutive runs of overlapping
  intervals, ``maxGap = max(gapFactor * max(G, S), minGap)`` and
  ``targetGap = max(G, S/2)``. *G* is the median of the *smaller half* of the
  gaps, so that it isn't dominated by the very outliers it's meant to find
  (in a small drawing, one or two huge gaps can be most of the gaps).

  It's O(n log n) (one sort) and uses no distances -- just comparisons and
  differences.

  :param intervals: (low, high) extents along one axis.
  :type intervals: list[tuple[float, float]]
  :param gapFactor: How many times the typical spacing a gap must exceed to
    count as stranding what lies beyond it.
  :type gapFactor: float
  :param minGap: No gap smaller than this counts as stranding, however
    tightly packed the rest of the drawing is -- so a normal (if loose)
    layout is left alone.
  :type minGap: float
  :returns: The shift for each interval, in the same order.
  :rtype: list[float]
  '''
  n = len(intervals)
  shifts = [0.0] * n
  if n < 3:
    return shifts
  order = sorted(range(n), key=lambda i: intervals[i][0])

  # the gaps between consecutive runs of overlapping intervals
  gaps:list[float] = []
  reach = intervals[order[0]][1]
  for i in order[1:]:
    lo, hi = intervals[i]
    if lo > reach:
      gaps.append(lo - reach)
    reach = max(reach, hi)
  S = _median([hi - lo for lo, hi in intervals])
  G = _median(sorted(gaps)[:max(1, len(gaps)//2)])
  maxGap = max(gapFactor * max(G, S), minGap)
  targetGap = max(G, S / 2)
  if maxGap <= 0:
    return shifts

  # split into runs at the oversized gaps
  runs:list[list[int]] = [[order[0]]]
  gapAfter:list[float] = []  # gapAfter[k] is the gap between runs k and k+1
  reach = intervals[order[0]][1]
  for i in order[1:]:
    lo, hi = intervals[i]
    if lo - reach > maxGap:
      gapAfter.append(lo - reach)
      runs.append([i])
    else:
      runs[-1].append(i)
    reach = max(reach, hi)
  if len(runs) == 1:
    return shifts

  pack = max(range(len(runs)), key=lambda k: len(runs[k]))
  removed = 0.0
  for k in range(pack + 1, len(runs)):  # beyond the pack's high end: shift down
    removed += gapAfter[k - 1] - targetGap
    for i in runs[k]:
      shifts[i] = -removed
  removed = 0.0
  for k in range(pack - 1, -1, -1):     # beyond its low end: shift up
    removed += gapAfter[k] - targetGap
    for i in runs[k]:
      shifts[i] = removed
  return shifts

def gatherShifts(boxes:list[list[float]], *, gapFactor:float=6.0, minGap:float=300.0) -> list[tuple[float, float]]:
  '''
  Herd outlying boxes back toward the main pack, treating the x and y axes
  independently (see :py:func:`gatherAxisShifts`): something flung far away on
  only one axis is only pulled back on that axis.

  :param boxes: [x1, y1, x2, y2] bounding boxes.
  :type boxes: list[list[float]]
  :param gapFactor:
  :type gapFactor: float
  :param minGap:
  :type minGap: float
  :returns: The (dx, dy) to move each box by, in the same order.
  :rtype: list[tuple[float, float]]
  '''
  dxs = gatherAxisShifts([(b[0], b[2]) for b in boxes], gapFactor=gapFactor, minGap=minGap)
  dys = gatherAxisShifts([(b[1], b[3]) for b in boxes], gapFactor=gapFactor, minGap=minGap)
  return list(zip(dxs, dys))

# ---- Gathering into a context window -----------------------------------------

def freeSpotIn(box:list[float], rect:list[float], obstacles:Iterable[list[float]], *,
               margin:float=10.0, topMargin:float|None=None, gap:float|tuple[float, float]=10.0, step:float=10.0,
               rows:bool=False) -> tuple[float, float]|None:
  '''
  How far to move *box* to put it inside *rect* (*margin* in from its edges;
  *topMargin* from its top, if given), clear of every one of *obstacles* by
  *gap* (or (across, down)), on a *step* grid: the spot nearest to where *intoRect()* would put it
  (a box that's already inside and clear stays put) -- or, with *rows*, the
  first free spot reading *rect* row by row from its top left (so things
  brought from far away are set out tidily).

  :param box: [x1, y1, x2, y2].
  :type box: list[float]
  :param rect: [x1, y1, x2, y2].
  :type rect: list[float]
  :param obstacles: Boxes to keep clear of.
  :type obstacles: Iterable[list[float]]
  :returns: (dx, dy) -- or None if there's no room.
  :rtype: tuple[float, float] | None
  '''
  obs = [o for o in obstacles]
  gx, gy = gap if isinstance(gap, tuple) else (gap, gap)
  w, h = box[2] - box[0], box[3] - box[1]
  lo_x, lo_y = rect[0] + margin, rect[1] + (margin if topMargin is None else topMargin)
  hi_x, hi_y = rect[2] - margin - w, rect[3] - margin - h
  if hi_x < lo_x or hi_y < lo_y:
    return None
  def clear(x:float, y:float) -> bool:
    return all(x + w + gx <= o[0] or o[2] + gx <= x or y + h + gy <= o[1] or o[3] + gy <= y for o in obs)
  nx, ny = int((hi_x - lo_x) // step), int((hi_y - lo_y) // step)
  spots = [(lo_x + i * step, lo_y + j * step) for i in range(nx + 1) for j in range(ny + 1)]
  if rows:
    spots.sort(key=lambda p: (p[1], p[0]))
  else:
    ex, ey = intoRect(box, rect, margin, topMargin)
    tx, ty = box[0] + ex, box[1] + ey # (where it would go, ignoring the obstacles)
    if clear(tx, ty):
      return ex, ey
    spots.sort(key=lambda p: (p[0] - tx) ** 2 + (p[1] - ty) ** 2)
  for x, y in spots:
    if clear(x, y):
      return x - box[0], y - box[1]
  return None

# ---- Keeping out of context windows ------------------------------------------

def clearOf(box:list[float], keepOut:list[list[float]], obstacles:list[list[float]]=[], *,
            within:list[float]|None=None, gap:float=10.0) -> tuple[float, float]|None:
  '''
  How far to move *box* -- as little as can be -- so it's *gap* clear of every
  rect in *keepOut* (eg: windows it doesn't belong in), clear of *obstacles*
  too (by *gap* / 2), and inside *within* (if given: eg: its own pane). The
  candidates are the positions that just clear something (or line up with
  *within*'s edges), alone and in pairs (one across, one down), so the result
  is the nearest one there is, but not necessarily the very nearest point.

  :param box: [x1, y1, x2, y2].
  :type box: list[float]
  :param keepOut: Rects to stay out of.
  :type keepOut: list[list[float]]
  :param obstacles: Rects not to land on (if that can be helped: if there's
    no such place, they're ignored).
  :type obstacles: list[list[float]]
  :param within: A rect to stay in.
  :type within: list[float] | None
  :param gap: The clearance.
  :type gap: float
  :returns: (dx, dy), (0, 0) if it's fine where it is -- or None if there's no place.
  :rtype: tuple[float, float] | None
  '''
  w, h = box[2] - box[0], box[3] - box[1]
  def hits(x:float, y:float, rects:list[list[float]], g:float) -> bool:
    return any(x < r[2] + g and r[0] - g < x + w and y < r[3] + g and r[1] - g < y + h for r in rects)
  def inside(x:float, y:float) -> bool:
    return within is None or (within[0] <= x and within[1] <= y and x + w <= within[2] and y + h <= within[3])
  def search(rects:list[list[float]]) -> tuple[float, float]|None:
    xs, ys = {box[0]}, {box[1]}
    for r, g in [*((r, gap) for r in keepOut), *((r, gap / 2) for r in rects)]:
      xs |= {r[0] - g - w, r[2] + g}
      ys |= {r[1] - g - h, r[3] + g}
    if within is not None:
      xs |= {within[0], within[2] - w}
      ys |= {within[1], within[3] - h}
    best:tuple[float, float, float]|None = None
    for x in xs:
      for y in ys:
        d = (x - box[0]) ** 2 + (y - box[1]) ** 2
        if (best is None or d < best[0]) and inside(x, y) and not hits(x, y, keepOut, gap) and not hits(x, y, rects, gap / 2):
          best = (d, x, y)
    return None if best is None else (best[1] - box[0], best[2] - box[1])
  if inside(box[0], box[1]) and not hits(box[0], box[1], keepOut, gap):
    return 0.0, 0.0 # (nothing to do: it isn't in the way -- whatever it may overlap otherwise)
  return search(obstacles) or (search([]) if obstacles else None)
