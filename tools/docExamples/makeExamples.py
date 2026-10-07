'''
Make the example models that come with Semantic Nets -- src/sn/examples/
family.snm/.snv and animals.snm/.snv -- from scratch: the models, their views'
layouts, and their looks.

  python3.14 tools/docExamples/makeExamples.py [--keep]

It builds everything in a temporary folder, as a temporary user (HOME), so it
never touches your files or preferences; opens each model in the editor (off
screen) to lay out and save its view; and then copies the four files into
src/sn/examples/, stored as being in sn.EXAMPLES_PLACEHOLDER (see
sn.copyExamples(), which puts them where the user gets them).

The examples follow two conventions:

  - Relations are named "has-*" (eg: carol -has-parent-> alice: carol has
    alice as a parent), so they point the same way as isa does (a child to its
    parent, a subtype to its supertype); a verb (eg: "likes") reads the
    same way already.
  - How things look is set on their types (eg: person, mammal, bird), so their
    subtypes and instances inherit it: the colours and shapes show the
    inheritance.

The screenshots in the User Guide are taken from these examples: see
showScene.py.

.. codeauthor:: Rob Kremer <robkremer@me.com>
'''
import os, sys, shutil, tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
EXAMPLES = os.path.join(ROOT, "src", "sn", "examples")

def setUp() -> str:
  '''
  Make the temporary folder, and make it this process's home -- before sn is
  imported, as that reads the preferences from there (and logs there).

  :returns: The folder.
  :rtype: str
  '''
  folder = os.path.realpath(tempfile.mkdtemp(prefix="snExamples-")) # (resolved: on macOS, /var is /private/var)
  os.environ["HOME"] = folder
  os.environ["SN_NO_SAVE_PROMPT"] = "1"
  os.chdir(folder)
  sys.path[:0] = [os.path.join(ROOT, "src"), os.path.abspath(os.path.join(ROOT, "..", "pythonUtils", "src"))]
  return folder

# ---- the models -----------------------------------------------------------------

def makeFamily(folder:str) -> None:
  '''
  A small family, with a rule (uncle), a definition (brother), a query
  (who likes dave?) and a requirement (siblings have parents). The reasoner
  concludes that alice has-brother bob (from the definition: he's her
  sibling, and male), and so -- by the rule -- carol has-uncle bob; and,
  has-sibling being symmetric, that alice has-sibling bob. The requirement
  warns that alice and bob have siblings, but no parents (alice's sibling
  bob only by inference).

  :param folder: Where to save it (as family.snm).
  :type folder: str
  '''
  from sn.model.model import Model, Node, Relation
  m = Model(os.path.join(folder, "family.snm"))
  assert m.url.startswith("file://" + folder), m.url
  person = Node(m, [m.NODE], name="person")
  person["vis/shape"] = "RoundedRectangle"
  person["vis/fillColor"] = "LightSkyBlue1"
  def relType(name:str, color:str) -> Relation:
    r = Relation(m, [m.RELATION], person, person, name=name)
    r["vis/lineColor"] = color
    r["vis/lineFillColor"] = color
    r["vis/textColor"] = color
    r["vis/maxSize"] = 90 # (the system model's 40 is narrower than "has-brother": a line would run into the text)
    return r
  hasParent = relType("has-parent", "DarkOrange2")
  hasSibling = relType("has-sibling", "SeaGreen4")
  hasSibling["symmetric"] = True
  hasBrother = relType("has-brother", "RoyalBlue3")
  hasUncle = relType("has-uncle", "MediumPurple3")
  likes = relType("likes", "VioletRed3")
  p = {n: Node(m, [person], individual=True, name=n) for n in ("alice", "bob", "carol", "dave")}
  for n, g in (("alice", "female"), ("bob", "male"), ("carol", "female"), ("dave", "male")):
    p[n]["gender"] = g
  def rel(t:Relation, s, d) -> Relation:
    return Relation(m, [t], s, d, individual=True)
  rel(hasParent, p["carol"], p["alice"])
  rel(hasSibling, p["bob"], p["alice"])
  rel(likes, p["carol"], p["dave"])
  def var(name:str, **constraints) -> Node:
    v = Node(m, [person], individual=True, name=name)
    if constraints:
      v["constraints"] = ", ".join(f"{k}: {x}" for k, x in constraints.items())
    return v
  # the uncle rule: ?x has a parent ?y, who has a brother ?z => ?x has ?z as an uncle.
  # (The consequent has its own ?x and ?z: the same name is the same variable.)
  r = Node(m, [m.RULE], individual=True, name="uncle rule")
  X, Y, Z = var("?x"), var("?y"), var("?z")
  for x in (X, Y, Z, rel(hasParent, X, Y), rel(hasBrother, Y, Z)):
    rel(m.ANTECEDENT, r, x)
  X2, Z2 = var("?x"), var("?z")
  for x in (X2, Z2, rel(hasUncle, X2, Z2)):
    rel(m.CONSEQUENT, r, x)
  # the brother definition: ?a has-brother ?b means ?a has-sibling ?b, and ?b is male
  d = Node(m, [m.DEFINITION], individual=True, name="brother def")
  A, B = var("?a"), var("?b")
  for x in (A, B, rel(hasBrother, A, B)):
    rel(m.DEFINIENDUM, d, x)
  A2, B2 = var("?a"), var("?b", gender="male")
  for x in (A2, B2, rel(hasSibling, A2, B2)):
    rel(m.DEFINIENS, d, x)
  # the query
  q = Node(m, [m.QUERY], individual=True, name="who likes dave?")
  W = var("?who")
  rel(m.CONTAINS, q, W)
  rel(m.CONTAINS, q, rel(likes, W, p["dave"]))
  # the requirement: whoever has a sibling has some parent (?p: anyone) -- a warning
  req = Node(m, [m.REQUIREMENT], individual=True, name="siblings have parents")
  req["severity"] = "warning"
  req["report"] = "?s"
  req["message"] = "{0} has a sibling, but no parent"
  S, T = var("?s"), var("?t")
  for x in (S, T, rel(hasSibling, S, T)):
    rel(m.CONDITION, req, x)
  S2, P = var("?s"), var("?p")
  for x in (S2, P, rel(hasParent, S2, P)):
    rel(m.REQUIRED, req, x)
  m.save()

def makeAnimals(folder:str) -> None:
  '''
  A small taxonomy, for the animation layout's class diagram. Shapes are set
  on mammal and bird, colours on each species: the individuals inherit both.

  :param folder: Where to save it (as animals.snm).
  :type folder: str
  '''
  from sn.model.model import Model, Node
  m = Model(os.path.join(folder, "animals.snm"))
  assert m.url.startswith("file://" + folder), m.url
  def T(name:str, parent:Node|None=None, **look) -> Node:
    t = Node(m, [parent or m.NODE], name=name)
    for k, v in look.items():
      t["vis/" + k] = v
    return t
  animal = T("animal", shape="Hexagon", fillColor="grey90")
  mammal = T("mammal", animal, shape="RoundedRectangle", fillColor="burlywood1")
  bird = T("bird", animal, shape="Oval", fillColor="LightGoldenrod1")
  dog = T("dog", mammal, fillColor="tan1")
  cat = T("cat", mammal, fillColor="LightPink1")
  penguin = T("penguin", bird, fillColor="LightCyan2")
  robin = T("robin", bird, fillColor="IndianRed1")
  for name, typ in (("rex", dog), ("tom", cat), ("pingu", penguin), ("red", robin)):
    Node(m, [typ], individual=True, name=name)
  m.save()

# ---- the views ------------------------------------------------------------------

def layOutFamily(app, folder:str, done) -> None:
  '''
  Open the family model's view, arrange it -- the family on the left, the
  rule, definition and requirement in their windows on the right, and the
  query below the family -- and save it.

  :param app: The editor.
  :param folder: Where the model is.
  :type folder: str
  :param done: Called when it's saved.
  '''
  win = app.openWindow(os.path.join(folder, "family.snm"))
  win.geometry("1000x960+40+40")
  v = win.view; ctx = v.context
  v.showAllModel()
  for cat in ("system objects", "isa individuals", "types"):
    ctx.visibility(cat, "hide")
  def vo(name:str, n:int=0):
    return sorted([o for o in v.values() if o is not None and o.modelObject is not None and o.modelObject.name == name],
                  key=lambda o: o.modelObject._id)[n]
  def at(name:str, x:int, y:int, n:int=0) -> None:
    vo(name, n).moveTo(x, y, adjustPos=False)
  def box(name:str, x1:int, y1:int, x2:int, y2:int) -> None:
    ctx.resize(vo(name), x1, y1, x2, y2)
  def arrange() -> None:
    # the family
    at("alice", 160, 100); at("bob", 30, 230); at("carol", 160, 360); at("dave", 340, 585)
    # the windows (first: their contents are moved into them)
    box("uncle rule", 420, 30, 960, 260)
    box("brother def", 420, 300, 960, 520)
    box("who likes dave?", 40, 530, 300, 660)
    box("siblings have parents", 420, 560, 960, 760)
    # the rule: ?x -has-parent-> ?y -has-brother-> ?z  =>  ?x -has-uncle-> ?z
    at("?x", 450, 70); at("?y", 450, 190); at("?z", 600, 190)
    at("?x", 740, 70, 1); at("?z", 740, 190, 1)
    # the definition: ?a -has-brother-> ?b  <=>  ?a -has-sibling-> ?b {gender: male}
    at("?a", 450, 345); at("?b", 450, 460)
    at("?a", 740, 345, 1); at("?b", 740, 450, 1)
    at("?who", 70, 590)
    # the requirement: ?s -has-sibling-> ?t  requires  ?s -has-parent-> ?p
    at("?s", 450, 605); at("?t", 450, 715)
    at("?s", 740, 605, 1); at("?p", 740, 715)
    for r in [o for o in v.values() if o is not None and hasattr(o, "floating")]:
      try:
        r.floating(True)
      except Exception:
        pass
    v.freshPaint(); v.repaint()
    app.after(800, save)
  def save() -> None:
    assert v.url.startswith("file://" + folder) and v.model.url.startswith("file://" + folder), v.url
    v.save()
    done()
  app.after(800, arrange)

def layOutAnimals(app, folder:str, done) -> None:
  '''
  Open the animals model's view, lay it out as a class diagram with the
  animation layout (an isa current flowing down), and save it -- with the
  animation toolbar showing.

  :param app: The editor.
  :param folder: Where the model is.
  :type folder: str
  :param done: Called when it's saved.
  '''
  from sn.view.graphics.animatedLayouts import isEligible
  win = app.openWindow(os.path.join(folder, "animals.snm"))
  win.geometry("1000x560+60+60")
  v = win.view
  v.showAllModel()
  def start() -> None:
    v.context.visibility("system objects", "hide")
    v.showAnimationToolbar(True)
    v.setAnimationSetting("flowDirection", "down")
    v.toggleAnimationLayout()
    app.after(1000, wait)
  def wait() -> None:
    if v.animationLayout().active:
      app.after(500, wait)
      return
    for o in [o for o in v.values() if o is not None and isEligible(o)]: # (off the edges a little)
      bb = o.boundingBox()
      o.moveTo(bb[0] + 90, bb[1] + 40, adjustPos=False)
    v.freshPaint(); v.repaint()
    app.after(500, save)
  def save() -> None:
    assert v.url.startswith("file://" + folder), v.url
    v.save()
    done()
  app.after(800, start)

# ---- installing them --------------------------------------------------------------

def install(folder:str) -> None:
  '''
  Copy the examples into src/sn/examples/, stored as being in the placeholder
  folder -- and with the header's record of the program that wrote them
  neutralized -- so nothing of this temporary folder is left in them.

  :param folder: Where they were made.
  :type folder: str
  '''
  import sn
  for f in ("family.snm", "family.snv", "animals.snm", "animals.snv"):
    with open(os.path.join(folder, f), encoding="utf-8") as fd:
      text = fd.read()
    text = text.replace("file://" + folder, sn.EXAMPLES_PLACEHOLDER).replace(os.path.abspath(sys.argv[0]), "Semantic Nets")
    assert folder not in text, f"{f} still mentions {folder}"
    with open(os.path.join(EXAMPLES, f), "w", encoding="utf-8") as fd:
      fd.write(text)
    print("wrote", os.path.join(EXAMPLES, f))

def main() -> None:
  keep = "--keep" in sys.argv[1:]
  folder = setUp()
  import atexit, sn
  atexit.unregister(sn.savePrefsIfChanged) # (nothing of the temporary user to keep)
  atexit.unregister(sn.saveAtExit)
  makeFamily(folder)
  makeAnimals(folder)
  from sn.view.graphics.guiApp import Application
  app = Application()
  pending = {"family", "animals"}
  def finished(name:str) -> None:
    pending.discard(name)
    if not pending:
      app.after(200, app.closeAllWindows)
      app.after(400, app.quit)
  layOutFamily(app, folder, lambda: finished("family"))
  layOutAnimals(app, folder, lambda: finished("animals"))
  app.run()
  install(folder)
  if keep:
    print("kept", folder)
  else:
    shutil.rmtree(folder, ignore_errors=True)

if __name__ == "__main__":
  main()
