# -*- coding:utf-8 -*-
import requests
from bs4 import BeautifulSoup

class Searcher(object):
    pass

class SearcherException(Exception):
    pass

class Decoder(object):
    def __init__(self, raw):
        if type(raw) == requests.models.Response:
            self.soup = BeautifulSoup(raw.content, 'html5lib')
        elif type(raw) == str:
            self.soup = BeautifulSoup(raw, 'html5lib')
        else:
            raise Exception('Wrong format to decode. Should be response object or string.')

class Downloader(object):
    pass

class DownloaderException(Exception):
    pass

class Anime(object):
    pass