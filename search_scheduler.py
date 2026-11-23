"""Coalesce live query edits and run cancellable searches outside the UI thread."""

from dataclasses import dataclass, field
import threading
import time

from command_search_index import SearchResults


@dataclass
class _Request:
    number: int
    query: str
    due: float
    cancelled: threading.Event = field(default_factory=threading.Event)
    dispatched: bool = False


class HybridSearch:
    def __init__(self, search, delay=.25, clock=time.monotonic):
        self.search, self.delay, self.clock = search, delay, clock
        self.condition = threading.Condition()
        self.current = self.job = self.ready = None
        self.serial = self.applied = 0
        self.closed = False
        self.thread = threading.Thread(target=self._run, name='command-search', daemon=True)
        self.thread.start()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    @property
    def pending(self):
        with self.condition:
            return not self.closed and self.current is not None and self.applied != self.current.number

    @property
    def status(self):
        with self.condition:
            if not self.pending:
                return ''
            return 'Searching...' if self.current.dispatched else 'Waiting for typing to pause...'

    def request(self, query, immediate=False):
        with self.condition:
            if self.closed:
                raise RuntimeError('search is closed')
            if self.current:
                self.current.cancelled.set()
            self.serial += 1
            self.current = _Request(self.serial, query, self.clock() + (0 if immediate else self.delay))
            self.job = self.ready = None
            if not query.strip():
                self.current.dispatched = True
                self.ready = (self.serial, SearchResults())
            self.condition.notify()

    def expedite(self):
        with self.condition:
            if self.pending and not self.current.dispatched:
                self.current.due = self.clock()

    def poll(self):
        with self.condition:
            if self.closed or self.current is None:
                return None
            if self.ready is not None:
                number, result = self.ready
                self.ready = None
                if number == self.current.number:
                    self.applied = number
                    return result
            if not self.current.dispatched and self.clock() >= self.current.due:
                self.current.dispatched = True
                self.job = self.current
                self.condition.notify()
        return None

    def _run(self):
        while True:
            with self.condition:
                self.condition.wait_for(lambda: self.closed or self.job is not None)
                if self.closed:
                    return
                request, self.job = self.job, None
            try:
                result = self.search(request.query, request.cancelled.is_set)
            except Exception as error:
                result = SearchResults(error=f'Search failed: {error}')
            with self.condition:
                if not self.closed and not request.cancelled.is_set() and request is self.current:
                    self.ready = (request.number, result)
            del result

    def close(self):
        with self.condition:
            if self.closed:
                return
            self.closed = True
            if self.current:
                self.current.cancelled.set()
            self.job = self.ready = None
            self.condition.notify()
        self.thread.join()
