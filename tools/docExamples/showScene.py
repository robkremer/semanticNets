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

Screenshots have to be taken by hand (eg: with Shift-Cmd-4, then Space, to
take a window): macOS doesn't let a script capture the screen without screen
recording permission.

.. codeauthor:: Rob Kremer <robkremer@me.com>
'''
import os, sys, tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCENES = ("overview", "query", "collapsed", "attributes", "animals")

def main() -> None:
  scene = sys.argv[1] if len(sys.argv) > 1 else ""
  if scene not in SCENES:
    sys.exit(f"usage: showScene.py <scene>: one of {', '.join(SCENES)}")
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
    if scene in ("overview", "query"): # (once the window's terminal is set up, so the report goes there)
      app.after(1000, v.reason)
    if scene == "query":
      app.after(1500, lambda: vo(v, "who likes dave?").answerQuery())
    elif scene == "collapsed":
      v.context.collapse(vo(v, "uncle rule"), True)
    elif scene == "attributes":
      app.after(500, lambda: vo(v, "?b", 1).onEditAttributes()) # (the definiens' ?b: its constraints, and its inherited look)
    print(f"showing {scene}: close the window (or stop this) when done", flush=True)

  app.after(500, setUp)
  app.run()

if __name__ == "__main__":
  main()
