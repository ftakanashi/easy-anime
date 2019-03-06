# -*- coding:utf-8 -*-

import logging
import os
import sys

from logging.handlers import RotatingFileHandler, BufferingHandler
from logging import Formatter

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_logger(level=logging.DEBUG):
    logger = logging.getLogger('easy-anime')
    rotfile_handler = RotatingFileHandler(os.path.join(BASE_DIR, 'easy-anime.log'), maxBytes=1028*1024, backupCount=5)
    stdout_handler = logging.StreamHandler(sys.stdout)

    formatter = Formatter(
        fmt='[%(asctime)s] %(filename)s:%(lineno)d %(levelname)s  %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )
    rotfile_handler.setFormatter(formatter)
    rotfile_handler.setLevel(level)
    stdout_handler.setFormatter(formatter)
    stdout_handler.setLevel(level)
    logger.addHandler(rotfile_handler)
    logger.addHandler(stdout_handler)
    logger.setLevel(level)

    return logger

