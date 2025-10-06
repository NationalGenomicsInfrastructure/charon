" Charon: RequestHandler subclass."

import logging
import urllib.parse
import weakref
import functools

import tornado.web

import charon
from . import settings
from . import constants
from . import utils


class RequestHandler(tornado.web.RequestHandler):
    "Base request handler."

    def prepare(self):
        "Get the database connection. Set up caches."
        self.db = utils.get_db()
        self._cache = {}
        self._users = {}
        self._projects = {}
        self._samples = {}
        self._libpreps = {}
        self._seqruns = {}
    
    def on_finish(self):
        self._cache.clear()
        self._users.clear()
        self._projects.clear()
        self._samples.clear()
        self._libpreps.clear()
        self._seqruns.clear()

    def get_template_namespace(self):
        "Set the variables accessible within the template."
        result = super(RequestHandler, self).get_template_namespace()
        result['version'] = charon.__version__
        result['settings'] = settings
        result['constants'] = constants
        result['current_user'] = self.get_current_user()
        return result

    def get_absolute_url(self, name, *args, **kwargs):
        "Get the absolute URL given the handler name and any arguments."
        if name is None:
            path = ''
        else:
            path = self.reverse_url(name, *args)
        url = settings['BASE_URL'].rstrip('/') + path
        if kwargs:
            url += '?' + urllib.parse.urlencode(kwargs)
        return url

    def get_current_user(self):
        """Get the currently logged-in user.
        Send to login page if none."""
        try:
            status = self._user.get('status')
        except AttributeError:
            email = self.get_secure_cookie(constants.USER_COOKIE_NAME)
            if email:
                try:
                    email = email.decode('utf-8')
                    user = self.get_user(email)
                except tornado.web.HTTPError:
                    return None
                if user.get('status') != constants.ACTIVE:
                    return None
                self._user = user
            else:
                try:
                    api_token = self.request.headers['X-Charon-API-token']
                    rows = list(self.db.view('user/api_token', key=api_token))
                    if len(rows) != 1: raise KeyError
                    user = self.get_user(rows[0]['value'])
                    if user.get('status') != constants.ACTIVE: raise KeyError
                except KeyError:
                    return None
                else:
                    logging.debug("API token user '%s'", user['email'])
                    self._user = user
        else:
            if status != constants.ACTIVE:
                self.set_secure_cookie(constants.USER_COOKIE_NAME, '')
                del self._user
                return None
        return self._user

    def get_user(self, email):
        """Get the user identified by the email address.
        Raise HTTP 404 if no such user."""
        try:
            return self._users[email]
        except KeyError:
            return self.get_and_cache('user/email', email, self._users)

    def get_project(self, projectid):
        """Get the project by the projectid.
        Raise HTTP 404 if no such project."""
        try:
            return self._projects[projectid]
        except KeyError:
            try:
                return self.get_and_cache('project/projectid',
                                      projectid,
                                      self._projects)
            except tornado.web.HTTPError:
                return self.get_and_cache('project/name',
                                      projectid,
                                      self._projects)

    def get_not_done_projects(self):
        "Get projects that are not done."
        all = [r['value'] for r in
               self.db.view('project/not_done')]
        return all

    def get_not_done_samples(self, projectid=None):
        "Get samples that are not done."
        if projectid:
            all = [r['value'] for r in
                   self.db.view('sample/not_done') if r['key'][0] == projectid]
        else:
            all = [r['value'] for r in
                   self.db.view('sample/not_done')]

        return all

    def get_done_samples(self, projectid=None):
        "Get samples that are not done."
        if projectid:
            all = [r['value'] for r in
                   self.db.view('sample/done') if r['key'][0] == projectid]
        else:
            all = [r['value']for r in
                   self.db.view('sample/done')]

        return all

    def get_running_samples(self, projectid=None):
        "Get samples that are running."
        if projectid:
            all = [r['value'] for r in
                   self.db.view('sample/running') if r['key'][0] == projectid]
        else:
            all = [r['value'] for r in
                   self.db.view('sample/running')]

        return all

    def get_failed_samples(self, projectid=None):
        "Get samples that are failed."
        if projectid:
            all = [r['value'] for r in
                   self.db.view('sample/failed') if r['key'][0] == projectid]
        else:
            all = [r['value'] for r in
                   self.db.view('sample/failed')]

        return all

    def get_analyzed_failed_samples(self, projectid=None):
        "Get samples that are failed or done."
        if projectid:
            all = [r['value'] for r in
                   self.db.view('sample/analyzed_failed') if r['key'][0] == projectid]
        else:
            all = [r['value'] for r in
                   self.db.view('sample/analyzed_failed')]

        return all
    def get_projectids_from_sampleid(self, sampleid):
        pj_ids=[]
        rows=self.db.view('internal/sampleids_to_projectids', key=sampleid)
        for row in rows:
            pj_ids.append(row['value'])
            return pj_ids

    def get_projects(self, from_key=None, to_key=None, limit=20):
        "Get all projects."
        if from_key:
            view = self.db.view('project/modified', start_key=from_key, descending=True, limit=limit + 1)
        elif to_key:
            view = self.db.view('project/modified', start_key=to_key, limit=limit + 1)
        else:
            view = self.db.view('project/modified', limit=limit + 1, descending=True)

        projects = [self.get_project(r['value']) for r in view]
        has_more = len(projects) > limit

        # Sort the projects by the key desc if going backwards
        if to_key:
            projects.sort(key=lambda project: project.get('modified'), reverse=True)

        from_key = projects[0]['modified'] if projects else None
        to_key = projects[-1]['modified'] if has_more else None
        if has_more:
            projects = projects[:limit]
        

        view1 = 'sample/count'
        view2 = 'sample/count_done'
        view3 = 'libprep/count'
        view4 = 'sample/count_delivered'
        for project in projects:
            try:
                row = self.db.view(view1, key=project['projectid'])[0]
            except IndexError:
                project['sample_count'] = 0
            else:
                project['sample_count'] = row['value']
            try:
                row = self.db.view(view2, key=project['projectid'])[0]
            except IndexError:
                project['sample_count_done'] = 0
            else:
                project['sample_count_done'] = row['value']
            try:
                row = self.db.view(view4, key=project['projectid'])[0]
            except IndexError:
                project['sample_count_delivered'] = 0
            else:
                project['sample_count_delivered'] = row['value']
            startkey = [project['projectid']]
            endkey = [project['projectid'], constants.HIGH_CHAR]
            try:
                row = self.db.view(view3, start_key=startkey, end_key=endkey, group_level=1)[0]
            except IndexError:
                project['libprep_count'] = 0
            else:
                project['libprep_count'] = row['value']
        return projects, has_more, from_key, to_key

    def get_sample(self, projectid, sampleid):
        """Get the sample by the projectid and sampleid.
        Raise HTTP 404 if no such sample."""
        key = (projectid, sampleid)
        try:
            return self._samples[key]
        except KeyError:
            return self.get_and_cache('sample/sampleid', key, self._samples)

    def get_samples(self, projectid=None):
        "Get all samples for the project."
        startkey = (projectid or '', '')
        endkey = (projectid or constants.HIGH_CHAR, constants.HIGH_CHAR)
        return [self.get_sample(*r['key']) for r in
                self.db.view('sample/sampleid', start_key=startkey, end_key=endkey)]

    def get_libprep(self, projectid, sampleid, libprepid):
        """Get the libprep by the projectid, sampleid and libprepid.
        Raise HTTP 404 if no such libprep."""
        key = (projectid, sampleid, libprepid)
        try:
            return self._libpreps[key]
        except KeyError:
            return self.get_and_cache('libprep/libprepid', key, self._libpreps)

    def get_libpreps(self, projectid, sampleid=''):
        """Get the libpreps for the sample if sampleid given.
        For the entire project if no sampleid."""
        startkey = (projectid, sampleid, '')
        endkey = (projectid,
                  sampleid or constants.HIGH_CHAR,
                  constants.HIGH_CHAR)
        return [self.get_libprep(*r['key']) for r in
                self.db.view('libprep/libprepid', start_key=startkey, end_key=endkey)]

    def get_seqrun(self, projectid, sampleid, libprepid, seqrunid):
        """Get the libprep by the projectid, sampleid, libprepid and seqrunid.
        Raise HTTP 404 if no such seqrun."""
        try:
            key = (projectid, sampleid, libprepid, seqrunid)
            return self._seqruns[key]
        except (ValueError, KeyError):
            return self.get_and_cache('seqrun/seqrunid', key, self._seqruns)

    def get_seqruns(self, projectid='', sampleid='', libprepid=''):
        """Get the seqruns for the libprep if libprepid given.
        For the entire sample if no libprepid.
        For the entire project if no sampleid."""
        startkey = (projectid  or '', sampleid or '', libprepid or '', '')
        endkey = (projectid or constants.HIGH_CHAR,
                  sampleid or constants.HIGH_CHAR,
                  libprepid or constants.HIGH_CHAR,
                  constants.HIGH_CHAR)
        return [self.get_seqrun(*r['key']) for r in
                self.db.view('seqrun/seqrunid', start_key=startkey, end_key=endkey)]

    def get_and_cache(self, viewname, key, cache):
        """Get the item by the view name and the key.
        Try to get it from the cache, else from the database.
        Raise HTTP 404 if no such item."""
        view_rows = self.db.view(viewname, include_docs=True, key=key)
        if len(view_rows) == 1:
            item = cache[key] = view_rows[0]['doc']
            self._cache[item['_id']] = item
            return item
        else:
            logging.debug("{0} elements for key {1} ".format(len(view_rows), key))
            raise tornado.web.HTTPError(404, reason='{0} elements for key {1}'.format(len(view_rows), key))

    def get_logs(self, id):
        "Return the log documents for the given doc id."
        view_result = self.db.view('log/doc', include_docs=True, key=id)
        return sorted([r['doc'] for r in view_result],
                      key=functools.cmp_to_key(utils.cmp_timestamp),
                      reverse=True)

    def send_error(self, status_code=500, **kwargs):
        """ ** This is really a bug fix for Tornado!
        *** A bug fix has been pull-requested to the master Tornado repo.

        Sends the given HTTP error code to the browser.

        If `flush()` has already been called, it is not possible to send
        an error, so this method will simply terminate the response.
        If output has been written but not yet flushed, it will be discarded
        and replaced with the error page.

        Override `write_error()` to customize the error page that is returned.
        Additional keyword arguments are passed through to `write_error`.
        """
        if self._headers_written:
            gen_log.error("Cannot send error response after headers written")
            if not self._finished:
                self.finish()
            return
        self.clear()

        # reason = None               # *** Incorrect line!
        reason = kwargs.get('reason') # *** This is the corrected line.
        if 'exc_info' in kwargs:
            exception = kwargs['exc_info'][1]
            if isinstance(exception, tornado.web.HTTPError) and exception.reason:
                reason = exception.reason
        self.set_status(status_code, reason=reason)
        try:
            self.write_error(status_code, **kwargs)
        except Exception:
            app_log.error("Uncaught exception in write_error", exc_info=True)
        if not self._finished:
            self.finish()
