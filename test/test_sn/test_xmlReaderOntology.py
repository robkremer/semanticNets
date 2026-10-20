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
The XMLreader plugin's *buildModel()*: the model has the elements, and its
ontology -- its super-model, beside it -- the types, the has-<tag> relation
types (each a kind of xml-has-part), and the definition of xml-part-of as
xml-has-part's inverse; saved and read again, the model finds its ontology, and
the reasoner concludes an xml-part-of for each element in another. Read again
on an ontology made before, and changed since, the changes stay, and only
what's missing is added. An ontology can be shared by several files' models
(each adding what it hasn't); one that can't be changed (eg: on the web) is
left as it is, and what it hasn't goes in the model.

Created on Oct 18, 2026

@author: robkremer
'''
import os
import tempfile
import unittest
from pathlib import Path
from sn.model.model import Model, Node, Relation, IsaIndividual
from sn.plugins import importBundled

XML = '''<library id="lib">
  <book id="b1"><title>GEB</title><chapter/><chapter/></book>
  <book id="b2" type="novel"><title>Dune</title></book>
</library>'''

class TestOntology(unittest.TestCase):

  @classmethod
  def setUpClass(cls):
    cls.reader = importBundled("XMLreader", "reader")

  def setUp(self):
    Model._initCache()
    self.tmp = tempfile.TemporaryDirectory()
    self.folder = Path(self.tmp.name).resolve()
    self.xml = self.folder / "lib.xml"
    self.xml.write_text(XML)
    self.modelPath, self.viewPath, self.ontologyPath = self.reader.outputPaths(str(self.xml))

  def tearDown(self):
    Model._initCache()
    self.tmp.cleanup()

  @staticmethod
  def types(db:Model, cls=Node) -> dict[str, object]:
    return {str(o.name): o for o in db.values() if isinstance(o, cls) and o.model is db and o.isType()
            and (cls is Relation or not isinstance(o, Relation))}

  def test_paths(self):
    self.assertEqual([os.path.basename(p) for p in (self.modelPath, self.viewPath, self.ontologyPath)],
                     ["lib_xml.snm", "lib_xml.snv", "lib_xml_ontology.snm"])

  def test_split(self):
    'The types are in the ontology, the elements in the model, which builds on it.'
    m, o = self.reader.buildModel(str(self.xml), self.modelPath)
    self.assertIn(o, m.superDBs)
    self.assertEqual(set(self.types(o)), {"library", "book", "chapter", "novel"}) # (title's a property of book)
    self.assertEqual(self.types(m), {})
    self.assertEqual(self.types(m, Relation), {})
    elements = {str(n.name) for n in m.values() if isinstance(n, Node) and not isinstance(n, Relation) and n.isIndividual()}
    self.assertEqual(elements, {"lib", "GEB", "Dune", "chapter1", "chapter2"}) # (the books named by their titles)
    rels = self.types(o, Relation)
    hasPart = rels[self.reader.HAS_PART]
    self.assertIn(self.reader.PART_OF, rels)
    for tag in ("book", "chapter"):
      self.assertIn(hasPart, rels[f"has-{tag}"].getParents())
    geb = next(n for n in m.values() if n.name == "GEB")
    self.assertEqual((geb["property/id"], geb["property/title"]), ("b1", "GEB"))
    self.assertIn("property/title", self.types(o)["book"].getLocalAttr("vis/tooltip").value)
    self.assertEqual(len([d for d in o.values() if isinstance(d, Node) and d.isIndividual() and d.isa(o.DEFINITION)]), 1)

  def test_partOfConcluded(self):
    'Saved and read again: the model finds its ontology, and the reasoner concludes xml-part-of from each has-<tag>.'
    from sn.model.reasoner import reason
    m, o = self.reader.buildModel(str(self.xml), self.modelPath)
    o.save()
    m.save()
    Model._initCache()
    m = Model.getDB(Path(self.modelPath).as_uri())
    self.assertEqual(m.superModelPaths(), ["lib_xml_ontology.snm"])
    self.assertEqual(m.unlistedModels(), {})
    res = reason(m, silent=True)
    self.assertEqual([v for v in res.violations if v.code.startswith(("rule", "bad"))], [])
    partOf = {(str(r.localSrc.name), str(r.localDst.name)) for r in m.inferredObjects()
              if isinstance(r, Relation) and any(str(t.name) == self.reader.PART_OF for t in r.getParents())}
    self.assertEqual(partOf, {("GEB", "lib"), ("Dune", "lib"), ("chapter1", "GEB"), ("chapter2", "GEB")})

  def reread(self, edit=None) -> tuple[Model, Model]:
    '''
    :param edit: Changes the ontology, given it, before it's saved (eg: as the user might).
    :returns: The model and ontology read again from the XML file, on the
      ontology made the first time, saved (and the model removed), as
      *view.convert()* does when it's kept.
    '''
    m, o = self.reader.buildModel(str(self.xml), self.modelPath)
    if edit is not None:
      edit(o)
    o.save()
    m.save()
    Model._initCache()
    os.remove(self.modelPath)
    o = Model.getDB(Path(self.ontologyPath).as_uri())
    m, o2 = self.reader.buildModel(str(self.xml), self.modelPath, o)
    self.assertIs(o2, o)
    self.assertIn(o, m.superDBs)
    return m, o

  def test_rereadUnchanged(self):
    'Read again on its own ontology: nothing is added to it, and the elements are of its types.'
    def contents(o:Model) -> list[tuple[str, str]]:
      return sorted((str(t.name), type(t).__name__) for t in o.values())
    before:list = []
    with self.assertNoLogs(self.reader.logger, "INFO"):
      m, o = self.reread(lambda o: before.extend(contents(o)))
    self.assertEqual(contents(o), before)
    dune = next(n for n in m.values() if n.name == "Dune")
    self.assertEqual([str(t.name) for t in dune.getParents()], ["novel"])
    self.assertIs(dune.getParents()[0].model, o)

  def test_rereadEdited(self):
    '''Read again on its ontology after it's changed: a type moved under another,
    and an attribute and a type the user added, stay; a type renamed or deleted
    is made afresh (and logged), and the rest are found by name.'''
    ids:dict[str, int] = {}
    def edit(o:Model):
      types = self.types(o)
      publication = Node(o, [o.NODE], name="publication")
      book = types["book"]
      link = next(r for r, _ in book._getOutgoing(lambda r: isinstance(r, IsaIndividual)))
      link.dst = publication # (book isa publication, not node)
      book["isbn"] = "?"
      types["chapter"]["name"] = "section"
      types["novel"]._disconnect()
      ids.update({n: t._id for n, t in types.items()}, hasBook=self.types(o, Relation)["has-book"]._id)
    with self.assertLogs(self.reader.logger, "INFO") as logs:
      m, o = self.reread(edit)
    self.assertEqual(len(logs.records), 2)
    added, rangeWarning = sorted(logs.records, key=lambda r: r.levelno)
    self.assertEqual(added.getMessage().split(": ", 1)[1], "chapter, novel (a kind of book).")
    self.assertIn("has-chapter's range is section", rangeWarning.getMessage()) # (has-chapter is kept, still to section)
    types = self.types(o)
    self.assertEqual(set(types), {"library", "book", "publication", "novel", "section", "chapter"})
    book = types["book"]
    self.assertEqual(book._id, ids["book"])
    self.assertEqual([str(t.name) for t in book.getParents()], ["publication"])
    self.assertEqual(book["isbn"], "?")
    self.assertNotEqual(types["novel"]._id, ids["novel"])
    self.assertEqual(types["novel"].getParents(), [book])
    self.assertEqual(self.types(o, Relation)["has-book"]._id, ids["hasBook"])
    self.assertEqual(types["chapter"].getParents(), [o.NODE]) # (made afresh, under node, with a look of its own)
    self.assertTrue(str(types["chapter"].get("vis/fillColor")).startswith("#"))
    geb = next(n for n in m.values() if n.name == "GEB")
    self.assertTrue(geb.isa(types["publication"]))
    self.assertEqual(geb["property/id"], "b1")
    chapter1 = next(n for n in m.values() if n.name == "chapter1")
    self.assertEqual(chapter1.getParents(), [types["chapter"]])

  def test_rereadSameNames(self):
    '''A subtype named as a tag (<object type="book"> and <book>: two types named
    book, one a kind of object): read again, each element's type is found, and
    nothing is added.'''
    self.xml.write_text('<shelf><object id="o1" type="book"/><book id="b1" year="1"/></shelf>')
    with self.assertNoLogs(self.reader.logger, "INFO"):
      m, o = self.reread()
    o1, b1 = (next(n for n in m.values() if n.name == name) for name in ("o1", "b1"))
    self.assertEqual([str(t.name) for t in o1.getParents()[0].getParents()], ["object"])
    self.assertEqual(b1.getParents()[0].getParents(), [o.NODE])

  def test_shared(self):
    '''Two files' models on one ontology, somewhere else: the second's adds only
    the types the first's hadn't (and the attributes), and the first's still
    works with it.'''
    shared = str(self.folder / "onto" / "library.snm")
    os.makedirs(os.path.dirname(shared))
    m1, o = self.reader.buildModel(str(self.xml), self.modelPath, shared)
    self.assertEqual(o.url, Path(shared).as_uri())
    o.save()
    m1.save()
    xml2 = self.folder / "more.xml"
    xml2.write_text('<library id="lib2"><book id="b9" year="1965"><title>Dune</title></book><magazine id="byte" issue="5"/></library>')
    model2 = self.reader.outputPaths(str(xml2))[0]
    with self.assertLogs(self.reader.logger, "INFO") as logs:
      m2, o2 = self.reader.buildModel(str(xml2), model2, o)
    self.assertIs(o2, o)
    self.assertEqual(logs.records[0].getMessage().split(": ", 1)[1], "book's attribute property/year, magazine, has-magazine.")
    self.assertEqual(self.types(m2), {})
    o.save()
    m2.save()
    Model._initCache()
    for path, names in ((self.modelPath, {"GEB", "Dune"}), (model2, {"Dune"})):
      m = Model.getDB(Path(path).as_uri())
      self.assertEqual(m.superModelPaths(), [os.path.relpath(shared, os.path.dirname(path))])
      book = self.types(Model.getDB(Path(shared).as_uri()))["book"] # (the one it's read with: in memory)
      books = {str(n.name) for n in m.values() if isinstance(n, Node) and n.isIndividual() and n.isa(book)}
      self.assertEqual(books, names)

  def test_typesFromTheOntology(self):
    '''A value is made the type its attribute has in the ontology (made from
    another file), if it can be without losing anything; if not, it's kept as
    text beside it, and the log says so.'''
    shared = str(self.folder / "devices.snm")
    self.xml.write_text('<house><dev id="d1"><temp>20</temp><level>1.5</level></dev><dev id="d2"><temp>19</temp><level>2.5</level></dev></house>')
    m1, o = self.reader.buildModel(str(self.xml), self.modelPath, shared)
    o.save()
    m1.save()
    dev = self.types(o)["dev"]
    self.assertIs(dev.getAttr("property/temp").type, int)
    self.assertIs(dev.getAttr("property/level").type, float)
    xml2 = self.folder / "other.xml"
    xml2.write_text('<house><dev id="e1"><temp>20.5</temp><level>3</level></dev><dev id="e2"><temp>21.0</temp><level>4</level></dev>'
                    '<dev id="e3"><temp>warm</temp><level>5</level></dev></house>')
    with self.assertLogs(self.reader.logger, "WARNING") as logs:
      m2, _ = self.reader.buildModel(str(xml2), self.reader.outputPaths(str(xml2))[0], o)
    e = {str(n.name): n for n in m2.values() if isinstance(n, Node) and n.isIndividual()}
    self.assertEqual((e["e1"]["property/level"], e["e2"]["property/temp"]), (3.0, 21)) # (as the ontology's types)
    self.assertIsInstance(e["e1"]["property/level"], float)
    self.assertEqual((e["e1"]["property/temp/text"], e["e3"]["property/temp/text"]), ("20.5", "warm"))
    self.assertIsNone(e["e1"].getLocalAttr("property/temp"))
    [message] = [r.getMessage() for r in logs.records]
    self.assertIn("dev's property/temp is an int, but 2 of its values in other.xml aren't (eg: '20.5')", message)
    o.save()
    m2.save()
    Model._initCache()
    Model.getDB(Path(self.modelPath).as_uri()) # (the first file's model still reads: the ontology's types are as they were)

  def test_unchangeable(self):
    '''On an ontology that's not to be changed: it's left as it is, and the types,
    has-<tag>s and subtypes it hasn't go in the model; an attribute its types
    haven't is just in the elements.'''
    m, o = self.reader.buildModel(str(self.xml), self.modelPath)
    o.save()
    Model._initCache()
    os.remove(self.modelPath) if os.path.exists(self.modelPath) else None
    o = Model.getDB(Path(self.ontologyPath).as_uri())
    before = len(o)
    self.xml.write_text('<library id="lib"><book id="b1" year="1979" type="essay"><title>GEB</title></book><magazine id="m" issue="3"/></library>')
    with self.assertLogs(self.reader.logger, "INFO") as logs:
      m, o2 = self.reader.buildModel(str(self.xml), self.modelPath, o, extendOntology=False)
    self.assertIs(o2, o)
    self.assertEqual(len(o), before)
    self.assertFalse(o.isDirty())
    self.assertEqual(set(self.types(m)), {"magazine", "essay"})
    self.assertEqual(set(self.types(m, Relation)), {"has-magazine"})
    self.assertIn(self.types(o)["book"], self.types(m)["essay"].getParents())
    geb = next(n for n in m.values() if n.name == "GEB")
    self.assertEqual(geb["property/year"], 1979)
    self.assertNotIn("property/year", self.types(o)["book"])
    messages = [r.getMessage() for r in logs.records]
    self.assertIn("as lib_xml_ontology.snm can't be changed", messages[0])
    self.assertTrue(messages[1].endswith("not in their types: book's property/year."), messages[1])

  def test_onTheWeb(self):
    '''An ontology on the web: read from its URL, write-locked, so what it hasn't
    goes in the model; the model, saved and read again, finds it there.'''
    import functools, threading
    from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
    web = self.folder / "web"
    web.mkdir()
    m, o = self.reader.buildModel(str(self.xml), str(web / "x.snm"), str(web / "onto.snm"))
    o.save()
    Model._initCache()
    class Quiet(SimpleHTTPRequestHandler):
      def log_message(self, *args): pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(web)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
      url = f"http://127.0.0.1:{server.server_address[1]}/onto.snm"
      self.assertTrue(self.reader.isRemote(url))
      self.assertFalse(self.reader.canChange(url))
      o = Model.getDB(url)
      self.assertTrue(o.writeLocked())
      self.xml.write_text('<library id="lib"><book id="b1"/><magazine id="byte" issue="1"/></library>') # (book: a type there)
      m, _ = self.reader.buildModel(str(self.xml), self.modelPath, o) # (extendOntology, but it can't be)
      self.assertEqual(set(self.types(m)), {"magazine"})
      m.save()
      Model._initCache()
      m = Model.getDB(Path(self.modelPath).as_uri())
      self.assertEqual(m.superModelPaths(), [url])
      byte = next(n for n in m.values() if n.name == "byte")
      self.assertEqual(byte.getParents(), [self.types(m)["magazine"]])
      self.assertTrue(next(n for n in m.values() if n.name == "b1").isa(self.types(Model.getDB(url))["book"]))
    finally:
      server.shutdown()
      server.server_close()

  def test_canChange(self):
    '''Where an ontology is, and whether it can be changed.'''
    r = self.reader
    f = self.folder / "o.snm"
    self.assertEqual(r.localPath(f.as_uri()), str(f))
    self.assertEqual(r.localPath(str(f)), str(f))
    self.assertIsNone(r.localPath("https://example.com/o.snm"))
    self.assertTrue(r.canChange(str(f))) # (not there: it can be made)
    f.write_text("")
    self.assertTrue(r.canChange(f.as_uri()))
    f.chmod(0o444)
    try:
      self.assertFalse(r.canChange(str(f)))
    finally:
      f.chmod(0o644)
    self.assertFalse(r.canChange("https://example.com/o.snm"))

if __name__ == "__main__":
  unittest.main()
