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
from .logger import get_logger

from django.conf import settings
from django_redis import get_redis_connection

import sys
reload(sys)
sys.setdefaultencoding('utf-8')

redis = get_redis_connection()

logger = get_logger()

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
    def __init__(self, anime_html, root_url='http://kisssub.org/'):
        tds = anime_html.find_all(name='td')
        self.update_date = tds[0].string.strip()
        self.category = tds[1].string.strip()
        self.title = ''
        for item in tds[2].find(name='a').contents:
            if type(item) is bs4.element.NavigableString:
                self.title += item.strip()
            else:
                self.title += item.string.strip()
        self.href = root_url + tds[2].find(name='a').attrs.get('href')
        self.size, self.size_unit = self._adapt_size(tds[3].string.strip())
        self.magnet = ''

    def __str__(self):
        return json.dumps(self.to_dict())

    def _adapt_size(self, size_str):
        m = re.match('^([\d\.]+)([KMG]B)$', size_str)
        if m is None:
            return -1.0, ''
        else:
            unit = m.group(2)
            size = float(m.group(1))
            if unit == 'GB':
                size = size * 1024 * 1024
            elif unit == 'MB':
                size = size * 1024
            elif unit == 'KB':
                size = size
            return size, unit

    def to_dict(self):
        return {'update_date': self.update_date, 'category': self.category, 'title': self.title,
               'href': self.href, 'size': self.size, 'size_unit': self.size_unit, 'magnet': self.magnet}

class KisssubDecoder(Decoder):
    def decode_for_page(self):
        pages = self.soup.find(name='div', attrs={'class': 'pages clear'})
        if pages is None:
            logger.debug(str(self.soup).replace('\n',''))
            logger.debug('没有找到div.pages，请观察上面获取到的HTML')
            return 1
        else:
            last_page_num = pages.find_all(name=['a','span'])[-2].string
            return int(last_page_num)

    def decode_for_content(self):
        animes = []
        content_list = self.soup.find(attrs={'id': 'data_list'})
        if content_list is None:
            logger.debug(str(self.soup).replace('\n',''))
            logger.debug('没有找到div#data_list，请观察上面获取到的HTML')
        elif content_list.find(name='td').string.strip() == '没有可显示资源':
            pass
        else:
            for anime in content_list.find_all(name='tr'):
                animes.append(KisssubAnime(anime))

        return animes

class KisssubSearcher(Searcher):
    QUERY_KEY = settings.QUERY_KEY
    def __init__(self, uuid, page_limit, root_url='http://kisssub.org/'):
        self.page_limit = page_limit
        self.root_url = root_url
        self.key = self.QUERY_KEY.format(uuid)

    def log(self, level, msg):
        logger.log(level, msg)
        redis.rpush(self.key, msg)
        redis.expire(self.key, 60)

    def search(self, kw):
        search_res = []
        query_url = self.root_url + 'search.php'

        emph = lambda x: '<span class="label label-primary">' + str(x) + '</span>'

        self.log(logging.DEBUG, '请求URL为[{}]'.format(emph(query_url)))

        first_page = self.query_for_page(query_url, kw)
        decoder = KisssubDecoder(first_page)
        page_num = decoder.decode_for_page()
        self.log(logging.DEBUG, '总共找到了 [{}] 页与关键词 [{}] 相关内容'.format(emph(page_num), emph(kw)))

        if self.page_limit <= 0:
            self.log(logging.DEBUG, '无指定页数限制，将爬取所有内容')
        else:
            self.log(logging.DEBUG, '指定页数限制为[{0}]页，只爬取前[{0}]页信息'.format(emph(self.page_limit)))

        page_res = decoder.decode_for_content()
        self.log(logging.DEBUG, '在第 {} 页上发现了 [{}] 行内容'.format(emph(1), emph(len(page_res))))
        search_res.extend(page_res)

        for i in range(page_num - 1):
            page_idx = i + 2
            if self.page_limit > 0 and page_idx > self.page_limit:
                self.log(logging.DEBUG, '达到在指定页数限制，不再查找信息')
                break    # 已经超过了页数限制
            page = self.query_for_page(query_url, kw, page_idx=page_idx)
            decoder = KisssubDecoder(page)
            page_res = decoder.decode_for_content()
            self.log(logging.DEBUG, '在第 {} 页上发现了 [{}] 行内容'.format(emph(page_idx), emph(len(page_res))))
            search_res.extend(page_res)

        self.log(logging.DEBUG, '所有信息都收集完毕')
        return search_res

    def query_for_page(self, query_url, kw, page_idx=1):
        emph = lambda x: '<span class="label label-primary">' + str(x) + '</span>'

        self.log(logging.DEBUG, '正在请求第 {} 页，关键词是 [{}]'.format(emph(page_idx), emph(kw)))
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
