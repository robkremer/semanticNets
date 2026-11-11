# Relation marks: overnight report

Jerald — this is what I did after you went to bed, what I found, and the decisions I didn't want to make for you or Rob. Nothing was pushed or posted: every change is a commit in a local worktree, exported as a patch file (paths at the end). The PRs on Rob's repos are as you left them.

## 1. Where things stand

- **Rob's two remarks**, both resolved:
  - *"Yours is a relation TYPE, mine an INDIVIDUAL."* The example (and the shared test fixture) parented the relation straight on the system type `relation`, which is how types are parented. Rendered Rob's way — a `has-pet` type carrying the look, Bob → golden retriever an individual of it, look inherited or own — the geometry is identical on `main` and with #34. No code change needed for the connected case.
  - *"Worse with floating terminals."* Real, and separate from #34: a floating end's stub was clipped to the invisible label box, leaving a hole with the `||>` pointing into it. Fixed in `VRelation._styleEnds()` (stubs run through an empty label to its centre), with a test modelled as a relation *type* with both ends floating. **This needs to reach the `claude/line-through-empty-label` branch on your fork, which this session can't push to** — patch `0001` below.
- **The eight PRs merge cleanly together** except one docstring-only conflict between #33 (middle marks beside the label) and #34 (line through an empty label) in `connectors.py` — whichever merges second needs a two-paragraph resolution. Resolution included in the patches.
- **Items 4 and 5 of the design review** (the only ones not in a PR) are done: a test that marks zoom with the view, and the docs to match. There is no release-notes file in the repo for the `vis/label = ""` note — see §4.

## 2. Speed

### 2.1 Re-timing (item 6's promised follow-up)

Same method as the other session's: the family example, reasoned, scaled to 119 nodes / 1997 relations, hidden Tk window under Xvfb, medians of 5. Absolute numbers are ~3× the other session's (this container is slower); the ratios are what matter.

| What a redraw does (ms, median) | `main` | PR stack (#17–19, #31–35 + stub fix) | + tonight's changes |
|---|---|---|---|
| Drag tick: hub node (127 relations) | 316 | 312 | **180** (1.7× faster than the stack) |
| Drag tick: all 119 nodes | 6503 | 5638 | **3033** (1.9×) |
| Tween step: all 119 nodes | 5157 | 5918 | **2416** (2.4×) |
| `_moveAll`: all 119 nodes | 3418 | 3577 | **1896** (1.9×) |
| Redraw all 1997 relations | 1782 | 1560 | **1056** (1.5×) |

_(All three columns from one uncontended run, one after the other, at the end of the night; raw log at `…/scratchpad/timing-final.log`. An earlier run beside a test suite gave the same ratios.)_

**`main` vs the stack is within run-to-run noise on every row.** pythonUtils #19 (remembered item types, quicker `paramAtDistance()`) recovered the 10–25% the marks had cost. So the stack is no slower than `main`; the remaining time is elsewhere, which the profile shows.

### 2.2 Where a redraw's time goes (profile of the stack)

Drag tick on the hub node (127 relations), shares of the tick:

| Share | What | Why |
|---|---|---|
| ~28% | `VRelation.placedLabel()` → `containmentHomes()` | Rebuilds, for *every relation on every tick*, the maps of what each context window (the example's rules) contains — 82k `isa()` calls and 30k inherited attribute lookups per tick. |
| ~30% | Redrawing the label (`VObject.draw()`) | Expanding the label template at every draw (`$name` is an inherited attribute lookup at 0.09 ms), `font.metrics()` round-trips (0.67 ms each), the shape asking the model which options it has (an inheritance walk per option). |
| ~23% | The connector (`drawSmoothConnector()`) | `_findBoundaryParam()` always bisects 24 steps × `pointInPoly()` (105k calls); Tk `coords`/`itemconfigure` per item. |

Full redraw of all relations: the same items in different proportions; a third of it is model attribute lookups through the types.

### 2.3 What I changed (semanticNets patch `0005`, commit `a187b46`)

All remembered until the view or model changes — `SNGView.structureChanged()`, which every model notification already bumps — so nothing goes stale on an edit:

1. `SNGView._containmentMaps()`: the containment/variable-use maps `containmentHomes()` builds, cached per structure version.
2. `VObject.labelText()`: the expanded label, memoised — except templates with a hook call `$(module:function)`, which the docs promise a call every time.
3. `Shape.updateKwargs()`: which shape options the object has, remembered.
4. `connectors._findBoundaryParam()`: stops when the bracketing points are within 0.25 view units (9–13 steps for ordinary curves) instead of always 24.
5. `decorators._lineSpace()`: a font's line spacing asked of Tk once.

Also: `_clipToEdgeStraight()` works the shape's outline out once per clip (patch `0002`); connector deletions go through `lineMarks.deleteItem()` (`0004`); the constraint marker's state is remembered too, and a renamed type's children are redrawn (`0006`, see §4.4); and on the pythonUtils side, `lineMarks` skips the per-frame `itemconfigure` of a mark item whose options haven't changed (pythonUtils patch `0001`).

Tests: all 241 view tests and the full suite pass (only the pre-existing `test_canChange`, a root-user artefact); pythonUtils 106/106. The final timing is in §5.

## 3. Visual review

I rendered every mark kind and the ER/UML stacks (gallery at `…/scratchpad/gallery-z1.png`, `gallery-z2.png`), smooth and straight, with and without label text, width 1 and 3, a self-loop, an inherited (faded) end and a floating type, at zoom 1 and 2. **No geometry defects**: arrow necks, hollow ring and diamond, crow's foot toes, bar spacing, line cut-backs all right; everything scales with zoom. One finding was a documentation gap, now fixed: at the *source* end an ER foot must be written `{` (toes toward the source) or `crow` — the docs only showed `terminator4` examples.

## 4. Decisions for you / Rob (with my recommendation)

1. **Getting the stub fix onto #34.** Patch `0001` must land on the fork's `claude/line-through-empty-label`. Either the other session applies it (it's idle, waiting on you) or you start a session with your forks as sources. _Recommend: the latter — and give that session the `0002–0006` patches too, so they can become PRs._

2. **How to ship tonight's speed work.** The five `sn-opt` commits sit on top of *all five* semanticNets branches merged (they touch `connectors.py`, `vrelations.py`, `vobjects.py`, `decorators.py`, `shapes.py`, `viewContainment.py`). Two options: (a) one more PR after #31–#35 merge, or (b) rebase onto `main` now (most of it doesn't depend on the marks work — only the test file does). _Recommend (a): it's the honest dependency, and it keeps the PRs reviewable. Two PRs: 0002+0004+0005 ("redraw speed", with pythonUtils 0001 alongside), and 0003+0006 ("docs, tests, the `$type` fix"); 0006 applies after 0005._

3. **The caches' invalidation key.** Everything new is remembered until `SNGView.structureChanged()` bumps, which happens on *every* model notification the view receives (I also bump it at the top of `VObject.update()`, since objects observe the model independently of the view and could otherwise redraw before the bump). That is deliberately coarse: any model change recomputes every label once on its next draw. It is correct for anything that reaches the view as a notification. _What it would miss: a model edited by code that bypasses notifications, or a label hook (`$(module:function)`) whose result depends on something outside the model — hooks are excluded from the memo for that reason, as the docs promise them a call each time. Rob should confirm there's no notification-free path he relies on._

4. **A pre-existing bug the new test caught**: renaming a *type* never redrew instances whose label shows `$type` (they're only notified for attributes they inherit). Fixed in 0006 for direct children. _Question: should it go deeper — `$type` only shows parents, so children suffice — unless Rob wants subtypes' subtypes redrawn for inherited names too (those already get "mod inherited attribute")._

5. **Release notes.** Item 5 asked for a line saying `vis/label = ""` now means no label. There is no release-notes/changelog file in either repo (only `README.md` and the Sphinx user docs). The behaviour is documented in `viewing.rst` and `LABEL_NOTE`. _Recommend: Rob decides whether he wants a `CHANGES.md`; I didn't invent one._

6. **The straight connector during drags.** `connectors.py`'s own docstring says the straight variant exists so a caller can use it "every frame of a drag/animation" and switch to smooth when settled — but `VRelation.draw()` picks by `vis/lineType` only; the `fast` flag never selects it. Wiring it would cut a drag tick further (the curve clipping is ~30% of what's left), at the cost of lines visibly snapping straight→curved on release. _Design call for Rob; I didn't do it._

7. **ER notation at the source end.** `}`/`{` mean "toes toward the destination/source", so ER "one-or-many" at the *source* is `{|`, not `|}` (which draws toes pointing away from the node). The docs now show it. _Alternative Rob might prefer: make `crow` (outward) the recommended spelling in the docs, or make `}`/`{` mean toward/away from the end they're at. I left the semantics alone._

8. **What's left on the profile, not done** (diminishing returns; each ~5–8% of a redraw): a node's outline is recomputed for each relation that clips to it in a tick (`_insideTest` → `shape.points()`); `awayFromWindows()`/`belongsIn()` per floating label per tick; `_applyHidden()` → `shouldHide()` per draw; `_faded()` makes two `winfo_rgb` round-trips per faded end per draw; `recolorMarks()` asks `gettags`+`type` per item. All cacheable on the same key if wanted.

9. **PR descriptions on Rob's repos.** #18, #19 and #35 target `main` and therefore show their parent PR's commits in their diff until the parent merges; the descriptions say so. If Rob would rather see clean diffs, the bases can be changed to the parent branches — but those branches would have to exist on *his* repo, which this session couldn't push.

## 5. Results

- **Speed** (table in §2.1): against the PR stack, a drag tick on a busy node 1.7× faster, moving every node 1.9–2.4× faster, a full redraw of 2000 relations 1.5× faster. The remaining time is roughly half connector geometry/Tk, half label drawing; §4.8 lists what's left and what each would be worth.
- **Tests:** semanticNets full suite on the optimised tree 473 run, only the pre-existing `test_canChange` (a root-user file-permission check, fails on `main` here too); `test_view` 241/241 after the last commit; pythonUtils 106/106 with the options memo. The stub fix alone: 466 run, same single failure.
- **Visual:** no geometry defects in the gallery (`…/scratchpad/gallery-z1.png`, `gallery-z2.png`); marks scale with zoom (now pinned by a test).
- **Profiles**, if anyone wants to look further: `…/scratchpad/profile-stack.log` (before) and `profile-opt.log` (after); the scripts `timing.py`, `snprofile.py`, `gallery.py` are beside them. `…/scratchpad` is `/tmp/claude-0/-home-user/9364412b-b609-5b4f-a68a-4170282c7fc4/scratchpad`.

## 6. Patches

All in `/home/user/patches/` with a `README.md` giving the apply order; `git am <file>`.

| | applies on | what |
|---|---|---|
| `semanticNets/0001` | the fork's `claude/line-through-empty-label` (PR #34) | stubs through an empty label — **Rob's floating-terminals case; push this first** |
| `semanticNets/0002` | the five branches merged | `_clipToEdgeStraight()` outline worked out once |
| `semanticNets/0003` | " | marks-zoom test; docs (item 4, `{|` at the source, stubs) |
| `semanticNets/0004` | " | connector deletions through `lineMarks.deleteItem()` |
| `semanticNets/0005` | " | the redraw hot spots (§2.3) |
| `semanticNets/0006` | after 0005 | `$type` redraw on a type's rename; constraint marker memo; version bump before a notified object redraws; fixture as an individual of a type; label-follows-model test |
| `semanticNets/merge-resolution-33-34-connectors.diff` | — | the one conflict in the stack, as I resolved it |
| `pythonUtils/0001` | `claude/marks-redraw-speed` (PR #19) | skip unchanged `itemconfigure` of mark items |

Worktrees with the commits, if you'd rather push from here in a session that can: `/home/user/sn-fix` (0001), `/home/user/sn-opt` (branch `claude/opt`: the stack + 0002–0006), `/home/user/pu-opt` (`claude/opt`: #19's branch + pythonUtils 0001). This session's GitHub access reaches only Rob's repos, and pushing branches there was refused by the harness, so none of it has left this container.
