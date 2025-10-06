"Test speed of CouchDB connection."

import time
import uuid

from charon import utils


def do_create(db, total=400):
    timer = Timer()
    count = 0
    for i in range(total):
        doc = dict(id=uuid.uuid4().hex,
                   number=i,
                   doctype='garbage')
        db.save(doc)
        count += 1
    print('create', count, timer)

def do_read(db):
    timer = Timer()
    count = 0
    for key in db:
        doc = db[key]
        # print doc.id
        count += 1
    print('read', count, timer)

def do_delete(db):
    timer = Timer()
    count = 0
    for key in list(db):
        doc = db[key]
        try:
            if doc['doctype'] == 'garbage':
                del db[key]
                count += 1
        except KeyError:
            pass
    print('delete', count, timer)


class Timer(object):

    def __init__(self):
        self.start_cpu = time.clock()
        self.start_wall = time.time()

    def __str__(self):
        return "wall: %.2f, cpu: %s" % (self.wall, self.cpu)

    @property
    def cpu(self):
        return time.clock() - self.start_cpu

    @property
    def wall(self):
        return time.time() - self.start_wall


if __name__ == '__main__':
    import sys
    COUCHDB_SERVER = sys.argv[1]
    COUCHDB_DATABASE = 'charon'
    db = utils.get_db()
    do_create(db)
    do_read(db)
    do_delete(db)
