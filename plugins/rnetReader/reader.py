'''
Make a Semantic Nets model of a Rep Plus net (see *rnet*), for *view* to
show (see *buildModel()*), built on *ONTOLOGY* (the kernel of Gaines's
protologic, so that the reasoners draw KNet's inferences):

  - Each node type (section ``T``) becomes a node type (an SN subtype of
    *KNODE*: a KNet node, with its truth marks' bars and menu items -- see
    *hooks*) of the same name, with its shape and colours (see *NODE_SHAPES* and
    *NODE_COLORS*); one that's just its text (eg: "Title", "Note") has no
    outline or fill. A node with no type gets *UNTYPED*. One with the
    enclosure shape (*ENCLOSURE*: eg, "construct", "frame", "rules") becomes
    an SN subtype of context instead, that doesn't quote what it contains (see
    *GraphObject.quotesContents()*): its nodes are boxes of facts -- but one
    of no size (an invisible end of links CNet draws, eg: in a drawing) is a
    *POINT*, with its type's name in its "rnetType" attribute.
  - Each link type (section ``A``) becomes a relation type of the same name,
    drawn with its arrowheads, bars and middle symbol as relation marks (see
    *endMarks()* and *MID_MARKS*), in its colour (see *LINK_COLORS*), as a
    straight line, with no label: a dashed one's colours are faded. It's an
    SN subtype of the kernel relation type its look says it is (see
    *kernelKind()*: eg, an arrow is includes, an arrow with a bar excludes),
    if any -- or of the connective's, if it has a heavy or a double
    arrowhead (see *connectiveKind()*: eg, "Conjunct includes"), whose links
    define a conjunction or a disjunction (Gaines's structural
    connectives). One drawn backwards -- its arrow at its tail (eg: "Includes
    reverse") -- is drawn the other way round instead: its arrow at its
    destination, and its links from the file's destination to its source
    (see *isReversed()*), so that it means what it shows.
  - Each node (section ``N``) becomes an individual of its type, named by its
    label (its line breaks and all; one with no label has no name). Its mark,
    if it has one, becomes attributes -- "mark" (T, F or TF: true, false, or
    both), "markKind" (eg: "Asserted"), and "markDerived" (if it was
    inferred, rather than asserted) -- with "marks", the number as the file
    has it (in hexadecimal), and its label says the mark (see *LABEL*). It's
    drawn as Rep Plus draws it (see *rnet.NetNode*): filled with the mark
    kind's background colour, and its outline in the kind's colour, if the
    mark says so. An asserted mark is the node's truth mark, too, which the
    reasoners propagate: *hooks.MARK_TRUE* and/or *hooks.MARK_FALSE*, saying
    its kind (eg: "asserted"), shown as Gaines's bars. (A derived one isn't:
    it's what the reasoners conclude again.) Pictures and drawings aren't
    made (they aren't concepts).
  - Each link (section ``L``) becomes a relation of its type from its source
    to its destination -- and one of its second type, if it has one, back
    from its destination to its source (see *rnet.Link*) -- or the other way,
    for a reversed type (as it's drawn). Any more fields it has (eg: a weight)
    are in its "values" attribute. Derived links (CNet's or KNet's
    inferences: see *rnet.LinkType.derived*) are made as they are: they're
    what the reasoners infer anyway.
  - Each box (a node of an enclosure type) contains -- by "contains"
    relations -- the nodes whose centres are inside it, and the smaller boxes
    that are: each in the smallest box it's in (CNet lists them nowhere: it's
    where they are).
  - A construct box's poles (the nodes it contains) exclude each other, as
    CNet's construct macro says, unless an includes link (or a chain of them)
    joins them: each pair gets a relation of *CONSTRUCT_EXCLUDES*, an SN
    subtype of the net's own symmetric exclusion, faded as derived links are
    (see *addConstructMeaning()*).
  - Groups (section ``G``) aren't made: in Rep Plus they're only a way to
    select and drag nodes together, with no meaning (and they'd fight the
    layouts).

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
from sn.model.model import GraphObject, Model, Node, Relation
from util.attribute import Attribute, VAR_DEFAULTED
from .rnet import Net, NetNode, NodeType, LinkType
from .hooks import MARK_TRUE, MARK_FALSE, ASSERTED

ONTOLOGY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "knet.snm")
'''The model the models made build on: the kernel of Gaines's protologic -- its
relation types (*KERNEL*) and inference patterns, as rules (made by
tools/makeKnetRules.py, whose doc says what they are).'''

INCLUDES, EQUIVALENT, EXCLUDES, COEXCLUDES, NEGATES, INCONSISTENT = \
  "includes", "equivalent", "excludes", "coexcludes", "negates", "inconsistent"
KERNEL = (INCLUDES, EQUIVALENT, EXCLUDES, COEXCLUDES, NEGATES, INCONSISTENT)
"The kernel relation types' names, in *ONTOLOGY*."

CONJUNCT_INCLUDES, CONJUNCT_EXCLUDES, DISJUNCT_INCLUDES, DISJUNCT_COEXCLUDES = \
  "conjunct includes", "conjunct excludes", "disjunct includes", "disjunct coexcludes"
CONNECTIVES = {(2, 0): CONJUNCT_INCLUDES, (2, 1): CONJUNCT_EXCLUDES, (3, 0): DISJUNCT_INCLUDES, (3, 2): DISJUNCT_COEXCLUDES}
'''The structural connectives' relation types, in *ONTOLOGY* (SN subtypes of
the kernel's: see tools/makeKnetRules.py), by the arrowhead (a heavy one, a
conjunction's; a double one, a disjunction's: *rnet.LinkType.head*) and its
bars: see *connectiveKind()*.'''

KNODE = "knode"
"The SN type of a KNet net's nodes, in *ONTOLOGY*: the net's node types are its SN subtypes."

ARROWHEADS = (1, 2, 3)
'''The ends (*rnet.LinkType.head*, *tail*) that are arrowheads: plain, heavy
(a conjunction's) and double (a disjunction's) -- each an ordinary link, as
far as the kernel goes (Gaines: their connective's iterative clause comes on
top).'''

BY_BARS = {0: INCLUDES, 1: EXCLUDES, 2: COEXCLUDES, 3: NEGATES}
"An arrowhead's bars (or a line's middle symbol: *rnet.LinkType.mid*) -> the kernel relation type it is."

NOT_KERNEL = ("generic", "etc", "prefer", "preferred", "prohibited", "forbidden", "defeasible", "conjecture",
              "possible", "particular")
'''Words in a link type's name that say it isn't the kernel link it looks
like: generic links stand for any of them (Gaines, section 2.7); "Etc" links
for more of the same, in pictures; preferences and defaults are defeasible;
the rest are prohibitions and modalities.'''

NODE_SHAPES = {0: "Rectangle", 1: "Rectangle", 2: "Oval", 3: "Rectangle"}
'''A node type's shape (*rnet.NodeType.shape*) -> its shape here (\"vis/shape\"). A grid's (\"rgrid\") is a
FileFolder. An enclosure's (see *ENCLOSURE*) is a box, drawn as a window.'''

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

MARK_WIDTH = 2
'''The width of the outline a mark draws (in its kind's colour) on a node
whose type has none (as Rep Plus does).'''

LABEL = "$name${mark:+ $mark}"
"Each node type's label template: the name, and the mark, if there is one (see the module doc)."

UNTYPED = "text"
"The node type made for nodes with none (eg: text the program wrote): just its text."

POINT = "point"
"The node type made for nodes of an enclosure type that have no size: invisible ends of links (eg: in a drawing)."

ENCLOSURE = 3
'''A node type's shape (*rnet.NodeType.shape*) that's an enclosure: a box that
holds the nodes inside it (RepNet manual, sections 3.7 and 6.2). Every node
type of the test nets named for a box ("collection", "frame", "context",
"construct", "cases", "rules", "Context:", "Cluster") has it.'''

TITLEBAR_TINT = 0.8
"How far a box's title bar is faded from its outline colour toward white."

CONSTRUCT = "construct"
"The name (any case; it may go on: eg, \"Construct:\") of the enclosure type whose boxes are Kelly constructs."

CONSTRUCT_EXCLUDES = "construct excludes"
"The relation type of the exclusions a construct box's poles get (see *addConstructMeaning()*)."

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

def kernelKind(t:LinkType) -> str|None:
  '''
  :returns: The kernel relation type (*KERNEL*) that links of *t* are, as its
    look says (Gaines's notation): an arrow is includes, and one with one,
    two or three bars at its head excludes, coexcludes or negates (a heavy or
    a double arrowhead -- a conjunction's or a disjunction's -- is still an
    arrow); a line with one, two or three bars across its middle (and no
    arrowheads, or one at each end) is the symmetric exclusion, coexclusion or
    negation; an arrow at each end is equivalent, and so is a plain line
    named so. None for anything else -- generic links, preferences,
    prohibitions, lines -- and for a type whose name says it isn't (see
    *NOT_KERNEL*).
  '''
  words = t.name.lower().replace("-", " ").split()
  if any(w in NOT_KERNEL for w in words) or t.mid > 3:
    return None
  ends = [bars for shape, bars in ((t.head, t.headBars), (t.tail, t.tailBars)) if shape in ARROWHEADS]
  if any(b not in BY_BARS for b in ends) or (len(ends) == 2 and ends[0] != ends[1]) \
     or 6 in (t.head, t.tail): # (generic)
    return None
  if ends and ends[0]:
    return BY_BARS[ends[0]]
  if t.mid:
    return BY_BARS[t.mid]
  if len(ends) == 2 or (not ends and "equivalent" in words):
    return EQUIVALENT
  return INCLUDES if ends else None

def connectiveKind(t:LinkType) -> str|None:
  '''
  :returns: The connective relation type (see *CONNECTIVES*) that links of
    *t* are: a kernel link (see *kernelKind()*) with a heavy or a double
    arrowhead at one end (and nothing at the other), with the bars that one
    has (none or one for a conjunction's, none or two for a disjunction's) --
    unless it's derived (KNet's inferences aren't definitions). None for
    anything else.
  '''
  if t.derived or kernelKind(t) is None:
    return None
  ends = [(shape, bars) for shape, bars in ((t.head, t.headBars), (t.tail, t.tailBars)) if shape]
  return CONNECTIVES.get(ends[0]) if len(ends) == 1 and not t.mid else None

def isReversed(t:LinkType) -> bool:
  '''
  :returns: Whether *t* is drawn backwards: an arrowhead (or a generic one) at
    its tail, and none at its head (eg: "Includes reverse").
  '''
  return t.tail in (*ARROWHEADS, 6) and t.head == 0

def ontology(m:Model) -> Model:
  '''
  :param m: A model built on *ONTOLOGY*.
  :returns: *ONTOLOGY*'s model.
  '''
  from util.utils import urlPath
  return next(db for db in m.superDBs if isinstance(db, Model) and db.url.startswith("file:")
              and os.path.realpath(urlPath(db.url) or "") == os.path.realpath(ONTOLOGY))

def kernelTypes(m:Model) -> dict[str, Relation]:
  '''
  :param m: A model built on *ONTOLOGY*.
  :returns: The kernel relation types (*KERNEL*), and the connectives' (*CONNECTIVES*), by name.
  '''
  onto = ontology(m)
  names = {*KERNEL, *CONNECTIVES.values()}
  return {str(o.name): o for o in onto.values()
          if o.model is onto and isinstance(o, Relation) and o.isType() and str(o.name) in names}

def knodeType(m:Model) -> Node:
  '''
  :param m: A model built on *ONTOLOGY*.
  :returns: *KNODE*: the SN type of a KNet net's nodes.
  '''
  onto = ontology(m)
  return next(o for o in onto.values() if o.model is onto and isinstance(o, Node) and o.isType() and o.name == KNODE)

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

def setNote(obj:GraphObject, text:str) -> None:
  '''
  Give *obj* the note *text*: a new attribute (see *note()*), unless it
  inherits one (eg: a kernel type's), whose kind it then has.
  '''
  if any("note" in p for p in obj.getParents()):
    obj["note"] = text
  else:
    obj.setAttr("note", note(text))

@dataclass
class Built:
  '''
  What *buildModel()* made of a net.
  '''
  net:Net
  model:Model
  nodeTypes:dict[int, Node] = field(default_factory=dict)
  "Each node type's place in the net -> its type (-1: *UNTYPED*, -2: *POINT*, if they were needed)."
  linkTypes:dict[int, Relation] = field(default_factory=dict)
  "Each link type's place in the net -> its relation type."
  kernel:dict[str, Relation] = field(default_factory=dict)
  "The kernel relation types (see *KERNEL*), and the connectives' (*CONNECTIVES*), by name."
  nodes:dict[int, Node] = field(default_factory=dict)
  "Each node's place in the net -> its individual (not the pictures and drawings)."
  relations:list[tuple[Relation, int]] = field(default_factory=list)
  "Each relation, and the place in the net of the link it's of."
  boxes:dict[int, Node] = field(default_factory=dict)
  "Each box's place in the net -> its individual (a node of an enclosure type: see *ENCLOSURE*)."
  members:dict[int, list[int]] = field(default_factory=dict)
  "Each box's place in the net -> the places of the nodes (and boxes) it contains, in order."
  derived:list[Relation] = field(default_factory=list)
  "The relations added for what the boxes mean (eg: a construct's poles' exclusions: see *addConstructMeaning()*)."
  skipped:list[str] = field(default_factory=list)
  "What wasn't made, and why."

  def report(self) -> str:
    '''
    :returns: What was made, in a sentence or two.
    '''
    contained = sum(len(v) for v in self.members.values())
    s = (f"{len(self.nodes)} nodes ({len(self.boxes)} of them boxes, holding {contained}) and {len(self.relations)} "
         f"relations, of {len(self.nodeTypes)} node types and {len(self.linkTypes)} relation types")
    kernel = sum(1 for t in self.linkTypes.values() if any(p in self.kernel.values() for p in t.getParents()))
    if kernel:
      s += f" ({kernel} of them KNet's kernel links: includes, excludes, ...)"
    if self.derived:
      s += f"; {len(self.derived)} exclusions between construct poles were added"
    marked = sum(1 for n in self.net.nodes if n.marks and n.index in self.nodes)
    if marked:
      s += f"; {marked} nodes have marks"
    if self.skipped:
      s += f". Left out: {'; '.join(self.skipped)}"
    return s + "."

def makeNodeType(m:Model, t:NodeType, file:str, knode:Node|None=None) -> Node:
  '''
  :param knode: *KNODE*, if *m*'s built on *ONTOLOGY*: the parent of a type that isn't a box's.
  :returns: A new node type in *m* for the net's node type *t* (see the module doc).
  '''
  box = t.shape == ENCLOSURE
  n = Node(m, [m.CONTEXT if box else knode if knode is not None else m.NODE], name=t.name or f"node type {t.index}")
  if box: # (a box of facts: see GraphObject.quotesContents())
    n[GraphObject.QUOTED] = False
  n["vis/shape"] = "FileFolder" if t.extra == "rgrid" else "Rectangle" if box else NODE_SHAPES.get(t.shape, "Rectangle")
  for key, i in NODE_COLORS.items():
    c = t.colors[i] if i < len(t.colors) and t.colors[i] else ""
    if key == "vis/borderColor" and not c and t.colors:
      c = t.colors[0]
    if c:
      n[key] = c
  if t.frameless:
    n["vis/fillColor"] = ""
    n["vis/borderColor"] = ""
  if box:
    outline = n.get("vis/borderColor", "")
    if isinstance(outline, str) and outline.startswith("#"):
      n["vis/titlebarColor"] = fade(outline, TITLEBAR_TINT)
  n["vis/label"] = LABEL
  setNote(n, f"A node type of {file}: shape {t.shape} (variant {t.variant}), {t.font} {t.size} point, "
             f"flags {t.flags}, colours {', '.join(c or '-' for c in t.colors)}"
             + (f', for "{t.extra}" files' if t.extra else "")
             + ("; an enclosure: a box that holds the nodes inside it" if box else "") + ".")
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

def makePoint(m:Model, file:str) -> Node:
  '''
  :returns: A new *POINT* type in *m*: nothing drawn.
  '''
  n = Node(m, [m.NODE], name=POINT)
  n["vis/fillColor"] = ""
  n["vis/borderColor"] = ""
  n["vis/label"] = LABEL
  n.setAttr("note", note(f"The nodes of {file} of box types that have no size: invisible ends of the links CNet draws "
                         "(eg: in a drawing). Their own types' names are their rnetType attributes."))
  return n

def makeLinkType(m:Model, t:LinkType, file:str, kernel:dict[str, Relation]|None=None) -> Relation:
  '''
  :param kernel: The kernel relation types (see *kernelTypes()*): it's an SN
    subtype of the one it is (see *connectiveKind()* and *kernelKind()*), if any.
  :returns: A new relation type in *m* for the net's link type *t* (see the module doc).
  '''
  kind = connectiveKind(t) or kernelKind(t)
  parent = (kernel or {}).get(kind or "")
  r = Relation(m, [parent if parent is not None else m.RELATION], None, None, name=t.name or f"link type {t.index}")
  if isReversed(t): # (its links go the other way: see buildModel())
    r["vis/terminator1"] = endMarks(t.head, t.headBars, atSource=True)
    r["vis/terminator4"] = endMarks(t.tail, t.tailBars, atSource=False)
  else:
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
    if t.dashed:
      color = fade(color)
  r["vis/lineColor"] = color
  r["vis/lineFillColor"] = color
  how = (f"bits {t.bits}" if t.bits is not None else
         f"head {t.head} with {t.headBars} bars, tail {t.tail} with {t.tailBars} bars, line {t.lineFlags}, middle {t.mid}")
  setNote(r, (f"A link type of {file}: {how}; colours {', '.join(c or '-' for c in t.colors)}"
                         + ("; derived (CNet's or KNet's inferences)" if t.derived else "")
                         + ("; drawn dashed (faded here)" if t.dashed and t.bits is None else "")
                         + ("; drawn backwards in the file (its links go the other way here)" if isReversed(t) else "")
                         + (f"; it means {kind} (the kernel's)" if parent is not None else "") + "."))
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
  if kind is not None and n.marks & 0xFF:
    node["markKind"] = kind.name
  if n.derived:
    node["markDerived"] = True
  else: # (its truth mark: see the module doc)
    how = kind.name.lower() if kind is not None and kind.name else ASSERTED
    for letter, key in (("T", MARK_TRUE), ("F", MARK_FALSE)):
      if letter in (n.truth or ""):
        node[key] = how
  if kind is None:
    return
  color, background = (kind.colors + ["", ""])[:2]
  if n.filled and background:
    node["vis/fillColor"] = background
  if n.outlined and color:
    frameless = not node.get("vis/borderColor", "") # (its type's: eg, a title)
    node["vis/borderColor"] = color
    if frameless:
      node["vis/borderWidth"] = MARK_WIDTH

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
  m.setSuperModels([ONTOLOGY])
  b = Built(net, m, kernel=kernelTypes(m))
  knode = knodeType(m)
  for t in net.nodeTypes:
    b.nodeTypes[t.index] = makeNodeType(m, t, file, knode)
  for t in net.linkTypes:
    b.linkTypes[t.index] = makeLinkType(m, t, file, b.kernel)
  pictures = 0
  for n in net.nodes:
    if n.kind != "node":
      pictures += 1
      continue
    t = b.nodeTypes.get(n.type)
    point = t is not None and t.isa(m.CONTEXT) and (n.w <= 0 or n.h <= 0) # (a box of no size: an invisible end of links)
    if t is None or point:
      key = -2 if point else -1
      if key not in b.nodeTypes:
        b.nodeTypes[key] = makePoint(m, file) if point else makeUntyped(m, file)
      t, was = b.nodeTypes[key], t
    node = Node(m, [t], individual=True, name=nodeName(n))
    if point:
      node["rnetType"] = str(was.name)
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
    for slot, t in enumerate(l.types):
      typ = b.linkTypes.get(t)
      if typ is None:
        continue
      backwards = l.backwards(slot) != (0 <= t < len(net.linkTypes) and isReversed(net.linkTypes[t])) # (as it's drawn)
      r = Relation(m, [typ], dst if backwards else src, src if backwards else dst, individual=True)
      if l.extra:
        r["values"] = " ".join(l.extra)
      b.relations.append((r, l.index))
  if missing:
    b.skipped.append(f"{missing} links to pictures, drawings or nodes that aren't there")
  if net.groups:
    b.skipped.append(f"{len(net.groups)} groups (Rep Plus's way to drag nodes together: they mean nothing)")
  b.boxes = {i: node for i, node in b.nodes.items() if node.isCollection()}
  b.members = enclosed(net, set(b.boxes))
  for i, inside in b.members.items():
    for j in inside:
      if j in b.nodes:
        b.boxes[i].addMember(b.nodes[j])
  addConstructMeaning(b)
  return b

def enclosed(net:Net, boxes:set[int]) -> dict[int, list[int]]:
  '''
  :param boxes: The places in *net* of its boxes (its nodes of enclosure types).
  :returns: Each box's place -> the places of the nodes it holds, in order:
    those whose centres are inside it -- the smaller boxes too -- each in the
    smallest box it's in (CNet lists them nowhere: it's where they are).
  '''
  rect = {n.index: (n.x, n.y, n.x + n.w, n.y + n.h) for n in net.nodes if n.kind == "node"}
  area = lambda i: (rect[i][2] - rect[i][0]) * (rect[i][3] - rect[i][1])
  ret:dict[int, list[int]] = {}
  for n in net.nodes:
    if n.index not in rect:
      continue
    cx, cy = n.x + n.w / 2, n.y + n.h / 2
    around = [i for i in boxes if i != n.index and i in rect and area(i) > area(n.index)
              and rect[i][0] <= cx <= rect[i][2] and rect[i][1] <= cy <= rect[i][3]]
    if around:
      ret.setdefault(min(around, key=area), []).append(n.index)
  return ret

def _isIncludes(t:LinkType) -> bool:
  "Whether links of *t* are includes (ordination): a plain arrow, with no bars or other marks."
  return t.head == 1 and t.headBars == 0 and t.tail == 0 and t.tailBars == 0 and t.mid == 0

def _isSymmetricExclusion(t:LinkType) -> bool:
  "Whether *t* is the symmetric exclusion: a line with one bar across its middle, and no arrowheads."
  return t.mid == 1 and t.head == 0 and t.tail == 0 and t.headBars == 0 and t.tailBars == 0

def addConstructMeaning(b:Built) -> None:
  '''
  Add what CNet's construct macro means (RepNet manual, section 3.7): the
  poles of a construct box (the nodes it holds: see *enclosed()*) are linked
  by mutual opposition, unless that conflicts with an ordination link -- an
  includes link (see *_isIncludes()*), or a chain of them, from one pole to
  the other. Each pair that's opposed, and isn't linked so already, gets a
  relation of *CONSTRUCT_EXCLUDES* (an SN subtype of the net's symmetric
  exclusion, or of a new one if it has none), drawn faded as CNet's derived
  links are, and noted as added by the reader -- so it can be hidden, or
  taken out, by its type.
  '''
  net, m = b.net, b.model
  constructs = [i for i, box in b.boxes.items()
                if any(p.name and str(p.name).strip().lower().startswith(CONSTRUCT) for p in box.getParents())]
  if not constructs:
    return
  includes:dict[int, set[int]] = {}
  excluded:set[tuple[int, int]] = set()
  for l in net.links:
    kinds = [net.linkTypes[t] for t in l.types if 0 <= t < len(net.linkTypes)]
    if any(_isIncludes(t) for t in kinds):
      includes.setdefault(l.source, set()).add(l.destination)
    if any(_isSymmetricExclusion(t) for t in kinds):
      excluded.add((min(l.source, l.destination), max(l.source, l.destination)))
  def reaches(a:int, z:int) -> bool:
    seen, todo = {a}, [a]
    while todo:
      for n in includes.get(todo.pop(), ()):
        if n == z:
          return True
        if n not in seen:
          seen.add(n)
          todo.append(n)
    return False
  typ:Relation|None = None
  for i in constructs:
    poles = [j for j in b.members.get(i, []) if j not in b.boxes]
    for x in range(len(poles)):
      for y in range(x + 1, len(poles)):
        p, q = poles[x], poles[y]
        if (min(p, q), max(p, q)) in excluded or reaches(p, q) or reaches(q, p):
          continue
        if typ is None:
          typ = _constructExcludes(b)
        b.derived.append(Relation(m, [typ], b.nodes[p], b.nodes[q], individual=True))

def _constructExcludes(b:Built) -> Relation:
  '''
  :returns: A new *CONSTRUCT_EXCLUDES* relation type in *b*'s model: an SN
    subtype of the net's symmetric exclusion (or of a new "Excludes
    symmetric", if it has none), faded.
  '''
  m = b.model
  base = next((b.linkTypes[t.index] for t in b.net.linkTypes if _isSymmetricExclusion(t) and t.index in b.linkTypes), None)
  if base is None:
    kernel = b.kernel.get(EXCLUDES)
    base = Relation(m, [kernel if kernel is not None else m.RELATION], None, None, name="Excludes symmetric")
    base["vis/terminator4"] = ""
    base["vis/midMarks"] = MID_MARKS[1]
    base["vis/label"] = ""
    base["vis/lineType"] = "straight"
    base["vis/lineColor"] = "#00a000"
    base["vis/lineFillColor"] = "#00a000"
    setNote(base, "The symmetric exclusion (made for the exclusions between construct poles: the net has none).")
  ret = Relation(m, [base], None, None, name=CONSTRUCT_EXCLUDES)
  color = base.get("vis/lineColor", "#000000")
  if isinstance(color, str) and color.startswith("#"):
    ret["vis/lineColor"] = fade(color)
    ret["vis/lineFillColor"] = fade(color)
  ret["note"] = ("Added by the Rep Plus Net Reader: the poles of a construct box exclude each other (CNet's construct "
                 "macro), unless an includes link, or a chain of them, joins them.") # (its base's note's kind: see note())
  return ret
