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
    ssh.data_json = settings.PROXY_SCRIPT_PATH.get('data')
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

def get_proxy_channel():
    try:
        hostname = settings.SSH_PROXY_CONFIG['proxy_name']
        port = settings.SSH_PROXY_CONFIG['proxy_port']
        username = settings.SSH_PROXY_CONFIG['proxy_user']
        key = settings.SSH_PROXY_CONFIG['proxy_pkey']
    except KeyError as e:
        logger.error('Bad format of configuration SSH_PROXY_CONFIG')
        raise e

    try:
        list_script_path = settings.PROXY_SCRIPT_PATH['list']
        detail_script_path = settings.PROXY_SCRIPT_PATH['detail']
    except KeyError as e:
        logger.error('Bad format of configuration PROXY_SCRIPT_PATH')
        raise e

    try:
        trans = paramiko.Transport(sock=(hostname, port))
        key = paramiko.RSAKey.from_private_key_file(key)
        trans.connect(username=username, pkey=key)
        channel = trans.open_session()
        channel.get_pty()
        channel.invoke_shell()
    except Exception as e:
        logger.error('Failed to create SSH shell:\n{}'.format(traceback.format_exc(e)))
        raise e
    else:
        channel.list_script_path = list_script_path
        channel.detail_script_path = detail_script_path
        return channel
