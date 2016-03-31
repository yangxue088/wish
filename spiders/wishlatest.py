# -*- coding: utf-8 -*-
import json
from urllib import quote, urlencode

import re
import scrapy
from pybloom import ScalableBloomFilter


class WishLatestSpider(scrapy.Spider):
    name = "wishlatest"
    allowed_domains = ["wish.com"]
    start_urls = (
        'https://www.wish.com/',
    )

    xsrfpattern = re.compile(r'.*_xsrf=(.*?);')

    def __init__(self, username, password, ajaxcount=100):
        self.username = username
        self.password = password
        self.ajaxcount = 66

    def start_requests(self):
        yield scrapy.Request('https://www.wish.com/', callback=self.login)

    def login(self, response):
        match = self.xsrfpattern.match(str(response.headers))

        if match:
            xsrf = match.group(1)
            yield scrapy.Request(
                'https://www.wish.com/api/email-login?email={}&password={}&_buckets=&_experiments='.format(
                    quote(self.username), quote(self.password)),
                method='POST',
                headers={
                    'Accept': 'application/json, text/javascript, */*; q=0.01',
                    'Content-Type': ' application/x-www-form-urlencoded; charset=UTF-8',
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-XSRFToken': xsrf
                }, meta={'xsrf': xsrf},
                callback=self.request_tab)

    def request_tab(self, response):
        tabs = {'Latest': 'tabbed_feed_latest'}

        for tabname, tabid in tabs.items():
            yield self.feed_tab_ajax(response.meta['xsrf'], tabname, tabid)

    def feed_tab_ajax(self, xsrf, tabname, tabid, offset=0):
        formdata = {
            'count': str(self.ajaxcount),
            'offset': str(offset),
            'request_id': tabid,
            'request_categories': 'false',
            '_buckets': '',
            '_experiments': ''
        }

        return scrapy.Request(
            'https://www.wish.com/api/feed/get-filtered-feed',
            method='POST', body=urlencode(formdata),
            headers={
                'Accept': 'application/json, text/javascript, */*; q=0.01',
                'Content-Type': ' application/x-www-form-urlencoded; charset=UTF-8',
                'X-Requested-With': 'XMLHttpRequest',
                'X-XSRFToken': xsrf
            },
            meta={
                'xsrf': xsrf,
                'tabname': tabname,
                'tabid': tabid
            },
            callback=self.parse_tab_ajax)

    def parse_tab_ajax(self, response):
        json_data = json.loads(response.body)
        data = json_data.get('data', None)
        if data is not None:
            tabname = response.meta['tabname']

            next_offset = data.get('next_offset')
            no_more_items = data.get('no_more_items', True)
            products = data.get('products', [])

            print '{} tab parse products:{}, next_offset:{}'.format(tabname, len(products), next_offset)

            if not no_more_items:
                yield self.feed_tab_ajax(response.meta['xsrf'], response.meta['tabname'], response.meta['tabid'],
                                         next_offset)
