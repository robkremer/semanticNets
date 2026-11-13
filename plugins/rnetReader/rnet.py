'''
Read a Rep Plus net file (".rnet": the nets of Brian Gaines's CNet and KNet,
in Rep Plus 2 and its forerunners) into plain Python objects (see *parse()*),
with nothing of Semantic Nets in it: *reader* makes the model and view from
what this finds.

The file is text: UTF-8 (with a byte order mark), its lines ended by CRs (or
LFs), its fields by tabs. The first line is a header, ``\\tC\\t<version>\\t<background
colour>...``, and the rest are sections, each a line naming it and how many
lines it has, and then those lines:

``D``
    settings: a name and a value on each line (eg: "Date", "NodeType").
    (Versions 6 and 7 have a "PS:" line instead: ``PS:CNet\\tT:All\\t...``.)
``T``
    the node types: shape, a variant of it, font, size, bold, flags, four
    colours (see *NodeType*), ..., and the name, last.
``A``
    the link types: in versions 7 and 8, and some 9s, four fields --
    *bits* (an arrowhead at the destination, at the source, a bar, ...),
    two colours and the name; in version 9, eleven -- the head's shape
    and bars, the tail's shape and bars, the line's flags, a symbol in the
    middle, four colours, and the name (see *LinkType*). Version 6 has none:
    its links' codes are the bits themselves.
``M``
    the kinds of mark (see *MarkKind*): two colours and the name.
``N``
    the nodes: type, marks (none in version 6), x, y, width, height,
    label, and (from version 7) one more field. A node whose type is
    prefixed by "P" or "G" is a picture or a drawing: a drawing's records
    (rectangles, lines, text...) follow it, in lines of their own.
``L``
    the links: source and destination nodes (by their place in ``N``,
    from 0), the link types (by their place in ``A``): the link's from the
    source to the destination, and, if there's a second (after a space),
    the type of a link back, from the destination to the source -- Rep
    Plus's Link.Type(0) and Type(1), drawn side by side -- and, in some
    files, more fields (its flags, and a label: eg, a weight).
``G``
    the groups (panels: parts of the net that go together): the nodes in
    each, and in a second field (if any) the groups in it.

A type's colours, and a link type's, are 6 hexadecimal digits (RRGGBB), but
older files leave out leading zeros ("8A00" for 008A00). A label's line breaks
are U+FFFD characters (as CNet wrote them).

Worked out from the files themselves (and the SVG pictures CNet exported of
some of them): see *NodeType* and *LinkType* for what's known, and guessed,
of what their fields mean.

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
import re
from dataclasses import dataclass, field

LINE_BREAK = "\ufffd"
"What stands for a line break in a label."

# What a link type's *bits* (versions 6 to 8, and some 9s) say (see *LinkType*):
HEAD = 1
"An arrowhead at the destination."
TAIL = 2
"An arrowhead at the source."
BAR = 4
"A bar across the middle of the line."
HEAVY = 16
"Heavy arrowheads (a conjunction)."
DOUBLE = 32
"Double arrowheads (a disjunction)."

V6_LINK_NAMES = {HEAD: "Entails", HEAD | BAR: "Opposite", BAR: "Opposite", HEAD | TAIL: "Equivalent",
                 HEAD | HEAVY: "Defined by", HEAD | BAR | HEAVY: "Defined by opposite"}
"Names for version 6's links, which have no link types: by their bits (as later versions' files call them)."

def color(value:str) -> str:
  '''
  :param value: A colour in a net file: hexadecimal RRGGBB, perhaps without leading zeros.
  :returns: It as "#rrggbb" (or "" if it isn't one).
  '''
  value = value.strip()
  if not value or len(value) > 6 or not all(c in "0123456789abcdefABCDEF" for c in value):
    return ""
  return "#" + value.zfill(6).lower()

def _int(value:str, default:int=0) -> int:
  try:
    return int(value.strip())
  except ValueError:
    return default

def label(value:str) -> str:
  '''
  :param value: A label in a net file.
  :returns: It with its line breaks (see *LINE_BREAK*) as "\\n", and none at the end.
  '''
  return value.replace(LINE_BREAK, "\n").rstrip("\n")

@dataclass
class NodeType:
  '''
  A node type (a line of section ``T``).

  CNet's SVG pictures of its nets show that of the four colours, the second
  is the fill and the third the text's (eg: "All": 008A00, D8FFFF, 006400,
  008A00 is drawn as an ellipse filled with D8FFFF, outlined in 008A00, with
  text in 006400). The outline is the first or the fourth: they're the same in
  every type those pictures show.
  '''
  index:int
  name:str
  shape:int
  "0: a box; 1: a note; 2: an ellipse; 3: a rounded box (a context)."
  variant:int
  "A variant of the shape (eg: \"Any\" is a variant 1 ellipse; \"Set\", a variant 3 box)."
  font:str
  size:int
  "The font's size, in points."
  bold:int
  flags:int
  "Eg: 16 -- just its text, with no outline or fill (titles, notes)."
  colors:list[str]
  "The four colours, as \"#rrggbb\" (see the class doc)."
  extra:str = ""
  "Eg: \"rgrid\": the kind of file a grid node opens."
  fields:list[str] = field(default_factory=list)
  "All its fields, as they are in the file."

  @property
  def frameless(self) -> bool:
    "Whether it's just its text (eg: a title, or a note): no outline, nor fill."
    return bool(self.flags & 16)

@dataclass
class LinkType:
  '''
  A link type (a line of section ``A``): how its links are drawn, and its name.

  Versions 7 and 8 (and some files of version 9) give it as *bits* (see
  *HEAD*, *TAIL*, *BAR*, *HEAVY* and *DOUBLE*) and two colours, the line's and
  the arrowheads' and bars' (as CNet's SVG pictures show). Version 9 gives
  the head's shape (*head*: 0 none, 1 an arrowhead, 2 a heavy one, 3 a double
  one) and bars (*headBars*: 0 to 3), the same at the tail, the line's flags
  (4: drawn dashed: see *dashed*), a symbol in the middle (*mid*), and four colours.
  For version 6, which has no link types, they're made from the codes its
  links have, which are the bits.
  '''
  index:int
  name:str
  head:int = 0
  headBars:int = 0
  tail:int = 0
  tailBars:int = 0
  lineFlags:int = 1
  mid:int = 0
  "The symbol in the middle: 1, 2, 3 for the symmetric exclusion, coexclusion and negation; 4 prohibited; 6 preferred."
  colors:list[str] = field(default_factory=list)
  "Two (from *bits*) or four colours, as \"#rrggbb\"."
  bits:int|None = None
  "Its bits, if it was given by them (see the class doc)."
  fields:list[str] = field(default_factory=list)
  "All its fields, as they are in the file."

  @staticmethod
  def fromBits(index:int, name:str, bits:int, colors:list[str], fields:list[str]|None=None) -> LinkType:
    '''
    :returns: The link type that's drawn as *bits* say, with *colors*.
    '''
    shape = 3 if bits & DOUBLE else 2 if bits & HEAVY else 1
    return LinkType(index, name, head=shape if bits & HEAD else 0, tail=shape if bits & TAIL else 0,
                    lineFlags=1, mid=1 if bits & BAR else 0, colors=colors, bits=bits, fields=fields or [])

  @property
  def derived(self) -> bool:
    '''Whether its links were derived (inferred by CNet or KNet), rather than
    drawn: its name says so (eg: "Includes derived"), as every one of the test
    nets' do -- in version 9, most of them are drawn in their own colour (a
    light blue), some *dashed*.'''
    return "derived" in self.name.lower()

  @property
  def dashed(self) -> bool:
    '''Whether its links are drawn dashed (its line's flag 4: eg, some derived
    ones, and "Etc" ones, which stand for more of the same).'''
    return bool(self.lineFlags & 4)

@dataclass
class MarkKind:
  '''
  A kind of mark (a line of section ``M``): a node's mark says where it came
  from (eg: "Asserted", "Included", "Excluded") by its colours.
  '''
  index:int
  name:str
  colors:list[str]
  '''Two colours, as "#rrggbb": the mark's -- its symbols' and its outline's
  (see *NetNode.marks*) -- and its background, a lighter one, the fill's.'''

@dataclass
class NetNode:
  '''
  A node (a line of section ``N``).
  '''
  index:int
  kind:str
  "\"node\"; or \"picture\" or \"drawing\" (an image, or a vector drawing), which aren't concepts."
  type:int
  "Its node type's place in section ``T`` (-1: none -- eg: text the program wrote, and some pictures and drawings)."
  flags:int
  "The bits above the type's (its type field's, from 1024 up)."
  marks:int
  "Its marks, as a number (0: none): see *truth*, *symbols*, *outlined*, *filled*, *derived* and *markKind*."
  x:int
  y:int
  w:int
  h:int
  label:str
  "Its text, with \"\\n\" for its line breaks."
  extra:str = ""

  @property
  def truth(self) -> str:
    '''Its mark's truth value: "T" (true: a vertical bar), "F" (false: a
    horizontal bar), "TF" (both) or "" (neither).'''
    return ("", "T", "F", "TF")[self.marks & 3]

  @property
  def symbols(self) -> int:
    '''The symbols Rep Plus draws on it, in its mark kind's colour (its
    Node.PaintMark): 1, a vertical bar (true); 2, a horizontal bar (false); 4
    and 8, the two diagonals; 16, a dot in the middle; 32, a ring round it.'''
    return self.marks & 0x3F

  @property
  def outlined(self) -> bool:
    "Whether its outline is drawn in its mark kind's colour."
    return bool(self.marks & 0x40)

  @property
  def filled(self) -> bool:
    "Whether it's filled with its mark kind's background colour."
    return bool(self.marks & 0x80)

  @property
  def derived(self) -> bool:
    '''Whether its mark was inferred, rather than asserted: it has the ring
    (*symbols* 32), as KNet's inferences (0xE0: ring, outline and fill) and
    CNet's (0xA0) have, and its assertions (0x80) don't.'''
    return bool(self.marks & 0x20)

  @property
  def markKind(self) -> int:
    "Its mark's kind: its place in section ``M``."
    return (self.marks >> 8) & 0xFF

@dataclass
class Link:
  '''
  A line drawn between two nodes (a line of section ``L``): a link of its
  first type from its *source* to its *destination*, and one of its second
  type, if it has one, back from its destination to its source (Rep Plus
  draws the two side by side, the second one backwards: see *backwards()*).
  '''
  index:int
  source:int
  destination:int
  types:list[int]
  '''Its link types' places in section ``A`` (in version 6: their codes): the
  first is the link's from *source* to *destination*, the second (if any) the
  one back.'''
  extra:list[str] = field(default_factory=list)
  "Any more fields (eg: its flags, and a weight)."

  @staticmethod
  def backwards(slot:int) -> bool:
    '''
    :param slot: A place in *types*.
    :returns: Whether the link of the type there goes from *destination* to
      *source*: the second does (KNet takes it so -- KNet.InitLinks -- and
      Rep Plus draws it so, from the destination's end).
    '''
    return slot == 1

@dataclass
class Group:
  '''
  A group (a line of section ``G``): nodes that go together (eg: a panel of a
  picture), and the groups in it.
  '''
  index:int
  nodes:list[int]
  groups:list[int] = field(default_factory=list)

@dataclass
class Net:
  '''
  A net file's contents (see *parse()*).
  '''
  path:str
  version:int
  background:str
  "The background colour, as \"#rrggbb\" (or \"\")."
  settings:dict[str, str] = field(default_factory=dict)
  nodeTypes:list[NodeType] = field(default_factory=list)
  linkTypes:list[LinkType] = field(default_factory=list)
  markKinds:list[MarkKind] = field(default_factory=list)
  nodes:list[NetNode] = field(default_factory=list)
  links:list[Link] = field(default_factory=list)
  groups:list[Group] = field(default_factory=list)
  problems:list[str] = field(default_factory=list)
  "What couldn't be read, or doesn't fit (eg: a link to a node that isn't there)."

  def check(self) -> list[str]:
    '''
    Add to *problems* whatever refers to something that isn't there.

    :returns: *problems*.
    '''
    for n in self.nodes:
      if n.kind == "node" and not -1 <= n.type < len(self.nodeTypes): # (-1: no type -- eg: text the program wrote)
        self.problems.append(f"node {n.index} ({n.label!r}) has type {n.type}, which isn't there")
      if n.marks & 0xFF and n.markKind >= len(self.markKinds): # (drawn in its kind's colours)
        self.problems.append(f"node {n.index} ({n.label!r}) has mark kind {n.markKind}, which isn't there")
    for l in self.links:
      for end in (l.source, l.destination):
        if not 0 <= end < len(self.nodes):
          self.problems.append(f"link {l.index} goes to node {end}, which isn't there")
      for t in l.types:
        if not 0 <= t < len(self.linkTypes):
          self.problems.append(f"link {l.index} has type {t}, which isn't there")
    for g in self.groups:
      for i in g.nodes:
        if not 0 <= i < len(self.nodes):
          self.problems.append(f"group {g.index} has node {i}, which isn't there")
      for i in g.groups:
        if not 0 <= i < len(self.groups) or i == g.index:
          self.problems.append(f"group {g.index} has group {i}, which isn't there")
    return self.problems

_NODE = re.compile(r"^([PG]?)(-?\d+)$")
_KINDS = {"": "node", "P": "picture", "G": "drawing"}

def _isInt(s:str) -> bool:
  return s.lstrip("-").isdigit()

def _ints(s:str) -> list[int]:
  return [int(x) for x in s.split() if _isInt(x)]

def parse(path:str) -> Net:
  '''
  :param path: A net file (".rnet").
  :returns: What's in it (see *Net*). What can't be read is in its *problems*.
  :raises ValueError: if it isn't a net file.
  '''
  with open(path, encoding="utf-8-sig", errors="replace") as f:
    text = f.read()
  return parseText(text, path)

def parseText(text:str, path:str="") -> Net:
  '''
  :param text: A net file's contents.
  :param path: Where it's from (for *Net.path*).
  :returns: What's in it (see *Net*). What can't be read is in its *problems*.
  :raises ValueError: if it isn't a net file.
  '''
  lines = re.split(r"\r\n|\r|\n", text.lstrip("\ufeff"))
  header = lines[0].split("\t")
  if len(header) < 3 or header[1] != "C" or not header[2].isdigit():
    raise ValueError("It isn't a Rep Plus net file: its first line should start with a tab, \"C\", and the version.")
  net = Net(path, int(header[2]), color(header[3]) if len(header) > 3 else "")
  hasMarks = net.version >= 7
  v6codes:dict[int, int] = {} # (version 6: a link's code -> its link type's place)
  stage = 0 # (0: before the nodes; 1: after them, before the links -- skipping the last drawing's records; 2: after the links)
  i = 1
  def rows(n:int) -> list[list[str]]:
    nonlocal i
    got = [lines[j].split("\t") for j in range(i, min(i + n, len(lines)))]
    i += n
    return got
  while i < len(lines):
    line = lines[i]
    p = line.split("\t")
    i += 1
    if not line.strip():
      continue
    key = p[0]
    count = _int(p[1], -1) if len(p) > 1 and _isInt(p[1]) else -1
    isLinks = key == "L" and count >= 0 and len(p) in (3, 4) and all(_isInt(x) for x in p[1:])
    if stage == 1 and not isLinks or stage == 2 and key != "G":
      continue # (a record of the last drawing (eg: "T\t9\t37\ttext", "L\t1\t2\t3\t4", "G\t10\t-1\t0"), or something unknown)
    if key == "D" and count >= 0:
      net.settings.update({r[0]: r[1] if len(r) > 1 else "" for r in rows(count)})
    elif key.startswith("PS:"): # (versions 6 and 7: "PS:CNet\tT:All\tI:/CNet/")
      net.settings.update({k: v for k, _, v in (f.partition(":") for f in p if f)})
    elif key == "T" and count >= 0:
      for r in rows(count):
        if len(r) < 11:
          net.problems.append(f"node type {len(net.nodeTypes)} has too few fields: {r}")
          r = r + [""] * (11 - len(r))
        net.nodeTypes.append(NodeType(len(net.nodeTypes), r[-1], _int(r[0]), _int(r[1]), r[2], _int(r[3], 9), _int(r[4]),
                                      _int(r[5]), [color(c) for c in r[6:10]], r[-2] if len(r) >= 12 else "", r))
    elif key == "A" and count >= 0:
      for r in rows(count):
        n = len(net.linkTypes)
        if len(r) >= 11:
          net.linkTypes.append(LinkType(n, r[-1], _int(r[0]), _int(r[1]), _int(r[2]), _int(r[3]), _int(r[4], 1), _int(r[5]),
                                        [color(c) for c in r[6:10]], None, r))
        elif len(r) >= 4:
          net.linkTypes.append(LinkType.fromBits(n, r[-1], _int(r[0]), [color(c) for c in r[1:3]], r))
        else:
          net.problems.append(f"link type {n} has too few fields: {r}")
          net.linkTypes.append(LinkType(n, r[-1] if r else f"link {n}", fields=r))
    elif key == "M" and count >= 0:
      for r in rows(count):
        net.markKinds.append(MarkKind(len(net.markKinds), r[-1], [color(c) for c in r[:-1]]))
    elif key == "N" and count >= 0:
      got = 0
      while got < count and i < len(lines):
        q = lines[i].split("\t")
        i += 1
        m = _NODE.match(q[0].split(" ")[0]) # (version 6 may have more after a space: "0 A")
        if m is None or len(q) < (6 if hasMarks else 5) or not all(_isInt(v) for v in q[2 if hasMarks else 1:6 if hasMarks else 5]):
          continue # (a record of the drawing before it)
        typ = int(m.group(2))
        f = q[1:] if hasMarks else ["0"] + q[1:]
        f += [""] * (7 - len(f))
        try:
          marks = int(f[0], 16) if f[0] else 0
        except ValueError:
          net.problems.append(f"node {got} has marks {f[0]!r}, which aren't hexadecimal")
          marks = 0
        net.nodes.append(NetNode(got, _KINDS[m.group(1)], typ & 1023 if typ >= 0 else typ, typ >> 10 if typ >= 0 else 0, marks,
                                 int(f[1]), int(f[2]), int(f[3]), int(f[4]), label(f[5]), f[6]))
        got += 1
      if got < count:
        net.problems.append(f"{count} nodes were expected, but there are {got}")
      stage = 1
    elif isLinks:
      stage = 2
      for r in rows(count):
        if len(r) < 3 or not _isInt(r[0]) or not _isInt(r[1]):
          net.problems.append(f"link {len(net.links)} can't be read: {r}")
          continue
        types = _ints(r[2])
        if net.version <= 6: # (no link types: the codes are their bits)
          for code in types:
            if code not in v6codes:
              v6codes[code] = len(net.linkTypes)
              net.linkTypes.append(LinkType.fromBits(len(net.linkTypes), V6_LINK_NAMES.get(code, f"link {code}"), code, ["#000000", "#000000"]))
          types = [v6codes[code] for code in types]
        net.links.append(Link(len(net.links), int(r[0]), int(r[1]), types, [x for x in r[3:] if x.strip()]))
    elif key == "G" and count >= 0:
      for r in rows(count):
        fields = [f for f in r if f.strip()]
        net.groups.append(Group(len(net.groups), _ints(fields[0]) if fields else [], _ints(fields[1]) if len(fields) > 1 else []))
  net.check()
  return net
