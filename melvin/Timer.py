import time


class Timer:
    """Keeps track of current runtime"""

    _start_time = 0.0
    diff = 0.0

    def __time(self):
        return time.time()

    def start(self):
        self._start_time = self.__time()

    def split(self):
        self.diff = self.__time() - self._start_time
        self.start()
