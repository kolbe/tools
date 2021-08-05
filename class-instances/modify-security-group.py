#!/usr/bin/env python3

import argparse
import ipaddress
import sys

import boto3

parser = argparse.ArgumentParser(description='Adjust existing security group to have ')

parser.add_argument('-s', '--security-group-id', type=str,
        help='The ID of the security group to modify', required=True)

'''
parser.add_argument('--port', type=int, nargs='+',
        help='Port number(s) to open (default %(default)d)', default=[2379,3000,4000])
'''

parser.add_argument('ip_address', type=ipaddress.ip_interface, nargs='*')

args = parser.parse_args()

print('Modifying security group {}'.format(args.security_group_id), file=sys.stderr)

ec2 = boto3.client('ec2')

sg_info = ec2.describe_security_groups(GroupIds=[args.security_group_id])['SecurityGroups'][0]
for ip_perms in sg_info['IpPermissions']:
    if ip_perms['IpProtocol'] == '-1':
        existing_ipv4 = ip_perms['IpRanges']
        existing_ipv6 = ip_perms['Ipv6Ranges']

ipv4_ranges=[]
ipv6_ranges=[]

if not args.ip_address:
    print('Reading IP addresses from stdin', file=sys.stderr)
    for line in sys.stdin:
        line = line.strip()
        try:
            args.ip_address.append(
                    ipaddress.ip_network(line)
                    )
        except ValueError as e:
            print('Error parsing address "{}" from stdin'.format(line), file=sys.stderr)

for ip in args.ip_address:
    cidr = ipaddress.ip_network(ip)
    if type(cidr) == ipaddress.IPv4Network:
        new_ip = {'CidrIp': str(cidr)}
        if new_ip not in existing_ipv4:
            ipv4_ranges.append(new_ip)
        else:
            print('IP {} already allowed to connect'.format(new_ip), file=sys.stderr)
    elif type(cidr) == ipaddress.IPv6Network:
        new_ip = {'CidrIpv6': str(cidr)}
        if new_ip not in existing_ipv6:
            ipv6_ranges.append(new_ip)
        else:
            print('IP {} already allowed to connect'.format(new_ip), file=sys.stderr)

if not (ipv4_ranges or ipv6_ranges):
    print('No new IPs to add', file=sys.stderr)
    sys.exit(0)

sg_ingress_template = {
        'GroupId': args.security_group_id,
        'IpPermissions': [
            {'IpProtocol': '-1',
                'IpRanges': ipv4_ranges,
                'Ipv6Ranges': ipv6_ranges,
                }
			],
		}

print(sg_ingress_template, file=sys.stderr)

ec2.authorize_security_group_ingress(**sg_ingress_template)
