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
*fadeColor()* (an inferred object's colours) remembers what it worked out on
the canvas, for the canvas's background at the time: a changed background
gets its own, and the result is the same as working it out afresh.

Created on Oct 18, 2026

@author: robkremer
'''
import unittest
from sn.view.graphics.vobjects import fadeColor

class StandInCanvas:
  'Just what *fadeColor()* asks of a Tk canvas, counting the *winfo_rgb()* calls.'
  RGB = {"white": (65535, 65535, 65535), "black": (0, 0, 0), "red": (65535, 0, 0), "#0000ff": (0, 0, 65535)}

  def __init__(self, background:str):
    self.background = background
    self.rgbCalls = 0

  def cget(self, option:str) -> str:
    assert option == "background"
    return self.background

  def winfo_rgb(self, color:str) -> tuple[int, int, int]:
    self.rgbCalls += 1
    return self.RGB[color]

class Test(unittest.TestCase):

  def test_remembered(self):
    c = StandInCanvas("white")
    self.assertEqual(fadeColor(c, "red", 0.4), "#ff9999")
    self.assertEqual(c.rgbCalls, 2)
    self.assertEqual(fadeColor(c, "red", 0.4), "#ff9999")
    self.assertEqual(c.rgbCalls, 2) # (remembered)
    self.assertEqual(fadeColor(c, "red", 1), "#ff0000") # (another amount: worked out)
    self.assertEqual(fadeColor(c, "#0000ff", 0.4), "#9999ff")
    self.assertEqual(c.rgbCalls, 6)

  def test_backgroundChanged(self):
    c = StandInCanvas("white")
    self.assertEqual(fadeColor(c, "red", 0.4), "#ff9999")
    c.background = "black" # (eg: configure(background="black"))
    self.assertEqual(fadeColor(c, "red", 0.4), "#660000")
    c.background = "white"
    self.assertEqual(fadeColor(c, "red", 0.4), "#ff9999")
    self.assertEqual(c.rgbCalls, 4)

  def test_perCanvas(self):
    a, b = StandInCanvas("white"), StandInCanvas("black")
    self.assertEqual(fadeColor(a, "red", 0.4), "#ff9999")
    self.assertEqual(fadeColor(b, "red", 0.4), "#660000")

  def test_unreadable(self):
    c = StandInCanvas("white")
    self.assertEqual(fadeColor(c, "no such colour", 0.4), "no such colour")
    self.assertEqual(fadeColor(c, "no such colour", 0.4), "no such colour") # (not remembered: tried again)
    self.assertEqual(c.rgbCalls, 2)

if __name__ == "__main__":
  unittest.main()
