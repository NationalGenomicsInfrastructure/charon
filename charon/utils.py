" Charon: Various utility functions. "

import os
import socket
import logging
import urllib.parse
import uuid
import datetime
import unicodedata
from importlib.metadata import version

import tornado.web
from ibmcloudant import CouchDbSessionAuthenticator, cloudant_v1
import ibm_cloud_sdk_core
import yaml

import charon
from . import constants
from . import settings


class CloudantDatabaseWrapper:
    # Wrap a CloudantV1 client to provide a minimal CouchDB-like database interface.
    def __init__(self, client, db_name):
        self.client = client
        self.db_name = db_name

    def __getitem__(self, doc_id):
        """Mimics db['doc_id']"""
        response = self.client.get_document(
            db=self.db_name,
            doc_id=doc_id
        ).get_result()
        return response
    
    def __delitem__(self, doc_id):
        """Mimics del db['doc_id'] - deletes a document by ID"""
        try:
            # Get the document first to obtain the revision
            doc = self.get_document(doc_id)
            response = self.client.delete_document(
                db=self.db_name,
                doc_id=doc_id,
                rev=doc['_rev']
            ).get_result()
            return response
        except Exception as e:
            logging.error(f"Error deleting document {doc_id}: {e}")
            raise KeyError(f"Cannot delete document {doc_id}: {e}")

    def __iter__(self):
        """Make the database wrapper iterable by document IDs"""
        try:
            # Get all document IDs using _all_docs view
            response = self.client.post_all_docs(
                db=self.db_name,
                include_docs=False  # Only get IDs, not full documents
            ).get_result()

            for row in response.get('rows', []):
                yield row['id']
        except Exception as e:
            logging.error(f"Error iterating database: {e}")
            return

    def get(self, doc_id):
        """Get a document by ID, returns None if not found."""
        try:
            response = self.client.get_document(
                db=self.db_name,
                doc_id=doc_id
            ).get_result()
            return response
        except ibm_cloud_sdk_core.api_exception.ApiException as e:
            if e.code == 404:
                return None
            raise KeyError(f"Error fetching document: {e}")

    def view(self, viewname, **options):
        """Mimics db.view(...)"""
        ddoc, view = viewname.split('/')
        response = self.client.post_view(
            db=self.db_name,
            ddoc=ddoc,
            view=view,
            **options
        ).get_result()
        return response.get('rows', [])

    def save(self, document):
        """Mimics db.save(doc)"""
        if '_id' in document:
            doc_id = document['_id']
        else:
            doc_id = uuid.uuid4().hex
            document['_id'] = doc_id
        response = self.client.put_document(
            db=self.db_name,
            doc_id=doc_id,
            document=document
        ).get_result()
        return response

    def delete(self, document):
        """Mimics db.delete(doc)"""
        if '_id' not in document or '_rev' not in document:
            raise ValueError("Document must have '_id' and '_rev' to be deleted")
        response = self.client.delete_document(
            db=self.db_name,
            doc_id=document['_id'],
            rev=document['_rev']
        ).get_result()
        return response

    def get_attachment(self, doc_id, attachment_name):
        """Get an attachment from a document."""
        response = self.client.get_attachment(
            db=self.db_name,
            doc_id=doc_id,
            attachment_name=attachment_name
        ).get_result()
        return response

    def put_attachment(self, doc_id, data, attachment_name, content_type, rev):
        """Put an attachment to a document."""
        response = self.client.put_attachment(
            db=self.db_name,
            doc_id=doc_id,
            attachment=data,
            attachment_name=attachment_name,
            content_type=content_type,
            rev=rev
        ).get_result()
        return response


def load_settings(filepath=None):
    """Load and return the settings from the given settings file,
    or from the first existing file in a predefined list of filepaths.
    Raise IOError if no readable settings file was found.
    Raise KeyError if a settings variable is missing.
    Raise ValueError if the settings variable value is invalid."""
    homedir = os.path.expandvars('$HOME')
    basedir = os.path.dirname(__file__)
    localdir = '/var/local/charon'
    if not filepath:
        hostname = socket.gethostname().split('.')[0]
        for filepath in [os.path.join(homedir, "{0}.yaml".format(hostname)),
                         os.path.join(homedir, 'default.yaml'),
                         os.path.join(basedir, "{0}.yaml".format(hostname)),
                         os.path.join(basedir, 'default.yaml'),
                         os.path.join(localdir, "{0}.yaml".format(hostname)),
                         os.path.join(localdir, 'default.yaml')]:
            if os.path.exists(filepath) and \
               os.path.isfile(filepath) and \
               os.access(filepath, os.R_OK):
                break
        else:
            raise IOError('no readable settings file found')
    with open(filepath) as infile:
        settings.update(yaml.safe_load(infile))
    # Set logging state
    if settings.get('LOGGING_DEBUG'):
        kwargs = {'level':logging.DEBUG}
    else:
        kwargs = {'level':logging.INFO}
    try:
        kwargs['format'] = settings['LOGGING_FORMAT']
    except KeyError:
        pass
    try:
        rotating_file_handler = logging.handlers.RotatingFileHandler(
            settings['LOGGING_FILENAME'],
            mode=settings.get('LOGGING_FILEMODE', 'a'),
            maxBytes=1024 * 1024 * 100,
            backupCount=5
        )  # 5 files of 100MB
        kwargs['handlers'] = [rotating_file_handler]
    except KeyError:
        pass
    logging.basicConfig(**kwargs)
    logging.info("settings from file %s", filepath)
    # Check settings
    for key in ['BASE_URL', 'DB_SERVER', 'DB_DATABASE',
                'DB_USERNAME', 'DB_PASSWORD', 'COOKIE_SECRET', 'AUTH']:
        if key not in settings:
            raise KeyError("no settings['{0}'] item".format(key))
        if not settings[key]:
            raise ValueError("settings['{0}'] has invalid value".format(key))
    # Only Userman is available currently
    key = 'SERVICE'
    if settings['AUTH'].get(key) != 'Userman':
        raise ValueError("settings['{0}'] has invalid value".format(key))
    for key in ['HREF', 'USER_HREF', 'AUTH_HREF', 'API_TOKEN']:
        if key not in settings['AUTH']:
            raise KeyError("no settings['AUTH']['{0}'] item".format(key))
    if len(settings['COOKIE_SECRET']) < 10:
        raise ValueError("settings['COOKIE_SECRET'] too short")
    # Settings computable from others
    settings['DB_SERVER_VERSION'] = get_couchdb_client().get_server_information().get_result().get("version")
    if 'PORT' not in settings:
        parts = urllib.parse.urlparse(settings['BASE_URL'])
        items = parts.netloc.split(':')
        if len(items) == 2:
            settings['PORT'] = int(items[1])
        elif parts.scheme == 'http':
            settings['PORT'] =  80
        elif parts.scheme == 'https':
            settings['PORT'] =  443
        else:
            raise ValueError('could not determine port from BASE_URL')
    return settings

def get_couchdb_client():
    "Return the handle for the CouchDB server."
    try:
        cloudant = cloudant_v1.CloudantV1(
            authenticator=CouchDbSessionAuthenticator(
                settings.get("DB_USERNAME"), settings.get("DB_PASSWORD")
            )
        )
        cloudant.set_service_url(settings.get("DB_SERVER"))
        return cloudant
    except Exception as e:
        raise KeyError("Could not connect to CouchDB server: %s" % str(e))

def get_db():
    "Return the handle for the CouchDB database."
    try:
        return CloudantDatabaseWrapper(get_couchdb_client(), settings['DB_DATABASE'])
    except ibm_cloud_sdk_core.api_exception.ApiException:
        raise KeyError("CouchDB database '%s' does not exist" %
                       settings['DB_DATABASE'])

def get_versions():
    "Get version numbers for software components as list of tuples."
    return [('Charon', charon.__version__),
            ('tornado', tornado.version),
            ('CouchDB server', settings['DB_SERVER_VERSION']),
            ('Cloudant module', version('ibmcloudant'))]

def get_iuid():
    "Return a unique instance identifier."
    return uuid.uuid4().hex

def timestamp(days=None):
    """Current date and time (UTC) in ISO format, with millisecond precision.
    Add the specified offset in days, if given."""
    instant = datetime.datetime.utcnow()
    if days:
        instant += datetime.timedelta(days=days)
    instant = instant.isoformat()
    return instant[:-9] + "%06.3f" % float(instant[-9:]) + "Z"

def to_ascii(value):
    "Convert any non-ASCII character to its closest equivalent."
    if not isinstance(value, str):
        value = str(value, 'utf-8')
    return unicodedata.normalize('NFKD', value).encode('ascii', 'ignore')

def to_bool(value):
    " Convert the value into a boolean, interpreting various string values."
    if not value: return False
    value = value.lower()
    return value in ['true', 'yes'] or value[0] in ['t', 'y']

def log(db, doc, changed={}, current_user=None):
    "Create a log entry for the given document."
    entry = {'_id':get_iuid(),
                'doc':doc['_id'],
                'doctype':doc[constants.DB_DOCTYPE],
                'changed':changed,
                'timestamp':timestamp()}
    entry[constants.DB_DOCTYPE] = constants.LOG
    try:
        if current_user:
            entry['operator'] = current_user['email']
    except KeyError:
        pass
    if changed:
        db.save(entry)

def cmp_timestamp(i, j):
    "Compare the two documents by their 'timestamp' values."
    return cmp(i['timestamp'], j['timestamp'])

def cmp(x, y):
    """
    From the Python porting guide
    Replacement for built-in function cmp that was removed in Python 3

    Compare the two objects x and y and return an integer according to
    the outcome. The return value is negative if x < y, zero if x == y
    and strictly positive if x > y.
    """

    return (x > y) - (x < y)

def delete_project(db, project):
    "Delete the project and all its dependent entities."
    startkey = (project['projectid'], '')
    endkey = (project['projectid'], constants.HIGH_CHAR)
    view_result = db.view('sample/sampleid', include_docs=True, startkey=startkey, endkey=endkey)
    samples = [r['doc'] for r in view_result]
    for sample in samples:
        delete_sample(db, sample)
    delete_logs(db, project['_id'])
    db.delete(project)

def delete_sample(db, sample):
    "Delete the sample and all its dependent entities."
    delete_logs(db, sample['_id'])
    startkey = (sample['projectid'], sample['sampleid'], '')
    endkey = (sample['projectid'], sample['sampleid'], constants.HIGH_CHAR)
    view_result = db.view('libprep/libprepid', include_docs=True, startkey=startkey, endkey=endkey)
    libpreps = [r['doc'] for r in view_result]
    for libprep in libpreps:
        delete_libprep(db, libprep)
    db.delete(sample)

def delete_libprep(db, libprep):
    "Delete the libprep and all its dependent entities."
    delete_logs(db, libprep['_id'])
    startkey = (libprep['projectid'], libprep['sampleid'],
                libprep['libprepid'], '')
    endkey = (libprep['projectid'], libprep['sampleid'],
              libprep['libprepid'], constants.HIGH_CHAR)
    view_result = db.view('seqrun/seqrunid', include_docs=True, startkey=startkey, endkey=endkey)
    seqruns = [r['doc'] for r in view_result]
    for seqrun in seqruns:
        delete_seqrun(db, seqrun)
    logging.debug("deleting libprep %s", startkey)
    db.delete(libprep)

def delete_seqrun(db, seqrun):
    "Delete the seqrun and all its dependent entities."
    delete_logs(db, seqrun['_id'])
    db.delete(seqrun)

def delete_logs(db, id):
    "Delete the log documents for the given doc id."
    ids = [r['id'] for r in db.view('log/doc', key=id)]
    for id in ids:
        del db[id]

class QueueHandler(logging.Handler):
    """
    This handler sends events to a queue. Typically, it would be used together
    with a multiprocessing Queue to centralise logging to file in one process
    (in a multi-process application), so as to avoid file write contention
    between processes.

    This code is new in Python 3.2, but this class can be copy pasted into
    user code for use with earlier Python versions.
    """

    def __init__(self, queue):
        """
        Initialise an instance, using the passed queue.
        """
        logging.Handler.__init__(self)
        self.queue = queue

    def enqueue(self, record):
        """
        Enqueue a record.

        The base implementation uses put_nowait. You may want to override
        this method if you want to use blocking, timeouts or custom queue
        implementations.
        """
        self.queue.put_nowait(record)

    def prepare(self, record):
        """
        Prepares a record for queuing. The object returned by this method is
        enqueued.

        The base implementation formats the record to merge the message
        and arguments, and removes unpickleable items from the record
        in-place.

        You might want to override this method if you want to convert
        the record to a dict or JSON string, or send a modified copy
        of the record while leaving the original intact.
        """
        # The format operation gets traceback text into record.exc_text
        # (if there's exception data), and also puts the message into
        # record.message. We can then use this to replace the original
        # msg + args, as these might be unpickleable. We also zap the
        # exc_info attribute, as it's no longer needed and, if not None,
        # will typically not be pickleable.
        self.format(record)
        record.msg = record.message
        record.args = None
        record.exc_info = None
        return record

    def emit(self, record):
        """
        Emit a record.

        Writes the LogRecord to the queue, preparing it for pickling first.
        """
        try:
            self.enqueue(self.prepare(record))
        except Exception:
            self.handleError(record)
