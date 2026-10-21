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
The model directory's scanning (sn.model.directory): the search path, peeking
into files, and the entries made from them.

Created on Oct 12, 2026

@author: robkremer
'''
import os
import tempfile
import unittest
from sn.model.directory import Folder, parsePath, formatPath, covered, withFolder, filesIn, peekFile, \
  scanFile, Directory, modelURLOf, urlOf, urlProblem
from util.utils import pathURL

S = os.pathsep # (":" as in the shell's PATH; but ";" on Windows, where ":" is in "C:\\...")

def N(path:str) -> str:
  "A folder in the search path, as *parsePath()* makes it (on Windows: eg, \"/a/b\" is \"C:\\a\\b\")."
  return os.path.normpath(os.path.abspath(os.path.expanduser(path)))

def U(path:str) -> str:
  "A folder's URL, as *formatPath()* makes it."
  return pathURL(N(path), quoted=False)

XML2 = '''<?xml version='1.0' encoding='utf-8'?>
<object type="util.persistence.serialize.strdict">
  <property key="header">
    <object type="util.persistence.serialize.strdict">
      <property key="protocol" type="str" value="XML2" />
      <property key="url" type="str" value="{url}" />
    </object>
  </property>
  <property key="root">
    <object type="{type}" id="1">
      <property key="url" type="str" value="{url}" />
      {model}
      <property key="nextID" type="int" value="42" />
      <property key="_db">
        <object type="util.persistence.serialize.strdict">
          <property key="1"><object type="x.Y"><property key="model" type="str" value="not this one" /></object></property>
        </object>
      </property>
    </object>
  </property>
</object>
'''

XML = '''<?xml version='1.0' encoding='utf-8'?>
<object type="util.persistence.serialize.strdict">
  <property key="header">
    <object type="util.persistence.serialize.strdict">
      <property key="protocol"><object type="str" value="XML" /></property>
    </object>
  </property>
  <property key="root">
    <object type="sn.view.graphics.sngView.SNGView" id="1">
      <property key="url"><object type="str" value="file:///old/place/v.snv" /></property>
      <property key="model"><object type="str" value="m.snm" /></property>
      <property key="nextID"><object type="int" value="7" /></property>
      <property key="_db"><object type="util.persistence.serialize.strdict" /></property>
    </object>
  </property>
</object>
'''

def write(path:str, text:str) -> str:
  os.makedirs(os.path.dirname(path), exist_ok=True)
  with open(path, "w") as f:
    f.write(text)
  return path

def model(path:str) -> str:
  return write(path, XML2.format(url=pathURL(path, quoted=False), type="sn.model.model.Model", model=""))

def view(path:str, modelRef:str) -> str:
  return write(path, XML2.format(url=pathURL(path, quoted=False), type="sn.view.graphics.sngView.SNGView",
                                 model=f'<property key="model" type="str" value="{modelRef}" />'))


class Test(unittest.TestCase):

  def setUp(self):
    self.tmp = tempfile.TemporaryDirectory()
    self.dir = os.path.realpath(self.tmp.name)

  def tearDown(self):
    self.tmp.cleanup()

  def test0100parsePath(self):
    folders = parsePath(f"/a/b{S}/c/**\n ~/d \n\n/a/b")
    self.assertEqual(folders, [Folder(N("/a/b")), Folder(N("/c"), True), Folder(N("~/d"))])
    self.assertEqual(parsePath(formatPath(folders)), folders)
    self.assertEqual(parsePath(""), [])

  def test0150urlsInThePath(self):
    folders = parsePath("file:///a/My%20Models/**; https://example.org/onto/animals.snm\n/b")
    self.assertEqual(folders, [Folder(N("/a/My Models"), True), Folder("https://example.org/onto/animals.snm"), Folder(N("/b"))])
    self.assertTrue(folders[1].remote)
    self.assertEqual(str(folders[0]), U("/a/My Models") + "/**")
    self.assertEqual(parsePath(formatPath(folders)), folders)
    self.assertFalse(covered(folders, "/onto"))
    self.assertEqual(list(filesIn([folders[1]])), ["https://example.org/onto/animals.snm"])

  def test0200covered(self):
    folders = parsePath(f"/a/b{S}/c/**")
    self.assertTrue(covered(folders, "/a/b"))
    self.assertFalse(covered(folders, "/a/b/sub"))  # not with its subfolders
    self.assertTrue(covered(folders, "/c"))
    self.assertTrue(covered(folders, "/c/d/e"))
    self.assertFalse(covered(folders, "/cd"))       # not just a prefix of the name
    self.assertIsNone(withFolder(f"/a/b{S}/c/**", "/c/x"))
    self.assertEqual(withFolder("/a/b", "/e"), f"{U('/a/b')};{U('/e')}")

  def test0300filesIn(self):
    d = self.dir
    m = model(f"{d}/top/m.snm")
    v = view(f"{d}/top/sub/v.snv", "../m.snm")
    write(f"{d}/top/notes.txt", "x")
    model(f"{d}/top/.hidden/h.snm")
    m, v = N(m), N(v) # (the paths as found: on Windows, "\\"s)
    self.assertEqual(list(filesIn(parsePath(f"{d}/top"))), [m])
    self.assertEqual(list(filesIn(parsePath(f"{d}/top/**"))), [m, v])
    self.assertEqual(list(filesIn(parsePath(f"{d}/top/**{S}{d}/top/sub"))), [m, v])  # each once
    self.assertEqual(list(filesIn(parsePath(f"{d}/nowhere"))), [])

  def test0400peekXML2(self):
    v = view(f"{self.dir}/v.snv", "m.snm")
    peeked = peekFile(v)
    self.assertEqual(peeked["type"], "sn.view.graphics.sngView.SNGView")
    self.assertEqual(peeked["model"], "m.snm")  # (not the one further in)
    self.assertEqual(peeked["nextID"], "42")
    self.assertEqual(scanFile(v).objects, 41)  # (a view's first id is 1)
    self.assertEqual(peeked["url"], pathURL(v, quoted=False))

  def test0500peekXML(self):
    v = write(f"{self.dir}/v.snv", XML)
    self.assertEqual(peekFile(v), {"type": "sn.view.graphics.sngView.SNGView", "url": "file:///old/place/v.snv",
                                   "model": "m.snm", "nextID": "7"})

  def test0600peekOnlyTheStart(self):
    v = view(f"{self.dir}/v.snv", "m.snm")
    with open(v, "a") as f:  # (garbage after the start: never read)
      f.write("<<< not xml at all")
    self.assertEqual(peekFile(v)["model"], "m.snm")

  def test0700peekNotAModel(self):
    p = write(f"{self.dir}/x.snm", "not xml")
    with self.assertRaises(ValueError):
      peekFile(p)
    e = scanFile(p)
    self.assertIsNotNone(e.error)

  def test0800modelURL(self):
    d = self.dir
    model(f"{d}/m.snm")
    base = urlOf(f"{d}/v.snv")
    self.assertEqual(modelURLOf(base, "m.snm"), urlOf(f"{d}/m.snm"))
    self.assertEqual(modelURLOf(base, "sn:/sn.xml"), "sn:/sn.xml")
    # a view copied on its own: its model's where it was copied from
    model(f"{d}/orig/m2.snm")
    os.makedirs(f"{d}/copy")
    copied = urlOf(f"{d}/copy/v.snv")
    self.assertEqual(modelURLOf(copied, "m2.snm", urlOf(f"{d}/orig/v.snv")), urlOf(f"{d}/orig/m2.snm"))

  def test0900directory(self):
    d = self.dir
    model(f"{d}/lib/zoo.snm")
    model(f"{d}/lib/apes.snm")
    view(f"{d}/lib/zoo.snv", "zoo.snm")
    view(f"{d}/lib/zoo2.snv", "zoo.snm")
    model(f"{d}/elsewhere/other.snm")
    view(f"{d}/lib/other.snv", "../elsewhere/other.snm")
    view(f"{d}/lib/sys.snv", "sn:/sn.xml")
    directory = Directory()
    entries = list(directory.scan(parsePath(f"{d}/lib")))
    self.assertEqual(len(entries), 8)  # 6 in lib, and the models views refer to: other, and the system model
    models = directory.models()
    self.assertEqual([m.name for m in models], ["apes", "other", "sn.xml", "zoo"])
    byName = {m.name: m for m in models}
    self.assertEqual([v.name for v in byName["zoo"].views], ["zoo", "zoo2"])
    self.assertFalse(byName["other"].onPath)
    self.assertIsNone(byName["other"].error)
    self.assertEqual(byName["zoo"].objects, 0)  # (a model's first id is 256: its nextID's 42 here)
    self.assertEqual(byName["zoo"].location, U(f"{d}/lib") + "/")
    self.assertEqual([v.name for v in byName["sn.xml"].views], ["sys"])
    # a view gone: its entry goes; a model gone that a view refers to stays, missing
    os.remove(f"{d}/lib/zoo2.snv")
    directory.update(f"{d}/lib/zoo2.snv")
    os.remove(f"{d}/lib/zoo.snm")
    directory.update(f"{d}/lib/zoo.snm")
    byName = {m.name: m for m in directory.models()}
    self.assertEqual([v.name for v in byName["zoo"].views], ["zoo"])
    self.assertEqual(byName["zoo"].error, "missing")

  def test0920withHead(self):
    '''A file with a head (XML3): what's in it is read from there, and how many objects it has is exact.'''
    d = self.dir
    path = write(f"{d}/v.snv", '''<?xml version='1.0' encoding='utf-8'?>
<document>
  <head>
    <property key="format" value="XML3" />
    <property key="type" value="sn.view.graphics.sngView.SNGView" />
    <property key="url" value="file:///old/v.snv" />
    <property key="model" value="m.snm" />
    <property key="objects" type="int" value="12" />
  </head>
  <object type="sn.view.graphics.sngView.SNGView" id="1"><property key="nextID" type="int" value="999" />''') # (and no more: only the head's read)
    self.assertEqual(peekFile(path), {"type": "sn.view.graphics.sngView.SNGView", "url": "file:///old/v.snv",
                                      "model": "m.snm", "objects": "12"})
    entry = scanFile(path)
    self.assertEqual((entry.objects, entry.objectsExact, entry.kind), (12, True, "view"))

  def test0950urlProblem(self):
    d = self.dir
    m, v = model(f"{d}/m.snm"), view(f"{d}/v.snv", "m.snm")
    self.assertIsNone(urlProblem(urlOf(m), ("model",)))
    self.assertIn("view, not a model", urlProblem(urlOf(v), ("model",)) or "")
    self.assertIsNone(urlProblem(urlOf(v)))
    self.assertIn("nothing at", urlProblem(U(f"{d}/gone.snm")) or "")

  def test1000remote(self):
    import threading, functools
    from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
    d = self.dir
    class Quiet(SimpleHTTPRequestHandler):
      def log_message(self, *args): pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=f"{d}/web"))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
      base = f"http://127.0.0.1:{server.server_address[1]}"
      model(f"{d}/web/onto/animals.snm")
      view(f"{d}/local/zoo.snv", f"{base}/onto/animals.snm")  # a local view of a model on the web
      directory = Directory()
      list(directory.scan(parsePath(f"{d}/local;{base}/onto/animals.snm;{base}/onto/gone.snv")))
      byName = {m.name: m for m in directory.models()}
      animals = byName["animals"]
      self.assertTrue(animals.remote)
      self.assertTrue(animals.onPath)
      self.assertIsNone(animals.error)
      self.assertEqual(animals.objects, 0)
      self.assertEqual(animals.size, os.path.getsize(f"{d}/web/onto/animals.snm"))
      self.assertIsNotNone(animals.modified)
      self.assertEqual(animals.location, f"{base}/onto/")
      self.assertEqual([v.name for v in animals.views], ["zoo"])
      gone = [e for e in directory.entries.values() if e.url.endswith("gone.snv")][0]
      self.assertEqual(gone.error, "missing")
    finally:
      server.shutdown()
      server.server_close()


if __name__ == "__main__":
  unittest.main()
