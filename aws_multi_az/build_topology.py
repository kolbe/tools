#!/usr/bin/env python3
import ipaddress, os, sys
from collections import defaultdict

import argparse

import boto3
import yaml
import json

parser = argparse.ArgumentParser(description='Build topology.yaml file')

parser.add_argument('-o', '--operating-system', type=str,
        help='The operating system type, of: [ ubuntu , centos ]',
        default='ubuntu')

args = parser.parse_args()

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

management_node={}
for k in sorted(instance_details.keys()):
    for i, instance in enumerate(sorted(instance_details[k], key=lambda x: ipaddress.ip_address(x['PrivateIpAddress']))):
        # First node will be our "management node", where TiUP and monitoring will be installed
        if not management_node:
            for section in ['monitoring_servers', 'grafana_servers', 'alertmanager_servers']:
                management_node = {
                    'public_ip': instance['PublicIpAddress']
                  , 'ec2_id': instance['InstanceId']
                }
                template[section].append(host(instance))
        # After management node is defined, the "first" node in each AZ will be a tidb/pd node
        elif i==0:
            for section in ['tidb_servers', 'pd_servers']:
                template[section].append(host(instance))
        # All other nodes will be tikv nodes
        else:
            template['tikv_servers'].append(host(instance, config={'server.labels': {'zone': instance['Placement']['AvailabilityZone']}}))

username = ''
if args.operating_system == 'ubuntu':
    username = 'ubuntu'
elif args.operating_system == 'centos':
    username = 'ec2-user'
else:
    username = args.operating_system
    print('Unsupported OS: {0} - please check global settings: [ user , deploy_dir , data_dir ]'.format(args.operating_system))

template['global']['user'] = username
template['global']['deploy_dir'] = '/home/{0}/tidb-deploy'.format(username)
template['global']['data_dir'] = '/home/{0}/tidb-data'.format(username)

print(yaml.dump(template))

print('scp topology.yaml {0}@{1}:~'.format(username, management_node['public_ip']), file=sys.stderr)
print("\n")

print('echo \'curl --proto =https --tlsv1.2 -sSf https://tiup-mirrors.pingcap.com/install.sh | sh\' |', file=sys.stderr)
print('ssh -o StrictHostKeyChecking=accept-new {}@{}'.format(username, management_node['public_ip']), file=sys.stderr)
print("\n")

print('rsync -av ~/.ssh {0}@{1}:~'.format(username, management_node['public_ip']), file=sys.stderr)
print('rsync -av ~/.aws {0}@{1}:~'.format(username, management_node['public_ip']), file=sys.stderr)
print("\n")

print('echo \'wget https://download.pingcap.org/tidb-toolkit-v5.2.1-linux-amd64.tar.gz\' |', file=sys.stderr)
print('ssh -o StrictHostKeyChecking=accept-new {}@{}'.format(username, management_node['public_ip']), file=sys.stderr)
print("\n")

print('Management node ec2 instance id: [{0}]'.format(management_node['ec2_id']), file=sys.stderr)
