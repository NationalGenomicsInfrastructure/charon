" Charon: Libprep entity interface. "

import logging
import json

import tornado.web

from . import constants
from . import settings
from . import utils
from .requesthandler import RequestHandler
from .api import ApiRequestHandler
from .saver import *


class LibprepidField(IdField):
    "The unique identifier for the libprep within the sample."

    def check_valid(self, saver, value):
        "Also check uniqueness."
        super(LibprepidField, self).check_valid(saver, value)
        key = (saver.project['projectid'], saver.sample['sampleid'], value)
        view_result = saver.db.view('libprep/libprepid', key=key)
        if len(list(view_result)) > 0:
            raise ValueError('not unique')


class LibprepSaver(Saver):
    "Saver and fields definitions for the libprep entity."

    doctype = constants.LIBPREP

    fields = [LibprepidField('libprepid', title='Identifier'),
            SelectField('qc', description='The status of the libprep\'s analysis.',
                          options=constants.BASE_STATUS),
              ]

    def __init__(self, doc=None, rqh=None, db=None, sample=None):
        super(LibprepSaver, self).__init__(doc=doc, rqh=rqh, db=db)
        if self.is_new():
            assert sample
            assert 'sampleid' not in self.doc
            self.project = rqh.get_project(sample['projectid'])
            self.sample = sample
            self.doc['projectid'] = sample['projectid']
            self.doc['sampleid'] = sample['sampleid']
        else:
            self.project = rqh.get_project(self.doc['projectid'])
            if sample:
                assert (self.doc['sampleid'] == sample['sampleid']) and \
                    (self.doc['projectid'] == sample['projectid'])
                self.sample = sample
            else:
                self.sample = rqh.get_sample(self.doc['projectid'],
                                             self.doc['sampleid'])

class Libprep(RequestHandler):
    "Display the libprep data."

    saver = LibprepSaver

    @tornado.web.authenticated
    def get(self, projectid, sampleid, libprepid):
        libprep = self.get_libprep(projectid, sampleid, libprepid)
        seqruns = self.get_seqruns(projectid, sampleid, libprepid)
        logs = self.get_logs(libprep['_id']) # XXX limit?
        self.render('libprep.html',
                    libprep=libprep,
                    seqruns=seqruns,
                    fields=self.saver.fields,
                    logs=logs)


class LibprepCreate(RequestHandler):
    "Create a libprep."

    saver = LibprepSaver

    @tornado.web.authenticated
    def get(self, projectid, sampleid):
        sample = self.get_sample(projectid, sampleid)
        self.render('libprep_create.html',
                    sample=sample,
                    fields=self.saver.fields)

    @tornado.web.authenticated
    def post(self, projectid, sampleid):
        self.check_xsrf_cookie()
        sample = self.get_sample(projectid, sampleid)
        try:
            with self.saver(rqh=self, sample=sample) as saver:
                saver.store()
                libprep = saver.doc
        except (IOError, ValueError) as msg:
            self.render('libprep_create.html',
                        project=self.get_project(projectid),
                        sample=sample,
                        fields=self.saver.fields,
                        error=str(msg))
        else:
            url = self.reverse_url('libprep',
                                   projectid,
                                   sampleid,
                                   libprep['libprepid'])
            self.redirect(url)


class LibprepEdit(RequestHandler):
    "Edit an existing libprep."

    saver = LibprepSaver

    @tornado.web.authenticated
    def get(self, projectid, sampleid, libprepid):
        libprep = self.get_libprep(projectid, sampleid, libprepid)
        self.render('libprep_edit.html',
                    libprep=libprep,
                    fields=self.saver.fields)

    @tornado.web.authenticated
    def post(self, projectid, sampleid, libprepid):
        self.check_xsrf_cookie()
        libprep = self.get_libprep(projectid, sampleid, libprepid)
        try:
            with self.saver(doc=libprep, rqh=self) as saver:
                saver.store()
        except (IOError, ValueError) as msg:
            self.render('libprep_edit.html',
                        libprep=libprep,
                        fields=self.saver.fields,
                        error=str(msg))
        else:
            url = self.reverse_url('libprep', projectid, sampleid, libprepid)
            self.redirect(url)


class ApiLibprep(ApiRequestHandler):
    "Access a libprep."

    saver = LibprepSaver

    def get(self, projectid, sampleid, libprepid):
        """Return the libprep data as JSON.
        Return HTTP 404 if no such libprep, sample or project."""
        libprep = self.get_libprep(projectid, sampleid, libprepid)
        if not libprep: return
        self.add_libprep_links(libprep)
        self.write(libprep)

    def put(self, projectid, sampleid, libprepid):
        """Update the libprep with the given JSON data.
        Return HTTP 204 "No Content".
        Return HTTP 400 if the input data is invalid.
        Return HTTP 409 if there is a document revision conflict."""
        try:
            libprep = self.get_libprep(projectid, sampleid, libprepid)
            data = json.loads(self.request.body)
        except Exception as msg:
            self.send_error(400, reason=str(msg))
        else:
            try:
                with self.saver(doc=libprep, rqh=self) as saver:
                    saver.store(data=data)
            except ValueError as msg:
                self.send_error(400, reason=str(msg))
            except IOError as msg:
                self.send_error(409, reason=str(msg))
            else:
                self.set_status(204)
    def delete(self, projectid, sampleid, libprepid):
        """NOTE: This is for unit test purposes only!
        Delete the libprepand all of its dependent entities.
        Returns HTTP 204 "No Content"."""
        libprep= self.get_libprep(projectid, sampleid, libprepid)
        if not libprep: return
        utils.delete_libprep(self.db, libprep)
        logging.debug("deleted libprep {0}, {1}, {2}",
                      projectid, sampleid, libprepid)
        self.set_status(204)


class ApiLibprepCreate(ApiRequestHandler):
    "Create a libprep within a sample."

    saver = LibprepSaver

    def post(self, projectid, sampleid):
        """Create a libprep within a sample.
        Return HTTP 201, libprep URL in header "Location", and libprep data.
        Return HTTP 400 if something is wrong with the input data.
        Return HTTP 404 if no such project or sample.
        Return HTTP 409 if there is a document revision conflict."""
        project = self.get_project(projectid)
        if not project: return
        sample = self.get_sample(projectid, sampleid)
        if not sample: return
        try:
            data = json.loads(self.request.body)
        except Exception as msg:
            self.send_error(400, reason=str(msg))
        else:
            try:
                with self.saver(rqh=self, sample=sample) as saver:
                    saver.store(data=data)
                    libprep = saver.doc
            except (KeyError, ValueError) as msg:
                self.send_error(400, reason=str(msg))
            except IOError as msg:
                self.send_error(409, reason=str(msg))
            else:
                url = self.reverse_url('api_libprep',
                                       projectid,
                                       sampleid,
                                       libprep['libprepid'])
                self.set_header('Location', url)
                self.set_status(201)
                self.add_libprep_links(libprep)
                self.write(libprep)


class ApiProjectLibpreps(ApiRequestHandler):
    "Access to all libpreps for a project."

    def get(self, projectid):
        "Return a list of all libpreps for the given project."
        libpreps = self.get_libpreps(projectid)
        for libprep in libpreps:
            self.add_libprep_links(libprep)
        self.write(dict(libpreps=libpreps))


class ApiSampleLibpreps(ApiRequestHandler):
    "Access to all libpreps for a sample."

    def get(self, projectid, sampleid):
        "Return a list of all libpreps for the given sample and project."
        libpreps = self.get_libpreps(projectid, sampleid)
        for libprep in libpreps:
            self.add_libprep_links(libprep)
        self.write(dict(libpreps=libpreps))
