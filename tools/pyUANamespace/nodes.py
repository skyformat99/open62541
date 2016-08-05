#!/usr/bin/env/python
# -*- coding: utf-8 -*-

###
### Author:  Chris Iatrou (ichrispa@core-vector.net)
### Version: rev 13
###
### This program was created for educational purposes and has been
### contributed to the open62541 project by the author. All licensing
### terms for this source is inherited by the terms and conditions
### specified for by the open62541 project (see the projects readme
### file for more information on the LGPL terms and restrictions).
###
### This program is not meant to be used in a production environment. The
### author is not liable for any complications arising due to the use of
### this program.
###

import sys
import logging
from sets import Set
from datatypes import *
from constants import *

logger = logging.getLogger(__name__)

if sys.version_info[0] >= 3:
  # strings are already parsed to unicode
  def unicode(s):
    return s

def getNextElementNode(xmlvalue):
  if xmlvalue == None:
    return None
  xmlvalue = xmlvalue.nextSibling
  while not xmlvalue == None and not xmlvalue.nodeType == xmlvalue.ELEMENT_NODE:
    xmlvalue = xmlvalue.nextSibling
  return xmlvalue

# References are not really described by OPC-UA. This is how we
# use them here.

class Reference():
  # source, referenceType and target are expected to be Nodes (not NodeIds)
  def __init__(self, source, referenceType, target, isForward = True):
    self.source = source
    self.referenceType = referenceType
    self.target = target
    self.isForward = isForward

  def getCodePrintableID(self):
    src = str(self.source.id)
    tgt = str(self.target.id)
    type = str(self.referenceType.id)
    tmp = src+"_"+type+"_"+tgt
    tmp = tmp.lower()
    refid = ""
    for i in tmp:
      if not i in "ABCDEFGHIJKLMOPQRSTUVWXYZ0123456789".lower():
        refid = refid + ("_")
      else:
        refid = refid + i
    return refid

  def __str__(self):
    retval = str(self.source)
    if not self.isForward:
      retval = retval + "<"
    retval = retval + "--[" + str(self.referenceType) + "]--"
    if self.isForward:
      retval = retval + ">"
    return retval + str(self.target)

  def __repr__(self):
      return str(self)

  def __hash__(self):
    return hash(str(self))

class Node:
  def __init__(self):
    self.id             = NodeId()
    self.nodeClass      = NODE_CLASS_GENERERIC
    self.browseName     = QualifiedName()
    self.displayName    = LocalizedText()
    self.description    = LocalizedText()
    self.writeMask      = 0
    self.userWriteMask  = 0
    self.references     = Set()
    self.inverseReferences = Set()

  def __str__(self):
    return self.__class__.__name__ + "(" + str(self.id) + ")"

  def __repr__(self):
    return str(self)

  def sanitize(self):
    pass

  def parseXMLReferences(self, xmlelement):
    for ref in xmlelement.childNodes:
      if ref.nodeType != ref.ELEMENT_NODE:
        continue
      target = NodeId(unicode(ref.firstChild.data))
      reftype = None
      forward = True
      for (at, av) in ref.attributes.items():
        if at == "ReferenceType":
          if '=' in av:
            reftype = NodeId(av)
          else:
            reftype = av # cleartext, such as "HasSubType"
        elif at == "IsForward":
          forward = not "false" in av.lower()
      if forward:
        self.references.add(Reference(self.id, target, reftype, forward))
      else:
        self.inverseReferences.add(Reference(self.id, target, reftype, forward))

  def parseXML(self, xmlelement):
    """ Extracts base attributes from the XML description of an element.
        ParentNodeIds are ignored.
    """
    for idname in ['NodeId', 'NodeID', 'nodeid']:
      if xmlelement.hasAttribute(idname):
        self.id = NodeId(xmlelement.getAttribute(idname))

    thisxml = xmlelement
    for (at, av) in thisxml.attributes.items():
      if at == "BrowseName":
        self.browseName = av
      elif at == "DisplayName":
        self.displayName = av
      elif at == "Description":
        self.description = av
      elif at == "WriteMask":
        self.writeMask = int(av)
      elif at == "UserWriteMask":
        self.userWriteMask = int(av)
      elif at == "EventNotifier":
        self.eventNotifier = int(av)

    for x in thisxml.childNodes:
      if x.nodeType != x.ELEMENT_NODE:
        continue
      if x.firstChild:
        if x.tagName == "BrowseName":
          self.browseName = unicode(x.firstChild.data)
        elif x.tagName == "DisplayName":
          self.displayName = LocalizedText(x)
        elif x.tagName == "Description":
          self.description = LocalizedText(x)
        elif x.tagName == "WriteMask":
          self.writeMask = int(unicode(x.firstChild.data))
        elif x.tagName == "UserWriteMask":
          self.userWriteMask = int(unicode(x.firstChild.data))
        if x.tagName == "References":
          self.parseXMLReferences(x)

  def getType(self):
    """For variables and objects, return the type"""
    pass

  def getParent(self):
    """ Return a tuple of (Node, ReferencePointer) indicating
        the first node found that references this node. If this node is not
        referenced at all, None will be returned.

        Note that there may be more than one nodes that reference this node.
        The parent returned will be determined by the first isInverse()
        Reference of this node found. If none exists, the first hidden
        reference will be returned.
    """
    # TODO What a parent is depends on the node type
    parent = None
    parentref = None

    for hiddenstatus in [False, True]:
      for r in self.references:
        if r.isForward == False:
          parent = r.source
          for r in parent.references:
            if r.target == self.id:
              parentref = r
              break
          if parentref != None:
            return (parent, parentref)
    return (parent, parentref)

class ReferenceTypeNode(Node):
  def __init__(self):
    Node.__init__(self)
    self.nodeClass = NODE_CLASS_REFERENCETYPE
    self.isAbstract    = False
    self.symmetric     = False
    self.inverseName   = ""

  def parseXML(self, xmlelement):
    Node.parseXML(self, xmlelement)
    for (at, av) in xmlelement.attributes.items():
      if at == "Symmetric":
        self.symmetric = "false" not in av.lower()
      elif at == "InverseName":
        self.inverseName = str(av)
      elif at == "IsAbstract":
        self.isAbstract = "false" not in av.lower()

    for x in xmlelement.childNodes:
      if x.nodeType == x.ELEMENT_NODE:
        if x.tagName == "InverseName" and x.firstChild:
          self.inverseName = str(unicode(x.firstChild.data))

class ObjectNode(Node):
  def __init__(self):
    Node.__init__(self)
    self.nodeClass = NODE_CLASS_OBJECT
    self.eventNotifier = 0

  def parseXML(self, xmlelement):
    Node.parseXML(self, xmlelement)
    for (at, av) in xmlelement.attributes.items():
      if at == "EventNotifier":
        self.eventNotifier = int(av)

class VariableNode(Node):
  def __init__(self):
    Node.__init__(self)
    self.nodeClass = NODE_CLASS_VARIABLE
    self.dataType            = NodeId()
    self.valueRank           = -1
    self.arrayDimensions     = []
    self.accessLevel         = 0
    self.userAccessLevel     = 0
    self.minimumSamplingInterval = 0.0
    self.historizing         = False
    self.value               = None
    self.xmlValueDef         = None

  def parseXML(self, xmlelement):
    Node.parseXML(self, xmlelement)
    for (at, av) in xmlelement.attributes.items():
      if at == "ValueRank":
        self.valueRank = int(av)
      elif at == "AccessLevel":
        self.accessLevel = int(av)
      elif at == "UserAccessLevel":
        self.userAccessLevel = int(av)
      elif at == "MinimumSamplingInterval":
        self.minimumSamplingInterval = float(av)
      elif at == "DataType":
        self.dataType = NodeId(str(av))

    for x in xmlelement.childNodes:
      if x.nodeType != x.ELEMENT_NODE:
        continue
      if x.tagName == "Value":
          self.__xmlValueDef__ = x
      elif x.tagName == "DataType":
          self.dataType = NodeId(str(x))
      elif x.tagName == "ValueRank":
          self.valueRank = int(unicode(x.firstChild.data))
      elif x.tagName == "ArrayDimensions":
          self.arrayDimensions = int(unicode(x.firstChild.data))
      elif x.tagName == "AccessLevel":
          self.accessLevel = int(unicode(x.firstChild.data))
      elif x.tagName == "UserAccessLevel":
          self.userAccessLevel = int(unicode(x.firstChild.data))
      elif x.tagName == "MinimumSamplingInterval":
          self.minimumSamplingInterval = float(unicode(x.firstChild.data))
      elif x.tagName == "Historizing":
          self.historizing = "false" not in x.lower()

class VariableTypeNode(VariableNode):
  def __init__(self):
    VariableNode.__init__(self)
    self.nodeClass = NODE_CLASS_VARIABLETYPE

class MethodNode(Node):
  def __init__(self):
    Node.__init__(self)
    self.nodeClass = NODE_CLASS_METHOD
    self.executable     = True
    self.userExecutable = True
    self.methodDecalaration = None

  def parseXML(self, xmlelement):
    Node.parseXML(self, xmlelement)
    for (at, av) in xmlelement.attributes.items():
      if at == "Executable":
        self.executable = "false" not in av.lower()
      if at == "UserExecutable":
        self.userExecutable = "false" not in av.lower()
      if at == "MethodDeclarationId":
        self.methodDeclaration = str(av)

class ObjectTypeNode(Node):
  def __init__(self):
    Node.__init__(self)
    self.nodeClass = NODE_CLASS_OBJECTTYPE
    self.isAbstract = False

  def parseXML(self, xmlelement):
    Node.parseXML(self, xmlelement)
    for (at, av) in xmlelement.attributes.items():
      if at == "IsAbstract":
        self.isAbstract = "false" not in av.lower()

class DataTypeNode(Node):
  def __init__(self):
    Node.__init__(self)
    self.nodeClass = NODE_CLASS_DATATYPE
    self.isAbstract = False

  def parseXML(self, xmlelement):
    Node.parseXML(self, xmlelement)
    for (at, av) in xmlelement.attributes.items():
      if at == "IsAbstract":
        self.isAbstract = "false" not in av.lower()

class ViewNode(Node):
  def __init__(self):
    Node.__init__(self)
    self.nodeClass = NODE_CLASS_VIEW
    self.containsNoLoops == False
    self.eventNotifier == False

  def parseXML(self, xmlelement):
    Node.parseXML(self, xmlelement)
    for (at, av) in xmlelement.attributes.items():
      if at == "ContainsNoLoops":
        self.containsNoLoops = "false" not in av.lower()
      if at == "eventNotifier":
        self.eventNotifier = "false" not in av.lower()
