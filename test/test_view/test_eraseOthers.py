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
What "erase everything else" keeps (see *sn.view.graphics.sngView.keptWith()*):
the part that needs no screen. Objects are strings; relations are "a-b" (from
a to b, with "_" for a dangling end; names, as identifiers, are interned); windows hold what *WINDOWS* says.

Created on Oct 13, 2026

@author: robkremer
'''
import sys
import unittest
from sn.view.graphics.sngView import keptWith

def ends(o):
  if "-" not in o:
    return None
  src, dst = (sys.intern(e) for e in o.split("-", 1)) # (the same objects as the names written here: keptWith() goes by identity)
  return (None if src == "_" else src, None if dst == "_" else dst)

def kept(keep, objects, windows=None):
  windows = windows or {}
  return set(keptWith(keep, objects, ends, lambda o: windows.get(o, [])))

class Test(unittest.TestCase):

  def test0100justTheNode(self):
    self.assertEqual(kept(["a"], ["a", "b", "c", "a-b", "b-c"]), {"a"})

  def test0200relationsAmongKept(self):
    objs = ["a", "b", "c", "a-b", "b-a", "b-c", "a-a", "c-a"]
    self.assertEqual(kept(["a", "b"], objs), {"a", "b", "a-b", "b-a", "a-a"})

  def test0300keptRelationKeepsItsEnds(self):
    self.assertEqual(kept(["a-b"], ["a", "b", "c", "a-b", "b-c"]), {"a", "b", "a-b"})

  def test0400relationOnARelation(self):
    # c-(a-b): a relation whose end is a relation: kept when both its ends are
    objs = ["a", "b", "c", "a-b", "c-a-b"]
    ends2 = lambda o: {"a-b": ("a", "b"), "c-a-b": ("c", "a-b")}.get(o)
    self.assertEqual(set(keptWith(["a", "b", "c"], objs, ends2, lambda o: [])), set(objs))
    self.assertEqual(set(keptWith(["c-a-b"], objs, ends2, lambda o: [])), set(objs))
    self.assertEqual(set(keptWith(["a", "c"], objs, ends2, lambda o: [])), {"a", "c"})

  def test0500danglingRelationTypes(self):
    self.assertEqual(kept(["a"], ["a", "a-_", "_-a"]), {"a"})

  def test0600windows(self):
    windows = {"rule": ["x", "y", "inner"], "inner": ["z"], "other": ["w"]}
    objs = ["rule", "inner", "other", "x", "y", "z", "w", "rule-x", "rule-y", "x-y"]
    self.assertEqual(kept(["x"], objs, windows), {"x", "rule", "rule-x"})
    self.assertEqual(kept(["z"], objs, windows), {"z", "inner", "rule"})
    # a window kept for itself keeps what's in it (nested too), and the relations among them
    self.assertEqual(kept(["rule"], objs, windows), {"rule", "inner", "x", "y", "z", "rule-x", "rule-y", "x-y"})
    self.assertEqual(kept(["inner"], objs, windows), {"inner", "z", "rule"})

if __name__ == "__main__":
  unittest.main()
