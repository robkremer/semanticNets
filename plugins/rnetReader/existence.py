'''
The existential status of a KNet net's nodes: Gaines's five senses in which
what a node stands for exists (section 3.5) --

  - conceptual: it's a node of the net (each is);
  - logical: it's consistent (it has no inconsistent link: see the kernel's
    *inconsistent*);
  - categorical: it's specified to be essentially a top node (a maximally
    generic entity);
  - singular: it's specified to be essentially a bottom node (a single
    entity);
  - situated: it's a bottom node within a universe of discourse -- here, the
    net's: nothing in the net but what's equivalent to it includes it.

Whether a node is essentially top or bottom isn't something the net's links
say: Gaines has it specified, by "extra-logical or metalogical constraints".
Here it's the node's *EXISTENCE* attribute (see *specify()*), and where the
net's links disagree with it -- something includes an essentially bottom
node, or an essentially top one includes something -- the report says so.

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
from typing import Any
from sn.model.model import Model, Node
from sn.model.reasoner import Reasoner
from .reader import INCLUDES, EQUIVALENT, INCONSISTENT
from .forms import _kernel, _netName
from .probes import netNodes, name

EXISTENCE = "existence"
"A node's attribute specifying what it essentially is: *TOP* or *BOTTOM* (see *specify()*)."

TOP, BOTTOM = "top", "bottom"
"The values of *EXISTENCE*: essentially a top node (categorical existence), or a bottom one (singular existence)."

SENSES = ("conceptual", "logical", "categorical", "singular", "situated")
"Gaines's senses of existence, in his order."

@dataclass
class Status:
  '''A node's existential status (see *status()*).'''
  node:Node
  consistent:bool
  "Whether it has no inconsistent link (logical existence)."
  above:list[str] = field(default_factory=list)
  "The nodes it includes (in the net, and not equivalent to it), by name: none, it's a top node of the net."
  below:list[str] = field(default_factory=list)
  "The nodes that include it (likewise): none, it's a bottom node of the net (situated existence)."
  specified:str|None = None
  "What it's specified to be (its *EXISTENCE*: *TOP*, *BOTTOM*), if anything."

  def senses(self) -> dict[str, bool]:
    ''':returns: For each of *SENSES*, whether it exists in that sense.'''
    return {"conceptual": True, "logical": self.consistent, "categorical": self.specified == TOP,
            "singular": self.specified == BOTTOM, "situated": not self.below}

  def conflicts(self) -> list[str]:
    ''':returns: Where the net's links disagree with what it's specified to be (each a sentence).'''
    n = name(self.node)
    if self.specified == TOP and self.above:
      return [f"{n} is specified to be essentially top, but it includes {', '.join(self.above)}."]
    if self.specified == BOTTOM and self.below:
      return [f"{n} is specified to be essentially bottom, but {', '.join(self.below)} include{'s' if len(self.below) == 1 else ''} it."]
    return []

def specified(n:Node) -> str|None:
  ''':returns: What *n* is specified to be (its *EXISTENCE*, if it's *TOP* or *BOTTOM*), or None.'''
  v = n.get(EXISTENCE, None)
  return v if v in (TOP, BOTTOM) else None

def specify(n:Node, what:str|None, context:Any=None) -> None:
  '''
  Specify what *n* essentially is: its *EXISTENCE*.

  :param what: *TOP*, *BOTTOM*, or None (not specified: the attribute taken out).
  :param context: A view's *ModelContext*, to do it as one command (undone); or None, to change *n* as it is.
  '''
  from util.attribute import Attribute, VAR
  if what not in (TOP, BOTTOM, None):
    raise ValueError(f'What a node essentially is is "{TOP}" or "{BOTTOM}", not "{what}".')
  local = n.getLocalAttr(EXISTENCE)
  if what is None:
    if local is not None:
      context.delete_attribute(n, EXISTENCE) if context is not None else n.__delitem__(EXISTENCE)
  elif local is None or local.value != what:
    a = Attribute(what, str, VAR)
    context.set_attribute(n, EXISTENCE, a) if context is not None else n.setAttr(EXISTENCE, a)

def status(model:Model, engine:str|None=None) -> list[Status]:
  '''
  :param engine: The reasoner engine (by default, the setting's).
  :returns: The existential status of each node of *model*'s net (see
    *probes.netNodes()*), in their order: what the kernel's links (asserted
    and inferred) say of it, and what it's specified to be.
  '''
  kernel = _kernel(model)
  nodes = netNodes(model)
  ids = {id(n) for n in nodes}
  inc, equ, bad = kernel.get(INCLUDES), kernel.get(EQUIVALENT), kernel.get(INCONSISTENT)
  includes:dict[int, set[int]] = {}
  equivalent:set[tuple[int, int]] = set()
  inconsistent:set[int] = set()
  for t, s, d in Reasoner.create(model, engine).run().holds:
    if id(s) not in ids or id(d) not in ids:
      continue
    if t is inc and s is not d:
      includes.setdefault(id(s), set()).add(id(d))
    elif t is equ:
      equivalent |= {(id(s), id(d)), (id(d), id(s))}
    elif t is bad:
      inconsistent.add(id(s))
  byId = {id(n): n for n in nodes}
  names = lambda xs: [name(byId[x]) for x in sorted(xs, key=lambda x: nodes.index(byId[x]))]
  ret = []
  for n in nodes:
    above = {d for d in includes.get(id(n), set()) if (id(n), d) not in equivalent}
    below = {s for s, ds in includes.items() if id(n) in ds and (s, id(n)) not in equivalent}
    ret.append(Status(n, id(n) not in inconsistent, names(above), names(below), specified(n)))
  return ret

def report(model:Model, engine:str|None=None) -> str:
  '''
  :returns: The existential status of *model*'s net's nodes (see *status()*),
    as text: a table of the senses each exists in, and where the net
    disagrees with what's specified.
  '''
  found = status(model, engine)
  net = _netName(model) or str(model.name)
  lines = [f"Existence in {net}", "",
           "Gaines's senses (section 3.5): conceptual (a node of the net); logical (consistent); categorical",
           "(specified to be essentially top); singular (specified to be essentially bottom); situated (a",
           "bottom node of the net: nothing in it but what's equivalent includes it).", ""]
  if not found:
    return "\n".join(lines + ["The net has no nodes."])
  width = max(len("node"), *(len(name(s.node)) for s in found))
  lines.append(f"{'node':<{width}}  " + "  ".join(SENSES))
  for s in found:
    senses = s.senses()
    lines.append(f"{name(s.node):<{width}}  " + "  ".join(f"{'yes' if senses[k] else '-':<{len(k)}}" for k in SENSES).rstrip())
  conflicts = [c for s in found for c in s.conflicts()]
  lines += ["", "Where the net disagrees with what's specified:"] + ([f"  {c}" for c in conflicts] or ["  nowhere"])
  return "\n".join(lines)
