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
The PDF drawing behind "copy as picture" (see *sn.view.graphics.imageExport*):
the parts that need no screen.

Created on Oct 8, 2026

@author: robkremer
'''
import re
import unittest
from sn.view.graphics.imageExport import PDF, splineSegments, arrowHead


class Test(unittest.TestCase):

  def test0100straight(self):
    pts = [(0, 0), (10, 0), (10, 10)]
    self.assertEqual(splineSegments(pts, "0", closed=False), [((0, 0),), ((10, 0),), ((10, 10),)])

  def test0200tkSpline(self): # (Tk's: ends at the end points, through the midpoints of the inner segments)
    segs = splineSegments([(0, 0), (10, 0), (10, 10), (20, 10)], "true", closed=False)
    self.assertEqual(segs[0], ((0, 0),))
    self.assertEqual([s[-1] for s in segs[1:]], [(10, 5), (20, 10)])
    self.assertTrue(all(len(s) == 3 for s in segs[1:]))

  def test0300closedSpline(self):
    segs = splineSegments([(0, 0), (10, 0), (10, 10), (0, 10)], "true", closed=True)
    self.assertEqual(len(segs), 5)
    self.assertEqual(segs[0][0], segs[-1][-1])                     # (it closes)

  def test0400arrowHead(self):
    head, end = arrowHead((100, 0), (0, 0), 1.0, (8, 10, 3))
    self.assertEqual(head[0], (100, 0))                            # the tip
    self.assertEqual(head[2], (92, 0))                             # the neck, 8 back
    self.assertAlmostEqual(abs(head[1][1]), 3.5)                   # trailing points 3 out from the line's edge
    self.assertLess(end[0], 100)                                   # the line stops under the head
    self.assertGreater(end[0], 90)

  def test0500pdf(self):
    p = PDF([0, 0, 100, 50], scale=2)
    p.color((1, 0, 0), stroke=True)
    p.path([((0, 0),), ((100, 50),)], close=False)
    p.paint(False, True)
    p.text(10, 20, b"(a) \\ b", "Helvetica", 12)
    data = p.bytes()
    self.assertTrue(data.startswith(b"%PDF-1.4"))
    self.assertIn(b"/MediaBox [0 0 200.00 100.00]", data)
    self.assertIn(b"/BaseFont /Helvetica", data)
    start = int(re.search(rb"startxref\n(\d+)", data).group(1)) # type: ignore[union-attr]       # the cross-reference table is where it says
    self.assertTrue(data[start:].startswith(b"xref"))
    for n, off in enumerate(re.findall(rb"(\d{10}) 00000 n", data), 1): # and so is each object
      self.assertTrue(data[int(off):].startswith(f"{n} 0 obj".encode()))


if __name__ == "__main__":
  unittest.main()
