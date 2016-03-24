# -*- coding: utf-8 -*-
import json
from urllib import quote, urlencode

import re
import scrapy

from .. import items


class WishMerchantSpider(scrapy.Spider):
    name = "wishmerchant"
    allowed_domains = ["wish.com"]
    start_urls = (
        'http://www.wish.com/',
    )

    merchants = set()

    xsrfpattern = re.compile(r'.*_xsrf=(.*?);')

    def __init__(self, username, password, merchant, ajaxcount=100):
        self.username = username
        self.password = password
        self.ajaxcount = ajaxcount
        self.merchant = merchant

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
                callback=self.request_merchant)

    def request_merchant(self, response):
        merchant_name = self.merchant
        if merchant_name not in self.merchants:
            self.merchants.add(merchant_name)
            merchant_url = "https://www.wish.com/merchant/%s" % merchant_name
            return scrapy.Request(merchant_url, meta={'xsrf': response.meta['xsrf']}, callback=self.parse_merchant_page)

    def parse_merchant_page(self, response):
        xscript = response.xpath('//script')

        next_offset = xscript.re_first("\['next_offset'\] = (.*?);")
        merchant_name = xscript.re_first("\['merchant_name'\] = \"(.*?)\";")
        urls = xscript.re(r'"external_url": "(.*?)"')

        print 'page:{}'.format(len(urls))
        for url in urls:
            item = items.WishItem()
            item['url'] = url
            # item['merchant'] = merchant_name
            yield item

        if len(urls) > 0:
            yield self.feed_merchant_ajax(response.meta['xsrf'], merchant_name, next_offset, urls)

    def feed_merchant_ajax(self, xsrf, merchant_name, offset, last_cids, num_results=0):
        formdata = {
            'start': str(offset),
            'query': merchant_name,
            'is_commerce': 'true',
            'transform': 'true',
            'count': str(self.ajaxcount),
            'include_buy_link': 'true',
            'num_results': str(num_results),
            '_buckets': '',
            '_experiments': '',
            'last_cids[]': last_cids
        }

        return scrapy.Request('https://www.wish.com/api/merchant', method='POST', body=urlencode(formdata),
                              headers={
                                  'Accept': 'application/json, text/javascript, */*; q=0.01',
                                  'Content-Type': ' application/x-www-form-urlencoded; charset=UTF-8',
                                  'X-Requested-With': 'XMLHttpRequest',
                                  'X-XSRFToken': xsrf
                              }, meta={'xsrf': xsrf}, callback=self.parse_merchant_ajax)

    def parse_merchant_ajax(self, response):
        json_data = json.loads(response.body)
        data = json_data.get('data', None)
        if data is not None:
            next_offset = data.get('next_offset')
            num_results = data.get('num_results')
            merchant_name = data.get('merchant_info')['name']

            urls = []
            for result in data.get('results'):
                url = result.get('external_url')
                urls.append(url)
                item = items.WishItem()
                item['url'] = url
                # item['merchant'] = merchant_name
                yield item

            if len(urls) > 0:
                yield self.feed_merchant_ajax(response.meta['xsrf'], merchant_name, next_offset, urls, num_results)
