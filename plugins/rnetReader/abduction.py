'''
KNet's abductive inference ("Abductive Inference", on a node's menu): what
must hold if a node is true, whatever explains it. Its explanations are the
bottom nodes below it -- found going down the links that include it (and
those that include them, and so on) through nodes with no mark yet, to
nodes nothing includes -- and each is a world: the net with that node true.
What the net's nodes with no mark yet are marked in every world, the same
way, is abduced (Gaines: the disjuncts of what's true are the candidate
states of affairs; see *abduce()*).

As KNet does: each world's marks are the kernel's propagation from the
net's marks with the explanation true -- by any engine (see
*sn.model.reasoner.Reasoner.worlds()*); an explanation that makes a node
both true and false is a world all the same (its incoherent marks are
common to every world, or not abduced); and the marks abduced are
inferences (*ABDUCED*), gone at the next "reason" -- KNet's are, at its next
inference.

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
from dataclasses import dataclass, field
from sn.model.model import Model, Node, Relation, IsaIndividual
from sn.model.reasoner import Reasoner, Inferences
from .reader import INCLUDES, SAME_LABEL
from .forms import _kernel, _netName
from .probes import netNodes, name
from .hooks import MARK_TRUE, MARK_FALSE, ASSERTED

ABDUCED = "abduced"
"How a node got a mark *abduce()* gives it (see *hooks.MARK_TRUE*): drawn as KNet draws them, as defaults."

KEYS = {"T": MARK_TRUE, "F": MARK_FALSE}
"The mark attribute of each truth value's letter."

@dataclass
class Abduction:
  '''What abducing from a node finds (see *abduce()*).'''
  node:Node
  "The node abduced from."
  net:str
  "Its net's name."
  explanations:list[Node] = field(default_factory=list)
  "The bottom nodes below it (see *explanations()*): each a world."
  worlds:list[dict[int, str]] = field(default_factory=list)
  "Each one's marks (by node id): \"T\", \"F\" or \"TF\" -- of the nodes with no mark to start with."
  abduced:dict[int, str] = field(default_factory=dict)
  "The marks the same in every world (by node id)."
  nodes:dict[int, Node] = field(default_factory=dict)
  "The net's nodes, by id."

  def report(self) -> str:
    ''':returns: What it found, as text.'''
    n = name(self.node)
    if not self.explanations:
      return f"Abduction from {n} in {self.net}: nothing explains it."
    lines = [f"Abduction from {n} in {self.net}: {len(self.explanations)} explanation"
             f"{'' if len(self.explanations) == 1 else 's'} ({', '.join(name(e) for e in self.explanations)})"]
    if not self.abduced:
      lines.append("  nothing's the same in every one")
    for x, tv in self.abduced.items():
      lines.append(f"  {name(self.nodes[x])} {_says(tv)}")
    return "\n".join(lines)

def _says(tv:str) -> str:
  ''':returns: What a truth value's letters (see *Abduction.worlds*) say: eg, "true".'''
  return {"T": "true", "F": "false", "TF": "both true and false"}.get(tv, "unmarked")

def _given(n:Node) -> str:
  ''':returns: The marks *n* has of its own (not inferred: asserted ones), as letters (see *Abduction.worlds*).'''
  return "".join(v for v, k in KEYS.items() if (a := n.getLocalAttr(k)) is not None and not getattr(a, "inferred", False))

def _marks(res:Inferences, nodes:dict[int, Node], supposed:Node|None=None) -> dict[int, str]:
  '''
  :param res: A run's results.
  :param supposed: The node supposed true in it, if any.
  :returns: The marks of *nodes* (by id) in it -- their own, the rules', and
    the supposition's -- as letters (see *Abduction.worlds*); none, for one with none.
  '''
  got:dict[int, set[str]] = {x: set(_given(n)) for x, n in nodes.items()}
  for _, x, k, _v in res.ruleAttrs:
    if isinstance(x, Node) and id(x) in got:
      got[id(x)] |= {v for v, key in KEYS.items() if key == k}
  if supposed is not None and id(supposed) in got:
    got[id(supposed)].add("T")
  return {x: "".join(v for v in "TF" if v in s) for x, s in got.items() if s}

def _sameLabel(r:Relation) -> bool:
  ''':returns: Whether *r* is one of the reader's same-label equivalences (see *reader.addSameLabels()*).'''
  return any(str(t.name) == SAME_LABEL for t in r.isa() if isinstance(t, Relation))

def explanations(model:Model, node:Node, marks:dict[int, str]) -> list[Node]:
  '''
  KNet's bottom nodes below *node*: going down each link that includes it
  (asserted: of the kernel's includes, or an SN subtype -- eg, an
  equivalence, or a connective's defining inclusion), from the node that
  includes it, if that has no mark (see *marks*), and on; a node no link
  includes is a bottom node (*node* itself, if none includes it). Nodes with
  the same label (see *reader.addSameLabels()*) are one node, as they're
  KNet's.

  :param marks: The nodes' marks, by id (see *Abduction.worlds*).
  :returns: The bottom nodes, in the order they're found.
  '''
  kernel = _kernel(model)
  inc = kernel.get(INCLUDES)
  nodes = {id(n): n for n in netNodes(model)}
  same:dict[int, int] = {x: x for x in nodes}
  def root(x:int) -> int:
    while same[x] != x:
      x = same[x]
    return x
  back:dict[int, list[Node]] = {}
  for r in model.values():
    if not isinstance(r, Relation) or isinstance(r, IsaIndividual) or r.model is not model or not r.isIndividual() \
       or getattr(r, "inferred", False) or id(r.src) not in nodes or id(r.dst) not in nodes or r.src is r.dst:
      continue
    if _sameLabel(r):
      same[root(id(r.src))] = root(id(r.dst))
    elif inc is not None and r.isa(inc):
      back.setdefault(id(r.dst), []).append(r.src)
  members:dict[int, list[int]] = {}
  for x in nodes:
    members.setdefault(root(x), []).append(x)
  ret:list[Node] = []
  seen:set[int] = set()
  def down(n:Node) -> None:
    g = root(id(n))
    if g in seen:
      return
    seen.add(g)
    srcs = [s for x in members[g] for s in back.get(x, []) if root(id(s)) != g]
    if not srcs:
      ret.append(n)
    for s in srcs:
      if not marks.get(id(s)):
        down(s)
  if id(node) in nodes:
    down(node)
  return ret

def abduce(model:Model, node:Node, engine:str|None=None) -> Abduction:
  '''
  Abduce from *node* (see the module doc): the net reasoned over as it is,
  and once for each explanation (see *explanations()*), with it true.

  :param engine: The reasoner engine (by default, the setting's).
  :returns: What it found.
  '''
  nodes = {id(n): n for n in netNodes(model)}
  ret = Abduction(node, _netName(model) or str(model.name), nodes=nodes)
  reasoner = Reasoner.create(model, engine)
  start = _marks(reasoner.run(), nodes)
  ret.explanations = explanations(model, node, start)
  suppose = lambda e: [] if "T" in _given(e) else [("lattr", (e, MARK_TRUE)), ("attr", (e, MARK_TRUE, ASSERTED))]
  results = reasoner.worlds([suppose(e) for e in ret.explanations])
  open_ = [x for x in nodes if x not in start]
  for e, res in zip(ret.explanations, results):
    marks = _marks(res, nodes, e)
    ret.worlds.append({x: marks[x] for x in open_ if x in marks})
  if ret.worlds:
    for x in open_:
      tvs = {w.get(x, "") for w in ret.worlds}
      if len(tvs) == 1 and (tv := tvs.pop()):
        ret.abduced[x] = tv
  return ret

def markAbduced(found:Abduction) -> list[tuple[Node, str]]:
  '''
  Give the nodes what *abduce()* found: each mark abduced, as an inference
  (see *ABDUCED*) -- the next "reason" takes it out (unless the rules give
  the node that mark then). As what's inferred, it doesn't change the model
  (it isn't saved: see *Model.inferring()*).

  :returns: The marks given: (the node, the mark's key).
  '''
  from util.attribute import Attribute, Restriction
  ret = []
  with found.node.model.inferring():
    for x, tv in found.abduced.items():
      n = found.nodes[x]
      for v in tv:
        key = KEYS[v]
        if n.getLocalAttr(key) is None:
          n.setAttr(key, Attribute(ABDUCED, str, Restriction.fromstring("VAR"), inferred=True))
          ret.append((n, key))
  return ret
