# -*- coding:utf-8 -*-

import bs4
import json
import logging
import requests
import threading
import re
import traceback
from Queue import Queue, Empty

from . import Anime, Decoder, Downloader, DownloaderException, Searcher, SearcherException

from django_redis import get_redis_connection

redis = get_redis_connection()
logger = logging.getLogger('easy-anime')

HEADERS = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Encoding': 'gzip, deflate',
    'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
    'Cache-Control': 'no-cache',
    'Connection': 'keep-alive',
    'Host': 'kisssub.org',
    'Pragma': 'no-cache',
    'Upgrade-Insecure-Requests': '1',
    'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; Win64; x64; rv:65.0) Gecko/20100101 Firefox/65.0'
}

class KisssubAnime(Anime):
    def __init__(self, anime_html):
        tds = anime_html.find_all(name='td')
        self.update_date = tds[0].string.strip()
        self.category = tds[1].string.strip()
        self.title = ''
        for item in tds[2].find(name='a').contents:
            if type(item) is bs4.element.NavigableString:
                self.title += item.strip()
            else:
                self.title += item.string.strip()
        self.href = tds[2].find(name='a').attrs.get('href')
        self.size = tds[3].string.strip()
        self.magnet = ''

    def __str__(self):
        return json.dumps(self.to_dict())

    def to_dict(self):
        return {'update_date': self.update_date, 'category': self.category, 'title': self.title,
               'href': self.href, 'size': self.size, 'magnet': self.magnet}

class KisssubDecoder(Decoder):
    def decode_for_page(self):
        pages = self.soup.find(name='div', attrs={'class': 'pages clear'})
        if pages is None:
            return 1
        else:
            return len(list(pages)) - 2

    def decode_for_content(self):
        animes = []
        content_list = self.soup.find(attrs={'id': 'data_list'})
        cnt = 0
        for anime in content_list.find_all(name='tr'):
            animes.append(KisssubAnime(anime))
            cnt += 1

        logger.log(logging.DEBUG, '{} rows of anime decoded.'.format(cnt))

        return animes

class KisssubSearcher(Searcher):
    QUERY_KEY = 'easy_anime_log:{}'
    def __init__(self, uuid, root_url='http://kisssub.org/'):
        self.root_url = root_url
        key = self.QUERY_KEY.format(uuid)
        def _log(level, msg):
            logger.log(level, msg)
            if level in (logging.DEBUG, logging.INFO):
                redis.rpush(key, msg)

        self.log = _log

    def search(self, kw):
        search_res = []
        query_url = self.root_url + 'search.php'
        self.log(logging.DEBUG, 'Main query url is [{}]'.format(query_url))

        first_page = self.query_for_page(query_url, kw)

        decoder = KisssubDecoder(first_page)
        page_num = decoder.decode_for_page()
        self.log(logging.DEBUG, 'Fetched [{}] pages while searching for [{}]'.format(page_num, kw))
        search_res.extend(decoder.decode_for_content())

        for i in range(page_num - 1):
            page_idx = i + 2
            page = self.query_for_page(query_url, kw, page_idx=page_idx)
            decoder = KisssubDecoder(page)
            search_res.extend(decoder.decode_for_content())

        return search_res

    def query_for_page(self, query_url, kw, page_idx=1):
        self.log(logging.DEBUG, 'Query for page[{}] with keyword [{}]'.format(
            page_idx, kw
        ))
        p = {
            'keyword': kw,
            'page': page_idx
        }
        try:
            query = requests.get(query_url, params=p, headers=HEADERS)
            if query.status_code != 200:
                raise Exception('HTTP Error[{}]'.format(query.status_code))
        except Exception as e:
            self.log(logging.ERROR, traceback.format_exc(e))
            raise SearcherException('Failed to get page[{}] while searching with keyword [{}]'.format(page_idx, kw))
        else:
            return query

class KisssubMagnetGetter(Downloader):
    def __init__(self, thread_class, pool_size, searched_animes, root_url='http://kisssub.org/'):
        self.queue = Queue(len(searched_animes))
        for anime in searched_animes:
            self.queue.put(anime)

        self.pool = [thread_class(i, self.queue, root_url) for i in range(pool_size)]

    def get_magnet(self):
        for t in self.pool:
            t.start()

        for t in self.pool:
            if t.isAlive():
                t.join()

class KisssubMagnetGetThread(threading.Thread):
    def __init__(self, idx, queue, root_url):
        super(KisssubMagnetGetThread, self).__init__()
        self.queue = queue
        self.root_url = root_url
        self.name = 'downloader_{}'.format(idx)

    def run(self):
        while True:
            try:
                anime = self.queue.get(block=False)

                query_url = self.root_url + anime.href
                try:
                    query = requests.get(query_url, headers=HEADERS)
                    if query.status_code != 200:
                        raise Exception('HTTP Error [{}]'.format(query.status_code))
                except Exception as e:
                    logger.log(logging.ERROR, traceback.format_exc(e))
                    raise DownloaderException('Error occured when querying [{}] @{}'.format(query_url, self.name))

                soup = bs4.BeautifulSoup(query.content, 'html5lib')
                dmain = soup.find(name='div', attrs={'class': 'main'})
                script_text = dmain.find_all(name='script', recursive=False)[-1].string.strip()

                magnet = 'magnet:?xt=urn:btih:{hash}&tr={announce}'
                hash = re.search('Config\[\'hash_id\'\]\ = "(.+?)"', script_text).group(1)
                announce = re.search('Config\[\'announce\'\] = "(.+?)"', script_text).group(1)
                magnet = magnet.format(hash=hash, announce=announce)
                anime.magnet = magnet
                logger.log(logging.INFO, '[{}] has finished magnet searching'.format(self.name))

                self.queue.task_done()
            except Empty as e:
                logger.log(logging.INFO, 'No more task for [{}]'.format(self.name))
                break
            except Exception as e:
                logger.log(logging.ERROR, '[ERROR # {}]'.format(self.name))
                logger.log(logging.ERROR, traceback.format_exc(e))
                break
