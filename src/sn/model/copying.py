'''
Copying model objects: what cut, copy and paste are made of.

Copying is done on the model, not the view: a view can't show a model object
twice, so a copy of what a view shows has to be new model objects -- with new
ids -- which the view (or any view of the model) then shows as it shows any
new object.

*copyObjects()* takes a snapshot of some objects -- a *Clip* -- and
*pasteInto()* makes new objects from it in a model, as often as it's asked.
What's copied:

- the objects themselves, with their own (not inherited) attributes, as they
  are when they're copied (later changes to them aren't pasted);
- a context's contents (see *contents()*), and theirs, with the containment
  relations: copying a rule copies its antecedent and consequent;
- each object's isa links, so a copy has the original's types.

A copied relation's end that's copied too is the copy's end; an end that
isn't copied is shared: the copy relates the same object. Likewise a type
that isn't copied: the copy is another instance (or subtype) of it. So a copy
refers to the objects around it, which must be there -- in the model it's
pasted into, or in one that model builds on (see *pasteProblem()*). That's
what keeps a paste into another model sound, and why it's refused when it
isn't.

What the reasoner concluded (see *GraphObject.inferred*) isn't copied: not
inferred objects, nor inferred isa links or attributes.

Created on Oct 8, 2026

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
import copy
from dataclasses import dataclass, field
from typing import Any, Iterable
from util.attribute import Attribute
from util.observer import Subject
from sn.model.model import GraphObject, Model, Node, Collection, Relation, IsaIndividual

Ref = int|GraphObject|None
'''
How a *Clip* entry refers to another object: the index of another entry (an
object copied with it), the object itself (one that isn't copied: shared by
the copy), or None (no such end).
'''

@dataclass
class Entry:
  '''
  One copied object, in a *Clip*.
  '''
  kind:str
  'What to make: "node", "relation" or "isa" (an isa link).'
  individual:bool
  'An individual or a type.'
  attributes:dict[str, Attribute]
  'Copies of the object\'s own attributes (not inherited ones, nor inferred ones).'
  original:GraphObject
  'What was copied (so a view can find how it showed it -- see *Clip.geometry*).'
  src:Ref = None
  'A relation\'s own source (not one it inherits), if any.'
  dst:Ref = None
  'A relation\'s own destination, if any.'

@dataclass
class Clip:
  '''
  A snapshot of copied objects (see *copyObjects()*): enough to make copies of
  them later, in this model or another (see *pasteInto()*).
  '''
  entries:list[Entry]
  model:Model
  'The model the objects were copied from.'
  selected:list[int] = field(default_factory=list)
  'The entries for the objects asked for (not the contents and isa links that came with them).'
  geometry:dict[int, dict[str, Any]] = field(default_factory=dict)
  '''
  How a view showed the copied objects, by entry, if they were copied from a
  view: what it takes to show the copies the same way (eg: the bounding box).
  Filled by the view; the model doesn't look at it.
  '''
  viewURL:str|None = None
  'The view they were copied from, if any.'

  def originals(self) -> list[GraphObject]:
    '''
    :returns: The copied objects, in entry order.
    :rtype: list[GraphObject]
    '''
    return [e.original for e in self.entries]

  def externals(self) -> list[GraphObject]:
    '''
    :returns: The objects the copies refer to but which aren't copied (types,
      and relations' ends), each once.
    :rtype: list[GraphObject]
    '''
    ret:list[GraphObject] = []
    for e in self.entries:
      for r in (e.src, e.dst):
        if isinstance(r, GraphObject) and not any(r is o for o in ret):
          ret.append(r)
    return ret

clipboard:Clip|None = None
'''
What was last cut or copied (see *sn.controller.modelInterface.ModelContext.copy()*):
one for the whole application, so it can be pasted into any view.
'''

def contents(context:GraphObject) -> list[GraphObject]:
  '''
  :param context: Any object.
  :type context: GraphObject
  :returns: The (asserted) containment relations from *context* (relations
    that isa *contains*: eg: a rule's antecedent relations), each followed by
    what it contains. Empty if it isn't a context.
  :rtype: list[GraphObject]
  '''
  model = context.model
  contains = getattr(model, "CONTAINS", None)
  ret:list[GraphObject] = []
  if contains is None or not context.isIndividual() or isinstance(context, Relation):
    return ret
  for r in list(context._outgoing):
    if getattr(r, "inferred", False) or not r.isIndividual() or isinstance(r, IsaIndividual):
      continue
    if r.localSrc is context and r.localDst is not None and r.isa(contains):
      ret += [r, r.localDst]
  return ret

def closure(objects:Iterable[GraphObject]) -> list[GraphObject]:
  '''
  :param objects: The objects asked for.
  :type objects: Iterable[GraphObject]
  :returns: What's copied when *objects* are: them, the contents of any that
    are contexts (at any depth: see *contents()*), and the isa links of all
    of those -- each once, in that order. Not anything inferred, nor anything
    that's been deleted.
  :rtype: list[GraphObject]
  '''
  ret:list[GraphObject] = []
  seen:set[int] = set()
  def add(o:GraphObject) -> None:
    if id(o) in seen or getattr(o, "inferred", False) or not o._isConnected():
      return
    seen.add(id(o))
    ret.append(o)
    for c in contents(o):
      add(c)
  for o in objects:
    add(o)
  for o in list(ret):
    for r in list(o._outgoing):
      if isinstance(r, IsaIndividual) and r.localSrc is o:
        add(r)
  return ret

def _kind(o:GraphObject) -> str|None:
  '''
  :param o:
  :type o: GraphObject
  :returns: What *Entry.kind* copies *o*, or None if it can't be copied.
  :rtype: str | None
  '''
  if isinstance(o, IsaIndividual):
    return "isa"
  if isinstance(o, Relation):
    return "relation"
  if isinstance(o, Node) and not isinstance(o, Collection):
    return "node"
  return None

def copyObjects(objects:Iterable[GraphObject]) -> Clip:
  '''
  Take a snapshot of *objects* and what comes with them (see *closure()*).

  :param objects: What's asked for (eg: what's selected in a view).
  :type objects: Iterable[GraphObject]
  :returns: The snapshot.
  :rtype: Clip
  :raises ValueError: If there's nothing that can be copied.
  '''
  asked = [o for o in objects if o is not None]
  objs = [o for o in closure(asked) if _kind(o) is not None]
  if not objs:
    raise ValueError("There's nothing to copy (what's inferred can't be copied: mark it as asserted first).")
  index = {id(o):i for i, o in enumerate(objs)}
  def ref(o:GraphObject|None) -> Ref:
    if o is None:
      return None
    return index.get(id(o), o)
  entries:list[Entry] = []
  for o in objs:
    attrs = {k:_copyAttribute(a) for k in dict.keys(o) if isinstance(a := dict.get(o, k), Attribute) and not a.inferred}
    e = Entry(kind=_kind(o), individual=o.isIndividual(), attributes=attrs, original=o) #type: ignore[arg-type]
    if isinstance(o, Relation):
      e.src, e.dst = ref(o.localSrc), ref(o.localDst)
    entries.append(e)
  selected = [index[id(o)] for o in asked if id(o) in index]
  return Clip(entries, objs[0].model, selected=selected)

def _copyAttribute(a:Attribute) -> Attribute:
  '''
  :param a:
  :type a: Attribute
  :returns: A copy of *a* (and of its value), as given (not inferred).
  :rtype: Attribute
  '''
  ret = Attribute(copy.deepcopy(a.value), a.type, a.restriction, a.note)
  ret.userNote = a.userNote
  return ret

def visibleModels(model:Model) -> list[Model]:
  '''
  :param model:
  :type model: Model
  :returns: The models whose objects *model*'s objects may refer to: itself,
    and those it builds on.
  :rtype: list[Model]
  '''
  ret:list[Model] = [model]
  for m in [*model.allSuperDBs(), *model.implicitSuperDBs()]:
    if isinstance(m, Model) and not any(m is r for r in ret):
      ret.append(m)
  return ret

def pasteProblem(clip:Clip|None, model:Model) -> str|None:
  '''
  :param clip:
  :type clip: Clip | None
  :param model: Where it's to be pasted.
  :type model: Model
  :returns: Why *clip* can't be pasted into *model*, or None if it can: the
    objects the copies would refer to (see *Clip.externals()*) must still be
    there, and be in *model* or in a model it builds on -- a model can't
    refer to one it doesn't know about.
  :rtype: str | None
  '''
  if clip is None or not clip.entries:
    return "There's nothing to paste: cut or copy something first."
  if model.writeLocked():
    return f'"{model.name}" is write locked: nothing can be pasted into it.'
  visible = visibleModels(model)
  for o in clip.externals():
    if not o._isConnected():
      return f'The copy refers to "{o.name}", which has been removed from "{o.model.name}" since it was copied.'
    if not any(o.model is m for m in visible):
      return (f'The copy refers to "{o.name}" in "{o.model.name}", which "{model.name}" doesn\'t build on: '
              f'paste it into a view of "{o.model.name}" (or of a model that builds on it), '
              f'or make "{o.model.name}" a super model of "{model.name}" first.')
  return None

def pasteInto(clip:Clip, model:Model) -> list[GraphObject]:
  '''
  Make new objects in *model* from *clip*, with new ids.

  :param clip:
  :type clip: Clip
  :param model:
  :type model: Model
  :returns: The new objects, by entry (as *clip.entries*).
  :rtype: list[GraphObject]
  :raises ValueError: If it can't be pasted there (see *pasteProblem()*).
  '''
  problem = pasteProblem(clip, model)
  if problem is not None:
    raise ValueError(problem)
  made:list[GraphObject|None] = [None] * len(clip.entries)
  def end(r:Ref) -> GraphObject|None:
    if isinstance(r, int):
      return made[r]
    return r
  with Subject.ChangeMgr(model, later=True):
    # the objects first (their ends may be any of them -- relations can relate relations), ...
    for i, e in enumerate(clip.entries):
      if e.kind == "node":
        made[i] = Node(model, [], individual=e.individual)
      elif e.kind == "relation":
        made[i] = Relation(model, [], individual=e.individual)
    # ... then their ends, then the isa links (whose ends must be there when they're made) ...
    for i, e in enumerate(clip.entries):
      o = made[i]
      if isinstance(o, Relation):
        o.connect(end(e.src), end(e.dst))
      elif e.kind == "isa":
        made[i] = IsaIndividual(model, end(e.src), end(e.dst))
    # ... then the attributes (as they were: they were legal with these types)
    for i, e in enumerate(clip.entries):
      o = made[i]
      assert o is not None
      for k, a in e.attributes.items():
        dict.__setitem__(o, k, _copyAttribute(a))
      o.setDirty()
  return made #type: ignore[return-value]

def cutObjects(clip:Clip) -> list[GraphObject]:
  '''
  :param clip: What's being cut (see *copyObjects()*).
  :type clip: Clip
  :returns: What cutting removes: what was copied, except what came with a
    context (see *contents()*) that another context, not being cut, contains
    too -- it's still that one's.
  :rtype: list[GraphObject]
  '''
  objs = clip.originals()
  cut = {id(o) for o in objs}
  asked = {id(clip.entries[i].original) for i in clip.selected}
  contains = getattr(clip.model, "CONTAINS", None)
  def shared(o:GraphObject) -> bool:
    return contains is not None and any(r.localDst is o and r.isIndividual() and id(r.localSrc) not in cut and r.isa(contains)
                                        for r in o._incoming if not isinstance(r, IsaIndividual))
  return [o for o in objs if id(o) in asked or not shared(o)]

def removeObjects(objects:Iterable[GraphObject]) -> list[GraphObject]:
  '''
  Take *objects* out of their models (undoably: see *restoreObjects()*).
  Removing an object takes its relations with it (see
  *GraphObject._disconnect()*), so one may already be gone when its turn comes:
  it's skipped.

  :param objects:
  :type objects: Iterable[GraphObject]
  :returns: Those that were taken out, in order: what to give *restoreObjects()*.
  :rtype: list[GraphObject]
  '''
  ret:list[GraphObject] = []
  for o in objects:
    if o._isConnected():
      o._disconnect()
      ret.append(o)
  return ret

def restoreObjects(removed:list[GraphObject]) -> None:
  '''
  Put back what *removeObjects()* took out (in reverse order, each with the
  relations it took with it), as far as it can: one that's back already is
  skipped.

  :param removed: What *removeObjects()* returned.
  :type removed: list[GraphObject]
  '''
  for o in reversed(removed):
    if not o._isConnected():
      o._reconnect()
