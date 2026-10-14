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
Opening a file at a line (see *sn.view.graphics.sourceWindow*): the editor's
command, filled in; and, when there's no editor or it can't be run, the
window here instead. (Nothing's run: subprocess.Popen and showSource() are
patched.)

Created on Oct 14, 2026

@author: robkremer
'''
import os
import unittest
from unittest import mock
from sn.view.graphics import sourceWindow
from sn.view.graphics.sourceWindow import editorCommand, EditorCommandError, openSource, EDITOR_PREF

class Test(unittest.TestCase):

  def test0100fillIn(self):
    self.assertEqual(editorCommand("bbedit +{line} {path}", "/a/b c.py", 12), ["bbedit", "+12", "/a/b c.py"])
    self.assertEqual(editorCommand("code -g {path}:{line}", "/a/b.py", 3), ["code", "-g", "/a/b.py:3"])
    self.assertEqual(editorCommand('open "txmt://open?url={url}&line={line}"', "/a/b c&d.py", 7),
                     ["open", "txmt://open?url=file:///a/b%20c%26d.py&line=7"])
    self.assertEqual(editorCommand("ed +{line} {path}", "x.py", 0)[1:], ["+1", os.path.abspath("x.py")]) # (absolute: never an option)
    self.assertEqual(editorCommand("echo {{literal}} {path}", "/x.py", 1), ["echo", "{literal}", "/x.py"])

  def test0200malformed(self):
    for t in ["", "   ", 'open "unclosed', "ed {file}", "ed {0}", "ed {path"]:
      with self.assertRaises(EditorCommandError, msg=t):
        editorCommand(t, "/x.py", 1)

  def test0300noShell(self):
    # a path with shell syntax in it is just a word
    cmd = editorCommand("ed {path}", "/tmp/x; rm -rf ~ $(whoami).py", 1)
    self.assertEqual(cmd, ["ed", "/tmp/x; rm -rf ~ $(whoami).py"])

  def openWith(self, template, popen=None):
    with mock.patch.object(sourceWindow.snPrefs, "get", side_effect=lambda k, d=None, **kw: template if k == EDITOR_PREF else d), \
         mock.patch.object(sourceWindow.subprocess, "Popen", side_effect=popen) as p, \
         mock.patch.object(sourceWindow, "showSource") as show:
      openSource("/a/b.py", 5, 9)
    return p, show

  def test0400openSource(self):
    p, show = self.openWith("bbedit +{line} {path}")
    self.assertEqual(p.call_args.args[0], ["bbedit", "+5", "/a/b.py"])
    self.assertNotIn("shell", p.call_args.kwargs)
    show.assert_not_called()
    p, show = self.openWith("")                              # (no editor: shown here)
    p.assert_not_called()
    show.assert_called_once_with("/a/b.py", 5, 9, None)
    with self.assertLogs("sn.view.graphics.sourceWindow", "WARNING"):
      p, show = self.openWith("nosucheditor {path}", popen=FileNotFoundError(2, "No such file"))
    show.assert_called_once()                                # (couldn't be run: shown here)
    with self.assertLogs("sn.view.graphics.sourceWindow", "WARNING"):
      p, show = self.openWith("ed {file}")
    p.assert_not_called(); show.assert_called_once()

if __name__ == "__main__":
  unittest.main()
