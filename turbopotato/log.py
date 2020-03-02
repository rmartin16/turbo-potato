import logging.config
import os
from pathlib import Path
import tempfile

from turbopotato.arguments import args
from turbopotato.media_defs import clean_path_part


class Log:
    def __init__(self):
        log_file_prefix = str(os.path.commonprefix(args.paths))
        if log_file_prefix:
            if Path(log_file_prefix).name:
                log_file_prefix = Path(log_file_prefix).name
            log_file_prefix = clean_path_part(log_file_prefix + '_', replace=' ')

        base_dir = Path(tempfile.gettempdir(), 'znp_logs')
        if not base_dir.is_dir():
            os.mkdir(base_dir)
        info_filename = log_file_prefix + '_znp_log_info.log'
        debug_filename = log_file_prefix + '_znp_log_debug.log'
        for i in range(1, 500):
            self.info_log = Path(base_dir, info_filename)
            self.debug_log = Path(base_dir, debug_filename)
            if self.info_log.is_file() or self.debug_log.is_file():
                info_filename = log_file_prefix + '_znp_log_info.log' + f'.{i}'
                debug_filename = log_file_prefix + '_znp_log_debug.log' + f'.{i}'
            else:
                break

        console_level = args.log_level or 'INFO'

        logging_config = {
            'version': 1,
            'disable_existing_loggers': False,
            'formatters': {
                'fixed_width': {
                    'format': '[%(asctime)s] {%(name)21s:%(lineno)3d} %(levelname)5s - %(message)s'
                },
                'console': {
                    'format': '[%(asctime)s] {%(name)21s:%(lineno)3d} %(levelname)5s - %(message)s'
                }
            },
            'handlers': {
                'console': {
                    'level': ('%s' % console_level),
                    'formatter': 'console',
                    'class': 'logging.StreamHandler',
                    'stream': 'ext://sys.stdout',  # Default is stderr
                },
                'logfile_info': {
                    'level': 'INFO',
                    'formatter': 'fixed_width',
                    'class': 'logging.FileHandler',
                    'filename': ("%s" % self.info_log),
                    "encoding": "utf-8"
                },
                'logfile_debug': {
                    'level': 'DEBUG',
                    'formatter': 'fixed_width',
                    'class': 'logging.FileHandler',
                    'filename': ("%s" % self.debug_log),
                    "encoding": "utf-8"
                }
            },
            'loggers': {
                '': {
                    'level': 'DEBUG',
                    'handlers': ['console', 'logfile_info', 'logfile_debug'],
                }
            }
        }

        logging.config.dictConfig(logging_config)
        self.logger = logging.getLogger(__name__)

    def delete_logs(self):
        logging.shutdown()
        for log in [self.info_log, self.debug_log]:
            try:
                os.remove(log)
            except Exception as e:
                print(f'Error deleting log file {log}: {e}')
