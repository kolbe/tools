# print password and addresses for all seats and instances
jq '.seats[] | {password, instances}' < instances.json

# output key of last seat in a file to "key"
jq -r '.seats[-1]|.key' < instances.json > key

# output list of all subnet Name tags
# there's 1 subnet per course, so this is a good proxy to get a list of existing course IDs
aws ec2 describe-subnets --filters Name=tag:CourseId,Values='my-class-*' | jq -r '.Subnets[] | .Tags[] | select(.Key=="CourseId") | .Value'

# all running ec2 instances
aws ec2 describe-instances --filters Name=instance-state-name,Values=running
