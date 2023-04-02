
"""
CloudLab profile to set up a Kubernetes cluster with flannel CNI and multus CNI plugin installed. Each node runs Ubuntu 20.04.

Instructions:
Create the experiment in CloudLab. Wait until the start script completes (can see status in the CloudLab experiment page). Interact with the cluster
using kubectl on node1 (the control-plane node). If something goes wrong, check the logs found in /home/k8s-flannel.
"""

import time

# Import the Portal object.
import geni.portal as portal
# Import the ProtoGENI library.
import geni.rspec.pg as rspec
import geni.rspec.emulab as emulab

BASE_IP = "10.10.1"
BANDWIDTH = 100000
IMAGE = 'urn:publicid:IDN+utah.cloudlab.us+image+cuadvnetfall2022-PG0:k8s-flannel:1'

# Set up parameters
pc = portal.Context()
pc.defineParameter("nodeCount",
                   "Number of nodes in the experiment. It is recommended that at least 3 be used.",
                   portal.ParameterType.INTEGER,
                   2)
pc.defineParameter("coreCount",
                   "Number of cores in each worker node.",
                   portal.ParameterType.INTEGER,
                   4)
pc.defineParameter("nodeType",
                   "Master Node Hardware Type",
                   portal.ParameterType.NODETYPE,
                   "m510",
                   longDescription="A specific hardware type to use for node. This profile has primarily been tested with m510 and xl170 nodes.")

pc.defineParameter("startKubernetes",
                   "Create Kubernetes cluster",
                   portal.ParameterType.BOOLEAN,
                   True,
                   longDescription="Create a Kubernetes cluster using default image setup (calico networking, etc.)")

pc.defineParameter("ifExclusive",
                   "Exclusive access to physical node",
                   portal.ParameterType.BOOLEAN,
                   True,
                   longDescription="If the physical node that hosted vm should be exclusive")

pc.defineParameter("workerRAM",
                   "RAM in MB for every worker node",
                   portal.ParameterType.INTEGER,
                   4096,
                   longDescription="Allocated RAM volumn for each worker node")
pc.defineParameter("corePerVM",
                   "allocated core for every worker node",
                   portal.ParameterType.INTEGER,
                   1,
                   longDescription="How many cores does each vm worker node have")

# Below option copy/pasted directly from small-lan experiment on CloudLab
# Optional ephemeral blockstore
pc.defineParameter("tempFileSystemSize",
                   "Temporary Filesystem Size",
                   portal.ParameterType.INTEGER,
                   5,
                   advanced=True,
                   longDescription="The size in GB of a temporary file system to mount on each of your " +
                   "nodes. Temporary means that they are deleted when your experiment is terminated. " +
                   "The images provided by the system have small root partitions, so use this option " +
                   "if you expect you will need more space to build your software packages or store " +
                   "temporary files. 0 GB indicates maximum size.")

params = pc.bindParameters()

pc.verifyParameters()
request = pc.makeRequestRSpec()


def create_worker(name, nodes, pnode, lan):
    # Create node
    node = request.XenVM(name)
    node.cores = params.corePerVM
    node.ram = params.workerRAM
    node.disk_image = IMAGE
    node.exclusive = params.ifExclusive
    # Add interface
    iface = node.addInterface("if1")
    iface.addAddress(rspec.IPv4Address("{}.{}".format(
        BASE_IP, 1 + len(nodes)), "255.255.255.0"))
    lan.addInterface(iface)

    # Add extra storage space
    bs = node.Blockstore(name + "-bs", "/mydata")
    bs.size = str(params.tempFileSystemSize) + "GB"
    bs.placement = "any"

    # Add to node list
    if params.ifExclusive:
        node.InstantiateOn(pnode)
    nodes.append(node)


def create_master(name, nodes, lan):
    # Create node
    node = request.RawPC(name)
    node.disk_image = IMAGE
    node.hardware_type = params.nodeType

    # Add interface
    iface = node.addInterface("if1")
    iface.addAddress(rspec.IPv4Address("{}.{}".format(
        BASE_IP, 1 + len(nodes)), "255.255.255.0"))
    lan.addInterface(iface)

    # Add extra storage space
    bs = node.Blockstore(name + "-bs", "/mydata")
    bs.size = str(params.tempFileSystemSize) + "GB"
    bs.placement = "any"

    # Add to node list
    nodes.append(node)


nodes = []
lan = request.LAN()
# lan.bandwidth = BANDWIDTH
# if params.sameSwitch:
#     lan.setNoInterSwitchLinks()
# Create nodes
# The start script relies on the idea that the primary node is 10.10.1.1, and subsequent nodes follow the
# pattern 10.10.1.2, 10.10.1.3, ...

create_master("node1", nodes, lan)

total_cores = (params.nodeCount - 1) * params.coreCount

node_id = 2
for i in range(1, params.nodeCount):
    pnode = None
    if params.ifExclusive:
        pnode = request.RawPC("pnode" + str(i))
        pnode.hardware_type = params.nodeType
        # iface = pnode.addInterface("if1")
        # iface.addAddress(rspec.IPv4Address("{}.{}".format(
        #     BASE_IP, 1 + total_cores + i), "255.255.255.0"))
        # lan.addInterface(iface)

    for c in range(params.coreCount):
        name = "node" + str(node_id)
        node_id += 1
        create_worker(name, nodes, pnode, lan)

# Iterate over secondary nodes first
for i, node in enumerate(nodes[1:]):
    node.addService(rspec.Execute(shell="bash", command="/local/repository/start.sh secondary {}.{} {} > /home/k8s-flannel/start.log 2>&1 &".format(
        BASE_IP, i + 2, params.startKubernetes)))

# Start primary node
nodes[0].addService(rspec.Execute(shell="bash", command="/local/repository/start.sh primary {}.1 {} {} > /home/k8s-flannel/start.log 2>&1".format(
    BASE_IP, total_cores + 1, params.startKubernetes)))

pc.printRequestRSpec()
