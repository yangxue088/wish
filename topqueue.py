import heapq


class TopQueue:
    def __init__(self, maxsize):
        self.heap = []
        self.maxsize = int(maxsize)
        heapq.heapify(self.heap)

    def put(self, item):
        if len(self.heap) >= self.maxsize:
            top_item = self.heap[0]
            if top_item < item:
                heapq.heappop(self.heap)
                heapq.heappush(self.heap, item)
                return True
            else:
                return False
        else:
            heapq.heappush(self.heap, item)
            return True

    def get(self):
        return heapq.heappop(self.heap)

    def empty(self):
        return len(self.heap) == 0