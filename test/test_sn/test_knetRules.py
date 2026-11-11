'''
The KNet kernel that the rnetReader plugin's models build on
(plugins/rnetReader/knet.snm, made by tools/makeKnetRules.py): the reader's
link types are SN subtypes of the kernel relation types their looks say they
are (*reader.kernelKind()*), turned round if they're drawn backwards; and
every installed reasoner engine draws Gaines's kernel inferences from a net's
links -- exclusion and coexclusion (and its inheritance), negation and double
negation, equivalence from a cycle of inclusions, inconsistency (local, with
a warning), symmetry between types too, and isa as inclusion for types under
knode -- and nothing from links that aren't kernel links (preferences,
generic links).

If the environment variable REP_PLUS_DATA names the folder of Rep Plus 2's
test data (Brian Gaines's), the reasoners must also infer every derived link
that KNet saved in some of its nets (see *TestRepPlusData*).

The nets here are made up, small, in the files' format.

Created on Nov 11, 2026

@author: robkremer
'''
import os
import tempfile
import unittest
from pathlib import Path
from sn.model.model import Model, Node, Relation
from sn.model.reasoner import Reasoner, installedEngines
from sn.plugins import importBundled
from test_sn.test_rnetReader import net

KERNEL = net(
  "|C|9|FFFFFF||32",
  "T|1",
  "2|0|Arial|9|1|0|000000|FFFFFF|000000|008A00|0|0|0||Concept",
  "A|8",
  "1|0|0|0|1|0|000000|000000|000000|000000|Includes",
  "1|1|0|0|1|0|000000|000000|000000|000000|Excludes",
  "0|0|0|0|1|2|000000|000000|000000|000000|Coexcludes symmetric",
  "0|0|0|0|1|3|000000|000000|000000|000000|Negates symmetric",
  "0|0|1|0|1|0|000000|000000|000000|000000|Includes reverse",
  "0|0|0|0|1|1|000000|000000|000000|000000|Excludes symmetric",
  "0|0|0|0|1|6|000000|000000|FF6CFE|3B003A|Prefer",
  "6|0|0|0|3|0|000000|000000|000000|000000|Generic",
  "N|21|0|-1",
  "0|0|0|0|30|20|dog|",       # 0
  "0|0|0|0|30|20|animal|",    # 1
  "0|0|0|0|30|20|plant|",     # 2
  "0|0|0|0|30|20|three|",     # 3
  "0|0|0|0|30|20|odd|",       # 4
  "0|0|0|0|30|20|even|",      # 5
  "0|0|0|0|30|20|number|",    # 6
  "0|0|0|0|30|20|on|",        # 7
  "0|0|0|0|30|20|off|",       # 8
  "0|0|0|0|30|20|lit|",       # 9
  "0|0|0|0|30|20|a|",         # 10
  "0|0|0|0|30|20|b|",         # 11
  "0|0|0|0|30|20|c|",         # 12
  "0|0|0|0|30|20|p|",         # 13
  "0|0|0|0|30|20|q|",         # 14
  "0|0|0|0|30|20|square circle|", # 15
  "0|0|0|0|30|20|round|",     # 16
  "0|0|0|0|30|20|x|",         # 17
  "0|0|0|0|30|20|y|",         # 18
  "0|0|0|0|30|20|z|",         # 19
  "0|0|0|0|30|20|w|",         # 20
  "L|14|0",
  "0|1|0",    # dog includes animal,
  "1|2|1",    # animal excludes plant: so dog excludes plant (and plant dog)
  "4|5|2",    # odd coexcludes even,
  "3|5|5",    # three excludes even: so three includes odd;
  "4|6|0",    # odd includes number: so number coexcludes even
  "7|8|3",    # on negates off,
  "9|8|3",    # and so does lit: so on and lit are equivalent
  "10|11|0",  # a includes b,
  "11|12|0",  # b includes c,
  "10|12|4",  # and c includes a (drawn backwards: from a to c, its arrow at a): a cycle
  "13|14|0 0",  # p includes q, and q p (the link back): equivalent
  "15|16|0 5",  # square circle includes round, and round excludes it: inconsistent
  "17|18|6",  # x prefer y: not a kernel link
  "19|20|7",  # z generic w: nor is this
  "G|0",
)

class TestKernelKinds(unittest.TestCase):

  @classmethod
  def setUpClass(cls):
    cls.rnet = importBundled("rnetReader", "rnet")
    cls.reader = importBundled("rnetReader", "reader")

  def kind(self, name, head=0, headBars=0, tail=0, tailBars=0, mid=0, flags=1):
    return self.reader.kernelKind(self.rnet.LinkType(0, name, head, headBars, tail, tailBars, flags, mid))

  def test_byLook(self):
    'An arrow includes; with 1, 2 or 3 bars it excludes, coexcludes or negates; likewise the symmetric ones by their middle.'
    r = self.reader
    self.assertEqual(self.kind("Includes", head=1), r.INCLUDES)
    self.assertEqual(self.kind("Entails derived", head=1, flags=516), r.INCLUDES) # (CNet's name; derived links too)
    self.assertEqual(self.kind("Conjunct includes", head=2), r.INCLUDES) # (a heavy arrow: still an arrow)
    self.assertEqual(self.kind("Disjunct includes", head=3), r.INCLUDES) # (a double one)
    self.assertEqual(self.kind("Excludes", head=1, headBars=1), r.EXCLUDES)
    self.assertEqual(self.kind("Coexcludes", head=1, headBars=2), r.COEXCLUDES)
    self.assertEqual(self.kind("Negates", head=1, headBars=3), r.NEGATES)
    self.assertEqual(self.kind("Includes reverse", tail=1), r.INCLUDES)
    self.assertEqual(self.kind("Excludes symmetric", mid=1), r.EXCLUDES)
    self.assertEqual(self.kind("Coexcludes symmetric", mid=2), r.COEXCLUDES)
    self.assertEqual(self.kind("Negates offset", head=94, mid=3), r.NEGATES) # (an offset line: no arrowhead)
    self.assertEqual(self.kind("Opposite", head=1, mid=1), r.EXCLUDES) # (CNet's arrow with a bar)
    self.assertEqual(self.kind("Equivalent", head=1, tail=1), r.EQUIVALENT)
    self.assertEqual(self.kind("Equivalent"), r.EQUIVALENT) # (a plain line, by its name)
    self.assertEqual(self.kind("Double opposite", head=1, headBars=1, tail=1, tailBars=1), r.EXCLUDES)

  def test_notKernel(self):
    'Generic links, preferences, prohibitions, "Etc" links, plain lines, and odd mixtures mean nothing to the kernel.'
    for name, look in (("Generic", dict(head=6)), ("Generic derived reverse", dict(tail=1)), ("Prefer", dict(mid=6)),
                       ("Includes prohibited", dict(head=1, mid=4)), ("Etc", dict(head=1)), ("Line", {}),
                       ("Relation", dict(flags=257)), ("Transitive", dict(head=5)), ("Entails forbidden", dict(head=1)),
                       ("Odd", dict(head=2, tail=1, tailBars=2)), ("Conjunct includes", dict(head=1, headBars=11))):
      with self.subTest(name):
        self.assertIsNone(self.kind(name, **look))

  def test_reversed(self):
    'Drawn backwards: an arrowhead at the tail only.'
    lt = lambda **k: self.rnet.LinkType(0, "x", **k)
    self.assertTrue(self.reader.isReversed(lt(tail=1)))
    self.assertTrue(self.reader.isReversed(lt(tail=6))) # (a generic one)
    self.assertFalse(self.reader.isReversed(lt(head=1)))
    self.assertFalse(self.reader.isReversed(lt(head=1, tail=1)))
    self.assertFalse(self.reader.isReversed(lt(mid=1)))

class TestKernelInference(unittest.TestCase):

  @classmethod
  def setUpClass(cls):
    cls.rnet = importBundled("rnetReader", "rnet")
    cls.reader = importBundled("rnetReader", "reader")

  def setUp(self):
    Model._initCache()
    self.tmp = tempfile.TemporaryDirectory()
    self.folder = Path(self.tmp.name).resolve()

  def tearDown(self):
    Model._initCache()
    self.tmp.cleanup()

  def test_built(self):
    '''
    The model builds on the kernel: each link type is an SN subtype of its
    kernel type (or not, if it hasn't one), drawn as the file draws it -- a
    backwards one turned round, its links too.
    '''
    b = self.reader.buildModel(self.rnet.parseText(KERNEL, "kernel.rnet"), str(self.folder / "kernel.snm"))
    self.assertEqual(sorted(b.kernel), sorted(self.reader.KERNEL))
    parents = {str(t.name): [str(p.name) for p in t.getParents()] for t in b.linkTypes.values()}
    self.assertEqual(parents, {"Includes": ["includes"], "Excludes": ["excludes"], "Coexcludes symmetric": ["coexcludes"],
                               "Negates symmetric": ["negates"], "Includes reverse": ["includes"],
                               "Excludes symmetric": ["excludes"], "Prefer": ["relation"], "Generic": ["relation"]})
    rev = b.linkTypes[4]
    self.assertEqual((rev["vis/terminator1"], rev["vis/terminator4"]), ("", "arrow")) # (its arrow: at its destination)
    rels = {(str(r.src.name), str(r.dst.name)) for r, _ in b.relations if r.getParents()[0] is rev}
    self.assertEqual(rels, {("c", "a")}) # (the file's from a to c, its arrow at a)
    back = {(str(r.src.name), str(r.dst.name), str(r.getParents()[0].name)) for r, li in b.relations if li in (10, 11)}
    self.assertEqual(back, {("p", "q", "Includes"), ("q", "p", "Includes"),                     # (a link's second type: back)
                            ("square circle", "round", "Includes"), ("round", "square circle", "Excludes symmetric")})
    self.assertIn("of them KNet's kernel links", b.report())

  def test_inferences(self):
    '''
    Each installed engine draws the kernel's inferences (see the module doc),
    and warns of the inconsistent node.
    '''
    engines = installedEngines()
    self.assertIn("clingo", engines)
    for engine in engines:
      with self.subTest(engine):
        Model._initCache()
        b = self.reader.buildModel(self.rnet.parseText(KERNEL, f"{engine}.rnet"), str(self.folder / f"{engine}.snm"))
        res = Reasoner.create(b.model, engine).run()
        kinds = {t: name for name, t in b.kernel.items()}
        holds = {(kinds[t], str(s.name), str(d.name)) for t, s, d in res.holds
                 if t in kinds and s is not None and d is not None and s.model is b.model and d.model is b.model}
        for fact in [("excludes", "dog", "plant"), ("excludes", "plant", "dog"),       # exclusion (and symmetry)
                     ("includes", "three", "odd"),                                     # coexclusion
                     ("coexcludes", "number", "even"),                                 # coexclusion inherited
                     ("negates", "off", "on"), ("excludes", "lit", "off"),             # negation: excludes, coexcludes
                     ("includes", "on", "lit"), ("equivalent", "on", "lit"), ("equivalent", "lit", "on"), # double negation
                     ("includes", "a", "c"), ("equivalent", "a", "b"), ("equivalent", "c", "b"), # a cycle
                     ("equivalent", "p", "q"),                                         # a link and its link back
                     ("inconsistent", "square circle", "round"),
                     ("inconsistent", "square circle", "square circle")]:              # (it excludes itself)
          self.assertIn(fact, holds)
        for fact in [("includes", "odd", "three"), ("excludes", "dog", "animal"), ("inconsistent", "round", "round"),
                     ("equivalent", "a", "a")]:
          self.assertNotIn(fact, holds)
        self.assertFalse({h for h in holds if {h[1], h[2]} & {"x", "y", "z", "w"}}) # (not kernel links: nothing from them)
        warnings = [(v.code, v.severity, str(v.subject.name)) for v in res.violations]
        self.assertEqual(warnings, [("inconsistent node", "warning", "square circle")])

  def test_types(self):
    '''
    Between types too: the kernel's symmetric types are symmetric, and isa is
    inclusion for types under knode (dog isa animal isa knode) -- not
    others' (cat isa pet), nor SN's own (node, top).
    '''
    reader = self.reader
    m = Model((self.folder / "types.snm").as_uri())
    m.setSuperModels([reader.ONTOLOGY])
    onto = next(db for db in m.superDBs if db.url.endswith("/knet.snm"))
    knode = next(o for o in onto.values() if o.model is onto and o.name == "knode")
    kernel = reader.kernelTypes(m)
    animal = Node(m, [knode], name="animal")
    dog = Node(m, [animal], name="dog")
    plant = Node(m, [knode], name="plant")
    pet = Node(m, [m.NODE], name="pet")
    Node(m, [pet], name="cat")
    Relation(m, [kernel["excludes"]], animal, plant, individual=True)
    for engine in installedEngines():
      with self.subTest(engine):
        res = Reasoner.create(m, engine).run()
        kinds = {t: name for name, t in kernel.items()}
        holds = {(kinds[t], str(s.name), str(d.name)) for t, s, d in res.holds if t in kinds and s is not None and d is not None}
        for fact in [("includes", "dog", "animal"), ("excludes", "plant", "animal"), ("excludes", "dog", "plant"),
                     ("excludes", "plant", "dog")]:
          self.assertIn(fact, holds)
        self.assertNotIn(("includes", "cat", "pet"), holds)
        self.assertFalse({h for h in holds if h[0] == "includes" and h[2] in ("node", "top")})

@unittest.skipUnless(os.environ.get("REP_PLUS_DATA"), "set REP_PLUS_DATA to Rep Plus 2's test data folder to run these")
class TestRepPlusData(unittest.TestCase):
  '''
  Built from the nets of some of KNet's figures for Gaines's paper, without
  the derived links KNet saved in them, the reasoners infer every one of
  those (that's a kernel link: not a preference's or a generic link's).
  "taxonomy merge" isn't here: some of its derived links join separate nodes
  that only share a label (its query panels), which says nothing about the rules.
  '''
  NETS = ["Nets-CNet-Dev/knets/paper/paper1/coexclusion squares.rnet",
          "Nets-CNet-Dev/knets/paper/paper1/inclusion patterns.rnet",
          "Nets-CNet-Dev/knets/paper/paper1/dynamics.rnet",
          "Nets-CNet-Dev/knets/paper/paper1/states of affairs/platodivision.rnet"]

  @classmethod
  def setUpClass(cls):
    cls.rnet = importBundled("rnetReader", "rnet")
    cls.reader = importBundled("rnetReader", "reader")

  def setUp(self):
    Model._initCache()
    self.tmp = tempfile.TemporaryDirectory()
    self.folder = Path(self.tmp.name).resolve()

  def tearDown(self):
    Model._initCache()
    self.tmp.cleanup()

  def test_derivedLinks(self):
    for engine in installedEngines():
      for path in self.NETS:
        with self.subTest(engine=engine, net=path):
          Model._initCache()
          n = self.rnet.parse(os.path.join(os.environ["REP_PLUS_DATA"], path))
          b = self.reader.buildModel(n, str(self.folder / f"{engine}-{os.path.basename(path)}.snm"))
          derived = {id(b.linkTypes[t.index]): t for t in n.linkTypes if t.derived and t.index in b.linkTypes}
          expected = []
          for r, _ in b.relations:
            t = derived.get(id(r.getParents()[0]))
            if t is not None:
              if self.reader.kernelKind(t) is not None:
                expected.append((self.reader.kernelKind(t), r.src, r.dst))
              r._disconnect()
          self.assertTrue(expected)
          res = Reasoner.create(b.model, engine).run()
          kinds = {t: name for name, t in b.kernel.items()}
          holds = {(kinds[t], id(s), id(d)) for t, s, d in res.holds if t in kinds}
          self.assertEqual([e for e in expected if (e[0], id(e[1]), id(e[2])) not in holds], [])

if __name__ == "__main__":
  unittest.main()
