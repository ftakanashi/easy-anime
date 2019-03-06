# -*- coding:utf-8 -*-

from uuid import uuid4

from django.conf import settings
from django.http import JsonResponse
from django.views.generic import View
from django.shortcuts import render
from django_redis import get_redis_connection

redis = get_redis_connection()

class QueryView(View):
    QUERY_KEY = 'easy_anime_log:{}'
    def get(self, request):
        uuid = request.GET.get('uuid')
        key = self.QUERY_KEY.format(uuid)
        j = redis.llen(key)
        logs = []
        for _ in range(j):
            logs.append(redis.lpop(key))
        if j == 0:
            return '暂无信息'
        return '<br/>'.join(logs)

class IndexView(View):

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
            res_list = [a.to_dict() for a in self._kisssub_search(keyword, uuid)]
            return JsonResponse({'data': res_list})
        else:
            return JsonResponse({'msg': '非法的源站，目前只支持 {} '.format(','.join(settings.VALID_SRC_SITE))}
                                ,status=500)

    def _kisssub_search(self, kw, uuid):
        from searcher.kisssub import KisssubSearcher as Searcher
        searcher = Searcher(uuid)
        return searcher.search(kw)