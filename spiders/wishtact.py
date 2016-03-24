# -*- coding: utf-8 -*-
import json
import logging
from urllib import quote, urlencode

import re
import scrapy
from pybloom import ScalableBloomFilter

from .. import items


class WishTactSpider(scrapy.Spider):
    name = "wishtact"
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
        tabs = {'Latest': 'tabbed_feed_latest', 'Recently Viewed': 'recently_viewed__tab',
                'Accessories': 'tag_53dc186421a86318bdc87f16', 'Hobbies': 'tag_54ac6e18f8a0b3724c6c473f',
                'Gadgets': 'tag_53dc186421a86318bdc87f20', 'Fashion': 'tag_53dc186321a86318bdc87ef8',
                'Home Decor': 'tag_53e9157121a8633c567eb0c2', 'Watches': 'tag_53dc186421a86318bdc87f1c',
                'Tops': 'tag_53dc186321a86318bdc87ef9', 'Phone Upgrades': 'tag_53dc186421a86318bdc87f0f',
                'Shoes': 'tag_53dc186421a86318bdc87f31',
                'Wallets & Bags': 'tag_53dc186421a86318bdc87f22', 'Bottoms': 'tag_53dc186321a86318bdc87f07',
                'Underwear': 'tag_53dc2e9e21a86346c126eae4'}

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
            next_offset = data.get('next_offset')
            no_more_items = data.get('no_more_items', True)
            products = data.get('products', [])

            for product in products:
                url = product.get('external_url')
                yield scrapy.Request(url, meta={'xsrf': response.meta['xsrf']}, callback=self.request_merchant)
            if not no_more_items:
                self.log('feed tab ajax:{}, offset:{}'.format(response.meta['tabname'], next_offset), logging.INFO)
                yield self.feed_tab_ajax(response.meta['xsrf'], response.meta['tabname'], response.meta['tabid'],
                                         next_offset)
            else:
                self.log('feed tab ajax:{}, total:{}'.format(response.meta['tabname'], next_offset), logging.INFO)

    def request_merchant(self, response):
        xscript = response.xpath('//script')
        merchant_name = xscript.re_first(r'"merchant_name": "(.*?)",')
        merchant_rating = xscript.re_first(r'"merchant_rating": (.*?),')
        merchant_rating_count = xscript.re_first(r'"merchant_rating_count": (.*?),')

        if merchant_name.startswith('\u'):
            merchant_name = eval("'" + merchant_name.decode('unicode-escape') + "'")

        if merchant_name not in self.merchants:
            self.merchants.add(merchant_name)
            if int(merchant_rating_count) >= 10000 and float(merchant_rating) >= 4.0:
                self.log(
                    'found merchant:{}, count:{}, rating:{}'.format(merchant_name, merchant_rating_count,
                                                                    merchant_rating),
                    logging.INFO)
                merchant_url = "https://www.wish.com/merchant/%s" % quote(merchant_name)
                yield scrapy.Request(merchant_url, meta={'xsrf': response.meta['xsrf']},
                                     callback=self.parse_merchant_page)

    def parse_merchant_page(self, response):
        xscript = response.xpath('//script')

        next_offset = xscript.re_first("\['next_offset'\] = (.*?);")
        merchant_name = xscript.re_first("\['merchant_name'\] = \"(.*?)\";")

        if merchant_name.startswith('\u'):
            merchant_name = eval("'" + merchant_name.decode('unicode-escape') + "'")

        match = re.search("\['orig_feed_items'\] = (\[.*?\]);\n", response.body)
        if match:
            feed_items = match.group(1)
            products = json.loads(feed_items)

            urls = []
            for product in products:
                url = product.get('external_url')
                urls.append(url)

                product_rating = product['product_rating']
                if product_rating['rating_count'] >= 1000 and product_rating['rating'] >= 4.0:
                    self.log('found product:{}, count:{}, rating:{}, merchant:{}'.format(url,
                                                                                         product_rating['rating_count'],
                                                                                         product_rating['rating'],
                                                                                         merchant_name),
                             logging.INFO)
                    item = items.WishItem()
                    item['url'] = url
                    yield item

            if len(products) > 0:
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

            if merchant_name.startswith('\u'):
               merchant_name = eval("'" + merchant_name.decode('unicode-escape') + "'")

            urls = []
            for result in data.get('results'):
                url = result.get('external_url')
                urls.append(url)

                product_rating = result['product_rating']
                if product_rating['rating_count'] >= 1000 and product_rating['rating'] >= 4.0:
                    self.log('found product:{}, count:{}, rating:{}, merchant:{}'.format(url,
                                                                                         product_rating['rating_count'],
                                                                                         product_rating['rating'],
                                                                                         merchant_name),
                             logging.INFO)
                    item = items.WishItem()
                    item['url'] = url
                    yield item

            if len(urls) > 0:
                self.log('feed merchant ajax:{}, offset:{}'.format(merchant_name, next_offset), logging.INFO)
                yield self.feed_merchant_ajax(response.meta['xsrf'], merchant_name, next_offset, urls, num_results)
            else:
                self.log('feed merchant ajax:{}, total:{}'.format(merchant_name, next_offset), logging.INFO)

