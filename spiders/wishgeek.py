# -*- coding: utf-8 -*-
import json
from urllib import quote, urlencode

import re
import scrapy
from pybloom import ScalableBloomFilter

from .. import items
import logging

class WishGeekSpider(scrapy.Spider):
    name = "wishgeek"
    allowed_domains = ["wish.com"]
    start_urls = (
        'http://www.wish.com/',
    )

    contests = ScalableBloomFilter(mode=ScalableBloomFilter.LARGE_SET_GROWTH)

    xsrfpattern = re.compile(r'.*_xsrf=(.*?);')

    def __init__(self, username, password, ajaxcount=70):
        self.username = username
        self.password = password
        self.ajaxcount = ajaxcount

    def start_requests(self):
        yield scrapy.Request('https://www.wish.com/geek/m', callback=self.login)

    def login(self, response):
        match = self.xsrfpattern.match(str(response.headers))

        if match:
            xsrf = match.group(1)
            yield scrapy.Request(
                'https://www.wish.com/api/email-login?email={}&password={}&_buckets=&_experiments=&_app_type=geek&_client=mobileweb&_version=1.0.0'.format(
                    quote(self.username), quote(self.password)),
                method='POST',
                headers={
                    'Accept': 'application/json, text/javascript, */*; q=0.01',
                    'Content-Type': ' application/x-www-form-urlencoded; charset=UTF-8',
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-XSRFToken': xsrf
                }, meta={'xsrf': xsrf},
                callback=self.request_home)

    def request_home(self, response):
        yield self.feed_home_ajax(response.meta['xsrf'])

    def feed_home_ajax(self, xsrf, offset=0):
        formdata = {
            'count': str(self.ajaxcount),
            'offset': str(offset),
            '_buckets': '',
            '_experiments': '',
            '_app_type': 'geek',
            '_client': 'mobileweb',
            '_version': '1.0.0',
        }

        return self.feed_ajax('https://www.wish.com/api/feed/get', xsrf, formdata)

    def feed_similar_ajax(self, xsrf, contest_id, offset=0):
        formdata = {
            'contest_id': contest_id,
            'feed_mode': 'similar',
            'count': str(self.ajaxcount),
            'offset': str(offset),
            '_buckets': '',
            '_experiments': '',
            '_app_type': 'geek',
            '_client': 'mobileweb',
            '_version': '1.0.0',
        }

        return self.feed_ajax('https://www.wish.com/api/related-feed/get', xsrf, formdata)

    def feed_ajax(self, url, xsrf, formdata):
        return scrapy.Request(
            url,
            method='POST', body=urlencode(formdata),
            headers={
                'Accept': 'application/json, text/javascript, */*; q=0.01',
                'Content-Type': ' application/x-www-form-urlencoded; charset=UTF-8',
                'X-Requested-With': 'XMLHttpRequest',
                'X-XSRFToken': xsrf
            },
            meta={
                'xsrf': xsrf,
                'contest_id': formdata.get('contest_id', None)
            },
            callback=self.parse_feed_ajax)

    def parse_feed_ajax(self, response):
        json_data = json.loads(response.body)
        data = json_data.get('data', None)
        if data is not None:
            next_offset = data.get('next_offset')
            feed_ended = data.get('feed_ended', True)
            products = data.get('items', [])

            for pid in (product.get('id') for product in products if product.get('id') not in self.contests):
                self.contests.add(pid)
                item = items.WishItem()
                item['url'] = 'https://www.wish.com/c/{}'.format(pid)
                yield item

                # yield self.feed_similar_ajax(response.meta['xsrf'], pid)

            if not feed_ended:
                if response.meta['contest_id'] is None:
                    yield self.feed_home_ajax(response.meta['xsrf'], next_offset)
                else:
                    yield self.feed_similar_ajax(response.meta['xsrf'], response.meta['contest_id'], next_offset)
            else:
                if response.meta['contest_id'] is None:
                    self.log('home ajax end. total:{}'.format(next_offset), logging.INFO)
                else:
                    self.log('relate ajax end. contest_id:{}, total:{}'.format(response.meta['contest_id'], next_offset), logging.INFO)