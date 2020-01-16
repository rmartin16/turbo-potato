import urwid
import os
from pathlib import Path
from tempfile import gettempdir
from operator import itemgetter
from subprocess import run, PIPE, STDOUT
from qbittorrentapi import Client
from qbittorrentapi import APIError

import logging
logging.basicConfig(level=logging.INFO)
# logging.disable(level=logging.CRITICAL)
# logging.basicConfig(level=logging.WARNING,
#                    format='[%(asctime)s] {%(name)s:%(lineno)d} %(levelname)s - %(message)s',
#                    filename='/home/user/output.txt',
#                    filemode='w')


def quit_tormon(*args, **kwargs):
    raise urwid.ExitMainLoop()


class Tormon(object):
    def __init__(self):
        super().__init__()
        self.qbt_client = Client(VERIFY_WEBUI_CERTIFICATE=False)  # host='http://localhost:8080', username='test', password='testtest', VERIFY_WEBUI_CERTIFICATE=False)
        self.log_path = Path(gettempdir()) / 'znp_logs/'

        self.free_space_w = urwid.Filler(urwid.Text(''))
        self.torrents_stats_w = urwid.Text('')
        self.transiting_torrents_column1 = urwid.Text('', wrap=urwid.CLIP)
        self.transiting_torrents_column2 = urwid.Text('', align=urwid.RIGHT, wrap=urwid.CLIP)
        self.footer_w = urwid.Filler(urwid.Text('', align=urwid.RIGHT, wrap=urwid.CLIP))

    @staticmethod
    def handle_key(key):
        if key in ('q', 'Q'):
            quit_tormon()

    def refresh(self, loop=None, user_data=None):
        self.free_space_w.base_widget.set_text(print_free_space())
        self.torrents_stats_w.base_widget.set_text(print_torrent_stats(self.qbt_client))
        transiting_torrents_tuple = print_transiting_torrents(self.log_path, 10000)
        self.transiting_torrents_column1.base_widget.set_text(transiting_torrents_tuple[0])
        self.transiting_torrents_column2.base_widget.set_text(transiting_torrents_tuple[1])
        self.footer_w.base_widget.set_text(print_qbt_version(self.qbt_client))
        loop.set_alarm_in(sec=2, callback=self.refresh)

    def run(self):
        transiting_torrents_w = urwid.Columns(
            widget_list=[self.transiting_torrents_column1,
                         self.transiting_torrents_column2],
            dividechars=2
        )

        mainframe = urwid.Pile(
            [
                ('fixed', 2, self.free_space_w),
                ('fixed', 1, urwid.Filler(urwid.Divider())),
                ('fixed', 1, urwid.Filler(urwid.Text(" >>> Torrent Stats <<<"))),
                ('pack', self.torrents_stats_w),
                ('fixed', 1, urwid.Filler(urwid.Divider())),
                ('fixed', 1, urwid.Filler(urwid.Text(" >>> Torrent Handling <<<"))),
                ('pack', transiting_torrents_w),
                urwid.Filler(urwid.Divider()),
                ('fixed', 1, self.footer_w)
            ]
        )

        loop = urwid.MainLoop(
            mainframe,
            handle_mouse=False,
            unhandled_input=self.handle_key
        )
        loop.set_alarm_in(sec=.01, callback=self.refresh)
        loop.run()


def print_free_space():
    output = []
    df_cmd = '/bin/df -h | grep -E "/dev/mapper/xubuntu--vg-root|Filesystem"'
    result = run([df_cmd], shell=True, stdout=PIPE, stderr=STDOUT, encoding='utf-8')
    for line in [line for line in result.stdout.split('\n') if line != ""]:
        output.append(line)
    return '\n'.join(output)


def print_torrent_stats(qbt):
    output = []
    try:
        torrent_list = qbt.torrents_info(status_filter='all')
        stats = {}
        stats.setdefault('category', {})
        stats.setdefault('state', {})

        state_map = {'pausedUP': "Completed",
                     'uploading': 'Uploading',
                     'stalledUP': 'Uploading',
                     'forcedUP': 'Uploading',
                     'queuedUP': 'Queued',
                     'pausedDL': "Paused",
                     'downloading': 'Downloading',
                     'stalledDL': "Downloading",
                     'checkingUP': "Checking",
                     'checkingDL': "Checking",
                     "metaDL": "Metadata Dl"}

        # get counts of categories and states
        for torrent in torrent_list:
            cat = torrent.category
            if cat != "":
                stats['category'].update({cat: stats['category'].setdefault(cat, 0)+1})
            state = torrent.state
            if state in state_map:  # map qbittorrent state to local states
                state = state_map[state]
            stats['state'].update({state: stats['state'].setdefault(state, 0)+1})

        # find longest length of torrents' states
        max_key_length = 0
        if stats['state']:
            max_key_length = max(map(len, stats['state']))

        # generate printable strings of counts
        for _ in range(max(len(stats['state']), len(stats['category']))):
            try:
                (state_name, state_count) = stats['state'].popitem()
            except KeyError:
                (state_name, state_count) = ("", 0)
            try:
                (category_name, category_count) = stats['category'].popitem()
            except KeyError:
                (category_name, category_count) = ("", 0)

            string = ""
            if state_name != "":
                string = "%s:%s%2d" % (state_name, ' '*(max_key_length-len(state_name)+1), state_count)
            if category_name != "":
                space_count = (max_key_length+10) - len(string)
                string += "%s%s: %s" % (' '*space_count, category_name, category_count)
            output.append(string)
        return '\n'.join(output)

    except APIError as e:
        output.append("Error: %s" % e)
        return '\n'.join(output)


def print_transiting_torrents(log_path, cols):
    torrent_list = []
    filename_list = []
    transfer_details_list = []

    for directory, _, files in os.walk(log_path):
        # process each debug log file
        for f in [open(Path(directory, file)) for file in files if "_debug.log" in file]:
            lines = f.readlines()
            srch_list = ['INFO - >>> Starting transit for ', '>>> Starting identification for ', ]
            for srch in srch_list:
                try:
                    # extract filename from last line in log that actually contains a filename
                    # example line: [2019-04-27 17:37:08,453] {       processor: 75} INFO - Filename: American.Gods.S01E01.720p.WEBRip.X264-DEFLATE.mkv
                    filename = [line[line.find(srch)+len(srch):].strip() for line in lines if srch in line][-1]
                    if filename:
                        if filename.endswith('...'):
                            filename = filename[:-3]
                        break
                except IndexError:  # failure here would suggest there are no filename in the file...
                    filename = ''
            try:
                lastline = lines[-1]  # there should always be a last line...even for an empty file...but not always
            except IndexError:
                lastline = ''

            srch = 'Output:'          # indication of rsync output
            cushion = 15              # chars between filename and details of last line of log file
            filename_end_length = 3   # if trimming filename, how much to keep from end of filename (e.g. 3 for file extension)
            cushion_char = "_"        # char to use to separate filename and list line of log detail
            percent_uploaded = 0      # initialize percent uploaded of file to zero

            # extract relevant portion of lastline of log file
            if srch in lastline:   # if rsync output is in lastline
                transfer_details = lastline[lastline.find(srch)+len(srch):].strip()  # get rsync output e.g "1.64G  97%  170.30kB/s    0:04:02"
                if transfer_details.find('%') >= 0:
                    try:
                        percent_uploaded = int(transfer_details[transfer_details.find('%')-2:transfer_details.find('%')])
                    except ValueError:  # somehow a non-integer was found...
                        percent_uploaded = 0
            else:   # if something other than rsync output is lastline
                # example: [2019-04-27 20:10:28,305] {      processor:232} INFO - >>> Finished Database Query
                transfer_details = '{' + lastline[lastline.find('{')+1:cols-15].strip()
            transfer_details_list.append(transfer_details)
            transfer_details_len = len(transfer_details)

            # cut out a middle piece of filename if necessary due to screen width
            filename_list.append(filename)
            if len(filename) > (cols - transfer_details_len - cushion):
                filename = filename[:cols - transfer_details_len - cushion - 3 - filename_end_length] + '...' + filename[len(filename)-filename_end_length:]

            # build list of tuples (torrent, % uploaded)
            torrent_list.append(("%s%s%s" % (filename, cushion_char*(cols-len(filename)-transfer_details_len), transfer_details), percent_uploaded, filename, transfer_details))

    # sort torrents by percent uploaded and add to be printed
    torrent_list.sort(key=itemgetter(1), reverse=True)

    return '\n'.join([x[2] for x in torrent_list]), '\n'.join([x[3] for x in torrent_list])


def print_qbt_version(qbt):
    ret = ''
    try:
        version = qbt.app.version
        api_version = qbt.app.web_api_version
    except APIError:
        pass
    else:
        ret = f'{version} ({api_version})'
    return ret


if __name__ == '__main__':
    Tormon().run()
