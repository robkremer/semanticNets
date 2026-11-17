'''
Cut, copy and paste in a view, not the model (see *ViewClip*): "Edit | Copy in
view" remembers view objects, and "Paste in view" makes copies of them -- new
view objects that show the same model objects, laid out the same way. Only in
a view that may show a model object more than once (see *SNGView.canonical()*).
The model's own cut, copy and paste (new model objects) is *sn.model.copying*.

Created on Nov 17, 2026

.. codeauthor:: Rob Kremer <robkremer@me.com>
'''
#################################################################################
# (c) Copyright 2026, Rob Kremer, MIT open source license.                      #
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
from dataclasses import dataclass, field
from typing import Iterable, TYPE_CHECKING
from sn.model.model import GraphObject, Model
from sn.model.modelPrefs import CANONICAL_VIEWS
if TYPE_CHECKING:
  from sn.view.graphics.vobjects import VObject
  from sn.view.graphics.sngView import SNGView

@dataclass
class Entry:
  '''
  One copied view object, in a *ViewClip*: what it shows, and how.
  '''
  modelObject:GraphObject
  'What it shows (the copy shows it too).'
  relation:bool
  'Whether it\'s a relation (a line, with its label) rather than a node (or box).'
  bb:list[int]
  'Its bounding box (view coords).'
  userSized:bool = False
  ownLabel:str|None = None
  'What it shows as its model object\'s name, if not that (see *VObject.ownLabel*).'
  collapsed:bool = False
  expandedHeight:int|None = None
  floating:bool|None = None
  'A relation\'s: whether its label floats between its ends.'
  filtered:bool = False
  'Whether it was hidden by its category (so is the copy): else the copy\'s shown, even if its category\'s hidden.'
  src:int|None = None
  '''A relation's: the entry its source end was drawn to, if that was copied too;
  else None (the copy's drawn to the nearest copy of its source).'''
  dst:int|None = None
  'A relation\'s: the entry its destination end was drawn to, as *src*.'

@dataclass
class ViewClip:
  '''
  View objects copied by "Copy in view" (see *copyViewObjects()*): enough to
  show their model objects again, as they were shown (see
  *EditingMixin.pasteCopies()*). The model objects themselves aren't copied:
  the copies show the same ones.
  '''
  entries:list[Entry]
  'Nodes first, then relations (each after the relations it\'s drawn to).'
  model:Model
  'The model of the view they were copied from.'
  selected:list[int] = field(default_factory=list)
  'The entries for the view objects asked for (not what came with them: what a box carries, and the lines between them).'
  viewURL:str|None = None
  'The view they were copied from.'

  def modelObjects(self) -> list[GraphObject]:
    ':returns: What the entries show, in entry order (each once).'
    ret:list[GraphObject] = []
    for e in self.entries:
      if not any(e.modelObject is o for o in ret):
        ret.append(e.modelObject)
    return ret

clipboard:ViewClip|None = None
'''
What was last cut or copied in a view (see *copyViewObjects()*): one for the
whole application, so it can be pasted into any view of the same model (or of
one that builds on it) that may show copies.
'''

def closure(vos:Iterable[VObject]) -> list[VObject]:
  '''
  :param vos: The view objects asked for (eg: what's selected).
  :returns: What "Copy in view" copies when *vos* are: them; what any that are
    boxes carry (at any depth: see *VObject.carriedContents()* -- hidden too:
    eg, in a collapsed box); and the lines between any of those (and between
    those) -- each once, in that order. Only what's in the view.
  '''
  from sn.view.graphics.vrelations import VRelation
  ret:list[VObject] = []
  seen:set[int] = set()
  def add(vo:VObject) -> None:
    if id(vo) in seen or not vo._isConnected() or vo.modelObject is None:
      return
    seen.add(id(vo))
    ret.append(vo)
    for c in vo.carriedContents():
      add(c)
  given = list(vos)
  for vo in given:
    add(vo)
  if not ret:
    return ret
  view = ret[0].view
  more = True
  while more: # (the lines between them -- and between those)
    more = False
    for vo in view.values():
      if isinstance(vo, VRelation) and id(vo) not in seen and id(vo.src) in seen and id(vo.dst) in seen \
         and vo._isConnected() and vo.modelObject is not None:
        seen.add(id(vo))
        ret.append(vo)
        more = True
  return ret

def copyViewObjects(vos:Iterable[VObject]) -> ViewClip:
  '''
  Take a snapshot of view objects (see *closure()*): what each shows, and how.

  :param vos: What's asked for (eg: what's selected in a view).
  :returns: The snapshot.
  :raises ValueError: If there's nothing to copy.
  '''
  from sn.view.graphics.vrelations import VRelation
  asked = [vo for vo in vos if vo is not None and vo._isConnected() and vo.modelObject is not None]
  objs = closure(asked)
  if not objs:
    raise ValueError("There's nothing to copy.")
  view = objs[0].view
  nodes = [vo for vo in objs if not isinstance(vo, VRelation)]
  rels = [vo for vo in objs if isinstance(vo, VRelation)]
  ordered:list[VObject] = list(nodes)
  placed = {id(vo) for vo in nodes}
  while rels: # (a relation after any relation it's drawn to: relations can relate relations)
    ready = [r for r in rels if all(e is None or id(e) in placed or not any(e is o for o in rels) for e in (r.src, r.dst))] or rels[:1]
    for r in ready:
      ordered.append(r)
      placed.add(id(r))
      rels.remove(r)
  index = {id(vo): i for i, vo in enumerate(ordered)}
  entries:list[Entry] = []
  for vo in ordered:
    mo = vo.modelObject
    assert mo is not None
    e = Entry(modelObject=mo, relation=isinstance(vo, VRelation), bb=[int(v) for v in vo.boundingBox()],
              userSized=bool(vo.userSized), ownLabel=vo.ownLabel,
              collapsed=bool(getattr(vo, "collapsed", False)), expandedHeight=getattr(vo, "expandedHeight", None),
              filtered=view.isFiltered(mo) and not vo.categoryExempt)
    if isinstance(vo, VRelation):
      e.floating = vo.floating()
      e.src, e.dst = index.get(id(vo.src)), index.get(id(vo.dst))
    entries.append(e)
  return ViewClip(entries, view.model, selected=[index[id(vo)] for vo in asked if id(vo) in index], viewURL=view.url)

def pasteProblem(clip:ViewClip|None, view:SNGView) -> str|None:
  '''
  :param view: Where it's to be pasted.
  :returns: Why *clip* can't be pasted into *view*, or None if it can: the view
    must be one that may show copies (see *SNGView.canonical()*), and at least
    one of the objects copied must still be in its model, or in one its model
    builds on (see *pastable()*).
  '''
  if clip is None or not clip.entries:
    return "There's nothing to paste in the view: cut or copy something in a view first."
  if view.canonical():
    return (f'"{view.name}" shows each object once (its model\'s "{CANONICAL_VIEWS}" preference): '
            f'"Paste in view" is for views that may show copies.')
  if not any(pastable(e, view) for e in clip.entries):
    gone = [o for o in clip.modelObjects() if not o._isConnected()]
    if len(gone) == len(clip.modelObjects()):
      return "What was copied has been removed from its model since."
    return (f'What was copied is in "{clip.model.name}", which "{view.model.name}" doesn\'t build on: '
            f'paste it into a view of "{clip.model.name}" (or of a model that builds on it).')
  return None

def pastable(e:Entry, view:SNGView) -> bool:
  '''
  :returns: Whether *view* can show what *e* shows: it's still in its model,
    and that's the view's model or one the view's model builds on.
  '''
  from sn.model.copying import visibleModels
  mo = e.modelObject
  return mo._isConnected() and any(mo.model is m for m in visibleModels(view.model))
