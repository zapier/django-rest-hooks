import threading
import collections

import requests


class FlushThread(threading.Thread):
    def __init__(self, client):
        threading.Thread.__init__(self)
        self.client = client

    def run(self):
        self.client.sync_flush()


class Client(object):
    """
    Manages a simple pool of threads to flush the queue of requests.
    """
    def __init__(self, num_threads=3):
        self.queue = collections.deque()

        self.flush_lock = threading.Lock()
        self.num_threads = num_threads
        self.flush_threads = [FlushThread(self) for _ in range(self.num_threads)]
        self.total_sent = 0

    def enqueue(self, method, *args, **kwargs):
        self.queue.append((method, args, kwargs))
        self.refresh_threads()

    def get(self, *args, **kwargs):
        self.enqueue('get', *args, **kwargs)

    def post(self, *args, **kwargs):
        self.enqueue('post', *args, **kwargs)

    def put(self, *args, **kwargs):
        self.enqueue('put', *args, **kwargs)

    def delete(self, *args, **kwargs):
        self.enqueue('delete', *args, **kwargs)

    def refresh_threads(self):
        with self.flush_lock:
            # refresh if there are jobs to do and no threads are alive
            if len(self.queue) > 0:
                to_refresh = [index for index, thread in enumerate(self.flush_threads) if not thread.is_alive()]
                for index in to_refresh:
                    self.flush_threads[index] = FlushThread(self)
                    self.flush_threads[index].start()

    def sync_flush(self):
        session = requests.Session()
        while self.queue:
            method, args, kwargs = self.queue.pop()
            getattr(session, method)(*args, **kwargs)
            self.total_sent += 1
