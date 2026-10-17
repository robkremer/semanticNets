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
Plugins (see *sn.plugins*): installing the bundled ones, reading their
manifests, loading them -- into a scratch plugins folder, with a menu bar on a
plain Tk root standing in for the editor's -- and their menu items and hooks.

Created on Oct 17, 2026

@author: robkremer
'''
import os
import sys
import tempfile
import textwrap
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
import sn
from sn import hooks, plugins

def makePlugin(folder:Path, name:str, version:str="1.0", init:str="def register(ctx):\n  pass\n",
               snVersion:str="1.0", files:dict[str, str]|None=None) -> Path:
  path = folder / name
  path.mkdir(parents=True)
  (path / plugins.MANIFEST).write_text(f'name = "{name} plugin"\nversion = "{version}"\n'
                                       f'description = "A test."\nsn-version = "{snVersion}"\n')
  (path / "__init__.py").write_text(textwrap.dedent(init))
  for f, text in (files or {}).items():
    (path / f).write_text(textwrap.dedent(text))
  return path

class Test(unittest.TestCase):
  root:tk.Tk

  @classmethod
  def setUpClass(cls):
    cls.root = tk.Tk()
    cls.root.withdraw()

  @classmethod
  def tearDownClass(cls):
    cls.root.destroy()

  def setUp(self):
    self.folder = tempfile.TemporaryDirectory()
    self.addCleanup(self.folder.cleanup)
    self.bundled = Path(self.folder.name) / "bundled"
    self.installed = Path(self.folder.name) / "installed"
    self.bundled.mkdir()
    self.installed.mkdir()
    self.disabled:list[str] = []
    real = plugins.snPrefs.get
    patcher = mock.patch.object(plugins.snPrefs, "get", side_effect=lambda key, default=None, **kw:
                                self.disabled if key == plugins.DISABLED_PREF else real(key, default, **kw))
    patcher.start()
    self.addCleanup(patcher.stop)
    menubar = tk.Menu(self.root)
    for label in ("File", "Window", "Help"):
      menubar.add_cascade(label=label, menu=tk.Menu(menubar))
    self.app = SimpleNamespace(menubar=menubar)
    self.addCleanup(menubar.destroy)
    self.before = {m: sys.modules[m] for m in self.pluginModules()} # (eg: another test's bundled pythonParser: put back after)
    self.addCleanup(self.forget)

  def pluginModules(self) -> list[str]:
    return [m for m in sys.modules if m == plugins.NAMESPACE or m.startswith(plugins.NAMESPACE + ".")]

  def forget(self):
    for m in self.pluginModules():
      del sys.modules[m]
    sys.modules.update(self.before)
    for id in list(plugins.loaded):
      hooks.trust(plugins.loaded[id].manifest.module, False)
    plugins.loaded.clear()
    plugins.problems.clear()

  def labels(self, menu:tk.Menu) -> list[str]:
    last = menu.index(tk.END)
    return [menu.entrycget(i, "label") if menu.type(i) != "separator" else "-"
            for i in range(last + 1 if last is not None else 0)]

  def test0100version(self):
    self.assertEqual(plugins.version("1.2.10"), (1, 2, 10))
    self.assertLess(plugins.version("1.2"), plugins.version("1.10"))
    self.assertEqual(plugins.version("1.x"), (1, 0))

  def test0200manifest(self):
    m = plugins.Manifest.read(str(makePlugin(self.installed, "alpha", "2.1")))
    self.assertEqual((m.id, m.name, m.version, m.description, m.snVersion, m.module),
                     ("alpha", "alpha plugin", "2.1", "A test.", "1.0", "snplugins.alpha"))
    self.assertEqual(m.exclude, ())
    bad = self.installed / "has-dash"
    bad.mkdir()
    (bad / plugins.MANIFEST).write_text('name = "x"\n')
    broken = self.installed / "broken"
    broken.mkdir()
    (broken / plugins.MANIFEST).write_text('name = "x\n')
    (self.installed / "notAPlugin").mkdir()
    with self.assertLogs(plugins.logger.name, "WARNING") as logs:
      found = plugins.manifests(str(self.installed))
    self.assertEqual([m.id for m in found], ["alpha"])
    self.assertEqual(len(logs.records), 2)

  def test0300installBundled(self):
    makePlugin(self.bundled, "alpha", "1.0", files={"data.txt": "new"})
    (self.bundled / "alpha" / "__pycache__").mkdir()
    makePlugin(self.bundled, "beta", "2.0")
    self.assertEqual(plugins.installBundled(str(self.bundled), str(self.installed)), ["alpha", "beta"])
    self.assertTrue((self.installed / "alpha" / "data.txt").exists())
    self.assertFalse((self.installed / "alpha" / "__pycache__").exists())
    # the same versions: left alone (eg: the user's changes kept)
    (self.installed / "alpha" / "data.txt").write_text("mine")
    self.assertEqual(plugins.installBundled(str(self.bundled), str(self.installed)), [])
    self.assertEqual((self.installed / "alpha" / "data.txt").read_text(), "mine")
    # a newer one bundled: replaces it
    (self.bundled / "alpha" / plugins.MANIFEST).write_text('name = "alpha plugin"\nversion = "1.1"\n')
    self.assertEqual(plugins.installBundled(str(self.bundled), str(self.installed)), ["alpha"])
    self.assertEqual((self.installed / "alpha" / "data.txt").read_text(), "new")
    # an older one bundled: the installed one's kept
    (self.installed / "beta" / plugins.MANIFEST).write_text('name = "beta plugin"\nversion = "3.0"\n')
    self.assertEqual(plugins.installBundled(str(self.bundled), str(self.installed)), [])

  def test0320exclude(self):
    makePlugin(self.bundled, "alpha", files={"data.snm": "", "app.log": "", ".gitignore": "", "keep.txt": ""})
    (self.bundled / "alpha" / "examples").mkdir()
    for f in ("a.xml", "a_xml.snm", "a_xml.snv"):
      (self.bundled / "alpha" / "examples" / f).write_text("")
    with open(self.bundled / "alpha" / plugins.MANIFEST, "a") as f:
      f.write('exclude = ["examples/*.snm", "examples/*.snv"]\n')
    self.assertEqual(plugins.Manifest.read(str(self.bundled / "alpha")).exclude, ("examples/*.snm", "examples/*.snv"))
    plugins.installBundled(str(self.bundled), str(self.installed))
    installed = sorted(str(p.relative_to(self.installed / "alpha")) for p in (self.installed / "alpha").rglob("*"))
    self.assertEqual(installed, ["__init__.py", "data.snm", "examples", "examples/a.xml", "keep.txt", plugins.MANIFEST])

  def test0350relocate(self):
    makePlugin(self.bundled, "alpha", files={
      "onto.snm": '<property key="url" value="file:///somewhere/else/alpha/onto.snm" />\n'
                  '<ref value="file:///somewhere/else/alpha/sub/x.snm" /><ref value="file:///other/beta/y.snm" />\n',
      "onto.snv": '<property key="model" value="file:///Users/me/git/project/plugins/alpha/onto.snm" />\n',
      "notes.txt": "file:///somewhere/else/alpha/onto.snm"})
    plugins.installBundled(str(self.bundled), str(self.installed))
    here = (self.installed / "alpha").as_uri()
    self.assertEqual((self.installed / "alpha" / "onto.snm").read_text(),
                     f'<property key="url" value="{here}/onto.snm" />\n'
                     f'<ref value="{here}/sub/x.snm" /><ref value="file:///other/beta/y.snm" />\n')
    self.assertEqual((self.installed / "alpha" / "onto.snv").read_text(), f'<property key="model" value="{here}/onto.snm" />\n')
    self.assertEqual((self.installed / "alpha" / "notes.txt").read_text(), "file:///somewhere/else/alpha/onto.snm")

  def test0380importBundled(self):
    makePlugin(self.bundled, "alpha", files={"tools.py": "X = 42\n"})
    with mock.patch.object(plugins, "bundledFolder", return_value=str(self.bundled)):
      self.assertEqual(plugins.importBundled("alpha", "tools").X, 42)
      self.assertEqual(plugins.importBundled("alpha").__name__, "snplugins.alpha")
    self.assertNotIn("alpha", plugins.loaded)

  def test0400menus(self):
    m = plugins.Manifest.read(str(makePlugin(self.installed, "alpha")))
    ctx = plugins.PluginContext(self.app, m)
    calls = []
    ctx.addMenuItem("Do it", lambda: calls.append("tools"))
    ctx.addSeparator()
    ctx.addMenuItem("Tools/Again", lambda: calls.append("again"))
    ctx.addMenuItem("Alpha/Sub/Deep", lambda: calls.append("deep"))
    self.assertEqual(self.labels(self.app.menubar), ["File", "Tools", "Alpha", "Window", "Help"])
    tools = ctx.menu("Tools")
    self.assertEqual(self.labels(tools), ["Do it", "-", "Again"])
    sub = ctx.menu("Alpha/Sub")
    self.assertEqual(self.labels(ctx.menu("Alpha")), ["Sub"])
    tools.invoke(0)
    sub.invoke(0)
    self.assertEqual(calls, ["tools", "deep"])
    # a failing command: logged and shown, not raised
    ctx.addMenuItem("Fail", lambda: 1/0)
    with mock.patch("util.utils.showExceptionDialog") as shown, self.assertLogs(ctx.logger.name, "ERROR"):
      tools.invoke(3)
    shown.assert_called_once()
    # no Window menu: added at the end
    bare = SimpleNamespace(menubar=tk.Menu(self.root))
    self.addCleanup(bare.menubar.destroy)
    plugins.PluginContext(bare, m).addMenuItem("X", lambda: None)
    self.assertEqual(self.labels(bare.menubar), ["Tools"])

  def test0500prefs(self):
    ctx = plugins.PluginContext(self.app, plugins.Manifest.read(str(makePlugin(self.installed, "alpha"))))
    self.assertEqual(ctx.prefKey("depth"), "plugins/alpha/depth")
    with mock.patch.object(plugins, "snPrefs", {"plugins/alpha/depth": 3}):
      self.assertEqual(ctx.pref("depth"), 3)
      self.assertEqual(ctx.pref("other", "x"), "x")

  def test0600load(self):
    makePlugin(self.installed, "alpha", init='''
      from . import tools
      def register(ctx):
        ctx.addMenuItem("Alpha thing", lambda: None)
        ctx.app.registered = ctx.manifest.id
      ''', files={"tools.py": '''
      from sn.hooks import hook
      @hook
      def shout(obj, context):
        return str(obj).upper()
      '''})
    makePlugin(self.installed, "later", snVersion="99.0")
    makePlugin(self.installed, "noRegister", init="x = 1\n")
    makePlugin(self.installed, "badImport", init="raise ImportError('nope')\n")
    makePlugin(self.installed, "badRegister", init="def register(ctx):\n  raise RuntimeError('oops')\n")
    makePlugin(self.installed, "off")
    self.disabled[:] = ["off"]
    with self.assertLogs(plugins.logger.name, "INFO"):
      loaded = plugins.loadAll(self.app, str(self.installed))
    self.assertEqual(list(loaded), ["alpha"])
    self.assertEqual(set(plugins.problems), {"later", "noRegister", "badImport", "badRegister"})
    self.assertIn("99.0", plugins.problems["later"])
    self.assertEqual(self.app.registered, "alpha")
    self.assertEqual(self.labels(plugins.loaded["alpha"].context.menu("Tools")), ["Alpha thing"])
    # its hooks are trusted; a plugin that failed to register isn't
    self.assertTrue(hooks.trusted("snplugins.alpha.tools"))
    self.assertFalse(hooks.trusted("snplugins.badRegister"))
    self.assertFalse(hooks.trusted("snplugins.off"))
    self.assertEqual(hooks.call("snplugins.alpha.tools:shout", "hi", hooks.HookContext()), "HI")
    # loading again: nothing new
    self.assertEqual(list(plugins.loadAll(self.app, str(self.installed))), ["alpha"])

if __name__ == "__main__":
  unittest.main()
