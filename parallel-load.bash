#!/usr/bin/env bash

# Usage: parallel-load <numthreads> <table name> <filename>

# this script takes a number of threads, a table name, and a filename
# it creates FIFOs, determines the size of the file, splits it up into roughly-even chunks,
# and sends one chunk to each FIFO. a number of mysql clients are spawned and a separate
# LOAD DATA INFILE command is executed in each to read from the FIFOs

# put mysql login information in a ~/.my.cnf file or other location where this script can read it

# you can either use database= in a my.cnf file to tell the client what database to use or you can 
# qualify the table name with a database prefix.

threads=$1
shift

table=$1
shift

fifodir="/tmp"

files=("$@")
offsets=(1)
fifos=()

if ! lock_mode=$(mysql -BNe 'select @@innodb_autoinc_lock_mode'); then
    echo "[ERROR] couldn't get server information from MySQL. Aborting." >&2
    exit 1
fi

if [[ $(mysql -BNe "select count(*) from information_schema.tables where concat(table_schema,'.',table_name) in (concat(database(),'.','$table'),'$table')") -ne 1 ]]; then
    echo "[ERROR] table $table not found (or name is ambiguous). Aborting." >&2
    exit 1
fi

if ! has_auto_inc=$(mysql -BNe "select count(*) from information_schema.columns where concat(table_schema,'.',table_name) in (concat(database(),'.','$table'),'$table')  and extra like '%auto_increment%'"); then
    echo "[ERROR] couldn't get table information from MySQL. Aborting." >&2
    exit 1
fi

if ((has_auto_inc && lock_mode != 2)); then
    echo "[ERROR] $table has an auto-inc column and innodb_autoinc_lock_mode is not 2 (\"interleaved\"). Parallel threads will be blocked." >&2
    exit 2
fi


for ((t=0;t<threads;t++)); do
    fifos+=("$fifodir/parallel_load_$$_$t.fifo")
    if ! mkfifo "${fifos[t]}"; then
        echo "[ERROR] failed to create fifo #$t: $f. Aborting." >&2
        exit 3
    fi
done

for f in "${files[@]}"; do 
    if ! [[ -f "$f" ]]; then
        echo "[ERROR] could not read file $f. Aborting." >&2
        exit 1
    fi
    read -r size _ < <(wc -c "$f")
    chunk_size=$((size / threads))
    printf "%i bytes total\n%i bytes per chunk\n%i threads\n" "$size" "$chunk_size" "$threads"
    for ((t=0;t<threads;t++)); do
        guess=$((offsets[t] + chunk_size))
        IFS='' read -r extra < <(tail -c +"$guess" "$f")
        extra_bytes=$((${#extra} + 1)) # account for newline
        offsets+=($((guess + extra_bytes)))
    done

    for ((o=0;o<"${#offsets[@]}"-1;o++)); do
        start=${offsets[o]}
        bytes=$((${offsets[o+1]} - start))
        fifo=${fifos[o]}
        tail -c +"$start" "$f" | head -c "$bytes" >> "$fifo" &
        printf "Thread #%i reading from %i for %i bytes in PID %i" "$o" "$start" "$bytes" "$!"
        mysql -e "LOAD DATA INFILE '$fifo' INTO TABLE $table" &
        #cat "$fifo" > "part$o.csv" 
        printf " executed by mysql client PID %i\n" "$!"
        last_client=$!
    done

done

echo "Waiting for PID $last_client to finish..." && wait $last_client

for fifo in "${fifos[@]}"; do
    if ! rm "$fifo"; then
        echo "[WARNING] failed to remove fifo: $fifo" >&2
    fi
done

