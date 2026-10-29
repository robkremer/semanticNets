'''
A model's super-models given relatively (eg: "../../../../lib/far.snm") are
saved relatively, however far from the model they are, and so are its
references to their objects -- so a folder of models put on the web together
still finds them there. Those given absolutely stay so (unless they're near).

Created on Oct 29, 2026

@author: robkremer
'''
import unittest
import tempfile
import threading
import functools
import re
from pathlib import Path
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from sn.model.model import Model, Node
from sn.controller.modelInterface import ModelContext


class Test(unittest.TestCase):

  def setUp(self):
    self._tmp = tempfile.TemporaryDirectory()
    self.dir = Path(self._tmp.name).resolve() # (macOS: /var is /private/var)
    (self.dir / "site/a/b/c/web").mkdir(parents=True)
    (self.dir / "site/lib").mkdir()
    Model._initCache()
    far = Model(str(self.dir / "site/lib/far.snm"))
    Node(far, [far.NODE], name="farthing")
    far.save()
    near = Model(str(self.dir / "site/a/b/c/web/base.snm"))
    Node(near, [near.NODE], name="person")
    near.save()
    self.far, self.near = far, near
    self.mainPath = self.dir / "site/a/b/c/web/main.snm"

  def tearDown(self):
    Model._initCache()
    self._tmp.cleanup()

  def makeMain(self, farRef:str) -> Model:
    m = Model(str(self.mainPath))
    m.setSuperModels(["base.snm", farRef])
    Node(m, [self.near["person"]], individual=True, name="fred")
    Node(m, [self.far["farthing"]], individual=True, name="penny")
    m.save()
    return m

  def savedRefs(self) -> tuple[list[str], set[str]]:
    text = self.mainPath.read_text()
    supers = re.findall(r'<item value="([^"]*)"', re.findall(r'superDBs.*?</property>', text, re.S)[0])
    refs = set(re.findall(r'"([^"#]+)#\d+"', text))
    return supers, refs

  def test0100relative(self):
    m = self.makeMain("../../../../lib/far.snm")
    self.assertEqual(m.superModelPaths(), ["base.snm", "../../../../lib/far.snm"])
    supers, refs = self.savedRefs()
    self.assertEqual(supers[-2:], ["base.snm", "../../../../lib/far.snm"])
    self.assertEqual(refs, {"base.snm", "../../../../lib/far.snm"})

    Model._initCache() # (read again: still relative)
    m = Model.getDB(self.mainPath.as_uri())
    self.assertEqual(m.superModelPaths(), ["base.snm", "../../../../lib/far.snm"])
    self.assertEqual(m["penny"].getSupers()[0].db.url, self.far.url)
    m.setDirty()
    m.save()
    self.assertEqual(self.savedRefs()[1], {"base.snm", "../../../../lib/far.snm"})

  def test0200absolute(self):
    '''Given absolutely, a far one stays absolute (as it always has).'''
    m = self.makeMain(self.far.url)
    self.assertEqual(m.superModelPaths(), ["base.snm", self.far.url])
    supers, refs = self.savedRefs()
    self.assertEqual(supers[-1], self.far.url)
    self.assertEqual(refs, {"base.snm", self.far.url})
    m.setSuperModels(["base.snm", "../../../../lib/far.snm"]) # (now relatively)
    self.assertEqual(m.superModelPaths(), ["base.snm", "../../../../lib/far.snm"])
    m.setSuperModels(["base.snm", self.far.url]) # (and back)
    self.assertEqual(m.superModelPaths(), ["base.snm", self.far.url])

  def test0300onTheWeb(self):
    '''Put on the web together, the model finds its super-models there.'''
    self.makeMain("../../../../lib/far.snm")
    class Quiet(SimpleHTTPRequestHandler):
      def log_message(self, *args): pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(self.dir / "site")))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
      site = f"http://127.0.0.1:{server.server_address[1]}"
      Model._initCache()
      m = Model.getDB(f"{site}/a/b/c/web/main.snm")
      self.assertEqual([db.url for db in m.superDBs[-2:]], [f"{site}/a/b/c/web/base.snm", f"{site}/lib/far.snm"])
      self.assertEqual(m.superModelPaths(), ["base.snm", "../../../../lib/far.snm"])
      self.assertEqual(m["penny"].getSupers()[0].db.url, f"{site}/lib/far.snm")
    finally:
      server.shutdown()
      server.server_close()

  def test0400textCommand(self):
    '''"super_models add=..." takes a relative path as relative to the model's file.'''
    m = Model(str(self.mainPath))
    ModelContext(m).super_models(add="../../../../lib/far.snm")
    self.assertIn(self.far, m.superDBs)
    self.assertEqual(m.superModelPaths(), ["../../../../lib/far.snm"])

  def test0500replace(self):
    '''Replacing a super-model by one given relatively.'''
    m = self.makeMain(self.far.url)
    self.far.save(saveas=str(self.dir / "site/lib/far2.snm")) # (a copy)
    far2 = Model.getDB((self.dir / "site/lib/far2.snm").as_uri())
    m.replaceSuperModel(self.far, far2, relative=True)
    self.assertEqual(m.superModelPaths(), ["base.snm", "../../../../lib/far2.snm"])


if __name__ == "__main__":
  unittest.main()
