#################################################################################
# (c) Copyright 2024-2026, Rob Kremer, MIT open source license.                 #
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
from typing import Any, override, Optional, cast
import xml.etree.ElementTree as ET
from xml.etree.ElementTree import Element, ElementTree
from util.utils import getFullClassName, getClassFromFullyQualifiedName
from sn.persistence import PersistenceStrategy, ParamInfo, TAG_OBJECT,\
  PersistentObject, InstantiationInfo, ATTR_TYPE, getInstantiationInfo,\
  ATTR_VALUE, TAG_PROPERTY, ATTR_NAME, TAG_WRAPPER, TAG_VERSION, VERSION

    
class XMLPersistenceStrategy(PersistenceStrategy[Element]):
  
  @override
  def _encodeObject(self, obj:PersistenceStrategy.PersistentTypes) -> Element:
    
    def getAttrsAndSubs(obj:PersistenceStrategy.PersistentTypes, 
                        pinfos:list[ParamInfo]
                        ) -> tuple[list[tuple[str, str]], list[tuple[str, Element]]]:
      'Return the list of XML attributes and the list of XML subelements (children).'
      attrs:list[tuple[str, str]] = []
      subelems:list[tuple[str, Element]] = []
      for pinfo in pinfos:
        typ:type = pinfo.typ
        name:str = pinfo.name
        writeMethod = pinfo.writeMethod
        if issubclass(typ, PersistentObject):
          elem:Element = Element(TAG_PROPERTY, {ATTR_NAME: name, ATTR_TYPE: getFullClassName(typ)})
          info:InstantiationInfo = typ.getInstantiationInfo()
          for args in (info.conArgs, info.conKWArgs, info.postconArgs, info.finalArgs):
            attrs, subs = getAttrsAndSubs(writeMethod(obj), args)
            for a in attrs:
              elem.attrib[a[0]] = a[1]
            for s in subs:
              elem.append(s[1])
          subelems.append((name, elem))
        elif typ in (int, float, bool):
          attrs.append((name, str(writeMethod(obj))))
        elif typ is str:
          attrs.append((name, writeMethod(obj)))
        elif typ in (list, tuple, set):
          subelem:Element = Element(TAG_PROPERTY, {ATTR_NAME: name, ATTR_TYPE: getFullClassName(typ)})
          for i in writeMethod(obj):
            subelem.append(self._encodeObject(i))
          subelems.append((name, subelem))
        elif typ is dict:
          subelem = Element(TAG_PROPERTY, {ATTR_NAME: name, ATTR_TYPE: getFullClassName(typ)})
          for k,v in writeMethod(obj).items():
            subelem.append(self._encodeObject(k))
            subelem.append(self._encodeObject(v))
          subelems.append((name, subelem))
      return attrs, subelems
                 
    if isinstance(obj, PersistentObject):
      elem = Element(TAG_OBJECT, {ATTR_TYPE: getFullClassName(type(obj))})
      info:InstantiationInfo = obj.getInstantiationInfo()
      for args in (info.conArgs, info.conKWArgs, info.postconArgs, info.finalArgs):
        attrs, subs = getAttrsAndSubs(obj, args)
        for a in attrs:
          elem.attrib[a[0]] = a[1]
        for s in subs:
          elem.append(s[1])
      return elem
    elif isinstance(obj, (int,float,str)):
      return Element(TAG_OBJECT, {ATTR_TYPE: obj.__class__.__name__, ATTR_VALUE:str(obj)})
    elif isinstance(obj, (list, tuple, set)):
      elem = Element(TAG_OBJECT, {ATTR_TYPE: obj.__class__.__name__})
      for i in obj:
        elem.append(self._encodeObject(i))
      return elem
    elif isinstance(obj, dict):
      elem = Element(TAG_OBJECT, {ATTR_TYPE: obj.__class__.__name__})
      for k,v in obj.items():
        elem.append(self._encodeObject(k))
        elem.append(self._encodeObject(v))
      return elem
    else:
      raise TypeError(f'Unsupported type: "{obj.__class__.__name__}".') 
    
  @override
  def _decodeObject(self, elem:Element) -> PersistenceStrategy.PersistentTypes:
    
    def getArgs(desc:list[ParamInfo]) -> list[tuple[str, PersistenceStrategy.PersistentTypes]]: 
      ret:list[tuple[str, PersistenceStrategy.PersistentTypes]] = []
      for p in desc:
        pinfo:ParamInfo = p
        if pinfo.typ in PersistenceStrategy.PersistentTypesInAttrs:
          ret.append((pinfo.name, pinfo.typ(elem.attrib[pinfo.name])))
        else:
          assert pinfo.typ in PersistenceStrategy.PersistentTypesInSubs or issubclass(pinfo.typ, PersistentObject)
          sub:Optional[Element] = elem.find(f"./{TAG_PROPERTY}[@{ATTR_NAME}='{pinfo.name}']")
          if sub is None:
            raise LookupError(f'Subelement property named "{pinfo.name}" not found in Element "{elem.tag}" of type {elem.attrib[ATTR_TYPE]}.')
          sub.tag = TAG_OBJECT
          assert sub.attrib[ATTR_TYPE] == getFullClassName(pinfo.typ)
          ret.append((pinfo.name, self._decodeObject(sub)))
      return ret
    
    assert elem.tag == TAG_OBJECT, f'Expecting element tag {TAG_OBJECT}, but got "{elem.tag}".'
    className = elem.attrib[ATTR_TYPE]
    cls = getClassFromFullyQualifiedName(className)
    if cls is None:
      raise TypeError(f'Could not find type "{className}"')
    if issubclass(cls, PersistentObject):
      info:InstantiationInfo = getInstantiationInfo(className)
      stuff = getArgs(info.conArgs)
      args:list = [x[1] for x in stuff] # convert from pairs to list of 2nds
      stuff = getArgs(info.conKWArgs)
      kwargs:dict[str,Any] = dict(stuff)
      ret = cls(*args, **kwargs)
      if info.postconMethod is not None:
        stuff = getArgs(info.postconArgs)
        info.postconMethod(ret, **dict(stuff))
      if info.finalMethod is not None:
        stuff = getArgs(info.finalArgs)
        self.finalMethodsList.append(lambda 
                                        obj=ret, 
                                        method=info.finalMethod, 
                                        kwargs=dict(stuff): 
                                          method(obj, **kwargs))
      return ret
    elif cls in (int, float, str):
      return cls(elem.attrib[ATTR_VALUE]) # type: ignore[call-arg, return-value]
    elif cls is bool:
      s = elem.attrib[ATTR_VALUE]
      return s != "False"
    elif cls in (list, tuple, set):
      stuff2 = []
      for e in elem.findall(f"./{TAG_OBJECT}"):
        stuff2.append(self._decodeObject(e))
      return cls(stuff2) # type: ignore[call-arg, return-value]
    elif cls is dict:
      items = elem.findall(f".//{TAG_OBJECT}")
      if len(items) % 2 != 0:
        raise ValueError(f"List must have an even number of elements, got {len(items)}.")
      objs = [self._decodeObject(e) for e in items] # convert the elements in items to Python values
      return {objs[i]: objs[i + 1] for i in range(0, len(objs), 2)} #change pair-list to a dict
    else:
      raise TypeError(f'Unsupported type: "{className}".') 
   
    return None
    
  @override
  def defaultExtension(self) -> str:
    return ".xml"
    
  @override
  def _wrap(self, elem:Element) -> Element:
    ret = Element(TAG_WRAPPER, {TAG_VERSION: VERSION})
    ret.append(elem)
    return ret
  
  @override
  def _unwrap(self, root:Element) -> Element:
    if root.tag != TAG_WRAPPER:
      raise TypeError(f'Data does not seem to be XML {TAG_WRAPPER} data: Expected tag "{TAG_WRAPPER}" but got "{root.tag}".')
    self.readingVersion = root.attrib[TAG_VERSION]
    
    ret = root.find(f"./{TAG_OBJECT}")
    if ret is None:
      raise SyntaxError(f'Malfored XML doc: Could not find outer "{TAG_OBJECT}" Element.')
    return ret
    
  def tostring(self, obj:PersistenceStrategy.PersistentTypes) -> str:
    """
    Return the data as a strategy-specific formatted string.
  
    :param obj: The object to serialise and returned.
    :type obj: PersistentTypes
    :returns: The serialized object as a string.
    :rtype: str
    """
    root:Element = self._wrap(self._encodeObject(obj))
    tree:ElementTree = ElementTree(root)
    ET.indent(tree)
    xmlString:str = ET.tostring(
      cast(Element, tree.getroot()),
      encoding="unicode",
      xml_declaration=True,
      short_empty_elements=True,
    )
    return xmlString

  def fromstring(self, string:str) -> PersistenceStrategy.PersistentTypes:
    """
    Return an object made from a strategy-specific formatted string.
  
    :param string: The string to interpret.
    :type string: str
    :returns: The object interpreted from *string*.
    :rtype: PersistentTypes
    """
    self.finalMethodsList = []
    root:Optional[Element] = ET.fromstring(string)
    if root is None:
      raise SyntaxError('Could not interpret given XML string.')
    assert isinstance(root, Element)
    elem:Element = self._unwrap(root) 

    ret = self._decodeObject(elem)
    
    for finalMethod in self.finalMethodsList:
      finalMethod()
    self.finalMethodsList = []
    
    return ret

# import os
# import urllib.request
# from urllib.parse import urlparse

  # def write(self, url:str, obj:PersistenceStrategy.PersistentTypes, replaceExt:Optional[bool]=True) -> None:
  #   """Write an :class:`xml.etree.ElementTree.ElementTree` to a URL.
  #
  #   For ``file:`` URLs the XML is written directly to the local filesystem path.
  #   For all other schemes (e.g. ``http:``, ``https:``) the XML is uploaded via
  #   :func:`urllib.request.urlopen` as an HTTP PUT request with content-type
  #   ``application/xml``.
  #
  #   :param url: The destination URL. Use ``file:///absolute/path`` or
  #     ``file://relative/path`` for local files.
  #   :type url: str
  #   :param tree: The element tree to serialise and write.
  #   :type tree: xml.etree.ElementTree.ElementTree
  #   :param replaceExt: If True, (the default) any extension will be replace with
  #     the default extension; if False, the default will extension will be 
  #     appended to the path if it's not already there; if None, nothing will
  #     be done to the path.
  #   :type replaceExt: Optional[bool]
  #   :returns: None
  #   :rtype: None
  #   :raises ValueError: If *url* is an empty string.
  #   :raises FileNotFoundError: If the parent directory of a ``file:`` URL path
  #     does not exist.
  #   :raises urllib.error.URLError: If a remote URL cannot be reached.
  #
  #   Usage::
  #
  #     >>> tree = ET.parse("data.xml")
  #     >>> write("file:///tmp/output.xml", tree)
  #     >>> write("https://example.com/api/document", tree)
  #   """
  #   if not url:
  #     raise ValueError("url must not be empty")
  #   parsedUrl = urlparse(url)
  #
  #   root = self._wrap(self._encodeObject(obj))
  #   tree:ElementTree = ElementTree(root)
  #
  #   ET.indent(root)
  #
  #   if parsedUrl.scheme == "file":
  #     localPath: str = parsedUrl.netloc + parsedUrl.path
  #     absolutePath: str = os.path.abspath(localPath)
  #     tree.write(
  #       absolutePath,
  #       encoding="unicode",
  #       xml_declaration=True,
  #       short_empty_elements=True,
  #     )
  #     return
  #
  #   xmlBytes: bytes = ET.tostring(
  #     cast(Element, tree.getroot()),
  #     encoding="utf-8",
  #     xml_declaration=True,
  #     short_empty_elements=True,
  #   )
  #   request:urllib.request.Request = urllib.request.Request(
  #     url,
  #     data=xmlBytes,
  #     method="PUT",
  #     headers={"Content-Type": "application/xml; charset=utf-8"},
  #   )
  #   with urllib.request.urlopen(request):
  #     pass
  #
  # def read(self, url: str) -> PersistenceStrategy.PersistentTypes:
  #   """Fetch and parse XML data from a URL or local file.
  #
  #   Supports ``http://``, ``https://``, and ``file://`` protocols.
  #   For ``file://`` URLs, the path is resolved from the URL and read
  #   directly from the local filesystem.
  #
  #   :param url: The URL to fetch XML from. May use ``http``, ``https``,
  #     or ``file`` schemes. A bare path is also accepted and treated as
  #     a ``file://`` URL.
  #   :type url: str
  #   :returns: The root element of the parsed XML document.
  #   :rtype: xml.etree.ElementTree.Element
  #   :raises ValueError: If the URL scheme is not supported.
  #   :raises FileNotFoundError: If a ``file://`` URL points to a missing file.
  #   :raises urllib.error.URLError: If the remote URL cannot be reached.
  #   :raises xml.etree.ElementTree.ParseError: If the response is not valid XML.
  #
  #   Example::
  #
  #     root = fetchXml("https://example.com/data.xml")
  #     root = fetchXml("file:///home/user/data.xml")
  #   """
  #   self.finalMethodsList = []
  #
  #   parsedUrl: urllib.parse.ParseResult = urlparse(url)
  #
  #   # Treat bare paths (no scheme) as file:// URLs.
  #   scheme: str = parsedUrl.scheme.lower() if parsedUrl.scheme else "file"
  #
  #   if scheme == "file":
  #     localPath: str = parsedUrl.path if parsedUrl.path else url
  #     tree = ET.parse(localPath)
  #     root = tree.getroot()
  #     if root is None:
  #       raise LookupError(f'URL "{url}" exists, but seems to have no data.')
  #     elem:Element = self._unwrap(root)
  #   elif scheme in ("http", "https"):
  #     with urllib.request.urlopen(url) as response:
  #       rawBytes: bytes = response.read()
  #     elem = self._unwrap(ET.fromstring(rawBytes))
  #   else:
  #     raise ValueError(f"Unsupported URL scheme: '{scheme}'. Use 'file', 'http', or 'https'.")    
  #
  #   ret = self._decodeObject(elem)
  #
  #   for finalMethod in self.finalMethodsList:
  #     finalMethod()
  #   self.finalMethodsList = []
  #
  #   return ret
  
    