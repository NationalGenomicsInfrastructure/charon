" Charon: Web application root. "

import logging

import tornado
import tornado.web

from charon import constants
from charon import utils
from charon import uimodules
from charon.requesthandler import RequestHandler

from charon.home import *
from charon.user import *
from charon.project import *
from charon.sample import *
from charon.libprep import *
from charon.seqrun import *
from charon.api import *


class Dummy(RequestHandler):
    @tornado.web.authenticated
    def get(self, *args, **kwargs):
        logging.debug("dummy, %s, %s", args, kwargs)


URL = tornado.web.url

handlers = \
    [URL(r'/', Home, name='home'),
     URL(r'/project', ProjectCreate, name='project_create'),
     URL(r'/project/([^/]+)', Project, name='project'),
     URL(r'/project/([^/]+)/edit', ProjectEdit, name='project_edit'),
     URL(r'/project/([^/]+)/upload', ProjectUpload, name='project_upload'),
     URL(r'/project/([^/]+)/update', ProjectUpdate, name='project_update'),
     URL(r'/projects', Projects, name='projects'),
     URL(r'/sample/([^/]+)', SampleCreate, name='sample_create'),
     URL(r'/sample/([^/]+)/([^/]+)', Sample, name='sample'),
     URL(r'/sample/([^/]+)/([^/]+)/edit', SampleEdit, name='sample_edit'),
     URL(r'/samplesrunning', SamplesRunning, name='samples_running'),
     URL(r'/samplesdone', SamplesDone, name='samples_done'),
     URL(r'/samplesfailed', SamplesFailed, name='samples_failed'),
     URL(r'/samplesdonefailed', SamplesDoneFailed, name='samples_done_failed'),
     URL(r'/libprep/([^/]+)/([^/]+)', LibprepCreate, name='libprep_create'),
     URL(r'/libprep/([^/]+)/([^/]+)/([^/]+)', Libprep, name='libprep'),
     URL(r'/libprep/([^/]+)/([^/]+)/([^/]+)/edit',
         LibprepEdit, name='libprep_edit'),
     URL(r'/seqrun/([^/]+)/([^/]+)/([^/]+)',
         SeqrunCreate, name='seqrun_create'),
     URL(r'/seqrun/([^/]+)/([^/]+)/([^/]+)/([^/]+)',
         Seqrun, name='seqrun'),
     URL(r'/seqrun/([^/]+)/([^/]+)/([^/]+)/([^/]+)/edit',
         SeqrunEdit, name='seqrun_edit'),
     URL(r'/summary', Summary, name='summary'),
     URL(r'/search', Search, name='search'),
     URL(r'/user/([^/]+)', User, name='user'),
     URL(r'/user/([^/]+)/token', UserApiToken, name='user_token'),
     URL(constants.LOGIN_URL, Login, name='login'),
     URL(r'/users', Users, name='users'),
     URL(r'/logout', Logout, name='logout'),
     URL(r'/version', Version, name='version'),
     URL(r'/apidoc', ApiDocumentation, name='apidoc'),
     URL(r'/api/v1', ApiHome, name='api_home'),
     URL(r'/api/v1/summary', SummaryAPI, name='api_summary'),
     URL(r'/api/v1/project', ApiProjectCreate, name='api_project_create'),
     URL(r'/api/v1/project/(?P<projectid>[^/]+)',
         ApiProject, name='api_project'),
     URL(r'/api/v1/projects', ApiProjects, name='api_projects'),
     URL(r'/api/v1/projectidsfromsampleid/(?P<sampleid>[^/]+)', ApiProjectsFromSampleIds, name='api_projectidsfromsampleid'),
     URL(r'/api/v1/sample/(?P<projectid>[^/]+)',
         ApiSampleCreate, name='api_sample_create'),
     URL(r'/api/v1/sample/(?P<projectid>[^/]+)/(?P<sampleid>[^/]+)',
         ApiSample, name='api_sample'),
     URL(r'/api/v1/samples/(?P<projectid>[^/]+)',
         ApiSamples, name='api_samples'),
     URL(r'/api/v1/libprep/(?P<projectid>[^/]+)/(?P<sampleid>[^/]+)',
         ApiLibprepCreate, name='api_libprep_create'),
     URL(r'/api/v1/libprep/(?P<projectid>[^/]+)/(?P<sampleid>[^/]+)/(?P<libprepid>[^/]+)',
         ApiLibprep, name='api_libprep'),
     URL(r'/api/v1/libpreps/(?P<projectid>[^/]+)',
         ApiProjectLibpreps, name='api_project_libpreps'),
     URL(r'/api/v1/libpreps/(?P<projectid>[^/]+)/(?P<sampleid>[^/]+)',
         ApiSampleLibpreps, name='api_sample_libpreps'),
     URL(r'/api/v1/seqrun/(?P<projectid>[^/]+)/(?P<sampleid>[^/]+)/(?P<libprepid>[^/]+)',
         ApiSeqrunCreate, name='api_seqrun_create'),
     URL(r'/api/v1/seqrun/(?P<projectid>[^/]+)/(?P<sampleid>[^/]+)/(?P<libprepid>[^/]+)/(?P<seqrunid>[^/]+)',
         ApiSeqrun, name='api_seqrun'),
     URL(r'/api/v1/seqruns/(?P<projectid>[^/]+)',
         ApiProjectSeqruns, name='api_project_seqruns'),
     URL(r'/api/v1/seqruns/(?P<projectid>[^/]+)/(?P<sampleid>[^/]+)',
         ApiSampleSeqruns, name='api_sample_seqruns'),
     URL(r'/api/v1/seqruns/(?P<projectid>[^/]+)/(?P<sampleid>[^/]+)/(?P<libprepid>[^/]+)',
         ApiLibprepSeqruns, name='api_libprep_seqruns'),
     URL(r'/api/v1/version', ApiVersion, name='api_version'),
     URL(r'/api/v1/doc/([a-f0-9]{32})', ApiDocument, name='api_doc'),
     URL(r'/api/v1/logs/([a-f0-9]{32})', ApiLogs, name='api_logs'),
     URL(r'/api/v1/notify', ApiNotify, name='api_notify'),
     URL(r'/api/v1/projectsnotclosed', ApiProjectsNotDone, name='projects_not_done'),
     URL(r'/api/v1/samplesdone', ApiSamplesDone, name='api_samples_done'),
     URL(r'/api/v1/samplesfailed', ApiSamplesFailed, name='api_samples_failed'),
     URL(r'/api/v1/samplesdonefailed', ApiSamplesDoneFailed, name='api_samples_failed'),
     URL(r'/api/v1/samplesrunning', ApiSamplesRunning, name='api_samples_running'),
     URL(r'/api/v1/samplesnotdone', ApiSamplesNotDone, name='api_samples_not_done'),
     URL(r'/api/v1/samplesnotdone/(?P<projectid>[^/]+)', ApiSamplesNotDonePerProject, name='api_samples_not_done_per_project'),
     URL(r'/api/v1/seqrunsdone', ApiSeqrunsDone, name='api_seqruns_done'),
     URL(r'/api/v1/customquery', ApiSamplesCustomQuery, name='api_custom_query'),
     ]


if __name__ == "__main__":
    import sys
    import tornado.ioloop
    try:
        settings = utils.load_settings(filepath=sys.argv[1])
    except IndexError:
        settings = utils.load_settings()
    application = tornado.web.Application(
        handlers=handlers,
        debug=settings.get('TORNADO_DEBUG', False),
        cookie_secret=settings['COOKIE_SECRET'],
        ui_modules=uimodules,
        template_path=constants.TEMPLATE_PATH,
        static_path=constants.STATIC_PATH,
        static_url_prefix=constants.STATIC_URL,
        login_url=constants.LOGIN_URL)
    application.listen(settings['PORT'])
    logging.info("Charon web server on port %s", settings['PORT'])
    tornado.ioloop.IOLoop.instance().start()
