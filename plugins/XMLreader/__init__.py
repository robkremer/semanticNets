'''
XMLreader: a plugin (see *sn.plugins*) that makes a model of an XML file --
a type for each tag, an individual for each element, and relations for their
nesting (each a kind of xml-has-part), on an ontology of its own (the types,
and the definition of xml-part-of) -- and a view of it, arranged, from the
Tools menu's "XML Reader...".

  - *reader*: reads the XML file, and makes the model;
  - *view*: the front end, and the view;
  - *examples*: some XML files to try.

Created on Oct 3, 2026 (a plugin since Oct 17)

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
from typing import Any

_dialog:Any = None
"The dialog, while it's open: the menu item brings it to the front rather than opening another."

def register(ctx:Any) -> None:
  '''
  Add "XML Reader..." to the Tools menu (see *sn.plugins.PluginContext*): its
  dialog (see *view.ReaderDialog*) asks for the file -- in the folder last
  read from, or at first the plugin's examples -- and the files to make of it,
  and makes them (see *view.convert()*). Those of the plugin's own examples
  are made in the example models' folder (see *Application.EXAMPLES_FOLDER*)
  by default, not in the plugin's folder, which is replaced when a newer
  version's installed.

  :param ctx: The plugin's context.
  :type ctx: sn.plugins.PluginContext
  '''
  def openDialog() -> None:
    global _dialog
    if _dialog is not None and _dialog.winfo_exists():
      _dialog.lift()
      _dialog.focus_force()
      return
    from .view import ReaderDialog, defaultPaths # (here: tkinter, the views, ... only once it's used)
    def defaults(xmlPath:str) -> tuple[str, str, str]:
      mine = os.path.commonpath([os.path.realpath(xmlPath), os.path.realpath(ctx.folder)]) == os.path.realpath(ctx.folder)
      return defaultPaths(xmlPath, os.path.expanduser(ctx.app.EXAMPLES_FOLDER) if mine else None)
    def closed() -> None:
      global _dialog
      _dialog = None
    _dialog = ReaderDialog(ctx.app, folder=ctx.pref("lastFolder", None) or os.path.join(ctx.folder, "examples"),
                           defaults=defaults, onChosen=lambda path: ctx.setPref("lastFolder", os.path.dirname(path)),
                           onClose=closed)
  ctx.addMenuItem("XML Reader...", openDialog)
