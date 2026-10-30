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
import heapq
import itertools
import math
import time
from abc import ABC
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Optional, override, Iterable, Sequence, Collection
from sn.view.graphics.vobjects import VObject
from sn.view.graphics.vrelations import VRelation
from util.utils import Point
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
  :return: the isa-depth of *obj*: the number of isa steps on the longest path
    from *obj* up to the top (0 for the top itself).
  '''
  i:int = -1
  p = [obj]
  while len(p) > 0:
    q = []
    for pp in p:
      q += list(pp.getParents())
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
  '''"relation" (a relation type: a *Relation*, or its name), "relations"
  (an ordered table of relation types: a *relationTable.RelationTable*, or
  its text), "choice" (one of *choices*), "int" or "bool".'''
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
  :returns: The layout heuristics (in *LAYOUTS*) of that kind, in the order they were registered.
  '''
  return [c for c in LAYOUTS.values() if category in c.CATEGORIES]

def relationTypes(model:Model) -> list[Relation]:
  '''
  :param model: A model.
  :returns: The relation types a layout can follow: isa, then the model's
    own and its super-models' (eg: an ontology it's built on: *values()* has
    only its own), but not the system's or the base rules' (see
    *Model.implicitSuperDBs()*), by name.
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

def nodeTypes(model:Model) -> list[Node]:
  '''
  :param model: A model.
  :returns: Its node types (not relation types): its own and its
    super-models' (eg: an ontology it's built on), but not the system's or the
    base rules' (see *relationTypes()*), by name.
  '''
  implicit = model.implicitSuperDBs()
  models = [model] + [db for db in model.allSuperDBs() if isinstance(db, Model) and not any(db is i for i in implicit)]
  seen:set[int] = set()
  ret:list[Node] = []
  for m in models:
    if id(m) in seen:
      continue
    seen.add(id(m))
    ret += [n for n in m.values() if isinstance(n, Node) and not isinstance(n, Relation) and n.isType() and n.model is m
            and not n.isSystemObject()]
  return sorted(ret, key=lambda n: str(n.name).lower())

def relationNamed(model:Model, name:str) -> Relation|None:
  '''
  :param model: A model.
  :param name: A relation type's name.
  :returns: The first of *relationTypes()* with that name, if any.
  '''
  return next((r for r in relationTypes(model) if r.name == name), None)

def nodeNamed(model:Model, name:str) -> Node|None:
  '''
  :param model: A model.
  :param name: A node type's name.
  :returns: The first of *nodeTypes()* with that name, if any.
  '''
  return next((n for n in nodeTypes(model) if n.name == name), None)

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
    "Its parameters' values (see *PARAMETERS*): relations as *Relation* objects."
    for p in self.PARAMETERS:
      v = kwargs.get(p.name, p.default)
      if p.kind == "relations" and isinstance(v, str):
        from sn.view.graphics.relationTable import RelationTable
        v = RelationTable.decode(v)
      elif p.kind == "relation" and isinstance(v, str):
        name = v
        v = relationNamed(view.model, name)
        if v is None:
          logger.warning(f'{type(self).__name__}: there\'s no relation type "{name}" in {view.model.name} '
                         f'or its super-models: its {p.name} is the default.')
      self.params[p.name] = v

  # ---- parameters -------------------------------------------------------------

  @classmethod
  def parametersFor(cls, category:str, current:dict[str, Any]|None=None) -> tuple[list[LayoutParameter], dict[str, Any]]:
    '''
    :param category: How it'll be used: *STATIC* or *DYNAMIC*.
    :param current: The values to start with, if not the defaults.
    :returns: The parameters to ask for, for *category* (see
      *LayoutParameter.categories*), and all of them with the values to start
      with: what its dialog (see *askParameters()*), or its page in the layout
      panel (see *layoutPanel*), shows.
    '''
    asked = [p for p in cls.PARAMETERS if category in p.categories]
    return asked, {p.name: (current or {}).get(p.name, p.default) for p in cls.PARAMETERS}

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
    :param current: The values to start with, if not the defaults.
    :param parent: The window the dialog's over.
    :returns: The keyword arguments for its constructor, or None if the user cancelled.
    '''
    asked, values = cls.parametersFor(category, current)
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
    :param values: All the parameters' values, now.
    :returns: The values to show.
    '''
    return values

  def parameters(self) -> dict[str, Any]:
    '''
    :returns: Its parameters' values: as keyword arguments for its constructor.
    '''
    return dict(self.params)

  # ---- saving it with the view ---------------------------------------------------

  def state(self) -> str:
    '''
    :returns: What's saved with the view about it, as its dynamic layout (see
      *fromState()*): its name, parameters, and anything else it keeps (see
      *extraState()*): eg: "name=tree;relations=includes:shapes:source;direction=right;pins=12,40".
    '''
    return self.encodeParameters(self.params, self.extraState())

  @classmethod
  def encodeParameters(cls, params:dict[str, Any], extra:dict[str, str]={}) -> str:
    '''
    :param params: Values of its parameters (see *PARAMETERS*): a relation as a
      *Relation* or its name.
    :param extra: Anything else to say (see *extraState()*).
    :returns: Them as text: its name, then each parameter's value (see
      *decodeParameters()*): eg: "name=tree;relations=includes:shapes:source;direction=right".
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
    :returns: The kind of layout it's of, its parameters' values (keyword
      arguments for its constructor: a relation by its name), and everything
      said (eg: for *restoreExtraState()*) -- or None if there's no such layout.
    '''
    state = dict(kv.split("=", 1) for kv in text.split(";") if "=" in kv)
    cls = LAYOUTS.get(state.get("name", ""))
    if cls is None:
      return None
    state = cls.upgradeParameters(state)
    kwargs:dict[str, Any] = {}
    for p in cls.PARAMETERS:
      if p.name in state:
        v = state[p.name]
        try:
          kwargs[p.name] = int(v) if p.kind == "int" else (v == "1") if p.kind == "bool" else v
        except ValueError: # (not a number: the default, then)
          pass
    return cls, kwargs, state

  @classmethod
  def upgradeParameters(cls, state:dict[str, str]) -> dict[str, str]:
    '''
    :param state: What *decodeParameters()* read: eg: saved by an older
      version, whose parameters were different.
    :returns: It, with any old parameters converted to the ones there are
      now. As it is, by default.
    '''
    return state

  def extraState(self) -> dict[str, str]:
    '''
    :returns: Anything else it keeps that's saved with the view (see *state()*):
      none, by default. (Values mustn't contain ";" or "=".)
    '''
    return {}

  def restoreExtraState(self, state:dict[str, str]) -> None:
    '''
    Put back what *extraState()* saved.

    :param state: What was saved (and the parameters).
    '''
    pass

  @staticmethod
  def fromState(view, text:str) -> "LayoutHeuristic|None":
    '''
    :param view: A view, being read.
    :type view: SNGView
    :param text: What *state()* saved.
    :returns: The layout it describes -- or None if there's no such layout.
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
    '''
    return {}

  def arrange(self, animate:bool=True) -> "LayoutMoves|None":
    '''
    Arrange the view (see *targets()*), as one undoable command.

    :param animate: Whether to move things smoothly (see *tween()*), rather than at once.
    :returns: The command, or None if nothing moved.
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
    '''
    pass

  def placeAll(self) -> None:
    "As *arrange()*."
    self.arrange()

  # ---- dynamic --------------------------------------------------------------------

  def _setDirection(self, node:VObject, referenceNode:Optional[VObject], loc:Optional[Point]=None):
    '''
    Which way from *referenceNode* to put *node*: nearest *loc*, if there is one; else sideways, if there's no
    *referenceNode*; else below it if *node* is its subtype, or above.
    '''
    if loc is not None:
      return Direction.NEAREST
    if referenceNode is None: # and loc is None
      return Direction.LATERAL
    else: #referenceNode is not None and loc is None
      if node.modelObject.isa(referenceNode.modelObject): # type: ignore[union-attr, arg-type]
        return Direction.SUB
      elif referenceNode:
        return Direction.SUPER
    
  def findOverlapping(self, rect:Sequence[float], exclude:Collection[int]=[], shapes:Collection[int]|None=None) -> list[int]:
    '''
    :param shapes: The view's 'vis/shape'-tagged canvas item ids, if the caller
      has them (eg: a set, from *find_withtag()*): as one trying many places
      for one object would -- asking Tk for each overlapping item's tags,
      otherwise, takes most of the time. (*FindFree* doesn't ask Tk at all:
      see *FindFree.obstacles()*.)
    :return: The (possible zero-length) list of 'vis/shape'-tagged tk.Canvas object ids
        that overlap with bounding box of *node*.
    '''
    if shapes is not None:
      return [i for i in self.view.canvas.find_overlapping(*rect) if i in shapes and i not in exclude]
    overlapping = self.view.intersectTag(self.view.canvas.find_overlapping(*rect), 'vis/shape', list(exclude))
    return overlapping
    
  def __call__(self, node:Optional[VObject]=None, **kwargs):
    '''
    Place *node* (see *placeNode()*) -- or, if it's None, everything (see *placeAll()*).

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

    :param referenceNode: What it's to go near, if anything.
    :param direction: Which way from *referenceNode*.
    :param loc: Where to start looking, if not where it is.
    :param kwargs: Eg: "aggressive", "within" (see *FindFree.placeNode()*).
    :returns: Where it's put (its top left).
    '''
    bb = node.boundingBox()
    return bb[0], bb[1]

  BATCH_GAP = (20.0, 30.0)
  "The room *placeBatch()* leaves between the nodes it puts in rows (view units): across, and between the rows."
  BATCH_ASPECT = 2.0
  "Roughly how many times as wide as it's tall *placeBatch()* makes its block of rows."

  def placeBatch(self, nodes:Sequence[VObject], near:VObject) -> None:
    '''
    As the view's dynamic layout: put *nodes* -- many, just made together
    (eg: by expanding *near*: see *VObject.expand()*), and not placed yet --
    all at once. Placed one by one (see *placeNode()*), each would be tried
    against everything placed before it, which for thousands takes minutes.
    By default, in rows, in their order: a block about *BATCH_ASPECT* times
    as wide as it's tall, centred below *near*, as close below it as clears
    what's there (but not *nodes*, nor their relations' labels: they follow
    their ends).

    :param nodes: The nodes.
    :param near: What they're put below.
    '''
    if not nodes:
      return
    gx, gy = self.BATCH_GAP
    sizes = [layoutSize(vo) for vo in nodes]
    width = max(max(w for w, _ in sizes), math.sqrt(sum((w + gx) * (h + gy) for w, h in sizes) * self.BATCH_ASPECT))
    places:list[tuple[float, float]] = []
    x = y = rowHeight = 0.0
    for w, h in sizes:
      if x > 0 and x + w > width:
        x, y, rowHeight = 0.0, y + rowHeight + gy, 0.0
      places.append((x, y))
      x += w + gx
      rowHeight = max(rowHeight, h)
    blockW = max(px + w for (px, _), (w, _) in zip(places, sizes))
    blockH = y + rowHeight
    bb = near.boundingBox()
    x0 = (bb[0] + bb[2]) / 2 - blockW / 2
    labels = [r for vo in nodes for r in vo.relations]
    y0 = clearBelow(shownBoxes(self.view, [*nodes, *labels]), x0, x0 + blockW, bb[3] + gy, blockH, max(gx, gy))
    for vo, (px, py) in zip(nodes, places):
      vo.moveTo(int(x0 + px), int(y0 + py), adjustPos=False)

  def placeLabels(self, labels:Sequence[VObject]) -> None:
    '''
    As the view's dynamic layout: put the labels of relations made together
    (eg: by an expansion: see *VObject.expand()*) -- midway between their
    ends, as they're made -- somewhere suitable, all at once. By default,
    one by one, as each would be (see *placeNode()*).

    :param labels: The relations.
    '''
    for r in labels:
      self(r)

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
    view (see *viewCommands.ViewDoList*), to say what else to move. The command
    returned is done, and undone with *command*, as one.

    :param command: The command just done.
    :returns: What to move (not done yet), or None for nothing (the default).
    '''
    return None

LayoutHieristic = LayoutHeuristic

def fitToText(vo:VObject) -> VObject:
  '''
  :param vo: A node or relation (its label) in a view: eg: just made.
  :returns: It, sized to its text now -- as it would be when it's next drawn
    (see *decorators.WrappingText.fitOwner()*) -- so a layout can place it by its size.
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
  :returns: Its (width, height) as it'll be when it's moved: fitted to its
    text (see *fitToText()*), and at least the minimums a box is held to when
    it's set (see *VObject.boundingBox()*: "vis/minSize", and *VObject.minHeight()*)
    -- which a box first fitted to a little text may be smaller than.
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

  @override
  def placeBatch(self, nodes:Sequence[VObject], near:VObject) -> None:
    pass # (they stay where they're made, too)

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

TWEEN_MAX_RELATIONS = 400
'''The most relations attached to the objects moved smoothly: with more, they're
moved at once. Each step of a smooth move redraws every one of them (eg: a
module with dozens of imports): a step could take seconds, and the whole
move look like nothing's happening.'''

TWEEN_SLOW_STEP = 0.08
"Seconds: if a step of a smooth move takes longer, the rest is done at once."

def _moveAll(view, moves:list[tuple[VObject, float, float]]) -> None:
  '''
  Move each object to (x, y) (its top left) at once -- without redrawing its
  relations as it goes (see *VObject.moveTo()*'s *fast*) -- and then redraw
  each relation of what moved, once (see *VRelation.reposition()*: a floating
  label goes between its ends, wherever they've gone). Moving them one by
  one redraws every relation of each as it moves -- one between two moved
  objects twice -- which is slow with a lot of them (eg: a module's dozens
  of imports).

  :param view:
  :type view: SNGView
  :param moves: (object, x, y).
  '''
  touched:dict[int, VRelation] = {}
  for vo, x, y in moves:
    if not vo._isConnected():
      continue
    vo.moveTo(x, y, adjustPos=False, carry=False, fast=True)
    if isinstance(vo, VRelation):
      touched[id(vo)] = vo
    for r in (vo.relations or ()):
      if isinstance(r, VRelation):
        touched[id(r)] = r
  view.freshPaint()
  for r in touched.values():
    if r._isConnected():
      r.reposition(adjustPos=False)

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
    began = time.perf_counter()
    t = self.step / TWEEN_STEPS
    t = t * t * (3 - 2 * t) # (eased: slow, fast, slow)
    for vo, (x0, y0), (x1, y1) in self.moves:
      if vo._isConnected():
        vo.moveTo(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, adjustPos=False, carry=False)
    if time.perf_counter() - began > TWEEN_SLOW_STEP: # (too slow to look smooth: the rest at once)
      self.finish()
      return
    self.job = self.view.canvas.after(TWEEN_INTERVAL, self.next)

  def finish(self) -> None:
    '''Put everything where it's going, now.'''
    try:
      self.view.canvas.after_cancel(self.job)
    except Exception:
      pass
    if self.view.__dict__.get("_tween") is self:
      self.view._tween = None
    _moveAll(self.view, [(vo, x1, y1) for vo, _, (x1, y1) in self.moves])
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
  else is done to the view. At once if there are more than *TWEEN_MAX*, or
  they have more than *TWEEN_MAX_RELATIONS* relations between them (each step
  redraws them all: it'd be slow), or there's no window; and the rest at once
  if a step takes longer than *TWEEN_SLOW_STEP*.

  :param view:
  :type view: SNGView
  :param moves: (object, from, to): top left corners.
  '''
  finishTween(view)
  if not moves:
    return
  if not getattr(view, "canvas", None) or len(moves) > TWEEN_MAX \
     or sum(sum(1 for _ in (getattr(vo, "relations", None) or ())) for vo, _, _ in moves) > TWEEN_MAX_RELATIONS:
    _moveAll(view, [(vo, x1, y1) for vo, _, (x1, y1) in moves])
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
  "So the view's dynamic layout doesn't adjust after it (see *viewCommands.ViewDoList*)."

  def __init__(self, view, name:str, targets:dict[VObject, tuple[float, float]], animate:bool=True):
    '''
    :param view:
    :type view: SNGView
    :param name: What the undo menu calls it.
    :param targets: Where things go (their top left corners): those already there are left out. A
      context window they'd land on is moved out of their way, with its contents (see
      *windowsOutOfTheWay()*).
    :param animate: Whether to move them smoothly when it's first done.
    '''
    super().__init__(name)
    self.view = view
    self.animate = animate
    self.first = True
    self.moves:list[tuple[VObject, tuple[float, float], tuple[float, float], bool|None]] = []
    "(object, from, to, whether it floated: for a relation's label)"
    if targets and getattr(view, "contextWindows", None) is not None:
      targets = {**targets, **windowsOutOfTheWay(view, targets)}
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
      _moveAll(self.view, [(vo, x, y) for vo, _, (x, y), _ in self.moves])
      _settled(self.view)
    self.first = False

  @override
  def undo(self) -> None:
    super().undo()
    finishTween(self.view)
    _moveAll(self.view, [(vo, x, y) for vo, (x, y), _, _ in reversed(self.moves)])
    for vo, _, _, floated in self.moves:
      if floated is not None and vo._isConnected():
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

class _BoxIndex:
  '''
  Boxes, bucketed by where they are: for finding those near a place quickly.
  '''
  CELL = 100.0

  def __init__(self, boxes:Iterable[Sequence[float]]=[]):
    self.cells:dict[tuple[int, int], list[Sequence[float]]] = {}
    for b in boxes:
      self.add(b)

  def _cells(self, b:Sequence[float]):
    c = self.CELL
    for i in range(int(b[0] // c), int(b[2] // c) + 1):
      for j in range(int(b[1] // c), int(b[3] // c) + 1):
        yield (i, j)

  def add(self, b:Sequence[float]) -> None:
    for k in self._cells(b):
      self.cells.setdefault(k, []).append(b)

  def hits(self, b:Sequence[float], gap:float) -> bool:
    ''':returns: Whether *b* is on (or within *gap* of) one of the boxes.'''
    g = [b[0] - gap, b[1] - gap, b[2] + gap, b[3] + gap]
    return any(o[0] < g[2] and g[0] < o[2] and o[1] < g[3] and g[1] < o[3]
               for k in self._cells(g) for o in self.cells.get(k, ()))

def shownBoxes(view, exclude:Iterable[VObject]=(), around:Sequence[float]|None=None) -> list[Sequence[float]]:
  '''
  :param view: A view.
  :type view: SNGView
  :param exclude: What to leave out: eg: what's being placed.
  :param around: [x1, y1, x2, y2]: where to look, if not everywhere: those not on it are left out.
  :returns: What things placed in *view* keep clear of: the bounding boxes
    (view coordinates) of its objects whose shapes are shown and tagged
    'vis/shape' (not a context window's frame: see *decorators.ContextFrame*).
  '''
  shapes = set(view.canvas.find_withtag('vis/shape'))
  skip = {id(vo) for vo in exclude}
  x1, y1, x2, y2 = around if around is not None else (-math.inf, -math.inf, math.inf, math.inf)
  return [b for vo in view.values()
          if isinstance(vo, VObject) and (b := vo.boundingBox())[0] < x2 and x1 < b[2] and b[1] < y2 and y1 < b[3]
          and id(vo) not in skip and not vo.isHidden() and vo._shape is not None and vo._shape.id in shapes]

def windowsOutOfTheWay(view, targets:dict[VObject, tuple[float, float]], gap:float=20.0) -> dict[VObject, tuple[float, float]]:
  '''
  Where to put the context windows that what a layout arranges would land
  on: each is moved whole -- with what it carries (see
  *VObject.carriedContents()*) -- the least it takes to be *gap* clear of
  what's arranged, and off everything else (other windows too), so nothing
  ends up in a window it doesn't belong in, and a window's contents stay in
  it. (A layout moves things without carrying: see *LayoutMoves*.) Windows
  inside another window, and what *targets* moves itself, are left be.

  :param view: A view.
  :type view: SNGView
  :param targets: Where the layout puts things (their top left).
  :param gap: The clearance.
  :returns: Where the windows moved, and what they carry, go (their top left).
  '''
  windows = [w for w in view.contextWindows() if not w.isHidden() and w not in targets]
  if not windows or not targets:
    return {}
  homes = view.containmentHomes()
  arranged:list[list[float]] = []
  for vo, (x, y) in targets.items():
    if vo in homes or (not isinstance(vo, VRelation) and vo.isContextWindow()): # (what moves with a window)
      continue
    bb = vo.boundingBox()
    arranged.append([x, y, x + bb[2] - bb[0], y + bb[3] - bb[1]])
  if not arranged:
    return {}
  hit = lambda b, g: any(a[0] - g < b[2] and b[0] < a[2] + g and a[1] - g < b[3] and b[1] < a[3] + g for a in arranged)
  moving = sorted((w for w in windows if homes.get(w) is None and hit(w.boundingBox(), gap)), # (not one inside another: it goes with that one)
                  key=lambda w: (w.boundingBox()[1], w.boundingBox()[0]))
  if not moving:
    return {}
  carried = {w: [vo for vo in w.carriedContents() if vo not in targets] for w in moving}
  skip = {id(vo) for w in moving for vo in [w, *carried[w]]} | {id(vo) for vo in targets}
  floats = lambda vo: isinstance(vo, VRelation) and vo.floating()
  others = [list(vo.boundingBox()) for vo in view.values()
            if isinstance(vo, VObject) and id(vo) not in skip and vo._isConnected() and not vo.isHidden() and not floats(vo)]
  ret:dict[VObject, tuple[float, float]] = {}
  for w in moving:
    box = list(w.boundingBox())
    near = [box[0] - 2000, box[1] - 2000, box[2] + 2000, box[3] + 2000]
    keepOut = [a for a in arranged if a[0] < near[2] and near[0] < a[2] and a[1] < near[3] and near[1] < a[3]]
    obstacles = [o for o in others if o[0] < near[2] and near[0] < o[2] and o[1] < near[3] and near[1] < o[3]]
    d = clearOf(box, keepOut, obstacles, gap=gap)
    if d is None or d == (0.0, 0.0):
      continue
    dx, dy = round(d[0]), round(d[1])
    for vo in [w, *carried[w]]:
      bb = vo.boundingBox()
      ret[vo] = (bb[0] + dx, bb[1] + dy)
    others.append([box[0] + dx, box[1] + dy, box[2] + dx, box[3] + dy]) # (the next keeps off it)
  return ret

def clearBelow(boxes:Iterable[Sequence[float]], x1:float, x2:float, y:float, height:float, gap:float) -> float:
  '''
  :param boxes: [x1, y1, x2, y2] each: what's in the way.
  :returns: The top of the highest band from *x1* to *x2*, *height* high,
    starting at *y* or below, that's at least *gap* from each of *boxes*.
  '''
  for b in sorted((b for b in boxes if b[0] - gap < x2 and x1 < b[2] + gap), key=lambda b: b[1]):
    if b[1] - gap >= y + height: # (this one's below the band -- and so are the rest)
      break
    if b[3] + gap > y: # (in the band: below it, then)
      y = b[3] + gap
  return y

def freeRingSpot(rect:Sequence[int], index:_BoxIndex, gap:float, *, quanta:int=10,
                 limit:Sequence[int]=(-UNBOUNDED, -UNBOUNDED, UNBOUNDED, UNBOUNDED),
                 maxRings:int=100) -> tuple[int, int]|None:
  '''
  Where to put *rect* (its top left) so it isn't on, or within *gap* of, any
  of *index*'s boxes: the first such place met looking out from where it is,
  in square rings *quanta* apart -- each ring's rows from the top, a row's
  places from the left, all of its top and bottom rows' places but just the
  ends of the others' -- with its top left within *limit*. Each place is
  tried against just the boxes near it (see *_BoxIndex*), so even a crowded
  view's thousands of places are tried quickly.

  :param rect: [x1, y1, x2, y2], ints.
  :param limit: [x1, y1, x2, y2], ints: where its top left may go.
  :returns: Its new top left -- or None if there's no such place within *maxRings* rings.
  '''
  w, h = rect[2] - rect[0], rect[3] - rect[1]
  assert w > 0
  assert h > 0
  for dist in range(0, maxRings): # the width/height of the rectangular scan
    yStart = max(limit[1], rect[1] - dist * quanta)
    yEnd   = min(limit[3], rect[1] + dist * quanta)
    for y in range(yStart, yEnd + 1, quanta):
      xStart = max(limit[0], rect[0] - dist * quanta)
      xEnd   = min(limit[2], rect[0] + dist * quanta)
      # the ring's perimeter: all of its top and bottom rows, just the ends of the others
      xIncr  = quanta if y == yStart or y == yEnd else max(1, xEnd - xStart)
      for x in range(xStart, xEnd + 1, xIncr):
        if not index.hits([x, y, x + w, y + h], gap):
          return x, y
  return None # (nowhere free within maxRings)

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
                **kwargs) -> Point|tuple[float, float]:
    '''
    :param within: Where it may be put (x1, y1, x2, y2: view coords), if not anywhere: eg: the visible part of the view.
    '''
    from sn.view.graphics.vrelations import VRelation
    expandFactor = self.expandFactor_relations \
          if node.modelObject is not None and node.modelObject.isIndividual() and isinstance(node, VRelation) \
          else self.expandFactor_nodes
    
    if direction == Direction.UNSPECIFIED:
      if loc is not None:
        direction = Direction.NEAREST
      elif referenceNode is not None:
        if node.modelObject.isa(referenceNode.modelObject): # type: ignore[union-attr, arg-type]
          direction = Direction.SUB
        elif referenceNode.modelObject.isa(node.modelObject): # type: ignore[union-attr, arg-type]
          direction = Direction.SUPER
        else:
          direction = Direction.LATERAL
      else:
        direction = Direction.LATERAL
        
    assert direction != Direction.UNSPECIFIED   
        
    maxRings = 100 # (how far out to look for a free spot: see LABEL_PLACEMENT_PREF)
    if isinstance(node, VRelation):
      level = labelPlacementLevel()
      if level == 0: # (labels stay where they're made: midway between their ends)
        bb = node.boundingBox()
        return bb[0], bb[1]
      maxRings = level * level

    rect = node.boundingBox()
    if loc is not None:
      rect = [loc.x, loc.y, loc.x+rect[2]-rect[0], loc.y+rect[3]-rect[1]]

    leftLimit:float; topLimit:float; rightLimit:float; bottomLimit:float
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
      
    finalLimit = [int(i) for i in self._inHome(node, rect, [leftLimit, topLimit, rightLimit, bottomLimit], expandFactor)]
    reach = maxRings * self.quanta + expandFactor # (as far as the search goes)
    around = [rect[0] - reach, rect[1] - reach, rect[2] + reach, rect[3] + reach]
    # (not on itself, nor on its own relations' labels)
    pt = freeRingSpot([int(i) for i in rect], self.obstacles(around, [node, *node.relations]), expandFactor,
                      quanta=self.quanta, limit=finalLimit, maxRings=maxRings)
    if pt is None: # (nowhere free close enough: it stays where it is)
      bb = node.boundingBox()
      return bb[0], bb[1]
    
    # if pt[0]!=rect[0] or pt[1]!=rect[1]:
    #   logger.debug(f'Node "{node.modelObject.name}:{node.modelObject._id}" moving in direction {direction}, limit={finalLimit} to {pt}, ref={referenceNode}.')
    
    node.moveTo(*pt, adjustPos=False)

    return pt

  def _inHome(self, node:VObject, rect:Sequence[float], limit:Sequence[float], expandFactor:float,
              homes:dict|None=None) -> Sequence[float]:
    '''
    What a context contains (a relation's label too), dropped in its pane,
    stays in it (see *SNGView.containmentHomes()*).

    :param rect: Its box, where it's to be placed from.
    :param limit: [x1, y1, x2, y2]: where its top left may go.
    :param homes: *SNGView.containmentHomes()* of it, if the caller has it (eg: for many at once).
    :returns: *limit*, kept to the pane it's in, if it's in its home pane (and fits in it).
    '''
    if node.modelObject is None:
      return limit
    if homes is None:
      homes = self.view.containmentHomes([node])
    win, pane = homes.get(node, (None, ""))
    cx, cy = node.centerPt()
    px1, py1, px2, py2 = self.view.homeRect(win, pane) if win is not None else (0, 0, -1, -1)
    if px1 <= cx <= px2 and py1 <= cy <= py2:
      w, h = rect[2] - rect[0], rect[3] - rect[1]
      inside = [max(limit[0], px1 + expandFactor), max(limit[1], py1 + expandFactor),
                min(limit[2], px2 - expandFactor - w), min(limit[3], py2 - expandFactor - h)]
      if inside[0] <= inside[2] and inside[1] <= inside[3]:
        return inside
    return limit

  def obstacles(self, around:Sequence[float], exclude:Iterable[VObject]=()) -> _BoxIndex:
    '''
    What's placed keeps clear of (see *shownBoxes()*): by their bounding boxes
    -- in view coordinates, as what's placed is (the canvas's are zoomed) --
    and not by asking Tk (*findOverlapping()*): for each place tried, Tk tests
    every item on the canvas, lines' exact curves too, so trying the thousands
    of places a crowded view needs took many seconds for each thing placed.

    :param around: [x1, y1, x2, y2]: where to look: those not on it are left out.
    :param exclude: What not to keep clear of: eg: what's being placed, and its relations' labels.
    '''
    return _BoxIndex(shownBoxes(self.view, exclude, around))

  @override
  def placeLabels(self, labels:Sequence[VObject]) -> None:
    '''
    Each in the nearest free place, as *placeNode()* would put it, but
    against what's there gathered once for them all (each label added as
    it's placed), rather than each against everything again: which for
    thousands takes minutes.
    '''
    from sn.view.graphics.vrelations import VRelation
    level = labelPlacementLevel()
    if level == 0 or not labels:
      return
    maxRings = level * level
    factor = lambda r: self.expandFactor_relations \
      if r.modelObject is not None and r.modelObject.isIndividual() and isinstance(r, VRelation) else self.expandFactor_nodes
    boxes = [r.boundingBox() for r in labels]
    reach = maxRings * self.quanta + max(self.expandFactor_relations, self.expandFactor_nodes)
    around = [min(b[0] for b in boxes) - reach, min(b[1] for b in boxes) - reach,
              max(b[2] for b in boxes) + reach, max(b[3] for b in boxes) + reach]
    index = self.obstacles(around, labels)
    homes = self.view.containmentHomes(list(labels))
    for r, rect in zip(labels, boxes):
      if rect[2] <= rect[0] or rect[3] <= rect[1]: # (no label to place)
        continue
      expandFactor = factor(r)
      limit = [int(i) for i in self._inHome(r, rect, self.limit, expandFactor, homes)]
      pt = freeRingSpot([int(i) for i in rect], index, expandFactor, quanta=self.quanta, limit=limit, maxRings=maxRings)
      if pt is not None:
        r.moveTo(*pt, adjustPos=False)
      index.add(r.boundingBox())

  @override
  def placeAll(self):
    pass # (not a static layout)


def intoRect(box:Sequence[float], rect:Sequence[float], margin:float=0.0, topMargin:float|None=None) -> tuple[float, float]:
  '''
  How far to move *box* to put it inside *rect*, *margin* in from its edges
  (*topMargin* from its top, if given) -- the least move that does it; centred
  in an axis it's too big for.

  :param box: [x1, y1, x2, y2].
  :param rect: [x1, y1, x2, y2].
  :param margin: The space to leave inside *rect*'s edges.
  :param topMargin: The space to leave at its top (default: *margin*).
  :returns: (dx, dy).
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
  The median of *values* (0 if there are none).
  '''
  if not values:
    return 0.0
  s = sorted(values)
  n = len(s)
  return s[n//2] if n % 2 else (s[n//2 - 1] + s[n//2]) / 2

def gatherAxisShifts(intervals:Sequence[tuple[float, float]], *,
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
  :param gapFactor: How many times the typical spacing a gap must exceed to
    count as stranding what lies beyond it.
  :param minGap: No gap smaller than this counts as stranding, however
    tightly packed the rest of the drawing is -- so a normal (if loose)
    layout is left alone.
  :returns: The shift for each interval, in the same order.
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
  :returns: The (dx, dy) to move each box by, in the same order.
  '''
  dxs = gatherAxisShifts([(b[0], b[2]) for b in boxes], gapFactor=gapFactor, minGap=minGap)
  dys = gatherAxisShifts([(b[1], b[3]) for b in boxes], gapFactor=gapFactor, minGap=minGap)
  return list(zip(dxs, dys))

# ---- Gathering into a context window -----------------------------------------

def freeSpotIn(box:Sequence[float], rect:Sequence[float], obstacles:Iterable[Sequence[float]], *,
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
  :param rect: [x1, y1, x2, y2].
  :param obstacles: Boxes to keep clear of.
  :returns: (dx, dy) -- or None if there's no room.
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
  if not rows:
    ex, ey = intoRect(box, rect, margin, topMargin)
    tx, ty = box[0] + ex, box[1] + ey # (where it would go, ignoring the obstacles)
    if clear(tx, ty):
      return ex, ey
  # The grid spots (lo_x + i * step, lo_y + j * step), row by row: those an
  # obstacle blocks (the same test as clear()'s) are marked, an obstacle's
  # a block of them -- not every spot tried against every obstacle.
  nx, ny = int((hi_x - lo_x) // step), int((hi_y - lo_y) // step)
  W = nx + 1
  blocked = bytearray(W * (ny + 1))
  for o in obs:
    xr = _gridSpan(lo_x, step, nx, lambda x: x + w + gx > o[0], lambda x: o[2] + gx > x)
    yr = _gridSpan(lo_y, step, ny, lambda y: y + h + gy > o[1], lambda y: o[3] + gy > y)
    if xr and yr:
      ones = b"\1" * len(xr)
      for j in yr:
        blocked[j * W + xr.start:j * W + xr.stop] = ones
  first = blocked.find(0)
  if first < 0:
    return None
  if rows: # (the first free one, reading row by row)
    j, i = divmod(first, W)
    return lo_x + i * step - box[0], lo_y + j * step - box[1]
  # The nearest free one to (tx, ty) -- ties to the lowest (i, j), as a
  # stable sort of all of them, column by column, would have it -- searched
  # in square rings out from the spot nearest it, till no spot further out
  # can be as near as the best found.
  ci, cj = min(max(round((tx - lo_x) / step), 0), nx), min(max(round((ty - lo_y) / step), 0), ny)
  off = max(abs(lo_x + ci * step - tx), abs(lo_y + cj * step - ty))
  best:tuple[float, int, int]|None = None
  for r in range(max(ci, nx - ci, cj, ny - cj) + 1):
    if best is not None:
      near = r * step - off # (no spot in this ring, or out from it, is nearer)
      if near > 0 and near * near > best[0] * (1 + 1e-9) + 1e-9:
        break
    if r == 0:
      ring:Iterable[tuple[int, int]] = ((ci, cj),)
    else:
      i0, i1, j0, j1 = max(ci - r, 0), min(ci + r, nx), max(cj - r + 1, 0), min(cj + r - 1, ny)
      ring = itertools.chain(
        ((i, j) for j in (cj - r, cj + r) if 0 <= j <= ny for i in range(i0, i1 + 1)),
        ((i, j) for i in (ci - r, ci + r) if 0 <= i <= nx for j in range(j0, j1 + 1)))
    for i, j in ring:
      if not blocked[j * W + i]:
        x, y = lo_x + i * step, lo_y + j * step
        spot = ((x - tx) ** 2 + (y - ty) ** 2, i, j)
        if best is None or spot < best:
          best = spot
  assert best is not None
  return lo_x + best[1] * step - box[0], lo_y + best[2] * step - box[1]

def _gridSpan(lo:float, step:float, n:int, after:Callable[[float], bool], before:Callable[[float], bool]) -> range:
  '''
  :param lo: The first grid point.
  :param step: The grid's spacing.
  :param n: The last grid point's index.
  :param after: Of a point: false up to some point, true from there on.
  :param before: Of a point: true up to some point, false from there on.
  :returns: The indices *i* (0 to *n*) of the grid points *lo* + *i* * *step*
    that are both *after* and *before* (found by bisection, testing the
    points just as they're written).
  '''
  a, b = 0, n + 1
  while a < b: # (the first that's after)
    m = (a + b) // 2
    if after(lo + m * step):
      b = m
    else:
      a = m + 1
  start, a, b = a, a, n + 1
  while a < b: # (the first that isn't before)
    m = (a + b) // 2
    if before(lo + m * step):
      a = m + 1
    else:
      b = m
  return range(start, max(start, a))

# ---- Keeping out of context windows ------------------------------------------

def clearOf(box:Sequence[float], keepOut:Sequence[Sequence[float]], obstacles:Sequence[Sequence[float]]=[], *,
            within:Sequence[float]|None=None, gap:float=10.0) -> tuple[float, float]|None:
  '''
  How far to move *box* -- as little as can be -- so it's *gap* clear of every
  rect in *keepOut* (eg: windows it doesn't belong in), clear of *obstacles*
  too (by *gap* / 2), and inside *within* (if given: eg: its own pane). The
  candidates are the positions that just clear something (or line up with
  *within*'s edges), alone and in pairs (one across, one down), so the result
  is the nearest one there is, but not necessarily the very nearest point.

  :param box: [x1, y1, x2, y2].
  :param keepOut: Rects to stay out of.
  :param obstacles: Rects not to land on (if that can be helped: if there's
    no such place, they're ignored).
  :param within: A rect to stay in.
  :param gap: The clearance.
  :returns: (dx, dy), (0, 0) if it's fine where it is -- or None if there's no place.
  '''
  w, h = box[2] - box[0], box[3] - box[1]
  def hits(x:float, y:float, rects:Sequence[Sequence[float]], g:float) -> bool:
    return any(x < r[2] + g and r[0] - g < x + w and y < r[3] + g and r[1] - g < y + h for r in rects)
  def inside(x:float, y:float) -> bool:
    return within is None or (within[0] <= x and within[1] <= y and x + w <= within[2] and y + h <= within[3])
  def search(rects:Sequence[Sequence[float]]) -> tuple[float, float]|None:
    xs, ys = {box[0]}, {box[1]}
    for r, g in [*((r, gap) for r in keepOut), *((r, gap / 2) for r in rects)]:
      xs |= {r[0] - g - w, r[2] + g}
      ys |= {r[1] - g - h, r[3] + g}
    if within is not None:
      xs |= {within[0], within[2] - w}
      ys |= {within[1], within[3] - h}
    # The pairs (x, y) nearest first -- ties to the first in (xs, ys)'s
    # order, as a scan of every pair keeping only nearer ones would have it
    # -- till the first that's clear: a heap of one run of pairs for each x,
    # its ys nearest first. Each x's rects that it could hit (across) are
    # picked out once.
    xl, yl = list(xs), list(ys)
    ysNear = sorted(((y - box[1]) ** 2, b, y) for b, y in enumerate(yl))
    heap = [((x - box[0]) ** 2 + ysNear[0][0], a, ysNear[0][1], 0) for a, x in enumerate(xl)]
    heapq.heapify(heap)
    across:dict[int, list[tuple[Sequence[float], float]]] = {}
    def clear(a:int, b:int) -> bool:
      x, y = xl[a], yl[b]
      if not inside(x, y):
        return False
      if a not in across:
        across[a] = [(r, g) for r, g in [*((r, gap) for r in keepOut), *((r, gap / 2) for r in rects)]
                     if x < r[2] + g and r[0] - g < x + w]
      return not any(y < r[3] + g and r[1] - g < y + h for r, g in across[a])
    found:tuple[float, int, int]|None = None
    while heap:
      d, a, b, k = heapq.heappop(heap)
      if found is not None and d != found[0]:
        break # (past the nearest: the first of those as near that's clear is found)
      if k + 1 < len(ysNear):
        heapq.heappush(heap, ((xl[a] - box[0]) ** 2 + ysNear[k + 1][0], a, ysNear[k + 1][1], k + 1))
      if (found is None or (a, b) < found[1:]) and clear(a, b):
        found = (d, a, b)
    return None if found is None else (xl[found[1]] - box[0], yl[found[2]] - box[1])
  if inside(box[0], box[1]) and not hits(box[0], box[1], keepOut, gap):
    return 0.0, 0.0 # (nothing to do: it isn't in the way -- whatever it may overlap otherwise)
  return search(obstacles) or (search([]) if obstacles else None)
