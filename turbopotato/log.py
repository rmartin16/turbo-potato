import logging.config
import os
from pathlib import Path
import tempfile

from turbopotato.arguments import args
from turbopotato.helpers import clean_path_part


class Log:
    def __init__(self):
        log_file_prefix = str(os.path.commonprefix(args.paths))
        if log_file_prefix:
            if Path(log_file_prefix).name:
                log_file_prefix = Path(log_file_prefix).name
            log_file_prefix = clean_path_part(log_file_prefix, replace=' ')
        tmp_dir = tempfile.gettempdir()
        self.info_log = Path(tmp_dir, 'znp_logs', log_file_prefix + '_znp_log_info.log')
        self.debug_log = Path(tmp_dir, 'znp_logs', log_file_prefix + '_znp_log_debug.log')

        console_level = args.log_level or "INFO"

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
