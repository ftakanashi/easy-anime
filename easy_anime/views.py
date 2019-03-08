# -*- coding:utf-8 -*-

import json
import logging
import traceback
import sys

reload(sys)
sys.setdefaultencoding('utf-8')

from uuid import uuid4

from django.conf import settings
from django.http import JsonResponse
from django.views.generic import View
from django.shortcuts import render, redirect, reverse
from django_redis import get_redis_connection

redis = get_redis_connection()

logger = logging.getLogger('easy-anime')

class QueryView(View):
    QUERY_KEY = settings.QUERY_KEY
    def get(self, request):
        uuid = request.GET.get('uuid')
        key = self.QUERY_KEY.format(uuid)
        j = redis.llen(key)
        if j == 0:
            msg = ''
        else:
            msg = '<br/>'.join([redis.lpop(key) for _ in range(j)])
            # print msg
        return JsonResponse({'msg': msg})

class IndexView(View):
    RESLIST_CACHE_KEY = settings.RESLIST_CACHE_KEY

    def get(self, request):
        ctx = {}
        ctx['uuid'] = str(uuid4())
        ctx['src_sites'] = settings.VALID_SRC_SITE
        return render(request, 'index.html', ctx)

    def post(self, request):
        keyword = request.POST.get('kw')
        uuid = request.POST.get('uuid')
        src = request.POST.get('src')

        if src == 'kisssub':
            logger.info('Source site is kisssub.')
            res_list = [a.to_dict() for a in self._kisssub_search(keyword, uuid)]
            key = self.RESLIST_CACHE_KEY.format(uuid)
            redis.set(key, json.dumps(res_list))
            redis.expire(key, 60)
            return JsonResponse({'src': src})
        elif src == 'dmhy':
            logger.info('Source site is dmhy.')
            try:
                output = self._dmhy_search(kw=keyword, uuid=uuid)
                data = json.loads(output)
            except Exception as e:
                logger.error('Error when search dmhy:\n{}'.format(traceback.format_exc(e)))
                return JsonResponse({'msg': '获取信息失败，请查看后台日志'}, status=500)
            try:
                key = self.RESLIST_CACHE_KEY.format(uuid)
                redis.set(key, json.dumps(data))
                redis.expire(key, 60)
            except Exception as e:
                logger.error('Failed to dump information into redis:\n{}'.format(traceback.format_exc(e)))
                return JsonResponse({'msg': '存储信息失败，请查看后台日志'}, status=500)
            return JsonResponse({'src': src})
        else:
            return JsonResponse({'msg': '非法的源站，目前只支持 {} '.format(','.join(settings.VALID_SRC_SITE))}
                                ,status=500)

    def _kisssub_search(self, kw, uuid):
        from searcher.kisssub import KisssubSearcher as Searcher
        searcher = Searcher(uuid)
        return searcher.search(kw)

    def _dmhy_search(self, kw, uuid):
        from utils import get_proxy_ssh_client, close_proxy_ssh_client
        ssh = get_proxy_ssh_client()
        if ssh is None:
            raise Exception('Failed to get ssh proxy client.')

        cmd = '{} -k {}'.format(ssh.list_script_path, kw)
        stdin, stdout, stderr = ssh.exec_command(cmd)
        out, err = stdout.read(), stderr.read()

        if not close_proxy_ssh_client(ssh):
            logger.warning('Failed to close ssh proxy.')
        if err != '':
            logger.error('Failed to execute command [{}] for:{}'.format(cmd, err))
            raise Exception(err)
        else:
            logger.debug(out)
            return out

class ResView(View):
    RESLIST_CACHE_KEY = settings.RESLIST_CACHE_KEY

    def get(self, request):
        ctx = {}
        type = request.GET.get('cate')
        uuid = request.GET.get('u')
        src = request.GET.get('src')
        if type not in ('p', 'd') or uuid is None or src not in [s['code'] for s in settings.VALID_SRC_SITE]:
            return redirect(reverse('index'), msg='错误的请求参数')

        if type == 'p':    # 请求页面(p for page)
            ctx['uuid'] = uuid
            ctx['src'] = src
            return render(request, 'res.html', ctx)
        elif type == 'd':    # 请求数据(d for data)
            key = self.RESLIST_CACHE_KEY.format(uuid)
            res_list_dumped = redis.get(key)
            if res_list_dumped is None:
                return redirect(reverse('index'), msg='没有找到相关缓存')
            redis.expire(key, 60)
            res_list = json.loads(res_list_dumped)
            return JsonResponse(res_list, safe=False)

class MagnetView(View):
    pass