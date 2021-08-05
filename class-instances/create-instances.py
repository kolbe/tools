#!/usr/bin/env python3

import argparse
import ipaddress
import json
import os
import secrets
import sys
import time

import boto3
import passlib.hash
import yaml

# If no explicit instance AMI is given, we look up the most-recent release of
# Ubuntu 20.20 LTS for amd64. Using this most-recent AMI means that we don't
# have to pay attention to their periodic releases or worry too much about 
# packages on the instances being out of date. It does menn that something
# might break, though, but if that happens the user can just give an explicit
# previous AMI ID that is known to work.
def get_default_image_id():
    ssm = boto3.client('ssm')
    return ssm.get_parameters(
        Names=["/aws/service/canonical/ubuntu/server/20.04/stable/current/amd64/hvm/ebs-gp2/ami-id"]
    )['Parameters'][0]['Value']

parser = argparse.ArgumentParser(description='Deploy resources for a group of students')

parser.add_argument('-n', '--num-seats', type=int,
        help='The number of students to create resources for', required=True)
parser.add_argument('-i', '--instances-per-seat', type=int,
        help='The number of instances to create per student (default %(default)d)', default=1)
parser.add_argument('--course-id', type=str,
        help='The ID to identify this specific deployment of resources (default %(default)s)',
        default='my-class-{}'.format(time.strftime('%s')))

parser.add_argument('--vpc-id', type=str,
        help='The ID of the VPC you want to deploy to', required=True)
parser.add_argument('--owner', type=str,
        help='The name of the person responsible for these resources', default=os.getenv('USER'))
parser.add_argument('--instance-ami', type=str, default=get_default_image_id(),
        help='The EC2 instance AMI to use (default latest Ubuntu 20.04 Server AMI: %(default)s)')
parser.add_argument('--instance-ami-user', type=str, default="ubuntu",
        help='The OS username of the default login user: %(default)s)')
parser.add_argument('--instance-type', type=str,
        help='The EC2 instance type to use (default %(default)s)', default='m5d.large')
parser.add_argument('--disk-size', type=int,
        help='Size in GB of root EBS volume (default %(default)d)', default=64)
parser.add_argument('--subnet-offset', type=int,
        help='Subnet offset (default %(default)d)', default=0)

class Seat(dict):
    def __init__(self, key, password, instances):
        dict.__init__(self,
                key=key,
                password=password,
                instances=[instance['InstanceId'] for instance in instances['Instances']],
                addresses=[]
        )

args = parser.parse_args()

# This user_data structure is in a strange place at the top of this file
# because it might be useful to modify this or make it a parameter or
# something in case we want to change the packages installed on the host
user_data = {
        'packages': [
            'haproxy',
            'jq',
            'mariadb-client',
            'net-tools',
            'screen',
            'sysbench',
            'vim',
        ],
        'runcmd': [
            # These commands copy the SSH key for the student from /root to /home/ubuntu
            # so that TiUP can use it to connect to other instances, including back to
            # itself. The file is included in user_data later in this script, after the
            # student's new key-pair is generated.
            'cp /root/.ssh/id_rsa /home/{}/.ssh/id_rsa'.format(args.instance_ami_user),
            'chown {user}:{user} /home/{user}/.ssh/id_rsa'.format(user=args.instance_ami_user),

            # install TiUP
            'curl --proto =https --tlsv1.2 -sSf https://tiup-mirrors.pingcap.com/install.sh | sudo -H -u {} sh'.format(args.instance_ami_user),
            ],
        'ssh_pwauth': True,
        'system_info': {
            'default_user': {
                'lock_passwd': False,
                }
            },
        'write_files': ['SSH_KEY'],
        }

print('Creating resources for course_id {}'.format(args.course_id), file=sys.stderr)

tags = [ {'Key': 'Owner', 'Value': args.owner},
        {'Key': 'CourseId', 'Value': args.course_id} ]

subnet_template = {
        #'AvailabilityZone': az,
        'CidrBlock': None,
        'TagSpecifications':[{'ResourceType': 'subnet', 'Tags': tags, }],
        'VpcId': args.vpc_id
        }

# boto3.set_stream_logger('')
ec2 = boto3.client('ec2')

print('Using AMI {}'.format(args.instance_ami), file=sys.stderr)

# For now, get the list of existing VPCs and loop through them until we find the
# VPC given on the command line.
# TODO: Yeah, it should just filter server-side.
vpc = None
for v in ec2.describe_vpcs()['Vpcs']:
    if v['VpcId']==args.vpc_id:
        vpc=v
if vpc:
    vpc_cidr = vpc['CidrBlock']
else:
    print('VPC "{}" could not be found'.format(args.vpc_id), file=sys.stderr)

# This is some weird "special sauce" to try to find an unused CIDR range that
# can be used for a new subnet. If it's possible to find one, we will simply
# create a subnet and put all instances in it. If the existing subnets are too
# complex, especially if there are existing subnets with different prefix sizes,
# such as "/22" and "/24" together in the same VPC, the math is too difficult,
# and it's best to create a new VPC.
subnet_prefix = 22
subnet_ranges = list(ipaddress.ip_network(vpc_cidr).subnets(new_prefix=subnet_prefix))
if args.subnet_offset == 0:
    subnets = ec2.describe_subnets(Filters=[{'Name':'vpcId','Values':[args.vpc_id]}])['Subnets']
    if subnets:
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
                print('Existing subnets have inconsistent prefix, please create a new VPC',
                        file=sys.stderr)
                sys.exit(1)

        # This formula identifies the next available CIDR range after accounting for
        # existing subnets.
        args.subnet_offset = ( pow(2,(32-p))*len(subnets) // pow(2,32-subnet_prefix) )
print('Trying subnet_offset={}'.format(args.subnet_offset), file=sys.stderr)

subnet_template['CidrBlock'] = subnet_ranges[args.subnet_offset].exploded
subnet = ec2.create_subnet(**subnet_template)['Subnet']
print(subnet['SubnetId'], file=sys.stderr)

sg = ec2.create_security_group(
        VpcId = args.vpc_id,
        Description = args.course_id,
        GroupName = args.course_id,
        TagSpecifications=[{'ResourceType': 'security-group', 'Tags': tags, }],
)
sg_id = sg['GroupId']
print(sg_id, file=sys.stderr)

sg_ingress_template = {
        'GroupId': sg_id,
        'IpPermissions': [
            {'IpProtocol': '-1',
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
        'ImageId': args.instance_ami,
        'TagSpecifications': [{'ResourceType': 'instance', 'Tags': tags }],
        'BlockDeviceMappings': [{
            'DeviceName': '/dev/sda1',
            'Ebs': {
                'DeleteOnTermination': True,
                'VolumeSize': args.disk_size,
                'VolumeType': 'gp2'
                }}],
            'NetworkInterfaces': [{
                'Groups': [sg_id],
                'AssociatePublicIpAddress': True,
                'DeleteOnTermination': True,
                'DeviceIndex': 0,
                'SubnetId': subnet['SubnetId'],
                'NetworkCardIndex': 0
                }],
            'MinCount': args.instances_per_seat,
            'MaxCount': args.instances_per_seat
            }

seats = []
for seat in range(args.num_seats):
    password = secrets.token_urlsafe(18)

    user_data['system_info']['default_user']['passwd'] = \
        passlib.hash.sha512_crypt.hash(password)

    key = ec2.create_key_pair(
            KeyName='{}-{}'.format(args.course_id, seat),
            TagSpecifications=[{'ResourceType': 'key-pair', 'Tags': tags, }],
    )
    user_data['write_files'][0]={
            'path': '/root/.ssh/id_rsa',
            'permissions': '0600',
            'content': key['KeyMaterial']
            }
    instances = ec2.run_instances(
            KeyName = key['KeyName'],
            UserData = '#cloud-config\n' + yaml.dump(user_data),
            **instance_template
            )
    seats.append(Seat(key,password,instances))

# run_instances can only give you the instance ID and private IP, but NOT
# the public IP. So we get the list of created instances, and then we have
# to wait for them to be "running" before we can use describe_instances
# to get their public IP addresses.
instance_ids = []
for seat in seats:
    for instance in seat['instances']:
        instance_ids.append(instance)

print('Waiting for all {} instances to be "running"... ({})'.format(
    len(instance_ids), ", ".join(instance_ids)), file=sys.stderr)

waiter = ec2.get_waiter('instance_running')
waiter.wait(InstanceIds=instance_ids)

instance_info = ec2.describe_instances(InstanceIds=instance_ids)

# it's easier to just build a new dict keyed on InstanceId so we can
# loop through seats later and match the instance IDs associated with the
# seat with the connection information in describe_instances output
instances = {}
for r in instance_info['Reservations']:
    for inst in r['Instances']:
        instances[inst['InstanceId']] = {
                'id': inst['InstanceId'],
                'private': inst['PrivateIpAddress'],
                'public': inst['PublicIpAddress']
        }

for seat in seats:
    for instance in seat['instances']:
        seat['addresses'].append(instances[instance])

# This should be the only output to stdout, so that it can easily be
# redirected to a file and used later to send connection information to
# students.
print( json.dumps({
    'course_id': args.course_id,
    'security_group': sg_id,
    'subnet': subnet['SubnetId'],
    'seats': [
        {
            'key_name': s['key']['KeyName'],
            'key': s['key']['KeyMaterial'],
            'password': s['password'],
            'instances': s['addresses']
        } for s in seats
    ]
}) )
