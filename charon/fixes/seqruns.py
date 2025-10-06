"""Write out seqrun documents from librep docs.
Only for transfer from version 14.6 to 14.7.
"""

from charon import utils


def write_seqrun_docs(db, libprep):
    for pos, seqrun in enumerate(libprep.get('seqruns', [])):
        doc = seqrun.copy()
        doc['charon_doctype'] = 'seqrun'
        doc['_id'] = utils.get_iuid()
        doc['projectid'] = libprep['projectid']
        doc['sampleid'] = libprep['sampleid']
        doc['libprepid'] = libprep['libprepid']
        doc['seqrunid'] = pos + 1
        doc['runid'] = None
        doc['modified'] = libprep['modified']
        doc['created'] = libprep['created']
        db.save(doc)
        print(doc)



if __name__ == '__main__':
    import sys
    try:
        utils.load_settings(filepath=sys.argv[1])
    except IndexError:
        utils.load_settings()
    db = utils.get_db()
    for id in db:
        doc = db[id]
        if doc.get('charon_doctype') != 'seqrun': continue
        del db[id]
    for id in db:
        doc = db[id]
        if doc.get('charon_doctype') != 'libprep': continue
        write_seqrun_docs(db, doc)
