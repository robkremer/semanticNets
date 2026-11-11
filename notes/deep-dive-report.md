# semanticNets deep dive: logic and visualization

> **Read this first (Jerald/Rob).** This review ran against the tree as it stood on the night of Nov 2–3 (`sn-opt`: the eight PRs merged plus my seven commits), so where it names commits `a187b46`, `47e098b` or `c7a139e`, those are `3aafde2`, `cc3fef1` and `dd76e6e` on Rob's `main`, where Rob also reworked the memo invalidation. I re-ran the three findings that depend on that code against Rob's `main` (`45ba33c`): the **variable dragged out of its rule window is put back** reproduces there unchanged; the **`$type` label stale after a type's rename in another view** reproduces there, including after a repaint; the **Replace-super-model** one is milder there (labels are stale only until some later repaint). All three were my regressions; they are fixed, with tests, in robkremer/semanticNets#37 (one commit on Rob's `main`; full suite 479 run, only the root-only `test_canChange`), and Rob's own `test0695` still passes. Everything else below is as the reviewers and verifiers found it on the Nov 2–3 tree; line numbers may be off by a few on Rob's `main`. The verification scripts are under the scratchpad path given below, and each entry quotes what its script printed.


Paths are relative to the sn-opt repo root unless prefixed `pu:` (pythonUtils, /home/user/pu-opt). Reproduction scripts are under the scratchpad folder `/tmp/claude-0/-home-user/9364412b-b609-5b4f-a68a-4170282c7fc4/scratchpad/deepdive/`, abbreviated below as `deepdive/`.

## Summary

The code is in good shape at the core: the model, persistence, command system and reasoner all held up under probing, and the existing test suites (model, controller, copy/paste, relation marks, layouts, lineMarks, image export) all pass on the unchanged tree. Every one of the 71 bugs reported was reproduced by an independent verifier; none was refuted, and none is left unverified. The most important findings are the four that lose or corrupt work: an attribute type written with a space (`choices[yes, no]`, the editor's own recommended syntax) saves a model that can never be reopened; a failed open leaves an empty model in memory that the next open silently returns and Save then writes over the file; the attribute editor's Add/override change the live object outside the command system so Cancel and Undo don't take them back; and closing the last window never asks to save a modified model while the GUI is alive. Three regressions from last night's commits (a187b46, 47e098b, c7a139e) need attention first: the `$type` label memo goes stale when the type isn't in the view, and the containment-map cache is read before the model's notifications arrive, so a variable dragged out of a rule window is put straight back in. The visualization findings cluster around zoom (new shapes drawn at view coordinates, screen-pixel line widths beside zoomed marks, no repaint after zoom), relation marks with dangling ends, and layouts that pin labels the user then can't place. Last, the reasoner's report drops every attribute and type conclusion about existing objects because it judges "news" after materialize() has already added them. The fourteen adopted improvements are mostly small; the biggest wins are batching label placement at the end of an animation (16x) and the selection-box fix (6 s to 3 ms).

## Confirmed bugs

### High

**An attribute type containing a space saves mangled, and the model can never be opened again**
pu: src/util/attribute.py:605
`Attribute.getInstantiationInfo()` writes the type through `utils.getFullClassName()`, which does `str(cls).split()` and takes `splt[1][1:-2]`; for a type string with whitespace (`choices[yes, no]`, the syntax attributeEditor.py:1336 recommends and isValidType() accepts) it returns `''` or garbage (`choices[error, warning]` -> `arnin`). On reread Attribute.__init__ asserts, decodeClass() yields None, `isDirty()` fails on None, and every strategy fails with an opaque LookupError.
Repro: `deepdive/verify-pythonUtils-core-logic/probeA.py` Claim 0 -- `getFullClassName('choices[a, b]') -> ''`; saved file has `value=""`; `REOPEN FAILED: LookupError ... XML3: AttributeError: 'NoneType' object has no attribute 'isDirty'`; control `choices[yes,no]` reopens.
Fix: write the type with `typeAsString(slf.type)`; make `getFullClassName()` return a str argument unchanged (it's called with type strings from attribute.py:293/354/438/440 too); in the `attributes` setter (attribute.py:647) skip None entries with a logged warning so one bad attribute never makes a model unreadable. Round-trip test with `choices[yes, no]`.

**A failed read leaves a half-built model in PRDb.AllDBs; the next open returns an empty model and Save overwrites the file**
pu: src/util/persistence/pRef.py:841 (registration), :772-776 (`__new__`)
`PRDb.__init__` registers the DB in AllDBs before its objects are decoded; if decoding raises, `__new__` only discards `_readingURLs`. The next `getDB()`/`Model(url)` hits the `url in AllDBs` branch and returns the empty, not-dirty model without touching the file. guiApp.openWindow() calls `Model(viewSpec)` directly, so a second File > Open after the error dialog takes this path.
Repro: probeA.py Claim 1 -- attempt 1 `LookupError ... Could not find type "sn.model.model.Nodd"`; attempt 2 returned `Model(..., <0 items>)`; `save()` shrank the file 4735 -> 2058 bytes, `'animal' still in file: False`.
Fix: in `PRDb.__new__` wrap `cls._read(url)` so on any exception a DB this read created is removed (via `unload()` if it has one) before re-raising; same in `PRDb._read()`. Fix the `_readingURLs` docstring. Have `readx()` raise the first strategy's error as the cause so the dialog says "Could not find type ..." instead of five unrelated failures.

**Attribute editor changes the model object directly: Cancel and Undo don't take back a new attribute or an override**
pu: src/util/attributeEditor.py:919 (add), :2058 (override), :2028 (editKey)
All three write to the live GraphObject while the dialog is open. Only value changes come back in `updatedKeys`, so the creation is never a command: Cancel leaves the attribute, Save+Undo restores the placeholder instead of deleting it, and Add then Save without a value leaves `Attribute('', str)` with no undo entry at all. On a type, an override added by mistake stops type changes reaching every instance.
Repro: `deepdive/verify-input-editing-logic/verify_a.py` 0a-0d -- after Cancel `A.getLocalAttr("newA") = Attribute('', str, ...)`, `dirty: True`, `undo entries added: 0`; override then Cancel leaves `Attribute(black, None, None, None)`; add+Save+Undo leaves the key.
Fix: keep rows added by Add/override/editKey in a dialog-local pending dict (build the row from it, not from `self.attrs`); make `hasChanged()` and `save()` treat a pending key as changed (`save()` currently `continue`s when `getLocalAttr(k)` is None); return the record in `updatedKeys` so `set_attribute` creates it (oldAttrValue None -> undo deletes). The override case returns the value-only `Attribute(value, None, None, None)` that `_saveKey` already produces. Tests in pythonUtils (add+Cancel unchanged; add+Save returns key) and sn (Save then undo removes the key).

**Closing the last window never asks to save a modified model while the GUI is alive**
src/sn/view/graphics/guiApp.py:1047
`_closeWindow()` checks only the window's view (line 1027), then `quit()` destroys the root. The model is left to the atexit `sn.saveAtExit()`, which with no root falls to `askViaTk()`: a second Tk interpreter and a `simpledialog.askstring` "(Y/N)" box. With stdin not a tty (the packaged app) a dismissed or failed box returns None and the changes are dropped. `onQuit()` gets it right by calling `saveAtExit()` before `quit()`; File > Close model asks about its own model but not others still in memory.
Repro: `deepdive/verify-app-files-export-logic/b0_exit.py` -- `asked during close: []`, then `(simpledialog.askstring, 'Save modified model?', ... parent=<tkinter.Tk object .> new root? True)`; b0_exit_b.py with the box dismissed: `model saved? False | still dirty: True`.
Fix: in `Application.quit()` call `sn.saveAtExit()` (and `savePrefsIfChanged()`) before `self.destroy()`, as `onQuit()` does; the `_savedAtExit` guard makes the atexit call a no-op. Test that closing the last window with a dirty model calls `messagebox.askyesno`.

**An asserted relation can be connected to an inferred object; the saved file then has dangling references**
src/sn/model/model.py:2295 (`Relation.connect`), src/sn/controller/modelInterface.py:955-1003 (`_Assert_`)
`connect()`/`__init__` have no inferred check (`_refuseIfInferred()` guards only attribute changes on the inferred object itself), and `_Assert_` never calls `_refuseInferred()` unlike `_New_relation` and `_Reconnect`. `assert fred likes ghost` and `assert person ghost` (an asserted isa whose src is inferred) both make asserted links to an unsaved object; after save/reload both ends are "couldn't be found" and the relation is left unconnected.
Repro: `deepdive/verify-model-logic/v0_v2_v4.py` -- `assert ['fred','likes','ghost'] -> Relation inferred: False`; after save+reload `WARNING 3 references to objects couldn't be followed ... has no object #262`; `validate()` reports `Its dst couldn't be found` / `Its src couldn't be found`.
Fix: in `Relation.connect()`, when `not _inferringDepth and not self.inferred and not self.model.reading`, raise PermissionError for an end with `inferred=True` (so `__init__`, `_redirect` and `pasteInto` inherit it). In `_Assert_.__init__` add `_refuseInferred('relate', obj1, obj2)` for the 3-element form and `('make an instance of', typ)`/`('give a type to', obj1)` for the 2-element form. Test in test_controller: both forms raise; save/reload validates clean.

**Reasoner report and "show conclusions" drop a rule's attribute and isa conclusions once reason() has materialized them**
src/sn/model/reasoner.py:343, :347
`ruleConclusions()` tests `x.get(k) == v` and `x.isa(t)` against the model, but `reason()` calls `materialize()` first, which puts exactly those inferred attributes/isa links in. So the report lists only relations and new objects, the count is wrong, and a rule's "show conclusions" prints "0 conclusion(s)" while still highlighting the object. user/reasoning.rst:41-43 promises attribute values and types are listed.
Repro: `deepdive/reasoner/probe1.py` -- `run()` alone lists `bob {gender: male} (by "brothers are male men")`; `reason().report()` prints `Rule conclusions: 4` without it; `ruleConclusions(r1) -> []` while `bob.getLocalAttr('gender').inferred` is True.
Fix: judge news against asserted state: `a = x.getLocalAttr(k)`; known iff `a is not None and not a.inferred and a.value == v`, or `a is None and x.get(k) == v`. For isa, follow only non-inferred IsaIndividual links -- the test materialize() already uses at :1574 -- factored into an `assertedIsa(x, t)` helper used by both. Test that the line survives `reason()`; keep test_rules.py:370 (given value is not news).

**`assert <type> <rel-type> <type>`: undo doesn't restore unterminated ends, and redo raises**
src/sn/controller/modelInterface.py:1008, :1055-1057
Undo calls `rel.connect(oldSrc, oldDst)`, and `connect()` treats None as "leave alone", so a previously unterminated type keeps its new ends. Redo takes the `artifact is not None` branch and calls `_reconnect()` on a still-connected relation, tripping `assert not self._isConnected()`. Redo is broken for every use of this form, not just the unterminated one.
Repro: `deepdive/verify-controller-logic/verify.py` CLAIM 0 -- `after undo (expect None None): Node(person...) Node(animal...)`; `'redo' raised AssertionError`; undo queue still lists the assert, redo queue `[]`. Terminated case: undo ok, redo still raises.
Fix: in `undo`, when `oldSrcDst is not None` set `self.rel.src`/`.dst` through the setters (they accept None); in `do()` for that case call `self.rel.connect(obj1, obj2)` and return, never `_reconnect()`. Test assert/undo/redo/undo on both an unterminated and a terminated type.

**`set attribute --type bool` makes "false"/"no"/"0" True, and a plain re-set drops an attribute's recorded type**
src/sn/controller/modelInterface.py:681, :696
`typ(value)` is `bool("false") == True`, so a bool attribute set by command is stuck true (a rule's `disabled` can't be switched back on with `--type bool`; omitting `--type` works only when a bool record already exists). And `do()` decides "create new" only by whether a super attribute exists, so `set attribute person age 30 --type int` then `... age 31` replaces the local int record with `Attribute('31', str, UNRESTRICTED)` -- the tutorial's own path.
Repro: verify.py CLAIM 1a `after false: True Attribute(True, None, ...)` (same for no, 0); CLAIM 1b `after --type int: Attribute(30, int)`, `after plain re-set: Attribute(31, str)`; verify2.py: new attr `happy false --type bool` -> `Attribute(True, bool)`.
Fix: convert with `coerceValue(typ, value)` (util.attribute), letting its ValueError propagate. In `do()`, if `getLocalAttr(key)` exists and neither `--type` nor `--restriction` was given, do `self.object[key] = value` (coerces to the record's type, keeps restriction); build a fresh Attribute only when there is neither local nor super record or a type/restriction was given. Tests: bool false/no/0; int re-set keeps int; undo restores the record.

**Undoing "erase from view" reconnects an object without checking the view already shows it, or that it's still in the model**
src/sn/view/graphics/sngContext.py:399 (`_Erase.undo`), also `_Represent`/`_Expand` redo, `_Visibility.undo` :518
`update('del')` caches only connected view objects (sngView.py:574), so an object erased then removed from the model and restored by the model's undo gets a brand-new VNode from `update('new')`; the view's own undo then reconnects the old one too. If the object is removed elsewhere and not restored, undo reconnects a view object whose model object is gone, drawn as if fine, and saved as a dangling reference.
Repro: `deepdive/verify-view-core-logic/verify2.py` V1a (two windows) -- `view objects for x in A: 2 [2, 1]  faults: 3  canvas items for x: 4`; V1b -- ghost drawn, `validate: 0`, after save/re-read `"this model" has no object #256`.
Fix: one guard, e.g. `VObject._canReconnect(): mo is None or (mo._isConnected() and not view.viewObjectsFor(mo))`, used by `_Erase.undo()`, `_Represent`/`_Expand` redo and `_Visibility.undo()`; when the view already shows `mo`, drop the old object from the command (or adopt the shown one). Also have `update('del')` cache disconnected view objects held by live commands. Two-view test for both sequences.

**An object made while the view is zoomed has its box drawn at view coordinates**
src/sn/view/graphics/shapes.py:272; decorators.py:994 (`ShadowDecorator.draw`)
`Shape.draw()` creates the polygon from `points()` in view units with no `viewToWindow()`, while the redraw branch and every decorator use window coordinates. At any zoom but 1 a new node (normal path, paste, show, expand, inferred object) gets a stray box with its text, markers and isa line elsewhere; hit-testing and FindFree's overlap search use the misplaced box. `ShadowDecorator.draw()` deliberately mirrors the asymmetry.
Repro: `deepdive/verify-view-core-visualization/v0.py` -- `carol: scale=2.0 bbox(view)=[-12,65,24,87] shape x -12..24 y 65..87 expected window=[-24,130,48,174] text item at=[12,152] OK=False`; still wrong after 1 s idle; right only after `moveTo()`. Render v0-z2.png.
Fix: `create_polygon(self.vobject.view.viewToWindow(self.points(fast=fast)))` as `Oval.draw()` does on both branches; same in `ShadowDecorator.draw()`, deleting the "mirror the asymmetry" comment. Test: zoom 2, make a node, assert `canvas.coords(vo._shape.id) == viewToWindow(points)`; same for a new type's shadow.

**Line and border widths stay in screen pixels while marks, nodes and text zoom -- contrary to the docs** (also raised as an improvement by the view-core reviewer; merged here)
src/sn/view/graphics/connectors.py:436-438; shapes.py:247; vrelations.py:324
viewing.rst:267-269 (added in 70e182e) says sizes are in view units "like the line's width", but `_Style` passes the width straight through as `strokeWidth` (deriving view-unit `width` only for the marks), `zoom()` uses `canvas.scale()` which scales coordinates not widths, and node borders and stubs are likewise pixels. Zoomed out (Cmd-9 on a big network) arrowheads and rings shrink to specks on full-strength lines and selected lines bury the nodes; zoomed in, hairlines carry 15-px rings and 25-pt text.
Repro: `deepdive/verify-relations-marks-visualization/verify.py zoom` -- `r1 srcLine width=1.0` at zoom 1, 3 and 0.35; `dstT oval extent 5.0 -> 15.0 -> 1.75`; node border `1.0` at every zoom, font 10 -> 30 -> 3. PNGs zoom-3.png, zoom-0.35.png.
Fix: in `_Style.__init__` keep `self.width` as given (view units) and `self.strokeWidth = max(1.0, width * scale)`; same for the stub in `_styleEnds()` and `vis/borderWidth` in `Shape.updateKwargs()`. zoom() must then redraw lines and borders (see "Zooming never repaints" below, or a width pass in zoom()). Extend test0680 to assert `itemcget(line, 'width')` doubles at zoom 2. If pixel widths are preferred, rewrite viewing.rst instead -- but then the marks are out of proportion at every zoom but 1.

**A variable dragged out of its window is put straight back in (stale containment cache at bump time) -- regression from a187b46/c7a139e**
src/sn/view/graphics/viewContainment.py:225; viewCommands.py:82 (`_BumpIntruders.do`)
`_containmentMaps()` is memoized on `modelVersion()`, which is bumped only when the model's `notifyLater()` notifications reach the view (after_idle). `ViewDoList.do()` runs `_bump()` synchronously after the drag's composite command, so `homeStrays()` still sees the old containment, counts the variable a stray and gathers it back. The model is right, the picture wrong; in one run the model ended with the variable in R's consequent while the picture showed it inside C in R's antecedent. Non-variables are unaffected (only `strayVariables()` gathers). The 011f789 tree leaves the variable where dropped.
Repro: `deepdive/verify-containment-visibility-logic/v_drag.py` -- current tree `((20, 51), (20, 51))` with `INFO: put 1 variable back in its window.`; against 011f789 `((50, 411), (50, 411))`. `deepdive/containment/drag_stale.py`: at homeStrays time `modelVersion` 17, `C contains x in model? False`, yet `containmentHomes()` says `'?x': ('C', 'contains')`.
Fix: in `_BumpIntruders.do()` on its first (planning) run call `self.view.modelChanged()` before `homeStrays()`/`bumpIntruders()`, so the maps are rebuilt from the live model (the remove/new_relation commands have already run). Test on the release path: a contained variable dragged out stays where dropped and the model's containment is gone.

**Dropping a drag runs the 15-unit overlap avoidance per object: a dragged group comes apart, and a node can't be put beside a neighbour**
src/sn/view/graphics/vobjects.py:1214; layout.py:1010, :1120
Each released object is committed with `adjustPos=True`, so `FindFree.placeNode` re-places it; `freeRingSpot` tests even the spot it is on against every other box with the `expandFactor_nodes=15` margin, and the obstacles include the other members of the group just dragged. editing.rst:50 promises only a nudge "off anything it landed on".
Repro: `deepdive/verify-input-editing-visualization/bug0_drop.py` -- `gap 6: ... delta=(0, -40)`, `gap 12 ... (0, -40)`, `gap 14 ... (0, -40)`, `gap 16 ... (0, 0)`; group drag by (120,-60): `{N1: (120, -60), N2: (120, -100), N3: (120, -60)}`.
Fix: pass the moved set through `_Move` to `moveTo/adjustPos/placeNode` as extra excluded obstacles (an `exclude` kwarg, as `placeLabels` has `labels`); for a drop (`_drag` already exists on `_Move`) accept the starting spot when it does not actually intersect another box (ring 0 with gap 0, later rings with the margin), or skip adjustPos when the dropped box intersects nothing. Test: two nodes dropped 6 apart stay 6 apart; a selected pair keeps its relative positions.

**Selection-box release is O(canvas items x view objects): ~6-12 s freeze on a 2000-3000-object view** (found by both input-editing lenses; merged)
src/sn/view/graphics/viewInput.py:589-593
`for _id in ids: for n in self.values(): if n._shape.id == _id` over every overlapping canvas item (a relation is 4-5 items; handles add more) times every view object. Cmd-A on the same selection takes 0.9 s.
Repro: `deepdive/verify-input-editing-visualization/bug1_scale.py` -- 2116 objects / 9170 items: `selection-box release over all 5998.3 ms`, `selectAll 934.9 ms`, `nested loop alone: 17316 ids x 2116 objects -> 2076 matches in 8223.1 ms`, `dict lookup: 2076 matches in 2.0 ms`. `verify_scale.py` (2316 objects): 7.69 s real release.
Fix: build `byShape = {vo._shape.id: vo for vo in self.values() if vo is not None and vo._shape is not None and vo._shape.id is not None}` once, then `byShape.get(_id)`; skip ids that aren't shapes. The remaining ~1 s is the per-object `selected()` redraws (see improvements). `_relationTerminalNear()`'s per-motion dict rebuild is milliseconds; cache it only if motion feels laggy.

### Medium

**Relation.connect() moves a relation's ends without telling observers, so views go stale**
src/sn/model/model.py:2279-2314
`connect()` writes `_src/_dst` directly and calls `setDirty()`, never `_endpointChanged()` (:2052), so no `mod src`/`mod dst`/`mod inherited src/dst` topics; `VRelation.update()` (vrelations.py:739) follows exactly those. The terminal's `assert animal likes animal` (type signature) and its undo, and `Model._redirect()` (:1550), go through `connect()`.
Repro: `deepdive/verify-model-logic/v1_view_stale.py` -- after `assert animal likes animal`: model `animal->animal`, view VRelation `src=person dst=person`; same after undo; `reconnect likes source=animal` (setters) moves it at once.
Fix: remember oldSrc/oldDst and after each end that changed call `self._endpointChanged('src', old, new)`/`('dst', ...)`; drop the now-redundant retract loop in `IsaIndividual.connect()` (its `_endpointChanged` override does it). `AGRelation.__init__` also calls connect() during construction (no observers yet; harmless). Tests in test_model and a view test for the terminal assert.

**pasteInto loses a relation's end when that end is an isa link copied after it**
src/sn/model/copying.py:277-283
The second pass connects 'relation' entries and makes 'isa' entries in one pass in entry order; `closure()` (:170-173) appends isa links after the asked-for objects, so a relation whose src is an isa link runs `connect(None, ...)` (a no-op) and the copy's end reads as its type's domain. Purely order-dependent and silent.
Repro: v0_v2_v4.py -- entries `[node, relation(2), isa(0), isa(1)]`; `pasted since: localSrc = None  src (calculated) = top`; order `[isa, rel, a]` gives the right result.
Fix: split the pass: first make every 'isa' entry, then connect 'relation' entries (a loop until nothing is pending for the pathological isa-of-isa case). Add both orders to test_copyPaste.

**A kept new object keeps the types and attributes an earlier reason gave it, even when the rule now says otherwise**
src/sn/model/reasoner.py:1581-1601
`materialize()` computes `types` only in the `node is None` branch; ruleIsa entries whose subject is a NewObject are never in `want` (:1572 requires GraphObject), and nothing deletes an attribute the rule no longer concludes (the `_inferredAttributes` sweep at :1609 covers only the model's own objects). The docs promise the next reason "keeps those still inferred, adds the new ones, and removes the rest".
Repro: `deepdive/reasoner/probe2.py` E -- retype `?m` to woman, reason again: `same node kept: True parents after: [person] rule said: woman`, report line `exists: a woman`. verify.py claim 1: constraint removed, `gender = female` persists.
Fix: inside `with model.inferring(...)`, for each kept node compute wanted types from ruleIsa, disconnect inferred IsaIndividuals no longer wanted, add `IsaIndividual(model, node, t, inferred=True)` for new ones (fallback `model.NODE`), and `del node[k]` for attributes not in ruleAttrs for that key.

**An int written in a constraint never matches a float attribute (height: 2 vs 2.0), and vice versa**
src/sn/model/clingoReasoner.py:91-96, :208
`constraints._value()` parses `2` as int; `_term()` renders an int as a bare number but a float through `_str()`, so the attr fact `"2.0"` and constraint `2` never unify; `age: 30.0` against an int attribute fails too. `materialize()` coerces concluded values by type (reasoner.py:1614) but matching doesn't, and nothing warns.
Repro: verify.py claim 2 -- `'height: 2' -> []`; `'height: 2.0' -> [alice]`; `'age: 30' -> [alice]`; `'age: 30.0' -> []`.
Fix: canonicalise in `_term()`: a float with `.is_integer()` and abs < 2**30 renders as its int; keep non-integral floats as strings. Fixes both directions, needs no typed variable. Tests both ways; note in contexts.rst that 2 and 2.0 are the same value.

**A consequent variable's drawn types are concluded only if it's a new object; for a bound copy they're silently ignored**
src/sn/model/reasoner.py:725
`typed = own.values() if meaning else new.values()`: a consequent copy bound by the antecedent gets its constraints concluded (:729-737) but not its drawn parents, and only an isa link itself contained by the pane counts -- which the GUI's "new instance of man" in a pane never contains (viewEditing.py:76-82 contains only the node command). `ruleOf`'s docstring describes the narrowing, but reasoning.rst:111-113 and contexts.rst:236 say the opposite.
Repro: probe1.py -- `bob.gender = male` but `bob isa man? False`; verify.py claim 3 (pane-style creation): `isa links contained? False`, `ruleOf(r3).isas: [] problems: []`.
Fix: conclude drawn types of every consequent-own copy in rules too (`typed = own.values()`), update ruleOf's docstring, add a test; risk is low since a type the object already has is skipped by materialize and ruleConclusions. If the narrowing is kept, document it and add a `rule_type_ignored` warning in `_spec()`.

**A clingo keyword in a constraint's report ('not') makes the whole reason fail with an uncaught RuntimeError**
src/sn/model/clingoReasoner.py:91 (`_SYMBOL` :381); viewReasoning.py:113
A report word matching `_*[a-z]\w*` is emitted bare; `not` is the one such clingo keyword ('été', 'Not' are fine). `ctl.ground()` raises `RuntimeError('parsing failed')`; `ReasoningMixin.reason()` catches only ImportError, so the Reason button dies with a stderr traceback and the toolbar keeps the old summary; nothing in the UI names the constraint.
Repro: probe2.py D -- `<block>:1:28-31: error: syntax error, unexpected not` then `RuntimeError parsing failed`; verify.py claim 4: 'strange' OK, 'not' RuntimeError.
Fix: quote a Sym that is a reserved word (`str(x) if _SYMBOL.match(x) and x != 'not' else _str(str(x))`), and in `ReasoningMixin.reason()`/`ModelContext.reason` catch RuntimeError and log "The rules couldn't be compiled: ...". Test with a report containing 'not'.

**"format object tostring"/"torepr" then any result print -> NameError: 'context'**
src/sn/view/textUserInterface.py:83-93
The formatters close over a module global `context` bound only in the `__main__` block. In the GUI terminal every subsequent result line becomes a logged traceback (util/terminal.py:1164) until the user types `format object str`. Separately, `format model tostring` is rejected by the parser (`format_model`'s `format` param isn't positional-only, :191).
Repro: `deepdive/verify-controller-logic/verify.py` CLAIM 2 -- `tostring -> raised NameError name 'context' is not defined`; `format model tostring -> SyntaxError: unrecognized arguments: tostring`.
Fix: formatters take `(obj, model)`; `printLists` passes its (already received, ignored) `contextModel`; drop the global. Make `format_model(self, format=None, /)`. Test each listed format on a node and a model.

**`assert <type> <obj>` adds a duplicate isa link when obj already has that type, and makes a second object when the name is ambiguous**
src/sn/controller/modelInterface.py:989, :1015
When obj exists the command always creates a new IsaIndividual (help says "if need be"); and the bare `except:` at :989 swallows DuplicateNameError, so an ambiguous name takes the create path and a third object of that name is made, after which even `remove fred` is refused.
Repro: verify.py CLAIM 3a -- `after 2nd assert isa links: 2 ['person', 'person']`, `validate says: []`; 3b -- `freds before: 2 ... freds after: 3`, then `remove fred` raised `resolves to multiple objects`.
Fix: catch only NoSuchObjectError around the lookup; in `do()` for the 2-element form with obj1 found, if `typ in obj1.getParents()` leave artifact None and return obj1 (silent no-op, since re-running a script of asserts is normal) and make undo tolerate a None artifact. Tests: repeated assert adds nothing; ambiguous name raises and creates nothing. See also the adopted `parentProblem()` improvement below.

**An individual's overriding value is orphaned when its isa link is removed: `key in obj` and `getAttr()` raise ValueError**
pu: src/util/attribute.py:843-844, :933
`obj[key] = v` on an inherited key stores `Attribute(v, None, None)`; nothing completes it when the super goes away (isa deleted, retyped, super-model removed). `getAttr()` then raises "Inherited Attribute is not complete", `__contains__` propagates it, the attribute editor's loop (attributeEditor.py:740-750) logs "Failed to load on key" and omits the attribute, while `obj[key]` and labels still show the value; persists through save/reread.
Repro: probeA.py Claim 3 -- `fred['hair'] -> red`; `'hair' in fred RAISED: ValueError Attribute "hair": Inherited Attribute is not complete`; same after reread.
Fix: in `getAttr()`, when the local attribute is incomplete and no complete inherited one exists, return `Attribute(myAttr.value, myAttr.type or type(myAttr.value), myAttr.restriction or VAR_DEFAULTED, note)`; make `__contains__` never raise. Better still, when a super is removed (`IsaIndividual`/`notifySupersChanged`) complete the value-only locals below so the file is self-describing. Test delete-isa-then-`key in obj`.

**A $type label goes stale when its type isn't in the view -- regression from a187b46**
src/sn/view/graphics/vobjects.py:587
`labelText()` memoizes on `(view.modelVersion(), template)`; the version is bumped only by `VObject.update()` of an object shown in that view or the view's own new/del topics. A type's rename notifies the type's observers only, so a view showing just the instances keeps the old type name; Cmd-R can't fix it (repaint bumps only the draw version). test0690 passes only because the type is in the view.
Repro: `deepdive/verify-view-core-logic/verify.py` V0 (two windows) -- `after rename in A: A label: human:fred  B label: person:fred  B modelVersion: 1`; `after B.repaint(): B label: person:fred`; an unrelated change to fred fixes it.
Fix: include `tuple(p.name for p in mo.getParents())` in the memo key (always, or when the template reads `$type`/`${type`/`localName`); cheap beside `expand()`. Add a test0690 variant with the type erased from the view before the rename.

**An object changed while erased from the view comes back with a stale look**
src/sn/view/graphics/vobjects.py:864, :869, :2205
`update()` skips `cache.refresh()` for 'mod inherited attribute'/'mod supers' when not connected ("drawing it would put it back" -- moot, since `draw()` at :1704 already refuses a disconnected object), and `_reconnect()` just re-shows the old canvas items. Own changes are wrong until a repaint; inherited ones are wrong permanently (until "refresh all caches").
Repro: verify.py V2 -- `after undo: shown text: x  labelText(): renamed  cache fill: snow ... model fill: red`; `after repaint: shown text: renamed  cache fill: snow`.
Fix: drop the `_isConnected()` guards at :864/:869; in `_reconnect()` after `_showItems()` do `view.freshPaint(); self.draw()` (always: one object). Test: erase, change own and inherited attributes, undo, assert text and fill.

**Decorators are chosen once at construction: a node that becomes a rule is a big plain box, a rule that stops being one keeps its frame, set_kind leaves the shadow wrong**
src/sn/view/graphics/vobjects.py:1681
`makeDecorators()` decides frame-vs-text, the disabled slash and the type shadow once; `isContextWindow()` follows the model, so after an isa to rule the node is sized 320x200 and listed by `contextWindows()` but drawn as 'x' centred in an empty box; the reverse keeps the titled frame with no text decorator. Reopening the view rebuilds decorators (only the enlarged box persists), so medium.
Repro: `deepdive/view-core/exp2.py`, exp3.py -- `after isa->rule: isContextWindow: True  decorators: [markers, text]  bb: [20, 20, 340, 220]`; `y no longer a rule: ... decorators: [disabled, frame, markers]  shown text: <no text decorator>`; EXP11 set_kind: no shadow / keeps shadow. Pictures exp5_rule.png, exp5_unrule.png.
Fix: on 'mod supers'/'mod individual' in `VObject.update()` (and from `SNGView.update()` for a new/del isa whose src is shown) compare the decorator set `makeDecorators()` would choose with the current one; when it differs, erase the old frame/text/shadow/disabled decorators, make the new ones, `freshPaint()` and `draw()`; shrink the box back when an object stops being a window.

**Zooming never repaints: selection handles grow/shrink with the zoom, window titles keep the old font, glows change size**
src/sn/view/graphics/viewViewport.py:137-160
`zoom()` scales items and re-fonts 'text'-tagged ones; nothing redraws the screen-sized Selected handles (documented as the same size at any zoom, decorators.py:639), Highlight's pad or ContextFrame's labels (tagged 'context-frame'). No caller of zoom() repaints (`_drawVersion` unchanged across `zoomIn()`).
Repro: `deepdive/verify-view-core-visualization/v1234.py` -- `[zoomAbout(2.5), no repaint] handle=20px | title font='Arial 10 bold' banner h=45 | glow w=105`; `[after repaint()] handle=8px | title font='Arial 25 bold' | glow w=87`; `[zoomAbout(0.4)] handle=1px`.
Fix: end `zoom()` with `self.repaintSoon()` (coalesced at idle, so Option-drag costs one repaint); if too slow on a 2000-relation view, restrict to `freshPaint()` + `draw()` of selected, highlighted and context-window objects. Fix the marker font with it (below). Assert in test0680 that a selected node's handle is still 8px after zoom(2.0).

**Hide a category, zoom, show it again: the shown objects are outside the scroll region**
src/sn/view/graphics/viewViewport.py:156; viewVisibility.py:167
`zoom()` replaces `scrollRegion` with `bbox('all')` + margins, and Tk's bbox ignores hidden items; `applyVisibility()` only flips item states and never calls `resetScrollRegion()` (only `draw()` does). Same for a collapsed window expanded after a zoom.
Repro: v1234.py (2) -- `after zoomAbout(1.25): scrollRegion=(-790,-442,1165,1077)`; `types shown: person shape (1873,1498,1937,1538) ... inside=False`; scrolled to SE corner shows x up to 1165.
Fix: call `self.resetScrollRegion()` at the end of `applyVisibility()` and of `VObject.setCollapsed()` when expanding (only grows, no jump); in `zoom()` union the bbox-based region with the old region scaled by `scale/oldScale`. Test the hide/zoom/show sequence.

**Marker letters (E/S/T/R/{}) are drawn in 'fixed 9' at every zoom, and the E count never updates**
src/sn/view/graphics/decorators.py:458-459, :481
`font=('TkSmallCaptionFont', size)`: Tk takes the tuple's first element as a family, so the size is dropped and the family resolves to `fixed 9` while the circle scales (12 -> 30 -> 5 px); right after `zoom()` the 'text' loop re-fonts them to Arial so they look right until the next draw. `kwargs['text']` is set only inside `if self.id is None`, so the E badge keeps its first count.
Repro: v1234.py -- `T-marker font='TkSmallCaptionFont 25' actual=(fixed,9) circle d=30`; `(3) E: problems=2 text='2'`, `problems=3 text='2'`, `problems=1 text='2'`. Renders v1-z25-repaint.png, v1-z04-repaint.png.
Fix: use `(self.owner.view._fontFace, max(1, int(fontSize() * 0.8)))` on both lines; move the `kwargs['text']` assignment out of the creation branch (and redraw the owner when its status report changes); give markers their own tag so zoom() leaves them to draw(), or keep its loop consistent.

**A relation with no drawable ends never draws its middle marks, and keeps stale ones where its label used to be** (found by both relations-marks lenses; merged)
src/sn/view/graphics/connectors.py:687-689, :793-795; vrelations.py:293-327 (`_styleEnds`)
Both draw functions return `prior` untouched when source and destination are None, before `layoutMarks()`/`style.middle()`; `_styleEnds()` clears only the two sides and never looks at `vis/midMarks`. So a relation type with no ends of its own (the normal way a type is defined) never shows its middle marks with or without label text (`emptyLabelSize()` still reserves a 14x22 or 32x32 box for them), and a connected type with middle marks keeps those canvas items where they were after both end nodes are erased -- they don't follow the label.
Repro: `deepdive/verify-relations-marks-logic/probe.py` -- `F middleIDs: [] ... bb: [160, 400, 174, 422]`; `R moved to y=90; centre: (167, 101) middle coords now: [[162.4, 46.5, ...]]` (probe.png: orphaned `///`). `verify-relations-marks-visualization/verify.py noends`: F, G, H print no mid items; d5 (one end) shows `|||`. noends.png.
Fix: in the both-None branch build `style` and `middle` and return a copy of prior with `middleIDs = style.middle(middle, label.centerPt(), (1.0, 0.0), prior.middleIDs, through)` (the stubs' axis). With a text label hand the src stub's label end `_labelNearMarks(terms, self._middleLayout(), through)` (and `_labelFarMarks` for the dst stub), and cut the stubs back at `_middleStops()` (see the stub bug below). Tests: floating type with midMarks has middleIDs with and without label text; erasing both end nodes moves them with the label.

**Self-loops draw as a 3-unit sliver, with their middle marks turned across the line**
src/sn/view/graphics/connectors.py:746
`_selfLoopOffset()` separates the virtual centres by `(_SELF_LOOP_GAP + width)/2`, so the two arcs run side by side from the node's edge to the label 30 units away: a hairpin with both terminators overlapping on the edge. The marks' direction is `_sub(cd, cs)` (the offset vector, perpendicular to the hairpin), so `|||` draws as `≡` and `<|>` points up and down; the straight variant's `unit(ua+ub)` degenerates the same way. The 3-unit gap is a documented choice ("per Rob"), so the thin shape is partly by design.
Repro: verify.py loop -- mid lines `[72,125,82,125], [72,121,82,121], [72,117,82,117]` (horizontal, along the lines); loop2 `<|>` vertical. loop.png.
Fix (certain): when `source is destination`, turn the middle marks to the node->label axis `_sub(cl, source.centerPt())` computed before the offset -- the tangent-based alternative gives the same wrong answer since the curve really is a hairpin. Design question for Rob: whether a loop should bulge (offset centres by a fraction of the node's size, label off the node's corner) so the two terminators don't overlap.

**A label dragged onto (or placed over) its own end node draws a stray arc and marks through the node**
src/sn/view/graphics/connectors.py:332-334
`_clippedArc()` documents returning None when the shapes overlap, but the check is `if inside0(p2) or inside2(p0): pass`; `_findBoundaryParam()` then bisects between two inside points and the half-arc leaves the node on the far side with its terminators on it. Not routine for floating labels (`gapMidpoint()` keeps them in the gap); it needs a drop on the node, overlapping nodes or a stacking layout.
Repro: verify.py overlap -- label centre (50,36) inside alice [20,20,55,42]; `srcLine coords [19.9,31.1,-10.4,31.8,44.9,35.7]`; crow's foot at x 22-38. overlap.png.
Fix: `if inside0(p2) or inside2(p0): return None` (the None branch already deletes the stale half); the matching check in `_clippedHalf()` and `_drawSingleSegment()`. Optionally push a floating label out of its own ends in `placedLabel()` as it is pushed out of windows.

**Kept-arranged tree un-pins the label of every non-tree ("loose") relation after each command**
src/sn/view/graphics/treeLayout.py:1041-1043
`_adjustment()` floats every relation in `loose` (shaping but not a tree relation) that isn't floating; `adjust()` runs after every command, so a label the user just pinned by dropping snaps back to the midpoint, and after undo it is left pinned there. The class doc says such relations are "left floating".
Repro: `deepdive/verify-layouts-logic/ui.py` A (real press/motion/release) -- `after the drag: floats: True at [60, 405] wanted about (360, 597)`; `after undo: floats: False`.
Fix: have TreeLayout remember the ids of the labels it placed last time (the keys of `_labelTargets()` in the last `compute()`, kept like `known`, saved/undone with it) and float only `r in loose` whose id is in that set. Test: drag a loose label under a kept tree, assert it stays pinned; undo, assert it floats.

**Balloon/radial/hubs re-centre and pin the label of every non-tree relation, so those labels can't be placed and stop following their ends** (found by both layout lenses; merged)
src/sn/view/graphics/balloonLayout.py:790-796, :993-1024
`_RoundLayout._withLabels()` always merges `_otherLabels()` (the midpoint of every individual relation between arranged nodes), in the dynamic `compute()` too, and `LayoutMoves` pins what it moves. On activation all such labels are pinned; a dropped label is moved back by the adjust that follows; after switching back to "avoid overlaps" they stay pinned and no longer follow their ends (TreeLayout leaves the same labels floating; the midpoint target buys nothing since a floating label sits there anyway).
Repro: ui.py D -- `after balloon activation: likes floats: False at [63, 94]`; `after dragging it +250,+250: floats: False at [63, 94]`; `base1 dragged +300,+100: likes label at [113, 64]`. `verify-layouts-visualization/v_main.py`: after balloon/radial/hubs all non-tree labels `False`, after tree `True`; v_balloon_dragged.png.
Fix: have `_otherLabels()` return targets only for the side-by-side case (several relations between the same pair), leaving single ones floating as TreeLayout does, and skip any the user pinned; or add them to LayoutMoves without pinning (a `floats` flag per move). Keep pinning for the static arrange. Test: activate balloon, a non-tree label still floats; drop it elsewhere, it stays.

**Dragging a parent together with its children under a kept-arranged tree pins the children, dissolves the tree and moves the dropped parent away**
src/sn/view/graphics/treeLayout.py:1083
`pinnable()` pins every dropped node that isn't a root; with a subtree dragged as a multi-selection each child is pinned, `structure()` drops its parent relation, and the parent, left with no tree, becomes one of the "others" and (with rows/near) is re-placed elsewhere.
Repro: ui.py B/B2 -- `roots: [] children of base1: [] pins: {'derived'}`; with rows `base1` moved from the drop point (458,193) to (546,365).
Fix: in `pinnable()` take `parentRel` from `structure(dynamic=True)` before the new pins and don't pin a drop that has an ancestor among the drops; only the topmost dropped node of each subtree is pinned. Test with a parent and child dragged together.

**Undoing a dragged relation label leaves it pinned: it no longer follows its ends** (found by layouts and input-editing; merged)
src/sn/view/graphics/vrelations.py:774-776; sngContext.py:~121-130 (`_Move.__init__`)
`VRelation.onB1_ButtonRelease()` calls `floating(False)` before `super()` builds the `_Move`, which records `self.obj.floating()` -- already False -- so `undo()` restores the position and pins it. Present since the initial commit; `_Move` already has a `_wasFloating` parameter (added for layouts) that does what's needed.
Repro: ui.py U and `verify-input-editing-logic/verify_a.py` section 1 (real Tk events) -- `after Undo: floating False bb [193, 50, 227, 72]`; `after moving B down 150: label bb [193, 50, ...]`; menu's floating value False.
Fix: in `VObject.onButton_1()` record `dragStartFloating = {n: n.floating() for n in the dragged set if isinstance(n, VRelation)}`; in `VObject.onB1_ButtonRelease()` pass `_wasFloating=dragStartFloating.get(n)` for each moved object; drop the early `floating(False)` in VRelation (a `_Move` with `_wasFloating` pins in do() and re-floats in undo()). Also makes multi-selection drags consistent. Test in test_objectDrag.

**Static layouts leave the labels of relations they don't shape sitting on top of nodes**
src/sn/view/graphics/layout.py:450-455, :703-706
"arrange now" with tree/balloon/radial/hubs moves nodes and tree labels; every other label is re-centred with `reposition(adjustPos=False)` and nothing looks for a free spot, so labels land across the nodes they relate. The animation layout settles labels; the one-shot layouts never do.
Repro: `verify-layouts-visualization/v_main.py` -- `[tree down] 3 text labels; on a node: [('has-parent', True, ['rex','fido']), ('has-parent', True, ['tom','felix']), ('likes', True, ['felix'])]`; after `placeLabels` `on a node: []`. v_tree.png / v_tree_placed.png. e7 family: 14 of 54 labels on nodes.
Fix: compute label targets from the node targets inside the same LayoutMoves (a `_BoxIndex` of arranged nodes' target boxes plus tree labels; each remaining label at the midpoint of its ends' targets, `freeRingSpot` as `FindFree.placeLabels` does), so they glide and Cmd-Z puts them back. Quick version: `FindFree(view).placeLabels(labels)` after `cmd.do()` in `arrange()` (pass FindFree explicitly: `NoLayout.placeLabels` is a no-op).

**Labels that show no text are reserved room for and pinned: trees by isa are twice as tall, and a dragged leaf's isa line loops back to its old label spot**
src/sn/view/graphics/treeLayout.py:711-715, :741-748; layout.py:841-843
`levelGaps()` charges `h + MIN_LINE(100) + 2*LABEL_GAP` for any VRelation (only a Terminal gets MIN_LEVEL_GAP 60), though an isa label is a 4x4 square; `_labelTargets()` moves and `LayoutMoves` pins that square. Dragging the child afterwards leaves the invisible pinned label behind and the line is drawn through it. Not a regression of 9e26eeb (before it the line kinked at the same spot).
Repro: v_main.py -- `animal->bird: gap 128 (child h 22)`, `bird->penguin: gap 141 (child h 32)`, `isa label sizes [(4, 4)] shown text? {False}`; after dragging pingu `its line: x range 12 252 ... / x range -46 12` (v_tree_dragged.png).
Fix: treat a tree relation whose label shows no text (`_labelShown()` False, "as last drawn", so compute after a first draw) as a Terminal: MIN_LEVEL_GAP in `levelGaps()`, left out of `TreeLayout._labelTargets()`, `_RoundLayout._labelTargets()` and `_edgeRoom()`. Also make LayoutMoves (and `sngContext.move` with `_wasFloating`) never pin a label with no shown text.

**"animate | start" silently and permanently replaces the layout that keeps the view arranged**
src/sn/view/graphics/viewLayouts.py:297-300
`toggleAnimationLayout()` sets `localLayout = FindFree` with only a `logger.info`; it is deliberate (a tree layout would undo the animation) but not restored, not part of the run's undo entry, and not in animation.rst or layouts.rst. The judge's note on the related improvement (below) argues restoring it during the run would make the animation pointless; the two findings are reconciled there.
Repro: `verify-layouts-visualization/v_dyn.py` -- `after animate|start: kept layout: avoid overlaps`; `after stop: ... avoid overlaps`; `after Cmd-Z: ... avoid overlaps`.
Fix: see the improvement "Starting the animation silently replaces the kept layout" -- keep the switch, document it, and make it an also-entry of the run's command so Cmd-Z restores the old layout object (pins intact) and the menu variable. If holding the layout off for the run is preferred instead: set `localLayout = None` (ViewDoList honours it) and restore in `_finish()`/`kill()`, settling labels with an explicit `FindFree(view).placeLabels(...)`.

**Collapsing a window that holds a nested window hides the inner window but not its contents** (found by both containment lenses; merged)
src/sn/view/graphics/viewVisibility.py:140-143, :151
`shouldHide()` tests "inside a hidden window" only under `if self.hides:` ("windows are only hidden by a category" -- no longer true once collapsing exists), and `_inCollapsedWindow()` tests only the collapsed window's direct `containmentOf()`. With rule R containing context C containing z: collapse R, C is hidden, z and its relations stay drawn under R's bare banner, draggable and editable. With no hidden categories (a fresh view's default, sngView.py:221) the same happens for a plain nested window.
Repro: `verify-containment-visibility-logic/v_collapse.py` -- `{'R': 'SHOWN', 'C': 'hidden', 'z': 'SHOWN', 'z2': 'SHOWN', 'zz': 'SHOWN'}`, collapsed.png; `verify-containment-visibility-visualization/verify.py b3NoHides` -- `'b' hidden=False`, with family hides `'b' hidden=True`.
Fix: drop the `if self.hides:` guard (the loop is over windows only; `_inCollapsedWindow()` already loops them for every object) and fix the comment; `_applyHidden()` already re-applies to `windowContents()` so nesting propagates. Test: outer{a, inner{b}}, no hides, collapse outer -> b hidden; expand -> shown.

**Erasing a category of windows (e.g. 'rules') strands the contents of windows nested in them**
src/sn/view/graphics/sngContext.py:498
`_Visibility.do()` iterates a list comprehension evaluated once from the original victims, so a nested window appended inside the loop never has its own `windowContents()` added.
Repro: v_erase.py -- `rules erased: {'R': False, 'C': False, 'z': True, 'z2': True, 'zz': True}`; erased.png; undo restores all.
Fix: a worklist: `queue = [windows among victims]; while queue: w = queue.pop(); for c in w.windowContents(): if c not in victims: victims.append(c); if window: queue.append(c)`; keep the nodes-first sort. Test with a nested window.

**Collapsing a window doesn't hide the variables its contents use but it doesn't contain (every shipped base rule)**
src/sn/view/graphics/viewVisibility.py:151, :161
`containmentHomes()`, `strayVariables()`, `carriedContents()` and `gatherIntoWindow()` all treat the variables a contained relation uses as the window's content, but `_inCollapsedWindow()` and `shouldHide()`'s hidden-window branch test only `containmentOf()`. In baseRules.snm every rule uses all its variables without containing them (symmetric: `!a ?b ^r`, transitive: `!a !b !c ^r`), so collapsing any base rule leaves every variable drawn in the empty space.
Repro: v_collapse.py -- `'?a': 'hidden', '?b': 'hidden', '^r': 'SHOWN'`; v_baseCollapse.py -- `transitive collapsed; of what belongs in it, still drawn: ['!a', '!b', '!c', '^r']`.
Fix: `_containmentMaps()` (cached) already returns the `uses` map `{id(variable): {window: panes}}`; in both tests treat vo as the window's content if `w.containmentOf(mo) or (id(mo) in uses and w in uses[id(mo)])`, still requiring `w.paneAt(vo.centerPt())`. Test collapsing sn:/baseRules 'transitive'.

**Dragging a variable out of a rule silently removes its containment but snaps it back; afterwards it's treated inconsistently when collapsed or filtered**
src/sn/view/graphics/viewContainment.py:624 (`_updateContainment` "out" branch), :746-768 (`homeStrays`)
For a variable used by a contained relation two documented rules fire at once: the containment is removed, then the same command's `homeStrays()` moves the variable back. The user sees the drag refused; the model has lost the containment (saved file, undo entry). The variable is now only "used": collapsing leaves it drawn under the banner, hiding "nodes: person" hides it and its relation while the contained ?y/?z stay. The reasoner's `patternOf()` is unaffected. Related to, but distinct from, the stale-cache regression above (which bites even variables the window doesn't use via a relation).
Repro: `verify-containment-visibility-visualization/verify.py b2drag` -- `after: rule contains ?x: [] ?x bb: [110, 90, 130, 112]` (window x1=100); b2collapse -- `windowContents: ['?y','has-parent','?z','likes'] carried: ['?x', ...]`, `'?x' hidden=False`; b2hide -- ?x and has-parent hidden, ?y ?z likes shown.
Fix: in the "out" branch keep the containment of a variable the window's contained relations still use and log why ("?x is used by the rule's antecedent: drag the relation out too"); make `_inCollapsedWindow()`, `_inShownContext()` and the hidden-window loop decide by `containmentHomes()`/the `uses` map (previous bug) rather than `containmentOf()`.

**With "types" hidden, a rule's isa conclusion vanishes from its consequent**
src/sn/view/graphics/viewVisibility.py:133, :138
A contained relation is exempt from its own hidden category (`_inShownContext`) but :138 still hides it when an end is hidden; an isa in a consequent points at a type outside the window, so hiding "types" blanks the consequent. Same for a pattern relation to a constant with its node type hidden. The shipped family.snv is not affected (its rules relate variables to variables), but any user rule concluding a type is, under the hides that view sets.
Repro: verify.py b0 -- `'person' hidden=True`, `'isa' hidden=True`, `isa _inShownContext: True shouldHide(isa): True`; b0.png shows an empty consequent. b0const: `'mary' hidden=True`, `'likes' hidden=True`.
Fix: when `_inShownContext(vo)` holds for a relation, don't apply the hidden-end rule; have `_applyHidden()`/`applyVisibility()` mark the far end `categoryExempt` (as `_expand()` does) and report it once. Document the exception in viewing.rst beside "Relations to or from hidden objects are hidden too". Test: `?x isa person` in a consequent, types hidden -> both drawn.

**A relation between something in a window and something in a window nested inside it is pushed right out of the outer window**
src/sn/view/graphics/viewContainment.py:299 (`between()`)
A home is given only if both ends have the same home window; with a in outer and b in inner the relation has none, `belongsIn(label, outer)` fails and `bumpIntruders()` pushes the floating label above outer's banner, with the line looping out and back. `belongsIn()`/`windowChain()` already count b as held by outer.
Repro: verify.py b1 -- homes lack likes; `label after bump: [243, 22, 277, 44]` with outer at [50, 50, 650, 450]; after dragging a, still outside. b1.png.
Fix: in `between()` build each end's window chain from the memoised `home()`, take the innermost common window, and the pane via `sharedPane()` of the pane each end (or the nested window carrying it) sits in. Test: outer{a, inner{b}}, a->b floating -> home (outer, 'contains'), label stays inside.

**"make relation to... isa" accepts an individual as the parent (and a type under an individual), unlike reset src/dst; an isa cycle logs a traceback**
src/sn/view/graphics/viewEditing.py:762, ~781
`makeRelationFrom()` starts the elastic line with no filter for ISA; `makeRelation()` refuses only node<->relation. `VRelation.chooseNewEndpoint().acceptable()` (vrelations.py:707-711) refuses exactly these for reset dst. `validate()` is silent; only the clingo rule `isa_individual_parent` reports it when the user reasons. A cycle attempt's ValueError is logged with `logger.exception` as a full traceback.
Repro: `verify-input-editing-logic/verify_c.py` -- `T isa A: True | logged: ''`; `A isa B: True | logged: ''`; `B isa A: False | logged: ... Traceback ...`; reasoning report `E: A#256 isa individual B#258`.
Fix: when `typ is self.model.ISA` pass a filter mirroring `acceptable()` (isType, not inferred, `parentProblem()` None, same VRelation-ness) so the release reports "can't be chosen here"; in `makeRelation()` catch ValueError/PermissionError and `logger.error(str(ex))`. Test in test_viewSmoke.

**Find scrolls to the top-left of the union of all matches, so with matches far apart the window shows none of them; no next/previous**
src/sn/view/graphics/viewEditing.py:726-731, :489-491 (`scrollToShow.start`)
When the union box is bigger than the window, `start()` returns `a - margin`: the corner, often empty. viewing.rst:104 says the view scrolls to show them. The missing Next/Previous is a feature gap rather than a bug.
Repro: `verify-input-editing-visualization/bug2_find.py` -- `found: [zz-one, zz-two] visible after Find: ({zz-one: False, zz-two: False, middle: False}, (-21.0, -21.0, 809.0, 457.0))`.
Fix: if the union fits, keep `scrollToShow(union)`; else `_centreOn` the match nearest the window's centre and say how many more there are. Follow-ups: Next/Previous in the dialog (Return = next, "k of n"), a "zoom to fit matches" button via `zoomToFit()`.

**Re-ending a relation by dragging its terminal: the rubber band sprouts from the label, not the grabbed end, while the old connector stays drawn**
src/sn/view/graphics/vrelations.py:723; viewInput.py:314, :480
`chooseNewEndpoint()` calls `elasticLineChoice(self, ...)`, anchored at `originNode.centerPt()` -- the label's centre for a VRelation. A 3-px line in the relation's own colour is drawn from the label over anything in its way; for src the arrowhead is at the label end. The drop itself works.
Repro: bug3_terminal.py -- `terminalAt: dst`, `elastic line coords: [117.0, 236.0, 385.0, 121.0] colour: black width: 3.0 arrow: last` (label centre; terminal was at (118.7, 349.8)); `old connector still drawn`. bug3-dst.png, bug3-src.png.
Fix: give `elasticLineChoice` an optional `fromPoint` and pass the grabbed terminal's point (`connectInfo.sourceEnd/destEnd`); hide that half of the connector and its terminator during the choice (restore on cancel/drop); one dedicated rubber-band style (thin, dashed, fixed colour) shared with "make relation to..."; for src draw the band from the cursor to the label with the arrow at the label.

**Copy as picture: the PNG is four times the canvas size on Linux/Windows (twice on the Mac)**
src/sn/view/graphics/imageExport.py:428; pu: src/util/platformSupport.py:263
`copyImage()` draws the PDF at PNG_SCALE (2) pt per pixel and asks `pdfToPNG()` for 144 dpi; the sips branch renders at 1 px/pt and marks the dpi, the pypdfium2 branch renders at `scale=dpi/72=2`, giving 4x pixels tagged 144 dpi. DPI-honouring programs paste at 2x on-screen size, others at 4x.
Repro: `verify-app-files-export-logic/b1_copy.py` -- `canvas picture (px): (959, 754) | PNG: {size: (3836, 3016), dpi: (143.99, 143.99)} | ratio: 4.0`.
Fix: make `pdfToPNG()` render at one pixel per point and tag the dpi in both branches (`render(scale=1)`, `save(dpi=(dpi, dpi))`), reword its docstring; assert in test_imageExport that the PNG's pixel size is `PNG_SCALE * _size()`.

**If none of the files named at start-up can be opened, the app runs with no window and no model directory**
src/sn/view/graphics/guiApp.py:810-813; also `onOpenDocument()`/`onOpenFromAnotherCopy()`
`startUp()` returns as soon as `files` is non-empty without checking anything opened; `openWindow()` swallows every failure (dialog, None) and for a non-existent .snv asks for a model and returns None if cancelled. The root is withdrawn, so the process runs invisibly (off the Mac without a menu bar); the single-instance hand-off then sends later files to it.
Repro: b2_startup.py -- `(a) notes.txt: windows = [] | directory shown = False | root state = withdrawn`; `(b) brandNew.snv, model dialog cancelled: ...` same.
Fix: `if (files or self._openedDocuments) and (self.windows or self.directoryShown()): return`, so an all-failed start falls through to the directory; in the two document handlers, `showDirectory()` if nothing opened and there's no window. Test: `startUp([bad file])` leaves `directoryShown()` True.

**'Open super model' for the system model (and base rules) puts the view file inside the program's package, so it fails silently on a read-only install**
src/sn/view/graphics/viewFiles.py:423-425; guiApp.py:479-481
`superModelView()` places sn's view at `<sn.model package>/sn.snv` and the base rules' beside their file; `openViewOn()` builds `SNGView(viewURL, mode='w')` whose `fixURL` needs a writable folder -- an AppImage mount or Program Files isn't -- and the PermissionError is only logged. For the base rules, line 425's `fixURL(mode='w')` raises out of the menu command. Where writable, Save view writes sn.snv into the package.
Repro: b4_super.py -- `sn's view URL: file:///.../sn/model/sn.snv | inside the sn.model package: True`; `(read-only package) openSuperModel(sn) raised nothing; new windows: set()`; base rules: `PermissionError` out of the menu command.
Fix: when `canWriteUrl()` is False for the package folder, place sn.snv/baseRules.snv under `sn.SN_FOLDER` (~/.sn/) or open the view read-only (`mode=''`) at the package location; never `fixURL(mode='w')` for a possibly unwritable spot; have `openViewOn()`'s except show a dialog. Update files.rst's sentence about where these views live.

**File | Change model... on a never-saved view closes its window, asks for 'a Model file for the new view', and can leave nothing**
src/sn/view/graphics/viewFiles.py:175-181; guiApp.py:534-539
`changeModel()` closes the window and calls `openWindow(view.url)`; for a view made with File | New and not saved there is no file, so the non-existent-.snv branch asks for a model; cancel leaves no window and the view is gone; choosing a model makes an empty new view. The dirty check doesn't help (a fresh view isn't dirty).
Repro: b5_change.py -- `fresh.snv exists: False | windows: [...] | view dirty: False` then `changeModel() returned: None | windows now: [] | dialogs asked: [Open a Model file for the new view ...]`.
Fix: in `doChangeModel()`, if `not urlExists(self.url)` either `doSaveView()` first (return if refused) or refuse with "Save the view first: Change model re-reads it from its file"; make `Application.changeModel()` return None without closing when the file doesn't exist. Test: changeModel on an unsaved view leaves its window open.

**Copy as picture silently turns any text outside Windows-1252 into "?"**
src/sn/view/graphics/imageExport.py:362 (`drawRuns`), :62 (`SYMBOLS`)
Every run is `encode("cp1252", errors="replace")`; only 16 symbols are routed to PDF's Symbol font. Cyrillic, Greek, CJK and most logic/set symbols become `?` in the PDF and clipboard PNG while the terminal says "Copied a picture of N objects". (Side note from the run: under Xvfb a node named '東京' raised `ValueError: min() iterable argument is empty` in decorators.py:351 `preferredLayout()` when `layoutText()` measured a 0 natural width; guard `naturalW == 0`.)
Repro: `verify-app-files-export-visualization/export_unicode.py` -- pdftotext `???????`, `??? ? ?`, `??`; `Zoë Müller` and `∀`/`→` right; `warnings logged during export: []`. out/uni.png.
Fix: now: extend SYMBOLS with the Symbol font's Greek alphabet and set/logic glyphs (α=0x61..., ⊆ 0xCD, ⊂ 0xCC, ⊃ 0xC9, ⊇ 0xCA, ∪ 0xC8, ∩ 0xC7, ∉ 0xCF, ∅ 0xC6, ≡ 0xBA, ≈ 0xBB, ∴ 0x5C, ↔ 0xAB, ⇔ 0xDB, √ 0xD6, ∑ 0xE5, ∏ 0xD5, ∂ 0xB6, ∇ 0xD1, ⊕ 0xC5, ⊗ 0xC4), and have `drawRuns()` collect replaced characters so `doCopyImage()` logs a warning naming them and the objects (and flashes the terminal). Later, as its own item: embed a Unicode TrueType font (DejaVuSans/Arial Unicode via Pillow) as CIDFontType2/Identity-H.

### Low

**setSuperModels refuses to drop a super-model whose copy is already listed, with a misleading message**
src/sn/model/model.py:1611-1623
Only `added` (dbs not already in superDBs) are tried as the copy, so a copy that was already listed is never tried though `_copyChanges()` would find no problems; the message says "none of the others is a copy of it", which is false. The docstring matches the code; files.rst:141 doesn't say the copy must be new. Replace super-model... is a workaround.
Repro: `deepdive/model/probe2.py` Probe 3 -- `REFUSED: "onto.snm": 1 of this model's references are to its objects, and none of the others is a copy of it.`
Fix: at :1615 iterate `[db for db in dbs if db is not old]` sorted by name match first (added then kept); update the docstring. Test in test_relativeSuperModels.

**getDescendants(model=...) doesn't limit the descendants to the model, as its docstring promises**
src/sn/model/model.py:548-567
`model` is used only in the isa special case; the general walk never filters or passes it down, so with two related models open the terminal's `instances`/`subtypes`/`animal *` include the other model's objects.
Repro: v0_v2_v4.py -- `animal.getDescendants(model=A): [('dog','A.snm'), ('rex','B.snm')]`.
Fix: decide which is meant. Cheapest: fix the docstring (callers rely on all descendants). If scoping is wanted, an explicit keyword (`onlyIn=model`) that skips and stops at a foreign child, used by the terminal's query.

**reasoning.rst contradicts itself about whether conclusions are added to the model**
sphinx/source/user/reasoning.rst:115-117
"None of the reasoner's conclusions are added to the model" contradicts :54-69 on the same page and developer/reasoner.rst; the code matches the earlier section (settled by reading).
Fix: replace the paragraph with the current rule: conclusions are added as inferred objects/attributes (faded, not saved, not editable, retracted by Retract, kept by the next reason while still concluded), pointing to "mark as asserted".

**fixKwargs fills a default for a parameter already passed positionally: context.reason(m), paste(m), show(obj, m) raise TypeError**
pu: src/util/commandParser.py:1702-1706, :1778-1782
The default-filling loop looks only at `kwargs`, so a positional model is supplied twice. No shipped caller passes model positionally; bites plugin/script authors and tests.
Repro: verify.py CLAIM 4 -- `c.reason(m) -> TypeError ModelContext.reason() got multiple values for argument 'model'`; keyword forms work.
Fix: `bound = sig.bind_partial(*args, **kwargs).arguments` (fall back to old behaviour on error) and fill only names not in `bound`; same guard on the positional-only move. Test `f(a, /, model=None)` as `f(x, m)` and `f(x, model=m)`.

**An observer (or callback) that detaches itself while being notified makes Subject._notify() skip the next observer**
pu: src/util/observer.py:314, :230, :258
`_notify()` iterates the live lists; `detach()`/`detachCallback()` shrink them. `notifyLater()` already snapshots. No current sn path detaches during a notification (SNGView.update guards with `_closed`), so latent.
Repro: probeB.py Claim 2 -- observers a(self-detaching), b, c -> `{'a': 1, 'c': 1}` (b never updated); callbacks `['one']`.
Fix: `for tup in list(observers)` and `for tup3 in list(callbacks)`; testObserver.py case for a self-detaching observer and callback.

**PRDb: `'name' in db` is False for an object of a super-DB that `db['name']` returns**
pu: src/util/persistence/pRef.py:1163-1170, :1180-1190
`__getitem__` falls back to superDBs for str keys (and ints < 256, undocumented); `__contains__` resolves only locally. No user-facing sn path uses the idiom today.
Repro: probeA.py Claim 4 -- `'animal' in m2 -> False; m2['animal'] -> Node(animal, ...#256)`.
Fix: make `__contains__` mirror `__getitem__` (document or drop the `< 256` rule); test `'k' in db == (db.get(k) is not None)`.

**DoList.undo()/redo() move the index even when the command raised, so the next Ctrl-Z undoes the wrong thing and redo re-runs the failed command**
pu: src/util/command.py:330-347, :60
The index moves in a `finally`; `Command.undo()` clears `done` before the subclass raises, so `redo()` re-runs `do()` on effects never removed. `ViewDoList` doesn't catch command exceptions, so a PermissionError (write-locked model, inferred object) during undo reaches this path.
Repro: probeB.py Claim 5 -- `dl.undo() raised: boom; undoDesc = one; redoDesc = bad`; `redo() re-ran bad: log = ['do one', 'do bad', 'do bad']`.
Fix: move the index only after the command returns; on failure restore `done` (True for undo / False for redo) and re-raise; have ViewDoList catch and show the message. Honour or remove `LambdaCommand`'s ignored `changesState` (:151).

**A label whose hook is in the `${(module:function):+...}` form is memoized, though a hook in a label is promised a call each draw**
src/sn/view/graphics/vobjects.py:587; labels.py:160-170
The memo is skipped only for `"$(" in template`; labels.py also accepts `${(` as a call (viewing.rst:300; view.rst:187 promises a call each draw).
Repro: verify.py V4 -- `'$(vverify:tick)': 3 labelText() calls -> hook called 3 time(s)`; `'${(vverify:tick):+has source}': ... hook called 0 time(s)`.
Fix: `labels.hasHookCall(template)` (True for `$(` or `${(`) used at :587; one labels test per form.

**A context window's title runs past its banner and over the italic kind label** (found by view-core and containment visualization; merged)
src/sn/view/graphics/decorators.py:767-776; vobjects.py:1708-1717 (window sizing)
Title anchored 'w', kind anchored 'e' at x2-6, no width, clipping or fit check; WINDOW_MIN 160 ignores the title. A 25-character sentence-name in a 180-wide window overprints "rule" and sticks 25 px past the frame; a 160-wide requirement window named "siblings have parents" overprints 73 px, collapsed the same.
Repro: v1234.py (4) -- `banner x 20..200; title x 39..225 past-right=25; ... overlap=True`; `verify-containment-visibility-visualization/verify.py b4` -- `title bbox (39, 21, 189, 37)`, `kind bbox (102, 21, 175, 37)`. narrowShot.png.
Fix: draw the kind first, measure with `tkfont.Font(...).measure()` at the current scaled font, cut the title with an ellipsis to the banner's inner width minus the kind, and drop the kind item when fewer than ~3 characters remain; keep the full name in the tooltip. Don't use `create_text` width (it wraps) and don't raise WINDOW_MIN (resizes windows behind the user's back). Test: 40-character name in a 180-wide window.

**A dangling end's stub runs from the label's centre straight through the middle marks** (found by both relations-marks lenses; merged)
src/sn/view/graphics/vrelations.py:311
`_styleEnds()` starts a stub at `centerPt()` when the label shows no text, while the connected half is cut back to `_middleStops()`; the stub is drawn later (above), so a ring, dot or `<|>` gets a faded line through it.
Repro: probe3.py -- `ring: [162,43,178,59] src line end: [162.08, 49.87] dst stub line: [170.0, 51.0, ...]`, `stub drawn ABOVE the ring`; verify.py stub -- `d` stub `[186.0,46.0,212.3,48.5]` through the right arrowhead (x 189.6-200); d2 `*` stub starts at the dot's centre. probe3.png, stub.png.
Fix: `s1, s2 = _middleStops(self._middleLayout())`; src stub from `centre + (dx,dy)*s1`, dst from `*s2` (stops are 0 without solid marks, so test0650 keeps passing). `_middleLayout()` lays out with the unscaled width while the connector uses `width/scale`; use the same for both (moot once line widths zoom). Add to test0600danglingStub.

**'arrow'/'crow' middle marks point at the label when moved after it (no source side, text label)**
src/sn/view/graphics/connectors.py:499-508 (`_labelFarMarks`); pu: lineMarks.py:538
The middle's Mark objects go unchanged to the START stack of the label->destination line, where OUTWARD resolves backward. `_labelNearMarks()` is fine.
Repro: probe.py -- `arrowhead tip x: 176.64 ... -> tip at the LEFT (toward label)`; probe.png `U <--...--> e3`.
Fix: pass `tuple(dataclasses.replace(p.mark, direction=FORWARD if p.forward else BACKWARD) for p in middle.marks)` in `_labelFarMarks()` (and `_labelNearMarks()` for symmetry). Test with src None, 'arrow' and 'crow'.

**MarkerWithTooltip.draw() drops its tooltip reference on every redraw, so erase()/delete() never remove the tooltip**
src/sn/view/graphics/decorators.py:514-521, :524-535
`draw()` starts with `self.tooltip = None` and only creates one for a new item; after any redraw `erase()`/`delete()` skip `tooltip.delete()`, leaking a CreateToolTip, three Tcl commands and a pending `after` per hide/show cycle; a tooltip can pop up for an erased marker.
Repro: `verify-relations-marks-logic/verify.py` -- `after first draw: marker id 7 tooltip None | live canvas tooltips 15 tcl commands 441`; `after 5 hide/show cycles: ... tooltips 20 tcl commands 456; stale tooltips bound to deleted items: 5`.
Fix: initialise `self.tooltip = None` in `__init__` and delete the first line of `draw()`. Test: draw twice, assert tooltip set; erase, assert no `<Enter>` binding for the old id.

**vis/shadowColor is documented for the user but does not exist**
src/sn/view/graphics/decorators.py:942; sphinx/source/user/viewing.rst:187
ShadowDecorator hard-codes gray70 (its docstring admits it); nothing in sn/model defines the attribute. (Code reading; grep shows only the two mentions.)
Fix: remove the row from viewing.rst, or define `TOP['vis/shadowColor'] = Attribute('gray70', 'color', VAR_DEFAULTED, ...)` and read it in `ShadowDecorator.draw()` each draw.

**Inherited ends: middle marks are faded when the label shows text but full-strength when it doesn't**
src/sn/view/graphics/vrelations.py:333-334
With text the middle's marks live in `labelNearTerminatorIDs` (part of `sourceIDs()`) and are recoloured with the source half; with an empty label they are in `middleIDs`, never recoloured. The same relation changes its middle's strength by setting `vis/label = ''`. (The MAYBE improvement below argues the other direction -- never fade the middle; one rule is needed either way.)
Repro: verify.py inherit2 -- i1 bars `#9191f7` (faded); i2 mid items `red` between `#f79191` lines. inherit2.png.
Fix: simplest and consistent with the text case: after the loop, `if all(self.inheritedEnds.values()): recolorMarks(canvas, info.middleIDs, faded line, faded fill)`. If the middle is meant to be the relation's own, return its ids separately from the label-near stack (see the MAYBE item).

**arrange() builds its LayoutMoves while an earlier smooth move is still under way, so undo puts things back at mid-tween positions**
src/sn/view/graphics/layout.py:~450
`LayoutMoves.__init__` records current boxes as 'from' before `doList.do(cmd)` calls `finishTween()`; a second arrange within the 200 ms tween (8 x 25 ms) records mid-tween positions.
Repro: `verify-layouts-logic/scen.py` N -- `undo of the balloon puts back the tree arrangement: {'base1': ((-15, -4), (46, 153)), ...}` (between the two).
Fix: `finishTween(self.view)` at the top of `arrange()` before `targets()`, and at the top of `TreeLayout._adjustment()`/`_RoundLayout._adjustment()` (adjustAgain runs from after_idle).

**A dropped node is never nudged left, and the nudge jumps upward or diagonally instead of the shortest way off**
src/sn/view/graphics/layout.py:1063, :1113, :1001-1011
`adjustPos()` calls `layout(self)` with no direction, so `placeNode` takes LATERAL and sets `leftLimit = rect[0]`; and `freeRingSpot` scans each ring from the top row, so the first free place is the top/left one. The LATERAL limit currently masks the ring-order defect for drops onto a bottom edge, so fix both together.
Repro: `verify-layouts-visualization/v_drop.py` -- `b3: 10px into tall's left edge: moved (+0,-50)`; `b2: 10px into wide's right edge: moved (+30,-30)`; NEAREST alone from b3's spot -> up-left diagonal.
Fix: (1) for a drop (direction UNSPECIFIED, no reference/loc) use `Direction.NEAREST`; (2) in `freeRingSpot` test each ring's places in order of distance from the rect, or try `clearOf(box, keepOut=overlapping boxes, obstacles, gap)` first and fall back to the ring scan.

**'show > relations...' for a hidden relation type reports 'all shown already' and shows nothing**
src/sn/view/graphics/viewVisibility.py:270, :303 (nodes)
`showRelationsOfTypes()` skips anything in `_shownModelObjects()`, which by its docstring includes hidden ones; `_Represent.do()` would exempt them. Erased categories work (disconnected), only the hidden case fails.
Repro: v_show.py -- `likes hidden: True`, `MESSAGE: There are no relations of those types to show: they're all shown already.`, `after: likes: True exempt: False`.
Fix: in both methods count as shown only view objects that are connected and not hidden by category (`vo.isHidden() and isFiltered(mo, ('hide',)) and not categoryExempt` -> not shown) so they go through `represent()`. Test each menu with a hidden category.

**Undoing a hide/erase doesn't restore the exemptions it cleared**
src/sn/view/graphics/sngContext.py:490-493, :509-521
`_Visibility.do()` clears `categoryExempt` on objects shown anyway, recording nothing; `undo()` restores only `hides`. After hide/show/hide and two undos, an object the user was told would stay shown is hidden.
Repro: v_undoExempt.py -- `undo B: T hidden True exempt False hides {'types': 'hide'}  <- before B it was shown`.
Fix: collect the unexempted objects in `self.unexempted` (first time only, like `self.erased`), restore the flag in `undo()` before `applyVisibility()`, clear again on redo; clear the list in `delete()`.

**Open Read-only is refused for a model that is only in memory, with a message saying it's 'already open'**
src/sn/view/graphics/guiApp.py:636-640
`openEntry()` treats any model in `PRDb.AllDBs` as open; a model whose windows were all closed stays there, while the directory's `_isOpen()` says False. Workaround: open normally, Close model, then Open Read-only.
Repro: b3_readonly.py -- `open windows: 0`, `write-locked: False | infos: ["family" isn't opened read-only: its model ... is already open, and can be changed.]`; after `unload()` write-locked True.
Fix: treat the model as open only if some window's view is of it (`DirectoryPane._isOpen()`'s test); if merely in memory with no dependents, `checkSaveModified()` then `unload()` and proceed as a fresh open; if it has dependents say "in memory, used by X". Don't just write-lock an in-memory dirty model.

**Every new window opens at 300x400 at exactly +20+20, on top of the last: the cascade is computed but never used**
src/sn/view/graphics/guiApp.py:442, :482, :1077; sngView.py:106/115
`defaultChildLocation` is incremented and never read; `SNGView.__init__` always builds "300x400+20+20". Saved views keep their geometry, so only File | New, a model with no view, and super-model views are affected.
Repro: `deepdive/app-files-export/new_windows.py` -- `geometry: 300x400+20+20` for both windows, `defaultChildLocation: (100, 140)`.
Fix: `Application.nextWindowGeometry()` (~70% of the screen, capped, at the cascade point, advancing 40 px and wrapping); pass it from `openWindow()`/`openViewOn()` for new views; remove the dead increments; keep "300x400+20+20" only as the no-Application fallback.

## Plausible bugs (not reproduced)

None. Every reported bug was reproduced by its verifier; there are no PLAUSIBLE or unverified findings in this dossier.

## Improvements worth doing

Ranked by the judge's value (desc) then cost (asc).

**Make `set attribute <rel-type> symmetric no` (or false) clear the tag** -- value 4, cost S
src/sn/controller/modelInterface.py:697. Relational properties are presence tags (snAttribute.py:75-83), so the inverse of the documented `set attribute has-sibling symmetric yes` reports success and leaves the type symmetric; only `delete attribute` clears it. Proposal: in `_Set_attribute.__init__`, for `key in RELATIONAL_ATTRS` with a str value, parse with `strToBool` (ValueError otherwise) and record `clearTag`; `do()` deletes the local record when clearing, else sets the tag; undo restores the saved record or absence. Leave `setAttr`/`__setitem__` and the editor alone; document in the help and concepts.rst. Risk: concepts.rst/tutorial say the tag is "there or it isn't, whatever its value" -- touch only the typed-command path; undo must be exact.

**Batch the label placement at the end of an animation run** -- value 4, cost S
src/sn/view/graphics/animatedLayouts.py:919-925. `_settleLabels()` calls `reposition(adjustPos=True)` per label, each scanning the whole view; `FindFree.placeLabels()` (layout.py:1174-1203) already gathers obstacles once. Re-measured: 12.05 s vs 0.68 s on 119 nodes / 1957 relations, and "place labels" is on by default. Proposal: collect floating, shown, connected VRelations; `reposition(adjustPos=False)` each; then one `placeLabels(labels)` call via `view.localLayout` if it defines it usefully, else `FindFree(view)`. Risk: placement differs slightly from one-by-one (the expansions' convention); labels must stay in the run's `start` moves so Cmd-Z undoes them.

**Expand counts should say what expanding will bring in** -- value 4, cost S
src/sn/view/graphics/expandDialog.py:74; vobjects.py:1603, :1970. "expand all (3)" and "has-parent -> (3)" count shown relations too; expanding a choice that adds nothing gives no feedback. Proposal: a `shown` predicate beside `hidden` in `relationChoices()`, a `Choice.shown` count merged in `expandChoices()`, labels "has-parent -> (3, 1 new)" / "(3, all shown)" greyed, menu "expand all (1 new of 3)", and a "nothing new to show" log line. Risk: update viewing.rst:20-24 and the three asserting tests (test_expandBatch.py:221,237; test_expandDialog.py:85).

**Scale line and border widths with the view (with a 1 px floor)** -- value 4, cost M
Same change as the confirmed bug "Line and border widths stay in screen pixels" above; the judge's refinement: `_Style` keeps `width` in view units and `strokeWidth = max(1.0, width * scale)`; `Shape.updateKwargs()` maps `vis/borderWidth` to `max(1, w * scale)`; `selectedLineWidth()` stays in view units; zoom() applies it via `repaintSoon()` or a width pass over 'vis/shape' and connector items; test0680 asserts the line width doubles. Treat "hide labels below a 4 px font" and "smaller handles on sub-20 px boxes" as separate proposals to be measured first. Risk: depends on repaint-on-zoom; the floor must keep lines from vanishing.

**Refuse a second isa link between the same two objects** -- value 3, cost S
src/sn/model/model.py:524 (`parentProblem`). Each `assert person fred` or `new_relation(ISA, fred, person)` adds another IsaIndividual; `getParents()` lists duplicates and deleting one link changes nothing. Proposal: `parentProblem(parent, except_=None)` returns a message when `parent` is already a direct non-inferred parent via a link other than `except_`; pass the moved link as `except_` from `_Reconnect` and the view's connector; de-duplicate `getParents()` as a safety net; report duplicates from old files in the status report with a "remove the extra isa link" action, as `_validateSelfIsa()` does. Risk: moving an isa link's end back onto its own current destination must stay allowed; old files must still load; check the reasoner's inferred-beside-asserted isa case before adding the check there. (Pairs with the confirmed `assert <type> <obj>` bug.)

**Undo the creation when the name dialog of a new object is cancelled** -- value 3, cost S
src/sn/view/graphics/viewEditing.py:72-80, :808. Escape/Cancel leaves a nameless 20x12 box in the model and every view (prop0.png). Proposal: in `addNewObjectMenus.make()` and the object menu's make-new path, after `new(...)` returns, if the object's name is still `''` call `self.context.undo()` and log "cancelled" (the `into` case undoes the composite); make `_askName` report whether the editor was accepted; optionally draw a nameless object as "(unnamed)". Risk: `_askName()` runs inside the creating command's do() via the 'new' notification, so the undo must happen after `new_node()`/`new_relation()` returns; a nameless object may be legitimate in a pane, so only an empty name counts as cancel.

**Title windows by file name and folder, not the raw URL** -- value 3, cost S
src/sn/view/graphics/guiApp.py:1085-1088. Titles read `file:///Users/me/Documents/Semantic%20Nets%20Examples/family.snv`; `sn._displayPath()` already exists. Proposal: title `f'{fileName} — {folder}'` with the folder as `_displayPath()` shows it (a remote view: its URL folder); keep `self.windows` keyed by URL. Second step, once a dirty-changed hook exists on Dirtyable/SNGView: `wm_attributes('-modified', dirty)` on macOS, a "• " prefix elsewhere. Risk: none on the title itself (the two `.title()` reads are log messages); keep the folder so same-named views stay distinguishable.

**Grey "File | Save model" for a write-locked model** -- value 3, cost S
src/sn/view/graphics/viewFiles.py:309, :503-525. Verified: after Open Read-only the item is `normal` and choosing it only logs a warning. Proposal: `WRITE_LOCKED_ITEMS = ('File|Save model',)` greyed in `refreshLock()` on `model.writeLocked()`, and `enabled=not self.model.writeLocked()` at :309; keep `doSaveModel()`'s warning. Risk: keep Save view/Save view as.../Save model as... enabled; grey on the model's write lock only, not the view's edit lock.

**Batch selection changes instead of redrawing each object** -- value 3, cost M
src/sn/view/graphics/vobjects.py:2059; vrelations.py:422-432; viewInput.py:382, :588. At 2116 objects: deselect-all by a background click 1.4-1.6 s, selectAll 0.93 s, Delete of the selection 2.4 s (undo 0.18 s). Proposal: `VRelation.selected()` itemconfigures the line and mark items' widths instead of `draw()`; `VObject.selected(False)` drops `self.draw()` if only the handles need removing (or defers one after_idle pass per deselect loop); a view-level deselect helper updates `view.selected` once. Target under 200 ms; profile the Delete cost separately. Risk: `draw()` on deselect may restore stacking order -- check before removing; the proposal's `batchedItemStates()` misreads that helper (it batches hide/show, not draws); a full `repaintSoon()` costs as much as selectAll does now.

**Bump the model version in modelObjectsReplaced()** -- value 2, cost S
src/sn/view/graphics/sngView.py:259-266. After Replace super-model the vis caches are cleared but `_labelMemo`, `Shape._presentOptions` and `_containmentMaps()` are keyed on `modelVersion()`, which isn't bumped; reproduced (verify2.py P0): a `$name/$note` label still read `person/old` after the method's own repaint. Proposal: call `self.structureChanged()` before `repaint()` inside `if count:`; extend test_sharedOntology with a differing note. Risk: none worth naming.

**Don't keep the source window transient for the view it was opened from** -- value 2, cost S
src/sn/view/graphics/sourceWindow.py:161. `ownDialog(self, parent)` defaults to `keep=True`; the project's own convention for long-lived tool windows (pythonParser/dialog.py:278, XMLreader/view.py:443, and ownDialog()'s docstring) is `keep=False`, so on macOS the code window can't go behind its view, isn't in the Cmd-` cycle, and is orphaned when the view closes. Proposal: `ownDialog(self, parent, keep=False)` with the same comment as pythonParser/dialog.py; no change to `showSource()`. Risk: practically none (macOS-only effects, not visible under Xvfb).

## Improvements to consider

**Don't fade the middle marks with an inherited source end (text label)** -- value 2, cost M. Reproduced (probe2.png): with a text label the middle's bars are drawn as part of the label-near stack and faded with the source half; the docs don't say whether the middle counts as part of the half. The marks' meaning (cardinality, a "not" bar) is the relation's own, so full colour is the better picture, but the case is uncommon and the ids are interleaved by one `drawMarkedPath()` call. Do it only while touching `_labelNearMarks()`/`_labelFarMarks()` for the dangling-ends bugs: have lineMarks return per-mark id groups, store the middle's in `middleIDs` even when drawn beside the label, and have `sourceIDs()`/`destIDs()` exclude them. Note this is the opposite rule from the simplest fix of the confirmed "inherited ends" low bug; pick one.

**Starting the animation replaces the kept layout: document it and make it undoable** -- value 2, cost S, partly present already. The switch to "avoid overlaps" is deliberate and right (a tree layout would re-lay the trees after the run's composite command and on the next edit), the menu tick does follow it, and the info line reaches the log pane. What's missing: a sentence in animation.rst and layouts.rst, and the layout change as part of the run's undo entry (a small command in `_finish()`'s composite whose undo puts the old layout object back, pins intact, and resets the menu variable); optionally the same line in the layout panel's status. Don't suspend-and-restore for the run. Resolves the confirmed medium bug of the same name.

**Replace the modal "isn't opened read-only" box with a terminal line** -- value 2, cost S. The box matches `openEntry()`'s docstring and guarantees the user notices that an explicit Open Read-only did something else; from the directory the root is on screen so `parent=self` is right. Only if the author generally prefers the terminal pane plus a flash (as `_saveCopy()` does): replace with `logger.warning()` + flash once the window is open. Independently and cheaply, give the message boxes in `closeModel()` (guiApp.py:942) and `onInstallExamples()` (:892/906) `parent=dialogOwner(self.focus_get() or self)` so they can't come up behind a view window on macOS.

## Rejected or already present

| Title | Why |
|---|---|
| (none rejected) | Every improvement was ADOPT or MAYBE. |
| Starting the animation replaces the kept layout (menu tick and log line) | Partly present already: `setDynamicLayout()` updates the menu variable and the info line reaches the log pane; the doc and undo parts remain (see "Improvements to consider"). |

## Refuted claims

None. No bug was refuted by its verifier. A few claims were narrowed in scope rather than refuted, so nobody re-reports the wider version:

| Claim as reported | Verifier's correction |
|---|---|
| `format model tostring` breaks the terminal | Not reachable: the parser rejects it (`format` isn't positional-only), a separate small bug; only the GraphObject formatters raise NameError. |
| Decorators chosen once persist in the saved view | Reopening rebuilds them; only the enlarged 320x200 box persists. |
| Labels on their own end node happen routinely | Only when dropped there, nodes overlap, or a layout stacks them; `gapMidpoint()` keeps floating labels in the gap. |
| Shipped family.snv loses isa conclusions with "types" hidden | The shipped rules relate variables to variables; only user-made rules concluding a type are affected. |
| Open Read-only on an in-memory model needs quit-and-restart | Open normally, Close model, then Open Read-only works. |
| Self-loop fix via the curve's tangent | Gives the same wrong answer (the curve is a hairpin); turn the marks to the node->label axis explicitly. |
| fixKwargs positional defaults hit the documented `context.move(vo, 10, 20)` | That signature has no default-named parameter early; no shipped caller is affected. |
| Observer self-detach affects sn today | No current sn path detaches during a notification; latent. |

## Coverage

**Model (logic).** Read fully: model.py, model/__init__.py, copying.py, constraints.py, directory.py, sn/__init__.py, snAttribute.py, pu abstractGraph.py, developer/model.rst, user/concepts.rst, user/files.rst; the AttributedObject part of pu attribute.py and PRObject/PRDb init/register/save/superDB parts of pRef.py, dirtyable.py. Skimmed reasoner.materialize, modelInterface commands, viewEditing copy paths, sngView.modelObjectsReplaced, vrelations topics, test setups. Ran deepdive/model/probe1-3.py and test_model, test_copyPaste, test_relativeSuperModels (19 OK). Checked fine: delete/undo of a type keeps children's parents; inferred-attribute overwrite; parsePath('file:/path').

**Reasoner (logic).** Read fully: reasoner.py, clingoReasoner.py, clingoReasoner.lp, viewReasoning.py, developer/reasoner.rst, user/reasoning.rst, test_reasoner.py; relevant parts of model.py, modelInterface (reason/clear_reasoning/mark_asserted), sngView topics, vobjects (validate, answerQuery, showConclusions), viewContainment, constraints.py, contexts.rst; skimmed test_rules.py. Ran deepdive/reasoner/probe1.py and probe2.py under xvfb (deleting a node with inferred relations behaved acceptably). Not run: full suite. Not examined: the attribute editor's inferred-value UI, http super-models, undo across mark_asserted after a later reason.

**Controller (logic).** Read fully: modelInterface.py, controller/__init__.py, textUserInterface.py, __main__.py, pu commandParser.py, pu command.py, architecture.rst, terminal.rst, the four test_controller modules; the model/abstractGraph/attribute/utils code the commands call and the view call sites of CompositeCommandMgr and paste/cut/copy. Ran the four test_controller modules (31 OK) and deepdive/controller/probe1-4.py. Noted, not reported: CompositeCommandMgr.__exit__ runs queued commands when the with-block raised (commandParser.py:1645-1647); `delete attribute` of an inherited-only attribute gives a bare KeyError and is listed as "set attribute" in the undo queue (modelInterface.py:746, 756); query() mutates its argument; ConvertingDict.typeCheck's message prints "type". Leftover probe files in sn-opt were removed; git status clean.

**pythonUtils core (logic).** Read fully: attribute.py, observer.py, command.py, pRef.py, serialize.py, serializeXML3.py; followed into utils.py, attributeEditor.py, prefs.py, sn/__init__.py, model.py (getSupers/getSubs/setitem/IsaIndividual._supersChanged/unload), sngView, sngContext, viewCommands, guiApp.openWindow. Skimmed pu tests and test_parentsCache.py. Ran deepdive/pu-core/probe1.py and probe2.py. Not run: full suite. Not reported: `get(key, note=...)` sets the note on a throwaway copy; `obj[key]=None` asserts (NoneType not a valid type); strdict values decode as dict.

**View core (logic and visualization).** Read fully: sngView.py, sngContext.py, viewBase.py, viewViewport.py, vobjects.py (all), decorators.py, shapes.py, viewVisibility.py, viewInput.py, developer/view.rst, user/viewing.rst, the diffs of a187b46/47e098b/c7a139e, connectors._Style, VRelation init/draw/reposition/placedLabel, viewEditing._placeNew/showAllModel/showTypes, test_relationMarks fixture and tests 0680/0690; followed into pu abstractGraph, pRef, dirtyable, attribute, labels.py. Ran under Xvfb (Python 3.14/Tk 9.0.3): deepdive/view-core/exp1-3.py, tkprobe.py, fontprobe.py, zoomstate.py, misc.py, emarker.py with renders. Checked and cleared: Tk's bbox/find ignore hidden items (zoomToFit, resetScrollRegion, selection box not fooled), cache refresh/fade paths, `_priorStates` bookkeeping, undo of moves, drag deltas at zoom. Not run: full suite, the replace-model path (later covered by the judge's verify2.py P0). Noted: vis/borderSmooth listed in viewing.rst but unimplemented; fontSize() truncates to int (text up to ~7% small at fractional zooms).

**Relations and marks (logic and visualization).** Read fully: vrelations.py, connectors.py, labels.py, decorators.py, shapes.py, pu lineMarks.py, user/viewing.rst, test_relationMarks.py, pu test_lineMarks.py; skimmed vobjects draw/hide/show/labelText/emptyLabelSize/containsPt/disconnect, viewViewport zoom, pu tooltip.py, modelInterface.reconnect, sn/model/__init__.py vis/ defaults. Ran test_relationMarks (18 OK), test_lineMarks (29 OK), deepdive/marks/probe.py, probe2.py, probe3.py and deepdive/marks-viz/scenes.py (loop, dangle, selected, inherit, overlap, straight, widths, zoom 0.35/3) and probe.py, viewing every PNG. Not exercised: remote models, inferred relations' dashes, live dragging. Noted, not reported: the straight line type with an empty label puts middle marks on the average direction at a sharp bend; hovering a relation shows the `sb_h_double_arrow` cursor (vrelations.py:768); a label too close to its node overlaps the end stack with the label-near stack. A polygon first drawn at zoom 2 self-heals (not reported there; the Shape.draw() bug above is the same mechanism, caught by the view-core lens).

**Layouts (logic and visualization).** Read fully: layout.py, treeLayout.py, balloonLayout.py, animatedLayouts.py, viewLayouts.py, layoutPanel.py, layoutDialog.py, animationControls.py, developer/layout.rst, user/layouts.rst, user/animation.rst; followed into ViewDoList.do/adjustAgain, sngContext._Move, VObject.moveTo/adjustPos/drag handlers, VRelation.floating/reposition, relationTable, resetScrollRegion, the shipped layout figures. Skimmed test_treeLayout, test_layoutPanel, test_animationLoop. Ran deepdive/layouts/scen.py (scenarios A, B, B2, D, J, N, P, T, U), e1-e7 scripts with PNGs, and test_treeLayout, test_balloonLayout, test_gather, test_layoutDepth, test_animationLoop (77 OK). Checked fine: pins saved/restored across reload; a new instance placed into its tree by adjustAgain; adjustAgain mid-tween. Not run: the panel/dialog widgets beyond reading, FieldsLayout with context windows. Noted, not reported: the animation doc claims the drawing is slid so nothing goes off the top/left but forces() has no such code since d2a3aa4 (objects end at negative coordinates, the scroll region covers them); keep-arranged tree re-lays 2000 relations in ~2.5 s per drop; a tree relation's label dragged under keep-arranged is put straight back (by design).

**Containment and visibility (logic and visualization).** Read fully: viewContainment.py, viewVisibility.py, relationTable.py, expandDialog.py, user/contexts.rst, user/viewing.rst; followed into vobjects (hiding, collapse, panes, containmentOf, windowContents, carriedContents, expand*, drag handlers, disconnect), vrelations (floating, inWindow, placedLabel), viewCommands (_BumpIntruders, ViewDoList, _ContainCreated), sngContext (_Collapse, _Represent, _Visibility, _Expand), sngView (update, versions, categories, default hides), viewEditing (showAllModel, makeRelation), decorators.ContextFrame, reasoner.patternOf, pu abstractGraph/observer.notifyLater, git history of viewContainment.py. Skimmed test_containmentGeometry, test_eraseOthers, test_objectDrag, test_copyPaste, test_gather, test_expandDialog, test_viewSmoke. Ran under Xvfb: deepdive/containment/collapse_nested.py, collapse_dbg.py, erase_rules.py, drag_contain*.py, drag_stale.py, drag_out.py (also against 47e098b and 011f789 extracts), show_hidden_rels.py, gather_hidden.py, snlib.py, family.py (shipped family example rendered), scenes.py, dialog.py, counts.py, narrow.py. relationTable.py and expandDialog.py reviewed by reading only: no defects beyond edge cases (a self-loop counts only as outgoing in expand choices; an isa cycle among relation types drops them from the table tree). Not run: full suite.

**Input and editing (logic and visualization).** Read fully: viewInput.py, viewEditing.py, viewCommands.py, searchDialog.py, user/editing.rst, user/shortcuts.rst, concepts.rst (types and individuals), and the AttrEditor/HierarchicalAttrEditor parts of pu attributeEditor.py; followed into vobjects (bindings, drag/resize/menus/onEditAttributes/selected), vrelations (terminals, grabTerminal, chooseNewEndpoint), decorators (Selected, Highlight), layout (placeNode, freeRingSpot), sngView, sngContext, modelInterface (_Reconnect, _New_relation, _Remove, _Set_attribute, _Delete_attribute), model.parentProblem/nameMatcher, pu command.DoList, utils.eventEqual, platformSupport.shortcut. Skimmed ListEditor/ColorEditor, test_selectionBox, test_objectDrag, test_viewSmoke. Ran under Xvfb with real Tk events (harness.py drives a mapped SNGView with event_generate + warp): deepdive/input-editing/probe1-6.py and exp1-8 (elastic line, terminal drag with PNGs, selection feedback at zoom 1/0.5, drop nudging, costs on a 2116/3316-object view, cancelled naming, double-click, Find). Checked fine: elastic-line drop on an object, terminal click without drag, doRemove+undo, mtext round trip, ask() focus-out, no None entries in _db, Escape during a terminal drag. Not run: full suite.

**App, files and export (logic and visualization).** Read fully: guiApp.py, viewFiles.py, imageExport.py, directoryWindow.py, sourceWindow.py, plugins.py, hooks.py, files.rst, gettingStarted.rst, extending.rst; followed into sn/__init__.py (checkSaveModified, saveAtExit, copyExamples), sngView (construction, readModel, save, detachFromModel), viewEditing.doCopyImage/pictureObjects, viewReasoning._showInferred, model.py (dependents, unload, save), directory.py, progress.py, pu utils.py (fixURL, urlExists, canWriteUrl, menu-bar helpers, askYesNo/askUser/askViaTk/askViaTerminal, ownDialog/dialogOwner), pRef.py mode semantics, platformSupport.py (pdfToPNG, copyPNG), terminal.py, tooltip.py, plugins/pythonParser/hooks.py. Skimmed test_changeModel, test_imageExport, test_viewSmoke, test_reopen. Ran under Xvfb: deepdive/app-files-export/harness.py, exit_path.py, copy_image.py, startup_nothing.py, remote.py (local HTTP server), change_unsaved.py, super_model_view.py, export_family.py (shipped family example exported and screenshotted for side-by-side comparison; a black box turned out to be a tooltip toplevel from the Xvfb pointer, diag_black.py), export_cases.py at zoom 1.0 and 0.5, new_windows.py; test_sourceWindow and test_imageExport (11 OK). Checked and dismissed: menu separators accumulating on focus changes; mode='r' write-locking; remote models writable via Open Recent/restart. Noted, not reported: Save view on a web view raises a raw HTTPError 501 dialog. Not verified on macOS: the transient-window and dialog-parent behaviour (rests on the codebase's own documented rationale).

## What this deep dive did not cover

### 1. Files and behaviours nobody was assigned, or only skimmed / not run

**sn-opt, never assigned (by `find`, excluding tests):**
- Plugins, 3.4k lines, untouched except `pythonParser/hooks.py._parent` glanced at: `/home/user/sn-opt/plugins/XMLreader/{reader,schema,view,__init__}.py`, `/home/user/sn-opt/plugins/pythonParser/{parser,dialog,source,__init__}.py`. Their tests (test_xmlReader*, test_pythonSource/Update, test_pythonParserUpdate) were not run.
- View dialogs/widgets: `vnodes.py`, `chooseModelDialog.py`, `replaceModelDialog.py` (the replace-model path explicitly "not run"), `visibilityDialog.py`, `progress.py`, `reasoningToolbar.py` (outline only).
- Model: `names.py` (name matching/uniqueness), `modelPrefs.py`; `snAttribute.py` read only incidentally.
- `sn/examples/*.snm/.snv` were used as fixtures but not themselves reviewed for consistency with current code; `tools/` (makeBaseRules.py, docExamples/petsapp) and `packaging/` (makePyz, bundledPlugins, dmgSettings) unassigned.

**pu-opt, never assigned:** `utils.py` (2.6k lines; only named helpers followed), `terminal.py` (1.65k, routed-input only), `abstractGraph.py` and `dirtyable.py` (followed for specific methods only), `prefs.py` (outline), `platformSupport.py` (pdfToPNG/copyPNG only), `tooltip.py`, `folderServer.py`, `singleInstance.py`, `validatedList.py`, `actionDialog.py`, `choiceDialog.py`, `urlDialog.py`, `rtValuesDialog.py`, `errorReportingObject.py`, and the legacy serializers `serializeJSON.py`, `serializePlist.py`, `serializeXML.py`, `serializeXML2.py`, `x_persistenceXML.py` (only XML3 was read; whether old-format files still load was not checked).

**Assigned but skimmed / not run, per the coverage notes:**
- `clingoReasoner.lp` read, but no probe drove clingo on anything beyond the small test models.
- `commandParser.py`: findings noted but much of it (parser generation, help text) was followed only through makeParserFromFunc.
- `layoutPanel.py`, `layoutDialog.py`, `animationControls.py`: reading only; `FieldsLayout` with context windows not run.
- `relationTable.py`, `expandDialog.py`: reading only.
- `attributeEditor.py`: ListEditor/ColorEditor classes skimmed; the inferred-value UI not examined.
- `sourceWindow.py`, `directoryWindow.py`: no interactive probe beyond the unit tests.
- Undo across `mark_asserted` followed by a later `reason`; remote (http) super-models in the reasoner; `Save view` on a web view (raw HTTPError noted, not pursued).
- Full unittest suite: no reviewer ran it (each ran 11-77 tests of their own area).

### 2. Kinds of checking not done
- No interactive session: every GUI probe used synthesized Tk events under Xvfb; nothing checked real pointer timing, keyboard focus traversal, menu accelerators, or window-manager behaviour (transient windows, dialog parents, geometry restore).
- Linux only, Python 3.14 / Tk 9. No macOS or Windows paths (`platformSupport`, shortcuts, DMG/pyz packaging, clipboard image copy, `singleInstance`), no Tk 8.6, no older Python.
- Reasoner at scale: no large rule sets, no deep recursion/cycles in rules, no timing or grounding-blowup checks of the clingo program, no unsatisfiable-program handling.
- File-format compatibility: no round trip of `.snm/.snv` files written by earlier versions (XML/XML2/JSON/plist readers untouched), no corrupt/truncated-file handling, no concurrent-edit or lock-file behaviour, no non-ASCII paths.
- Plugins and hooks: plugin discovery (`plugin.toml`), failing plugin import, the XML reader on `library200.xml`, the Python parser on real source - none exercised.
- No memory/leak or long-session checks (observer detachment over many open/close cycles), no profiling beyond one 2000-relation view, no accessibility/high-DPI/font-scaling checks.
- Terminal UI: `textUserInterface.py` read, but no scripted session drove it end to end through `__main__`.

### 3. Three next checks, concretely
1. **Whole-suite baseline + plugin tests.** `cd /home/user/sn-opt && SN_NO_SAVE_PROMPT=1 PYTHONPATH=... xvfb-run -a python -m unittest discover -s test 2>&1 | tail -40`, then the same in `/home/user/pu-opt`. Confirms only `test_canChange` fails and gives the XMLreader/pythonParser tests their first run of this dive.
2. **Old-file round trip.** Take `family.snm`/`.snv` and `animals.*` from the oldest tag reachable in `git -C /home/user/sn-opt log --all -- src/sn/examples`, plus the `pu-opt/test/temp*.xml/json` fixtures; open each with the current code, save, reopen, and diff the attribute set and object count (script under `/tmp/claude-0/-home-user/9364412b-b609-5b4f-a68a-4170282c7fc4/scratchpad/deepdive/compat/`). Targets the untouched serializers and `names.py`.
3. **Reasoner at scale.** Build on `scratchpad/timing.py`: the 2000-relation family model plus ~20 recursive rules (ancestor, sibling, in-law with negation), run `reason` three times with edits between, time it, and verify `clear_reasoning` + undo returns `inferredObjects` to empty and the file to its pre-reason bytes. Targets clingo grounding cost and the inferred-object lifecycle no probe covered.
