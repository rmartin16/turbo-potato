#!/usr/bin/env python3

from qbittorrentapi import Client
from qbittorrentapi import APIError
from time import time

try:
    qbt_client = Client(VERIFY_WEBUI_CERTIFICATE=False,
                        host='localhost:8080',
                        username='admin',
                        password='adminadmin')

    # for each torrent marked as uploaded
    for torrent in qbt_client.torrents.info(category='uploaded'):
        # wait for torrent to reach seeding ratio
        try:
            if torrent.state == "pausedUP":
                torrent.delete(delete_files=True)
                print("uploaded and paused: %s" % torrent.name)
                # delete if torrent added over two weeks ago
            elif (time() - torrent.added_on) / 60 / 60 / 24 > 14:
                torrent.delete(delete_files=True)
                print("uploaded and two weeks old: %s" % torrent.name)
        except Exception as e:
            print(f'Error: {e}')

except APIError as e:
    print("failed to connect to qbittorrent: %s" % e)
