destroy_resources()(
    export PAGER=cat

    if ! declare -p resources &>/dev/null; then
        echo >&2 "Reading list of resources from stdin"
        mapfile -t resources
    fi

    if ! (( ${#resources[@]} )); then
        echo >&2 "No resources specified."
        exit 1
    fi

    local -a instances
    for r in "${resources[@]}"; do
        if [[ $r = i-* ]]; then
            instances+=($r)
        fi
    done

    if (( ${#instances[@]} )); then
        aws ec2 terminate-instances --instance-ids "${instances[@]}"
        printf "Waiting for instances to be terminated... (%s)\n" "${instances[*]}"
        aws ec2 wait instance-terminated --instance-ids "${instances[@]}"
    fi

    for r in "${resources[@]}"; do
        if [[ $r = subnet-* ]]; then
            printf "Deleting subnet %s\n" "$r"
            aws ec2 delete-subnet --subnet-id "$r"
        fi
    done

    for r in "${resources[@]}"; do
        if [[ $r = sg-* ]]; then
            printf "Deleting security group %s\n" "$r"
            aws ec2 delete-security-group --group-id "$r"
        fi
    done
)


destroy_resources

echo "checking for remaining resources in CLUSTER_NAME=$CLUSTER_NAME"
aws ec2 describe-instances --filter Name=tag:Name,Values="$CLUSTER_NAME" --filter Name=instance-state-name,Values=running
aws ec2 describe-subnets --filter Name=tag:Name,Values="$CLUSTER_NAME"
aws ec2 describe-security-groups --filter Name=tag:Name,Values="$CLUSTER_NAME"
