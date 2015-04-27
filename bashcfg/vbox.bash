vbox_suspend_all() {
    VBoxManage list runningvms | while 
        IFS=\" read -r _ vm _; do 
            printf "suspending $vm "
            VBoxManage controlvm "${vm//\"/}" savestate
        done
}

vbox_start() {
    for vm in "$@"; do 
        VBoxManage startvm "$vm" --type=headless
    done
}

vbox_control(){ action=$1; shift; for vm in "$@"; do echo "${action}'ing $vm"; VBoxManage controlvm "$vm" "$action"; done; }

vboxls(){ 
    net=0
    while :; do
        [[ $1 ]] || break
        case $1 in
            -n|--net)
                net=1
                ;;
            *)
                continue
                ;;
        esac
        shift
    done
    VBoxManage list runningvms
    ((net)) && nmap -sn -n 192.168.30.255/24
}
