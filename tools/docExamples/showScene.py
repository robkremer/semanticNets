'''
Show one of the scenes the User Guide's screenshots are taken of (in
sphinx/source/images/user/), set up from the example models (see
makeExamples.py), and keep it on screen until the window is closed (or the
process is stopped):

  python3.14 tools/docExamples/showScene.py <scene>

Like makeExamples.py, it runs as a temporary user (HOME), on copies of the
examples, so it never touches your files or preferences. The scenes, and the
screenshots taken of them:

  overview     the family after reasoning: family-reasoned.png (the whole
               window); and rule-window.png, definition-window.png (the
               rule's and the definition's windows, close up)
  query        the query answered (carol highlighted): query-answer.png
               (the left part of the window, with the terminal pane)
  collapsed    the rule's window collapsed: collapsed-window.png (its title bar)
  requirement  the requirement's window, close up: requirement-window.png
  attributes   the attribute editor, on the definition's ?b (it has
               constraints): attribute-editor.png (the editor's window)
  animals      the taxonomy laid out with an isa current, and the layout
               panel's "animate" page: animation-class-diagram.png (the panel and the
               diagram)
  tree, balloon, radial
               the taxonomy arranged by that layout (by isa):
               layout-tree.png, layout-balloon.png, layout-radial.png (what's
               drawn)
  hubs         the XMLreader's books.xml arranged round hubs:
               layout-hubs.png (what's drawn)
  xmlreader    the XMLreader's books.xml, as it comes: xmlreader-books.png
               (what's drawn)
  pythonparser the pythonParser's model of the XMLreader's own code (no
               imports followed): pythonparser-xmlreader.png (what's drawn)
  familytree   the User Guide's worked example: a family tree by has-parent
               (a subtype of the transitive has-ancestor), kept arranged,
               after reasoning: tutorial-family-tree.png (what's drawn)

With --capture, it takes the scene's screenshots itself (see *CAPTURES*),
into the given folder (eg: sphinx/source/images/user), and quits:

  python3.14 tools/docExamples/showScene.py overview --capture sphinx/source/images/user

That needs screen recording permission for whatever runs it (eg: the
terminal): without it, macOS gives a blank picture, and nothing is saved.
Otherwise, take them by hand (eg: with Shift-Cmd-4, then Space, to take a
window). The other screenshots (rule-window.png, definition-window.png,
collapsed-window.png, attribute-editor.png) are still taken by hand.

The scene's output (eg: the reasoner's report) goes to its window's terminal
pane, even if the window isn't the frontmost one -- as when it's started
from the background.

.. codeauthor:: Rob Kremer <robkremer@me.com>
'''
import os, sys, tempfile, subprocess

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCENES = ("overview", "query", "collapsed", "attributes", "animals", "requirement",
          "tree", "balloon", "radial", "hubs", "xmlreader", "pythonparser", "familytree")
LAYOUT_SCENES = ("tree", "balloon", "radial", "hubs")
"The scenes that arrange a view with a static layout (see *arrange()*)."
TITLE_BAR = 28
"The height (points) of a macOS window's title bar, above the window's content."
CAPTURES:dict[str, list[tuple[str, str, float]]] = {
  "overview": [("family-reasoned.png", "window", 0.5)],
  "query":    [("query-answer.png", "left", 1.0)],
  "animals":  [("animation-class-diagram.png", "diagram", 1.0)],
  "requirement": [("requirement-window.png", "context:siblings have parents", 1.0)],
  "tree":     [("layout-tree.png", "drawing", 0.5)],
  "balloon":  [("layout-balloon.png", "drawing", 0.5)],
  "radial":   [("layout-radial.png", "drawing", 0.5)],
  "hubs":     [("layout-hubs.png", "drawing", 0.5)],
  "xmlreader": [("xmlreader-books.png", "drawing", 0.5)],
  "pythonparser": [("pythonparser-xmlreader.png", "drawing", 0.5)],
  "familytree": [("tutorial-family-tree.png", "drawing", 0.5)],
}
"""
Each scene's screenshots, for --capture: (file name, what's in it, scale --
of the screen's pixels: 0.5 halves a Retina screen's). What's in it:
"window" is the whole window, title bar and all; "left" its left part, from
the canvas to the terminal pane (without the reasoning toolbar below); and
"diagram" the canvas and the layout panel beside it; "drawing" what's
drawn on the canvas (as much as is in the window, and a little around it);
and "context:<name>" the context window of that name (and a few points
around it).
"""
CAPTURE_DELAY = 4000
"How long (ms) to let a scene settle (eg: reasoning, answering) before it's captured."

def region(win, what:str) -> tuple[int, int, int, int]:
  '''
  :param win: The scene's window.
  :param what: What's in the screenshot: see *CAPTURES*.
  :returns: Where it is on the screen (points): (x, y, width, height).
  '''
  x, y, w = win.winfo_rootx(), win.winfo_rooty(), win.winfo_width()
  paned = win.appPanedWidget
  canvas = paned.canvasFrame
  terminal = win.view.terminalFrame
  if what == "window":
    return x, y - TITLE_BAR, w, win.winfo_height() + TITLE_BAR
  if what == "left":
    bottom = terminal.winfo_rooty() + terminal.winfo_height()
    return x, canvas.winfo_rooty(), 372, bottom - canvas.winfo_rooty()
  if what == "diagram": # (down to a little below what's drawn)
    panel = win.view.__dict__["_layoutPanel"]
    c = win.view.canvas
    drawn = c.bbox("all")
    bottom = canvas.winfo_rooty() + canvas.winfo_height()
    if drawn: # (but all of the panel's page)
      bottom = min(bottom, max(c.winfo_rooty() + int(drawn[3] - c.canvasy(0)) + 30,
                               panel.page.winfo_rooty() + panel.page.winfo_reqheight() + 8))
    return x, canvas.winfo_rooty(), w, bottom - canvas.winfo_rooty()
  if what == "drawing":
    c = win.view.canvas
    drawn = c.bbox("all")
    pad = 12
    left, top = c.winfo_rootx(), c.winfo_rooty()
    x1 = max(left, left + int(drawn[0] - c.canvasx(0)) - pad)
    y1 = max(top, top + int(drawn[1] - c.canvasy(0)) - pad)
    x2 = min(left + c.winfo_width(), left + int(drawn[2] - c.canvasx(0)) + pad)
    y2 = min(top + c.winfo_height(), top + int(drawn[3] - c.canvasy(0)) + pad)
    return x1, y1, x2 - x1, y2 - y1
  if what.startswith("context:"):
    c = win.view.canvas
    [o] = [o for o in win.view.values() if o is not None and o.modelObject is not None and o.modelObject.name == what[len("context:"):]]
    x1, y1, x2, y2 = c.bbox(o.tag)
    pad = 4
    return (c.winfo_rootx() + int(x1 - c.canvasx(0)) - pad, c.winfo_rooty() + int(y1 - c.canvasy(0)) - pad,
            int(x2 - x1) + 2 * pad, int(y2 - y1) + 2 * pad)
  raise ValueError(what)

def capture(win, scene:str, folder:str) -> None:
  '''
  Take *scene*'s screenshots (see *CAPTURES*) of *win*, into *folder*.

  :param win: The scene's window.
  :param scene: Its name.
  :param folder: Where to put them.
  '''
  from PIL import Image
  win.lift(); win.update()
  for name, what, scale in CAPTURES.get(scene, []):
    x, y, w, h = region(win, what)
    path = os.path.join(folder, name)
    tmp = path + ".tmp.png"
    subprocess.run(["screencapture", "-x", "-t", "png", f"-R{x},{y},{w},{h}", tmp], check=True)
    im = Image.open(tmp).convert("RGB")
    if im.getextrema() == ((0, 0), (0, 0), (0, 0)): # (no screen recording permission)
      os.remove(tmp)
      sys.exit(f"{name}: the screen capture is blank -- screen recording permission is needed")
    if scale != 1.0:
      im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
    im.save(path)
    os.remove(tmp)
    print(f"captured {path} ({im.width}x{im.height})", flush=True)

def main() -> None:
  scene = sys.argv[1] if len(sys.argv) > 1 else ""
  if scene not in SCENES:
    sys.exit(f"usage: showScene.py <scene> [--capture <folder>]: <scene> is one of {', '.join(SCENES)}")
  into = os.path.abspath(sys.argv[sys.argv.index("--capture") + 1]) if "--capture" in sys.argv else None
  if into is not None and not CAPTURES.get(scene):
    sys.exit(f"{scene}: its screenshots are taken by hand")
  folder = os.path.realpath(tempfile.mkdtemp(prefix="snScene-")) # (a temporary user: see makeExamples.py)
  os.environ["HOME"] = folder
  os.environ["SN_NO_SAVE_PROMPT"] = "1"
  os.chdir(folder)
  sys.path[:0] = [os.path.join(ROOT, "src"), os.path.abspath(os.path.join(ROOT, "..", "pythonUtils", "src"))]
  import atexit, sn
  atexit.unregister(sn.savePrefsIfChanged)
  atexit.unregister(sn.saveAtExit)
  sn.copyExamples(folder)
  sn.snPrefs["loggingLevel"] = "WARNING" # (so the terminal pane shows the program's output, not its INFO log)
  from sn.view.graphics.guiApp import Application
  app = Application()
  name = "animals.snv" if scene in ("animals", "tree", "balloon", "radial") else "family.snv"

  def vo(v, name:str, n:int=0):
    return sorted([o for o in v.values() if o is not None and o.modelObject is not None and o.modelObject.name == name],
                  key=lambda o: o.modelObject._id)[n]

  def openWindow():
    """
    :returns: The scene's window: on the examples -- or, for the example
      apps' scenes, on what they make of their own examples (copied here).
    """
    if scene in ("hubs", "xmlreader"): # (the model as the XMLreader makes it; arranged below)
      import shutil
      from sn.plugins import importBundled
      xmlReader = importBundled("XMLreader", "view") # (where it is: not installed, nor in the menus)
      buildModel, outputPaths = xmlReader.buildModel, xmlReader.outputPaths
      xml = shutil.copy(os.path.join(ROOT, "plugins", "XMLreader", "examples", "books.xml"), folder)
      modelPath = outputPaths(xml)[0]
      model, ontology = buildModel(xml, modelPath)
      ontology.save()
      model.save()
      win = app.openWindow(modelPath)
      win.view.context.visibility("system objects", "hide")
      if scene == "hubs": # (its elements, without their types, to arrange round hubs below)
        xmlReader.showTypesAndExpand(win.view, model)
      return win
    if scene == "pythonparser": # (the XMLreader's code, its imports not followed)
      import shutil
      from sn import hooks
      from sn.plugins import importBundled
      dialog = importBundled("pythonParser", "dialog") # (where it is: not installed, nor in the menus)
      hooks.trust("snplugins.pythonParser") # (as the editor does, having loaded it: its hooks are named by its ontology)
      Options, convert = dialog.Options, dialog.convert
      code = os.path.join(folder, "XMLreader")
      shutil.copytree(os.path.join(ROOT, "plugins", "XMLreader"), code,
                      ignore=shutil.ignore_patterns("examples", "__pycache__", "*.log"))
      before = set(app.windows)
      convert(app, [code], Options(depth=0))
      [url] = set(app.windows) - before
      return app.windows[url]
    if scene == "familytree": # (as the worked example makes it: see sphinx/source/user/tutorial.rst)
      from sn.model.model import Model, Node, Relation
      m = Model(os.path.join(folder, "tree.snm"))
      assert m.url.startswith("file://" + folder), m.url
      person = Node(m, [m.NODE], name="person")
      hasAncestor = Relation(m, [m.RELATION], name="has-ancestor")
      hasAncestor["transitive"] = True
      hasParent = Relation(m, [hasAncestor], name="has-parent")
      p = {n: Node(m, [person], individual=True, name=n) for n in ("alice", "bob", "carol", "dave", "erin")}
      for child, parent in (("carol", "alice"), ("dave", "carol"), ("alice", "bob"), ("erin", "alice")):
        Relation(m, [hasParent], p[child], p[parent], individual=True)
      m.save()
      win = app.openWindow(os.path.join(folder, "tree.snm"))
      win.view.context.view.showAllModel()
      return win
    return app.openWindow(os.path.join(folder, name))

  def arrange(v) -> None:
    "Arrange *v* with the scene's layout, at once (see *LAYOUT_SCENES*)."
    from sn.view.graphics.treeLayout import TreeLayout
    from sn.view.graphics.balloonLayout import BalloonLayout, RadialLayout, HubLayout
    if scene == "tree":
      TreeLayout(v, relation="isa", direction="down").arrange(animate=False)
    elif scene == "balloon":
      BalloonLayout(v, relation="isa").arrange(animate=False)
    elif scene == "radial":
      RadialLayout(v, relation="isa").arrange(animate=False)
    elif scene == "hubs":
      HubLayout(v).arrange(animate=False)

  def setUp() -> None:
    win = openWindow()
    v = win.view
    if scene in (*LAYOUT_SCENES, "xmlreader", "pythonparser", "familytree"): # (room for all of it)
      win.geometry("1500x1000+40+40")
    elif scene == "animals": # (room for the diagram beside the layout panel)
      win.geometry("1400x600+40+40")
    def roomForToolbar() -> None: # (the window grows by the reasoning toolbar's height: the canvas is as big as it was)
      bar = v.__dict__.get("_reasoningToolbar")
      if bar is None or not bar.winfo_ismapped(): # (not yet: the window's still being made)
        app.after(100, roomForToolbar)
        return
      win.update_idletasks()
      win.geometry(f"{win.winfo_width()}x{win.winfo_height() + bar.winfo_reqheight()}")
    app.after(100, roomForToolbar)
    def toTerminal() -> None: # (output goes to the focused, or frontmost, window's terminal -- which this may not be, if it's started from the background)
      app.terminalRegistry.bindThreadToTerminal(v.terminal)
    if scene in ("overview", "query"): # (once the window's terminal is set up, so the report goes there)
      app.after(1000, lambda: (toTerminal(), v.reason()))
    if scene == "query":
      app.after(1500, lambda: vo(v, "who likes dave?").answerQuery())
    elif scene == "collapsed":
      v.context.collapse(vo(v, "uncle rule"), True)
    elif scene == "attributes":
      app.after(500, lambda: vo(v, "?b", 1).onEditAttributes()) # (the definiens' ?b: its constraints, and its inherited look)
    elif scene in LAYOUT_SCENES:
      app.after(1000, lambda: arrange(v))
    elif scene == "familytree": # (kept arranged as a tree, then reasoned over)
      from sn.view.graphics.treeLayout import TreeLayout
      def keep() -> None:
        v.context.visibility("system objects", "hide")
        v.context.visibility("isa individuals", "hide")
        v.doErase([vo(v, "has-ancestor"), vo(v, "has-parent")]) # (the relation types: not part of the family tree -- they'd be laid out as nodes, near person)
        v.setDynamicLayout(TreeLayout(v, relation="has-parent", parentEnd="destination", direction="down", spacing=60, others="rows"))
      app.after(1000, keep)
      app.after(2000, lambda: (toTerminal(), v.reason()))
      app.after(3500, v.zoomToFit) # (it's taller than the window)
    settled = [scene != "xmlreader"]
    if scene == "xmlreader": # (as the XMLreader does: the types, each with its elements round it)
      from sn.plugins import importBundled
      xmlReader = importBundled("XMLreader", "view")
      app.after(1000, lambda: (xmlReader.showTypesExpanded(v, v.model), xmlReader.separateNodes(v), settled.__setitem__(0, True)))
    if into is not None:
      def shoot() -> None:
        if not settled[0]:
          app.after(500, shoot)
          return
        if scene != "familytree": # (zoomed to fit: it's scrolled to suit)
          v.canvas.xview_moveto(0); v.canvas.yview_moveto(0)
        win.update()
        capture(win, scene, into)
        os._exit(0)
      app.after(CAPTURE_DELAY, shoot)
      return
    print(f"showing {scene}: close the window (or stop this) when done", flush=True)

  app.after(500, setUp)
  app.run()

if __name__ == "__main__":
  main()
