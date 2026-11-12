'''
Gaines's probes of a KNet net, as KNet's "Probes", "Probe Sets" and
"Reconstruct" commands give them: each probe is a way the net's nodes can be
marked -- true, false or both -- that its rules allow (see
*sn.model.clingoReasoner.ClingoReasoner.probes()*, and *PROBE_KINDS*:
consistent, admissible or compatible probes); a node's probe sets are the
probes it's true in and those it's false in; and the reconstruction is the
links that the probe sets say hold: A includes B if B is true in every
probe A is, and A false in every probe B is; A excludes B if each is false
in every probe the other's true in; and A coexcludes B if each is true in
every probe the other's false in.

  - *netNodes()*: the net's nodes (its *KNODE* individuals that KNet reasons
    about);
  - *findProbes()*: their probes, part by part (nodes that aren't linked have
    every combination of their probes: so each connected part's are found on
    their own);
  - *reconstruct()*: the reconstruction -- across the parts too;
  - *report()*: all three, as text, as KNet writes them;
  - *ProbesDialog*: shows the report, from a node's menu (see
    *hooks.showProbes()*).

Created on Nov 11, 2026

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
from sn.model.model import Model, Node, Relation
from sn.model.reasoner import Reasoner, probingEngine, PROBE_KINDS, PROBE_LIMIT, CONSISTENT
from .hooks import MARK_TRUE, MARK_FALSE
from .reader import KNODE, KNET_NODE

SYMBOLS = {"F": "−", "T": "|", "TF": "+"}
"How a probe shows each node's mark (as KNet does): ``−A`` false, ``|A`` true, ``+A`` both."

INCLUDES, INCLUDED, EXCLUDES, COEXCLUDES = "-->", "<--", "-|-", "-||-"
'''The links a reconstruction finds (see *reconstruct()*), as KNet writes them:
``A --> B`` (A includes B), ``A <-- B`` (B includes A), ``A -|- B`` (A
excludes B), and ``A -||- B`` (A coexcludes B).'''

@dataclass
class Part:
  '''Nodes that are linked (see *parts()*), and their probes.'''
  nodes:list[Node]
  "The nodes, by name."
  probes:list[dict[Node, str]] = field(default_factory=list)
  'Each probe: each node\'s mark in it -- "T", "F" or "TF" (both).'

@dataclass
class Probes:
  '''What *findProbes()* found.'''
  kind:str
  "Which probes (see *PROBE_KINDS*)."
  parts:list[Part]
  "The net's parts' (see *parts()*): a probe of the whole net is one of each part's."

  def count(self) -> int:
    ''':returns: How many probes the whole net has: the product of its parts'.'''
    ret = 1
    for p in self.parts:
      ret *= len(p.probes)
    return ret

def name(n:Node) -> str:
  ''':returns: *n*'s name, on one line.'''
  return " ".join(str(n.name or "").split())

def netNodes(model:Model) -> list[Node]:
  '''
  :returns: The nodes of *model*'s net, by name: its own individuals that are
    *KNODE*\\ s -- not the reasoner's, the patterns' (eg: a rule's), or those
    of an SN type whose *KNET_NODE* is False (eg: notes).
  '''
  knode = _knode(model)
  if knode is None:
    return []
  ret = [o for o in model.values()
         if o.model is model and isinstance(o, Node) and o.isIndividual() and not getattr(o, "inferred", False)
         and not o.isVariable() and not o.isPatternElement() and o.isa(knode)
         and all(t.get(KNET_NODE, True) is not False for t in o.isa() if isinstance(t, Node))]
  return sorted(ret, key=lambda n: (name(n).lower(), name(n)))

def _knode(model:Model) -> Node|None:
  ''':returns: *KNODE*, in *model* or a model it's built on (eg: knet.snm), if it's there.'''
  seen:set[int] = set()
  todo:list[Any] = [model]
  while todo:
    m = todo.pop(0)
    if id(m) in seen or not isinstance(m, Model):
      continue
    seen.add(id(m))
    found = next((o for o in m.values() if o.model is m and isinstance(o, Node) and o.isType() and o.name == KNODE), None)
    if found is not None:
      return found
    todo.extend(m.superDBs)
  return None

def parts(model:Model, nodes:list[Node]) -> list[list[Node]]:
  '''
  :returns: *nodes* in parts: those that relations (of any SN type) join, in
    the order of their first nodes.
  '''
  where = {id(n): i for i, n in enumerate(nodes)}
  parent = list(range(len(nodes)))
  def find(i:int) -> int:
    while parent[i] != i:
      parent[i] = parent[parent[i]]
      i = parent[i]
    return i
  for r in model.values():
    if isinstance(r, Relation) and r.model is model and r.isIndividual():
      a, b = where.get(id(r.src)), where.get(id(r.dst))
      if a is not None and b is not None:
        parent[find(a)] = find(b)
  ret:dict[int, list[Node]] = {}
  for i, n in enumerate(nodes):
    ret.setdefault(find(i), []).append(n)
  return list(ret.values())

def findProbes(model:Model, kind:str=CONSISTENT, engine:str|None=None, limit:int=PROBE_LIMIT) -> Probes:
  '''
  :param kind: Which probes (see *PROBE_KINDS*).
  :param engine: The reasoner engine to find them with (one that can: see
    *probingEngine()*, the default).
  :param limit: The most probes of a part to find.
  :returns: The probes of *model*'s net (see *netNodes()*), part by part (see *parts()*).
  :raises TooManyProbes: If a part has more than *limit*.
  :raises EngineMissing: If the engine isn't installed.
  :raises ValueError: If *kind* isn't one of *PROBE_KINDS*.
  '''
  if kind not in PROBE_KINDS:
    raise ValueError(f'There\'s no "{kind}" kind of probe: the kinds are {", ".join(PROBE_KINDS)}.')
  reasoner:Any = Reasoner.create(model, engine or probingEngine())
  found = Probes(kind, [Part(p) for p in parts(model, netNodes(model))])
  order = {"F": 0, "T": 1, "TF": 2, "": 3}
  for part in found.parts:
    part.probes = sorted(reasoner.probes(part.nodes, MARK_TRUE, MARK_FALSE, kind, limit=limit),
                         key=lambda p, nodes=part.nodes: [order[p[n]] for n in nodes])
  return found

def probeSets(part:Part) -> tuple[dict[int, set[int]], dict[int, set[int]]]:
  '''
  :returns: The probes (their places in *part*) each node (by id) is true in, and those it's false in.
  '''
  true = {id(n): {i for i, p in enumerate(part.probes) if "T" in p[n]} for n in part.nodes}
  false = {id(n): {i for i, p in enumerate(part.probes) if "F" in p[n]} for n in part.nodes}
  return true, false

def reconstruct(found:Probes) -> dict[Node, list[tuple[str, Node]]]:
  '''
  :returns: The links the probes say hold (see the module doc, and
    *INCLUDES* ...): each node's, to each node (in *netNodes()*'s order) --
    none to itself but an exclusion or coexclusion (an inconsistent node's).
    Between nodes of two parts, whose probes are every combination of
    theirs, a set includes another if it's empty or the other's every probe.
  '''
  sets = [probeSets(p) for p in found.parts]
  where = {id(n): k for k, p in enumerate(found.parts) for n in p.nodes}
  nodes = sorted((n for p in found.parts for n in p.nodes), key=lambda n: (name(n).lower(), name(n)))
  def contains(a:set[int], ka:int, b:set[int], kb:int) -> bool: # (whether a, of part ka, includes b, of part kb, in the whole net's probes)
    if ka == kb:
      return a >= b
    return not b or len(a) == len(found.parts[ka].probes)
  ret:dict[Node, list[tuple[str, Node]]] = {}
  for p in nodes:
    kp = where[id(p)]
    pt, pf = sets[kp][0][id(p)], sets[kp][1][id(p)]
    for c in nodes:
      kc = where[id(c)]
      ct, cf = sets[kc][0][id(c)], sets[kc][1][id(c)]
      ops = []
      if c is not p and contains(ct, kc, pt, kp) and contains(pf, kp, cf, kc):
        ops.append(INCLUDES)
      if c is not p and contains(pt, kp, ct, kc) and contains(cf, kc, pf, kp):
        ops.append(INCLUDED)
      if contains(pf, kp, ct, kc) and contains(cf, kc, pt, kp):
        ops.append(EXCLUDES)
      if contains(pt, kp, cf, kc) and contains(ct, kc, pf, kp):
        ops.append(COEXCLUDES)
      ret.setdefault(p, []).extend((op, c) for op in ops)
  return ret

def report(found:Probes, title:str="") -> str:
  '''
  :param title: What the probes are of (eg: the net's name).
  :returns: *found* as KNet writes its probes: each part's probes (each node
    marked as *SYMBOLS* says), and probe sets (true in, false in); and the
    reconstruction (see *reconstruct()*).
  '''
  kind = found.kind.capitalize()
  lines = [f"{kind} probes{' of ' + title if title else ''}: {found.count()}"]
  if not found.parts:
    return lines[0] + "\n\nThe net has no nodes."
  for k, part in enumerate(found.parts, 1):
    lines.append("")
    if len(found.parts) > 1:
      lines.append(f"Part {k} of {len(found.parts)}: {', '.join(name(n) for n in part.nodes)}")
    width = len(str(len(part.probes)))
    lines.append(f"{kind} probes/coprobes" if part.probes else f"{kind} probes/coprobes: none")
    for i, p in enumerate(part.probes, 1):
      lines.append(f"  {i:>{width}}: " + " ".join(SYMBOLS.get(p[n], "?") + name(n) for n in part.nodes))
    if part.probes:
      true, false = probeSets(part)
      lines.append("")
      lines.append(f"{kind} probe sets (true in, false in)")
      for n in part.nodes:
        show = lambda s: "{" + ",".join(str(i + 1) for i in sorted(s)) + "}"
        lines.append(f"  {name(n)}  {show(true[id(n)])} {show(false[id(n)])}")
  lines.append("")
  lines.append(f"Reconstruction from {found.kind} probes/coprobes")
  for n, links in reconstruct(found).items():
    by:dict[int, list[str]] = {}
    for op, c in links:
      by.setdefault(id(c), []).append(op)
    seen:dict[int, Node] = {id(c): c for _, c in links}
    lines.append(f"  {name(n)}: " + ", ".join(" ".join(ops) + " " + name(seen[k]) for k, ops in by.items()))
  return "\n".join(lines)

class ProbesDialog:
  '''
  A window showing the report (see *report()*) of a model's probes: which
  kind (see *PROBE_KINDS*), the report (which can be copied), and "Close".
  '''
  def __init__(self, parent:Any, model:Model, kind:str=CONSISTENT, title:str=""):
    '''
    :param parent: The window it's for (eg: the view's).
    :param model: The net's model.
    :param kind: The kind of probe to show first.
    :param title: What the probes are of (eg: the net's name).
    '''
    import tkinter as tk
    from tkinter import ttk
    from tkinter.scrolledtext import ScrolledText
    from util.utils import ownDialog
    self.model, self.title = model, title
    self.top = top = tk.Toplevel(parent)
    ownDialog(top, parent, keep=False)
    top.title(f"Probes{': ' + title if title else ''}")
    frame = ttk.Frame(top, padding=10)
    frame.pack(fill=tk.BOTH, expand=True)
    kinds = ttk.Frame(frame)
    kinds.pack(fill=tk.X)
    self.kind = tk.StringVar(value=kind)
    for k in PROBE_KINDS:
      ttk.Radiobutton(kinds, text=k.capitalize(), value=k, variable=self.kind, command=self.refresh).pack(side=tk.LEFT, padx=6)
    self.text = ScrolledText(frame, width=72, height=28, wrap=tk.NONE, font="TkFixedFont")
    self.text.pack(fill=tk.BOTH, expand=True, pady=(8, 8))
    bottom = ttk.Frame(frame)
    bottom.pack(fill=tk.X)
    ttk.Button(bottom, text="Close", command=top.destroy, default="active").pack(side=tk.RIGHT, padx=6)
    ttk.Button(bottom, text="Copy", command=self.copy).pack(side=tk.RIGHT, padx=6)
    top.bind("<Escape>", lambda _e: top.destroy())
    self.refresh()
    top.lift()
    top.focus_force()

  def refresh(self) -> None:
    '''Find the probes of the kind chosen, and show their report (or why they can't be found).'''
    from sn.model.reasoner import TooManyProbes, EngineMissing
    self.top.config(cursor="watch")
    self.top.update_idletasks()
    try:
      text = report(findProbes(self.model, self.kind.get()), self.title)
    except TooManyProbes as ex:
      text = f"{ex} Probes of nodes that aren't linked are every combination of theirs: try a smaller net."
    except EngineMissing as ex:
      text = str(ex)
    finally:
      self.top.config(cursor="")
    self.text.config(state="normal")
    self.text.delete("1.0", "end")
    self.text.insert("1.0", text)
    self.text.config(state="disabled")

  def copy(self) -> None:
    '''Put the report on the clipboard.'''
    self.top.clipboard_clear()
    self.top.clipboard_append(self.text.get("1.0", "end-1c"))
