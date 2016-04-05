# -*- coding: utf-8 -*-
from urllib import urlencode

import re
import scrapy
from pybloom import ScalableBloomFilter


class WishLoginSpider(scrapy.Spider):
    name = "wishlogin"
    allowed_domains = ["wish.com"]
    start_urls = (
        'http://www.wish.com/',
    )

    merchants = ScalableBloomFilter(mode=ScalableBloomFilter.LARGE_SET_GROWTH)

    xsrfpattern = re.compile(r'.*_xsrf=(.*?);')

    def __init__(self, username, password, ajaxcount=100):
        self.username = username
        self.password = password
        self.ajaxcount = ajaxcount

        from scrapy import optional_features
        optional_features.remove('boto')

    def start_requests(self):
        yield scrapy.Request('https://www.wish.com/', callback=self.login)

    def login(self, response):
        match = self.xsrfpattern.match(str(response.headers))

        if match:
            xsrf = match.group(1)

            body = urlencode({
                'email': self.username,
                'password': self.password,
                '_buckets': '',
                '_experiments': '',
            })

            print body

            request = scrapy.Request(
                'https://www.wish.com/api/email-login',
                method='POST',
                headers={
                    'Accept': 'application/json, text/javascript, */*; q=0.01',
                    'Accept-Encoding': 'gzip, deflate',
                    'Accept-Language': 'en-US,en;q=0.8,zh-CN;q=0.6',
                    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-XSRFToken': xsrf,
                },
                body=body, meta={
                    'xsrf': xsrf
                },
                callback=self.request_tab)

            print request.headers

            yield request

    def request_tab(self, response):
        print response.body
