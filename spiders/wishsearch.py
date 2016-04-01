# -*- coding: utf-8 -*-
import json
from urllib import quote, urlencode

import re
import scrapy

from ..topqueue import TopQueue


class WishSearchSpider(scrapy.Spider):
    name = "wishsearch"
    allowed_domains = ["wish.com"]
    start_urls = (
        'http://www.wish.com/',
    )

    xsrfpattern = re.compile(r'.*_xsrf=(.*?);')

    def __init__(self, username, password, word, top=100):
        self.username = username
        self.password = password
        self.word = word
        self.queue = TopQueue(top)
        self.xsrf = ''

    def start_requests(self):
        yield scrapy.Request('https://www.wish.com/', callback=self.login)

    def login(self, response):
        match = self.xsrfpattern.match(str(response.headers))

        if match:
            self.xsrf = match.group(1)

            yield scrapy.Request(
                'https://www.wish.com/api/email-login?email={}&password={}&_buckets=&_experiments='.format(
                    quote(self.username), quote(self.password)),
                method='POST',
                headers={
                    'Accept': 'application/json, text/javascript, */*; q=0.01',
                    'Content-Type': ' application/x-www-form-urlencoded; charset=UTF-8',
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-XSRFToken': self.xsrf,
                },
                callback=self.start_search_ajax)

    def start_search_ajax(self, response):
        data = {
            'query': self.word,
            'count': '10',
            'transform': 'true',
            '_buckets': '',
            '_experiments': '',
        }
        return self.feed_search_ajax(data)

    def continue_search_ajax(self, start, urls):
        data = {
            'start': str(start),
            'query': self.word,
            'transform': 'true',
            '_buckets': '',
            '_experiments': '',
            'last_cids[]': urls,
        }
        return self.feed_search_ajax(data)

    def feed_search_ajax(self, data):
        return scrapy.Request('https://www.wish.com/api/search', method='POST', body=urlencode(data),
                              headers={
                                  'Accept': 'application/json, text/javascript, */*; q=0.01',
                                  'Content-Type': ' application/x-www-form-urlencoded; charset=UTF-8',
                                  'X-Requested-With': 'XMLHttpRequest',
                                  'X-XSRFToken': self.xsrf,
                              }, callback=self.parse_search_ajax)

    def parse_search_ajax(self, response):
        json_data = json.loads(response.body)
        data = json_data.get('data', None)
        if data is not None:
            next_offset = data.get('next_offset')
            feed_ended = data.get('feed_ended')

            feed_continue = False
            urls = []
            for result in data.get('results'):
                url = result.get('external_url')
                urls.append(url)

                rating_count = result.get('product_rating').get('rating_count')
                print (rating_count, url)
                if self.queue.put((rating_count, url)):
                    feed_continue = True

            if not feed_ended and feed_continue:
                yield self.continue_search_ajax(next_offset, urls)
            else:
                print 'result:'
                while not self.queue.empty():
                    print self.queue.get()
                print 'finish.'
