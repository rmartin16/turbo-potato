import logging
import shlex
import subprocess

logger = logging.getLogger(__name__)


class RemoteExecuteError(Exception):
    pass


class RemoteExecuteSendCommandFailed(RemoteExecuteError):
    pass


class RemoteExecuteSendCommandError(RemoteExecuteError):
    pass


def send_file(local_filepath=None, remote_filepath=None):
    escaped_dirpath = shlex.quote(str(remote_filepath.parent))
    escaped_target_filepath = shlex.quote(str(remote_filepath))

    send_file_command = ['rsync',
                         # '-e "ssh -x -T -c chacha20-poly1305@openssh.com"',
                         '-e ssh -o compression=no',
                         '--human-readable', '--no-relative',
                         f'--rsync-path=mkdir -p {escaped_dirpath} && rsync',
                         '--stats', '--progress',
                         '--perms', '--chmod=Du=rwx,Dgo=rwx,Fu=rw,Fog=rw',
                         f'{local_filepath}',
                         f'nas:{escaped_target_filepath}']
    ''' send file to remote machine; skip to next file if failure '''
    send_command(remote_cmd=send_file_command)


def send_command(remote_cmd=None):
    try:
        logger.debug("Command: %s" % remote_cmd)
        p = subprocess.Popen(remote_cmd,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT,
                             encoding='utf-8',
                             bufsize=1)
        count = 0
        for line in p.stdout:
            # only print every 10th output for rsync upload status
            if 'rsync' in remote_cmd and "%" in line:
                if count % 30 == 0:  # about every 30 seconds
                    logger.debug("Output: %s" % str(line).rstrip())
                count += 1
            else:
                logger.debug("Output: %s" % str(line).rstrip())
        p.wait()
    except Exception as e:
        raise RemoteExecuteSendCommandFailed(f'Error executing remote command: {e}') from e

    if p.returncode != 0:
        raise RemoteExecuteSendCommandError(f'Non-zero return value for remote command: {remote_cmd}')
