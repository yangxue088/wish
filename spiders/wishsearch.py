# -*- coding: utf-8 -*-
import ConfigParser
import datetime
import json
import logging
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from urllib import quote, urlencode

import os
import scrapy

from ..topqueue import TopQueue


class WishSearchSpider(scrapy.Spider):
    name = "wishsearch"
    allowed_domains = ["wish.com"]
    start_urls = (
        'http://www.wish.com/',
    )

    xsrfpattern = re.compile(r'.*_xsrf=(.*?);')

    def __init__(self, config='search.ini'):
        cf = ConfigParser.ConfigParser()
        cf.read(config)

        self.username = cf.get('wish', 'username')
        self.password = cf.get('wish', 'password')
        self.word = cf.get('wish', 'word')
        self.queue = TopQueue(cf.get('wish', 'top'))

        self.mailuser = cf.get('mail', 'username')
        self.mailpass = cf.get('mail', 'password')
        self.mailsmtp = cf.get('mail', 'smtp')
        self.mailfrom = cf.get('mail', 'from')
        self.mailtos = cf.get('mail', 'tos').split(',')

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
                if self.queue.put((rating_count, url)):
                    feed_continue = True

            if not feed_ended and feed_continue:
                yield self.continue_search_ajax(next_offset, urls)
            else:
                search = []
                while not self.queue.empty():
                    search.append(self.queue.get())

                search.sort(reverse=True)

                self.process_result('{}    {}{}'.format(item[1], item[0], '\r\n') for item in search)

    def process_result(self, result):
        filename = '{}-{}.txt'.format(self.word,
                                      self.queue.maxsize)

        dirname = os.path.join('target', datetime.datetime.now().strftime("%Y-%m-%d"))
        if not os.path.exists(dirname):
            os.makedirs(dirname)

        resultfile = os.path.join(os.getcwd(), dirname, filename)

        with open(resultfile, 'w') as f:
            f.writelines(result)
            self.log('scrapy search wish finish, result file is {}'.format(f.name), logging.INFO)

        self.mail(resultfile)

    def mail(self, resultfile):
        msg = MIMEMultipart()

        text = '时间：{}\n关键词：{}\n前N个：{}\n（搜索结构按评价数量从多到少排列）'.format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                                                 self.word, self.queue.maxsize)

        content = MIMEText(text, _charset='utf-8')
        msg.attach(content)

        attach = MIMEText(open(resultfile, 'rb').read(), 'base64', 'utf-8')
        attach["Content-Type"] = 'application/octet-stream'
        attach["Content-Disposition"] = 'attachment; filename="{}"'.format(resultfile.split('/')[-1])
        msg.attach(attach)

        msg['to'] = ','.join(self.mailtos)
        msg['from'] = self.mailfrom
        msg['subject'] = 'WISH搜索结果通知'

        try:
            server = smtplib.SMTP()
            server.connect(self.mailsmtp)
            server.login(self.mailuser, self.mailpass)
            server.sendmail(self.mailfrom, self.mailtos, msg.as_string())
            server.quit()
            self.log('mail send success, word:{}, top:{}'.format(self.word, self.queue.maxsize), logging.INFO)
        except Exception, e:
            print str(e)
