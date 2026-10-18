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
The terminal pane flashes when a warning, error or exception (anything printed
in the "stderr" style) arrives -- once per burst of such lines -- but not for
ordinary output (*TerminalWidget._noteErrorLine()*).

Created on Oct 16, 2026

@author: robkremer
'''
import unittest
import sys
import builtins
import logging
import time
import tkinter as tk
from util import terminal
from util.terminal import TerminalWidget

class TestTerminalFlash(unittest.TestCase):

  @classmethod
  def setUpClass(cls):
    # (a TerminalWidget routes stdout, stderr, input(), logging and excepthook
    # to itself: put them all back afterwards)
    cls.saved = (sys.stdout, sys.stderr, builtins.input, sys.excepthook,
                 list(logging.getLogger().handlers), terminal._installedIORoutingRegistry)
    try:
      cls.root = tk.Tk()
    except tk.TclError as ex:
      raise unittest.SkipTest(f"no display: {ex}")
    cls.root.withdraw()

  @classmethod
  def tearDownClass(cls):
    cls.root.destroy()
    sys.stdout, sys.stderr, builtins.input, sys.excepthook, handlers, terminal._installedIORoutingRegistry = cls.saved
    logging.getLogger().handlers[:] = handlers

  def setUp(self):
    self.term = TerminalWidget(self.root, onLine=lambda line: None, bg="white",
                               queryFlashColor="red", errorFlashCount=2, errorBurstGapMs=500)

  def tearDown(self):
    if self.term.winfo_exists():
      self.term.destroy()

  def flashing(self) -> bool:
    return self.term._flashJob is not None

  def test_ordinaryOutputDoesntFlash(self):
    self.term.printLine("hello", style="stdout")
    self.term.printLine("world")
    self.term.printLine("42", style="result")
    self.assertFalse(self.flashing())
    self.assertEqual(self.term.cget("bg"), "white")

  def test_errorFlashes(self):
    self.term.printLine("WARNING: look out", style="stderr")
    self.assertTrue(self.flashing())
    self.assertEqual(self.term.cget("bg"), "red")

  def test_flashReverts(self):
    self.term.printLine("ERROR: oops", style="stderr")
    self.term.queryFlashIntervalMs = 5
    deadline = time.monotonic() + 5
    while self.flashing() and time.monotonic() < deadline:
      self.root.update()
    self.assertFalse(self.flashing())
    self.assertEqual(self.term.cget("bg"), "white")

  def test_burstFlashesOnce(self):
    starts = []
    original = self.term._flashTick
    def countingTick(ticksRemaining, untilReply=True):
      if ticksRemaining == self.term.errorFlashCount * 2:
        starts.append(ticksRemaining)
      original(ticksRemaining, untilReply)
    self.term._flashTick = countingTick
    for line in ["Exception in Tkinter callback", "Traceback (most recent call last):",
                 '  File "x.py", line 1, in f', "ZeroDivisionError: division by zero"]:
      self.term.printLine(line, style="stderr")
    self.assertEqual(len(starts), 1)
    # (the flash ends, but the next line is still part of the burst: no new flash)
    self.term._stopQueryFlash()
    self.term.printLine("ERROR: and another", style="stderr")
    self.assertEqual(len(starts), 1)
    # (a quiet spell ends the burst: the next error flashes again)
    self.term._lastErrorTime -= 1.0
    self.term.printLine("ERROR: later", style="stderr")
    self.assertEqual(len(starts), 2)

  def test_offWhenCountIsZero(self):
    self.term.errorFlashCount = 0
    self.term.printLine("ERROR: oops", style="stderr")
    self.assertFalse(self.flashing())

  def test_loggedWarningAndErrorFlash(self):
    terminal.terminalRegistry.bindThreadToTerminal(self.term)
    try:
      logging.getLogger("test").warning("look out")
      self.assertTrue(self.flashing())
      self.term._stopQueryFlash()
      self.term._lastErrorTime -= 1.0
      logging.getLogger("test").error("oops")
      self.assertTrue(self.flashing())
      self.term._stopQueryFlash()
      self.term._lastErrorTime -= 1.0
      logging.getLogger("test").info("just saying") # (style "stdout")
      self.assertFalse(self.flashing())
    finally:
      terminal.terminalRegistry.unbindThread()

  def test_tkCallbackExceptionFlashes(self):
    # (stderr routed to the terminal, as installGlobalIORouting() leaves it -- set
    # here, as a test runner that captures each test's output, eg: PyDev's, or
    # unittest -b, puts its own stream there after the first test's terminal routed it)
    stderr = sys.stderr
    sys.stderr = terminal.LineBufferedRoutingStream(terminal.terminalRegistry, style="stderr")
    terminal.terminalRegistry.bindThreadToTerminal(self.term)
    try:
      try:
        1/0
      except ZeroDivisionError as ex:
        self.root.report_callback_exception(type(ex), ex, ex.__traceback__)
      sys.stderr.flush()
      self.assertTrue(self.flashing())
      self.assertIn("ZeroDivisionError", self.term.get("1.0", "end"))
    finally:
      terminal.terminalRegistry.unbindThread()
      sys.stderr = stderr

  def test_safeIfDestroyedMidFlash(self):
    self.term.printLine("ERROR: oops", style="stderr")
    tick = self.term._flashTick
    self.term.destroy()
    self.assertIsNone(self.term._flashJob)
    tick(3, False) # (a tick that was already on its way)
    self.assertIsNone(self.term._flashJob)

if __name__ == "__main__":
  unittest.main()
