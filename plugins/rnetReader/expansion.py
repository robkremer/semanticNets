'''
Editing a KNet net without changing what it says (Gaines, sections 2.4, 3.3
and 3.4): the nets each of these makes are equivalent to the one it's done
to, but for what the new nodes are.

  - *expandProtoconnectives()*: a node whose label groups others' -- a
    protoconjunction ("A ∧ B", or "A & B") or a protodisjunction ("A ∨ B",
    or "A | B") -- is just notation: its links are those of its members (see
    *EXPANDS*), and it's replaced by them;
  - *addAnonymous()*: single-node expansion -- an anonymous node (an ideal
    element: no label) below a node, or above it, linked to it by one
    inclusion: ultra-conservative (it says nothing about the net);
  - *factor()*: factoring -- where some nodes each have the same kind of link
    to each of some others, an anonymous node interpolated between them
    carries those links (eg: I and J each including A, B and C: I and J
    include it, and it includes A, B and C), in fewer links (Gaines's figure
    28: 12 become 10).

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
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable
from sn.model.model import Model, Node, Relation, GraphObject, IsaIndividual
from .reader import INCLUDES, EXCLUDES, COEXCLUDES, CONNECTIVES, kernelTypes
from .forms import _AddObjects, _kernel, kernelOf, netLinks
from .probes import netNodes, name
from .hooks import MARK_TRUE, MARK_FALSE, ASSERTED

CONJUNCTION, DISJUNCTION = "conjunction", "disjunction"
"The kinds of protoconnective (see *protoconnective()*)."

SIGNS = {CONJUNCTION: ("∧", "&"), DISJUNCTION: ("∨", "|")}
"What separates the labels a protoconnective's label groups, by its kind."

EXPANDS = {INCLUDES: (DISJUNCTION, CONJUNCTION), EXCLUDES: (DISJUNCTION, DISJUNCTION),
           COEXCLUDES: (CONJUNCTION, CONJUNCTION)}
'''
The kernel's links a protoconnective at one of their ends is shorthand for
-- one link for each of its members -- and which kind it must be at each
end (tail, head). Extensionally (A includes B: A's instances are B's):

  - X includes A ∧ B: X includes A, and X includes B; and A ∨ B includes X:
    A includes X, and B does;
  - X excludes A ∨ B (either way round): it excludes A, and it excludes B
    (nothing's in X and in A or B);
  - X coexcludes A ∧ B (either way round): it coexcludes A, and B
    (everything's in X or in both A and B).

The others don't come apart into links of their members (eg: X includes A
∨ B says less than either; X negates A ∧ B, or is equivalent to it, says
more than links of its members can): a protoconnective with one of them
isn't expanded. Nor is a protoconjunction marked false, or a
protodisjunction marked true; one marked true is a protoconjunction whose
members are true, and one marked false a protodisjunction whose members
are.
'''

ANONYMOUS = "anonymous"
"The start of the names of the anonymous nodes made here (eg: \"anonymous 1\"): they're drawn without a label."

# ── Protoconnectives ──────────────────────────────────────────────────────

def protoconnective(label:str) -> tuple[str, list[str]]|None:
  '''
  :param label: A node's label.
  :returns: If it groups others' labels -- a protoconjunction's (its labels
    separated by "∧" or "&") or a protodisjunction's ("∨" or "|"), not both
    kinds' -- its kind (*CONJUNCTION* or *DISJUNCTION*) and the labels (each
    on one line, without spaces at its ends, and once); else None.
  '''
  kinds = [k for k, signs in SIGNS.items() if any(s in label for s in signs)]
  if len(kinds) != 1:
    return None
  parts = re.split("|".join(re.escape(s) for s in SIGNS[kinds[0]]), label)
  members = list(dict.fromkeys(" ".join(p.split()) for p in parts))
  if len(members) < 2 or not all(members):
    return None
  return kinds[0], members

@dataclass
class Expansion:
  '''What expanding a net's protoconnectives does (see *planProtoconnectives()*).'''
  groups:list[Node] = field(default_factory=list)
  "The protoconnectives expanded (taken out, with their links)."
  members:dict[int, list[Node|str]] = field(default_factory=dict)
  "Each one's members (by its id): the net's nodes with their labels, or the labels of those to make."
  links:list[tuple[Relation, Node|str, Node|str, Relation]] = field(default_factory=list)
  "The links to make: (the relation type, its ends -- as in *members* -- and the link it's one of)."
  marks:list[tuple[Node|str, str]] = field(default_factory=list)
  "The marks to assert: (the node, as in *members*, and the mark's key)."
  kept:list[tuple[Node, str]] = field(default_factory=list)
  "The protoconnectives that can't be expanded, and why."

def _definesConnective(n:Node, model:Model) -> bool:
  ''':returns: Whether *n* is a structural connective of *model*: the source or destination of a link that defines one.'''
  defining = [t for k, t in kernelTypes(model).items() if k in CONNECTIVES.values()]
  return any(r.isa(t) for r in [*n._outgoing, *n._incoming] if isinstance(r, Relation) and not isinstance(r, IsaIndividual)
             for t in defining)

def planProtoconnectives(model:Model) -> Expansion:
  '''
  :returns: What expanding the protoconnectives of *model*'s net does (see
    *expandProtoconnectives()*): the nodes whose labels group others' (see
    *protoconnective()*), but not a structural connective (one its links
    define: see *reader.CONNECTIVES*), with what each one's links and marks
    become (see *EXPANDS*) -- or why it's kept.
  '''
  kernel = _kernel(model)
  nodes = netNodes(model)
  byName:dict[str, Node] = {}
  for n in nodes:
    byName.setdefault(name(n), n)
  groups:dict[int, tuple[Node, str, list[Node|str]]] = {}
  for n in nodes:
    p = protoconnective(name(n))
    if p is not None and not _definesConnective(n, model):
      groups[id(n)] = (n, p[0], [byName.get(m, m) for m in p[1]])
  ret = Expansion()
  links = netLinks(model)
  why:dict[int, str] = {}
  for r in links:
    kinds = [str(t.name) for t in kernelOf(r, kernel)]
    for end, n in enumerate((r.src, r.dst)):
      if id(n) not in groups or id(n) in why:
        continue
      kind = groups[id(n)][1]
      allowed = EXPANDS.get(kinds[0]) if len(kinds) == 1 else None
      if allowed is None:
        why[id(n)] = f"its link {_describe(r)} isn't one of its members' links"
      elif allowed[end] != kind:
        why[id(n)] = f"a {kind}'s link {_describe(r)} isn't one of its members' links"
  for gid, (n, kind, members) in groups.items():
    if gid in why:
      continue
    for key, ok in ((MARK_TRUE, CONJUNCTION), (MARK_FALSE, DISJUNCTION)):
      a = n.getLocalAttr(key)
      if a is not None and not getattr(a, "inferred", False) and kind != ok:
        why[gid] = f"a {kind} marked {'true' if key == MARK_TRUE else 'false'} isn't its members marked so"
  for gid, (n, kind, members) in groups.items():
    if gid in why:
      ret.kept.append((n, why[gid]))
      continue
    ret.groups.append(n)
    ret.members[gid] = members
    for key in (MARK_TRUE, MARK_FALSE):
      a = n.getLocalAttr(key)
      if a is not None and not getattr(a, "inferred", False):
        ret.marks += [(m, key) for m in members]
  expanded = {id(n) for n in ret.groups}
  ends = lambda n: ret.members[id(n)] if id(n) in expanded else [n]
  made:set[tuple[int, str, str]] = set()
  for r in links:
    if id(r.src) not in expanded and id(r.dst) not in expanded:
      continue
    t = r.getParents()[0]
    for s in ends(r.src):
      for d in ends(r.dst):
        key = (id(t), _key(s), _key(d))
        if s is d or (isinstance(s, str) and s == d) or key in made or _linked(t, s, d, links):
          continue
        made.add(key)
        ret.links.append((t, s, d, r))
  return ret

def _key(n:Node|str) -> str:
  ''':returns: Who *n* is, for comparing: a node's id, or a label (of a node to make).'''
  return f"#{id(n)}" if isinstance(n, Node) else n

def _linked(t:Relation, s:Node|str, d:Node|str, links:list[Relation]) -> bool:
  ''':returns: Whether the net has a link of the relation type *t* from *s* to *d* already (not if either's to be made).'''
  return isinstance(s, Node) and isinstance(d, Node) and any(r.src is s and r.dst is d and r.isa(t) for r in links)

def _describe(r:Relation) -> str:
  ''':returns: A link, as its ends' names and its relation type's: eg, "dog Includes animal".'''
  return f"{name(r.src)} {r.getParents()[0].name} {name(r.dst)}"

def expandProtoconnectives(model:Model, context:Any=None) -> tuple[list[GraphObject], Expansion]:
  '''
  Expand the protoconnectives of *model*'s net (see *planProtoconnectives()*):
  each is replaced by its members -- the net's nodes with their labels, or
  new ones of its SN type -- each linked as it was (see *EXPANDS*) and marked
  as it was.

  :param context: A view's *ModelContext*, to do it as one command (undone in
    one go); or None, to change the model as it is.
  :returns: The objects made (the nodes, then the links), and the plan.
  '''
  from util.attribute import Attribute, VAR
  plan = planProtoconnectives(model)
  if not plan.groups:
    return [], plan
  def make() -> list[GraphObject]:
    nodes:dict[str, Node] = {}
    def node(n:Node|str, like:Node) -> Node:
      if isinstance(n, Node):
        return n
      if n not in nodes:
        nodes[n] = Node(model, [like.getParents()[0]], individual=True, name=n)
      return nodes[n]
    like = {_key(m): g for g in plan.groups for m in plan.members[id(g)]}
    relations:list[GraphObject] = []
    for t, s, d, r in plan.links:
      relations.append(Relation(model, [t], node(s, like.get(_key(s), r.src)), node(d, like.get(_key(d), r.dst)),
                                individual=True))
    for m, key in plan.marks:
      n = node(m, like[_key(m)])
      local = n.getLocalAttr(key)
      if local is None or getattr(local, "inferred", False):
        n.setAttr(key, Attribute(ASSERTED, str, VAR))
    return [*nodes.values(), *relations]
  return _change(model, context, "expand protoconnectives", make, list(plan.groups)), plan

def _change(model:Model, context:Any, what:str, make:Callable[[], list[GraphObject]],
            remove:list[GraphObject]|None=None) -> list[GraphObject]:
  '''
  Make objects in *model* (and take others out), as one command if there's a
  view's *context* (see *forms._AddObjects*).

  :returns: The objects made.
  '''
  if context is None:
    ret = make()
    for o in remove or []:
      if o._isConnected():
        o._disconnect()
    model.setDirty()
    return ret
  return context.doList.do(_AddObjects(what, model, make, remove))

# ── Anonymous nodes ───────────────────────────────────────────────────────

def anonymousName(model:Model, taken:set[str]|None=None) -> str:
  '''
  :param taken: More names not to use (eg: those just made), as well as the model's nodes'.
  :returns: A name for a new anonymous node (see *ANONYMOUS*) that none of *model*'s nodes has.
  '''
  used = {str(o.name) for o in model.values() if isinstance(o, Node)} | (taken or set())
  k = 1
  while f"{ANONYMOUS} {k}" in used:
    k += 1
  return f"{ANONYMOUS} {k}"

def _anonymous(model:Model, like:Node, taken:set[str]) -> Node:
  ''':returns: A new anonymous node in *model*, of *like*'s SN type, drawn without a label (its name added to *taken*).'''
  n = Node(model, [like.getParents()[0]], individual=True, name=anonymousName(model, taken))
  taken.add(str(n.name))
  n["vis/label"] = ""
  return n

def linkType(model:Model, kind:str) -> Relation:
  '''
  :param kind: A kernel relation type's name (eg: *reader.INCLUDES*).
  :returns: The relation type for a new link of *kind* in *model*'s net: the
    one most of the net's links of that kind are (eg: its "Includes"), or the
    kernel's, if it has none.
  '''
  kernel = _kernel(model)
  counts = Counter(id(r.getParents()[0]) for r in netLinks(model) if [str(t.name) for t in kernelOf(r, kernel)] == [kind])
  types = {id(r.getParents()[0]): r.getParents()[0] for r in netLinks(model)}
  return types[counts.most_common(1)[0][0]] if counts else kernel[kind]

def addAnonymous(node:Node, below:bool=True, context:Any=None) -> list[GraphObject]:
  '''
  Gaines's single-node expansion (section 3.3): add an anonymous node -- an
  ideal element, of *node*'s SN type, drawn without a label -- linked to
  *node* by one inclusion (of the net's: see *linkType()*). With at most one
  link, it's an ultra-conservative merge: it says nothing new about the net,
  and taking it out again changes nothing.

  :param below: Whether it's below *node* (it includes *node*: something
    more specific), or above it (*node* includes it: something more general).
  :param context: A view's *ModelContext*, to do it as one command (undone in
    one go); or None, to add it to the model as it is.
  :returns: The node made, and its link.
  '''
  model = node.model
  t = linkType(model, INCLUDES)
  def make() -> list[GraphObject]:
    n = _anonymous(model, node, set())
    return [n, Relation(model, [t], n, node, individual=True) if below else Relation(model, [t], node, n, individual=True)]
  return _change(model, context, "add an anonymous node", make)

# ── Factoring ─────────────────────────────────────────────────────────────

FACTORS = (INCLUDES, EXCLUDES, COEXCLUDES)
'''
The kinds of link *factor()* factors: where each of some nodes (T) has one
to each of some others (H), it interpolates an anonymous node α --

  - includes (T includes H): T include α, and α includes H;
  - excludes: T include α, and α excludes H;
  - coexcludes: α includes T, and α coexcludes H

-- so each of T has the link to each of H still, through α (by the kernel's
patterns), and α could be any node between them: the import is
ultra-conservative.
'''

@dataclass
class Factor:
  '''One factoring (see *factor()*).'''
  kind:str
  "The links' kernel relation type's name (see *FACTORS*)."
  tails:list[Node]
  "T: the nodes each with a link to each of *heads*."
  heads:list[Node]
  "H."
  links:list[Relation]
  "The links it replaces."

  def saving(self) -> int:
    ''':returns: How many fewer links the net has for it.'''
    return len(self.links) - len(self.tails) - len(self.heads)

def _bicliques(edges:dict[int, set[int]]) -> list[frozenset[int]]:
  '''
  :param edges: Each node's (by id) neighbours (those it has a link to).
  :returns: The sets of at least two nodes that are all the neighbours some
    nodes share (the intents of their formal context), smallest first.
  '''
  found:set[frozenset[int]] = {frozenset(v) for v in edges.values() if len(v) >= 2}
  todo = list(found)
  while todo:
    a = todo.pop()
    for b in list(found):
      c = a & b
      if len(c) >= 2 and c not in found:
        found.add(c)
        todo.append(c)
  return sorted(found, key=lambda s: (len(s), sorted(s)))

def planFactors(model:Model) -> list[Factor]:
  '''
  :returns: The factorings *factor()* does in *model*'s net, in turn: each
    the one (of each kind, in *FACTORS*' order) that saves the most links --
    T and H at least two nodes each, and more links between them than
    there are nodes (the size of T times that of H is more than their sum) -- among the net's links not
    factored already. (Greedy: the fewest links in all may take others.)
  '''
  kernel = _kernel(model)
  links = netLinks(model)
  nodes = {id(n): n for n in netNodes(model)}
  order = {id(n): k for k, n in enumerate(netNodes(model))}
  ret:list[Factor] = []
  for kind in FACTORS:
    mine = [r for r in links if [str(t.name) for t in kernelOf(r, kernel)] == [kind]]
    symmetric = kind != INCLUDES
    used:set[int] = set()
    while True:
      edges:dict[int, set[int]] = {}
      for r in mine:
        if id(r) in used or r.src is r.dst:
          continue
        edges.setdefault(id(r.src), set()).add(id(r.dst))
        if symmetric:
          edges.setdefault(id(r.dst), set()).add(id(r.src))
      best:Factor|None = None
      for heads in _bicliques(edges):
        tails = [t for t in edges if heads <= edges[t]]
        if len(tails) < 2 or len(tails) * len(heads) <= len(tails) + len(heads):
          continue
        if best is not None and len(tails) * len(heads) - len(tails) - len(heads) <= best.saving():
          continue
        ts, hs = set(tails), set(heads)
        between = [r for r in mine if id(r) not in used
                   and ((id(r.src) in ts and id(r.dst) in hs) or (symmetric and id(r.src) in hs and id(r.dst) in ts))]
        f = Factor(kind, sorted((nodes[t] for t in tails), key=lambda n: order[id(n)]),
                   sorted((nodes[h] for h in heads), key=lambda n: order[id(n)]), between)
        if f.saving() > 0 and (best is None or f.saving() > best.saving()):
          best = f
      if best is None:
        break
      ret.append(best)
      used |= {id(r) for r in best.links}
  return ret

def factor(model:Model, context:Any=None) -> tuple[list[GraphObject], list[Factor]]:
  '''
  Factor *model*'s net (Gaines, section 3.4): interpolate an anonymous node
  (drawn without a label) for each factoring *planFactors()* finds, linked
  as *FACTORS* says, in place of the links it factors. (The net's own
  links of each kind, as *linkType()* chooses them; the factored links' type
  for those to H.)

  :param context: A view's *ModelContext*, to do it as one command (undone in
    one go); or None, to change the model as it is.
  :returns: The objects made (each anonymous node, then its links), and the factorings.
  '''
  plan = planFactors(model)
  if not plan:
    return [], plan
  inc = linkType(model, INCLUDES)
  def make() -> list[GraphObject]:
    ret:list[GraphObject] = []
    taken:set[str] = set()
    for f in plan:
      a = _anonymous(model, f.tails[0], taken)
      types = {id(r.getParents()[0]): r.getParents()[0] for r in f.links}
      t = types[Counter(id(r.getParents()[0]) for r in f.links).most_common(1)[0][0]]
      ret.append(a)
      if f.kind == COEXCLUDES:
        ret += [Relation(model, [inc], a, n, individual=True) for n in f.tails]
      else:
        ret += [Relation(model, [inc], n, a, individual=True) for n in f.tails]
      ret += [Relation(model, [t], a, n, individual=True) for n in f.heads]
    return ret
  return _change(model, context, "factor", make, [r for f in plan for r in f.links]), plan
