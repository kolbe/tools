#!/usr/bin/env python3
'''
deploy_instances.py is a simple program to deploy a set of instances to AWS EC2

Consult README.md for more information.
'''

import argparse
import ipaddress
import os
import sys
import time
import urllib.request
from collections import defaultdict

import boto3
import botocore.exceptions

def comma_list(values):
    '''
    comma_list() is used to represent a type for the --availability-zones argument
    '''
    return values.split(',')

parser = argparse.ArgumentParser(description='Deploy multi-AZ resources to AWS')
parser.add_argument('-k', '--key-name', type=str,
        help='The name of the EC2 keypair you will use to connect to the instances', required=True)
parser.add_argument('-n', '--cluster-name', type=str,
        help='The Name tag of the resources we deploy (default %(default)s)',
        default=os.getenv('USER')+"-tiup-multi-az-"+time.strftime('%s'))
parser.add_argument('--vpc-id', type=str, help='The ID of the VPC you want to deploy to')
parser.add_argument('--availability-zones', type=comma_list,
        help='Comma-separated list of AZs to deploy to ' +
             '(default %(default)s)',
        default='us-west-2a,us-west-2b,us-west-2c,us-west-2d')
parser.add_argument('--owner-tag', type=str,
        help='The string used as the Owner tag on the resources ' +
             '(default %(default)s)', default=os.getenv('USER'))
parser.add_argument('--instances-per-az', type=int,
        help='The number of instances per AZ (default %(default)d)', default=3)
parser.add_argument('--instance-ami', type=str,
        help='The EC2 instance AMI to use (default %(default)s)', default='ami-038a0ccaaedae6406')
parser.add_argument('--instance-type', type=str,
        help='The EC2 instance type to use (default %(default)s)', default='m5.2xlarge')
parser.add_argument('--subnet-offset', type=int,
        help='Set this to a positive integer if you need to avoid some ' +
             'IP ranges already allocated to existing subnets', default=1)
parser.add_argument('--subnet-prefix', type=int,
        help='The CIDR prefix for the new subnets created (default %(default)d)', default=24)
parser.add_argument('--disk-size', type=int,
        help='Size in GB of root EBS volume (default %(default)d)', default=64)
parser.add_argument('--public-ip', type=str,
        help='This IP address will have unrestricted TCP and UDP ' +
             'access to all instances (default %(default)s)',
        default=urllib.request.urlopen('http://icanhazip.com',
            timeout=1).read().decode('utf-8').strip() + '/32')
parser.add_argument('--vpc-cidr', type=str,
        help=argparse.SUPPRESS, default='10.0.0.0/16')

args = parser.parse_args()

ec2 = boto3.client('ec2')

print('Creating cluster {}'.format(args.cluster_name))

if not any( key['KeyName']==args.key_name for key in ec2.describe_key_pairs()['KeyPairs'] ):
    print('KeyPair "{}" could not be found'.format(args.key_name), file=sys.stderr)
    sys.exit(1)

if args.vpc_id:
    vpc = [vpc for vpc in ec2.describe_vpcs()['Vpcs'] if vpc['VpcId']==args.vpc_id]
    if len(vpc):
        args.vpc_cidr = vpc[0]['CidrBlock']
    else:
        print('VPC "{}" could not be found'.format(args.vpc_id), file=sys.stderr)
        sys.exit(1)
    vpc_id = args.vpc_id
    print(vpc_id + ' (from command-line option)')
else:
    vpc = ec2.describe_vpcs(Filters=[{'Name':'isDefault', 'Values':['true']}])['Vpcs'][0]
    args.vpc_id = vpc['VpcId']
    args.vpc_cidr = vpc['CidrBlock']
    vpc_id = args.vpc_id
    print(vpc_id + ' (from default)')

tags = [ {'Key': 'Owner', 'Value': args.owner_tag},
        {'Key': 'Name', 'Value': args.cluster_name} ]

# vpc creation is a minefield because of very low VPC limits and internet gateway creation
'''
vpc_template = {
        'CidrBlock': args.vpc_cidr,
        'TagSpecifications':[{'ResourceType': 'vpc', 'Tags': tags, }]
}

else:
    vpc = ec2.create_vpc( **vpc_template )
    vpc_id = vpc['Vpc']['VpcId']
    print(vpc_id)
    waiter = ec2.get_waiter('vpc_available')
    waiter.wait(VpcIds=[vpc_id])
'''


# This will throw an Exception of any of the provided AZ names are bogus
ec2.describe_availability_zones(ZoneNames=args.availability_zones)

#print(args)
#sys.exit(1)



subnets=[]
subnet_ranges = list(ipaddress.ip_network(args.vpc_cidr).subnets(new_prefix=args.subnet_prefix))
for i, az in enumerate(args.availability_zones, start=1):
    subnet_template = {
            'AvailabilityZone': az,
            'CidrBlock': subnet_ranges[args.subnet_offset + i].exploded,
            'TagSpecifications':[{'ResourceType': 'subnet', 'Tags': tags, }],
            'VpcId': vpc_id
    }
    try:
        subnet = ec2.create_subnet(**subnet_template)
    except botocore.exceptions.ClientError as error:
        if error.response['Error']['Code'] == 'InvalidSubnet.Conflict':
            subnets = ec2.describe_subnets(Filters=[{'Name':'vpcId','Values':[vpc_id]}])['Subnets']
            print(error, file=sys.stderr)
            cidr_blocks = [s['CidrBlock'] for s in subnets]
            print('These are the existing subnets in VPC {}: {}'.format(
                args.vpc_id, ', '.join(sorted(cidr_blocks))), file=sys.stderr)
            # Try to see if all the existing subnets have the same prefix!
            # If so, we can safely calculate the next address. If not... *shrug* ...?
            p = None
            for c in cidr_blocks:
                n = ipaddress.ip_network(c)
                if p is None:
                    p = n.prefixlen
                elif n.prefixlen != p:
                    print('Existing subnets have inconsistent prefix, please create a new VPC')
                    sys.exit(1)
            print('Try --subnet-offset={}'.format(
                pow(2,(32-p))*len(subnets) // pow(2,32-args.subnet_prefix) ), file=sys.stderr)
            sys.exit(1)
        else:
            raise error

    print(subnet['Subnet']['SubnetId'])
    subnets.append(subnet['Subnet']['SubnetId'])
waiter = ec2.get_waiter('subnet_available')
waiter.wait(SubnetIds=subnets)

sg = ec2.create_security_group(
        VpcId = vpc_id,
        Description = args.cluster_name,
        GroupName = args.cluster_name,
        TagSpecifications=[{'ResourceType': 'security-group', 'Tags': tags, }],
)
sg_id = sg['GroupId']
print(sg_id)

sg_ingress_template = {
        'GroupId': sg_id,
        'IpPermissions': [
            {'IpProtocol': '-1',
                'IpRanges': [{'CidrIp': args.public_ip }],
                'UserIdGroupPairs': [{'GroupId': sg_id}],
                },
            {'FromPort': 22,
                'IpProtocol': 'tcp',
                'IpRanges': [{'CidrIp': '0.0.0.0/0'}],
                'Ipv6Ranges': [{'CidrIpv6': '::/0'}],
                'PrefixListIds': [],
                'ToPort': 22,
                'UserIdGroupPairs': []}
            ],
        }
ec2.authorize_security_group_ingress(**sg_ingress_template)

instance_template = {
        'InstanceType': args.instance_type,
        'KeyName': args.key_name ,
        'ImageId': args.instance_ami,
        'TagSpecifications': [{'ResourceType': 'instance', 'Tags': tags }],
        'BlockDeviceMappings': [{
            'DeviceName': '/dev/sda1',
            'Ebs': {
                'DeleteOnTermination': True,
                #'SnapshotId': 'snap-09d3a0caf8c20b475',
                'VolumeSize': args.disk_size,
                'VolumeType': 'gp2'
            }}],
        'NetworkInterfaces': [{
            'Groups': [sg_id],
            'AssociatePublicIpAddress': True,
            'DeleteOnTermination': True,
            'DeviceIndex': 0,
            'SubnetId': None,
            'NetworkCardIndex': 0
        }],
        'MinCount': args.instances_per_az,
        'MaxCount': args.instances_per_az
    }

instances=[]
for subnet in subnets:
    instance_template['NetworkInterfaces'][0]['SubnetId'] = subnet
    inst = ec2.run_instances( **instance_template )
    for i in inst['Instances']:
        print(i['InstanceId'])
        instances.append(i['InstanceId'])
print('Waiting for all instances to be "running"...')
waiter = ec2.get_waiter('instance_running')
waiter.wait(InstanceIds=instances)

print('Instances of cluster "{}" deployed!'.format(args.cluster_name))

instance_info = ec2.describe_instances(InstanceIds=instances)
instance_details = defaultdict(list)
for r in instance_info['Reservations']:
    for i in r['Instances']:
        instance_details[i['Placement']['AvailabilityZone']].append(i)
for k in sorted(instance_details.keys()):
    for i, instance in enumerate(
            sorted(instance_details[k],
                key=lambda x: ipaddress.ip_address(x['PrivateIpAddress']))):
        print('{}\t{}\t{}\t{}'.format(
            instance['PrivateIpAddress'],
            instance['PublicIpAddress'],
            instance['InstanceId'],
            instance['Placement']['AvailabilityZone']))

print('export CLUSTER_NAME={}'.format(args.cluster_name))
