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

Created on Oct 3, 2026

.. codeauthor:: Rob Kremer <robkremer@me.com>
'''
from __future__ import annotations
import colorsys
import os
import random
import xml.etree.ElementTree as ET
from sn.model.model import Model, Node, Relation
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
  shade of its own.
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

  def apply(self, t:Node) -> None:
    '''
    Give the type *t* the next look: a light fill, a dark border of the same
    hue, and a shape.

    :param t: A type.
    '''
    self.hue += self.GOLDEN
    self.hues[id(t)] = self.hue
    t["vis/fillColor"] = self._hex(self.hue, self.random.uniform(0.25, 0.45), self.random.uniform(0.92, 1.0))
    t["vis/borderColor"] = self._hex(self.hue, 0.8, self.random.uniform(0.45, 0.6))
    t["vis/shape"] = self.random.choice(SHAPES)

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
    if hue is None: # (not one of ours)
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
  hasPart = Relation(o, [o.RELATION], None, None, name=HAS_PART)
  hasPart.setAttr("note", Attribute("From an element to each element directly in it. Each has-<tag> is a kind of it.", "text", VAR_DEFAULTED))
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
  return o, hasPart

def buildModel(xmlPath:str, modelPath:str) -> tuple[Model, Model]:
  '''
  Make a model of the XML file *xmlPath* (as described in the module doc), as
  a new model file *modelPath*, and its ontology, beside it (see
  *ontologyPath()*): its super-model. (Neither's saved: call their *save()*.)

  :param xmlPath: The XML file.
  :param modelPath: The model's file: neither it nor the ontology's may exist yet.
  :returns: The model, and its ontology.
  :raises xml.etree.ElementTree.ParseError: if the file isn't well-formed XML.
  '''
  root = ET.parse(xmlPath).getroot() # (parse first: if it isn't XML, nothing is made)
  o, hasPart = makeOntology(ontologyPath(modelPath))
  m = Model(modelPath)
  m.setSuperModels([o.url])
  types:dict[str, Node] = {}                 # tag -> its type
  typeAttributes:dict[str, set[str]] = {}     # tag -> the attribute keys its type has
  relationTypes:dict[str, Relation] = {}      # tag -> has-<tag>
  subtypes:dict[tuple[str, str], Node] = {}   # (tag, type attribute's value) -> the subtype
  counts:dict[str, int] = {}                  # tag -> how many of its individuals so far
  looks = TypeLooks(os.path.basename(xmlPath))

  def typeFor(tag:str) -> Node:
    if tag not in types:
      t = Node(o, [o.NODE], name=tag)
      t.setAttr("note", Attribute(f"The type of the <{tag}> elements in {os.path.basename(xmlPath)}.", "text", VAR_DEFAULTED))
      looks.apply(t) # (the tags' types are all directly under node; their subtypes are shaded: see subtypeFor())
      types[tag] = t
      typeAttributes[tag] = set()
    return types[tag]

  def subtypeFor(tag:str, value:str) -> Node:
    if (tag, value) not in subtypes: # (per tag: <a type="x"> and <b type="x"> are different kinds of thing)
      parent = types[tag]
      sub = Node(o, [parent], name=value)
      sub["note"] = f'The type of the <{tag}> elements in {os.path.basename(xmlPath)} whose type is "{value}".' # (note is defined by parent)
      looks.applyShade(sub, parent)
      subtypes[(tag, value)] = sub
    return subtypes[(tag, value)]

  def addTypeAttribute(tag:str, key:str, note:str) -> None:
    if key not in typeAttributes[tag]:
      types[tag].setAttr(key, Attribute("", str, VAR_DEFAULTED, note))
      typeAttributes[tag].add(key)

  def relationTypeFor(tag:str) -> Relation:
    if tag not in relationTypes: # (from anything -- the same tag may be nested in several -- to the tag's type)
      relationTypes[tag] = Relation(o, [hasPart], None, types[tag], name=f"has-{tag}")
    return relationTypes[tag]

  def individualFor(elem:ET.Element) -> Node:
    tag = localName(elem.tag)
    t = typeFor(tag)
    attrs = {localName(k): v for k, v in elem.attrib.items()}
    counts[tag] = counts.get(tag, 0) + 1
    name = next((attrs[a] for a in NAMING_ATTRIBUTES if attrs.get(a)), f"{tag}{counts[tag]}")
    kind = next((attrs[a] for a in TYPE_ATTRIBUTES if attrs.get(a)), None)
    if kind is not None and kind != tag:
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
  return m, o
