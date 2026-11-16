'''
Make the view of the KNet rules model that comes with the Rep Plus Net Reader
plugin -- plugins/rnetReader/knet.snv, beside knet.snm (see makeKnetRules.py)
-- laid out: its node types along the top, and its rules and constraint below,
in rows, each wide enough for its name.

  python3.14 tools/makeKnetView.py

Or put a view of it that's been laid out by hand there instead -- eg: one
saved in the installed plugin (File | Open super model, from a view of a net
the reader made, opens it: ~/.sn/plugins/rnetReader/knet.snv):

  python3.14 tools/makeKnetView.py --from ~/.sn/plugins/rnetReader/knet.snv

Either way it's stored as being in *PLACEHOLDER* (it's read from wherever the
plugin is installed). The view a user has changed in their installed plugin
is theirs: a new one that comes with the plugin doesn't replace it (see
*sn.plugins.USER_FILES*). A view refers to the model's objects by their
ids, which makeKnetRules.py gives them in the order it makes them: if it's
changed to make other objects, or in another order, make the view again (a
view laid out by hand may need fixing: test_rnetReader's TestKnetView checks
that what it shows is there).

Either way, it's locked (Edit | Lock view): laying it out moves things about,
but can't change knet.snm. In an unlocked view, dragging a relation from one
part of a rule to another (eg: its antecedent to its consequent) changes what
the part holds, in the model -- which isn't saved (it's the plugin's), so the
view, saved, would refer to objects that aren't there when it's read again.

It lays the view out in a temporary folder, as a temporary user (HOME), so it
never touches your files or preferences.

.. codeauthor:: Rob Kremer <robkremer@me.com>
'''
import os, re, sys, shutil, tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MODEL = os.path.join(ROOT, "plugins", "rnetReader", "knet.snm")
TARGET = os.path.join(ROOT, "plugins", "rnetReader", "knet.snv")
PLACEHOLDER = "file:///SEMANTIC_NETS_PLUGINS/rnetReader"
"Where the view is stored as being (the folder): it's wherever the plugin is installed (see makeKnetRules.PLACEHOLDER)."

COLUMNS = 4
"How many rules to a row."
GAP = 30
"The space between the rules, and around them."
WIDTH = 330
"How wide a rule is, at least (the widest's name fits)."

def setUp() -> str:
  '''
  Make the temporary folder, and make it this process's home -- before sn is
  imported, as that reads the preferences from there (and logs there).

  :returns: The folder.
  '''
  folder = os.path.realpath(tempfile.mkdtemp(prefix="snKnetView-")) # (resolved: on macOS, /var is /private/var)
  os.environ["HOME"] = folder
  os.environ["SN_NO_SAVE_PROMPT"] = "1"
  os.chdir(folder)
  sys.path[:0] = [os.path.join(ROOT, "src"), os.path.abspath(os.path.join(ROOT, "..", "pythonUtils", "src"))]
  return folder

def layOut(app, path:str, done) -> None:
  '''
  Open the model's view, show its objects (not the system's, nor the isa
  links of the rules' relations to their types), and lay them out: the node
  types along the top, and the rules and constraint below, in rows of
  *COLUMNS*: first those about the node types (the isa rule, about knode:
  under it), and then in the model's order (the order makeKnetRules.py made
  them in: the kernel's patterns, the marks', then the constraint). The relation types
  are left out: they all join the system's top node to itself, so they'd be
  drawn on top of each other, where it is (hidden).

  :param app: The editor.
  :param path: The model's file.
  :param done: Called when it's saved.
  '''
  from sn.model.model import Relation
  from sn.view.graphics.vrelations import VRelation
  win = app.openWindow(path)
  win.geometry("1450x950+20+20")
  v = win.view; ctx = v.context
  v.showAllModel()
  for cat in ("system objects", "higher-order isa relations"):
    ctx.visibility(cat, "hide")
  def shown() -> list:
    return sorted((vo for vo in v.values() if vo is not None and vo._isConnected() and vo.modelObject is not None),
                  key=lambda vo: vo.modelObject._id)
  def arrange() -> None:
    relTypes = [vo for vo in shown() if isinstance(vo, VRelation) and vo.modelObject.isType()]
    ctx.erase(relTypes[0], relTypes[1:])
    windows = [vo for vo in shown() if not isinstance(vo, VRelation) and vo.isContextWindow()]
    held = {id(mo) for w in windows for _, _, mo in w.paneContents()} # (what's in the rules: in the model)
    boxes = [w for w in windows if id(w.modelObject) not in held]
    def ends(w) -> set[int]: # (the nodes rule w's relations join: eg, its type variables, ^a, ^b, that it doesn't hold)
      return {id(e) for _, _, mo in w.paneContents() if isinstance(mo, Relation) for e in (mo.src, mo.dst) if e is not None}
    nodes = [vo for vo in shown() if not isinstance(vo, VRelation) and not vo.isContextWindow() and not vo.isHidden()
             and id(vo.modelObject) not in held]
    def inside(vo, w) -> bool:
      x1, y1, x2, y2 = w.boundingBox()
      bb = vo.boundingBox()
      return x1 <= bb[0] and bb[2] <= x2 and y1 <= bb[1] and bb[3] <= y2
    types = [vo for vo in nodes if vo.modelObject.isType() and not any(inside(vo, w) for w in boxes)] # (not eg: ^a, in a rule)
    def about(w, vo) -> bool: # (whether rule w is about node type vo: eg, the isa rule, about knode)
      return id(vo.modelObject) in ends(w)
    boxes.sort(key=lambda w: not any(about(w, vo) for vo in types)) # (those first: under the types, not across the others)
    y = GAP * 4
    for row in range(0, len(boxes), COLUMNS):
      height = 0
      for col, w in enumerate(boxes[row:row + COLUMNS]):
        bb = w.boundingBox()
        left = GAP + col * (WIDTH + GAP)
        w.moveTo(left, y, adjustPos=False)
        ctx.resize(w, left, y, left + max(WIDTH, bb[2] - bb[0]), y + bb[3] - bb[1], _followPanes=True)
        height = max(height, bb[3] - bb[1])
      y += height + GAP
    # the node types (eg: knode, and probe isa knode), along the top: above the first rule that's about them
    x = GAP
    for vo in types:
      rule = next((w for w in boxes if about(w, vo)), None)
      bb = vo.boundingBox()
      if rule is not None:
        x = max(x, int(rule.boundingBox()[0]) + GAP)
      vo.moveTo(x, GAP, adjustPos=False)
      x += bb[2] - bb[0] + 3 * GAP
    v.tidyWindows()
    v.zoomToFit()
    v.freshPaint(); v.repaint()
    app.after(800, save)
  def save() -> None:
    assert v.url.startswith("file://" + os.path.dirname(path)), v.url
    v.setEditLocked(True)
    v.save()
    done()
  app.after(800, arrange)

def install(folder:str) -> None:
  '''
  Copy the view into plugins/rnetReader/, stored as being in *PLACEHOLDER*
  -- and with the header's record of the program that wrote it neutralized --
  so nothing of this temporary folder is left in it.

  :param folder: Where it was made.
  '''
  from pathlib import Path
  with open(os.path.join(folder, "knet.snv"), encoding="utf-8") as fd:
    text = fd.read()
  text = text.replace(Path(folder).as_uri(), PLACEHOLDER).replace(os.path.abspath(sys.argv[0]), "Semantic Nets")
  assert folder not in text, f"knet.snv still mentions {folder}"
  with open(TARGET, "w", encoding="utf-8") as fd:
    fd.write(text)
  print("wrote", TARGET)

def installFrom(path:str) -> None:
  '''
  Copy a view of knet.snm that's been laid out by hand into plugins/rnetReader/,
  stored as being in *PLACEHOLDER* (as *sn.plugins* relocates it when it's
  installed: wherever it was saved, in a folder named rnetReader), and locked.
  Not if it shows objects that aren't in knet.snm (eg: laid out in an
  unlocked view, which changed the model, and the model wasn't saved).

  :param path: Its file.
  '''
  with open(os.path.expanduser(path), encoding="utf-8") as fd:
    text = fd.read()
  if not re.search(r'<property key="type" value="sn\.view\.graphics\.sngView\.SNGView" />', text):
    sys.exit(f"{path} isn't a view.")
  if not re.search(r'<property key="model" value="(knet\.snm|file://[^"]*/rnetReader/knet\.snm)" />', text):
    sys.exit(f"{path} isn't a view of the rnetReader plugin's knet.snm.")
  with open(MODEL, encoding="utf-8") as fd:
    ids = set(re.findall(r'<property key="(\d+)">', fd.read()))
  missing = sorted(set(re.findall(r'<property key="modelObject" type="str" value="#(\d+)" />', text)) - ids, key=int)
  if missing:
    sys.exit(f"{path} shows {len(missing)} objects that aren't in knet.snm (eg: #{missing[0]}): erase them from it first.")
  text = re.sub(r'file://[^"\'<>\s]*/rnetReader/', PLACEHOLDER + "/", text)
  text, n = re.subn(r'<property key="editLocked" type="str" value="[01]" />',
                    '<property key="editLocked" type="str" value="1" />', text)
  if n != 1:
    sys.exit(f"{path} doesn't say whether it's locked.")
  with open(TARGET, "w", encoding="utf-8") as fd:
    fd.write(text)
  print("wrote", TARGET)

def main() -> None:
  if "--from" in sys.argv[1:]:
    i = sys.argv.index("--from")
    if i + 1 >= len(sys.argv):
      sys.exit("usage: makeKnetView.py [--from <a view of knet.snm>]")
    installFrom(sys.argv[i + 1])
    return
  folder = setUp()
  import atexit, sn
  from pathlib import Path
  atexit.unregister(sn.savePrefsIfChanged) # (nothing of the temporary user to keep)
  atexit.unregister(sn.saveAtExit)
  model = os.path.join(folder, "knet.snm")
  with open(MODEL, encoding="utf-8") as fd: # (as being where it is, so it's not taken to have been moved)
    text = fd.read().replace(PLACEHOLDER, Path(folder).as_uri())
  with open(model, "w", encoding="utf-8") as fd:
    fd.write(text)
  from sn import hooks
  from sn.plugins import importBundled
  hooks.trust("snplugins.rnetReader") # (knode's hooks: as when the plugin's loaded)
  importBundled("rnetReader", "hooks")
  from sn.view.graphics.guiApp import Application
  app = Application()
  def finished() -> None:
    app.after(200, app.closeAllWindows)
    app.after(400, app.quit)
  layOut(app, model, finished)
  app.run()
  install(folder)
  shutil.rmtree(folder, ignore_errors=True)

if __name__ == "__main__":
  main()
