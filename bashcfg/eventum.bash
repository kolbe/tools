export eventum_issue_root=$HOME/Documents/MariaDB/issue

# fetch bunches of files for an issue, using current dir
# as the issue number. for example:
# cd 9044; ev-gf {2..38}
# or: mkdir newlogs && ev-gf newlogs 3 4 5
ev-gf () { 
    issue=${PWD##*/}
    # if you provide a first argument that doesn't start
    # with a number, ev-gf will cd there before downloading
    if ! [[ $1 = [0-9]* ]]; then
        dest=$1
        dest=${dest##*=}
        if ! cd "$dest"; then
            echo "ERROR: couldn't cd to $dest"
            return 1
        fi
        shift
        echo "Downloading to '$dest'"
    fi
    for i in "$@"; do 
        ev "$issue" gf "$i"
    done
}

# eve uses the current directory (e.g. "9044")
# as the issue number to work on
eve () { 

    ev "${PWD##*/}" "$@"
}

# this creates a directory for your issue and switches to it
evi() {
    i=$1
    shift
    d=$eventum_issue_root/$i
    mkdir -p "$d" 
    if ! cd "$d"; then
        echo "[ERROR] could not create and change to '$d'" >&2
        return 1
    fi
    #ev "$i" &
}
