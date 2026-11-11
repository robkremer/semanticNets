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
generic links). And Gaines's truth marks: a net's asserted ones, the menu
items' (see the plugin's *hooks*), and the marks the reasoners propagate from
them, as KNet does (*TestMarks*).

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

def _panel(i:int, mark:str) -> list[str]:
  '''
  The nodes of one of KNet's mark propagation panels (Gaines, section 4.2):
  a, marked *mark* (hex: 81 true, 82 false, 83 both, asserted), and b to g
  around it (see *_panelLinks()*), named with *i*.
  '''
  return [f"0|{mark if n == 'a' else 0}|0|0|30|20|{n}{i}|" for n in "abcdefg"]

def _panelLinks(i:int) -> list[str]:
  '''
  The links of panel *i* (its nodes from 7*i): a coexcludes b, f excludes
  a, a includes c, e includes a, a negates d, and g is equivalent to a.
  '''
  a, b, c, d, e, f, g = range(7 * i, 7 * i + 7)
  return [f"{a}|{b}|3", f"{f}|{a}|2", f"{a}|{c}|0", f"{e}|{a}|0", f"{a}|{d}|4", f"{g}|{a}|1"]

MARKS = net(
  "|C|9|FFFFFF||32",
  "T|1",
  "2|0|Arial|9|1|0|000000|FFFFFF|000000|008A00|0|0|0||Concept",
  "A|5",
  "1|0|0|0|1|0|000000|000000|000000|000000|Includes",
  "1|0|1|0|1|0|000000|000000|000000|000000|Equivalent",
  "0|0|0|0|1|1|000000|000000|000000|000000|Excludes symmetric",
  "0|0|0|0|1|2|000000|000000|000000|000000|Coexcludes symmetric",
  "0|0|0|0|1|3|000000|000000|000000|000000|Negates symmetric",
  "M|2", "693804|FFCD7D|Asserted", "000000|A6A6A6|Included",
  "N|26|0|-1",
  *_panel(0, "81"), *_panel(1, "82"), *_panel(2, "83"),
  "0|0|0|0|30|20|s|",     # 21: s includes t, and excludes it: necessarily false
  "0|0|0|0|30|20|t|",     # 22
  "0|0|0|0|30|20|v|",     # 23: w includes v, and v coexcludes w: necessarily true
  "0|0|0|0|30|20|w|",     # 24
  "0|1E1|0|0|30|20|h|",   # 25: a derived mark (KNet's): not asserted
  "L|22|0",
  *_panelLinks(0), *_panelLinks(1), *_panelLinks(2),
  "21|22|0 2", "24|23|0 3",
  "G|0",
)
"Gaines's mark propagation figure (KNet's net of it: Logic Paper 2024/mark propagation.rnet), and necessary marks."

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
    self.assertEqual([str(p.name) for p in b.nodeTypes[0].getParents()], ["knode"]) # (a KNet node: its marks' bars and menu)

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
    others' (cat isa pet), nor knode's own (animal isa knode), nor SN's (node, top).
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
        self.assertFalse({h for h in holds if h[0] == "includes" and h[2] in ("node", "top", "knode")})

class TestMarks(unittest.TestCase):
  '''
  Gaines's truth marks (section 4.2): asserted ones, from a net's file or
  the menu items (see *hooks*), and those the reasoners conclude -- as KNet
  does (as its net of the paper's figure has them: see *MARKS*).
  '''
  @classmethod
  def setUpClass(cls):
    cls.rnet = importBundled("rnetReader", "rnet")
    cls.reader = importBundled("rnetReader", "reader")
    cls.hooks = importBundled("rnetReader", "hooks")

  def setUp(self):
    Model._initCache()
    self.tmp = tempfile.TemporaryDirectory()
    self.folder = Path(self.tmp.name).resolve()

  def tearDown(self):
    Model._initCache()
    self.tmp.cleanup()

  def build(self, name:str="marks"):
    return self.reader.buildModel(self.rnet.parseText(MARKS, f"{name}.rnet"), str(self.folder / f"{name}.snm"))

  def test_asserted(self):
    'A net\'s asserted marks are the nodes\' truth marks; a derived one isn\'t (the reasoners conclude it again).'
    b = self.build()
    marks = {str(n.name): self.hooks.marks(n) for n in b.nodes.values() if self.hooks.marks(n)}
    self.assertEqual(marks, {"a0": {"markTrue": "asserted"}, "a1": {"markFalse": "asserted"},
                             "a2": {"markTrue": "asserted", "markFalse": "asserted"}})
    h = b.nodes[25]
    self.assertEqual((h["mark"], h["markDerived"]), ("T", True))

  EXPECTED = {
    "c0": {"markTrue": "included"}, "f0": {"markFalse": "excluded"}, "d0": {"markFalse": "excluded"},
    "g0": {"markTrue": "included"},
    "b1": {"markTrue": "coexcluded"}, "e1": {"markFalse": "irrelevant"}, "d1": {"markTrue": "coexcluded"},
    "g1": {"markFalse": "irrelevant"},
    "b2": {"markTrue": "coexcluded"}, "f2": {"markFalse": "excluded"}, "c2": {"markTrue": "included"},
    "e2": {"markFalse": "irrelevant"}, "d2": {"markTrue": "coexcluded", "markFalse": "excluded"},
    "g2": {"markTrue": "included", "markFalse": "irrelevant"},
    "s": {"markFalse": "necessary"}, "v": {"markTrue": "necessary"}}
  "What KNet marks (as its net of the figure has it), and how (one of the ways, where there are more)."

  def test_propagated(self):
    '''
    Each installed engine marks the nodes KNet does, and no others -- true
    by inclusion and coexclusion, false by exclusion and (backwards)
    inclusion, both, and necessarily (an inconsistent node is false; its
    dual true) -- each in one of the ways KNet says it got it.
    '''
    for engine in installedEngines():
      with self.subTest(engine):
        Model._initCache()
        b = self.build(engine)
        res = Reasoner.create(b.model, engine).run()
        got:dict[str, dict[str, set]] = {}
        for _, x, k, v in res.ruleAttrs:
          if k in ("markTrue", "markFalse") and getattr(x, "model", None) is b.model and x.getLocalAttr(k) is None:
            got.setdefault(str(x.name), {}).setdefault(k, set()).add(v)
        self.assertEqual({n: sorted(ms) for n, ms in got.items()}, {n: sorted(ms) for n, ms in self.EXPECTED.items()})
        for n, ms in self.EXPECTED.items():
          for k, how in ms.items():
            self.assertIn(how, got[n][k], f"{n} {k}")

  def test_menu(self):
    '''
    The menu items (see *hooks*) assert a mark, both, and take back the
    asserted ones; and a node's marks are its bars: true's beside it, false's
    over it, in the colour of how it got it.
    '''
    from sn.hooks import HookContext, call, reference
    hooks = self.hooks
    b = self.build()
    node = b.nodes[22] # (t)
    self.assertEqual(node["vis/sideBars"], f"$({hooks.__name__}:markBars)") # (from knode: its bars, by the hook)
    self.assertEqual(hooks.markBars(node, HookContext()), "")
    ctx = HookContext()
    self.assertTrue(hooks._canMark(node, ctx))
    self.assertFalse(hooks._hasAsserted(node, ctx))
    call(reference(hooks.markTrue), node, ctx)
    self.assertEqual(hooks.marks(node), {"markTrue": "asserted"})
    self.assertEqual(hooks.markBars(node, ctx), "right:#693804")
    call(reference(hooks.markFalse), node, ctx)
    self.assertEqual(hooks.marks(node), {"markTrue": "asserted", "markFalse": "asserted"})
    self.assertTrue(hooks._hasAsserted(node, ctx))
    call(reference(hooks.clearMarks), node, ctx)
    self.assertEqual(hooks.marks(node), {})
    node["markFalse"] = "excluded"
    self.assertEqual(hooks.markBars(node, ctx), "top:#00a000")
    self.assertFalse(hooks._canMark(b.nodeTypes[0], ctx)) # (a type: its instances are marked)

@unittest.skipUnless(os.environ.get("REP_PLUS_DATA"), "set REP_PLUS_DATA to Rep Plus 2's test data folder to run these")
class TestRepPlusData(unittest.TestCase):
  '''
  Built from the nets of some of KNet's figures for Gaines's paper, without
  the derived links KNet saved in them, the reasoners infer every one of
  those (that's a kernel link: not a preference's or a generic link's).
  "taxonomy merge" isn't here: some of its derived links join separate nodes
  that only share a label (its query panels), which says nothing about the rules.
  And the reasoners mark the nodes KNet marked, from the asserted marks.
  '''
  NETS = ["Nets-CNet-Dev/knets/paper/paper1/coexclusion squares.rnet",
          "Nets-CNet-Dev/knets/paper/paper1/inclusion patterns.rnet",
          "Nets-CNet-Dev/knets/paper/paper1/dynamics.rnet",
          "Nets-CNet-Dev/knets/paper/paper1/states of affairs/platodivision.rnet"]

  MARK_NETS = ["Logic Paper 2024/mark propagation.rnet", "Nets-CNet-Dev/CNet tests/proper part 1.rnet",
               "Nets-CNet-Dev/knets/paper/Inference Process.rnet"]
  "Nets with marks KNet propagated (and, in proper part 1, a necessary one)."

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

  def test_derivedMarks(self):
    '''
    From the nets' asserted marks, the reasoners mark true and false the
    nodes KNet did (its derived marks), and no others.
    '''
    for engine in installedEngines():
      for path in self.MARK_NETS:
        with self.subTest(engine=engine, net=path):
          Model._initCache()
          n = self.rnet.parse(os.path.join(os.environ["REP_PLUS_DATA"], path))
          b = self.reader.buildModel(n, str(self.folder / f"{engine}-{os.path.basename(path)}.snm"))
          res = Reasoner.create(b.model, engine).run()
          got = {(id(x), k) for _, x, k, _ in res.ruleAttrs if k in ("markTrue", "markFalse") and x.getLocalAttr(k) is None}
          expected = {(id(b.nodes[nn.index]), "markTrue" if c == "T" else "markFalse")
                      for nn in n.nodes if nn.marks and nn.derived and nn.index in b.nodes for c in (nn.truth or "")}
          self.assertTrue(expected)
          self.assertEqual(got, expected)

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
