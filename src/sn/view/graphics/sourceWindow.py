'''
Showing a file at a line -- eg: a class or function's source (see
pythonParser) -- in the user's editor, or, failing that, in a read-only
window of its own here (*SourceWindow*).

The editor is the "gui/editorCommand" preference: a command, with ``{path}``,
``{line}`` and ``{url}`` (the file's ``file:`` URL, for URL schemes) in it --
eg: ``bbedit +{line} {path}``. It's split into words as a shell would (quotes
keep a word together), each word filled in, and run *without* a shell: so
whatever's in the path, it's only ever the file to open (and never an
option: it's always an absolute path). Empty, or if it can't be run, the
built-in window's used.

Eg (and see the preference's note, in *sn.PREFS*): for an Eclipse that's
running, on a Mac -- its launcher would start another, which finds the
workspace in use -- an AppleScript sends it the file as "path:line", which
Eclipse takes apart (giving its own app's path; the first time, macOS asks
whether this may control Eclipse)::

  osascript -e "on run a" -e "tell application \\"/Applications/Eclipse.app\\" to open (POSIX file (item 1 of a))" -e "end run" {path}:{line}

Created on Oct 14, 2026

.. codeauthor:: Rob Kremer <robkremer@me.com>
'''
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
from __future__ import annotations
import os
import shlex
import subprocess
import tkinter as tk
from pathlib import Path
from typing import Any
import sn
from sn import snPrefs
from util.utils import ownDialog

logger:sn.SNLogger = sn.getLogger(__name__)

EDITOR_PREF = "gui/editorCommand"
"The preference giving the editor's command (see the module doc, and its note in *sn.PREFS*)."


class EditorCommandError(ValueError):
  'An editor command that can\'t be made sense of.'

def editorCommand(template:str, path:str, line:int) -> list[str]:
  '''
  :param template: The command (see the module doc).
  :type template: str
  :param path: The file.
  :type path: str
  :param line: The line (1-based).
  :type line: int
  :returns: The command's words, filled in (see the module doc).
  :rtype: list[str]
  :raises EditorCommandError: If it's malformed: eg: an unclosed quote, a
    "{" that isn't one of {path}, {line} or {url} (use "{{" for a "{"), or
    it's empty.
  '''
  path = os.path.abspath(path)
  values = {"path": path, "line": str(max(1, int(line))), "url": Path(path).as_uri()}
  try:
    words = shlex.split(template)
  except ValueError as ex:
    raise EditorCommandError(f'{template!r}: {ex}') from None
  if not words:
    raise EditorCommandError("the command is empty")
  try:
    return [w.format(**values) for w in words]
  except (KeyError, IndexError, ValueError) as ex:
    raise EditorCommandError(f'{template!r}: can\'t fill in {ex} (only {{path}}, {{line}} and {{url}})') from None

def openSource(path:str, line:int=1, end:int|None=None, parent:Any=None) -> None:
  '''
  Show *path* at *line*: in the editor (see the module doc), or in a
  *SourceWindow*, with lines *line* to *end* highlighted.

  :param path: The file.
  :type path: str
  :param line: The line (1-based).
  :type line: int
  :param end: The last line of what to highlight, in the window here (an
    editor's told only *line*).
  :type end: int | None
  :param parent: What it's opened from (for the window here), if anything.
  :type parent: Any
  '''
  template = str(snPrefs.get(EDITOR_PREF, "") or "").strip()
  if template:
    try:
      cmd = editorCommand(template, path, line)
      subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       start_new_session=True)
      return
    except (EditorCommandError, OSError) as ex:
      why = str(ex)
      if isinstance(ex, OSError) and os.path.isdir(os.path.expanduser(cmd[0])):
        why = (f'{cmd[0]} is a folder, not a program' +
               (f' -- an app: name the program in it (eg: {os.path.join(cmd[0], "Contents", "MacOS", "...")}), '
                f'or use "open -a"' if cmd[0].rstrip("/").endswith(".app") else ""))
      logger.warning(f'Couldn\'t open {os.path.basename(path)} in the editor (the "{EDITOR_PREF}" setting): '
                     f'{why}. Showing it here instead.')
  showSource(path, line, end, parent)

_windows:dict[str, SourceWindow] = {}
"The source windows open, by file: a file's shown in one, again (see *showSource()*)."

def showSource(path:str, line:int=1, end:int|None=None, parent:Any=None) -> SourceWindow|None:
  '''
  Show *path* in a *SourceWindow* -- the one it's already in, if there is
  one, read afresh -- at *line*, with lines *line* to *end* highlighted.

  :param path: The file.
  :type path: str
  :param line: The line (1-based).
  :type line: int
  :param end: The last line to highlight; default: *line*.
  :type end: int | None
  :param parent: What it's opened from, if anything.
  :type parent: Any
  :returns: The window; None if the file can't be read (logged).
  :rtype: SourceWindow | None
  '''
  path = os.path.abspath(path)
  try:
    with open(path, encoding="utf-8", errors="replace") as f:
      text = f.read()
  except OSError as ex:
    logger.error(f'Can\'t show {path}: {ex.strerror or ex}.')
    return None
  w = _windows.get(path)
  if w is None or not w.winfo_exists():
    w = _windows[path] = SourceWindow(path, parent)
  w.show(text, line, end if end is not None else line)
  return w

class SourceWindow(tk.Toplevel):
  '''A file, read-only, with line numbers, and some lines highlighted (see *showSource()*).'''

  HIGHLIGHT = "#fff2b3"
  "The highlighted lines' background."

  def __init__(self, path:str, parent:Any=None):
    '''
    :param path: The file.
    :type path: str
    :param parent: What it's opened from, if anything.
    :type parent: Any
    '''
    root = parent.winfo_toplevel() if isinstance(parent, tk.Misc) else tk._get_default_root() #type: ignore[attr-defined]
    super().__init__(root)
    ownDialog(self, parent) # (over its parent's window, not full screen: see ownDialog())
    self.path = path
    self.title(os.path.basename(path))
    self.geometry("820x600")
    frame = tk.Frame(self)
    frame.pack(fill=tk.BOTH, expand=True)
    self.text = tk.Text(frame, wrap=tk.NONE, font="TkFixedFont", undo=False, background="white",
                        foreground="black", insertwidth=0, padx=4)
    ys = tk.Scrollbar(frame, orient=tk.VERTICAL, command=self.text.yview)
    xs = tk.Scrollbar(frame, orient=tk.HORIZONTAL, command=self.text.xview)
    self.text.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
    ys.pack(side=tk.RIGHT, fill=tk.Y)
    xs.pack(side=tk.BOTTOM, fill=tk.X)
    self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    self.text.tag_configure("number", foreground="grey55")
    self.text.tag_configure("chunk", background=self.HIGHLIGHT)
    self.text.tag_lower("chunk") # (under the selection)
    self.status = tk.Label(self, text=path, anchor=tk.W, foreground="grey40")
    self.status.pack(side=tk.BOTTOM, fill=tk.X)
    self.bind("<Escape>", lambda _e: self.destroy())
    self.bind("<Command-w>" if self.tk.call("tk", "windowingsystem") == "aqua" else "<Control-w>",
              lambda _e: self.destroy())

  def show(self, text:str, line:int, end:int) -> None:
    '''
    Show *text* (the file's), with lines *line* to *end* highlighted, and
    scrolled so that *line* is near the top.

    :param text:
    :type text: str
    :param line: The first line to highlight (1-based).
    :type line: int
    :param end: The last.
    :type end: int
    '''
    lines = text.split("\n")
    if lines and lines[-1] == "":
      lines.pop()
    width = len(str(len(lines)))
    t = self.text
    t.configure(state=tk.NORMAL)
    t.delete("1.0", tk.END)
    for i, l in enumerate(lines, 1):
      t.insert(tk.END, f"{i:>{width}}  ", "number")
      t.insert(tk.END, l + ("\n" if i < len(lines) else ""))
    line = max(1, min(line, len(lines)))
    end = max(line, min(end, len(lines)))
    t.tag_add("chunk", f"{line}.0", f"{end}.end+1c")
    t.configure(state=tk.DISABLED) # (read-only: it can still be selected and copied)
    self.status.configure(text=f"{self.path}  --  lines {line}-{end}" if end > line else f"{self.path}  --  line {line}")
    t.update_idletasks()
    t.yview_moveto(0)
    t.see(f"{max(1, line - 3)}.0")
    t.yview(f"{max(1, line - 3)}.0")
    self.deiconify()
    self.lift()
    self.focus_set()
