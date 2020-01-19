import argparse
import json
from pathlib import Path
import os
import sys
import time

from qbittorrentapi import Client

parser = argparse.ArgumentParser()
parser.add_argument('torrent_path', type=str, help='Filepath to torrent')
parser.add_argument('torrent_name', type=str, help='Torrent name')
parser.add_argument('torrent_hash', type=str, help='Torrent hash')
args = parser.parse_args()

with open(Path(__file__).parent / 'qbittorrent_config.txt') as file:
    qbt_config = json.load(file)

qbt = Client(**qbt_config)

upload = False
start_time = time.time()
while True:
    try:
        torrent = qbt.torrents.info(hashes=args.torrent_hash)[0]
    except:
        sys.exit(1)
    else:
        if torrent.state not in ('checkingUP', 'checkingDL', 'downloading', 'stalledDL', 'pausedDL', 'metaDL'):
            upload = True
            break
        if time.time() - start_time > 3600:
            break
        time.sleep(1)

if upload:
    sys.path.append(os.path.abspath(os.path.realpath(Path(__file__).parent.parent)))
    import turbopotato
    turbopotato.run(interactive=False, torrents=True, paths=[args.torrent_path])
