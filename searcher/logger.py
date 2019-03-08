# -*- coding:utf-8 -*-

import logging
import os

from logging.handlers import RotatingFileHandler
from logging import Formatter

from django.conf import settings

def get_logger(logger_name='search', level=logging.DEBUG):
    logger = logging.getLogger(logger_name)
    rotfile_handler = RotatingFileHandler(os.path.join(settings.PROJECT_BASE_DIR, 'logs', 'search.log'), maxBytes=1028*1024, backupCount=5)

    formatter = Formatter(
        fmt='[%(asctime)s] %(filename)s:%(lineno)d %(levelname)s  %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )
    rotfile_handler.setFormatter(formatter)
    rotfile_handler.setLevel(level)
    logger.addHandler(rotfile_handler)
    logger.setLevel(level)

    return logger

