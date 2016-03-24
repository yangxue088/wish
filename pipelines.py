# -*- coding: utf-8 -*-

# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: http://doc.scrapy.org/en/latest/topics/item-pipeline.html
from pybloom import ScalableBloomFilter
from scrapy.exceptions import DropItem
from scrapy_redis.pipelines import RedisPipeline


class WishPipeline(object):
    def __init__(self):
        self.urls = ScalableBloomFilter(mode=ScalableBloomFilter.LARGE_SET_GROWTH)

    def process_item(self, item, spider):
        if item is None or item['url'] is None or item['url'] in self.urls:
            raise DropItem("Duplicate item found.")
        else:
            self.urls.add(item['url'])
            return item


class ToRedisPipeline(RedisPipeline):

    def _process_item(self, item, spider):
        self.server.rpush('{}:products'.format(spider.name), item['url'])
        return item
