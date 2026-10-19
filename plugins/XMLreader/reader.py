'''
Turn an XML file into a Semantic Nets model (see *buildModel()*), built on an
ontology of its own: a second model, a super-model of the first, which has the
types and the definitions -- so there's one place to change the type hierarchy,
add rules, and so on. The model has the elements.

  - Each tag name becomes a type (a node isa *node*), the first time it's seen,
    with a look of its own (see *TypeLooks*), which its individuals inherit.
  - Each element becomes an individual of its tag's type -- or, if it has a
    "type" or "kind" attribute (see *TYPE_ATTRIBUTES*), of a subtype of its
    tag's type named by that attribute's value (eg: <object type="str"> is an
    individual of *str*, which isa *object*), made the first time it's seen.
    Subtypes look like their tag's type, in a different shade.
  - An element's attributes become attributes of its type (with the value "",
    unless an element of that type gives one), which each individual fills in
    with its own values. An XML attribute whose name Semantic Nets already uses
    for something else (eg: "name": an object's name) is stored as
    "xml/<name>" instead.
  - An element's text (if it isn't just white space) becomes its individual's
    "text" attribute.
  - A nested element's individual is related to its containing element's by a
    relation of type "has-<tag>" (eg: a book element's *has-chapter* relations
    to its chapters), made the first time it's needed. Each has-<tag> is a kind
    of *xml-has-part* (see *HAS_PART*), so the elements' tree is there whatever
    the tags.
  - *xml-part-of* (see *PART_OF*) is the other way round: it's defined (a
    definition in the ontology) as [?a -xml-part-of-> ?b] <-> [?b -xml-has-part-> ?a],
    so the reasoner concludes it.
  - An individual is named by its element's "id", "name" or "key" attribute (the
    first of those it has); otherwise by its tag and a number (eg: chapter1,
    chapter2, ...).

Namespaces are dropped from tag and attribute names (eg: "{http://...}book"
becomes "book").

The ontology can be one made before, for the same file (eg: by reading it
again, after changing the ontology: moving types about, adding rules, ...):
*buildModel()* builds on it, and adds only what's missing. What's in it is
found by name:

  - a tag's type, by the tag (any node type of that name: wherever it is in
    the type hierarchy);
  - a subtype, by its "type" or "kind" attribute's value: one of that name
    that's a kind of its tag's type (at any depth: eg: under another subtype);
  - has-<tag>, *HAS_PART* and *PART_OF*, by name (relation types).

What isn't found -- something the XML has that the ontology doesn't, or one
renamed or deleted since -- is made afresh, as for a new ontology, with a
look of its own, and logged; so is an attribute of an element that its type
doesn't have (nor inherit). (A has-<tag> found whose range its tag's type
isn't a kind of -- eg: the type was renamed, and so made afresh -- is left as
it is, with a warning: the reasoner would find each element out of range.) If
*PART_OF* isn't there, it's made with its definition; if it is, its
definition is left as it is (or isn't: one deleted stays deleted).

Created on Oct 3, 2026

.. codeauthor:: Rob Kremer <robkremer@me.com>
'''
from __future__ import annotations
import colorsys
import os
import random
import xml.etree.ElementTree as ET
import sn
from sn.model.model import GraphObject, Model, Node, Relation
from util.attribute import Attribute, VAR_DEFAULTED

HAS_PART = "xml-has-part"
"The relation type every has-<tag> is a kind of: from an element to each element in it."

PART_OF = "xml-part-of"
"The relation type defined as the inverse of *HAS_PART*: from an element to the element it's in."

RESERVED = {"name", "note", "constraints", "text"}
'''XML attribute names stored as "xml/<name>", as Semantic Nets uses them for
something else. ("text" is the element's own text: see the module doc.)'''

RESERVED_PREFIXES = ("vis/", "gui/", "xml/")
"Likewise for XML attribute names starting with these."

NAMING_ATTRIBUTES = ("id", "name", "key")
"The XML attributes an element's individual is named by (the first it has), if any."

logger:sn.SNLogger = sn.getLogger(__name__)

TYPE_ATTRIBUTES = ("type", "kind")
'''The XML attributes naming a subtype of an element's tag's type for its
individual to be one of (the first it has), if any. (Not "class": in HTML and
the like, that's a list of style classes.)'''

SHAPES = ("Rectangle", "RoundedRectangle", "Oval", "Hexagon", "FileFolder", "RightParallelogram",
          "LeftParallelogram", "TopPentagon", "RightPentagon", "LeftPentagon")
"The shapes the types are given (see *TypeLooks*)."

class TypeLooks:
  '''
  A look -- fill and border colours, and shape -- for each type, chosen at
  random, but the same each time for the same XML file. The fills' hues are
  spread out (by the golden ratio), so types made one after another look
  different; their individuals inherit the look, so it shows which type each
  is. A subtype (see *applyShade()*) keeps its type's hue and shape, in a
  shade of its own. Types already there (in an ontology made before: see
  *reuse()*) are counted as they come, so new ones look as they would have,
  had they been made with them.
  '''
  GOLDEN = 0.618033988749895

  def __init__(self, seed:str):
    '''
    :param seed: What the choices depend on: eg: the XML file's name.
    '''
    self.random = random.Random(seed)
    self.hue = self.random.random()
    self.hues:dict[int, float] = {}    # id(type) -> its hue
    self.shades:dict[int, int] = {}    # id(type) -> how many subtypes it has had shades for

  @staticmethod
  def _hex(h:float, s:float, v:float) -> str:
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, s, v)
    return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"

  def _next(self) -> tuple[str, str, str]:
    '''
    :returns: The next look: fill, border, shape (see *apply()*).
    '''
    self.hue += self.GOLDEN
    fill = self._hex(self.hue, self.random.uniform(0.25, 0.45), self.random.uniform(0.92, 1.0))
    border = self._hex(self.hue, 0.8, self.random.uniform(0.45, 0.6))
    return fill, border, self.random.choice(SHAPES)

  def apply(self, t:Node) -> None:
    '''
    Give the type *t* the next look: a light fill, a dark border of the same
    hue, and a shape.

    :param t: A type.
    '''
    t["vis/fillColor"], t["vis/borderColor"], t["vis/shape"] = self._next()
    self.hues[id(t)] = self.hue

  def reuse(self, t:GraphObject) -> None:
    '''
    Count the type *t*, which is already there, as if *apply()* had given it
    the next look, but leave it as it is (its subtypes are shaded from its own
    fill, if it has one: see *applyShade()*).

    :param t: A type.
    '''
    self._next()
    self.hues[id(t)] = self._hue(t) or self.hue

  def reuseShade(self, parent:GraphObject) -> None:
    '''
    Count a subtype of *parent* that's already there, as if *applyShade()* had
    given it the next shade, but leave it as it is.

    :param parent: Its type.
    '''
    self.shades[id(parent)] = self.shades.get(id(parent), 0) + 1

  @staticmethod
  def _hue(t:GraphObject) -> float|None:
    '''
    :returns: The hue of *t*'s fill colour (its own, or inherited), if it's "#rrggbb", else None.
    '''
    fill = t.get("vis/fillColor")
    if not isinstance(fill, str) or len(fill) != 7 or not fill.startswith("#"):
      return None
    try:
      r, g, b = (int(fill[i:i+2], 16) / 255 for i in (1, 3, 5))
    except ValueError:
      return None
    return colorsys.rgb_to_hsv(r, g, b)[0]

  def applyShade(self, sub:Node, parent:Node) -> None:
    '''
    Give *sub*, a new subtype of *parent* (a type given a look by *apply()*),
    the next shade of *parent*'s hue: its subtypes' fills range from pale to
    strong (spread by the golden ratio, so ones made one after another differ),
    with a border to match. Its shape is *parent*'s (inherited).

    :param sub: The subtype.
    :param parent: Its type.
    '''
    hue = self.hues.get(id(parent))
    if hue is None: # (not one of ours: eg: a type of the user's, in an ontology made before)
      hue = self._hue(parent)
      if hue is None:
        return
    n = self.shades[id(parent)] = self.shades.get(id(parent), 0) + 1
    step = (n * self.GOLDEN) % 1.0
    sub["vis/fillColor"] = self._hex(hue, 0.12 + 0.6 * step, 1.0 - 0.15 * step)
    sub["vis/borderColor"] = self._hex(hue, 0.85, 0.55 - 0.25 * step)

def outputPaths(xmlPath:str) -> tuple[str, str, str]:
  '''
  :param xmlPath: The XML file, eg: "/a/b/books.xml".
  :returns: The model, view and ontology files made from it: in the same
    folder, named "<name>_<ext>": eg: "/a/b/books_xml.snm", "/a/b/books_xml.snv"
    and "/a/b/books_xml_ontology.snm" (see *ontologyPath()*).
  '''
  folder, file = os.path.split(os.path.abspath(xmlPath))
  name, ext = os.path.splitext(file)
  base = os.path.join(folder, f"{name}_{ext[1:]}" if ext else name)
  return base + ".snm", base + ".snv", ontologyPath(base + ".snm")

def ontologyPath(modelPath:str) -> str:
  '''
  :param modelPath: A model's file, eg: "/a/b/books_xml.snm".
  :returns: Its ontology's file, beside it: eg: "/a/b/books_xml_ontology.snm".
  '''
  base, ext = os.path.splitext(modelPath)
  return f"{base}_ontology{ext or '.snm'}"

def localName(name:str) -> str:
  '''
  :param name: A tag or attribute name, perhaps with a namespace (eg: "{http://...}book").
  :returns: The name without its namespace (eg: "book").
  '''
  return name.rsplit("}", 1)[-1]

def attributeKey(name:str) -> str:
  '''
  :param name: An XML attribute's name (without a namespace).
  :returns: The attribute's name in the model: *name* -- or "xml/<name>" if
    Semantic Nets uses *name* for something else (see *RESERVED*).
  '''
  return f"xml/{name}" if name in RESERVED or name.startswith(RESERVED_PREFIXES) else name

def makeOntology(path:str) -> tuple[Model, Relation]:
  '''
  :param path: The ontology's file: it mustn't exist yet.
  :returns: A new ontology (not saved) with what every XML file's has --
    *HAS_PART*, *PART_OF*, and the definition of *PART_OF* as its inverse --
    and its *HAS_PART*.
  '''
  o = Model(path)
  hasPart = makeHasPart(o)
  makePartOf(o, hasPart)
  return o, hasPart

def makeHasPart(o:Model) -> Relation:
  '''
  :param o: An ontology.
  :returns: A new *HAS_PART* in it.
  '''
  hasPart = Relation(o, [o.RELATION], None, None, name=HAS_PART)
  hasPart.setAttr("note", Attribute("From an element to each element directly in it. Each has-<tag> is a kind of it.", "text", VAR_DEFAULTED))
  return hasPart

def makePartOf(o:Model, hasPart:Relation) -> Relation:
  '''
  :param o: An ontology.
  :param hasPart: Its *HAS_PART*.
  :returns: A new *PART_OF* in it, with its definition: the inverse of *hasPart*.
  '''
  partOf = Relation(o, [o.RELATION], None, None, name=PART_OF)
  partOf.setAttr("note", Attribute(f"From an element to the element it's directly in: the inverse of {HAS_PART} (see its definition).", "text", VAR_DEFAULTED))
  d = Node(o, [o.DEFINITION], individual=True, name=f"{PART_OF} def")
  d["note"] = f"?a -{PART_OF}-> ?b means ?b -{HAS_PART}-> ?a: each is concluded from the other."
  def var(name:str) -> Node:
    return Node(o, [o.NODE], individual=True, name=name)
  A, B = var("?a"), var("?b")
  for x in (A, B, Relation(o, [partOf], A, B, individual=True)):
    Relation(o, [o.DEFINIENDUM], d, x, individual=True)
  A2, B2 = var("?a"), var("?b")
  for x in (A2, B2, Relation(o, [hasPart], B2, A2, individual=True)):
    Relation(o, [o.DEFINIENS], d, x, individual=True)
  return partOf

def typesByName(o:Model) -> tuple[dict[str, list[Node]], dict[str, list[Relation]]]:
  '''
  :param o: An ontology.
  :returns: Its node types, and its relation types, by name (each name's in
    the order they were made). (Its own: not its super-models'.)
  '''
  nodes:dict[str, list[Node]] = {}
  relations:dict[str, list[Relation]] = {}
  for t in sorted((t for t in o.values() if isinstance(t, (Node, Relation)) and t.model is o and t.isType()), key=lambda t: t._id):
    if isinstance(t, Relation):
      relations.setdefault(str(t.name), []).append(t)
    else:
      nodes.setdefault(str(t.name), []).append(t)
  return nodes, relations

def kindOf(elem:ET.Element) -> str|None:
  '''
  :param elem: An element.
  :returns: The subtype of its tag's type its individual is one of (see
    *TYPE_ATTRIBUTES*), if any.
  '''
  attrs = {localName(k): v for k, v in elem.attrib.items()}
  kind = next((attrs[a] for a in TYPE_ATTRIBUTES if attrs.get(a)), None)
  return kind if kind != localName(elem.tag) else None

def buildModel(xmlPath:str, modelPath:str, ontology:Model|None=None) -> tuple[Model, Model]:
  '''
  Make a model of the XML file *xmlPath* (as described in the module doc), as
  a new model file *modelPath*, and its ontology, beside it (see
  *ontologyPath()*): its super-model -- or build on *ontology*, adding to it
  what's missing (see the module doc). (Neither's saved: call their *save()*.)

  :param xmlPath: The XML file.
  :param modelPath: The model's file: it mustn't exist yet (nor, unless
    *ontology* is given, the ontology's).
  :param ontology: An ontology made before (eg: for the same file, and read
    from its file), to build on; or None, to make one.
  :returns: The model, and its ontology.
  :raises xml.etree.ElementTree.ParseError: if the file isn't well-formed XML.
  '''
  root = ET.parse(xmlPath).getroot() # (parse first: if it isn't XML, nothing is made)
  added:list[str] = [] # (what's made in an ontology made before)
  made:set[int] = set() # (the ids of the types made here: their attributes aren't in *added*)
  if ontology is None:
    o, hasPart = makeOntology(ontologyPath(modelPath))
    nodesByName:dict[str, list[Node]] = {}
    relationsByName:dict[str, list[Relation]] = {}
  else:
    o = ontology
    nodesByName, relationsByName = typesByName(o)
    found = relationsByName.get(HAS_PART)
    if found:
      hasPart = found[0]
    else:
      hasPart = makeHasPart(o)
      added.append(HAS_PART)
    if PART_OF not in relationsByName:
      makePartOf(o, hasPart)
      added.append(f"{PART_OF} (and its definition)")
  m = Model(modelPath)
  m.setSuperModels([o.url])
  kinds = {(localName(e.tag), k) for e in root.iter() if isinstance(e.tag, str) and (k := kindOf(e)) is not None}
  types:dict[str, Node] = {}                 # tag -> its type
  typeAttributes:dict[str, set[str]] = {}     # tag -> the attribute keys its type has
  relationTypes:dict[str, Relation] = {}      # tag -> has-<tag>
  subtypes:dict[tuple[str, str], Node] = {}   # (tag, type attribute's value) -> the subtype
  counts:dict[str, int] = {}                  # tag -> how many of its individuals so far
  looks = TypeLooks(os.path.basename(xmlPath))

  def findType(tag:str) -> Node|None:
    candidates = nodesByName.get(tag, [])
    # (not one that's a kind of a type named for a tag which has elements whose type is this tag: that's
    # probably their subtype -- eg: <object type="book"> and <book>: book isa object is the subtype)
    def subtypeLike(c:Node) -> bool:
      return any(str(s.name) == t2 for s in c.getSupers() for t2, k in kinds if k == tag)
    return next((c for c in candidates if not subtypeLike(c)), candidates[0] if candidates else None)

  def typeFor(tag:str) -> Node:
    if tag not in types:
      t = findType(tag)
      if t is not None:
        looks.reuse(t)
      else:
        t = Node(o, [o.NODE], name=tag)
        t.setAttr("note", Attribute(f"The type of the <{tag}> elements in {os.path.basename(xmlPath)}.", "text", VAR_DEFAULTED))
        looks.apply(t) # (the tags' types are all directly under node; their subtypes are shaded: see subtypeFor())
        made.add(id(t))
        if ontology is not None:
          added.append(tag)
      types[tag] = t
      typeAttributes[tag] = set()
    return types[tag]

  def subtypeFor(tag:str, value:str) -> Node:
    if (tag, value) not in subtypes: # (per tag: <a type="x"> and <b type="x"> are different kinds of thing)
      parent = types[tag]
      sub = next((c for c in nodesByName.get(value, []) if c is not parent and c.isa(parent)), None)
      if sub is not None:
        looks.reuseShade(parent)
      else:
        sub = Node(o, [parent], name=value)
        sub["note"] = f'The type of the <{tag}> elements in {os.path.basename(xmlPath)} whose type is "{value}".' # (note is defined by parent)
        looks.applyShade(sub, parent)
        if ontology is not None:
          added.append(f"{value} (a kind of {parent.name})")
      subtypes[(tag, value)] = sub
    return subtypes[(tag, value)]

  def addTypeAttribute(tag:str, key:str, note:str) -> None:
    if key not in typeAttributes[tag]:
      t = types[tag]
      if key not in t: # (not if it has it already, or inherits it: eg: in an ontology made before)
        t.setAttr(key, Attribute("", str, VAR_DEFAULTED, note))
        if ontology is not None and id(t) not in made:
          added.append(f"{tag}'s attribute {key}")
      typeAttributes[tag].add(key)

  def relationTypeFor(tag:str) -> Relation:
    if tag not in relationTypes:
      found = relationsByName.get(f"has-{tag}")
      if found:
        relationTypes[tag] = found[0]
        rng = found[0].range
        if rng is not None and not types[tag].isa(rng): # (eg: the tag's type was renamed, and made afresh)
          logger.warning(f'In {os.path.basename(o.url)}, has-{tag}\'s range is {rng.name}, which {types[tag].name} '
                         f'isn\'t a kind of: the reasoner will say each <{tag}> is out of range. Change has-{tag}\'s range, '
                         f'or make {types[tag].name} a kind of {rng.name}.')
      else: # (from anything -- the same tag may be nested in several -- to the tag's type)
        relationTypes[tag] = Relation(o, [hasPart], None, types[tag], name=f"has-{tag}")
        if ontology is not None:
          added.append(f"has-{tag}")
    return relationTypes[tag]

  def individualFor(elem:ET.Element) -> Node:
    tag = localName(elem.tag)
    t = typeFor(tag)
    attrs = {localName(k): v for k, v in elem.attrib.items()}
    counts[tag] = counts.get(tag, 0) + 1
    name = next((attrs[a] for a in NAMING_ATTRIBUTES if attrs.get(a)), f"{tag}{counts[tag]}")
    kind = kindOf(elem)
    if kind is not None:
      t = subtypeFor(tag, kind)
    ind = Node(m, [t], individual=True, name=name)
    for k, v in attrs.items():
      key = attributeKey(k)
      addTypeAttribute(tag, key, f'The "{k}" attribute of <{tag}> elements.')
      ind[key] = v
    text = (elem.text or "").strip()
    if text:
      addTypeAttribute(tag, "text", f"The text of a <{tag}> element.")
      ind["text"] = text
    for child in elem:
      if not isinstance(child.tag, str): # (eg: a comment or processing instruction, if the parser keeps them)
        continue
      c = individualFor(child)
      Relation(m, [relationTypeFor(localName(child.tag))], ind, c, individual=True)
    return ind

  individualFor(root)
  if added: # (something the XML has that the ontology hadn't -- or one renamed or deleted since)
    logger.info(f"Added to {os.path.basename(o.url)}, which hadn't them: " + ", ".join(added) + ".")
  return m, o
