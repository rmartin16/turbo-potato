import logging
from pathlib import Path

from turbopotato.arguments import args
from turbopotato.config import config
from turbopotato.log import Log
from turbopotato.media import Media

logger = logging.getLogger('notify')


def notify(media: Media, logs: Log):
    if args.interactive:
        return

    file_groups = media.get_file_groups()

    for file_group in file_groups:
        if file_group.success:
            dest_dir = file_group.files[0].destination_directory.parts[-2]
            subject = f'Added Media to {dest_dir} ({file_group.name})'
        else:
            if args.no_notification_on_failure:
                continue
            subject = f'Adding Media Failed ({file_group.name})'

        log_to_send = ""
        for log_name, log_filepath in (('  >>> Info Log <<<', logs.info_log),
                                       ('  >>> Debug Log <<<', logs.debug_log)):
            try:
                with open(log_filepath) as file:
                    log = file.read()
            except (OSError, IOError) as e:
                logger.warning(f'Could not read log file for notification ("{log_filepath}"). Error {e}')
            else:
                log_to_send += "\n\r\n\r %s\n\r" % log_name
                log_to_send += log

        summary = ''
        for file in file_group.files:
            summary += f'<table>'
            if file.success:
                summary += '<tr><td colspan="2"><b>Media was added to your library</b></td></tr>'
                summary += f'<tr><td>Filename</td><td>{file.filepath.name}</td></tr>'
                summary += f'<tr><td>Parsed File Information</td><td>{file.parts}</td></tr>'
                summary += f'<tr><td>Identified Information</td><td>{file.chosen_one}</td></tr>'
                summary += f'<tr><td>Destination Directory</td><td>{file.destination_directory}</td></tr>'
                summary += f'<tr><td>Destination Filename</td><td>{file.destination_filename}</td></tr>'
            else:
                summary += '<tr><td colspan="2"><b>Failed to add media to your library<b></td></tr>'
                summary += f'<tr><td>Filename</td><td>{file.filepath.name}</td></tr>'
                summary += f'<tr><td>Parsed File Information</td><td>{file.parts}</td></tr>'

            if file.query.exact_matches + file.query.fuzzy_matches_sorted:
                summary += f'<tr><td></td><td></td></tr>'
                summary += '<tr><td colspan="2">Database Query Results</td></tr>'
                for result in file.query.exact_matches + file.query.fuzzy_matches_sorted:
                    summary += f'<tr><td colspan="2">\t{result}</td></tr>'

            summary += f'</table><br><br><br>'

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
