#!/usr/bin/env bash

if (( $# == 0 )); then
    echo >&2 "Please provide at least 1 course_id"
    exit 1
fi

export PAGER=cat

for course_id; do
    echo "Deleting resources for CourseId $course_id"

    filters=(
        Name=tag:CourseId,Values="$course_id"
    )

    mapfile -t instance_ids < <(
        aws ec2 describe-instances \
            --filter Name=instance-state-name,Values=running \
                     "${filters[@]}" \
            --query 'Reservations[].Instances[].[InstanceId]' --output text
    )

    if [[ "${#instance_ids[@]}" -gt 0 ]]; then
        echo "${instances_ids[*]}"
        aws ec2 terminate-instances --instance-id "${instance_ids[@]}"
        aws ec2 wait instance-terminated --instance-ids "${instance_ids[@]}"
    fi

    aws ec2 describe-security-groups --filter "${filters[@]}" \
        --query 'SecurityGroups[].[GroupId]' --output text |
        while read -r k; do
            echo "$k"
            aws ec2 delete-security-group --group-id "$k"
        done

    aws ec2 describe-key-pairs --filter "${filters[@]}" \
        --query 'KeyPairs[].[KeyName]' --output text |
        while read -r k; do
            echo "$k"
            aws ec2 delete-key-pair --key-name "$k"
        done

    aws ec2 describe-subnets --filter "${filters[@]}" \
        --query 'Subnets[].[SubnetId]' --output text |
        while read -r s; do
            echo "$s"
            aws ec2 delete-subnet --subnet-id "$s"
        done
done
