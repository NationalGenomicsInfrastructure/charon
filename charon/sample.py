" Charon: Sample entity interface. "

import logging
import json

import tornado.web

import charon.constants as cst
import charon.utils as utls
import charon.saver as sav
from charon.requesthandler import RequestHandler
from charon.api import ApiRequestHandler


class SampleidField(sav.IdField):
    "The unique identifier for the sample within the project."

    def check_valid(self, saver, value):
        "Also check uniqueness."
        super(SampleidField, self).check_valid(saver, value)
        key = (saver.project['projectid'], value)
        view = saver.db.view('sample/sampleid', key=key)
        if len(list(view)) > 0:
            raise ValueError('not unique')


class SampleSaver(sav.Saver):
    "Saver and fields definitions for the sample entity."

    doctype = cst.SAMPLE

    fields = [SampleidField('sampleid', title='Identifier'),
              sav.SelectField('analysis_status',
                          description='The status of the sample\'s analysis .',
                          options=list(cst.SAMPLE_ANALYSIS_STATUS.values())),
              sav.SelectField('delivery_status', title='Delivery status',
                    description='The delivery status of the sample.', options=list(cst.DELIVERY_STATUS.values())),
              sav.Field('delivery_token', title='Delivery token',
                    description='The delivery token from mover.', default="NO-TOKEN"),
              sav.ListField('delivery_projects', title='Delivery projects',
                    description='The delivery projects that this sample was delivered to.', default=[]),
              sav.SelectField('status', title='status',
                    description='The internal status of the sample.', options=list(cst.SEQUENCING_STATUS.values())),
              sav.SelectField('qc', title='QC',
                    description='The quality control status of the sample\'s analysis.', options=list(cst.SEQRUN_ANALYSIS_STATUS.values())),
              sav.SelectField('genotype_status',
                    description='The genotyping status of the sample.', options=list(cst.GENO_STATUS.values())),
              sav.FloatField('genotype_concordance',
                    description='The value of the genotyping concordance of the sample.', default=0.0),
              sav.FloatField('total_autosomal_coverage',
                    description='Coverage calculated in the last analysis steps.',
                    default=0.0),
              sav.FloatField('target_coverage',
                    description='Target coverage for the current sample.',
                    default=30.0),
              sav.FloatField('total_sequenced_reads',
                    description='Total of all for each seqrun in each libprep.'),
              sav.FloatField('requested_reads',
                    description='Number of Million of reads requested by the user.'),
              sav.FloatField('duplication_pc',
                    description='Picard\'s duplication rate percentage taken from the .metrics file.',
                    default=0.0),
              sav.SelectField('type', description='Identifies cancer samples.', options=cst.SAMPLE_TYPES),
              sav.Field('pair', description='Identifies related samples.')
              ]

    def __init__(self, doc=None, rqh=None, db=None, project=None):
        super(SampleSaver, self).__init__(doc=doc, rqh=rqh, db=db)
        if self.is_new():
            assert project
            assert 'projectid' not in self.doc
            self.doc['projectid'] = project['projectid']
            self.project = project
        else:
            if project:
                assert self.doc['projectid'] == project['projectid']
                self.project = project
            else:
                self.project = rqh.get_project(self.doc['projectid'])


class Sample(RequestHandler):
    "Display the sample data."

    saver = SampleSaver

    @tornado.web.authenticated
    def get(self, projectid, sampleid):
        sample = self.get_sample(projectid, sampleid)
        libpreps = self.get_libpreps(projectid, sampleid)
        for libprep in libpreps:
            try:
                startkey = [projectid, sampleid, libprep['libprepid']]
                endkey = [projectid, sampleid, libprep['libprepid'],
                          cst.HIGH_CHAR]
                row = self.db.view('seqrun/count', start_key=startkey,
                                   end_key=endkey)[0]
            except IndexError:
                libprep['seqruns_count'] = 0
            else:
                libprep['seqruns_count'] = row['value']
        logs = self.get_logs(sample['_id']) # XXX limit?
        self.render('sample.html',
                    sample=sample,
                    libpreps=libpreps,
                    fields=self.saver.fields,
                    logs=logs)


class SampleCreate(RequestHandler):
    "Create a sample."

    saver = SampleSaver

    @tornado.web.authenticated
    def get(self, projectid):
        self.render('sample_create.html',
                    project=self.get_project(projectid),
                    fields=self.saver.fields)

    @tornado.web.authenticated
    def post(self, projectid):
        self.check_xsrf_cookie()
        project = self.get_project(projectid)
        try:
            with self.saver(rqh=self, project=project) as saver:
                saver.store()
                sample = saver.doc
        except (IOError, ValueError) as msg:
            self.render('sample_create.html',
                        project=project,
                        fields=self.saver.fields,
                        error=str(msg))
        else:
            url = self.reverse_url('sample', projectid, sample['sampleid'])
            self.redirect(url)


class SampleEdit(RequestHandler):
    "Edit an existing sample."

    saver = SampleSaver

    @tornado.web.authenticated
    def get(self, projectid, sampleid):
        sample = self.get_sample(projectid, sampleid)
        self.render('sample_edit.html',
                    sample=sample,
                    fields=self.saver.fields)

    @tornado.web.authenticated
    def post(self, projectid, sampleid):
        self.check_xsrf_cookie()
        sample = self.get_sample(projectid, sampleid)
        try:
            with self.saver(doc=sample, rqh=self) as saver:
                saver.store()
        except (IOError, ValueError) as msg:
            self.render('sample_edit.html',
                        sample=sample,
                        fields=self.saver.fields,
                        error=str(msg))
        else:
            url = self.reverse_url('sample', projectid, sampleid)
            self.redirect(url)


class ApiSample(ApiRequestHandler):
    "Access a sample."

    saver = SampleSaver

    # Do not use authenticaton decorator; do not send to login page, but fail.
    def get(self, projectid, sampleid):
        """Return the sample data as JSON.
        Return HTTP 404 if no such sample or project."""
        sample = self.get_sample(projectid, sampleid)
        if not sample: return
        self.add_sample_links(sample)
        self.write(sample)

    # Do not use authenticaton decorator; do not send to login page, but fail.
    def put(self, projectid, sampleid):
        """Update the sample with the given JSON data.
        Return HTTP 204 "No Content".
        Return HTTP 400 if the input data is invalid.
        Return HTTP 409 if there is a document revision conflict."""
        sample = self.get_sample(projectid, sampleid)
        try:
            data = json.loads(self.request.body)
        except Exception as msg:
            self.send_error(400, reason=str(msg))
        else:
            try:
                with self.saver(doc=sample, rqh=self) as saver:
                    saver.store(data=data)
            except ValueError as msg:
                self.send_error(400, reason=str(msg))
            except IOError as msg:
                self.send_error(409, reason=str(msg))
            else:
                self.set_status(204)

    # Do not use authenticaton decorator; do not send to login page, but fail.
    def delete(self, projectid, sampleid):
        """NOTE: This is for unit test purposes only!
        Delete the sample and all of its dependent entities.
        Returns HTTP 204 "No Content"."""
        sample= self.get_sample(projectid, sampleid)
        if not sample: return
        utls.delete_sample(self.db, sample)
        logging.debug("deleted sample {0}, {1}".format(projectid, sampleid))
        self.set_status(204)


class ApiSampleCreate(ApiRequestHandler):
    "Create a sample within a project."

    saver = SampleSaver

    # Do not use authenticaton decorator; do not send to login page, but fail.
    def post(self, projectid):
        """Create a sample within a project.
        Return HTTP 201, sample URL in header "Location", and sample data.
        Return HTTP 400 if something is wrong with the input data.
        Return HTTP 404 if no such project.
        Return HTTP 409 if there is a document revision conflict."""
        project = self.get_project(projectid)
        if not project: return
        try:
            data = json.loads(self.request.body)
        except Exception as msg:
            self.send_error(400, reason=str(msg))
        else:
            try:
                with self.saver(rqh=self, project=project) as saver:
                    saver.store(data=data)
                    sample = saver.doc
            except (KeyError, ValueError) as msg:
                self.send_error(400, reason=str(msg))
            except IOError as msg:
                self.send_error(409, reason=str(msg))
            else:
                url = self.reverse_url('api_sample',
                                       projectid,
                                       sample['sampleid'])
                self.set_header('Location', url)
                self.set_status(201)
                self.add_sample_links(sample)
                self.write(sample)


class ApiSamples(ApiRequestHandler):
    "Access to all samples in a project."

    # Do not use authenticaton decorator; do not send to login page, but fail.
    def get(self, projectid):
        "Return a list of all samples."
        samples = self.get_samples(projectid)
        for sample in samples:
            self.add_sample_links(sample)
        self.write(dict(samples=samples))


class ApiSamplesNotDone(ApiRequestHandler):
    "Access to all samples that are not done."

    # Do not use authenticaton decorator; do not send to login page, but fail.
    def get(self):
        "Return a list of all undone samples."
        samples= self.get_not_done_samples()
        for sample in samples:
            self.add_sample_links(sample)
        self.write(dict(samples=samples))

class ApiSamplesDone(ApiRequestHandler):
    "Access to all samples that are not done."

    # Do not use authenticaton decorator; do not send to login page, but fail.
    def get(self):
        "Return a list of all done samples."
        samples= self.get_done_samples()
        for sample in samples:
            self.add_sample_links(sample)
        self.write(dict(samples=samples))
class SamplesDone(RequestHandler):
    "displays a list of currently Analyzed samples"
    def get(self):
        samples=self.get_done_samples(self.get_argument("projectid", None))
        self.render('samples_subset.html',
                    samples=samples,
                    identifier="Samples Analyzed successfully")

class ApiSamplesNotDonePerProject(ApiRequestHandler):
    "Access to all samples that are not done."

    # Do not use authenticaton decorator; do not send to login page, but fail.
    def get(self, projectid):
        "Return a list of all undone samples."
        samples= self.get_not_done_samples(projectid)
        for sample in samples:
            self.add_sample_links(sample)
        self.write(dict(samples=samples))

class ApiSamplesRunning(ApiRequestHandler):
    "retuns a list of samples that are currently running"
    def get(self):
        self.write(json.dumps(self.get_running_samples(self.get_argument("projectid", None))))

class SamplesRunning(RequestHandler):
    "displays a list of currently running samples"
    def get(self):
        samples=self.get_running_samples(self.get_argument("projectid", None))
        self.render('samples_subset.html',
                    samples=samples,
                    identifier="Samples Running")

class ApiSamplesFailed(ApiRequestHandler):
    "retuns a list of samples that are currently failed"
    def get(self):
        self.write(json.dumps(self.get_failed_samples(self.get_argument("projectid", None))))

class SamplesFailed(RequestHandler):
    "displays a list of currently Failed samples"
    def get(self):
        samples=self.get_failed_samples(self.get_argument("projectid", None))
        self.render('samples_subset.html',
                    samples=samples,
                    identifier="Samples with Failed Analysis")

class ApiSamplesDoneFailed(ApiRequestHandler):
    "retuns a list of samples that are currently failed"
    def get(self):
        self.write(json.dumps(self.get_analyzed_failed_samples(self.get_argument("projectid", None))))

class SamplesDoneFailed(RequestHandler):
    "displays a list of Done and Failed samples"
    def get(self):
        samples=self.get_analyzed_failed_samples(self.get_argument("projectid", None))
        self.render('samples_subset.html',
                    samples=samples,
                    identifier="Samples with Failed or Done Analysis")

class ApiProjectsFromSampleIds(ApiRequestHandler):
    "returns a list of project ids for the given sampleid"
    def get(self, sampleid):
        project_ids=self.get_projectids_from_sampleid(sampleid)
        self.write(json.dumps(project_ids))




class ApiSamplesCustomQuery(ApiRequestHandler):
    """Access to all samples that match the given query. The query MUST be a dictionnary with
    the following keys : projectid, sampleField, operator, value, type.
    ex : {'projectid':'P567', 'sampleField':'total_sequenced_reads', 'operator':'>=' , 'value':10, 'type':'float'}"""

    # Do not use authenticaton decorator; do not send to login page, but fail.
    def post(self):
        "Return a list of all samples matching the query."
        try:
            data = json.loads(self.request.body)
            if 'projectid' not in data:
                raise KeyError('data given does not contain a projectid')
            if 'sampleField' not in data:
                raise KeyError('data given does not contain a sampleField')
            if 'operator' not in data:
                raise KeyError('data given does not contain an operator ')
            if 'type' not in data:
                raise KeyError('data given does not contain a type')
            if 'value' not in data:
                raise KeyError('data given does not contain a value')
            if  data['operator'] not in ['==', '>', '<', '<=', '>=', 'is']:
                raise ValueError('Unallowed operator : {0}'.format(data['operator']))
            allsamples= self.get_samples(data['projectid'])
            samples=[]
            query="sample.get('{0}') {1} {2}('{3}')".format(data['sampleField'], data['operator'], data['type'], data['value'])
        except Exception as msg:
            self.send_error(400, reason=str(msg))

        for sample in allsamples:
            try:
                if not sample.get(data['sampleField']):
                    #if the field is not in the db, just skip the doc
                    continue
                if type(sample.get(data['sampleField'])).__name__ != data['type']:
                    raise TypeError('Given type does not match database type {0}'.format(type(sample.get(data['sampleField'])).__name__))
                if eval(query, {"__builtins__":None}, {'sample':sample, 'int':int, 'str':str, 'float':float, 'unicode':str, 'text':str} ):
                    samples.append(sample)
            except Exception as msg:
                self.send_error(400, reason=str(msg))
        for sample in samples:
            self.add_sample_links(sample)
        self.write(dict(samples=samples))
