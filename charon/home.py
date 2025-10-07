" Charon: Home and other top pages in the interface. "

import logging
import json
import functools

import tornado.web

from . import constants
from . import settings
from . import utils
from .requesthandler import RequestHandler
from .api import ApiRequestHandler

import time

def sampleStats(handler, projectid=None):
    data={}
    if projectid:
        total=projectid+"_TOTAL"
        aborted=projectid+"_ABORTED"
        passed=projectid+"_ANALYZED"
        passed_unab=projectid+"_ANALYZED_UNAB"
        failed=projectid+"_FAILED"
        running=projectid+"_UNDER_ANALYSIS"
        coverage=projectid+"_TOTAL_COV"
    else:
        total="TOTAL"
        aborted="ABORTED"
        passed="ANALYZED"
        passed_unab="ANALYZED_UNAB"
        failed="FAILED"
        running="UNDER_ANALYSIS"
        coverage="TOTAL_COV"

    db = handler.db
    view = 'sample/summary_count'
    pview = 'project/projectid'
    seqview = 'sample/sequenced'
    try:
        data['tot'] = db.view(view, key=total)[0]['value']
    except (KeyError, IndexError):
        data['tot']=0
    try:
        data['ab'] = db.view(view, key=aborted)[0]['value']
    except (KeyError, IndexError):
        data['ab']=0
    try:
        data['passed'] = db.view(view, key=passed)[0]['value']
    except (KeyError, IndexError):
        data['passed']=0
    try:
        data['passed_unab'] = db.view(view, key=passed_unab)[0]['value']
    except (KeyError, IndexError):
        data['passed_unab']=0
    try:
        data['failed'] = db.view(view, key=failed)[0]['value']
    except (KeyError, IndexError):
        data['failed']=0
    data['ana'] = data['passed'] + data['failed']
    try:
        data['runn'] = db.view(view, key=running)[0]['value']
    except (KeyError, IndexError):
        data['runn']=0
    try:
        seq=0
        if projectid:
            for row in db.view(seqview, group=True, start_key=[projectid, ''], end_key=[projectid, constants.HIGH_CHAR]):
                seq+=1
        else:
            for row in db.view(seqview, group=True):
                seq+=1
        data['seq'] = seq
    except (KeyError, IndexError):
        data['seq']=0
    try:
        data['cov'] = db.view(view, key=coverage)[0]['value']
    except (KeyError, IndexError):
        data['cov']=0
    data['hge'] = int(data['cov'] / 30)
    try:
        data['gdp'] = db.get(db.view(pview, key=projectid)[0]['id'])['delivery_projects']
    except (KeyError, IndexError, TypeError):
        data['gdp'] = []

    return data

class SummaryAPI(ApiRequestHandler):
    """Summarizes data for the whole DB, or one project"""
    def get(self):
        """returns stats from the DB as JSON data  """
        project_id=self.get_argument("projectid", default=None)
        self.write(json.dumps(sampleStats(self, project_id)))


class Summary(RequestHandler):

    @tornado.web.authenticated
    def get(self):
        project_id=self.get_argument("projectid", default=None)
        data=sampleStats(self, project_id)
        self.render('summary.html', data=data)



class Home(RequestHandler):
    "Home page: Form to login or link to create new account. Links to pages."

    def get(self):
        try:
            samples_count = self.db.view('sample/count')[0]['value']
        except IndexError:
            samples_count = 0
        try:
            libpreps_count = self.db.view('libprep/count')[0]['value']
        except IndexError:
            libpreps_count = 0
        view = self.db.view('project/modified', limit=10,
                            descending=True,
                            include_docs=True)
        projects = [r['doc'] for r in view]
        view = self.db.view('sample/modified', limit=10,
                            descending=True,
                            include_docs=True)
        samples = [r['doc'] for r in view]
        view = self.db.view('libprep/modified', limit=10,
                            descending=True,
                            include_docs=True)
        libpreps = [r['doc'] for r in view]
        self.render('home.html',
                    projects_count=len(list(self.db.view('project/name'))),
                    samples_count=samples_count,
                    libpreps_count=libpreps_count,
                    projects=projects,
                    samples=samples,
                    libpreps=libpreps,
                    next=self.get_argument('next', ''))


class Search(RequestHandler):
    "Search page."

    @tornado.web.authenticated
    def get(self):
        term = self.get_argument('term', '')
        items = dict()
        if term:
            view_result = self.db.view('project/projectid', start_key=term, end_key=term+constants.HIGH_CHAR)
            for row in view_result:
                doc = self.get_project(row['key'])
                items[doc['_id']] = doc
            view_result = self.db.view('project/name', start_key=term, end_key=term+constants.HIGH_CHAR)
            for row in view_result:
                doc = self.get_project(row['value'])
                items[doc['_id']] = doc
            view_result = self.db.view('project/splitname', start_key=term, end_key=term+constants.HIGH_CHAR)
            for row in view_result:
                doc = self.get_project(row['value'])
                items[doc['_id']] = doc
            view_result = self.db.view('user/email', start_key=term, end_key=term+constants.HIGH_CHAR)
            for row in view_result:
                doc = self.get_user(row['key'])
                items[doc['_id']] = doc
            view_result = self.db.view('user/name', start_key=term, end_key=term+constants.HIGH_CHAR)
            for row in view_result:
                doc = self.get_user(row['value'])
                items[doc['_id']] = doc
        items = sorted(list(items.values()),
                       key=functools.cmp_to_key(lambda i,j: utils.cmp(i['modified'], j['modified'])),
                       reverse=True)
        self.render('search.html',
                    term=term,
                    items=items)


class ApiHome(ApiRequestHandler):
    """API root: Links to API entry points.
    Every call to an API resource must include an API access
    token in the header.
    The key of the header record is 'X-Charon-API-token',
    and the value is a random hexadecimal string."""

    def get(self):
        """Return links to API entry points.
        Success: HTTP 200."""
        data = dict(links=dict(
                self=dict(href=self.get_absolute_url('api_home'),
                          title='API root'),
                version=dict(href=self.get_absolute_url('api_version'),
                             title='software versions'),
                projects=dict(href=self.get_absolute_url('api_projects'),
                              title='all projects'),
                ))
        self.write(data)


class Version(RequestHandler):
    "Page displaying the software component versions."

    def get(self):
        "Return version information for all software in the system."
        self.render('version.html', versions=utils.get_versions())


class ApiVersion(ApiRequestHandler):
    "Access to software component versions"

    def get(self):
        "Return software component versions."
        self.write(dict(utils.get_versions()))


class ApiDocumentation(RequestHandler):
    "Documentation of the API generated by introspection."

    def get(self):
        "Display only URLs beginning with '/api/'."
        hosts = []
        for handler in self.application.handlers:
            urlspecs = []
            hosts.append(dict(name=handler[0].pattern.rstrip('$'),
                              urlspecs=urlspecs))
            for urlspec in handler[1]:
                if not urlspec.regex.pattern.startswith('/api/'): continue
                saver = urlspec.handler_class.saver
                if saver is not None:
                    fields = saver.fields
                else:
                    fields = []
                methods = []
                for name in ('get', 'post', 'put', 'delete'):
                    method = getattr(urlspec.handler_class, name)
                    if method.__doc__ is None: continue
                    methods.append((name, self.process_text(method.__doc__)))
                urlspecs.append(dict(pattern=urlspec.regex.pattern.rstrip('$'),
                                     text=self.process_text(urlspec.handler_class.__doc__),
                                     fields=fields,
                                     methods=methods))
        self.render('apidoc.html', hosts=hosts)

    def process_text(self, text):
        if not text: return '-'
        lines = text.split('\n')
        if len(lines) >= 2:
            prefix = len(lines[1]) - len(lines[1].strip())
            for pos, line in enumerate(lines[1:]):
                try:
                    lines[pos+1] = line[prefix:]
                except IndexError:
                    pass
        return '\n'.join(lines)
