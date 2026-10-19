'''
Turn an XML file into a Semantic Nets model (see *buildModel()*), built on an
ontology of its own: a second model, a super-model of the first, which has the
types and the definitions -- so there's one place to change the type hierarchy,
add rules, and so on. The model has the elements.

What each tag and attribute is -- a node tag, a property, a group, a list
holder, an annotation, a kind, a reference -- is inferred from how they're
used throughout the file (see *schema*). Then:

  - Each node tag becomes a type (a node isa *node*), the first time it's
    seen, with a look of its own (see *TypeLooks*), which its individuals
    inherit, and a tooltip listing its properties (see *tooltip()*).
  - Each of its elements becomes an individual of its tag's type -- or, if its
    tag has a kind field (see *schema*), of a subtype of the tag's type named
    by its value (eg: <book kind="novel"> is an individual of *novel*, which
    isa *book*), made the first time it's seen. Subtypes look like their tag's
    type, in a different shade.
  - Its fields -- its XML attributes, and its property subelements (and those
    in its groups) -- become its individual's attributes, "property/<name>",
    of the datatype their values are; its type has each (with no value), with
    a note saying where it's from.
  - Its text (if it isn't just white space) becomes its individual's "text"
    attribute.
  - A nested node element's individual is related to its containing element's
    by a relation of type "has-<tag>" (eg: a book element's *has-chapter*
    relations to its chapters); a list holder's elements, by "has-<holder>"
    (eg: has-DeviceList, to each device). Each is a kind of *xml-has-part*
    (see *HAS_PART*), so the elements' tree is there whatever the tags.
  - *xml-part-of* (see *PART_OF*) is the other way round: it's defined (a
    definition in the ontology) as [?a -xml-part-of-> ?b] <-> [?b -xml-has-part-> ?a],
    so the reasoner concludes it.
  - A reference field (eg: DeviceID) also relates the individual to the one
    it refers to, by a relation named for the field: a kind of *xml-refers-to*
    (see *REFERS_TO*).
  - An individual is named by its name, title, label, id or key field, or its
    short text (see *schema.Schema.nameOf()*); otherwise by its tag and a
    number (eg: chapter1, chapter2, ...).

Namespaces are dropped from tag and attribute names (eg: "{http://...}book"
becomes "book").

The ontology can be one made before, for the same file (eg: by reading it
again, after changing the ontology: moving types about, adding rules, ...),
or for files of the same kind (one ontology, shared by their models):
*buildModel()* builds on it, and adds only what's missing -- to it, or, if
it can't be changed (eg: it's on the web: see *canChange()*), to the model
(an attribute its types haven't is then just in the elements). What's in it
is found by name:

  - a tag's type, by the tag (any node type of that name: wherever it is in
    the type hierarchy);
  - a subtype, by its "type" or "kind" attribute's value: one of that name
    that's a kind of its tag's type (at any depth: eg: under another subtype);
  - has-<tag>, has-<holder>, a reference's field, *HAS_PART*, *PART_OF* and
    *REFERS_TO*, by name (relation types);
  - what the tags are, as far as it says (see *hintsFrom()*): a tag with a
    type there is a node tag, and one a type there has a property for is a
    property.

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
from urllib.parse import unquote, urlparse
import sn
from sn.model.model import GraphObject, Model, Node, Relation
from util.attribute import Attribute, VAR_DEFAULTED
from .schema import Schema, Hints, Field, PROPERTY, attributes, children, convert, elements, localName, text

HAS_PART = "xml-has-part"
"The relation type every has-<tag> is a kind of: from an element to each element in it."

PART_OF = "xml-part-of"
"The relation type defined as the inverse of *HAS_PART*: from an element to the element it's in."

REFERS_TO = "xml-refers-to"
"The relation type every reference's is a kind of: from an element to one a field of it identifies (see *schema*)."

logger:sn.SNLogger = sn.getLogger(__name__)

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

def isRemote(ref:str) -> bool:
  '''
  :param ref: A model's file or URL.
  :returns: Whether it's on the web (eg: "https://..."): it can be read, but not saved there.
  '''
  return urlparse(ref).scheme in ("http", "https")

def localPath(ref:str) -> str|None:
  '''
  :param ref: A model's file or URL.
  :returns: Its file, if it's one here (a path, or a "file:" URL); else None.
  '''
  parsed = urlparse(ref)
  if parsed.scheme == "file":
    return unquote(parsed.path)
  return None if parsed.scheme and len(parsed.scheme) > 1 else os.path.abspath(os.path.expanduser(ref)) # (a drive letter isn't a scheme)

def canChange(ref:str) -> bool:
  '''
  :param ref: An ontology's file or URL.
  :returns: Whether it can be changed, and saved: it's a file here that can be
    written (or, if it isn't there yet, can be made) -- not on the web, say.
  '''
  path = localPath(ref)
  if path is None:
    return False
  return os.access(path, os.W_OK) if os.path.exists(path) else os.access(os.path.dirname(path) or ".", os.W_OK)

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

def makeRefersTo(o:Model) -> Relation:
  '''
  :param o: An ontology.
  :returns: A new *REFERS_TO* in it.
  '''
  refersTo = Relation(o, [o.RELATION], None, None, name=REFERS_TO)
  refersTo.setAttr("note", Attribute("From an element to one a field of it identifies (eg: by its id). "
                                     "Each reference field's relation type is a kind of it.", "text", VAR_DEFAULTED))
  return refersTo

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

def hintsFrom(o:Model, tags:set[str]) -> Hints:
  '''
  :param o: An ontology made before.
  :param tags: The XML file's tags.
  :returns: What it says about the tags (see *schema.Hints*): its node types'
    names (not those that are a kind of a type named as a tag: they're
    probably subtypes -- eg: <object type="book">), the properties its types
    have ("property/<tag>"), and its references (relation types that are
    kinds of *REFERS_TO*).
  '''
  nodes, relations = typesByName(o)
  def tagType(t:Node) -> bool:
    return not any(str(s.name) in tags for s in t.getSupers() if s is not t)
  hints = Hints(nodes={n for n, ts in nodes.items() if any(tagType(t) for t in ts)})
  for ts in nodes.values():
    for t in ts:
      for k in t.keys():
        if t.getLocalAttr(k) is not None and k.startswith(PROPERTY) and "/" not in k[len(PROPERTY):] and not k[len(PROPERTY):].startswith("@"):
          hints.properties.add(k[len(PROPERTY):])
  hints.properties -= hints.nodes
  refersTo = relations.get(REFERS_TO, [])
  hints.references = {n for n, rs in relations.items() if any(r.isa(x) and r is not x for r in rs for x in refersTo)}
  return hints

def tooltip(t:Node, order:list[str]=[]) -> str:
  '''
  :param t: A tag's type.
  :param order: Properties in the order to list them (eg: as they are in the
    XML): those it has that aren't in it are after them, by name.
  :returns: A tooltip template (see *sn.view.graphics.labels*) for its
    elements: their name and type, and each of the properties it has (see
    *schema.PROPERTY*) that they have a value for.
  '''
  has = {k for k in t.keys() if k.startswith(PROPERTY)}
  keys = list(dict.fromkeys(k for k in order if k in has)) + sorted(has - set(order))
  return "$name ($type)" + "".join(f"${{{k}:+\\n{k[len(PROPERTY):]}: ${{{k}}}}}" for k in keys)

def buildModel(xmlPath:str, modelPath:str, ontology:Model|str|None=None, extendOntology:bool=True,
               found:list[str]|None=None) -> tuple[Model, Model]:
  '''
  Make a model of the XML file *xmlPath* (as described in the module doc), as
  a new model file *modelPath*, and its ontology (beside it, unless *ontology*
  says where: see *ontologyPath()*): its super-model -- or build on *ontology*, adding to it
  what's missing (see the module doc), or, if it can't be changed, putting
  that in the model. (Neither's saved: call their *save()*.)

  :param xmlPath: The XML file.
  :param modelPath: The model's file: it mustn't exist yet (nor the ontology's, if one's made).
  :param ontology: An ontology made before (eg: for the same file, or one
    shared by files of the same kind, read from its file or URL), to build
    on; or the file to make one in; or None, to make one beside the model.
  :param extendOntology: Whether what *ontology* is missing goes in it: if
    not -- or if it's write-locked (eg: it's on the web: see
    *Model._wasRead()*) -- it goes in the model (types, has-<tag>s, ...), and
    an attribute its types haven't is just in their elements. (See *canChange()*.)
  :param found: If given, what the tags were found to be (see *schema.Schema.report()*) is added to it.
  :returns: The model, and its ontology.
  :raises xml.etree.ElementTree.ParseError: if the file isn't well-formed XML.
  '''
  root = ET.parse(xmlPath).getroot() # (parse first: if it isn't XML, nothing is made)
  file = os.path.basename(xmlPath)
  added:list[str] = [] # (what's made for an ontology made before)
  made:set[int] = set() # (the ids of the types made here: their attributes aren't in *added*)
  if not isinstance(ontology, Model):
    o, hasPart = makeOntology(ontology or ontologyPath(modelPath))
    ontology = None # (so what's made isn't "added")
    nodesByName:dict[str, list[Node]] = {}
    relationsByName:dict[str, list[Relation]] = {}
  else:
    o = ontology
    nodesByName, relationsByName = typesByName(o)
  schema = Schema(root, hintsFrom(o, {localName(e.tag) for e in elements(root)}) if ontology is not None else None)
  logger.debug(f"{file}: {schema.report()}.")
  if found is not None:
    found.append(schema.report())
  m = Model(modelPath)
  m.setSuperModels([o.url])
  into = o if ontology is None or (extendOntology and not o.writeLocked()) else m # (where what's made goes)
  if ontology is not None:
    haveHasPart = relationsByName.get(HAS_PART)
    if haveHasPart:
      hasPart = haveHasPart[0]
    else:
      hasPart = makeHasPart(into)
      added.append(HAS_PART)
    if PART_OF not in relationsByName:
      makePartOf(into, hasPart)
      added.append(f"{PART_OF} (and its definition)")
  refersTo:Relation|None = next(iter(relationsByName.get(REFERS_TO, [])), None)
  unchanged:list[str] = [] # (attributes its types haven't, which the ontology can't be given)
  kinds = {(localName(e.tag), k) for e in elements(root) if schema.isNode(localName(e.tag)) and (k := schema.kindOf(e)) is not None}
  types:dict[str, Node] = {}                 # tag -> its type
  typeAttributes:dict[str, dict[str, None]] = {} # tag -> the attribute keys its type has (in the order they're first seen)
  relationTypes:dict[str, Relation] = {}      # has-<tag>, or a reference's field -> the relation type
  subtypes:dict[tuple[str, str], Node] = {}   # (tag, kind) -> the subtype
  counts:dict[str, int] = {}                  # tag -> how many of its individuals so far
  individuals:dict[int, Node] = {}            # id(element) -> its individual
  pending:list[tuple[Node, str, str, ET.Element]] = [] # (individual, tag, field, the element its value identifies): references
  looks = TypeLooks(file)

  def findType(tag:str) -> Node|None:
    candidates = nodesByName.get(tag, [])
    # (not one that's a kind of a type named for a tag which has elements whose kind is this tag: that's
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
        t = Node(into, [into.NODE], name=tag)
        note = f"The type of the <{tag}> elements in {file}."
        if schema.tagAnnotations.get(tag):
          note += " Their XML attributes say: " + ", ".join(f'{a}="{v}"' for a, v in schema.tagAnnotations[tag].items()) + "."
        t.setAttr("note", Attribute(note, "text", VAR_DEFAULTED))
        looks.apply(t) # (the tags' types are all directly under node; their subtypes are shaded: see subtypeFor())
        made.add(id(t))
        if ontology is not None:
          added.append(tag)
      types[tag] = t
      typeAttributes[tag] = {}
    return types[tag]

  def subtypeFor(tag:str, value:str) -> Node:
    if (tag, value) not in subtypes: # (per tag: <a type="x"> and <b type="x"> are different kinds of thing)
      parent = types[tag]
      sub = next((c for c in nodesByName.get(value, []) if c is not parent and c.isa(parent)), None)
      if sub is not None:
        looks.reuseShade(parent)
      else:
        sub = Node(into, [parent], name=value)
        sub["note"] = f'The type of the <{tag}> elements in {file} whose {schema.kinds[tag].name} is "{value}".' # (note is defined by parent)
        looks.applyShade(sub, parent)
        if ontology is not None:
          added.append(f"{value} (a kind of {parent.name})")
      subtypes[(tag, value)] = sub
    return subtypes[(tag, value)]

  def addTypeAttribute(tag:str, key:str, typ:type, note:str) -> None:
    if key not in typeAttributes[tag]:
      t = types[tag]
      if key not in t: # (not if it has it already, or inherits it: eg: in an ontology made before)
        if t.model is not into: # (one found in an ontology that can't be changed)
          unchanged.append(f"{tag}'s {key}") # (its elements have it: just not their type)
        else:
          t.setAttr(key, Attribute("" if typ is str else None, typ, VAR_DEFAULTED, note))
          if ontology is not None and id(t) not in made:
            added.append(f"{tag}'s attribute {key}")
      typeAttributes[tag][key] = None

  def fieldNote(tag:str, f:Field) -> str:
    what = f'XML attribute "{f.name}"' if f.fromAttribute else f"<{'><'.join(f.path)}> subelement"
    note = f"The {what} of <{tag}> elements"
    if f.annotations:
      note += " (" + ", ".join(f'{a}="{v}"' for a, v in f.annotations.items()) + ")"
    return note + "."

  def relationTypeFor(name:str, parent:Relation, rng:Node|None) -> Relation:
    if name not in relationTypes:
      existing = relationsByName.get(name)
      if existing:
        relationTypes[name] = existing[0]
        have = existing[0].range
        if rng is not None and have is not None and not rng.isa(have): # (eg: the tag's type was renamed, and made afresh)
          logger.warning(f'In {os.path.basename(o.url)}, {name}\'s range is {have.name}, which {rng.name} '
                         f'isn\'t a kind of: the reasoner will say each is out of range. Change {name}\'s range, '
                         f'or make {rng.name} a kind of {have.name}.')
      else: # (from anything -- the same tag may be nested in several -- to the tag's type)
        relationTypes[name] = Relation(into, [parent], None, rng, name=name)
        if ontology is not None:
          added.append(name)
    return relationTypes[name]

  def referenceType(field:str, target:str|None) -> Relation:
    nonlocal refersTo
    if refersTo is None:
      refersTo = makeRefersTo(into)
      if ontology is not None:
        added.append(REFERS_TO)
    ranges = {t for (_, f), t in schema.references.items() if f == field}
    return relationTypeFor(field, refersTo, typeFor(target) if target is not None and ranges == {target} else None)

  def individualFor(elem:ET.Element) -> Node:
    tag = localName(elem.tag)
    t = typeFor(tag)
    counts[tag] = counts.get(tag, 0) + 1
    kind = schema.kindOf(elem)
    ind = Node(m, [subtypeFor(tag, kind) if kind is not None else t], individual=True,
               name=schema.nameOf(elem) or f"{tag}{counts[tag]}")
    individuals[id(elem)] = ind
    for f in schema.fields[tag].values():
      value = schema.fieldText(elem, f)
      if value is None:
        continue
      addTypeAttribute(tag, f.key, f.typ, fieldNote(tag, f))
      v = convert(value, f.typ)
      if v is not None:
        ind[f.key] = v #type: ignore[assignment]
      leaf = schema.fieldElement(elem, f)
      if leaf is not None:
        for k, x in schema.propertyExtras(f, leaf).items():
          addTypeAttribute(tag, k, str, f'An XML attribute of the <{"><".join(f.path)}> subelement of <{tag}> elements.')
          ind[k] = x
      if (tag, f.name) in schema.references and len(schema.identified.get(value, ())) == 1:
        pending.append((ind, tag, f.name, schema.identified[value][0][1]))
    own = text(elem)
    if own:
      addTypeAttribute(tag, "text", str, f"The text of a <{tag}> element.")
      ind["text"] = own
    for child in children(elem):
      ctag = localName(child.tag)
      if schema.isNode(ctag):
        Relation(m, [relationTypeFor(f"has-{ctag}", hasPart, typeFor(ctag))], ind, individualFor(child), individual=True)
      elif ctag in schema.holders: # (its elements are this one's, by has-<holder>)
        held = schema.holders[ctag]
        for g in children(child):
          Relation(m, [relationTypeFor(f"has-{ctag}", hasPart, typeFor(held))], ind, individualFor(g), individual=True)
      # (properties and groups: its fields, above)
    return ind

  individualFor(root)
  for ind, tag, field, target in pending: # (once every element's individual is made: they may refer to ones after them)
    to = individuals.get(id(target))
    if to is not None: # (not, if it's a property, say)
      Relation(m, [referenceType(field, schema.references[(tag, field)])], ind, to, individual=True)
  for tag, t in types.items(): # (a tooltip for each type made here: its properties)
    if t.model is into and id(t) in made and t.getLocal("vis/tooltip", None) is None:
      t["vis/tooltip"] = tooltip(t, [f.key for f in schema.fields[tag].values()] + list(typeAttributes[tag])) # (as in the XML)
  if added: # (something the XML has that the ontology hadn't -- or one renamed or deleted since)
    logger.info(f"Added to {os.path.basename(into.url)}" + ("" if into is o else f", as {os.path.basename(o.url)} can't be changed")
                + f", which hadn't them: " + ", ".join(added) + ".")
  if unchanged:
    logger.info(f"{os.path.basename(o.url)} can't be changed, so these attributes are just in the elements, "
                "not in their types: " + ", ".join(unchanged) + ".")
  return m, o
