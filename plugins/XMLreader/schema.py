'''
What an XML file's tags and attributes are (see *Schema*), inferred from how
they're used throughout the file -- not from their names, except as hints --
so the reader (see *reader.buildModel()*) can make a model that matches what
the file means:

  - **Property** tags: a tag with no subelements, that's never repeated within
    any element it's in (eg: <title> in a <book>), is a property of the element
    it's in -- an attribute of its individual, "property/<tag>" -- not an
    individual of its own. Its value is its text; or, if it has none, its
    attribute, if it has just one (eg: <author name="Hofstadter"/>).
  - **Groups**: likewise, a tag that's never repeated within an element, has
    no text nor attributes of its own, and holds only properties and groups
    (eg: <States> in a <Device>), is part of the element it's in: what it
    holds are properties of that element, "property/<group>/<tag>".
  - **Node** tags: every other tag -- one that has subelements, or is repeated
    in an element -- is a type, and each of its elements an individual.
  - **List holders**: a node tag whose elements hold nothing but elements of
    one other node tag (eg: <DeviceList> holding <Device>s) isn't made: the
    element it's in has the elements it holds, by a relation named for it
    (has-DeviceList).
  - **Annotations**: an XML attribute that's on several tags (with more than
    one element), and has the same value on all the elements of almost every
    one of them, from only a few values (eg: type="integer"), says what the
    tag is, not what each element is: it's noted on the type (or the
    property), not given to each element.
  - **Fields**: the rest of a node element's XML attributes, and its property
    subelements, are its fields: "property/<name>" (a subelement's wins: an
    attribute of the same name is "property/@<name>"). A property's own
    attributes, besides its value, are "property/<tag>/<attribute>".
  - **Datatypes**: a field whose values are all integers (or all numbers, or
    all true or false) is one: its values are stored as such.
  - **Kinds**: a node tag's field whose name says it's a kind (it has "type",
    "kind", "category" or "class" in it), whose values are names (not numbers)
    that recur, makes a subtype of the tag's type for each value (eg:
    <book kind="novel">, or <Device><TypeName>Dimmer</TypeName>...).
  - **Names**: an element's individual is named by its field called name,
    title, label, id, key or identifier (the first it has, ignoring case); or
    by its text, if that's short; or by its tag and a number.
  - **References**: a field called id (or identifier, key, uuid, guid) is an
    identifier; a field whose name ends in id or ref (eg: DeviceID, ref),
    most of whose values are identifiers, refers to the elements they identify:
    its values become relations too, named for the field.

What an ontology made before says (see *Hints*) wins: eg: a tag that's a type
there stays a node tag, and one that's a property of a type there stays a
property.

Created on Oct 19, 2026

.. codeauthor:: Rob Kremer <robkremer@me.com>
'''
from __future__ import annotations
import re
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Iterator

PROPERTY = "property/"
"The prefix of the attributes made of fields (see the module doc)."

NAMING = ("name", "title", "label", "id", "key", "identifier")
"The fields an element's individual is named by (the first it has, ignoring case), in order."

IDENTIFIERS = ("id", "identifier", "key", "uuid", "guid")
"The fields that identify an element, for references to it (ignoring case)."

REFERENCE = re.compile(r"(id|ref|idref)$", re.IGNORECASE)
"A field whose name matches this may refer to elements (see the module doc)."

KIND = re.compile(r"type|kind|category|class", re.IGNORECASE)
"A field whose name matches this may say what kind of thing an element is (see the module doc)."

KIND_DIFFERENT = 5
"A field whose values are all different, and there are more than this many, isn't a kind (they're names)."

SHORT_TEXT = 40
"An element's text up to this long (and on one line) names its individual, if nothing else does."

ANNOTATION_TAGS = 3
"An attribute on fewer tags than this (with more than one element) isn't an annotation."

ANNOTATION_CONSTANT = 0.9
"The share of an annotation's tags whose elements all have the same value for it."

def localName(name:str) -> str:
  '''
  :param name: A tag or attribute name, perhaps with a namespace (eg: "{http://...}book").
  :returns: The name without its namespace (eg: "book").
  '''
  return name.rsplit("}", 1)[-1]

def elements(root:ET.Element) -> Iterator[ET.Element]:
  ''':returns: The elements under *root* (and it), not comments or processing instructions.'''
  return (e for e in root.iter() if isinstance(e.tag, str))

def children(elem:ET.Element) -> list[ET.Element]:
  ''':returns: The elements directly in *elem*.'''
  return [c for c in elem if isinstance(c.tag, str)]

def attributes(elem:ET.Element) -> dict[str, str]:
  ''':returns: *elem*'s XML attributes, without their namespaces.'''
  return {localName(k): v for k, v in elem.attrib.items()}

def text(elem:ET.Element) -> str:
  ''':returns: *elem*'s own text, without the white space round it.'''
  return (elem.text or "").strip()

def datatype(values:Iterator[str]|list[str]) -> type:
  '''
  :param values: A field's values (empty ones are ignored).
  :returns: int, if they're all integers (not "007": that's a name); float, if
    they're all numbers (likewise); bool, if they're all true or false; else str.
  '''
  vs = [v for v in values if v != ""]
  if not vs:
    return str
  if all(re.fullmatch(r"-?(0|[1-9]\d*)", v) for v in vs):
    return int
  if all(re.fullmatch(r"-?((0|[1-9]\d*)(\.\d*)?|\.\d+)([eE][-+]?\d+)?", v) for v in vs):
    return float
  if all(v.lower() in ("true", "false") for v in vs):
    return bool
  return str

def convert(value:str, typ:type) -> object:
  '''
  :param value: A field's value, as in the XML.
  :param typ: Its field's datatype (see *datatype()*).
  :returns: *value* as one of *typ* (None if it's empty and *typ* isn't str).
  '''
  if typ is str:
    return value
  if value == "":
    return None
  if typ is bool:
    return value.lower() == "true"
  return typ(value)

NO_FIT = object()
"What *fit()* returns for a value that isn't one of the type asked for."

def fit(value:str, typ:object) -> object:
  '''
  :param value: A field's value, as in the XML.
  :param typ: The datatype of the attribute it's to be (eg: an ontology's,
    made from another file): a type, or a name of one (eg: "text": see
    *util.attribute.TYPE_EQUIVALENTS*).
  :returns: *value* as one of *typ*, if it can be without losing anything
    (eg: "20" as a float, or "20.0" as an int; anything as a string; None if
    it's empty, and *typ* isn't a string type); else *NO_FIT* (eg: "20.5" as
    an int).
  '''
  from util.attribute import TYPE_EQUIVALENTS
  py = TYPE_EQUIVALENTS.get(typ) if isinstance(typ, str) else typ
  if py is str:
    return value
  if value == "":
    return None
  if py is bool:
    return value.lower() == "true" if value.lower() in ("true", "false") else NO_FIT
  if py is int or py is float:
    try:
      number = int(value) if py is int and re.fullmatch(r"-?\d+", value) else float(value)
    except ValueError:
      return NO_FIT
    if py is float:
      return float(number)
    return int(number) if float(number).is_integer() else NO_FIT
  return NO_FIT

@dataclass
class Hints:
  '''
  What an ontology made before says about the tags (see *Schema*): it wins
  over what's inferred.
  '''
  nodes:set[str] = field(default_factory=set)
  "Tags that have a type: node tags."
  properties:set[str] = field(default_factory=set)
  "Tags that are a property of a type (it has a \"property/<tag>\" attribute), and haven't a type: property tags."
  references:set[str] = field(default_factory=set)
  "Fields that have a reference relation type."

@dataclass
class Field:
  '''
  A field of a node tag's elements (see the module doc): one of its XML
  attributes, or one of its property subelements.
  '''
  name:str
  "Its name: the attribute's or the subelement's."
  key:str
  'The attribute its individuals have: "property/<name>" (or "property/@<name>": see the module doc).'
  fromAttribute:bool
  "Whether it's an XML attribute (else it's a subelement)."
  path:tuple[str, ...] = ()
  "For a subelement: the tags down to it: eg: (\"States\", \"onOffState\") for one in a group (see the module doc)."
  typ:type = str
  "Its values' datatype (see *datatype()*)."
  annotations:dict[str, str] = field(default_factory=dict)
  "For a subelement: its annotations (see the module doc), and their values: eg: {\"type\": \"integer\"}."

class Schema:
  '''
  What the tags and attributes of an XML file are: see the module doc.
  '''
  def __init__(self, root:ET.Element, hints:Hints|None=None):
    '''
    :param root: The file's root element.
    :param hints: What an ontology made before says, if there is one.
    '''
    hints = hints or Hints()
    self.root:str = localName(root.tag)
    "The root element's tag."
    occurrences:Counter[str] = Counter()
    hasChildren:set[str] = set()
    hasText:set[str] = set()
    repeated:set[str] = set()                  # tags repeated in an element
    childTags:dict[str, set[str]] = defaultdict(set)
    attrValues:dict[str, dict[str, Counter[str]]] = defaultdict(lambda: defaultdict(Counter)) # attribute -> tag -> values
    self._order:dict[str, int] = {}             # tag -> where it's first seen
    for e in elements(root):
      tag = localName(e.tag)
      self._order.setdefault(tag, len(self._order))
      occurrences[tag] += 1
      if text(e):
        hasText.add(tag)
      inIt = Counter(localName(c.tag) for c in children(e))
      if inIt:
        hasChildren.add(tag)
        childTags[tag].update(inIt)
        repeated.update(t for t, n in inIt.items() if n > 1)
      for a, v in attributes(e).items():
        attrValues[a][tag][v] += 1
    self.occurrences:Counter[str] = occurrences
    "How many elements each tag has."

    # annotations: on several tags with more than one element (else it's the same on all of them, trivially), on almost
    # all of which it's the same on every element, from a few values
    self.annotations:set[str] = set()
    "The XML attributes that are annotations (see the module doc)."
    for a, byTag in attrValues.items():
      evidence = [vs for t, vs in byTag.items() if occurrences[t] > 1]
      if len(evidence) < ANNOTATION_TAGS:
        continue
      constant = sum(1 for t, vs in byTag.items() if occurrences[t] > 1 and len(vs) == 1 and sum(vs.values()) == occurrences[t])
      distinct = set().union(*(vs.keys() for vs in byTag.values()))
      if constant >= ANNOTATION_CONSTANT * len(evidence) and len(distinct) <= max(3, len(byTag) // 2):
        self.annotations.add(a)
    self.tagAnnotations:dict[str, dict[str, str]] = defaultdict(dict)
    "Each tag's annotations that have the same value on all its elements, and that value: eg: {\"Device\": {\"type\": \"dict\"}}."
    for a in self.annotations:
      for t, vs in attrValues[a].items():
        if len(vs) == 1 and sum(vs.values()) == occurrences[t]:
          self.tagAnnotations[t][a] = next(iter(vs))
    def informative(tag:str) -> list[str]:
      return [a for a, byTag in attrValues.items() if tag in byTag and a not in self.annotations]

    # property tags: no subelements, never repeated in an element; with text, or just one attribute (its value)
    self.properties:set[str] = set()
    "The property tags (see the module doc)."
    self.valueAttribute:dict[str, str] = {}
    "For a property tag with no text: the attribute its value's in."
    for tag in occurrences:
      if tag == self.root or tag in hints.nodes:
        continue
      if tag not in hints.properties and (tag in hasChildren or tag in repeated):
        continue
      own = informative(tag)
      if tag not in hasText and len(own) > 1 and tag not in hints.properties: # (a record, not a value)
        continue
      self.properties.add(tag)
      if tag not in hasText and len(own) == 1:
        self.valueAttribute[tag] = own[0]

    # groups: never repeated in an element, nothing of their own, holding only properties and groups
    self.groups:set[str] = set()
    "The group tags (see the module doc)."
    more = True
    while more:
      more = False
      for tag, kids in childTags.items():
        if (tag in self.groups or tag == self.root or tag in hints.nodes or tag in repeated or tag in hasText or informative(tag)
            or not all(k in self.properties or k in self.groups for k in kids)):
          continue
        self.groups.add(tag)
        more = True

    # list holders: nothing but elements of one other node tag (that isn't one too), and nothing of their own
    self.holders:dict[str, str] = {}
    "The list holders (see the module doc), and the tag of the elements each holds."
    for tag, kids in childTags.items():
      if tag == self.root or tag in self.properties or tag in self.groups or tag in hasText or informative(tag) or len(kids) != 1:
        continue
      [held] = kids
      if held not in self.properties and held not in self.groups:
        self.holders[tag] = held
    for tag in [t for t, held in self.holders.items() if held in self.holders]: # (one holding holders isn't one)
      del self.holders[tag]
    if hints.nodes:
      for tag in [t for t in self.holders if t in hints.nodes]: # (a type in the ontology: stays one)
        del self.holders[tag]

    # each node tag's fields: its informative attributes, then its property subelements
    self.fields:dict[str, dict[str, Field]] = {}
    "Each node tag's fields, by name (see *Field*)."
    def subelements(tag:str, path:tuple[str, ...]) -> Iterator[tuple[str, ...]]: # (the properties in it, and in its groups)
      for c in sorted(childTags.get(tag, ()), key=self._order.__getitem__):
        if c in self.properties:
          yield path + (c,)
        elif c in self.groups:
          yield from subelements(c, path + (c,))
    for tag in self.nodeTags():
      props = list(subelements(tag, ()))
      fs:dict[str, Field] = {}
      for a in informative(tag):
        fs[a] = Field(a, PROPERTY + ("@" + a if (a,) in props else a), True)
      for path in props:
        name = "/".join(path)
        fs[name] = Field(name, PROPERTY + name, False, path=path)
      self.fields[tag] = fs
    self._fieldValues(root)

    # the kind of each node tag's elements: a field named as one, whose values are recurring names
    self.kinds:dict[str, Field] = {}
    "The field that says what kind each node tag's elements are (see the module doc), if one does."
    for tag, fs in self.fields.items():
      candidates = []
      for f in fs.values():
        values = self._values.get((tag, f.name), Counter())
        if (not KIND.search(f.name) or f.typ is not str or not values or self.isIdentifier(f.name)
            or len(values) == sum(values.values()) > KIND_DIFFERENT): # (all different: names, not kinds)
          continue
        candidates.append(((not f.fromAttribute, not re.search(r"(type|kind|category|class)$", f.name, re.I), len(f.name)), f))
      if candidates:
        self.kinds[tag] = min(candidates, key=lambda c: c[0])[1]

    # references: fields named as one, most of whose values are identifiers
    self.identified:dict[str, list[tuple[str, ET.Element]]] = defaultdict(list)
    "Each identifier's value, and the elements (their tags, and them) it identifies."
    for e in elements(root):
      tag = localName(e.tag)
      for f in self.fields.get(tag, {}).values():
        if self.isIdentifier(f.name):
          ident = self.fieldText(e, f)
          if ident:
            self.identified[ident].append((tag, e))
    self.references:dict[tuple[str, str], str|None] = {}
    "(node tag, field) -> the tag of the elements it refers to (None if they're of several) (see the module doc)."
    for tag, fs in self.fields.items():
      for f in fs.values():
        if self.isIdentifier(f.name) or not (REFERENCE.search(f.name) or f.name in hints.references):
          continue
        values = self._values.get((tag, f.name), Counter())
        hits = [v for v in values if len(self.identified.get(v, ())) == 1]
        if not values or 2 * len(hits) < len(values):
          continue
        targets = Counter(self.identified[v][0][0] for v in hits)
        self.references[(tag, f.name)] = next(iter(targets)) if len(targets) == 1 else None

  def _fieldValues(self, root:ET.Element) -> None:
    '''
    Gather each field's values (see *fieldText()*), and so its datatype; and
    each property subelement's annotations.
    '''
    self._values:dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    annotations:dict[tuple[str, str], dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for e in elements(root):
      tag = localName(e.tag)
      fs = self.fields.get(tag)
      if fs is None:
        continue
      for f in fs.values():
        v = self.fieldText(e, f)
        if v is not None:
          self._values[(tag, f.name)][v] += 1
      for f in fs.values():
        leaf = self.fieldElement(e, f)
        if leaf is not None:
          for a, v in attributes(leaf).items():
            if a in self.annotations:
              annotations[(tag, f.name)][a].add(v)
    for tag, fs in self.fields.items():
      for f in fs.values():
        f.typ = datatype(list(self._values.get((tag, f.name), ())))
        f.annotations = {a: ", ".join(sorted(vs)) for a, vs in annotations.get((tag, f.name), {}).items()}

  def nodeTags(self) -> list[str]:
    ''':returns: The node tags (not properties, groups nor list holders), in the order they're first seen.'''
    return sorted((t for t in self.occurrences if self.isNode(t)), key=self._order.__getitem__)

  def isNode(self, tag:str) -> bool:
    ''':returns: Whether *tag* is a node tag (not a property, a group, nor a list holder).'''
    return tag not in self.properties and tag not in self.groups and tag not in self.holders

  @staticmethod
  def isIdentifier(name:str) -> bool:
    ''':returns: Whether a field called *name* identifies its element (see *IDENTIFIERS*).'''
    return name.lower() in IDENTIFIERS

  def fieldText(self, elem:ET.Element, f:Field) -> str|None:
    '''
    :param elem: An element of a node tag.
    :param f: One of its tag's fields.
    :returns: *elem*'s value for *f* (as in the XML), if it has one.
    '''
    if f.fromAttribute:
      return attributes(elem).get(f.name)
    child = self.fieldElement(elem, f)
    if child is None:
      return None
    attr = self.valueAttribute.get(f.path[-1])
    return attributes(child).get(attr, "") if attr is not None else text(child)

  @staticmethod
  def fieldElement(elem:ET.Element, f:Field) -> ET.Element|None:
    '''
    :param elem: An element of a node tag.
    :param f: One of its tag's fields: a subelement.
    :returns: *elem*'s subelement for *f* (in a group, perhaps), if it has one.
    '''
    e:ET.Element|None = elem
    for tag in f.path:
      e = next((c for c in children(e) if localName(c.tag) == tag), None) if e is not None else None
    return e if f.path else None

  def propertyExtras(self, f:Field, child:ET.Element) -> dict[str, str]:
    '''
    :param f: A field that's a subelement.
    :param child: Its element.
    :returns: Its attributes besides its value and annotations, by their
      attribute names in its node element's individual ("property/<field>/<attribute>").
    '''
    return {f"{f.key}/{a}": v for a, v in attributes(child).items()
            if a not in self.annotations and a != self.valueAttribute.get(f.path[-1])}

  def nameOf(self, elem:ET.Element) -> str|None:
    '''
    :param elem: An element of a node tag.
    :returns: Its individual's name (see the module doc), if it has one.
    '''
    fs = self.fields.get(localName(elem.tag), {})
    byLower = {n.lower(): f for n, f in fs.items()}
    for n in NAMING:
      f = byLower.get(n)
      if f is not None:
        v = self.fieldText(elem, f)
        if v:
          return v
    t = text(elem)
    return t if t and len(t) <= SHORT_TEXT and "\n" not in t else None

  def kindOf(self, elem:ET.Element) -> str|None:
    '''
    :param elem: An element of a node tag.
    :returns: The subtype of its tag's type its individual is one of (see the module doc), if any.
    '''
    tag = localName(elem.tag)
    f = self.kinds.get(tag)
    v = self.fieldText(elem, f) if f is not None else None
    return v if v and v != tag else None

  def report(self) -> str:
    ''':returns: What the tags are, briefly: for the log.'''
    kinds = ", ".join(f"{t} by {f.name}" for t, f in self.kinds.items())
    refs = ", ".join(f"{t}.{f}" + (f" -> {target}" if target else "") for (t, f), target in self.references.items())
    return (f"{len(self.nodeTags())} node tags, {len(self.properties)} property tags, {len(self.groups)} groups, "
            f"{len(self.holders)} list holders"
            + (f"; annotations: {', '.join(sorted(self.annotations))}" if self.annotations else "")
            + (f"; kinds: {kinds}" if kinds else "") + (f"; references: {refs}" if refs else ""))
