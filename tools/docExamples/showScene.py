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
  attributes   the attribute editor, on the definition's ?b (it has
               constraints): attribute-editor.png (the editor's window)
  animals      the taxonomy laid out with an isa current, and the animation
               toolbar: animation-class-diagram.png (the toolbar and the
               diagram)

With --capture, it takes the scene's screenshots itself (see *CAPTURES*),
into the given folder (eg: sphinx/source/images/user), and quits:

  python3.14 tools/docExamples/showScene.py overview --capture sphinx/source/images/user

That needs screen recording permission for whatever runs it (eg: the
terminal): without it, macOS gives a blank picture, and nothing is saved.
Otherwise, take them by hand (eg: with Shift-Cmd-4, then Space, to take a
window). The other screenshots (rule-window.png, definition-window.png,
collapsed-window.png, attribute-editor.png) are still taken by hand.

.. codeauthor:: Rob Kremer <robkremer@me.com>
'''
import os, sys, tempfile, subprocess

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCENES = ("overview", "query", "collapsed", "attributes", "animals")
TITLE_BAR = 28
"The height (points) of a macOS window's title bar, above the window's content."
CAPTURES:dict[str, list[tuple[str, str, float]]] = {
  "overview": [("family-reasoned.png", "window", 0.5)],
  "query":    [("query-answer.png", "left", 1.0)],
  "animals":  [("animation-class-diagram.png", "diagram", 1.0)],
}
"""
Each scene's screenshots, for --capture: (file name, what's in it, scale --
of the screen's pixels: 0.5 halves a Retina screen's). What's in it:
"window" is the whole window, title bar and all; "left" its left part, from
the canvas to the terminal pane (without the reasoning toolbar below); and
"diagram" the animation toolbar and the canvas below it.
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
    bar = win.view.__dict__["_animationToolbar"]
    c = win.view.canvas
    drawn = c.bbox("all")
    bottom = canvas.winfo_rooty() + canvas.winfo_height()
    if drawn:
      bottom = min(bottom, c.winfo_rooty() + int(drawn[3] - c.canvasy(0)) + 30)
    return x, bar.winfo_rooty(), w, bottom - bar.winfo_rooty()
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
  name = "animals.snv" if scene == "animals" else "family.snv"

  def vo(v, name:str, n:int=0):
    return sorted([o for o in v.values() if o is not None and o.modelObject is not None and o.modelObject.name == name],
                  key=lambda o: o.modelObject._id)[n]

  def setUp() -> None:
    win = app.openWindow(os.path.join(folder, name))
    v = win.view
    def roomForToolbar() -> None: # (the window grows by the reasoning toolbar's height: the canvas is as big as it was)
      bar = v.__dict__.get("_reasoningToolbar")
      if bar is None or not bar.winfo_ismapped(): # (not yet: the window's still being made)
        app.after(100, roomForToolbar)
        return
      win.update_idletasks()
      win.geometry(f"{win.winfo_width()}x{win.winfo_height() + bar.winfo_reqheight()}")
    app.after(100, roomForToolbar)
    if scene in ("overview", "query"): # (once the window's terminal is set up, so the report goes there)
      app.after(1000, v.reason)
    if scene == "query":
      app.after(1500, lambda: vo(v, "who likes dave?").answerQuery())
    elif scene == "collapsed":
      v.context.collapse(vo(v, "uncle rule"), True)
    elif scene == "attributes":
      app.after(500, lambda: vo(v, "?b", 1).onEditAttributes()) # (the definiens' ?b: its constraints, and its inherited look)
    if into is not None:
      def shoot() -> None:
        capture(win, scene, into)
        os._exit(0)
      app.after(CAPTURE_DELAY, shoot)
      return
    print(f"showing {scene}: close the window (or stop this) when done", flush=True)

  app.after(500, setUp)
  app.run()

if __name__ == "__main__":
  main()
