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
The geometry of context windows' containment (*viewContainment*'s functions,
which *ContainmentMixin.containmentHomes()* and *_updateContainment()* use):
which window and pane a point or box belongs in -- nested windows, and a
rule's divider -- *BOTH_PANES*, and what's dropped into or dragged out of a
window.

Created on Oct 18, 2026

@author: robkremer
'''
import unittest
from sn.view.graphics.viewContainment import (BOTH_PANES, rectArea, paneAt, windowAt, homeWindow, homePane,
                                              sharedPane, homeRect, containmentMove)

def rule(x1:float, y1:float, x2:float, y2:float, banner:float=20) -> dict[str, list[float]]:
  'A rule\'s panes (as VObject.panes() makes them): antecedent at the left, consequent at the right, below the banner.'
  mid = (x1 + x2) / 2
  return {"antecedent": [x1, y1 + banner, mid, y2], "consequent": [mid, y1 + banner, x2, y2]}

def context(x1:float, y1:float, x2:float, y2:float, banner:float=20) -> dict[str, list[float]]:
  'A plain context\'s one pane.'
  return {"contains": [x1, y1 + banner, x2, y2]}

# A rule, 0..400 x 0..300 (divider at x=200), with a smaller context window in its consequent, and a
# separate context off to the right.
RULE = ([0, 0, 400, 300], rule(0, 0, 400, 300))
INNER = ([250, 100, 350, 200], context(250, 100, 350, 200))
OTHER = ([500, 0, 700, 200], context(500, 0, 700, 200))
WINDOWS = {"rule": RULE, "inner": INNER, "other": OTHER}

class TestPanes(unittest.TestCase):

  def test_paneAt(self):
    panes = RULE[1]
    self.assertEqual(paneAt(panes, (100, 150)), "antecedent")
    self.assertEqual(paneAt(panes, (300, 150)), "consequent")
    self.assertEqual(paneAt(panes, (200, 150)), "antecedent") # (on the divider: the first, the left one)
    self.assertIsNone(paneAt(panes, (100, 10)))               # (in the banner)
    self.assertIsNone(paneAt(panes, (450, 150)))
    self.assertEqual(paneAt(panes, (0, 300)), "antecedent")    # (edges included)

  def test_rectArea(self):
    self.assertEqual(rectArea([10, 20, 30, 70]), 1000)

  def test_homeRect(self):
    panes = RULE[1]
    self.assertEqual(homeRect(panes, "consequent"), [200, 20, 400, 300])
    band = homeRect(panes, BOTH_PANES) # (astride the divider, a third of the window wide)
    self.assertEqual(band, [200 - 400 / 6, 20, 200 + 400 / 6, 300])
    self.assertAlmostEqual(band[2] - band[0], 400 / 3)

  def test_sharedPane(self):
    self.assertEqual(sharedPane("antecedent", "antecedent"), "antecedent")
    self.assertEqual(sharedPane("antecedent", BOTH_PANES), "antecedent")
    self.assertEqual(sharedPane(BOTH_PANES, "consequent"), "consequent")
    self.assertEqual(sharedPane(BOTH_PANES, BOTH_PANES), BOTH_PANES)
    self.assertEqual(sharedPane("antecedent", "consequent"), BOTH_PANES)

class TestWhichWindow(unittest.TestCase):

  def test_windowAt(self):
    self.assertEqual(windowAt((100, 150), WINDOWS), "rule")
    self.assertEqual(windowAt((300, 150), WINDOWS), "inner")   # (nested: the innermost)
    self.assertEqual(windowAt((300, 110), WINDOWS), "rule")    # (in the inner window's banner: not its pane)
    self.assertEqual(windowAt((600, 100), WINDOWS), "other")
    self.assertIsNone(windowAt((450, 100), WINDOWS))
    self.assertIsNone(windowAt((100, 10), WINDOWS))            # (the rule's banner)
    self.assertIsNone(windowAt((300, 150), {}))

  def test_homeWindow(self):
    self.assertEqual(homeWindow((300, 150), WINDOWS), "inner")  # (the innermost it's in)
    self.assertEqual(homeWindow((100, 150), WINDOWS), "rule")
    self.assertEqual(homeWindow((450, 400), WINDOWS), "inner")  # (in none: the smallest)
    self.assertEqual(homeWindow((450, 400), {"rule": RULE, "other": OTHER}), "other")
    self.assertIsNone(homeWindow((300, 150), {}))
    # a window belongs only in a bigger one
    innerArea = rectArea(INNER[0])
    self.assertEqual(homeWindow((300, 150), {"rule": RULE, "inner2": INNER}, biggerThan=innerArea), "rule")
    self.assertIsNone(homeWindow((300, 150), {"inner2": INNER}, biggerThan=innerArea))
    self.assertIsNone(homeWindow((300, 150), {"rule": RULE}, biggerThan=rectArea(RULE[0])))

  def test_homePaneContains(self):
    panes = INNER[1]
    self.assertEqual(homePane(panes, (300, 150), says=lambda p: True), "contains")
    self.assertEqual(homePane(panes, (900, 900), says=lambda p: False), "contains")
    self.assertEqual(homePane(panes, (900, 900), used={None}), "contains")

  def test_homePaneSaid(self):
    panes = RULE[1]
    says = lambda *said: (lambda p: p in said)
    self.assertEqual(homePane(panes, (300, 150), says=says("antecedent")), "antecedent")  # (as said, wherever it is)
    self.assertEqual(homePane(panes, (300, 150), says=says("consequent")), "consequent")
    self.assertEqual(homePane(panes, (300, 150), says=says("antecedent", "consequent")), "consequent") # (both: the one it's in)
    self.assertEqual(homePane(panes, (100, 150), says=says("antecedent", "consequent")), "antecedent")
    self.assertEqual(homePane(panes, (600, 150), says=says("antecedent", "consequent")), "antecedent") # (in neither: the first)

  def test_homePanePlainContains(self):
    'A rule\'s plain "contains" (its containment says no pane): the pane it\'s in, or the nearer one.'
    panes = RULE[1]
    none = lambda p: False
    self.assertEqual(homePane(panes, (100, 150), says=none), "antecedent")
    self.assertEqual(homePane(panes, (300, 150), says=none), "consequent")
    self.assertEqual(homePane(panes, (350, 10), says=none), "consequent")   # (in the banner: the nearer)
    self.assertEqual(homePane(panes, (-50, 500), says=none), "antecedent")  # (outside: the nearer)
    self.assertEqual(homePane(panes, (900, 150), says=none), "consequent")

  def test_homePaneUsed(self):
    'A variable the window\'s contents use, not contained: the side it\'s used on, or astride the divider.'
    panes = RULE[1]
    self.assertEqual(homePane(panes, (300, 150), used={"antecedent"}), "antecedent")
    self.assertEqual(homePane(panes, (100, 150), used={"consequent"}), "consequent")
    self.assertEqual(homePane(panes, (100, 150), used={"antecedent", "consequent"}), BOTH_PANES)
    self.assertEqual(homePane(panes, (100, 150), used={None}), BOTH_PANES)                # (used by a plain "contains")
    self.assertEqual(homePane(panes, (100, 150), used={"antecedent", None}), BOTH_PANES)

class TestDropAndDrag(unittest.TestCase):

  def test_droppedIn(self):
    panes = RULE[1]
    self.assertEqual(containmentMove(panes, (600, 150), target=True, contained=False), "in")
    self.assertEqual(containmentMove(panes, None, target=True, contained=False), "in")       # (new, made there)
    self.assertEqual(containmentMove(panes, (100, 150), target=True, contained=True), "in")  # (the caller sees it's in already, or switches panes)

  def test_draggedOut(self):
    panes = RULE[1]
    self.assertEqual(containmentMove(panes, (100, 150), target=False, contained=True), "out")
    self.assertEqual(containmentMove(panes, (300, 150), target=False, contained=True), "out")
    # dragged into the inner window, from the rule: out of the rule (into the inner window: target there)
    self.assertEqual(containmentMove(RULE[1], (100, 150), target=False, contained=True), "out")
    self.assertEqual(containmentMove(INNER[1], (100, 150), target=True, contained=False), "in")

  def test_leftBe(self):
    panes = RULE[1]
    self.assertIsNone(containmentMove(panes, (600, 150), target=False, contained=True))   # (it was outside: eg: in the "real world")
    self.assertIsNone(containmentMove(panes, (100, 10), target=False, contained=True))    # (it was in the banner: not a pane)
    self.assertIsNone(containmentMove(panes, None, target=False, contained=True))         # (new)
    self.assertIsNone(containmentMove(panes, (100, 150), target=False, contained=False))  # (not contained: nothing to take out)

  def test_windowMovedToo(self):
    'Whether it was in the window is by where it was relative to the window.'
    panes = RULE[1] # (where the window is now)
    moved = ((700, 650), (200, 150)) # (the window's centre: before, after)
    # it was at (600, 650), in the window where it was (left of its centre): out
    self.assertEqual(containmentMove(panes, (600, 650), target=False, contained=True, windowMove=moved), "out")
    # it was at (100, 150): outside the window where it was
    self.assertIsNone(containmentMove(panes, (100, 150), target=False, contained=True, windowMove=moved))

  def test_draggedAlong(self):
    'A relation dragged along by its ends: in only if both ends are in, out only if neither is.'
    panes = RULE[1]
    inA, inB, out = (100, 150), (300, 150), (600, 150)
    self.assertEqual(containmentMove(panes, (600, 150), target=True, contained=False, endCentres=[inA, inB]), "in")
    self.assertIsNone(containmentMove(panes, (600, 150), target=True, contained=False, endCentres=[inA, out]))
    self.assertIsNone(containmentMove(panes, (600, 150), target=True, contained=False, endCentres=[out]))     # (one end: a dangling relation)
    self.assertEqual(containmentMove(panes, (100, 150), target=False, contained=True, endCentres=[out, out]), "out")
    self.assertIsNone(containmentMove(panes, (100, 150), target=False, contained=True, endCentres=[inA, out]))
    self.assertIsNone(containmentMove(panes, (600, 150), target=False, contained=True, endCentres=[out, out])) # (its label was outside)

if __name__ == "__main__":
  unittest.main()
