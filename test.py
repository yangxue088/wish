from topqueue import TopQueue

if __name__ == '__main__':
    queue = TopQueue(10)

    for i in range(0, 100):
        print i
        queue.put((i, 'a'))

    print 'result:'
    while not queue.empty():
        print queue.get()
    print 'finish'

