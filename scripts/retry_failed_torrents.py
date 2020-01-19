#!/home/user/python/media_transport/venv/bin/python
import json
from pathlib import Path
import shlex
import subprocess

from qbittorrentapi import Client


try:
    with open(Path(__file__).parent / 'qbittorrent_config.txt') as file:
        qbt_config = json.load(file)
    qbt_client = Client(**qbt_config)

    for torrent in qbt_client.torrents.info(category='errored'):
        try:
            base_dir = torrent.save_path
            top_dir = None
            if torrent.files:
                file_path = torrent.files[0].name
                top_dir = file_path[:file_path.find('/')]

            if top_dir:
                print(f'Retrying "{torrent.name}"')
                subprocess.call(
                    ' '.join(
                        [
                            '/home/user/python/turbo-potato/venv/bin/python -u /home/user/python/turbo-potato/run.py',
                            '--non-interactive',
                            '--no-notification-on-failure',
                            '--torrents',
                            shlex.quote(str(Path(base_dir, top_dir))),
                            '> /dev/null'
                        ]
                    ),
                    shell=True
                )
        except Exception as e:
            print(e)

except Exception as e:
    print(e)
