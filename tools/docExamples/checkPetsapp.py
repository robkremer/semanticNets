'''
Check that the Developer Guide's example program, petsapp (here), does what
the guide (sphinx/source/developer/extending.rst) says it does:

  python3.14 tools/docExamples/checkPetsapp.py

Like makeExamples.py, it runs as a temporary user (HOME), in a temporary
folder, so it never touches your files or preferences. It builds the model
and reasons over it without a window; then runs the program, and checks its
window (it's shown for a few seconds): the tree layout, the grid layout, the
tooltip and the menu item. It prints what it checked, and exits with 1 if
anything isn't as it should be.

.. codeauthor:: Rob Kremer <robkremer@me.com>
'''
import os, sys, tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CHECK_DELAY = 4000
"How long (ms) to let the program's window settle before it's checked."

failures:list[str] = []

def check(what:str, ok:bool, detail:object="") -> None:
  print(f"{'ok  ' if ok else 'FAIL'} {what}" + (f": {detail}" if detail != "" else ""), flush=True,
        file=sys.__stdout__) # (not sys.stdout: once a window's open, that's its terminal pane)
  if not ok:
    failures.append(what)

def setUp() -> str:
  '''
  :returns: A temporary folder, made this process's home (before sn is imported: it reads its preferences from there).
  '''
  folder = os.path.realpath(tempfile.mkdtemp(prefix="snPetsapp-")) # (resolved: on macOS, /var is /private/var)
  os.environ["HOME"] = folder
  os.environ["SN_NO_SAVE_PROMPT"] = "1"
  os.makedirs(os.path.join(folder, ".sn"))
  os.chdir(folder)
  sys.path[:0] = [os.path.dirname(os.path.abspath(__file__)), os.path.join(ROOT, "src"),
                  os.path.abspath(os.path.join(ROOT, "..", "pythonUtils", "src"))]
  return folder

def checkModel(folder:str) -> None:
  "The model, read back, and reasoned over -- no window."
  from sn.model.model import Model
  from sn.model.reasoner import reason
  from sn import hooks
  from petsapp.build import buildPets
  import petsapp.hooks # (registers its hooks: see the checks below)
  path = os.path.join(folder, "model", "pets.snm")
  os.makedirs(os.path.dirname(path))
  buildPets(path)
  m = Model.getDB("file://" + path)
  byName = {o.name: o for o in m.values() if o.name and not (o.isIndividual() and o.isa(m.RELATION))} # (not individual relations: they're named after their types)
  result = reason(m)
  inferred = [f"{s.name} -{r.name}-> {d.name}" for r, s, d in result.inferred]
  check("reasoning infers fido -has-ancestor-> rover", inferred == ["fido -has-ancestor-> rover"], inferred)
  ancestors = sorted(o.name for o in result.related(byName["fido"], byName["has-ancestor"]))
  check("fido's ancestors are rex and rover", ancestors == ["rex", "rover"], ancestors)
  check("the tooltip hook says rex's age", hooks.call("petsapp.hooks:ageTip", byName["rex"]) == "3 years old")
  check("the menu hook applies to rex, not to dog",
        hooks.applies("petsapp.hooks:sayHello", byName["rex"]) and not hooks.applies("petsapp.hooks:sayHello", byName["dog"]))

def checkProgram(folder:str) -> None:
  "The program, run: its window."
  import tkinter as tk
  from sn.view.graphics.guiApp import Application
  from sn.view.graphics.layout import LAYOUTS
  path = os.path.join(folder, "pets.snm")
  sys.argv = ["petsapp", path]
  import petsapp.__main__ as program
  run = Application.run
  def runAndCheck(app) -> None:
    def inspect() -> None:
      try:
        [win] = list(app.windows.values())
        v = win.view
        vo = {o.modelObject.name: o for o in v.values() if o.modelObject is not None and o.modelObject.name}
        y = {n: vo[n].boundingBox()[1] for n in ("animal", "dog", "rex")}
        check("the tree puts animal above dog above rex", y["animal"] < y["dog"] < y["rex"], y)
        check("the view's saved", os.path.exists(os.path.join(folder, "pets.snv")))
        check('"grid" is a layout', "grid" in LAYOUTS)
        LAYOUTS["grid"](v, columns=3).arrange(animate=False)
        at = {n: tuple(vo[n].boundingBox()[:2]) for n in ("animal", "cat", "dog", "fido")}
        check("the grid puts animal, cat, dog in a row, and fido below animal",
              at["animal"][1] == at["cat"][1] == at["dog"][1] and at["animal"][0] < at["cat"][0] < at["dog"][0]
              and at["fido"][0] == at["animal"][0] and at["fido"][1] > at["animal"][1], at)
        tip = vo["rex"].tooltipFunc()
        check("rex's tooltip", tip == "rex\n3 years old", repr(tip))
        for name, expected in (("rex", ["Say hello"]), ("dog", [])):
          menu = tk.Menu(v.canvas)
          vo[name].addHookMenuItems(menu)
          end = menu.index("end")
          labels = [menu.entrycget(i, "label") for i in range(end + 1) if menu.type(i) == "command"] if end is not None else []
          check(f"{name}'s menu items from hooks", labels == expected, labels)
      except Exception as ex:
        import traceback
        traceback.print_exc(file=sys.__stderr__)
        failures.append(f"checking the window: {ex}")
      sys.__stdout__.flush()
      os._exit(1 if failures else 0)
    app.after(CHECK_DELAY, inspect)
    run(app)
  Application.run = runAndCheck # type: ignore[method-assign]
  program.main()

def main() -> None:
  folder = setUp()
  import atexit, sn
  atexit.unregister(sn.savePrefsIfChanged)
  atexit.unregister(sn.saveAtExit)
  checkModel(folder)
  checkProgram(folder) # (exits when it's checked the window)

if __name__ == "__main__":
  main()
