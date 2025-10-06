" Charon: Upload file interface. "

import logging
import csv
import io

import tornado.web

from . import constants
from . import settings
from . import utils
from .requesthandler import RequestHandler
from .project import ProjectSaver
from .sample import SampleSaver


class Upload(RequestHandler):
    "Display upload page."

    @tornado.web.authenticated
    def get(self):
        self.render('upload.html',
                    message=self.get_argument('message', None),
                    error=self.get_argument('error', None))


class UploadRequestHandler(RequestHandler):
    "Base upload handler."

    def read_records(self, **columns):
        """Get the input CSV file data.
        Set up the column mapping.
        Read in the rows."""
        try:
            data = self.request.files['csvfile'][0]
        except (KeyError, IndexError):
            raise tornado.web.HTTPError(400, reason='no CSV file uploaded')
        self.errors = []
        self.messages = ["Data from file {}".format(data['filename'])]
        infile = io.StringIO(data['body'])
        logging.debug(data['body'])
        dialect = csv.Sniffer().sniff(infile.read(1024))
        infile.seek(0)
        reader = csv.reader(infile, dialect)
        header_line = self.get_header_line(reader)
        if header_line is None:
            self.messages.append('No header line')
            self.columns = columns
            self.offset = 1
        else:
            self.messages.append('Header line present')
            self.columns = dict()
            for key in columns:
                key = key.lower()
                for pos, name in enumerate(header_line):
                    if key == name.lower():
                        self.columns[key] = pos
                        break
                else:
                    self.columns[key] = columns[key]
            self.offset = 2
        self.rows = list(reader)
        self.messages.append("{} data records in file".format(len(self.rows)))

    def get_header_line(self, reader):
        "Return the header line, if there is supposed to be one."
        if utils.to_bool(self.get_argument('header_line',False)):
            return next(reader)
        else:
            return None

    def get_new_project(self, pos, row):
        "Check and return the identifier for a new project. None if error."
        try:
            projectid = row[self.columns['project']].strip()
            if not projectid: raise IndexError
            if not constants.ID_RX.match(projectid): raise ValueError
            if projectid.lower() == 'project': raise ValueError
            self.get_project(projectid)
        except IndexError:
            self.errors.append("row {}: no project identifier".format(
                    pos+self.offset))
        except ValueError:
            self.errors.append("row {}: invalid project identifier '{}'".
                          format(pos+self.offset, projectid))
        except tornado.web.HTTPError: # Correct! No such project exists.
            return projectid
        else:
            self.errors.append("row {}: project identifier '{}' already exists".
                          format(pos+self.offset, projectid))

    def get_new_sample(self, pos, row, projectid):
        "Check and return the identifier for a new sample. None if error."
        try:
            sampleid = row[self.columns['sample']].strip()
            if not sampleid: raise IndexError
            if not constants.ID_RX.match(sampleid): raise ValueError
            if sampleid.lower() == 'sample': raise ValueError
        except IndexError:
            self.errors.append("row {}: no sample identifier".format(
                    pos+self.offset))
        except ValueError:
            self.errors.append("row {}: invalid sample identifier '{}'".
                               format(pos+self.offset, sampleid))
        else:
            try:
                self.get_sample(projectid, sampleid)
            except tornado.web.HTTPError:
                if sampleid in self.projects[projectid]:
                    self.errors.append(
                        "row {}: sample identifier twice in file'{}'".
                        format(pos+self.offset, sampleid))
                else:
                    self.projects[projectid].add(sampleid)
                    return sampleid
            else:
                self.errors.append("row {}: sample identifier exists '{}'".
                                   format(pos+self.offset, sampleid))

    def back_to_upload(self):
        "Redirecto to upload page, with messages and errors."
        self.redirect(self.get_absolute_url('upload',
                                            message='\n'.join(self.messages),
                                            error='\n'.join(self.errors)))


class UploadSamplesheetUppsala(UploadRequestHandler):
    "Upload an Illumina samplesheet as defined in Uppsala."

    @tornado.web.authenticated
    def post(self):
        "Check and optionally add data from samplesheet CSV file."
        logging.debug("UploadProjects post")
        # No need to pass column definitions; always header line in samplesheet.
        self.read_records()
        self.projects = dict()
        for pos, row in enumerate(self.rows):
            projectid = self.get_new_project(pos, row)
            if not projectid: continue
            self.projects.setdefault(projectid, set())
            self.get_new_sample(pos, row, projectid)

    def get_header_line(self, reader):
        "There is always a header line in a samplesheet file."
        return next(reader)

    def get_new_project(self, pos, row):
        "Check and return the identifier for a new project. None if error."
        try:
            projectid = row[self.columns['sampleproject']].strip()
            if not projectid: raise IndexError
            if not constants.ID_RX.match(projectid): raise ValueError
            if projectid.lower() == 'project': raise ValueError
            self.get_project(projectid)
        except IndexError:
            self.errors.append("row {}: no project identifier".format(
                    pos+self.offset))
        except ValueError:
            self.errors.append("row {}: invalid project identifier '{}'".
                          format(pos+self.offset, projectid))
        except tornado.web.HTTPError: # Correct! No such project exists.
            return projectid
        else:
            self.errors.append("row {}: project identifier '{}' already exists".
                          format(pos+self.offset, projectid))


class UploadProjects(UploadRequestHandler):
    "Upload a CSV file with new project(s) and their samples."

    @tornado.web.authenticated
    def post(self):
        "Check and optionally add data from CSV file."
        logging.debug("UploadProjects post")
        self.read_records(project=0, sample=1)
        self.projects = dict()
        for pos, row in enumerate(self.rows):
            projectid = self.get_new_project(pos, row)
            if not projectid: continue
            self.projects.setdefault(projectid, set())
            self.get_new_sample(pos, row, projectid)
        if not self.errors:
            if utils.to_bool(self.get_argument('add', False)):
                new_projects = dict()
                try:
                    for pos, row in enumerate(self.rows):
                        projectid = row[self.columns['project']].strip()
                        try:
                            project = new_projects[projectid]
                        except KeyError:
                            with ProjectSaver(rqh=self) as saver:
                                data = dict(projectid=projectid,
                                            # XXX Hard-coded! Bad, very bad!
                                            sequencing_facility='NGI-U')
                                saver.store(data=data)
                                project = saver.doc
                            new_projects[projectid] = project
                        sampleid = row[self.columns['sample']].strip()
                        with SampleSaver(rqh=self, project=project) as saver:
                            data = dict(sampleid=sampleid)
                            saver.store(data=data)
                            sample = saver.doc
                    self.messages.append('Added projects and samples')
                except Exception as msg: # Rollback
                    self.errors.append("Unexpected error: {}".format(msg))
                    for project in list(new_projects.values()):
                        utils.delete_project(self.db, project)
            else:
                for projectid in sorted(self.projects):
                    samples = ', '.join(sorted(self.projects[projectid]))
                    self.messages.append("new project {}, samples: {}".
                                         format(projectid, samples))
                self.messages.append("NOTE: no projects or samples added!")
        self.back_to_upload()


class UploadSamples(UploadRequestHandler):
    "Upload a CSV file with new samples into existing project(s)."

    @tornado.web.authenticated
    def post(self):
        "Check and optionally add data from CSV file."
        self.read_records(project=0, sample=1)
        # Check that projects exist
        self.projects = dict()
        existing_projects = dict()
        for pos, row in enumerate(self.rows):
            projectid = row[self.columns['project']].strip()
            try:
                project = self.get_project(projectid)
                existing_projects[projectid] = project
                self.projects.setdefault(projectid, set())
            except tornado.web.HTTPError:
                self.errors.append("row {}: no such project '{}'".format(
                    pos+self.offset, projectid))
                continue
            self.get_new_sample(pos, row, projectid)
        if not self.errors:
            if utils.to_bool(self.get_argument('add', False)):
                new_samples = []
                try:
                    for pos, row in enumerate(self.rows):
                        projectid = row[self.columns['project']].strip()
                        project = existing_projects[projectid]
                        sampleid = row[self.columns['sample']].strip()
                        with SampleSaver(rqh=self, project=project) as saver:
                            data = dict(sampleid=sampleid)
                            saver.store(data=data)
                            sample = saver.doc
                        new_samples.append(sample)
                    self.messages.append('Added samples')
                except Exception as msg: # Rollback
                    self.errors.append("Unexpected error: {}".format(msg))
                    for sample in new_samples:
                        utils.delete_sample(self.db, sample)
            else:
                for projectid in sorted(self.projects):
                    samples = ', '.join(sorted(self.projects[projectid]))
                    self.messages.append("project {}, new samples: {}".
                                         format(projectid, samples))
                self.messages.append("NOTE: no samples added!")
        self.back_to_upload()
