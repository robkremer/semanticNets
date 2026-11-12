'''
A KNet net as a whole (Gaines, section 3: the dynamics of logical
structures): its canonical forms, saturating it with probes, and what
merging it with another net does.

  - *minimalForm()*: the net without its links that the rest imply (see
    *redundantLinks()*) -- unique but for which links of a cycle stay;
  - *maximalForm()*: the net with every link the kernel's patterns infer
    (see *maximalLinks()*), asserted;
  - *saturate()*: the net with its probes (see *probes*) added as nodes of
    *PROBE*, from outside: each includes the nodes true in it and excludes
    those false in it;
  - *checkMerge()*: whether merging another net into it (their nodes with
    the same label one) is consistent (no new inconsistent links),
    conservative (no new links in the other net) and ultra-conservative (none
    in either).

Each changes the model through a view's *context* (as one command, undone
in one go), if it's given one.

Created on Nov 12, 2026

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
import itertools
import os
import tempfile
from dataclasses import dataclass, field
from typing import Any
from sn.model.model import Model, Node, Relation, GraphObject, IsaIndividual
from sn.model.reasoner import Reasoner, TooManyProbes, ADMISSIBLE
from sn.controller.modelInterface import ModelCommand
from .reader import (KERNEL, INCLUDES, EQUIVALENT, EXCLUDES, COEXCLUDES, NEGATES, INCONSISTENT, CONNECTIVES, SAME_LABEL,
                     CONSTRUCT_EXCLUDES, kernelTypes)
from .probes import netNodes, findProbes, name

PROBE = "probe"
'''The SN type (in the KNet rules model, an SN subtype of *reader.KNODE* that
isn't the net's: see *reader.KNET_NODE*) of the probes *saturate()* adds.'''

SATURATION_LIMIT = 64
"The most probes *saturate()* adds: each is a node in the view."

# ── The net's links ───────────────────────────────────────────────────────

def _kernel(model:Model) -> dict[str, Relation]:
  ''':returns: The kernel relation types (*reader.KERNEL*) of *model*'s net, by name.'''
  types = kernelTypes(model)
  return {k: types[k] for k in KERNEL if k in types}

def kernelOf(r:Relation, kernel:dict[str, Relation]) -> list[Relation]:
  '''
  :param kernel: The kernel relation types (see *_kernel()*).
  :returns: The kernel types *r* is (an SN subtype of) -- the nearest: eg, a
    negation's negates, not the excludes and coexcludes it is too.
  '''
  mine = [t for t in kernel.values() if r.isa(t)]
  return [t for t in mine if not any(o is not t and o.isa(t) for o in mine)]

def netLinks(model:Model) -> list[Relation]:
  '''
  :returns: The links of *model*'s net that say what the kernel says: its own
    individual relations (not the reasoner's) between its nodes (see
    *probes.netNodes()*) of the kernel's relation types -- not those that
    define a connective (see *reader.CONNECTIVES*: they're definitions), nor
    those the reader made for what boxes and labels mean (*reader.CONSTRUCT_EXCLUDES*,
    *reader.SAME_LABEL*). In the model's order.
  '''
  kernel = _kernel(model)
  nodes = {id(n) for n in netNodes(model)}
  defining = [t for k, t in kernelTypes(model).items() if k in CONNECTIVES.values()]
  ret = []
  for r in model.values():
    if not isinstance(r, Relation) or isinstance(r, IsaIndividual) or r.model is not model or not r.isIndividual() \
       or getattr(r, "inferred", False) or id(r.src) not in nodes or id(r.dst) not in nodes:
      continue
    names = {str(t.name) for t in r.isa() if isinstance(t, Relation)}
    if kernelOf(r, kernel) and not names & {SAME_LABEL, CONSTRUCT_EXCLUDES} and not any(r.isa(t) for t in defining):
      ret.append(r)
  return ret

def redundantLinks(model:Model, engine:str|None=None) -> list[Relation]:
  '''
  :returns: The links of *model*'s net (see *netLinks()*) that the rest
    imply (see *sn.model.reasoner.Reasoner.redundant()*), in the net's order:
    each, tried newest first, is redundant if its kernel types (see
    *kernelOf()*) still hold between its ends without it -- and those found
    so stay out while the rest are tried. (Eg: KNet's derived links, and A
    includes C beside A includes B and B includes C.) Newest first, so that
    what was added last goes first: eg, what *maximalForm()* asserted, and
    the net's own links stay -- the minimal form of its maximal form is the
    net's.
  :param engine: The reasoner engine (by default, the setting's).
  '''
  kernel = _kernel(model)
  links = netLinks(model)
  found = {id(r) for r in Reasoner.create(model, engine).redundant(links[::-1], lambda r: kernelOf(r, kernel))}
  return [r for r in links if id(r) in found]

def minimalForm(model:Model, context:Any=None, engine:str|None=None) -> list[Relation]:
  '''
  Gaines's minimal canonical form: take out the net's redundant links (see
  *redundantLinks()*).

  :param context: A view's *ModelContext*, to do it as one command (undone in
    one go); or None, to take them out of the model as it is.
  :returns: The links taken out.
  '''
  gone = redundantLinks(model, engine)
  if not gone:
    return gone
  if context is None:
    for r in gone:
      r._disconnect()
    return gone
  from util.commandParser import CompositeCommandMgr
  with CompositeCommandMgr(context):
    for r in gone:
      context.remove(r)
  return gone

def maximalLinks(model:Model, engine:str|None=None) -> list[Relation]:
  '''
  Reason over *model* (see *sn.model.reasoner.reason()*: its results are
  kept on it), and

  :returns: The kernel's links between the net's nodes that the reasoner
    inferred, and a view would show (see *SNGView._impliedByShown()*): not one
    from a node to itself, nor one beside a link of its type (or an SN
    subtype) between the same nodes -- the same way round, or either way, if
    either's symmetric -- in the net, or before it here (the subtypes'
    first: eg, an equivalence, then the inclusions it is).
  '''
  from sn.model.reasoner import reason
  reason(model, engine, silent=True)
  kernel = _kernel(model)
  nodes = {id(n) for n in netNodes(model)}
  found = [r for r in model.inferredObjects()
           if isinstance(r, Relation) and not isinstance(r, IsaIndividual) and r.isIndividual()
           and id(r.localSrc) in nodes and id(r.localDst) in nodes and r.localSrc is not r.localDst
           and any(t is k for t in r.getParents() for k in kernel.values())]
  def depth(r:Relation) -> int:
    t = r.getParents()[0]
    return -sum(1 for k in kernel.values() if t is not k and t.isa(k))
  found.sort(key=depth)
  kept:list[Relation] = list(netLinks(model))
  ret:list[Relation] = []
  for r in found:
    types = [t for t in r.getParents() if isinstance(t, Relation)]
    symmetric = any(t._hasRelationalProperty("symmetric") for t in types)
    def beside(o:Relation) -> bool:
      if not any(o.isa(t) for t in types):
        return False
      if o.localSrc is r.localSrc and o.localDst is r.localDst:
        return True
      return o.localSrc is r.localDst and o.localDst is r.localSrc \
             and (symmetric or any(p._hasRelationalProperty("symmetric") for p in o.getParents() if isinstance(p, Relation)))
    if not any(beside(o) for o in kept):
      kept.append(r)
      ret.append(r)
  return ret

def maximalForm(model:Model, context:Any=None, engine:str|None=None) -> list[Relation]:
  '''
  Gaines's maximal canonical form: the net with the kernel's links that it
  implies (see *maximalLinks()*) asserted.

  :param context: A view's *ModelContext*, to do it as one command (undone in
    one go); or None, to change the model as it is.
  :returns: The links asserted.
  '''
  added = maximalLinks(model, engine)
  if context is None:
    for r in added:
      for o in r.assertedWith():
        o.inferred = False
    if added:
      model.setDirty()
    return added
  from util.commandParser import CompositeCommandMgr
  if added:
    with CompositeCommandMgr(context):
      for r in added:
        context.mark_asserted(r)
  return added

# ── Saturation ────────────────────────────────────────────────────────────

class _AddObjects(ModelCommand):
  '''
  Add objects to a model: made the first time it's done (by *make*), and
  put back each time it's redone; taken out when it's undone.
  '''
  asksNames = False
  "A view doesn't ask the names of what it makes: they're named (see *sn.view.graphics.viewCommands.ViewDoList.do()*)."

  def __init__(self, name:str, model:Model, make:Any):
    '''
    :param name: The command's name (eg: "saturate").
    :param make: Makes the objects, in *model*: it returns them (the relations last).
    '''
    super().__init__(name)
    self.model, self.make = model, make
    self.objects:list[GraphObject]|None = None
    self.wasDirty:bool = model.isDirty()

  def do(self) -> list[GraphObject]:
    super().do()
    from util.observer import Subject
    with Subject.ChangeMgr(self.model, later=True):
      if self.objects is None:
        self.objects = list(self.make())
      else:
        for o in self.objects:
          o._reconnect()
    self.model.setDirty()
    return self.objects

  def undo(self) -> None:
    super().undo()
    from util.observer import Subject
    with Subject.ChangeMgr(self.model, later=True):
      for o in reversed(self.objects or []):
        if o._isConnected():
          o._disconnect()
    if not self.wasDirty:
      self.model.setDirty(False)

  def delete(self) -> None:
    super().delete()
    self.model, self.make, self.objects = None, None, None # type: ignore[assignment]

def probeType(model:Model) -> Node|None:
  ''':returns: *PROBE*, in the KNet rules model *model* is built on, if it's there.'''
  from .reader import ontology
  try:
    onto = ontology(model)
  except StopIteration:
    return None
  return next((o for o in onto.values() if o.model is onto and isinstance(o, Node) and o.isType() and o.name == PROBE), None)

def saturate(model:Model, kind:str=ADMISSIBLE, context:Any=None, limit:int=SATURATION_LIMIT, engine:str|None=None) \
    -> list[GraphObject]:
  '''
  Saturate *model*'s net (Gaines, section 3.6): add each of its probes (see
  *probes.findProbes()*: admissible ones, by default) as a node of *PROBE*,
  named "probe 1" and so on, that includes each node true in it and excludes
  each node false in it (both, for one both). They're probes of the whole
  net: each is one of each part's.

  :param context: A view's *ModelContext*, to do it as one command (undone in
    one go); or None, to add them to the model as it is.
  :param limit: The most probes to add.
  :returns: The nodes and relations added (the nodes first).
  :raises TooManyProbes: If there are more than *limit*.
  :raises ValueError: If the model isn't built on the KNet rules model (it has no *PROBE*).
  '''
  probe = probeType(model)
  if probe is None:
    raise ValueError(f'"{model.name}" isn\'t a KNet net: it has no "{PROBE}" type to make probes of.')
  found = findProbes(model, kind, engine)
  if found.count() > limit:
    raise TooManyProbes(limit)
  kernel = _kernel(model)
  inc, exc = kernel[INCLUDES], kernel[EXCLUDES]
  def make() -> list[GraphObject]:
    nodes:list[GraphObject] = []
    relations:list[GraphObject] = []
    taken = {str(o.name) for o in model.values() if isinstance(o, Node)}
    k = 0
    for each in itertools.product(*(part.probes for part in found.parts)):
      k += 1
      while f"probe {k}" in taken: # (a node of the net's name: not the same)
        k += 1
      p = Node(model, [probe], individual=True, name=f"probe {k}")
      nodes.append(p)
      for marks in each:
        for n, mark in marks.items():
          if "T" in mark:
            relations.append(Relation(model, [inc], p, n, individual=True))
          if "F" in mark:
            relations.append(Relation(model, [exc], p, n, individual=True))
    return nodes + relations
  if context is None:
    ret = make()
    model.setDirty()
    return ret
  return context.doList.do(_AddObjects("saturate", model, make))

# ── Merges ────────────────────────────────────────────────────────────────

Link = tuple[str, str, str]
"A link of the kernel between two nodes, by name: the relation type's, and the nodes' (see *probes.name()*)."

@dataclass
class MergeCheck:
  '''What merging one net into another does (see *checkMerge()*).'''
  importing:str
  "The net merged into (its model's name, without the file's extension)."
  imported:str
  "The net merged in."
  inconsistent:list[Link] = field(default_factory=list)
  "The inconsistent links the merge makes that neither net had."
  inImported:list[Link] = field(default_factory=list)
  "The links the merge makes between the imported net's nodes that it didn't have."
  inImporting:list[Link] = field(default_factory=list)
  "The links the merge makes between the importing net's nodes that it didn't have."
  shared:list[str] = field(default_factory=list)
  "The labels the nets share: their nodes with them are one."

  @property
  def consistent(self) -> bool:
    "Whether it's a consistent merge: it makes no inconsistent links neither net had."
    return not self.inconsistent

  @property
  def conservative(self) -> bool:
    "Whether it's a conservative one: it makes no new links in the imported net (only in the importing one)."
    return not self.inImported

  @property
  def ultraConservative(self) -> bool:
    "Whether it's an ultra-conservative one: it makes no new links in either."
    return not self.inImported and not self.inImporting

  def report(self) -> str:
    ''':returns: What it does, as text.'''
    def yes(b:bool) -> str:
      return "yes" if b else "no"
    def links(ls:list[Link]) -> list[str]:
      return [f"  {a} {t} {b}" for t, a, b in ls] or ["  none"]
    return "\n".join([
      f"Merging {self.imported} into {self.importing}",
      f"Nodes they share (by label): {', '.join(self.shared) or 'none'}",
      "",
      f"Consistent: {yes(self.consistent)}",
      f"Conservative: {yes(self.conservative)}",
      f"Ultra-conservative: {yes(self.ultraConservative)}",
      "",
      "New inconsistent links:", *links(self.inconsistent),
      "",
      f"New links in {self.imported}:", *links(self.inImported),
      "",
      f"New links in {self.importing}:", *links(self.inImporting)])

def _kernelLinks(holds:list[tuple[Any, Any, Any]], kernel:dict[str, Relation], nodes:list[Node]) -> set[tuple[str, int, int]]:
  ''':returns: The kernel's links that hold between *nodes* (each kernel type's name, and its ends' ids).'''
  names = {id(t): k for k, t in kernel.items()}
  where = {id(n) for n in nodes}
  return {(names[id(t)], id(s), id(d)) for t, s, d in holds if id(t) in names and id(s) in where and id(d) in where}

def _plain(links:set[tuple[str, int, int]], nodes:dict[int, Node]) -> list[Link]:
  '''
  :returns: *links* by the nodes' names, without the ones that say less than
    another (a symmetric one the other way round, an inclusion beside an
    equivalence, one of a node to itself but an inconsistent one), sorted.
  '''
  ret:set[Link] = set()
  for k, s, d in links:
    a, b = name(nodes[s]), name(nodes[d])
    if s == d and k != INCONSISTENT:
      continue
    if k in (INCLUDES, EXCLUDES) and (INCONSISTENT, s, d) in links: # (it says both)
      continue
    if k == EXCLUDES and (INCONSISTENT, d, s) in links: # (and exclusion's symmetric)
      continue
    if k == INCLUDES and ((EQUIVALENT, s, d) in links or (EQUIVALENT, d, s) in links):
      continue
    if k in (EXCLUDES, COEXCLUDES, EQUIVALENT, NEGATES) and (b.lower(), b) < (a.lower(), a): # (symmetric: one way round, by name)
      a, b = b, a
    ret.add((k, a, b))
  return sorted(ret, key=lambda l: (l[1].lower(), l[2].lower(), l[0]))

def _netName(model:Model) -> str:
  ''':returns: *model*'s name, without its file's extension (eg: "patterns").'''
  return os.path.splitext(str(model.name))[0]

def checkMerge(importing:Model, imported:Model, engine:str|None=None) -> MergeCheck:
  '''
  What merging the net *imported* into *importing* does (Gaines, section
  3.2): the nodes of the two with the same label (see *probes.name()*) are one
  -- equivalent (the reader's same label relation's SN supertype) -- and the
  merge is reasoned over (a model with the two as its super-models, not
  saved), and what it concludes compared with what each net does alone.

  :returns: The merge's new inconsistent links, and its new links in each net.
  '''
  kernel = _kernel(importing)
  a, b = netNodes(importing), netNodes(imported)
  aloneA = _kernelLinks(Reasoner.create(importing, engine).run().holds, kernel, a)
  aloneB = _kernelLinks(Reasoner.create(imported, engine).run().holds, kernel, b)
  folder = tempfile.mkdtemp(prefix="snMerge-")
  merged = Model(f"file://{os.path.join(folder, 'merge.snm')}")
  try:
    merged.setSuperModels([str(importing.url), str(imported.url)]) # (the models in memory: see PRDb.getDB())
    byName:dict[str, list[Node]] = {}
    for n in a:
      byName.setdefault(name(n), []).append(n)
    shared = []
    for n in b:
      if name(n) in byName:
        Relation(merged, [kernel[EQUIVALENT]], byName[name(n)][0], n, individual=True)
        if name(n) not in shared:
          shared.append(name(n))
    both = _kernelLinks(Reasoner.create(merged, engine).run().holds, kernel, a + b)
  finally:
    merged.unload() # (its equivalences come off the nets' nodes: see Model.unload())
    os.rmdir(folder) # (it's never saved)
  ids = {id(n): n for n in a + b}
  inA, inB = {id(n) for n in a}, {id(n) for n in b}
  check = MergeCheck(_netName(importing), _netName(imported), shared=sorted(shared, key=str.lower))
  check.inconsistent = _plain({l for l in both - aloneA - aloneB if l[0] == INCONSISTENT}, ids)
  check.inImported = _plain({l for l in both - aloneB if l[1] in inB and l[2] in inB}, ids)
  check.inImporting = _plain({l for l in both - aloneA if l[1] in inA and l[2] in inA}, ids)
  return check
