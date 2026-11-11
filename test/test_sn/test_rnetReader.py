'''
The rnetReader plugin: *rnet.parse()* reads each version of Rep Plus's net
files (9, with link types by their heads and bars; 8 and some 9s, by their
bits; 7, with a "PS:" line; 6, with no link types and no marks), skipping the
records of a drawing, wherever it is; and *reader.buildModel()* makes the
node and relation types, with their looks, the nodes (and their marks), the
relations (one of each type a link has), and the groups, as collections,
which keep their members when the model's saved and read again.

The nets here are made up, small, in the files' formats.

Created on Nov 11, 2026

@author: robkremer
'''
import tempfile
import unittest
from pathlib import Path
from sn.model.model import Collection, Model, Node, Relation
from sn.plugins import importBundled

def net(*lines:str) -> str:
  'A net file: its lines, each a tab-separated row (written here with "|"), ended by CRs, after a byte order mark.'
  return "﻿" + "\r".join(l.replace("|", "\t") for l in lines) + "\r"

V9 = net(
  "|C|9|FFFFE1||40",
  "D|2", "Date|2010-12-11", "NodeType|Concept",
  "T|3",
  "2|0|Arial|9|1|0|000000|FFFFFF|000000|008A00|0|0|0||Concept",
  "0|0|Arial|11|0|20|000000|FFFFFF|000080|000080|0|0|0||Title",
  "0|1|Arial|9|1|521|000000|FFE5B2|815A0E|AC770C|0|0|0|rgrid|Grid",
  "A|5",
  "1|0|0|0|1|0|000000|000000|000000|000000|Includes",
  "1|1|0|0|1|0|00A000|00A000|00A000|00A000|Excludes",
  "0|0|0|0|1|2|0000FF|0000FF|0000FF|0000FF|Coexcludes symmetric",
  "1|0|0|0|516|0|000000|000000|000000|000000|Includes derived",
  "2|0|1|2|1|0|000000|000000|800080|800080|Odd",
  "M|2", "693804|FFCD7D|Asserted", "000000|A6A6A6|Included",
  "N|7|0|-1",
  "0|81|10|20|19|19|A|",
  "0|1A1|50|20|19|19|B|",
  "0|0|90|20|19|19||",
  "1|0|10|60|80|14|Two�lines�|",
  "G7|0|130|20|40|40|drawing|",
  "R|0|0|10|10",
  "T|9|37|text in the drawing",
  "0|3A2|170|20|19|19|C|",
  "-1|0|10|90|60|14|by the program|",
  "L|5|0",
  "0|1|0",
  "1|2|1 0",
  "2|0|0 0|1|57.86",
  "4|0|3",
  "5|1|4",
  "G|3",
  "0 1 2|",
  "3|0",
  "5 6|1 2",
)

V8 = net(
  "|C|8|FF0000||8",
  "D|1", "NodeType|All",
  "T|1",
  "2|0|Arial|9|1|0|8A00|D8FFFF|6400|8A00|0|0||All",
  "A|3",
  "1|FF0000|FF|Entails",
  "5|A9A9A9|C0C0C0|Opposite derived",
  "51|0|0|Equivalent",
  "M|1", "8000|DDFFDD|Asserted",
  "N|2|0",
  "0|0|44|32|23|20|X|",
  "0|0|83|4|23|20|Y|",
  "L|2|0",
  "0|1|0",
  "1|0|1 2",
  "G|0",
)

V6 = net(
  "|C|6|FFFFE1|3|2|0",
  "PS:Base|T:Show Net Structure",
  "T|1",
  "2|2|Arial|9|1|0|8A00|D8FFFF|6400|FF0000|Base",
  "N|3",
  "0|101|76|42|18|young",
  "0 A|23|194|16|18|a",
  "0|219|210|16|18|",
  "L|3|0|2",
  "0|1|1",
  "1|2|5",
  "2|0|1",
)

TRAILING_DRAWING = net(
  "|C|9|FFFFE1||24",
  "T|1",
  "2|0|Arial|9|1|0|000000|FFFFFF|000000|008A00|0|0|0||Concept",
  "A|1",
  "1|0|0|0|1|0|000000|000000|000000|000000|Includes",
  "N|2|0",
  "0|0|10|10|19|19|A|",
  "G-1|0|40|10|200|100||",
  "G|10|-1|0",
  "T|9|377|dislike extremely",
  "L|11|149|11|367",
  "R|0|-2|1|272|148",
  "L|0|0",
  "G|0",
)

class TestParse(unittest.TestCase):

  @classmethod
  def setUpClass(cls):
    cls.rnet = importBundled("rnetReader", "rnet")

  def test_colorsAndLabels(self):
    'Colours as "#rrggbb", even without their leading zeros; a label\'s U+FFFDs are line breaks.'
    self.assertEqual(self.rnet.color("8A00"), "#008a00")
    self.assertEqual(self.rnet.color("FF0000"), "#ff0000")
    self.assertEqual(self.rnet.color("0"), "#000000")
    self.assertEqual(self.rnet.color("rgrid"), "")
    self.assertEqual(self.rnet.label("Two�lines�"), "Two\nlines")

  def test_version9(self):
    'Types, link types by head and bars, mark kinds, nodes and their marks (skipping a drawing\'s records), links, groups.'
    n = self.rnet.parseText(V9, "v9.rnet")
    self.assertEqual((n.version, n.background), (9, "#ffffe1"))
    self.assertEqual(n.settings["NodeType"], "Concept")
    self.assertEqual([t.name for t in n.nodeTypes], ["Concept", "Title", "Grid"])
    concept, title, grid = n.nodeTypes
    self.assertEqual((concept.shape, concept.colors), (2, ["#000000", "#ffffff", "#000000", "#008a00"]))
    self.assertTrue(title.frameless)
    self.assertFalse(concept.frameless)
    self.assertEqual(grid.extra, "rgrid")
    inc, exc, coexc, derived, odd = n.linkTypes
    self.assertEqual((inc.head, inc.headBars, inc.bits, inc.derived), (1, 0, None, False))
    self.assertEqual((exc.head, exc.headBars), (1, 1))
    self.assertEqual((coexc.head, coexc.mid), (0, 2))
    self.assertTrue(derived.derived)
    self.assertEqual((odd.head, odd.tail, odd.tailBars), (2, 1, 2))
    self.assertEqual([k.name for k in n.markKinds], ["Asserted", "Included"])
    self.assertEqual([(x.kind, x.label) for x in n.nodes],
                     [("node", "A"), ("node", "B"), ("node", ""), ("node", "Two\nlines"), ("drawing", "drawing"),
                      ("node", "C"), ("node", "by the program")])
    a, b, anon, note, drawing, c, untyped = n.nodes
    self.assertEqual((a.truth, a.marked, a.derived, a.markKind), ("T", True, False, 0))
    self.assertEqual((b.truth, b.marked, b.derived, b.markKind), ("T", True, True, 1))
    self.assertEqual((c.truth, c.markKind), ("F", 3))
    self.assertEqual((anon.truth, anon.marked), ("", False))
    self.assertEqual((note.type, note.x, note.y, note.w, note.h), (1, 10, 60, 80, 14))
    self.assertEqual((drawing.type, untyped.type), (7, -1))
    self.assertEqual([(l.source, l.destination, l.types, l.extra) for l in n.links],
                     [(0, 1, [0], []), (1, 2, [1, 0], []), (2, 0, [0, 0], ["1", "57.86"]), (4, 0, [3], []), (5, 1, [4], [])])
    self.assertEqual([(g.nodes, g.groups) for g in n.groups], [([0, 1, 2], []), ([3], [0]), ([5, 6], [1, 2])])
    self.assertIn("node 5 ('C') has mark kind 3, which isn't there", n.problems)
    self.assertIn("group 2 has group 2, which isn't there", n.problems)

  def test_version8(self):
    'Link types by their bits, with two colours: the line\'s, then the marks\'.'
    n = self.rnet.parseText(V8, "v8.rnet")
    entails, opposite, equivalent = n.linkTypes
    self.assertEqual((entails.bits, entails.head, entails.tail, entails.mid, entails.colors), (1, 1, 0, 0, ["#ff0000", "#0000ff"]))
    self.assertEqual((opposite.head, opposite.mid, opposite.derived), (1, 1, True))
    self.assertEqual((equivalent.head, equivalent.tail), (3, 3)) # (51: both ends, double)
    self.assertEqual(n.links[1].types, [1, 2])
    self.assertEqual(n.problems, [])

  def test_version6(self):
    'No marks, no link types (made from the links\' codes, which are their bits), a "PS:" line, and "0 A" types.'
    n = self.rnet.parseText(V6, "v6.rnet")
    self.assertEqual(n.settings["PS"], "Base")
    self.assertEqual([(x.type, x.marks, x.x, x.label) for x in n.nodes], [(0, 0, 101, "young"), (0, 0, 23, "a"), (0, 0, 219, "")])
    self.assertEqual([(t.name, t.bits) for t in n.linkTypes], [("Entails", 1), ("Opposite", 5)])
    self.assertEqual([l.types for l in n.links], [[0], [1], [0]])
    self.assertEqual(n.problems, [])

  def test_trailingDrawing(self):
    'The records of a drawing after the last node (some like sections: "G", "T", "L") are skipped, up to the links.'
    n = self.rnet.parseText(TRAILING_DRAWING, "t.rnet")
    self.assertEqual([x.kind for x in n.nodes], ["node", "drawing"])
    self.assertEqual((n.links, n.groups), ([], []))
    self.assertEqual([t.name for t in n.nodeTypes], ["Concept"])
    self.assertEqual(n.problems, [])

  def test_notANet(self):
    with self.assertRaises(ValueError):
      self.rnet.parseText("<xml/>")

class TestBuild(unittest.TestCase):

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

  def build(self, text:str, name:str="net"):
    return self.reader.buildModel(self.rnet.parseText(text, f"{name}.rnet"), str(self.folder / f"{name}.snm"))

  def test_endMarks(self):
    'Heads and bars, written from the source toward the destination.'
    e = self.reader.endMarks
    self.assertEqual(e(1, 0, False), "arrow")
    self.assertEqual(e(1, 1, False), "| arrow")
    self.assertEqual(e(1, 2, True), "arrow ||")
    self.assertEqual(e(3, 0, False), ">>")
    self.assertEqual(e(3, 0, True), "<<")
    self.assertEqual(e(2, 0, False), self.reader.HEAVY_ARROW)
    self.assertEqual(e(0, 0, False), "")

  def test_types(self):
    'Node types with their shapes and colours (2nd fill, 3rd text, 4th outline); relation types with their marks and colour.'
    b = self.build(V9)
    concept, title, grid = (b.nodeTypes[i] for i in range(3))
    self.assertEqual((concept.name, concept["vis/shape"], concept["vis/fillColor"], concept["vis/textColor"], concept["vis/borderColor"]),
                     ("Concept", "Oval", "#ffffff", "#000000", "#008a00"))
    self.assertEqual((title["vis/fillColor"], title["vis/borderColor"]), ("", ""))
    self.assertEqual(grid["vis/shape"], "FileFolder")
    self.assertEqual(concept["vis/label"], self.reader.LABEL)
    self.assertEqual(b.nodeTypes[-1].name, self.reader.UNTYPED) # (for the node with none)
    inc, exc, coexc, derived, odd = (b.linkTypes[i] for i in range(5))
    self.assertEqual((inc["vis/terminator4"], inc["vis/terminator1"], inc["vis/label"], inc["vis/lineType"]), ("arrow", "", "", "straight"))
    self.assertEqual((exc["vis/terminator4"], exc["vis/lineColor"]), ("| arrow", "#00a000"))
    self.assertEqual((coexc["vis/terminator4"], coexc["vis/midMarks"]), ("", "||"))
    self.assertEqual(derived["vis/lineColor"], "#808080") # (black, faded)
    self.assertEqual((odd["vis/terminator1"], odd["vis/terminator4"], odd["vis/lineColor"]),
                     ("arrow ||", self.reader.HEAVY_ARROW, "#800080"))
    for t in [*b.nodeTypes.values(), *b.linkTypes.values()]:
      self.assertFalse(t.isIndividual())
    b8 = self.build(V8, "v8")
    self.assertEqual(b8.linkTypes[0]["vis/lineColor"], "#ff0000") # (bits: the first colour's the line's)
    self.assertEqual(b8.linkTypes[1]["vis/midMarks"], "|")

  def test_nodesMarksRelationsGroups(self):
    'Nodes named by their labels (not the drawing), their marks, a relation of each type of each link, and the groups.'
    b = self.build(V9)
    self.assertEqual(sorted(b.nodes), [0, 1, 2, 3, 5, 6])
    a, nb, anon, note, c = (b.nodes[i] for i in (0, 1, 2, 3, 5))
    self.assertEqual((a.name, anon.name, note.name), ("A", "", "Two\nlines"))
    self.assertEqual((a["mark"], a["markKind"], a["vis/borderColor"], a["vis/borderWidth"]), ("T", "Asserted", "#693804", 3))
    self.assertEqual((nb["mark"], nb["markKind"], nb["markDerived"], nb["marks"]), ("T", "Included", True, "1A1"))
    self.assertEqual(c["mark"], "F") # (its kind isn't there)
    self.assertIsNone(anon.get("mark", None))
    self.assertIn(b.nodeTypes[0], a.getParents())
    rels = [(r.src.name, r.dst.name, r.getParents()[0].name) for r, _ in b.relations]
    self.assertEqual(rels, [("A", "B", "Includes"), ("B", "", "Excludes"), ("B", "", "Includes"), ("", "A", "Includes"),
                            ("C", "B", "Odd")]) # (not "Includes" twice; nor the link from the drawing)
    self.assertEqual(b.relations[3][0]["values"], "1 57.86")
    self.assertIn("1 pictures and drawings", b.report())
    g1, g2, g3 = (b.groups[i] for i in range(3))
    self.assertEqual([g.name for g in (g1, g2, g3)], ["group 1", "group 2", "group 3"])
    self.assertEqual(list(g1.getMembers()), [a, nb, anon])
    self.assertEqual(list(g2.getMembers()), [note, g1])
    self.assertEqual(list(g3.getMembers()), [c, b.nodes[6], g2]) # (not itself)

  def test_savedAndRead(self):
    'Saved and read again: the groups keep their members, and the marks are there.'
    b = self.build(V9)
    b.model.save()
    url = b.model.url
    Model._initCache()
    m = Model.getDB(url)
    groups = {o.name: o for o in m.values() if isinstance(o, Collection) and o.model is m and o.isIndividual()}
    self.assertEqual([str(x.name) for x in groups["group 2"].getMembers()], ["Two\nlines", "group 1"])
    self.assertEqual([str(x.name) for x in groups["group 1"].getMembers()], ["A", "B", ""])
    marked = sorted((str(o.name), o["mark"]) for o in m.values() if isinstance(o, Node) and o.model is m and o.get("mark", None))
    self.assertEqual(marked, [("A", "T"), ("B", "T"), ("C", "F")])
    self.assertEqual(sum(1 for o in m.values() if isinstance(o, Relation) and o.model is m and o.isIndividual()
                         and not type(o).__name__ == "IsaIndividual"), 5)

if __name__ == "__main__":
  unittest.main()
