#!/usr/bin/env python3

import os
import sys

import boto3
ec2 = boto3.client('ec2')

cluster_name = os.getenv('CLUSTER_NAME')
if not cluster_name:
    print('CLUSTER_NAME not defined in environment')
    sys.exit(1)

print('Deleting resources for CLUSTER_NAME={}'.format(cluster_name))

cluster_name_filter=[ {'Name':'tag:Name', 'Values':[cluster_name]} ]

instances = ec2.describe_instances(
        Filters=cluster_name_filter
            # [{'Name':'instance-state-name', 'Values':['running']}]
            )
instance_ids=[]
for r in instances['Reservations']:
    for i in r['Instances']:
        instance_ids.append(i['InstanceId'])
if instance_ids:
    print(ec2.terminate_instances( InstanceIds=instance_ids ))

    print('Waiting for all instances to be "terminated"...')
    waiter = ec2.get_waiter('instance_terminated')
    waiter.wait(InstanceIds=instance_ids)

subnets = ec2.describe_subnets(Filters=cluster_name_filter)
for s in subnets['Subnets']:
    print(ec2.delete_subnet(SubnetId=s['SubnetId']))

security_groups = ec2.describe_security_groups(Filters=cluster_name_filter)
for sg in security_groups['SecurityGroups']:
    print(ec2.delete_security_group(GroupId=sg['GroupId']))
