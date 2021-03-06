import re
import requests
from lib.log import LogHandler
import pika
import yaml
import json
from pymongo import MongoClient
import gevent
from lib.standardization import standard_city, standard_region, StandarCityError
import asyncio
import aiohttp
import time
from multiprocessing import Process

connection = pika.BlockingConnection(pika.ConnectionParameters(
    host='114.80.150.195',
    port=5673,
    heartbeat=0
))
channel = connection.channel()
channel.queue_declare(queue='51job_id')

client = MongoClient(host='114.80.150.196',
                     port=27777,
                     username='goojia',
                     password='goojia7102')
db = client['company']
collection = db['company_crawler']


def job_start_produce():
    companys = collection.find({'company_source': '51job'}, no_cursor_timeout=True)
    id_list = []
    for company in companys:
        company_id = company['company_id']
        id_list.append(company_id)
        if len(id_list) == 200:
            channel.basic_publish(
                exchange='',
                routing_key='51job_id',
                body=json.dumps(id_list)
            )
            id_list.clear()


class JobConsumer:

    def start_consume(self):
        channel.basic_qos(prefetch_count=10)
        channel.basic_consume(
            self.callback,
            queue='51job_id'
        )
        channel.start_consuming()

    def callback(self, ch, method, properties, body):
        ids = json.loads(body.decode())
        loop = asyncio.get_event_loop()
        tasks = [self.start_async(id) for id in ids]
        loop.run_until_complete(asyncio.wait(tasks))
        ch.basic_ack(delivery_tag=method.delivery_tag)

    async def start_async(self, id):
        await self.update_data(await self.standar_address(await self.find_mongo(id)))

    async def find_mongo(self, id):
        start_time = time.time()
        company = collection.find_one({'company_source': '51job', 'company_id': id}, no_cursor_timeout=True)
        return company

    async def standar_address(self, company):
        address = company['address']
        result, real_city = standard_city(address)
        if result:
            company['fj_city'] = real_city
            r, real_region = standard_region(real_city, address)
            if r:
                company['fj_region'] = real_region
            else:
                company['fj_region'] = None
        else:
            company['fj_city'] = None
            company['fj_region'] = None
        return company

    async def update_data(self, company):
        collection.update_one({'company_id': company['company_id'], 'company_source': company['company_source']},
                              {'$set': company})
        print('{}已经更新了'.format(company['company_id']))

if __name__ == '__main__':
    # job_start_produce()
    Process(target=JobConsumer().start_consume).start()
    Process(target=JobConsumer().start_consume).start()
    Process(target=JobConsumer().start_consume).start()
    Process(target=JobConsumer().start_consume).start()
