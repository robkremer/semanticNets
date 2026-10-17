'''
pythonParser: a plugin (see *sn.plugins*) that makes a model of a Python
program -- its packages, modules, classes, functions, methods, doc strings
and imports -- and a view of it, from the Tools menu's "Python Parser..."
(see *dialog*). It's built on the ontology pythonOntology.snm, in this folder,
whose types name the hooks (see *hooks*) that show a class's or function's
code from the view.

  - *parser*: reads the Python files, and makes the model;
  - *source*: finds a class or function in its file again, as it is now;
  - *hooks*: the menu items, tooltips and double-clicks the ontology names;
  - *dialog*: the front end, and the view.

Created on Oct 10, 2026 (a plugin since Oct 17)

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
from typing import Any

_dialog:Any = None
"The dialog, while it's open: the menu item brings it to the front rather than opening another."

def register(ctx:Any) -> None:
  '''
  Add "Python Parser..." to the Tools menu (see *sn.plugins.PluginContext*).

  :param ctx: The plugin's context.
  :type ctx: sn.plugins.PluginContext
  '''
  def openDialog() -> None:
    global _dialog
    if _dialog is not None and _dialog.winfo_exists():
      _dialog.lift()
      _dialog.focus_force()
      return
    from .dialog import Options, ParserDialog # (here: tkinter, the views, ... only once it's used)
    def closed() -> None:
      global _dialog
      _dialog = None
    _dialog = ParserDialog(ctx.app, [], Options(), onClose=closed)
  ctx.addMenuItem("Python Parser...", openDialog)
