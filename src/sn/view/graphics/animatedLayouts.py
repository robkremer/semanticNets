#################################################################################
# (c) Copyright 2024-2025, Rob Kremer, MIT open source license.                 #
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
from sn.model.model import Model
from traceback import format_exc
from concurrent.futures.thread import ThreadPoolExecutor
from concurrent.futures._base import Future
from concurrent.futures.process import ProcessPoolExecutor
import sn

'''
Created on Nov 19, 2025

.. codeauthor:: Rob Kremer <robkremer@me.com>

'''

import logging
import weakref
from typing import Optional, Generator, override, Tuple
from time import monotonic_ns
from math import sqrt
from random import random
from threading import Thread

from sn.view.graphics.vobjects import VObject
from sn.view.graphics.vrelations import VRelation
from sn.view.graphics.view import SNView
import fieldLayout

logger:sn.SNLogger = sn.getLogger(__name__)

class WeakrefError(Exception):
  'Specific error for FieldsLayout to signal the destruction of the owner SNView object'
  pass

def isEligible(obj:VObject):
  "ignore floating relation instances"
  #return not (isinstance(obj, VRelation) and obj.modelObject.isIndividual() and obj.floating()) # ignore floating relation instances
  return obj.modelObject.isType() or not isinstance(obj, VRelation)

class FieldsLayout():
  '''
  A class for animating a node-repulisive and relation-attraction field algorithm.
  
  The layout calculation can be very long, so the algorithm is designed to run
  for a certain time, queue itself for the a future time, and then give back
  control to *mainloop*.
  
  Use:
  
    .. code-block:: python
    
        f = FieldsLayout(tgview, ...)
        f(node) # starts algorithm for on a specific node, *node*
        f() # continues the algorithm for all nodes in the host tgview (including *node*)
  '''
  def __init__(self, view:SNView, 
               e:float=1000.0, gMaxDist:float=200.0, 
               k:float=0.005,  kMinDist:float=0.0, 
               displacementSensitivity=5.0, maxDisplacement=10.0, 
               dtime=100):
    assert isinstance(view, SNView)
    self.e:float        = float(e)
    'The "gravitational constant": repulsive strength of nodes (and relation types) to one another' 
    self.gMaxDist:float = float(gMaxDist)
    'The maximum 2d distance that e takes effect.'
    self.k:float        = float(k) 
    'The "spring constant" (spring stiffness): The attractive force of a relation'
    self.kMinDist:float = float(kMinDist)
    'The minimum 2d distance that *k* takes effect.'
    self.displacementSensitivity:float = float(displacementSensitivity)
    'The higher the number, the faster the algorithm comes to convergence'
    self.maxDisplacement:float = float(maxDisplacement)
    'The maximum x- or y-direction displacement that can happen in any once cycle. Prevents wild displacements.'
    self.dtime:int      = int(dtime)
    'The time (in ms) that the algorithm "rests" between activation.'
    self.dtime2:int     = int(dtime*4)
    'The max time (approximate) that the algorithm with run for before giving up control back to *mainloop*.'
    
    self.relationWeights:dict = {"*": 0.5}
    self._killFlag = False # the global killflag
    #self.killFlags:set = set() # ids, killflags for individual VObjects
    self.active = False
    'Indicates the algorithm is running.'
    self._generator = None
    self._lastRes = None
    self._targets = dict() # dict of id:node to update; empty dict means "all of them"
    
    self._view = weakref.ref(view)
    #view.fieldsLayoutObj = self
    
  @property
  def view(self) -> SNView:
    ret = self._view()
    if ret is None:
      raise WeakrefError()
    return ret
  
  def __call__(self, obj:Optional[VObject]=None, autoOff:bool=True):
    '''
    :param obj: [Optional] If given, indicates the given object is the only object
      that should be moved
    :param autoOff [Optional] Iff True, and the animation reaches convergence (nothing moved
      in some cycle), then terminate the animation.
      
    Do one cycle of calculating the animation and queue self for the next animation.
    '''
    if isinstance(obj, VRelation) and obj.modelObject.isIndividual() and obj.floating(): # ignore floating relation instances
      return

    if obj is not None:
      if self.active and (len(self._targets)==0 or id(obj) in self._targets): # No sense dealing with an object if we're already dealing with them all
        return
      elif self.active and len(self._targets) > 0: # we need to explicitly deal with this node
        self._targets[id(obj)] = obj
        return
      elif not self.active:
        self._targets[id(obj)] = obj
    else: # we're being asked to deal with all nodes
      self._targets.clear()
    if not self.active:
      self._killFlag = False
      self._call(autoOff=autoOff) #TODO: need to deal with autooff logic
    
  def _call(self, autoOff:bool):
    '''
    :param autoOff: iff True, and the animation reaches convergence (nothing moved
      in some cycle), then terminate the animation.
      
    Do one cycle of calculating the animation and queue self for the next animation.
    '''
    moved = False
    try:
      if not self.active:
        self.active = True
        logger.info("FieldsLayout animation on")
      if self._generator is None:
        self._generator:Generator = self.updateAll()
      assert isinstance(self._generator, Generator)
      try:
        res = next(self._generator)
        self._lastRes = res
        #logger.info("interrupt")
      except StopIteration:
        res = self._lastRes
        self._generator = None
        #logger.info("end cycle")
      if res is None:
        res = True
      if not res:
        moved = True
    except WeakrefError: # The view has gone away, so just end.
      logger.warning("FieldsLayout detected destroyed view.")
      #self._removeKillflag(obj)
      return
    except Exception:
      logger.exception("Exception during FieldsLayout processing.")
    
    # if not moved:
    #   logger.info("convergence!")
    if (moved or not autoOff) and not self._killFlag:
      self.view.canvas.winfo_toplevel().after(self.dtime, 
                                              lambda autoOff=autoOff: self._call(autoOff=autoOff))
    else:
      logger.info("FieldsLayout animation off")
      self._targets.clear()
      self.active = False
      
  def kill(self, obj:Optional[VObject]=None):
    if obj is None:
      self._killFlag = True
    else:
      self.killFlags.add(id(obj))
      
  # def _removeKillflags(self):#, obj:Optional[VObject]=None) -> bool:
  #   '''
  #   Removes any associated killflag, returns *True* iff it removed one.
  #   '''
  #   if len(self._targets)==0 and self._killFlag: # skip repeat if the killflag is set
  #     self._killFlag = False
  #     self.active = False
  #     return True
  #   if len(self._targets)>0:
  #     self.killFlags.clear()
  #     return True
  #   return False
      
  def setRelationWeight(self, relationName:str, weight:float=0.5):
    '''
    Give the named relation a weight between 0.0 and 1.0. You can use "*" to
    assign a default weight. Thus, setRelationWeight('*', 0.0) and 
    setRelationWeight('isa', 1.0) will only make use of isa relations.
    '''
    weight = float(weight)
    if weight < 0.0:  weight = 0.0
    if weight > 1.0:  weight = 1.0
    self.relationWeights[relationName] = weight 
    
  def updateAll(self) -> bool:
    '''
    Figure out the force and all the nodes and move them accordingly.
    Returns *True* iff at least one of the nodes moved.
    '''
    #logger.info("FieldsLayout updating")
    ret = False
    timeout = monotonic_ns() + 1000000
    changes:list[tuple[VObject, tuple[float, float]]] = []
    #for node in (self.view.makeGenerator(lambda n: not(isinstance(n, VRelation) and n.modelObject.isIndividual())) if len(self._targets)==0 else self._targets.values()):
    for node in self.view.makeGenerator(lambda n: isEligible(n)):
      f = self._calculateForce(node)
      if abs(f[0]) + abs(f[1]) > self.displacementSensitivity:
        changes.append((node, (f[0],f[1])))
        ret = True
      if monotonic_ns() > timeout:
        #print("timeout")
        yield None
        
    for n, offset in changes:
      n.moveBy(offset[0], offset[1], adjustPos=False)

    return ret
        
  # def update(self, node:VObject) -> bool:
  #   '''
  #   Figure out the force on *node* and move it accordingly.
  #   Returns *True* iff we actually moved the node
  #   '''
  #   f = self._calculateForce(node)
  #   if abs(f[0]) + abs(f[1]) > 1.0:
  #     node.moveBy(f[0], f[1], adjustPos=False)
  #     return True
  #   return False
  
  def _calculateForce(self, node:VObject) -> tuple[float, float]:
    fg = self._gravity(node)
    fk = self._elasticity(node)
    ret = fg[0]+fk[0], fg[1]+fk[1]
    ret = ret[0] if abs(ret[0]) < self.maxDisplacement else (self.maxDisplacement if ret[0] >= 0 else -self.maxDisplacement), \
          ret[1] if abs(ret[1]) < self.maxDisplacement else (self.maxDisplacement if ret[1] >= 0 else -self.maxDisplacement)
    return ret
      
  def _gravity(self, node:VObject) -> tuple[float, float]:
    pn = node.centerPt()
    forceX = 0.0
    forceY = 0.0
    #for other in self.view.makeGenerator(lambda n: not(isinstance(n, VRelation) and n.modelObject.isIndividual())):
    for other in self.view.makeGenerator(isEligible):
      if node is other:
        continue
      po = other.centerPt()
      dx = float(pn[0]-po[0]) # x distance, signed
      dy = float(pn[1]-po[1]) # y distance, signed
      if dx == 0 and dy == 0: #two objects exactly coincide, don't divide by zero
        return(random()*self.e, random()*self.e)
      r = sqrt(dx*dx + dy*dy) # distance between to two
      if r > self.gMaxDist: #ignore things too far away
        continue
      gf = self.e/float(r*r) # force of gravity 1/x^2
      #gf = self.e/float(r*r) # force of gravity 1/x
      fx = dx * gf
      fy = dy * gf
      forceX += fx
      forceY += fy
    #print(forceX, forceY)
    return forceX, forceY
      
  def _elasticity(self, node:VObject) -> tuple[float, float]:
    def doCalc(pn, po, weight):
      dx = float(pn[0]-po[0]) # x distance
      dy = float(pn[1]-po[1]) # y distance
      if dx == 0 and dy == 0: #two objects exactly coincide
        return(random()*self.k, random()*self.k)
      r = sqrt(dx*dx + dy*dy) # distance between to two
      if r <= self.kMinDist: # ignore things too close in already
        return 0.0, 0.0
      r -= self.kMinDist
      kf = r * self.k
      fx = -dx * kf
      fy = -dy * kf
      return fx * weight, fy * weight

    pn = node.centerPt()
    forceX = 0.0
    forceY = 0.0
    defaultWeight = float(self.relationWeights.get("*", 0.5)) #TODO: could easily optimize by moving this up
    # scan the relations
    for rel in node.relations:
      weight = self.relationWeights.get(rel.modelObject.name, defaultWeight)
      if weight <= 0.0:
        continue
      try:
        if rel.modelObject.isType():
          other:VObject = rel 
        else:
          other = rel.roles["src"][0].vobject()
          if node is other:
            other = rel.roles["dst"][0].vobject()
          if node is other: #self-reference, ignore it
            continue 
        if other.modelObject.isIndividual() and isinstance(other,VRelation):
          continue # ignore relations to relation instances as they float, so we can't know where they go
      except Exception as ex:
        logger.warning(f"_elasticity(): couldn't get other end of relations for object {node.modelObject.name}: {str(ex)}")
        continue              
      po = other.centerPt()
      f = doCalc(pn, po, weight)
      forceX += f[0]
      forceY += f[1]
    # scan the roles (if this is a relation)
    if isinstance(node, VRelation) and (weight := self.relationWeights.get(node.modelObject.name, defaultWeight) > 0.0):
      for other in [x[0].vobject() for x in node.roles.values()]:
        po = other.centerPt()
        f = doCalc(pn, po, weight)
        forceX += f[0]
        forceY += f[1]
      
    return forceX, forceY

      
class FieldsLayout_threaded(FieldsLayout):      
  '''
  Run in *mainloop*.
  '''
  @override
  def _call(self, autoOff:bool):
    '''
    Runs *self.updateAll()* in a thread.
    '''
    if not self.active:
      self.active = True
      logger.info("FieldsLayout animation on")
      
    thread = Thread(target=FieldsLayout_threaded.updateAll, args=(self, autoOff), daemon=True)
    thread.start()
            
  @override
  def updateAll(self, autoOff:bool) -> bool:
    '''
    Run in a thread.
    
    In a thread, figure out the force and all the nodes, then call *commitChanges()*
    on the *mainloop* to updated the GUI.
    '''
    try:
      changes:list[tuple[VObject, tuple[float, float]]] = []
      #for node in (self.view.makeGenerator(lambda n: not(isinstance(n, VRelation) and n.modelObject.isIndividual())) if len(self._targets)==0 else self._targets.values()):
      for node in self.view.makeGenerator(lambda n: isEligible(n)):
        f = self._calculateForce(node)
        if abs(f[0]) + abs(f[1]) > self.displacementSensitivity:
          changes.append((node, (f[0],f[1])))
    except WeakrefError: # The view has gone away, so just end.
      return
    except:
      trace = format_exc()
      self.view.canvas.winfo_toplevel().after(0, lambda msg=str(trace): logger.exception(f"Exception during FieldsLayout processing: {msg}."))
        
    self.view.canvas.winfo_toplevel().after(0, lambda changes=changes, ao=autoOff: self._commitChanges(changes=changes, autoOff=ao))
        

  def _commitChanges(self, changes, autoOff):
    '''
    Run in *mainloop*.
    
    '''  
    for n, offset in changes:
      n.moveBy(offset[0], offset[1], adjustPos=False)
      
    moved = len(changes) > 0
    
    if (moved or not autoOff) and not self._killFlag:
      self.view.canvas.winfo_toplevel().after(self.dtime, 
                                              lambda autoOff=autoOff: self._call(autoOff=autoOff))
    else:
      logger.info("FieldsLayout animation off")
      self._targets.clear()
      self.active = False

from fieldLayout import UpdateRec, Graph, Point, ID, Op, BNode, \
    OP_NEW_NODE, OP_NEW_REL, OP_DEL_NODE, OP_DEL_REL, OP_MOD_POS, OP_MOD_WEIGHT, \
    FIELD_LAYOUT_PARAMS
    
  
# class BonesGraph:
#
#   def __init__(self, relationWeights:dict[str,float]={"*":0.5}):
#     self.nodes:dict[id, BNode] = dict()
#     self.relationWeights:dict[str, float] = relationWeights
#     self.defaultWeight = self.relationWeights["*"] if "*" in self.relationWeights else 0.5
    
def makeBonesGraph(view:SNView, defaultWeight:float=0.5, relationWeights:dict[str,float]=dict()):
  
  nodes:dict[id, BNode] = dict()
  
  def addNode(vnode:VObject) -> ID:
    if not isEligible(vnode):
      return None
    id_ = vnode._id
    if id_ in nodes:
      return id_
    bnode = BNode(id_, vnode.centerPt())
    nodes[id_] = bnode
    # scan the relations
    for rel in vnode.relations:
      weight = relationWeights.get(rel.modelObject.name, defaultWeight)
      if weight <= 0.0:
        continue
      try:
        if rel.modelObject.isType():
          other:VObject = rel
        else:
          other:VObject = rel.roles["src"][0].vobject()
          if vnode is other:
            other = rel.roles["dst"][0].vobject()
          if vnode is other: #self-reference, ignore it
            continue 
        if other.modelObject.isIndividual() and isinstance(other,VRelation):
          continue # ignore relations to relation instances as they float, so we can't know where they go
      except:
        logger.warning(f"BonesGraph.addNode(): couldn't get other end of relations for object {vnode.modelObject.name}")
        continue
      o = addNode(other)
      if o is not None:
        bnode.rels.append((o, weight))
    # scan the roles (if this is a relation)
    if isinstance(vnode, VRelation) and (weight := relationWeights.get(vnode.modelObject.name, defaultWeight) > 0.0):
      for other in [x[0].vobject() for x in vnode.roles.values()]:
        if other is None: continue
        o = addNode(other)
        if o is not None:
          bnode.rels.append((o, weight))
    return id_ 
  
  for obj in view._objects.values():
    addNode(obj)
  
  return nodes
    
    
  

class FieldsLayout_threadPool(FieldsLayout):
  
  def __init__(self, view:SNView, 
               e:float=1000.0, gMaxDist:float=200.0, 
               k:float=0.005,  kMinDist:float=0.0, 
               displacementSensitivity=5.0, maxDisplacement=10.0, 
               dtime=100,
               autoOff=False):
    assert isinstance(view, SNView)
    self.e:float        = float(e)
    'The "gravitational constant": repulsive strength of nodes (and relation types) to one another' 
    self.gMaxDist:float = float(gMaxDist)
    'The maximum 2d distance that e takes effect.'
    self.k:float        = float(k) 
    'The "spring constant" (spring stiffness): The attractive force of a relation'
    self.kMinDist:float = float(kMinDist)
    'The minimum 2d distance that *k* takes effect.'
    self.displacementSensitivity:float = float(displacementSensitivity)
    'The higher the number, the faster the algorithm comes to convergence'
    self.maxDisplacement:float = float(maxDisplacement)
    'The maximum x- or y-direction displacement that can happen in any once cycle. Prevents wild displacements.'
    self.dtime:int      = int(dtime)
    'The time (in ms) that the algorithm "rests" between activation.'
    self.dtime2:int     = int(dtime*4)
    'The max time (approximate) that the algorithm with run for before giving up control back to *mainloop*.'
    self.autoOff:bool   = autoOff
    'Iff true, the automation should be turned off when the layout converges.'
    
    self.active = False
    self._view = weakref.ref(view)
    self._killFlag = False # the global killflag
    #self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="fields", initializer=fieldLayout.init)
    self.pool = ProcessPoolExecutor(max_workers=1, initializer=fieldLayout.init)
    print("ProcessPoolExecutor initialized")
    self.waiting:bool = False # used in self._resubmit to handle a suppressLocalLayout state

  @override
  def __call__(self, obj:Optional[VObject]=None, autoOff:bool=True):
    if obj is not None: #TODO fix this temporary patch
      return
    self.active = True
    self.waiting = False
    graph = makeBonesGraph(self.view)
    print(f"Animation on ({len(graph)})")
    self.job = self.pool.submit(fieldLayout.call, "newFrame", 
                                graph=graph, 
                                obj=obj._id if obj is not None else None)
    self.job.add_done_callback(lambda future: self.view.after(self._updateFromBones, future))

  def newNode(self, id:ID, pos:Point):
    self.pool.submit(fieldLayout.worker.newNode, id=id, pos=pos)
                                       
  def newRel(self, id1:ID, id2:ID, weight:float):
    self.pool.submit(fieldLayout.worker.newRel, id1=id1, id2=id2, weight=weight)
                                       
  def delNode(self, id:ID):
    self.pool.submit(fieldLayout.worker.delNode, id=id)
                                       
  def delRel(self, id1:ID, id2:ID):
    self.pool.submit(fieldLayout.worker.delRel, id1=id1, id2=id2)
                                       
  def updatePos(self, id:ID, pos:Point):
    self.pool.submit(fieldLayout.worker.updatePos, id=id, pos=pos)
                                       
  def updateWeight(self, id1:ID, id2:ID, weight:float):
    self.pool.submit(fieldLayout.worker.updateWeight, id1=id1, id2=id2, weight=weight)
    
  def updateSettings(self, **kwargs) -> Future: # A future object
    '''
    :return: A *future* object that can safely be ignored, but refers to remote
      worker's parameters table if *kwargs* is empty.
    '''
    print("FieldsLayout_threadPool.updateSettings()")
    if len(kwargs) == 0:
      job = self.pool.submit(fieldLayout.worker.updateSettings)
      return job # a future object
    for k,v in kwargs.items():
      assert k in FIELD_LAYOUT_PARAMS
    print(f'updating settings {str(kwargs)}')
    try:
      job = self.pool.submit(fieldLayout.worker.updateSettings, **kwargs)
      print("done submit")
    except:
      logger.exception("FieldsLayout_threadPool.updateSettings():")
    return job
    
                                       
  def _updateFromBones(self, future:Future)->bool:
    '''
    This is the callback from the *ThreadPoolExecutor* after the layout job has
    completed. Schedule the result into *tkinter's* mainloop (*self._drawFromBones()*).
    
    Calls *self._drawFromBones()* (ono the mainloop).
    '''
    try:
      bones = future.result(timeout=2)
      self.view.canvas.winfo_toplevel().after(100, lambda bones=bones: self._drawFromBones(bones))
    except:
      logger.exception("Animation raised an exception.")
    
  def _drawFromBones(self, bones:dict[ID, Point]):
    '''
    Move the *VObjects* in the view from the data in the *dict[ID, Point]*. This 
    needs to be executed in tk's mainloop.
     
    Calls *self._resubmit() if necessary.
    '''
    print(f"drawing from bones ({len(bones)})")
    for k,v in bones.items():
      self.view[k].moveTo(v[0], v[1], adjustPos=False)
    # if we're an ongoing animation resubmit
    if (len(bones)>0 or not self.autoOff) and not self._killFlag:
      self._resubmit()
    else:
      self.active = False
      self._killFlag = False
      print("Animation off")
    
  def _resubmit(self):
    '''
    Checks waiting state and calls itself on the mainloop (delayed) if we're waiting.
    Otherwise submits to the worker in other interpreter with a callback to 
    *self.updateFromBones()*.
    '''
    if self.waiting: # we are waiting for suppressLayout to clear
      if self.view.suppressLocalLayout(): # ...and we're still waiting
        print("waiting...")
        self.view.canvas.winfo_toplevel().after(500, self._resubmit)
      else: # we were waiting, but the suppresslayout has cleared: need to reset the graph
        print("waiting off")
        self.waiting = False
        self()
    elif self.view.suppressLocalLayout():
      print("start waiting")
      self.waiting = True
      self.view.canvas.winfo_toplevel().after(500, self._resubmit)
    else:
      print("submitting")
      self.job = self.pool.submit(fieldLayout.call, "newFrame")
      #self.job.add_done_callback(self._updateFromBones)
      self.job.add_done_callback(lambda future: self.view.after(self._updateFromBones, future))
  
# def testBones(view:SNView):
#   bg = BonesGraph()
#   # i = 0
#   # for obj in view._objects.values():
#   #   if bg.addNode(obj) is not None:
#   #     i += 1
#   #   if i>10: break
#   bg.setView(view)
#   for k,v in bg.nodes.items():
#     print('{:5d}: {!s:s}'.format(k, v))
    
    