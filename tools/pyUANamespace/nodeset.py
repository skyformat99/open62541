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

from __future__ import print_function
import sys
import xml.dom.minidom as dom
from struct import pack as structpack
from collections import deque
from time import struct_time, strftime, strptime, mktime
import logging; logger = logging.getLogger(__name__)

from datatypes import *
from nodes import *
from constants import *

knownNodeTypes = ['variable', 'object', 'method', 'referencetype', \
                  'objecttype', 'variabletype', 'methodtype', \
                  'datatype', 'referencetype', 'aliases']

class NodeSet():
  """ This class handles parsing XML description of namespaces, instantiating
      nodes, linking references, graphing the namespace and compiling a binary
      representation.

      Note that nodes assigned to this class are not restricted to having a
      single namespace ID. This class represents the entire physical address
      space of the binary representation and all nodes that are to be included
      in that segment of memory.
  """
  def __init__(self, name):
    self.nodes = []
    self.name = name
    self.nodeids = {}
    self.aliases = {}
    self.namespaceIdentifiers = ["http://opcfoundation.org/UA/"]

  def addNamespace(self, nsURL):
    if not nsURL in self.namespaceIdentifiers:
      self.namespaceIdentifiers.append(nsURL)

  def createNamespaceMapping(self, orig_namespaces):
    """Creates a dict that maps from the nsindex in the original nodeset to the
       nsindex in the combined nodeset"""
    m = {}
    for index,name in enumerate(orig_namespaces):
      m[index] = self.namespaceIdentifiers.index(name)
    return m

  def buildAliasList(self, xmlelement):
    """Parses the <Alias> XML Element present in must XML NodeSet definitions.
       Contents the Alias element are stored in a dictionary for further
       dereferencing during pointer linkage (see linkOpenPointer())."""
    if not xmlelement.tagName == "Aliases":
      logger.error("XMLElement passed is not an Aliaslist")
      return
    for al in xmlelement.childNodes:
      if al.nodeType == al.ELEMENT_NODE:
        if al.hasAttribute("Alias"):
          aliasst = al.getAttribute("Alias")
          if sys.version_info[0] < 3:
            aliasnd = unicode(al.firstChild.data)
          else:
            aliasnd = al.firstChild.data
          if not aliasst in self.aliases:
            self.aliases[aliasst] = aliasnd
            logger.debug("Added new alias \"" + str(aliasst) + "\" == \"" + str(aliasnd) + "\"")
          else:
            if self.aliases[aliasst] != aliasnd:
              logger.error("Alias definitions for " + aliasst + " differ. Have " + \
                           self.aliases[aliasst] + " but XML defines " + aliasnd + \
                           ". Keeping current definition.")

  def replaceAliases(self, node):
    if str(node.id) in self.aliases:
      node.id = NodeId(self.aliases[node.id])
    for ref in node.references:
      if str(ref.source) in self.aliases:
        ref.source = NodeId(self.aliases[ref.source])
      if str(ref.target) in self.aliases:
        ref.target = NodeId(self.aliases[ref.target])
      if str(ref.referenceType) in self.aliases:
        ref.referenceType = NodeId(self.aliases[ref.referenceType])
    for ref in node.inverseReferences:
      if str(ref.source) in self.aliases:
        ref.source = NodeId(self.aliases[ref.source])
      if str(ref.target) in self.aliases:
        ref.target = NodeId(self.aliases[ref.target])
      if str(ref.referenceType) in self.aliases:
        ref.referenceType = NodeId(self.aliases[ref.referenceType])

  def getRoot(self):
    return self.getNodeByBrowseName("Root")

  def getNodeByIDString(self, idstring):
    return next((n for n in self.nodes if idstring==str(n.id)), None)

  def getNodeByBrowseName(self, idstring):
    return next((n for n in self.nodes if idstring==str(n.browseName)), None)

  def createNode(self, xmlelement, nsMapping):
    """ createNode is instantiates a node described by xmlelement, its type being
        defined by the string ndtype.

        If the xmlelement is an <Alias>, the contents will be parsed and stored
        for later dereferencing during pointer linking (see linkOpenPointers).

        Recognized types are:
        * UAVariable
        * UAObject
        * UAMethod
        * UAView
        * UAVariableType
        * UAObjectType
        * UAMethodType
        * UAReferenceType
        * UADataType

        For every recognized type, an appropriate node class is added to the node
        list of the namespace. The NodeId of the given node is created and parsing
        of the node attributes and elements is delegated to the parseXML() and
        parseXMLSubType() functions of the instantiated class.

        If the NodeID attribute is non-unique in the node list, the creation is
        deferred and an error is logged.
    """
    if not isinstance(xmlelement, dom.Element):
      return
      raise Exception( "Error: Can not create node from invalid XMLElement")

    if xmlelement.nodeType != xmlelement.ELEMENT_NODE:
      return

    ndtype = xmlelement.tagName.lower()
    if ndtype[:2] == "ua":
      ndtype = ndtype[2:]

    if ndtype == 'aliases':
      self.buildAliasList(xmlelement)
      return

    node = None
    if ndtype == 'variable':
      node = VariableNode()
    elif ndtype == 'object':
      node = ObjectNode()
    elif ndtype == 'method':
      node = MethodNode()
    elif ndtype == 'objecttype':
      node = ObjectTypeNode()
    elif ndtype == 'variabletype':
      node = VariableTypeNode()
    elif ndtype == 'methodtype':
      node = MethodNode()
    elif ndtype == 'datatype':
      node = DataTypeNode()
    elif ndtype == 'referencetype':
      node = ReferenceTypeNode()
    else:
      return

    node.parseXML(xmlelement)

    if node.id == None:
      raise Exception("Error: XMLElement has no id")
    if node.id in self.nodeids:
      raise Exception("XMLElement with duplicate ID " + str(node.id))

    # Exchange the namespace indices
    self.replaceAliases(node)
    node.id.ns = nsMapping[node.id.ns]
    # TODO Exchange all the reference namespaces
    # TODO Create the inverse references in the node that should have the forward reference

    self.nodes.append(node)
    self.nodeids[str(node.id)] = node

  def removeNodeById(self, nodeId):
    nd = self.getNodeByIDString(nodeId)
    if nd == None:
      return

    logger.debug("Removing nodeId " + str(nodeId))
    self.nodes.remove(nd)
    for ref in nd.inverseReferences:
      src = ref.target;
      src.removeReferenceToNode(nd)

  @staticmethod
  def XmlNamespaces(xmlfile):
    # Extract a list of namespaces used. The first namespace is always
    # "http://opcfoundation.org/UA/". minidom gobbles up
    # <NamespaceUris></NamespaceUris> elements, without a decent way to reliably
    # access this dom2 <uri></uri> elements (only attribute xmlns= are accessible
    # using minidom). We need them for dereferencing though... This function
    # attempts to do just that.
    
    namespaces = ["http://opcfoundation.org/UA/"]
    infile = open(xmlfile.name)
    foundURIs = False
    nsline = ""
    line = infile.readline()
    for line in infile:
      if "<namespaceuris>" in line.lower():
        foundURIs = True
      elif "</namespaceuris>" in line.lower():
        foundURIs = False
        nsline = nsline + line
        break
      if foundURIs:
        nsline = nsline + line

    if len(nsline) > 0:
      ns = dom.parseString(nsline).getElementsByTagName("NamespaceUris")
      for uri in ns[0].childNodes:
        if uri.nodeType != uri.ELEMENT_NODE:
          continue
        if uri.firstChild.data in namespaces:
          continue
        namespaces.append(uri.firstChild.data)
    infile.close()
    return namespaces

  def addNodeSet(self, xmlfile):
    nodesets = dom.parse(xmlfile).getElementsByTagName("UANodeSet")
    if len(nodesets) == 0 or len(nodesets) > 1:
      raise Exception(self, self.originXML + " contains no or more then 1 nodeset")
    nodeset = nodesets[0] # Parsed DOM XML object
    orig_namespaces = self.XmlNamespaces(xmlfile) # List of namespaces used in the xml file
    for ns in orig_namespaces:
      if not ns in self.namespaceIdentifiers:
        self.namespaceIdentifiers.append(ns)
    nsMapping = self.createNamespaceMapping(orig_namespaces)

    # Instantiate nodes
    for nd in nodeset.childNodes:
      self.createNode(nd, nsMapping)

    logger.debug("Currently " + str(len(self.nodes)) + " nodes in address space.")

  def sanitize(self):
    remove = []
    logger.debug("Sanitizing nodes and references...")
    for n in self.nodes:
      if n.sanitize() == False:
        remove.append(n)
    if not len(remove) == 0:
      logger.warn(str(len(remove)) + " nodes will be removed because they failed sanitation.")
    # FIXME: Some variable ns=0 nodes fail because they don't have DataType fields...
    #        How should this be handles!?
    logger.warn("Not actually removing nodes... it's unclear if this is valid or not")

  def buildEncodingRules(self):
    """ Calls buildEncoding() for all DataType nodes (DataTypeNode). """
    return
    stat = {True: 0, False: 0}
    for n in self.nodes:
      if isinstance(n, DataTypeNode):
        n.buildEncoding()
        stat[n.isEncodable] = stat[n.isEncodable] + 1
    logger.debug("Type definitions built/passed: " +  str(stat))

  def allocateVariables(self):
    return
    for n in self.nodes:
      if isinstance(n, VariableNode):
        n.allocateValue()

  def getSubTypesOf2(self, node):
    re = [node]
    for ref in node.references: 
      if isinstance(ref.target(), Node):
        if ref.referenceType().displayName() == "HasSubtype" and ref.isForward():
          re = re + self.getSubTypesOf2(ref.target())
    return re

  def reorderNodesMinDependencies(self, printedExternally):
    #Kahn's algorithm
    #https://algocoding.wordpress.com/2015/04/05/topological-sorting-python/
    
    relevant_types = ["HierarchicalReferences", "HasComponent"]
    
    temp = []
    for t in relevant_types:
        temp = temp + self.getSubTypesOf2(self.getNodeByBrowseName(t))
    relevant_types = temp

    # determine in-degree
    in_degree = { u : 0 for u in self.nodes }
    for u in self.nodes: # of each node
      if u not in printedExternally:
        for ref in u.references:
         if isinstance(ref.target, Node):
           if(ref.referenceType() in relevant_types and ref.isForward):
             in_degree[ref.target] += 1
    
    # collect nodes with zero in-degree
    Q = deque()
    for u in in_degree:
      if in_degree[u] == 0:
        Q.appendleft(u)
 
    L = []     # list for order of nodes
    
    while Q:
      u = Q.pop()          # choose node of zero in-degree
      L.append(u)          # and 'remove' it from graph
      for ref in u.references:
       if isinstance(ref.target, Node):
         if(ref.referenceType in relevant_types and ref.isForward()):
           in_degree[ref.target] -= 1
           if in_degree[ref.target] == 0:
             Q.appendleft(ref.target)
    if len(L) == len(self.nodes):
        self.nodes = L
    else:                    # if there is a cycle,  
        logger.error("Node graph is circular on the specified references")
        self.nodes = L + [x for x in self.nodes if x not in L]
    return
