#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
缓存的一个高频使用场景就是:
    1:为了缓解请求对数据库的读写压力，将部分高频读的数据放入缓存中,请求去读缓存来缓解对db的压力.
    2:这样的做法实现需要考虑两个问题:
        1:db和缓存数据一致性问题；
        2:缓存key的生成规则；
        问题1：db:mongodb, 缓存:redis
            在回答问题1之前，需要提一下我们对缓存key的生成规则，以及存储的缓存数据结构，
            1:key生成规则：
                keys = [
                self.__class__.__name__,
                self.cache_version,
                self._input['api_version']
            ]
            key的生成一般采用具体缓存类名称+缓存版本+api版本的拼接再进行md5来保障缓存key的唯一性

            2:缓存存储结构-> 存储缓存采用的就是key:value字符串的存储,但是数据中包含id和value;
            data = {'id': self.cache_id, 'value': self.data}
            return self._client.set(self.cache_key, data, self.expires)

            再次需要着重讲一下这个cache_id的生成(直接上代码):
            def get_cache_id(self):
                row = self._model.find_one(sort=[('updated_at', pymongo.DESCENDING)])
                return row and '{}-{}'.format(row['_id'], row['updated_at'])
            id生成规则不难看出，是取的当前collections(就理解为mysql的表)中的最后一条数据的id及更新时间作为cache_id
            这样做的原因是为了在更新缓存时做比较,如果通过数据库数据拼成的cache_id和现有
            缓存中的cache_id,不相等，则需要刷新缓存;

    3：以上问题解决后，再次基础之上我们做了些功能上的升级和改造:
        1：增加智能缓存开关:
            force_cache ->强制使用缓存
            force_source ->强制使用db数据
        2: 设置缓存过期时间
"""

import abc
from django.conf import settings
from django.core.cache import cache

try:
    import simplejson as json
except:
    import json


class BaseSmartCache(object):
    '''
    智能缓存基类 适用于更新不频繁并且数据需要实时同步的情景

    '''
    __metaclass__ = abc.ABCMeta

    def __init__(self, force_cache=False, force_source=False, smart=False,
                 *args, **kwargs):
        """智能缓存类

        :param force_cache: 强制使用缓存的数据
        :param force_source:  强制使用源数据
        :param smart: 智能检查开关
        """
        assert not all([force_cache, force_source]), \
            ('force_cache and force_source can not assign to True '
             'at the same time')
        self._force_cache = force_cache
        self._force_source = force_source
        self._smart = smart
        self._data = None
        self._cache_id = None
        self._cache_key = None
        self._client = self.client()
        self._latest_update = None

    def client(self):
        return cache

    def prepare(self):
        pass

    def fetch(self):
        self.prepare()
        if self._force_source or not settings.ENABLE_CACHE:
            self._data = self.source()
        else:
            _cache = self.get()
            self._data = _cache and _cache['value']
            if not self._force_cache and (_cache is None or (
                    self._smart and _cache['id'] != self.cache_id)):
                self.refresh()
        return self.handle()

    def handle(self):
        return self.data

    def pre_set(self):
        pass

    def set(self):
        data = {'id': self.cache_id, 'value': self.data}
        return self._client.set(self.cache_key, data, self.expires)

    def get(self):
        return self._client.get(self.cache_key)

    def delete(self):
        return self._client.delete(self.cache_key)

    def refresh(self):
        self._data = self.source()
        self.pre_set()
        self.set()

    @property
    def data(self):
        return self._data

    @property
    def cache_key(self):
        if not self._cache_key:
            self._cache_key = self.get_cache_key()
        return self._cache_key

    @property
    def cache_id(self):
        if not self._cache_id:
            self._cache_id = self.get_cache_id()
        return self._cache_id

    @abc.abstractproperty
    def expires(self):
        pass

    @abc.abstractmethod
    def get_cache_key(self):
        pass

    @abc.abstractmethod
    def get_cache_id(self):
        pass

    @abc.abstractmethod
    def source(self):
        pass
