#!/home/user/python/media_transport/venv/bin/python

import qbittorrentapi
import subprocess
import shlex
from pathlib import Path


try:
    qbt_client = qbittorrentapi.Client(VERIFY_WEBUI_CERTIFICATE=False,
                                       host='localhost:8080',
                                       username='admin',
                                       password='adminadmin')

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
