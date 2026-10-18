'''
The commands a view (*sn.view.graphics.sngView.SNGView*) uses besides its
context's (see *sn.view.graphics.sngContext.SNGContext*): its undo list
(*ViewDoList*), which adjusts the view after each command -- bumping what's
been left in a context window it doesn't belong in, keeping it arranged --
and the commands that does it with; and *keptWith()*, what "erase everything
else" keeps.

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
import sn
from typing import Any, Callable, Iterable, override, TYPE_CHECKING
from util.command import Command, DoList
from util.commandParser import CompositeCommand
from sn.model.model import Model, Relation, GraphObject
from sn.controller.modelInterface import changesModel
from sn.view.graphics.vobjects import VObject
from sn.view.graphics.vrelations import VRelation
from sn.view.graphics.layout import LayoutMoves, finishTween
if TYPE_CHECKING:
  from sn.view.graphics.sngView import SNGView # (sngView imports this module)

logger:sn.SNLogger = sn.getLogger(__name__)

class _BumpIntruders(Command):
  '''
  Push what's in a context window it doesn't belong in out of it (see
  *SNGView.bumpIntruders()*). What to move is worked out when it's first done
  -- after the commands before it, so a drop into a pane has already made the
  object contained -- and replayed on a redo.
  '''
  def __init__(self, view:SNGView):
    '''
    :param view:
    :type view: SNGView
    '''
    super().__init__("bump out of windows")
    self.view:SNGView|None = view
    self.moves:list[tuple[VObject, list[int], list[int]]]|None = None
    "(object, its box before, after), in the order they were moved."

  @override
  def do(self) -> None:
    super().do()
    assert self.view is not None
    if self.moves is None:
      self.moves = self.view.bumpIntruders()
      return
    for vo, _, new in self.moves:
      vo.moveTo(new[0], new[1], adjustPos=False)

  @override
  def undo(self):
    super().undo()
    for vo, old, _ in reversed(self.moves or []):
      vo.moveTo(old[0], old[1], adjustPos=False)

  @override
  def delete(self):
    super().delete()
    self.view, self.moves = None, None

class _Bumped(CompositeCommand):
  '''
  A command, already done, and the bumping out of windows that followed it
  (see *ViewDoList*): one entry on the undo list, named as the command.
  '''
  def __init__(self, command:Command, bump:_BumpIntruders):
    '''
    :param command:
    :type command: Command
    :param bump:
    :type bump: _BumpIntruders
    '''
    super().__init__([command, bump])
    self.name = command.name
    self.done = True

  @override
  def undo(self) -> Any:
    '''
    Undo both -- then put the floating labels of the relations to and from
    what was bumped back between their ends: they were put back while what
    the command moved (eg: a window dropped on them) was still in the way.

    :returns:
    :rtype: Any
    '''
    ret = super().undo()
    bump = self.commands[1]
    assert isinstance(bump, _BumpIntruders)
    moved = [vo for vo, _, _ in bump.moves or []]
    for vo in [*moved, *(c for w in moved for c in w.carriedContents())]:
      for r in list(vo.relations):
        if isinstance(r, VRelation) and r._isConnected() and r.floating():
          r.reposition(adjustPos=False)
    return ret

  @override
  def __str__(self):
    '''
    :returns: A readable string for this object.
    :rtype:
    '''
    return str(self.commands[0])

class _Adjusted(CompositeCommand):
  '''
  A command, already done, and the view's dynamic layout's adjustment after
  it (see *ViewDoList*, *layout.LayoutHeuristic.adjust()*): one entry on the
  undo list, named as the command.
  '''
  def __init__(self, command:Command, adjustment:LayoutMoves):
    '''
    :param command:
    :type command: Command
    :param adjustment:
    :type adjustment: LayoutMoves
    '''
    super().__init__([command, adjustment])
    self.name = command.name
    self.done = True

  @override
  def __str__(self):
    '''
    :returns: A readable string for this object.
    :rtype:
    '''
    return str(self.commands[0])

class ViewDoList(DoList):
  '''
  A view's undo list (see *SNGContext*). After each command that changes
  anything, whatever is left in a context window it doesn't belong in is
  pushed out (see *SNGView.bumpIntruders()*), and then the view's dynamic
  layout adjusts the rest (see *layout.LayoutHeuristic.adjust()*) -- as part
  of the same undo entry. (Not during a drag, which isn't a command until
  it's dropped; nor after a layout's own moves: see *layout.LayoutMoves*.) A
  tweened move under way is finished first (see *layout.finishTween()*).
  '''
  def __init__(self, view:SNGView):
    '''
    :param view:
    :type view: SNGView
    '''
    super().__init__()
    self.view:SNGView = view
    self._adjustingAgain = False

  def adjustAgain(self) -> None:
    '''
    Once the view objects the last command made are drawn (they're made
    after it's done, when the model says what it made: see
    *SNGView._placeNew()*), let the view's dynamic layout adjust again (see
    *layout.LayoutHeuristic.adjust()*) -- as part of the same undo entry.
    Called for each new object: it adjusts once, when they all are.
    '''
    if self._adjustingAgain or not self.view.canvas:
      return
    self._adjustingAgain = True
    def again() -> None:
      self._adjustingAgain = False
      layout = self.view.localLayout
      if layout is None or not 0 <= self.index < len(self.queue):
        return
      c = self.queue[self.index]
      if getattr(c, "isLayout", False):
        return
      try:
        adjustment = layout.adjust(c)
        if adjustment is not None and not adjustment.isEmpty():
          adjustment.do()
          self.queue[self.index] = _Adjusted(c, adjustment)
      except Exception:
        logger.exception(f'the view\'s dynamic layout ("{layout.NAME}") couldn\'t adjust it')
    self.view.canvas.after_idle(again)

  def _refuses(self, c:Command, doing:str) -> bool:
    '''
    :param c: The command about to be done, undone or redone.
    :type c: Command
    :param doing: What's being done with it, for the message: eg, "undo".
    :type doing: str
    :returns: Whether it's refused (with a warning): it changes the model, and
      the view can't (see *SNGView.isModelEditor()*).
    :rtype: bool
    '''
    if self.view.isModelEditor() or not changesModel(c):
      return False
    logger.warning(f'Can\'t {doing} "{c.name}". {self.view.lockedReason()}')
    self.view.window.bell()
    return True

  @override
  def do(self, c:Command) -> Any:
    '''
    :param c:
    :type c: Command
    :returns:
    :rtype: Any
    :raises PermissionError: If *c* changes the model, and the view can't (see
      *SNGView.isModelEditor()*).
    '''
    finishTween(self.view)
    if not self.view.isModelEditor() and changesModel(c):
      raise PermissionError(self.view.lockedReason())
    ret = super().do(c)
    if c.mutatedData and 0 <= self.index < len(self.queue) and self.queue[self.index] is c:
      try:
        bump = _BumpIntruders(self.view)
        bump.do()
        if bump.moves:
          self.queue[self.index] = _Bumped(c, bump)
      except Exception:
        logger.exception("couldn't bump objects out of the windows they don't belong in")
      if not getattr(c, "isLayout", False) and self.view.localLayout is not None: # (None: a program's turned it off for now)
        try:
          adjustment = self.view.localLayout.adjust(c)
          if adjustment is not None and not adjustment.isEmpty():
            adjustment.do()
            self.queue[self.index] = _Adjusted(self.queue[self.index], adjustment)
        except Exception:
          logger.exception(f'the view\'s dynamic layout ("{self.view.localLayout.NAME}") couldn\'t adjust it')
    return ret

  @override
  def undo(self) -> Any:
    finishTween(self.view)
    if 0 <= self.index < len(self.queue) and self._refuses(self.queue[self.index], "undo"):
      return None
    return super().undo()

  @override
  def redo(self) -> Any:
    finishTween(self.view)
    if 0 <= self.index + 1 < len(self.queue) and self._refuses(self.queue[self.index + 1], "redo"):
      return None
    return super().redo()

class _ContainCreated(Command):
  '''
  Contains, in *context*, the relation (or node) that the command *creator*
  creates -- *creator* being queued earlier in the same composite command, so
  it doesn't exist yet when this is made. See *SNGView._containNewRelation()*
  and *SNGView.addNewObjectMenus()*.
  '''
  def __init__(self, model:Model, typ:Relation, context:GraphObject, creator:Command):
    '''
    :param model:
    :type model: Model
    :param typ:
    :type typ: Relation
    :param context:
    :type context: GraphObject
    :param creator:
    :type creator: Command
    '''
    super().__init__("contain")
    self.model, self.typ, self.context, self.creator = model, typ, context, creator
    self.relation:Relation|None = None

  @override
  def do(self) -> Relation|None:
    '''
    :returns:
    :rtype: Relation | None
    '''
    super().do()
    if self.relation is None:
      created = getattr(self.creator, "relation", None) or getattr(self.creator, "node", None)
      if created is None:
        return None
      self.relation = Relation(db=self.model, parents=[self.typ], src=self.context, dst=created, individual=True)
    else:
      self.relation._reconnect()
    return self.relation

  @override
  def undo(self):
    '''
    :returns:
    :rtype:
    '''
    super().undo()
    if self.relation is not None:
      self.relation._disconnect()
    return self.relation

def keptWith[T](keep:Iterable[T], objects:Iterable[T], ends:Callable[[T], tuple[T|None, T|None]|None],
                contents:Callable[[T], Iterable[T]]) -> list[T]:
  '''
  What stays in a view when everything but *keep* is erased (see
  *SNGView.doEraseOthers()*): *keep*, what's in the context windows in *keep*
  (and in the windows in those, ...), and, as long as there's more --

    - the ends of a kept relation (it can't be shown without them);
    - a relation between two kept objects (or from a kept object to itself);
    - a context window with a kept object in it (so a kept object in a rule
      is still seen to be in the rule) -- but not the rest of what's in it.

  :param keep: The objects to keep.
  :type keep: Iterable[T]
  :param objects: Everything in the view.
  :type objects: Iterable[T]
  :param ends: An object's ends (src, dst), if it's a relation (an end may
    be None: eg: a relation type's, dangling); else None.
  :type ends: Callable[[T], tuple[T | None, T | None] | None]
  :param contents: What's in an object's window, if it's a context window; else nothing.
  :type contents: Callable[[T], Iterable[T]]
  :returns: Those to keep, in no particular order (each once).
  :rtype: list[T]
  '''
  # (by id(): view objects' own hashing is slow -- and *objects* can be many)
  objects = list(objects)
  endsOf = {id(o): e for o in objects if (e := ends(o)) is not None}
  inside = {id(o): c for o in objects if (c := list(contents(o)))}
  kept:dict[int, T] = {id(o): o for o in keep}
  windows = [o for o in kept.values() if id(o) in inside]
  while windows:
    more = [c for c in inside[id(windows.pop())] if id(c) not in kept]
    kept.update((id(c), c) for c in more)
    windows += [c for c in more if id(c) in inside]
  while True:
    found = {id(e): e for o in kept.values() for e in endsOf.get(id(o), ()) if e is not None and id(e) not in kept}
    found.update((id(o), o) for o in objects if id(o) not in kept and
                 ((id(o) in endsOf and all(e is not None and id(e) in kept for e in endsOf[id(o)]))
                  or any(id(c) in kept for c in inside.get(id(o), ()))))
    if not found:
      return list(kept.values())
    kept.update(found)
