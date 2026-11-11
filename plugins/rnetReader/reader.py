'''
Make a Semantic Nets model of a Rep Plus net (see *rnet*), for *view* to
show (see *buildModel()*):

  - Each node type (section ``T``) becomes a node type (a kind of *node*) of
    the same name, with its shape and colours (see *NODE_SHAPES* and
    *NODE_COLORS*); one that's just its text (eg: "Title", "Note") has no
    outline or fill. A node with no type gets *UNTYPED*.
  - Each link type (section ``A``) becomes a relation type of the same name,
    drawn with its arrowheads, bars and middle symbol as relation marks (see
    *endMarks()* and *MID_MARKS*), in its colour (see *LINK_COLORS*), as a
    straight line, with no label: a derived one's colours are faded (CNet
    draws it dashed).
  - Each node (section ``N``) becomes an individual of its type, named by its
    label (its line breaks and all; one with no label has no name). Its mark,
    if it has one, becomes attributes -- "mark" (T, F or TF: true, false, or
    both), "markKind" (eg: "Asserted"), and "markDerived" (if it was
    propagated, rather than asserted) -- with "marks", the number as the file
    has it (in hexadecimal); and if it's shown (see *rnet.NetNode.marked*), its outline is
    thick, in the mark kind's colour, and its label says the mark (see
    *LABEL*). Pictures and drawings aren't made (they aren't concepts).
  - Each link (section ``L``) becomes a relation of each of its types from its
    source to its destination. Any more fields it has (eg: a weight) are in its
    "values" attribute.
  - Each group (section ``G``) becomes a collection, "group <n>" (numbered
    from 1, as they are in the file), whose members are its nodes and the
    groups in it.

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
import os
from dataclasses import dataclass, field
from pathlib import Path
from sn.model.model import Collection, Model, Node, Relation
from util.attribute import Attribute, VAR_DEFAULTED
from .rnet import Net, NetNode, NodeType, LinkType

NODE_SHAPES = {0: "Rectangle", 1: "Rectangle", 2: "Oval", 3: "RoundedRectangle"}
"A node type's shape (*rnet.NodeType.shape*) -> its shape here (\"vis/shape\"). A grid's (\"rgrid\") is a FileFolder."

NODE_COLORS = {"vis/fillColor": 1, "vis/textColor": 2, "vis/borderColor": 3}
'''Where a node type's colours go (which of its four, from 0): the second is
the fill and the third the text's (as CNet's SVG pictures of its nets show);
the fourth -- or the first: they're the same in every type in those
pictures -- the outline.'''

LINK_COLORS = {"vis/lineColor": 3}
'''Where a (version 9) link type's four colours go: the line's (and its marks')
is taken to be the fourth, as a node's outline is (eg: "Prefer", whose last
two are purple, was purple in the older files' link types). A link type
given by its bits (see *rnet.LinkType*) has two: the line's, and its marks'.'''

ARROW = "arrow"
"An arrowhead (pointing off the end it's at)."
HEAVY_ARROW = "arrow(11,13,6)"
"A heavy arrowhead (a conjunction's)."

MID_MARKS = {1: "|", 2: "||", 3: "|||", 4: "@", 6: ">"}
'''A link type's symbol in the middle (*rnet.LinkType.mid*) -> its middle marks:
the symmetric exclusion, coexclusion and negation (as one, two and three
bars, as their arrows have at the head), prohibited, preferred.'''

DERIVED_FADE = 0.5
"How far a derived link type's colour is faded toward white (CNet draws them dashed)."

MARK_WIDTH = 3
"The width of a marked node's outline (in its mark kind's colour)."

LABEL = "$name${mark:+ $mark}"
"Each node type's label template: the name, and the mark, if there is one (see the module doc)."

UNTYPED = "text"
"The node type made for nodes with none (eg: text the program wrote): just its text."

def endMarks(shape:int, bars:int, atSource:bool) -> str:
  '''
  :param shape: The end's head (see *rnet.LinkType.head*): 0 none, 1 an arrowhead, 2 a heavy one, 3 a double one.
  :param bars: How many bars there are behind the head.
  :param atSource: Whether it's the source's end (else the destination's).
  :returns: The relation marks for the end (see "vis/terminator1" and "vis/terminator4").
  '''
  head = {0: "", 1: ARROW, 2: HEAVY_ARROW, 3: "<<" if atSource else ">>"}.get(shape, ARROW)
  parts = [head, "|" * bars] if atSource else ["|" * bars, head] # (written from the source toward the destination)
  return " ".join(p for p in parts if p)

def fade(color:str, amount:float=DERIVED_FADE) -> str:
  '''
  :param color: "#rrggbb".
  :returns: It, faded toward white by *amount* (0: not at all; 1: white).
  '''
  if len(color) != 7:
    return color
  rgb = [int(color[i:i + 2], 16) for i in (1, 3, 5)]
  return "#" + "".join(f"{round(c + (255 - c) * amount):02x}" for c in rgb)

def note(text:str) -> Attribute:
  return Attribute(text, "text", VAR_DEFAULTED)

@dataclass
class Built:
  '''
  What *buildModel()* made of a net.
  '''
  net:Net
  model:Model
  nodeTypes:dict[int, Node] = field(default_factory=dict)
  "Each node type's place in the net -> its type (-1: *UNTYPED*, if it was needed)."
  linkTypes:dict[int, Relation] = field(default_factory=dict)
  "Each link type's place in the net -> its relation type."
  nodes:dict[int, Node] = field(default_factory=dict)
  "Each node's place in the net -> its individual (not the pictures and drawings)."
  relations:list[tuple[Relation, int]] = field(default_factory=list)
  "Each relation, and the place in the net of the link it's of."
  groups:dict[int, Collection] = field(default_factory=dict)
  "Each group's place in the net -> its collection."
  skipped:list[str] = field(default_factory=list)
  "What wasn't made, and why."

  def report(self) -> str:
    '''
    :returns: What was made, in a sentence or two.
    '''
    s = (f"{len(self.nodes)} nodes, {len(self.relations)} relations and {len(self.groups)} groups, of "
         f"{len(self.nodeTypes)} node types and {len(self.linkTypes)} relation types")
    marked = sum(1 for n in self.net.nodes if n.marks and n.index in self.nodes)
    if marked:
      s += f"; {marked} nodes have marks"
    if self.skipped:
      s += f". Left out: {'; '.join(self.skipped)}"
    return s + "."

def makeNodeType(m:Model, t:NodeType, file:str) -> Node:
  '''
  :returns: A new node type in *m* for the net's node type *t* (see the module doc).
  '''
  n = Node(m, [m.NODE], name=t.name or f"node type {t.index}")
  n["vis/shape"] = "FileFolder" if t.extra == "rgrid" else NODE_SHAPES.get(t.shape, "Rectangle")
  for key, i in NODE_COLORS.items():
    c = t.colors[i] if i < len(t.colors) and t.colors[i] else ""
    if key == "vis/borderColor" and not c and t.colors:
      c = t.colors[0]
    if c:
      n[key] = c
  if t.frameless:
    n["vis/fillColor"] = ""
    n["vis/borderColor"] = ""
  n["vis/label"] = LABEL
  n.setAttr("note", note(f"A node type of {file}: shape {t.shape} (variant {t.variant}), {t.font} {t.size} point, "
                         f"flags {t.flags}, colours {', '.join(c or '-' for c in t.colors)}"
                         + (f', for "{t.extra}" files' if t.extra else "") + "."))
  return n

def makeUntyped(m:Model, file:str) -> Node:
  '''
  :returns: A new *UNTYPED* type in *m*: just its text.
  '''
  n = Node(m, [m.NODE], name=UNTYPED)
  n["vis/fillColor"] = ""
  n["vis/borderColor"] = ""
  n["vis/label"] = LABEL
  n.setAttr("note", note(f"The nodes of {file} that have no type (eg: text the program wrote)."))
  return n

def makeLinkType(m:Model, t:LinkType, file:str) -> Relation:
  '''
  :returns: A new relation type in *m* for the net's link type *t* (see the module doc).
  '''
  r = Relation(m, [m.RELATION], None, None, name=t.name or f"link type {t.index}")
  r["vis/terminator1"] = endMarks(t.tail, t.tailBars, atSource=True)
  r["vis/terminator4"] = endMarks(t.head, t.headBars, atSource=False)
  r["vis/midMarks"] = MID_MARKS.get(t.mid, "") if t.mid else ""
  r["vis/label"] = ""
  r["vis/lineType"] = "straight"
  if t.bits is not None:
    color = t.colors[0] if t.colors and t.colors[0] else "#000000"
  else:
    i = LINK_COLORS["vis/lineColor"]
    color = (t.colors[i] if i < len(t.colors) else "") or (t.colors[0] if t.colors else "") or "#000000"
    if t.derived:
      color = fade(color)
  r["vis/lineColor"] = color
  r["vis/lineFillColor"] = color
  how = (f"bits {t.bits}" if t.bits is not None else
         f"head {t.head} with {t.headBars} bars, tail {t.tail} with {t.tailBars} bars, line {t.lineFlags}, middle {t.mid}")
  r.setAttr("note", note(f"A link type of {file}: {how}; colours {', '.join(c or '-' for c in t.colors)}"
                         + ("; derived (drawn dashed in CNet, faded here)" if t.derived else "") + "."))
  return r

def nodeName(n:NetNode) -> str:
  '''
  :returns: The name for the net's node *n*: its label.
  '''
  return n.label

def markNode(node:Node, n:NetNode, net:Net) -> None:
  '''
  Give *node* the mark of the net's node *n*, if it has one (see the module doc).
  '''
  if not n.marks:
    return
  node["marks"] = f"{n.marks:X}"
  if n.truth:
    node["mark"] = n.truth
  kind = net.markKinds[n.markKind] if n.markKind < len(net.markKinds) else None
  if kind is not None and (n.truth or n.marked):
    node["markKind"] = kind.name
  if n.derived:
    node["markDerived"] = True
  if n.marked:
    node["vis/borderWidth"] = MARK_WIDTH
    if kind is not None and kind.colors and kind.colors[0]:
      node["vis/borderColor"] = kind.colors[0]

def buildModel(net:Net, modelPath:str) -> Built:
  '''
  Make a model of *net* (as the module doc says), as a new model file
  *modelPath* (not saved: call its *save()*).

  :param net: A net (see *rnet.parse()*).
  :param modelPath: The model's file: it mustn't be open (nor, if it's there, in memory).
  :returns: What was made.
  '''
  file = os.path.basename(net.path) or "the net"
  m = Model(Path(modelPath).resolve().as_uri())
  b = Built(net, m)
  for t in net.nodeTypes:
    b.nodeTypes[t.index] = makeNodeType(m, t, file)
  for t in net.linkTypes:
    b.linkTypes[t.index] = makeLinkType(m, t, file)
  pictures = 0
  for n in net.nodes:
    if n.kind != "node":
      pictures += 1
      continue
    t = b.nodeTypes.get(n.type)
    if t is None:
      if -1 not in b.nodeTypes:
        b.nodeTypes[-1] = makeUntyped(m, file)
      t = b.nodeTypes[-1]
    node = Node(m, [t], individual=True, name=nodeName(n))
    if n.extra.strip():
      node["extra"] = n.extra
    markNode(node, n, net)
    b.nodes[n.index] = node
  if pictures:
    b.skipped.append(f"{pictures} pictures and drawings")
  missing = 0
  for l in net.links:
    src, dst = b.nodes.get(l.source), b.nodes.get(l.destination)
    if src is None or dst is None:
      missing += 1
      continue
    for t in dict.fromkeys(l.types): # (once each: some links list a type twice)
      typ = b.linkTypes.get(t)
      if typ is None:
        continue
      r = Relation(m, [typ], src, dst, individual=True)
      if l.extra:
        r["values"] = " ".join(l.extra)
      b.relations.append((r, l.index))
  if missing:
    b.skipped.append(f"{missing} links to pictures, drawings or nodes that aren't there")
  for g in net.groups:
    b.groups[g.index] = Collection(m, [m.COLLECTION], [], individual=True, name=f"group {g.index + 1}")
  for g in net.groups:
    c = b.groups[g.index]
    for i in g.nodes:
      if i in b.nodes:
        c.addMember(b.nodes[i])
    for i in g.groups:
      if i in b.groups and i != g.index:
        c.addMember(b.groups[i])
  return b
