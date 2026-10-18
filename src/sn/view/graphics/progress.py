'''
Progress reports for long jobs -- reading a model or view, drawing a view --
shown by whatever's listening (the model directory's progress bar: see
*sn.view.graphics.directoryWindow*), or nowhere.

A job is *begin()*, *step()* (as often as is convenient: reports are passed on
at most every *INTERVAL* seconds), *end()*; or *task()*, a context for the same.
Jobs nest (eg: reading a view reads its model): the innermost is shown.

Created on Oct 12, 2026

.. codeauthor:: Rob Kremer <robkremer@me.com>
'''
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
from __future__ import annotations
import time
from contextlib import contextmanager
from typing import Callable, Iterator, Optional

INTERVAL = 0.1
"The shortest time (seconds) between reports of the same job's progress."

Listener = Callable[[Optional[str], int, Optional[int]], None]
'''Told (label, done, total) as a job goes -- total None if it isn't known --
and (None, 0, None) when there's no job any more.'''

listener:Listener|None = None
"Who's told: see *Listener*."

_jobs:list[list] = [] # [label, done, total, when last reported]

def begin(label:str, total:int|None=None) -> None:
  '''
  :param label: What's being done, eg: 'Reading "family.snm"'.
  :param total: How many steps there'll be, if that's known.
  '''
  _jobs.append([label, 0, total, 0.0])
  _report(force=True)

def step(done:int, total:int|None=None) -> None:
  '''
  :param done: How many steps of the current job are done.
  :param total: How many there'll be, if that's now known (or has changed).
  '''
  if not _jobs:
    return
  job = _jobs[-1]
  job[1] = done
  if total is not None:
    job[2] = total
  _report()

def end(count:int=1) -> None:
  '''
  The current job is done.

  :param count: How many jobs are done: the current one, and those it's in
    (but not the one they're in): reported once.
  '''
  for _ in range(count):
    if _jobs:
      _jobs.pop()
  _report(force=True)

@contextmanager
def task(label:str, total:int|None=None) -> Iterator[None]:
  '''
  A job (see *begin()*) for the duration of the context.
  '''
  begin(label, total)
  try:
    yield
  finally:
    end()

def busy() -> bool:
  ":returns: Whether there's a job under way."
  return bool(_jobs)

def _report(force:bool=False) -> None:
  if listener is None:
    return
  if not _jobs:
    listener(None, 0, None)
    return
  job = _jobs[-1]
  now = time.monotonic()
  if not force and now - job[3] < INTERVAL:
    return
  job[3] = now
  try:
    listener(job[0], job[1], job[2])
  except Exception:
    pass # (a progress bar mustn't stop the work)
