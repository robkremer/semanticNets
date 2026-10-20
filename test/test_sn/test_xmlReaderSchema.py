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
'''
The XMLreader plugin's *schema*: what an XML file's tags and attributes are,
inferred from how they're used -- properties, groups, list holders,
annotations, datatypes, kinds, names and references -- and the model
*buildModel()* makes of them: the properties as "property/..." attributes, a
tooltip listing them on each type, subtypes for the kinds, has-<holder> for
what a list holder holds, and a relation for each reference. What an ontology
made before says wins.

Created on Oct 19, 2026

@author: robkremer
'''
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from sn.model.model import Model, Node, Relation
from sn.plugins import importBundled

XML = '''<inventory version="3">
  <meta><created>2026-01-01</created><owner>Rob</owner></meta>
  <shelves>
    <shelf id="s1"><label dt="string">Top</label></shelf>
    <shelf id="s2"><label dt="string">Bottom</label></shelf>
  </shelves>
  <items>
    <item><sku fmt="t">1001</sku><title dt="string">Lamp</title><shelfRef>s1</shelfRef><weight dt="number">1.5</weight>
          <fragile dt="bool">true</fragile><category dt="string">light</category></item>
    <item><sku fmt="t">1002</sku><title dt="string">Desk</title><shelfRef>s2</shelfRef><weight dt="number">20</weight>
          <fragile dt="bool">false</fragile><category dt="string">furniture</category></item>
    <item><sku fmt="t">1003</sku><title dt="string">Bulb</title><shelfRef>s1</shelfRef><weight dt="number">0.1</weight>
          <fragile dt="bool">true</fragile><category dt="string">light</category><color unit="nm">550</color></item>
    <item><sku fmt="t">1004</sku><title dt="string">Chair</title><shelfRef>nowhere</shelfRef><weight dt="number">5</weight>
          <fragile dt="bool">false</fragile><category dt="string">furniture</category></item>
  </items>
  <note>first</note>
  <note>second</note>
</inventory>'''

class TestSchema(unittest.TestCase):

  @classmethod
  def setUpClass(cls):
    cls.schema = importBundled("XMLreader", "schema")
    cls.reader = importBundled("XMLreader", "reader")

  def setUp(self):
    Model._initCache()
    self.tmp = tempfile.TemporaryDirectory()
    self.xml = Path(self.tmp.name).resolve() / "inventory.xml"
    self.xml.write_text(XML)
    self.s = self.schema.Schema(ET.fromstring(XML))

  def tearDown(self):
    Model._initCache()
    self.tmp.cleanup()

  def test_roles(self):
    'What each tag is.'
    s = self.s
    self.assertEqual(s.nodeTags(), ["inventory", "shelf", "item", "note"]) # (note: repeated, so a node)
    self.assertEqual(s.properties, {"created", "owner", "label", "sku", "title", "shelfRef", "weight", "fragile", "category", "color"})
    self.assertEqual(s.groups, {"meta"})
    self.assertEqual(s.holders, {"shelves": "shelf", "items": "item"})
    self.assertEqual(s.annotations, {"dt"}) # (not fmt: on one tag)

  def test_fields(self):
    'Fields, their keys, datatypes and annotations.'
    fs = self.s.fields
    self.assertEqual(list(fs["inventory"]), ["version", "meta/created", "meta/owner"])
    self.assertEqual(fs["inventory"]["meta/owner"].key, "property/meta/owner")
    self.assertIs(fs["inventory"]["version"].typ, int)
    item = fs["item"]
    self.assertEqual({n: f.typ for n, f in item.items()},
                     {"sku": int, "title": str, "shelfRef": str, "weight": float, "fragile": bool, "category": str, "color": int})
    self.assertEqual(item["weight"].annotations, {"dt": "number"})
    self.assertEqual(self.s.propertyExtras(item["color"], ET.fromstring('<color unit="nm">550</color>')), {"property/color/unit": "nm"})

  def test_kindsNamesReferences(self):
    s = self.s
    self.assertEqual({t: f.name for t, f in s.kinds.items()}, {"item": "category"})
    self.assertEqual(s.references, {("item", "shelfRef"): "shelf"})
    root = ET.fromstring(XML)
    self.assertEqual([s.nameOf(e) for e in root.iter("item")], ["Lamp", "Desk", "Bulb", "Chair"])
    self.assertEqual([s.nameOf(e) for e in root.iter("shelf")], ["Top", "Bottom"]) # (label before id)
    self.assertEqual([s.nameOf(e) for e in root.iter("note")], ["first", "second"]) # (short text)
    self.assertIsNone(s.nameOf(root))

  def test_datatype(self):
    d = self.schema.datatype
    self.assertIs(d(["1", "-2", ""]), int)
    self.assertIs(d(["007"]), str) # (a name, not a number)
    self.assertIs(d(["1", "2.5", "1e3"]), float)
    self.assertIs(d(["True", "false"]), bool)
    self.assertIs(d(["on", "off"]), str)
    self.assertIs(d([]), str)

  def test_fit(self):
    'A value made the type an ontology has for it, if nothing\'s lost.'
    fit, NO = self.schema.fit, self.schema.NO_FIT
    self.assertEqual([fit("20", float), fit("20.0", int), fit("-3", int), fit("x", "text"), fit("True", bool), fit("", int)],
                     [20.0, 20, -3, "x", True, None])
    self.assertIsInstance(fit("20", float), float)
    self.assertEqual([fit("20.5", int), fit("warm", float), fit("1", bool), fit("[1]", list)], [NO, NO, NO, NO])

  def test_model(self):
    'The model made of it.'
    m, o = self.reader.buildModel(str(self.xml), self.reader.outputPaths(str(self.xml))[0])
    types = {str(t.name): t for t in o.values() if isinstance(t, Node) and not isinstance(t, Relation) and t.model is o and t.isType()}
    self.assertEqual(set(types), {"inventory", "shelf", "item", "note", "light", "furniture"})
    self.assertEqual(types["light"].getParents(), [types["item"]])
    ind = {str(n.name): n for n in m.values() if isinstance(n, Node) and not isinstance(n, Relation) and n.isIndividual()}
    self.assertEqual(set(ind), {"inventory1", "Top", "Bottom", "Lamp", "Desk", "Bulb", "Chair", "first", "second"})
    lamp, bulb, inv = ind["Lamp"], ind["Bulb"], ind["inventory1"]
    self.assertEqual([str(t.name) for t in lamp.getParents()], ["light"])
    self.assertEqual((lamp["property/sku"], lamp["property/weight"], lamp["property/fragile"]), (1001, 1.5, True))
    self.assertEqual((bulb["property/color"], bulb["property/color/unit"]), (550, "nm"))
    self.assertEqual(inv["property/meta/owner"], "Rob")
    self.assertIn('dt="number"', types["item"].getAttr("property/weight").note)
    self.assertIn("${property/weight:+", types["item"]["vis/tooltip"])
    def related(rel:str) -> set[tuple[str, str]]:
      return {(str(r.localSrc.name), str(r.localDst.name)) for r in m.values()
              if isinstance(r, Relation) and r.isIndividual() and str(r.getParents()[0].name) == rel}
    self.assertEqual(related("has-shelves"), {("inventory1", "Top"), ("inventory1", "Bottom")})
    self.assertEqual(len(related("has-items")), 4)
    self.assertEqual(related("has-note"), {("inventory1", "first"), ("inventory1", "second")})
    self.assertEqual(related("shelfRef"), {("Lamp", "Top"), ("Desk", "Bottom"), ("Bulb", "Top")}) # (not Chair's: nowhere)
    shelfRef = next(r for r in o.values() if isinstance(r, Relation) and r.isType() and r.name == "shelfRef")
    self.assertEqual([str(t.name) for t in shelfRef.getParents()], [self.reader.REFERS_TO])
    self.assertIs(shelfRef.range, types["shelf"])
    for holder in ("has-shelves", "has-items"):
      t = next(r for r in o.values() if isinstance(r, Relation) and r.isType() and r.name == holder)
      self.assertEqual([str(p.name) for p in t.getParents()], [self.reader.HAS_PART])

  def test_ontologyWins(self):
    'Read again on an ontology in which a property tag has a type: it\'s a node tag.'
    path = self.reader.outputPaths(str(self.xml))[0]
    m, o = self.reader.buildModel(str(self.xml), path)
    Node(o, [o.NODE], name="title")
    hints = self.reader.hintsFrom(o, {"title", "item", "shelf"})
    self.assertIn("title", hints.nodes)
    self.assertNotIn("title", hints.properties)
    self.assertIn("sku", hints.properties)
    s = self.schema.Schema(ET.fromstring(XML), hints)
    self.assertIn("title", s.nodeTags())
    self.assertNotIn("title", s.fields["item"])

if __name__ == "__main__":
  unittest.main()
