#!/usr/bin/env bash
psmysql () { pids=($(pgrep -x mysqld)) && ps -o pid,user,rss,%cpu,command -p "${pids[@]}" | perl -pe 's#(^\s*\d+)(.*)#'"$(tput setaf 6; tput bold)"'\1'"$(tput sgr0; tput setaf 7)"'\2'"$(tput sgr0; tput setaf 7)"'#;s#(^.*?/)(\w+-\d\d?\.\d?\.\d\d?)(-.*$)#\1'"$(tput setaf 2; tput bold)"'\2'"$(tput sgr0; tput setaf 7)"'\3'"$(tput sgr0)"'#g; END{print "'"$(tput sgr0)"'";}'; }

my_status_diff() { egrep -h "$1" "${@:2}" | deltas -h | column -t; }

my_cnf() { 
    local debug=${debug:-0}
    local id
    re='^[0-9]+$'
    if [[ $1 =~ $re ]]; then
        id=$1
        shift
    fi
    local hostname=$(hostname)
    local cwd=${PWD##*/}

    local product=${cwd%%-*}

    local version=${cwd#*-}
    version=${version%%-*}
    version=${version//./}

    my_base_port=${my_base_port:-${version}0}
    if ((my_base_port > 65500)); then
        my_base_port=${my_base_port:0:1}${my_base_port:2}
    fi

    ((debug)) &&
        for v in hostname cwd version my_base_port; do 
            printf "# [DEBUG] %s %s\n" "$v" "${!v}" >&2
        done


    [[ -n $id ]] && local prompt_id=" $id"
    local prompt="$product\_\v\_(\u)\_[\d]${prompt_id}>\_"
    cat <<EoCNF
[client]
socket=./data$id/mysql.sock
user = root
password = ''
[mysql]
prompt=$prompt
database=test
[mysqld]
basedir=$PWD
pid-file=${hostname}.pid
socket=./mysql.sock

log-error=${hostname}.err
loose-log-basename=${hostname}

log-bin
log-slave-updates
binlog-format=row

datadir=data$id
server-id=$((0+id))
port=$((my_base_port+id))

loose-skip-slave-start
loose-innodb-file-per-table
loose-debug-gdb

lower_case_table_names=2

loose-feedback=ON
EoCNF
    (($#)) && for f in "$@"; do echo "# from file $f"; cat "$f"; done
}
alias mcnf=my_cnf

my_init() { 
    pids=()
    dirs=($@)
    (($# == 0)) && dirs=("")
    for d in "${dirs[@]}"; do
        datadir=data$d
        echo "running mysql_install_db for $datadir..."
        mkdir -p "$datadir"
        rm -rf "$datadir"/*
        ./scripts/mysql_install_db --datadir="$datadir" --skip-log-bin >/dev/null 2>&1 &
        pids+=($!)
    done
    wait "${pids[@]}"
}

#my_start() { eval "$(for i in "$@"; do echo mysqld_safe --port=1000$i --server-id=$i --datadir=data$i '&'; done)"; }
my_start() { 
    re_numeric='^[0-9]+$'
    srvs=()
    extras=()
    args=()
    while (($#)); do
        if [[ $1 =~ $re_numeric ]]; then srvs+=($1)
        elif [[ $1 = --* ]]; then args+=($1)
        else extras+=($1)
        fi
        shift
    done
    #printf "server %s\n" "${srvs[@]}"
    #printf "arg %s\n" "${args[@]}"
    #printf "extra %s\n" "${extras[@]}"
    my_cnf_args=(my_cnf)
    ((${#srvs[@]})) && my_cnf_args[1]=''
    my_cnf_args+=("${extras[@]}")
    eval "$(
        for ((i=0;i==0 || i<${#srvs[@]};i++)); do
            ((${#srvs[@]})) && my_cnf_args[1]="${srvs[i]}"
            echo "$(printf %q "$PWD/bin/mysqld")" --defaults-file=\<\(${my_cnf_args[*]}\) "${args[@]}" '&'
        done)"
}

#my_client() { eval "$(echo mysql -S ./data$1/mysql.sock --prompt='"'node$1\ [\\d]'> "')"; }
my_client() {
    id=$1
    shift
    eval "$(
        echo mysql --defaults-file=\<\(my_cnf $id\) 
    ) $(
        (($#)) && printf '%q ' "$@"
    )"
}
alias m=my_client

my_remote_unpack () { ( set -x; ssh "$1" 'tar -C mysql/ --exclude="mysql-test" --exclude="bin/*test*" --exclude="bin/mysql_embedded" --exclude="lib/libmysqld*" -xzf -' < "$2"; ); }

comdump () { mysqldump --compact "$@" | grep -v '^\/\*\!'; }

my_pid () { while read -r ln; do [[ $ln = n* ]] && dir="${ln:1}"; done < <(lsof -d cwd -a -p $1 -Fn) && cd "$dir/../" && "./bin/mysql" -S "$dir/mysql.sock"; }

ec2-galera-ips() { joinargs $(ec2-ls -n galera -q -o privateIpAddress); }
