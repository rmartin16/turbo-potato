from collections import namedtuple
import logging
import os
from pathlib import Path
from typing import List

from turbopotato.arguments import args
from turbopotato.config import config
from turbopotato.log import Log
from turbopotato.media import Media

logger = logging.getLogger(__name__)
FileGroup = namedtuple('FileGroup', 'success files name')


def notify(media: Media, logs: Log):
    if args.interactive:
        return

    file_groups: List[FileGroup] = list()
    if args.torrents:
        for torrent_hash in set(f.torrent_hash for f in media):
            files = [f for f in media if f.torrent_hash == torrent_hash]
            file_groups.append(
                FileGroup(
                    success=all(f.success for f in files),
                    files=files,
                    name=files[0].original_torrent_state.name
                )
            )
    else:
        file_groups.append(
            FileGroup(
                success=all(f.success for f in media),
                files=media.files,
                name=Path(os.path.commonprefix([f.filepath for f in media])).name
            )
        )

    for file_group in file_groups:
        if file_group.success:
            subject = f'Added Media Successfully ({file_group.name})'
        else:
            subject = f'Adding Media Failed ({file_group.name})'

        log_to_send = ""
        for log_name, log_filepath in (('  >>> Info Log <<<', logs.info_log),
                                       ('  >>> Debug Log <<<', logs.debug_log)):
            try:
                with open(log_filepath) as file:
                    log = file.read()
            except (OSError, IOError):
                logger.warning(f'log file not found for notification ({log_filepath})')
            else:
                log_to_send += "\n\r\n\r %s\n\r" % log_name
                log_to_send += log

        summary = ''
        for file in file_group.files:
            if file.success:
                summary += 'Media was added to your library'
                summary = ""
                summary += f'<table>'
                summary += f'<tr><td>Filename</td><td>{file.filepath.name}</td></tr>'
                summary += f'<tr><td>Parsed File Information</td><td>{file.parts}</td></tr>'
                summary += f'<tr><td>Identified Information</td><td>{file.chosen_one}</td></tr>'
                summary += f'<tr><td>Destination Directory</td><td>{Path(file.destination_directory).parent}</td></tr>'
                summary += f'<tr><td>Destination Filename</td><td>{file.destination_filename}</td></tr>'
                summary += f'<tr></tr>'
                summary += f'</table>'
            else:
                pass

            summary += '<br><br>Database Query Results'
            for result in [file.query.exact_matches + file.query.fuzzy_matches_sorted]:
                summary += f'<br>{type(result)}'

        send_email(subject, summary, log_to_send)


def send_email(subject, summary, log=""):

    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    fromaddr = "rmartin16@gmail.com"
    toaddr = "rmartin16+media-alerts@gmail.com"
    msg = MIMEMultipart()
    msg['From'] = fromaddr
    msg['To'] = toaddr
    msg['Subject'] = subject

    body = "<HTML><HEAD>"
    # body += "<style> table, th, td { border: 1px solid black; } </style>"
    body += '''
        <style>
        table {
          border-collapse: collapse;
          width: 100%;
          font-size: 11px;
          font-family: monospace;
        }
        th, td {
          padding: 5px;
          text-align: left;
          border-bottom: 1px solid #ddd;
        }
        tr:hover {background-color:#f5f5f5;}
        </style>'''
    body += "</HEAD><BODY>"
    body += "<font face=\"Courier New, Courier, monospace\"><pre>"

    summary = summary.replace("\r", "")
    summary = summary.replace("\n", "<BR>")
    body += summary
    body += log

    body += "</pre></font>"
    body += "</BODY></HTML>"
    # print(body)
    msg.attach(MIMEText(body, 'HTML'))

    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()
    server.login(fromaddr, config.GMAIL_APP_PASSWORD)
    text = msg.as_string()
    server.sendmail(fromaddr, toaddr, text)
    server.quit()
