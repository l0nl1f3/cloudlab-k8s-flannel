
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

BASE_IP = "10.10.1"
BANDWIDTH = 100000
IMAGE = 'urn:publicid:IDN+utah.cloudlab.us+image+cuadvnetfall2022-PG0:k8s-flannel:1'

# Set up parameters
pc = portal.Context()
pc.defineParameter("nodeCount",
                   "Number of nodes in the experiment. It is recommended that at least 3 be used.",
                   portal.ParameterType.INTEGER,
                   3)

pc.defineParameter("masterNodeType",
                   "Master Node Hardware Type",
                   portal.ParameterType.NODETYPE,
                   "m510",
                   longDescription="A specific hardware type to use for master node. This profile has primarily been tested with m510 and xl170 nodes.")

pc.defineParameter("startKubernetes",
                   "Create Kubernetes cluster",
                   portal.ParameterType.BOOLEAN,
                   True,
                   longDescription="Create a Kubernetes cluster using default image setup (calico networking, etc.)")

pc.defineParameter("workerRAM",
                   "RAM in MB for every worker node",
                   portal.ParameterType.INTEGER,
                   8192,
                   longDescription="Allocated RAM volumn for each worker node")

# Below option copy/pasted directly from small-lan experiment on CloudLab
# Optional ephemeral blockstore
pc.defineParameter("tempFileSystemSize",
                   "Temporary Filesystem Size",
                   portal.ParameterType.INTEGER,
                   0,
                   advanced=True,
                   longDescription="The size in GB of a temporary file system to mount on each of your " +
                   "nodes. Temporary means that they are deleted when your experiment is terminated. " +
                   "The images provided by the system have small root partitions, so use this option " +
                   "if you expect you will need more space to build your software packages or store " +
                   "temporary files. 0 GB indicates maximum size.")

pc.defineParameter("sameSwitch",  "No Interswitch Links", portal.ParameterType.BOOLEAN, False,
                   advanced=True,
                   longDescription="Sometimes you want all the nodes connected to the same switch. " +
                   "This option will ask the resource mapper to do that, although it might make " +
                   "it imppossible to find a solution. Do not use this unless you are sure you need it!")

params = pc.bindParameters()

pc.verifyParameters()
request = pc.makeRequestRSpec()


def create_worker(name, nodes, lan):
    # Create node
    node = request.XenVM(name)
    node.cores = 1
    node.ram = params.workerRAM
    node.disk_image = IMAGE
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


def create_master(name, nodes, lan):
    # Create node
    node = request.RawPC(name)
    node.disk_image = IMAGE
    node.hardware_type = params.masterNodeType

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
lan.bandwidth = BANDWIDTH
# if params.sameSwitch:
#     lan.setNoInterSwitchLinks()
# Create nodes
# The start script relies on the idea that the primary node is 10.10.1.1, and subsequent nodes follow the
# pattern 10.10.1.2, 10.10.1.3, ...

create_master("node1", nodes, lan)

for i in range(1, params.nodeCount):
    name = "node"+str(i+1)
    create_worker(name, nodes, lan)

# Iterate over secondary nodes first
for i, node in enumerate(nodes[1:]):
    node.addService(rspec.Execute(shell="bash", command="/local/repository/start.sh secondary {}.{} {} > /home/k8s-flannel/start.log 2>&1 &".format(
        BASE_IP, i + 2, params.startKubernetes)))

# Start primary node
nodes[0].addService(rspec.Execute(shell="bash", command="/local/repository/start.sh primary {}.1 {} {} > /home/k8s-flannel/start.log 2>&1".format(
    BASE_IP, params.nodeCount, params.startKubernetes)))

pc.printRequestRSpec()
