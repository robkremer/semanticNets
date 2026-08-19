'''
Created on Mar 21, 2026

@author: robkremer
'''
import unittest
from sn.persistence import PersistentObject, InstantiationInfo, ParamInfo,\
  PersistenceStrategy
from sn.persistenceXML import XMLPersistenceStrategy
from sn.persistenceJSON import JSONPersistenceStrategy

from typing import override
import os

class SamplePObject1(PersistentObject):

  @override
  @classmethod
  def getInstantiationInfo(cls) -> InstantiationInfo:
    info = InstantiationInfo(
            class_=cls, 
            conArgs=[ParamInfo("integer", int, lambda slf: slf.integer),
                     ParamInfo("floating", float, lambda slf: slf.floating)], 
            conKWArgs=[],
            postconArgs=[ParamInfo("static", tuple, lambda slf: slf.static)],
            postconMethod=cls._post__init__,
            finalArgs=[ParamInfo("alist", list, lambda slf: slf.alist)], 
            finalMethod=cls._final__init__
            )
    return info
  
  def __init__(self, integer:int=1, floating:float=1.3, alist = [1,2.3,"Hello World"]):
    self.integer:int = integer
    self.floating:float = floating
    self.alist:list = alist
    self.static = ("constant",)
    
  def _post__init__(self, static:tuple):
    self.static = static
    
  def _final__init__(self, alist:list):
    self.alist = alist
    print(f'{str(self)}: _final__init__({alist})')
    
  def __eq__(self, other):
    if other.__class__ is SamplePObject1:
      return self.integer == other.integer and \
             self.floating == other.floating and \
             self.alist == other.alist and \
             self.static == other.static
    return False
  
class SamplePObject2(PersistentObject):

  @override
  @classmethod
  def getInstantiationInfo(cls) -> InstantiationInfo:
    info = InstantiationInfo(
      class_=cls, 
      conArgs=[ParamInfo("integer", int, lambda slf: slf.integer),
               ParamInfo("floating", float, lambda slf: slf.floating), 
               ParamInfo("alist", list, lambda slf: slf.alist)], 
      conKWArgs=[],
      postconArgs=[ParamInfo("static", tuple, lambda slf: slf.static),
                   ParamInfo("obj", SamplePObject1, lambda slf: slf.obj)],
      postconMethod=cls._post__init__
      )
    return info
  
  def __init__(self, integer:int=2, floating:float=2.3, alist = [1,2.3,"Hello World"]):
    self.integer = integer
    self.floating = floating
    self.alist = alist
    self.static = ("constant",)
    self.obj = SamplePObject1()
    
  def _post__init__(self, static:tuple, obj:SamplePObject1):
    self.static = static
    self.obj = obj
  
  def __eq__(self, other):
    if isinstance(other, SamplePObject2):
      return self.integer == other.integer and \
             self.floating == other.floating and \
             self.alist == other.alist and \
             self.static == other.static and \
             self.obj == other.obj
    return False
  
XMLinstantiator = XMLPersistenceStrategy()

class Test(unittest.TestCase):

  def setUp(self):
#    strategy = XMLPersistenceStrategy()
    pass

  def tearDown(self):
    pass

  def test_tostring_XML(self):
    self._test_tostring(XMLPersistenceStrategy)

  def test_tostring_JSON(self):
    self._test_tostring(JSONPersistenceStrategy)
    
  def _test_tostring[T:type](self, Strategy:T):
    obj = SamplePObject1()
    strategy = Strategy()
    print(f'1:\n-----\n{strategy.tostring(1)}\n-----')
    print(f'32.5:\n-----\n{strategy.tostring(32.5)}\n-----')
    print(f'Hello world:\n-----\n{strategy.tostring("Hello world!")}\n-----')
    print(f'list:\n-----\n{strategy.tostring([3, "Hello world!", 2.4, 3, 4, 4, 4, 4])}\n-----')
    print(f'tuple:\n-----\n{strategy.tostring((3, "Hello world!", 2.4))}\n-----')
    print(f'obj:\n-----\n{strategy.tostring(obj)}\n-----')
    strategy.write("file://"+os.getcwd()+"/temp", obj)
    obj2 = SamplePObject2()
    print(f'obj2:\n-----\n{strategy.tostring(obj2)}\n-----')
    strategy.write("file://"+os.getcwd()+"/temp2", obj2)
    print(f'nested list:\n-----\n{strategy.tostring([1,2,[3,4,[5,6]]])}\n-----')
    print(f'dict:\n-----\n{strategy.tostring({1:"one", "two":2})}\n-----')
    
  def test_writeReadback_XML(self):
    self._test_writeReadback(XMLPersistenceStrategy)
  

  def test_writeReadback_JSON(self):
    self._test_writeReadback(JSONPersistenceStrategy)
  
  def _test_writeReadback[T:type](self, Strategy:T):
    url = "file://"+os.getcwd()+"/temp3"
    strategy = Strategy()
    
    # ints
    strategy.write(url, 1)
    x = strategy.read(url)
    self.assertEqual(x, 1)
    self.assertTrue(isinstance(x, int))
    
    # floats
    strategy.write(url, 14.5)
    x = strategy.read(url)
    self.assertEqual(x, 14.5)
    self.assertTrue(isinstance(x, float))
    
    # strs
    strategy.write(url, "hi")
    x = strategy.read(url)
    self.assertEqual(x, "hi")
    self.assertTrue(isinstance(x, str))
    
    # bools
    strategy.write(url, True)
    x = strategy.read(url)
    self.assertEqual(x, True)
    self.assertTrue(isinstance(x, bool))
    
    strategy.write(url, False)
    x = strategy.read(url)
    self.assertEqual(x, False)
    self.assertTrue(isinstance(x, bool))
    
    # lists
    strategy.write(url, [1,3,5])
    x = strategy.read(url)
    self.assertEqual(x, [1,3,5])
    self.assertTrue(isinstance(x, list))
    
    # dicts
    strategy.write(url, {"one":1, "three":3})
    x = strategy.read(url)
    self.assertEqual(x, {"one":1, "three":3})
    self.assertTrue(isinstance(x, dict))
    
    strategy.write(url, {1:"one", 3:"three"})
    x = strategy.read(url)
    self.assertEqual(x, {1:"one", 3:"three"})
    self.assertTrue(isinstance(x, dict))
    
    # tuples
    strategy.write(url, (1, "xx" ,5.9, True, False))
    x = strategy.read(url)
    self.assertEqual(x, (1, "xx" ,5.9, True, False))
    self.assertTrue(isinstance(x, tuple))
    
    #sets
    strategy.write(url, {"one", "three"})
    x = strategy.read(url)
    self.assertEqual(x, {"three", "one"})
    self.assertTrue(isinstance(x, set))
    
    # user defined objects
    obj = SamplePObject1()
    strategy.write(url, obj)
    x = strategy.read(url)
    self.assertEqual(x, obj)
    self.assertTrue(isinstance(x, SamplePObject1))
    
    # test finalMethod itialization
    obj = SamplePObject1()
    obj.alist = ['x', 'y'] # has a different alist that can only be restored by finalMethod.
    strategy.write(url, obj)
    x = strategy.read(url)
    self.assertEqual(x, obj)
    self.assertTrue(isinstance(x, SamplePObject1))
    
    obj2 = SamplePObject2()
    strategy.write(url, obj2)
    x = strategy.read(url)
    self.assertEqual(x, obj2)
    self.assertTrue(isinstance(x, SamplePObject2))
    
    obj2 = SamplePObject2()
    assert obj.alist == ['x', 'y']
    obj2.obj = obj
    assert obj2.obj.alist == ['x', 'y']   
    strategy.write(url, obj2)
    x = strategy.read(url)
    self.assertEqual(x, obj2)
    self.assertTrue(isinstance(x, SamplePObject2))
    self.assertEqual(x.obj, obj) # type: ignore[union-attr]
    self.assertTrue(isinstance(x.obj, SamplePObject1)) # type: ignore[union-attr]
    
    

if __name__ == "__main__":
  #import sys;sys.argv = ['', 'Test.testName']
  unittest.main()