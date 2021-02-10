#!/bin/bash

TORRENT_PATH="$1"
TORRENT_NAME="$2"

export PYTHONUNBUFFERED=1

#. /home/user/.bash_qbittorrentapi_defaults.sh

$HOME/python/turbo-potato/venv/bin/python $HOME/python/turbo-potato/run.py --non_interactive -t "$TORRENT_PATH" > "$HOME/znp_logs/$TORRENT_NAME.txt" 2>&1
