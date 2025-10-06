" Charon: base API request handlers. "

import json
import logging

import tornado.web
import ibm_cloud_sdk_core
import requests

from . import constants
from . import settings
from . import utils
from .requesthandler import RequestHandler
from .user import UserSaver


class ApiRequestHandler(RequestHandler):
    "Check API token unless logged in."

    saver = None

    def prepare(self):
        super(ApiRequestHandler, self).prepare()
        self.check_api_access()


    def check_api_access(self):
        """Check the API token given in the header.
        Return HTTP 401 if invalid or missing key."""
        if self.get_current_user(): return
        try:
            api_token = self.request.headers['X-Charon-API-token']
        except KeyError:
            self.send_error(401, reason='API token missing')
        else:
            rows = list(self.db.view('user/api_token', key=api_token))
            if len(rows) != 1:
                self.send_error(401, reason='invalid API token')
            else:
                try:
                    user = self.get_user(rows[0]['value'])
                except KeyError:
                    self.send_error(401, reason='invalid user email')
                else:
                    if user.get('status') == constants.ACTIVE:
                        self._user = user
                        logging.debug("API token user '%s'", user['email'])
                    else:
                        self.send_error(401, reason='user not active')

    def add_link(self, doc, rel, name, *args):
        """Add a link to JSON representation of an entity.
        The name is the reverse_url handler."""
        link = dict(rel=rel, href=self.get_absolute_url(name, *args))
        doc.setdefault('links', []).append(link)

    def add_project_links(self, project):
        "Add the links to a project representation."
        projectid = project['projectid']
        self.add_link(project, 'self', 'api_project', projectid)
        self.add_link(project, 'samples', 'api_samples', projectid)
        self.add_link(project, 'libpreps', 'api_project_libpreps', projectid)
        self.add_link(project, 'seqruns', 'api_project_seqruns', projectid)
        self.add_link(project, 'logs', 'api_logs', project['_id'])

    def add_sample_links(self, sample):
        "Add the links to a sample representation."
        projectid = sample['projectid']
        sampleid = sample['sampleid']
        self.add_link(sample, 'project', 'api_project', projectid)
        self.add_link(sample, 'self', 'api_sample', projectid, sampleid)
        self.add_link(sample, 'libpreps', 'api_sample_libpreps',
                      projectid, sampleid)
        self.add_link(sample, 'seqruns', 'api_sample_seqruns',
                      projectid, sampleid)
        self.add_link(sample, 'logs', 'api_logs', sample['_id'])

    def add_libprep_links(self, libprep):
        "Add the links to a libprep representation."
        projectid = libprep['projectid']
        sampleid = libprep['sampleid']
        libprepid = libprep['libprepid']
        self.add_link(libprep, 'project', 'api_project', projectid)
        self.add_link(libprep, 'sample', 'api_sample', projectid, sampleid)
        self.add_link(libprep, 'self', 'api_libprep',
                      projectid, sampleid, libprepid)
        self.add_link(libprep, 'seqruns', 'api_libprep_seqruns',
                      projectid, sampleid, libprepid)
        self.add_link(libprep, 'logs', 'api_logs', libprep['_id'])

    def add_seqrun_links(self, seqrun):
        "Add the links to a seqrun representation."
        projectid = seqrun['projectid']
        sampleid = seqrun['sampleid']
        libprepid = seqrun['libprepid']
        seqrunid = seqrun['seqrunid']
        self.add_link(seqrun, 'project', 'api_project', projectid)
        self.add_link(seqrun, 'sample', 'api_sample', projectid, sampleid)
        self.add_link(seqrun, 'libprep', 'api_libprep',
                      projectid, sampleid, libprepid)
        self.add_link(seqrun, 'self', 'api_seqrun',
                      projectid, sampleid, libprepid, seqrunid)
        self.add_link(seqrun, 'logs', 'api_logs', seqrun['_id'])


class ApiDocument(ApiRequestHandler):
    "Access a database document as is."

    def get(self, id):
        "Return a database document as is."
        try:
            self.write(self.db[id])
        except ibm_cloud_sdk_core.api_exception.ApiException:
            self.send_error(404, reason='no such item')


class ApiLogs(ApiRequestHandler):
    "Access log event documents for a given document."

    def get(self, id):
        "Return all log event documents for a given document."
        self.write(dict(logs=self.get_logs(id)))


class ApiNotify(ApiRequestHandler):
    """Notify this web service of an event in some other system.
    This web service is free to ignore the event.
    No API token is required for this call."""

    def check_api_access(self):
        pass

    def post(self):
        """Handle 'user' event; fetch new data.
        Userman is the authentication server."""
        logging.debug('API notify')
        try:
            data = json.loads(self.request.body)
            logging.debug("API notify post data: %s", data)
            # Only the designated authentication server is allowed to do this.
            if not data.get('event') == 'user':
                raise ValueError("event is not 'user'")
            href = data.get('href', '')
            if not href.startswith(settings['AUTH']['HREF']):
                raise ValueError("wrong Userman host: %s", href)
        except Exception as msg:
            logging.warning("API notify post error: %s", msg)
            self.send_error(400, reason=str(msg))
        else:
            self.set_status(202)
            try:
                headers = {'X-Userman-API-token': settings['AUTH']['API_TOKEN']}
                data = dict(service='Charon')
                response = requests.post(href, headers=headers,
                                         data=json.dumps(data))
                if response.status_code != requests.codes.ok:
                    raise ValueError("Userman error: %s %s",
                                     response.status_code,
                                     response.reason)
                data = response.json()
                user = self.get_user(data['email'])
                user.update(data)
                with UserSaver(doc=user, rqh=self):
                    pass            # Changes already made.
            except Exception as msg:
                logging.debug("API notify request error: %s", msg)
