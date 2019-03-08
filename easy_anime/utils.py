# -*- coding:utf-8 -*-

import logging
import paramiko
import traceback

from django.conf import settings

logger = logging.getLogger('easy-anime')

def get_proxy_ssh_client():
    config = settings.SSH_PROXY_CONFIG
    host = config.get('proxy_name')
    port = config.get('proxy_port')
    user = config.get('proxy_user')
    pkey = config.get('proxy_pkey')
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        key = paramiko.RSAKey.from_private_key_file(pkey)
        ssh.connect(hostname=host, port=port, username=user, pkey=key)
    except Exception as e:
        logger.error('Failed to get ssh proxy client for:\n{}'.format(traceback.format_exc(e)))
        return None

    ssh.list_script_path = settings.PROXY_SCRIPT_PATH.get('list')
    ssh.detail_script_path = settings.PROXY_SCRIPT_PATH.get('detail')

    return ssh

def close_proxy_ssh_client(ssh):
    try:
        ssh.close()
    except Exception as e:
        logger.error('Failed to close ssh proxy for:\n{}'.format(traceback.format_exc(e)))
        return False
    else:
        return True