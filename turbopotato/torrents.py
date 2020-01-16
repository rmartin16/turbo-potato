import logging
import time
from typing import List, Union

import qbittorrentapi as qbt_api
from qbittorrentapi import APIError as qBittorrentError

from turbopotato.config import config

logger = logging.getLogger(__name__)


class Torrents:
    def __init__(self):
        self.qbt_client = qbt_api.Client(host=config.qbittorrent_host,
                                         port=config.qbittorrent_port,
                                         username=config.qbittorrent_username,
                                         password=config.qbittorrent_password,
                                         VERIFY_WEBUI_CERTIFICATE=False,
                                         DISABLE_LOGGING_DEBUG_OUTPUT=True)
        self._torrent_cache = None
        self._torrent_cache_time = time.time()
        self._torrent_cache_max_age = 3

    @property
    def _torrents(self):  # -> Union[List[qbt_api.TorrentDictionary], None]:
        if (time.time() - self._torrent_cache_time) > self._torrent_cache_max_age or (self._torrent_cache is None):
            try:
                self._torrent_cache = self.qbt_client.torrents.info.all()
            except qBittorrentError as e:
                logger.error(f'Failed to retrieve torrent list: {e}', exc_info=True)
                return None
        return self._torrent_cache

    @staticmethod
    def wrap_api_call(func, **kwargs):
        torrent_hash = kwargs.get('hash') or kwargs.get('hashes')
        try:
            return func(**kwargs)
        except Exception as e:
            logger.warning(f'qBittorrent communications error for "{torrent_hash}". Function: {func}. kwargs: {kwargs}. Error: {e}',
                           exc_info=True)
            return None

    def get_torrent(self, torrent_name: str = None, torrent_hash: str = None):  # -> Union[qbt_api.TorrentDictionary, None]:
        if torrent_hash:
            try:
                return self.qbt_client.torrents.info(hashes=torrent_hash)[0]
            except (qBittorrentError, IndexError) as e:
                logger.warning(f'Torrent not found for "{torrent_hash}": {e}')
                return None
        if torrent_name:
            for torrent in self._torrents:
                if torrent.name == torrent_name:
                    return torrent
        return None

    # def is_already_transiting(torrent: qbt_api.TorrentDictionary = None) -> bool:
    def is_transiting(self, torrent=None, torrent_hash: str = None) -> bool:
        if torrent_hash:
            torrent = self.get_torrent(torrent_hash=torrent_hash)
        if torrent and torrent.category.lower() == 'transiting':
            return True
        return False


torrents = Torrents()
