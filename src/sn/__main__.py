'''
Run *Semantic Nets*' graphical editor: ``python -m sn [file ...]``. This is
also the entry point of the packaged app, and of the .pyz.

``--selftest`` instead checks that the program's parts are all there and work,
without opening a window: it reasons over a copy of the bundled family example
with each reasoner engine (in the apps, every one they include; else, every
one installed) and checks the conclusions -- and asks one that can explain why
one holds -- and installs the bundled plugins (in a scratch folder), imports
all their modules, and makes a model with each (see *selftestPlugins()*), and
checks the About box has its icon and licences (see *selftestAbout()*) -- as
the "app" and "pyz" ant targets, and the Build workflow, do after a build.
It exits with 0 if all's well, and 1 if not.

.. codeauthor:: Rob Kremer <robkremer@me.com>
'''
import sys

def selftest() -> int:
  '''
  :returns: The exit status: 0 if the reasoner's conclusions about the family
    example are as expected, 1 if not.
  '''
  import atexit, shutil, tempfile
  from pathlib import Path
  import sn
  from sn.model.model import Model
  from sn.model.reasoner import reason, clearReasoning, ENGINES, engineInstalled
  from sn.controller.modelInterface import ModelContext
  atexit.unregister(sn.savePrefsIfChanged) # (a test mustn't touch the user's preferences or models)
  atexit.unregister(sn.saveAtExit)
  folder = tempfile.mkdtemp()
  try:
    sn.copyExamples(folder, ["family.snm", "family.snv"])
    model = Model.getDB(Path(folder, "family.snm").as_uri())
    expected = ["-has-brother->", "-has-uncle->", "Violations: 0 error(s)"] # (alice has-brother bob, so carol has-uncle bob)
    missing:list[str] = []
    for engine, info in ENGINES.items():
      if not engineInstalled(engine):
        if getattr(sys, "frozen", False) and info.bundled:
          missing.append(f"the {engine} reasoner engine (the app should include it)")
        else:
          print(f"(the {engine} reasoner engine isn't installed: not tested)")
        continue
      clearReasoning(model)
      try:
        report = reason(model, engine).report(model)
        print(f"--- {engine} ---\n{report}") # (ASCII: a Windows console may not take more)
        missing += [f"{e} (by {engine})" for e in expected if e not in report]
        if info.explains:
          why = ModelContext(model).parser.parseLine("explain has-uncle carol bob")
          print(why)
          if 'by the rule "uncle rule"' not in why:
            missing.append(f"why carol has-uncle bob (by {engine})")
      except Exception as ex:
        import traceback
        traceback.print_exc()
        missing.append(f"the {engine} reasoner engine ({ex})")
    missing += selftestPlugins(folder)
    missing += selftestAbout()
    import platform
    print("selftest:", ("FAILED: missing " + ", ".join(missing)) if missing else "ok", f"({platform.machine()})")
    return 1 if missing else 0
  finally:
    shutil.rmtree(folder, ignore_errors=True)

def selftestAbout() -> list[str]:
  '''
  Check the About box has what it shows (see *sn.view.graphics.aboutBox*):
  its icon and the licences that come with the program (package data); and,
  in the apps, every library they include (each credit with a Python
  distribution, but the engines they use from the computer), with its
  licence's text -- from its metadata, which the build must include (see
  packaging/semanticNets.spec).

  :returns: What's wrong: empty if nothing is.
  '''
  from sn.view.graphics import aboutBox
  from sn.model.reasoner import ENGINES
  from util.aboutDialog import installed, licenceTexts
  missing = [] if aboutBox.resource("icon.png") else ["the About box's icon"]
  missing += [f"the licence {name}" for name in ("semanticNets.txt", "python.txt", "tcl-tk.txt", "nemo.txt")
              if not aboutBox.licence(name)]
  if getattr(sys, "frozen", False):
    external = {e.package for e in ENGINES.values() if not e.bundled}
    for _heading, credits in aboutBox.credits():
      for c in credits:
        if c.dist and c.dist not in external:
          if not installed(c):
            missing.append(f"{c.dist}'s metadata (the app should include it)")
          elif not licenceTexts(c):
            missing.append(f"{c.dist}'s licence")
  return missing

def selftestPlugins(folder:str) -> list[str]:
  '''
  Install the bundled plugins in *folder* (see *sn.plugins.installBundled()*),
  import every module in them -- catching any standard library module the
  build left out -- and make a model with each: XMLreader of its books.xml,
  pythonParser of its own parser.py, rnetReader of a small net. (Not
  registered: there's no editor.)

  :param folder: A scratch folder.
  :returns: What's wrong: empty if nothing is.
  '''
  import importlib, os, traceback
  from sn import plugins
  target = os.path.join(folder, "plugins")
  try:
    plugins.installBundled(target=target)
    found = [m.id for m in plugins.manifests(target)]
    problems = [f"the {p} plugin" for p in ("XMLreader", "pythonParser", "rnetReader") if p not in found]
    plugins.namespace(target)
    for id in found:
      for dirpath, dirs, files in os.walk(os.path.join(target, id)):
        dirs[:] = [d for d in dirs if os.path.isfile(os.path.join(dirpath, d, "__init__.py"))] # (packages only: not examples/)
        rel = os.path.relpath(dirpath, target).replace(os.sep, ".")
        for f in sorted(files):
          if f.endswith(".py"):
            importlib.import_module(f"{plugins.NAMESPACE}.{rel}" + ("" if f == "__init__.py" else f".{f[:-3]}"))
    if "XMLreader" in found:
      reader = importlib.import_module(f"{plugins.NAMESPACE}.XMLreader.reader")
      xml, ontology = reader.buildModel(os.path.join(target, "XMLreader", "examples", "books.xml"), os.path.join(folder, "books_xml.snm"))
      print(f"XMLreader: {len(list(xml.values()))} objects, {len(list(ontology.values()))} in its ontology")
    if "pythonParser" in found:
      parser = importlib.import_module(f"{plugins.NAMESPACE}.pythonParser.parser")
      code = parser.buildModel(os.path.join(folder, "parser_py.snm"), parser.readModules([parser.__file__]))
      print(f"pythonParser: {len(list(code.values()))} objects")
    if "rnetReader" in found:
      rnet = importlib.import_module(f"{plugins.NAMESPACE}.rnetReader.rnet")
      reader = importlib.import_module(f"{plugins.NAMESPACE}.rnetReader.reader")
      net = rnet.parseText("\ufeff\tC\t9\r" "T\t1\r" "2\t0\tArial\t9\t1\t0\t000000\tFFFFFF\t000000\t008A00\t0\t0\t0\t\tConcept\r"
                           "A\t1\r" "1\t0\t0\t0\t1\t0\t000000\t000000\t000000\t000000\tIncludes\r"
                           "N\t2\t0\t-1\r" "0\t81\t10\t20\t19\t19\tA\t\r" "0\t0\t200\t20\t19\t19\tB\t\r" "L\t1\t0\r" "0\t1\t0\r")
      built = reader.buildModel(net, os.path.join(folder, "net.snm"))
      print(f"rnetReader: {len(built.nodes)} nodes, {len(built.relations)} relations")
    return problems
  except Exception:
    traceback.print_exc()
    return ["the plugins (see above)"]

if __name__ == "__main__":
  if "--selftest" in sys.argv[1:]:
    sys.exit(selftest())
  from sn.view.graphics.guiApp import main
  main()
