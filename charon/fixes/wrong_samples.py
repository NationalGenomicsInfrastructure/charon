"""Delete samples that got no sampleid.
"""

from charon import utils



if __name__ == '__main__':
    import sys
    try:
        utils.load_settings(filepath=sys.argv[1])
    except IndexError:
        utils.load_settings()
    db = utils.get_db()
    total = 0
    count = 0
    for id in db:
        doc = db[id]
        if doc.get('charon_doctype') != 'sample': continue
        total += 1
        if 'sampleid' not in doc:
            db.delete(doc)
            count += 1
    print(total, count)
