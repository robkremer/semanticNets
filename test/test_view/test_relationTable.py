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
The layouts' relation table (see *sn.view.graphics.relationTable*): saving
it, what each relation does, and the rows the dialog shows.

Created on Oct 17, 2026

@author: robkremer
'''
import tempfile
import unittest
from pathlib import Path
from sn.model.model import Model, Node, Relation
from sn.view.graphics.layout import LayoutHeuristic
from sn.view.graphics.relationTable import (RelationTable, RelationRow, SHAPES, PULLS, IGNORED, TERMINALS,
                                            defaultParentEnd)
from sn.view.graphics.treeLayout import TreeLayout, upgradeRelation
import sn.view.graphics.balloonLayout # (registers the balloon and radial layouts)

def rows(table):
  return [(r.relation, r.role, r.parentEnd) for r in table.rows]

class Test(unittest.TestCase):

  def setUp(self):
    self.tmp = tempfile.TemporaryDirectory()
    m = self.m = Model(str(Path(self.tmp.name) / "t.snm"))
    person = Node(m, [m.NODE], name="person")
    self.hasAncestor = Relation(m, [m.RELATION], person, person, name="has-ancestor")
    self.hasParent = Relation(m, [self.hasAncestor], person, person, name="has-parent")
    self.hasMother = Relation(m, [self.hasParent], person, person, name="has-mother")
    self.likes = Relation(m, [m.RELATION], person, person, name="likes")
    a, b = Node(m, [person], individual=True, name="a"), Node(m, [person], individual=True, name="b")
    self.aMotherB = Relation(m, [self.hasMother], a, b, individual=True)
    self.aLikesB = Relation(m, [self.likes], a, b, individual=True)
    self.aIsa = next(r for r in m.values() if isinstance(r, Relation) and r.isIndividual() and r.src is a and r.dst is person)

  def tearDown(self):
    self.tmp.cleanup()

  def test0100encoding(self):
    t = RelationTable([RelationRow("a:b,c;d|e=f%", SHAPES, "source"), RelationRow("isa", IGNORED), RelationRow(TERMINALS)])
    self.assertNotRegex(t.encode(), r"[;|=]")                       # (safe in a view's layout parameters)
    self.assertEqual(RelationTable.decode(t.encode()), t)
    self.assertEqual(rows(t)[1:], [("isa", IGNORED, "destination"), (TERMINALS, PULLS, "destination")])
    self.assertEqual(rows(RelationTable.decode("isa:shapes:destination,junk,x:bad:source")), [("isa", SHAPES, "destination")])

  def test0200defaults(self):
    self.assertEqual([defaultParentEnd(n) for n in ("isa", "has-parent", "includes", TERMINALS)],
                     ["destination", "destination", "source", "destination"])
    self.assertEqual(rows(RelationTable.single("includes", "source")), [("includes", SHAPES, "source"), (TERMINALS, PULLS, "destination")])

  def test0300oldSettingsConvert(self):
    state = upgradeRelation({"name": "radial", "relation": "has-property", "parentEnd": "source", "spacing": "20"})
    self.assertEqual(state, {"name": "radial", "relations": RelationTable.single("has-property", "source").encode(), "spacing": "20"})
    for name in ("tree", "balloon", "radial"):
      cls, kwargs, _ = LayoutHeuristic.decodeParameters(f"name={name};relation=has-property;parentEnd=source;spacing=20") #type: ignore[misc]
      self.assertEqual(RelationTable.decode(kwargs["relations"]), RelationTable.single("has-property", "source"), name)
    self.assertNotIn("relation", [p.name for p in TreeLayout.PARAMETERS])

  def test0400mostSpecificRowWins(self):
    t = RelationTable([RelationRow("has-ancestor", PULLS), RelationRow("isa", SHAPES), RelationRow("has-parent", SHAPES, "destination"),
                       RelationRow(TERMINALS, IGNORED)])
    roles = t.roles(self.m)
    self.assertEqual(roles.rowOf(self.aMotherB)[0], 2)              # has-mother: under has-parent (not has-ancestor, earlier)
    self.assertEqual(roles.role(self.aMotherB), SHAPES)
    self.assertEqual(roles.rank(self.aIsa), 1)
    self.assertEqual(roles.role(self.aLikesB), PULLS)              # (no row: pulls together, after all the rows)
    self.assertEqual(roles.rank(self.aLikesB), 4)
    self.assertEqual(roles.role(None), IGNORED)                     # (the relation types' ends)
    self.assertEqual(roles.group(self.aMotherB), 1)                 # (has-parent's first direct subtype)
    self.assertEqual(roles.parentEnd(self.aMotherB), "destination")

  def test0500dialogRows(self):
    t = RelationTable([RelationRow("has-parent", SHAPES, "source"), RelationRow("isa", PULLS)])
    shown = [self.likes, self.hasMother, self.hasParent]
    self.assertEqual(rows(t.expanded(self.m, shown)),
                     [("has-parent", SHAPES, "source"), ("has-mother", SHAPES, "source"),   # (as its row did)
                      ("isa", PULLS, "destination"), ("likes", PULLS, "source"),            # (no row: pulls together)
                      (TERMINALS, PULLS, "destination")])

  def test0600hubsFollowTheTableIfAsked(self):
    from sn.view.graphics.balloonLayout import HubLayout, HUB_RELATIONS
    self.assertEqual(HUB_RELATIONS, ("all", "as in the table"))
    self.assertEqual({p.name: p.default for p in HubLayout.PARAMETERS}["follow"], "all")   # (as it was)
    cls, kwargs, _ = LayoutHeuristic.decodeParameters("name=hubs;follow=as in the table;relations=isa:ignored:destination") #type: ignore[misc]
    self.assertIs(cls, HubLayout)
    self.assertEqual((kwargs["follow"], rows(RelationTable.decode(kwargs["relations"]))), ("as in the table", [("isa", IGNORED, "destination")]))

if __name__ == "__main__":
  unittest.main()
