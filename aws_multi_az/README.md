# TiUP AWS Multi-AZ Deployment Demo

`deploy_resources.py` deploys a set of subnets, a security group, and 3 instances in each of the specified AZs (by default the 4 AZs in us-west-2). It emits to stdout a list of the IDs of the deployed resources as well as a handy list of information about the private and public IP addresses of the instances created.

Resources deployed:
* 1 security group
** allows all TCP/UDP communication between nodes in the cluster
** allows all TCP/UDP communication from your public IP address to all nodes in the cluster
** allows SSH connections from any IP
* 1 subnet for each AZ in `--availability-zones`
** each of these is in a different AZ
** each of these distributes IPs in different ranges
** if the subnet ranges conflict with your existing subnets, you can edit `subnet_offset` in the program to have it use higher ranges
* `--instances-per-az` x `len(--availability-zones)` instances

`build_topology.py` gets the information about the deployed instances and emits YAML to stdout that can be used by TiUP to deploy a cluster. It emits to stdout some handy commands that can be copied and pasted in order to connect to the "management node" using SSH. You need to set the `CLUSTER_NAME` environment variable so that `build_topology.py` can identify the resources deployed by `deploy_resources.py`.

Recommended usage:

```
./deploy_resources.py --vpc-id=vpc-abc --ssh-key=key-name --cluster-name=my-test-cluster | tee resources
CLUSTER_NAME=my-test-cluster ./build_topology > topology.yaml
```

You are responsible for getting an SSH key onto the management node that will allow it to connect to other nodes in the cluster. You can:
* copy the private key from AWS that is already allowed to connect to the nodes
* create a new private key on the management node using `ssh-keygen` and place that public key in `~/.ssh/authorized_keys` on each node
* use the SSH agent on your local machine along with `ssh -A` to forward the agent socket and propagate the credentials to the management node (note that support for this is not entirely well tested in TiUP; you may need to use `tiup cluster --ssh=system`)
