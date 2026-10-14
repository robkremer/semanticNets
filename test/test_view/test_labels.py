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
Label and tooltip templates (see *sn.view.graphics.labels*): the
substitutions, and calls to hooks: ``$(module:function)``.

Created on Oct 14, 2026

@author: robkremer
'''
import unittest
from sn.view.graphics.labels import expand, TemplateError, DEFAULT_LABEL, DEFAULT_TOOLTIP

VALUES = {"name": "fred", "note": "a note", "empty": "", "vis/x": "slashed"}
lookup = lambda key: VALUES.get(key, "")
CALLED = []
def call(ref):
  CALLED.append(ref)
  return {"m.n:code": "def f():\n  pass", "m:nothing": ""}.get(ref, "?")

class Test(unittest.TestCase):

  def setUp(self):
    CALLED.clear()

  def test0100substitutions(self):
    self.assertEqual(expand("$name", lookup), "fred")
    self.assertEqual(expand("${name}s", lookup), "freds")
    self.assertEqual(expand("${note:+[$note]}", lookup), "[a note]")
    self.assertEqual(expand("${empty:+[$note]}", lookup), "")
    self.assertEqual(expand("${empty:-none}", lookup), "none")
    self.assertEqual(expand("$$name\\n${vis/x}", lookup), "$name\nslashed")
    self.assertEqual(expand(DEFAULT_LABEL, lookup), "fred")

  def test0200calls(self):
    self.assertEqual(expand("$name:\\n$(m.n:code)", lookup, call), "fred:\ndef f():\n  pass")
    self.assertEqual(CALLED, ["m.n:code"])
    self.assertEqual(expand("$( m.n:code )", lookup, call), "def f():\n  pass")
    self.assertEqual(expand("${note:+$(m.n:code)}", lookup, call), "def f():\n  pass")
    self.assertEqual(expand("${empty:+$(m.n:code)}", lookup, call), "")
    self.assertNotIn("m.n:code", CALLED[3:]) # (not called when it isn't used)

  def test0300callsAsKeys(self):
    self.assertEqual(expand("${(m.n:code):+---\\n}$(m.n:code)", lookup, call), "---\ndef f():\n  pass")
    self.assertEqual(expand("${(m:nothing):+---}", lookup, call), "")
    self.assertEqual(expand("${(m:nothing):-no code}", lookup, call), "no code")
    self.assertEqual(expand("${(m.n:code)}", lookup, call), "def f():\n  pass")

  def test0400badCalls(self):
    for t in ["$(m:code", "$(code)", "$(m:a b)", "${(m:code)x}", "$()"]:
      with self.assertRaises(TemplateError, msg=t):
        expand(t, lookup, call)
    with self.assertRaises(TemplateError): # (no call given: hooks aren't allowed)
      expand("$(m.n:code)", lookup)

  def test0500defaultTooltip(self):
    self.assertEqual(expand(DEFAULT_TOOLTIP, lookup), "fred\n" + "▔"*18 + "\nNOTE:\na note")
    self.assertEqual(expand(DEFAULT_TOOLTIP, lambda k: {"name": "ann"}.get(k, "")), "ann")

if __name__ == "__main__":
  unittest.main()
