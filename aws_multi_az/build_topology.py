#!/usr/bin/env python3
import boto3, ipaddress, os, sys, yaml
from collections import defaultdict

if os.getenv('CLUSTER_NAME'):
    cluster_name = os.getenv('CLUSTER_NAME')
else:
    print("Set the CLUSTER_NAME environment variable before using this tool")
    sys.exit(1)

ec2 = boto3.client('ec2')

instance_info = ec2.describe_instances(Filters = [        {
    'Name': 'tag:Name', 'Values': [ cluster_name, ] },])

instance_details = defaultdict(list)
# [d[i['Placement']['AvailabilityZone']].append(i) for r in [r['Instances'] for r in instance_info['Reservations']] for i in r]
for r in instance_info['Reservations']:
    for i in r['Instances']:
        instance_details[i['Placement']['AvailabilityZone']].append(i)

template_yaml = '''
global:
  user: "ubuntu"
  ssh_port: 22
  deploy_dir: "/home/ubuntu/tidb-deploy"
  data_dir: "/home/ubuntu/tidb-data"
server_configs:
  pd:
    replication.location-labels: ["zone"]
pd_servers: []
tidb_servers: []
tikv_servers: []
tiflash_servers: []
monitoring_servers: []
grafana_servers: []
alertmanager_servers: []
'''

template = yaml.safe_load(template_yaml)

def host(instance, **kwargs):
	return {'host':instance['PrivateIpAddress'], **kwargs}

management_node=''
for k in sorted(instance_details.keys()):
    for i, instance in enumerate(sorted(instance_details[k], key=lambda x: ipaddress.ip_address(x['PrivateIpAddress']))):
        # First node will be our "management node", where TiUP and monitoring will be installed
        if management_node == '':
            for section in ['monitoring_servers', 'grafana_servers', 'alertmanager_servers']:
                management_node = instance['PublicIpAddress']
                template[section].append(host(instance)) 
        # After management node is defined, the "first" node in each AZ will be a tidb/pd node
        elif i==0:
            for section in ['tidb_servers', 'pd_servers']:
                template[section].append(host(instance)) 
        # All other nodes will be tikv nodes
        else:
            template['tikv_servers'].append(host(instance, config={'server.labels': {'zone': instance['Placement']['AvailabilityZone']}}))

print(yaml.dump(template))
print('ssh -o StrictHostKeyChecking=accept-new -l {} {}'.format('ubuntu', management_node), file=sys.stderr)
print('curl --proto =https --tlsv1.2 -sSf https://tiup-mirrors.pingcap.com/install.sh | sh', file=sys.stderr)
