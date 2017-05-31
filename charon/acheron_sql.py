
import argparse
import copy
import json
import logging
import multiprocessing as mp
import Queue
import requests
import time
import re

from datetime import datetime
from genologics_sql.tables import *
from genologics_sql.utils import *
from genologics_sql.queries import *
from sqlalchemy import text
from charon.utils import QueueHandler

REFERENCE_GENOME_PATTERN = re.compile("\,\s+([0-9A-z\._-]+)\)")


def main(args):
    main_log = setup_logging("acheron_logger", args)
    docs = []
    db_session = get_session()
    if args.proj:
        main_log.info("Updating {0}".format(args.proj))
        project = obtain_project(args.proj, db_session)
        cdt = CharonDocumentTracker(db_session, project, main_log, args)
        cdt.run()
    elif args.new:
        project_list = obtain_recent_projects(db_session)
        main_log.info("Project list : {0}".format(", ".join([x.luid for x in project_list])))
        masterProcess(args, project_list, main_log)
    elif args.all:
        project_list = obtain_all_projects(db_session)
        main_log.info("Project list : {0}".format(", ".join([x.luid for x in project_list])))
        masterProcess(args, project_list, main_log)
    elif args.test:
        print "\n".join(x.__str__() for x in obtain_recent_projects(db_session))


def setup_logging(name, args):
    mainlog = logging.getLogger(name)
    mainlog.setLevel(level=logging.INFO)
    mfh = logging.handlers.RotatingFileHandler(args.logfile, maxBytes=209715200, backupCount=5)
    mft = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    mfh.setFormatter(mft)
    mainlog.addHandler(mfh)
    return mainlog


def obtain_all_projects(session):
    query = "select pj.* from project pj \
            where pj.createddate > date '2016-01-01';"
    return session.query(Project).from_statement(text(query)).all()


def obtain_recent_projects(session):
    recent_projectids = get_last_modified_projectids(session)
    if recent_projectids:
        query = "select pj.* from project pj \
            where pj.luid in ({0});".format(",".join(["'{0}'".format(x) for x in recent_projectids]))
        return session.query(Project).from_statement(text(query)).all()
    else:
        return []


def obtain_project(project_id, session):
    query = "select pj.* from project pj \
            where pj.luid LIKE '{pid}'::text OR pj.name LIKE '{pid}';".format(pid=project_id)
    return session.query(Project).from_statement(text(query)).one()


def merge(d1, d2):
    """ Will merge dictionary d2 into dictionary d1.
    On the case of finding the same key, the one in d1 will be used.
    :param d1: Dictionary object
    :param s2: Dictionary object
    """
    d3 = copy.deepcopy(d1)
    for key in d2:
        if key in d3:
            if isinstance(d3[key], dict) and isinstance(d2[key], dict):
                d3[key] = merge(d3[key], d2[key])
            elif d3[key] != d2[key]:
                # special weird cases
                if key == 'status' and d3.get('charon_doctype') == 'sample':
                    d3[key] = d2[key]
            elif d3[key] == d2[key]:
                pass  # same value, nothing to do
        else:
            d3[key] = d2[key]
    return d3


def masterProcess(args, projectList, logger):
    projectsQueue = mp.JoinableQueue()
    logQueue = mp.Queue()
    childs = []
    # spawn a pool of processes, and pass them queue instance
    for i in range(args.processes):
        p = mp.Process(target=processCharon, args=(args, projectsQueue, logQueue))
        p.start()
        childs.append(p)
    # populate queue with data
    for proj in projectList:
        projectsQueue.put(proj.luid)

    # wait on the queue until everything has been processed
    notDone = True
    while notDone:
        try:
            log = logQueue.get(False)
            logger.handle(log)
        except Queue.Empty:
            if not stillRunning(childs):
                notDone = False
                break


def stillRunning(processList):
    ret = False
    for p in processList:
        if p.is_alive():
            ret = True

    return ret


def processCharon(args, queue, logqueue):
    db_session = get_session()
    work = True
    procName = mp.current_process().name
    proclog = logging.getLogger(procName)
    proclog.setLevel(level=logging.INFO)
    mfh = QueueHandler(logqueue)
    mft = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    mfh.setFormatter(mft)
    proclog.addHandler(mfh)
    try:
        time.sleep(int(procname[8:]))
    except:
        time.sleep(1)

    while work:
        # grabs project from queue
        try:
            proj_id = queue.get(block=True, timeout=3)
        except Queue.Empty:
            work = False
            break
        except NotImplementedError:
            # qsize failed, no big deal
            pass
        else:
            # locks the project : cannot be updated more than once.
            proclog.info("Handling {}".format(proj_id))
            project = obtain_project(proj_id, db_session)
            cdt = CharonDocumentTracker(db_session, project, proclog, args)
            cdt.run()

            # signals to queue job is done
            queue.task_done()


class CharonDocumentTracker:

    def __init__(self, session, project, logger, args):
        self.charon_url = args.url
        self.charon_token = args.token
        self.session = session
        self.project = project
        self.logger = logger
        self.docs = []

    def run(self):

        def _compare_doctype(doc):
            order=["project", "sample", "libprep", "seqrun"]
            return order.index(doc['charon_doctype'])

        # order matters because samples depend on seqruns.
        self.generate_project_doc()
        self.generate_libprep_seqrun_docs()
        self.generate_samples_docs()
        self.docs=sorted(self.docs, key=_compare_doctype)
        self.update_charon()


    def generate_project_doc(self):
        curtime = datetime.now().isoformat()
        doc = {}
        doc['charon_doctype'] = 'project'
        doc['created'] = curtime
        doc['modified'] = curtime
        doc['sequencing_facility'] = 'NGI-S'
        doc['pipeline'] = 'NGI'
        doc['projectid'] = self.project.luid
        doc['status'] = 'OPEN'
        doc['name'] = self.project.name
        doc['delivery_token'] = 'not_under_delivery'

        for udf in self.project.udfs:
            if udf.udfname == 'Bioinformatic QC':
                if udf.udfvalue == 'WG re-seq':
                    doc['best_practice_analysis'] = 'whole_genome_reseq'
                else:
                    doc['best_practice_analysis'] = udf.udfvalue
            if udf.udfname == 'Uppnex ID' and udf.udfvalue:
                doc['uppnex_id'] = udf.udfvalue.strip()
            if udf.udfname == 'Reference genome' and udf.udfvalue:
                matches = REFERENCE_GENOME_PATTERN.search(udf.udfvalue)
                if matches:
                    doc['reference'] = matches.group(1)
                else:
                    doc['reference'] = 'other'

        self.docs.append(doc)

    def generate_samples_docs(self):
        curtime = datetime.now().isoformat()
        for sample in self.project.samples:
            doc = {}
            doc['charon_doctype'] = 'sample'
            doc['projectid'] = self.project.luid
            doc['sampleid'] = sample.name
            doc['created'] = curtime
            doc['modified'] = curtime
            doc['duplication_pc'] = 0
            doc['genotype_concordance'] = 0
            doc['total_autosomal_coverage'] = 0
            doc['status'] = 'FRESH'
            doc['analysis_status'] = 'TO_ANALYZE'

            remote_sample=self.get_charon_sample(sample.name)
            if remote_sample and remote_sample.get('status') == 'STALE' and self.seqruns_for_sample(sample.name) == self.remote_seqruns_for_sample(sample.name):
                doc['status'] = 'STALE'

            for udf in sample.udfs:
                if udf.udfname == 'Status (manual)':
                    if udf.udfvalue == 'Aborted':
                        doc['status'] = 'ABORTED'
                if udf.udfname == 'Sample Links':
                    doc['Pair'] = udf.udfvalue
                if udf.udfname == 'Sample Link Type':
                    doc['Type'] = udf.udfvalue

            self.docs.append(doc)

    def generate_libprep_seqrun_docs(self):
        curtime = datetime.now().isoformat()
        for sample in self.project.samples:
            query = "select pc.* from process pc \
            inner join processiotracker piot on piot.processid=pc.processid \
            inner join artifact_sample_map asm on asm.artifactid=piot.inputartifactid \
            where asm.processid={pcid} and pc.typeid in (8,806);".format(pcid=sample.processid)
            libs = self.session.query(Process).from_statement(text(query)).all()
            alphaindex = 65
            for lib in libs:
                doc = {}
                doc['charon_doctype'] = 'libprep'
                doc['created'] = curtime
                doc['modified'] = curtime
                doc['projectid'] = self.project.luid
                doc['sampleid'] = sample.name
                doc['libprepid'] = chr(alphaindex)
                doc['qc'] = "PASSED"
                self.docs.append(doc)
                query = "select distinct pro.* from process pro \
                inner join processiotracker pio on pio.processid=pro.processid \
                inner join artifact_sample_map asm on pio.inputartifactid=asm.artifactid \
                inner join artifact_ancestor_map aam on pio.inputartifactid=aam.artifactid\
                inner join processiotracker pio2 on pio2.inputartifactid=aam.ancestorartifactid\
                inner join process pro2 on pro2.processid=pio2.processid \
                where pro2.processid={parent} and pro.typeid in (38,46,714) and asm.processid={sid};".format(parent=lib.processid, sid=sample.processid)
                seqs = self.session.query(Process).from_statement(text(query)).all()
                for seq in seqs:
                    seqdoc = {}
                    seqdoc['charon_doctype'] = 'seqrun'
                    seqdoc['created'] = curtime
                    seqdoc['modified'] = curtime
                    seqdoc['mean_autosomal_coverage'] = 0
                    seqdoc['total_reads'] = 0
                    seqdoc['alignment_status'] = 'NOT_RUNNING'
                    seqdoc['delivery_status'] = 'NOT DELIVERED'
                    seqdoc['projectid'] = self.project.luid
                    seqdoc['sampleid'] = sample.name
                    seqdoc['libprepid'] = chr(alphaindex)
                    for udf in seq.udfs:
                        if udf.udfname == "Run ID":
                            seqdoc['seqrunid'] = udf.udfvalue
                            break
                    if 'seqrunid' in seqdoc:
                        self.docs.append(seqdoc)

                alphaindex += 1


    def seqruns_for_sample(self, sampleid):
        seqruns = set()
        for doc in self.docs:
            if doc['charon_doctype'] == 'seqrun' and doc['sampleid'] == sampleid:
                seqruns.add(doc['seqrunid'])

        return seqruns

    def remote_seqruns_for_sample(self, sampleid):
        seqruns = set()
        session = requests.Session()
        headers = {'X-Charon-API-token': self.charon_token, 'content-type': 'application/json'}
        url = "{0}/api/v1/seqruns/{1}/{2}".format(self.charon_url, self.project.luid, sampleid)
        r = session.get(url, headers=headers)
        if r.status_code == requests.codes.ok:
            for sr in r.json()['seqruns']:
                seqruns.add(sr['seqrunid'])

        return seqruns

    def get_charon_sample(self, sampleid):
        session = requests.Session()
        headers = {'X-Charon-API-token': self.charon_token, 'content-type': 'application/json'}
        url = "{0}/api/v1/sample/{1}/{2}".format(self.charon_url, self.project.luid, sampleid)
        r = session.get(url, headers=headers)
        if r.status_code == requests.codes.ok:
            return r.json()
        else:
            return None

    def update_charon(self):
        session = requests.Session()
        headers = {'X-Charon-API-token': self.charon_token, 'content-type': 'application/json'}
        for doc in self.docs:
            try:
                if doc['charon_doctype'] == 'project':
                    self.logger.info("trying to update doc {0}".format(doc['projectid']))
                    url = "{0}/api/v1/project/{1}".format(self.charon_url, doc['projectid'])
                    r = session.get(url, headers=headers)
                    if r.status_code == 404:
                        url = "{0}/api/v1/project".format(self.charon_url)
                        rq = session.post(url, headers=headers, data=json.dumps(doc))
                        if rq.status_code == requests.codes.created:
                            self.logger.info("project {0} successfully updated".format(doc['projectid']))
                        else:
                            self.logger.error("project {0} failed to be updated : {1}".format(doc['projectid'], rq.text))
                    else:
                        pj = r.json()
                        merged = merge(doc, pj)
                        if merged != pj:
                            rq = session.put(url, headers=headers, data=json.dumps(merged))
                            if rq.status_code == requests.codes.no_content:
                                self.logger.info("project {0} successfully updated".format(doc['projectid']))
                            else:
                                self.logger.error("project {0} failed to be updated : {1}".format(doc['projectid'], rq.text))
                elif doc['charon_doctype'] == 'sample':
                    url = "{0}/api/v1/sample/{1}/{2}".format(self.charon_url, doc['projectid'], doc['sampleid'])
                    r = session.get(url, headers=headers)
                    if r.status_code == 404:
                        url = "{0}/api/v1/sample/{1}".format(self.charon_url, doc['projectid'])
                        rq = session.post(url, headers=headers, data=json.dumps(doc))
                        if rq.status_code == requests.codes.created:
                            self.logger.info("sample {0}/{1} successfully updated".format(doc['projectid'], doc['sampleid']))
                        else:
                            self.logger.error("sample {0}/{1} failed to be updated : {2}".format(doc['projectid'], doc['sampleid'], rq.text))
                    else:
                        pj = r.json()
                        merged = merge(pj, doc)
                        if merged != pj:
                            rq = session.put(url, headers=headers, data=json.dumps(merged))
                            if rq.status_code == requests.codes.no_content:
                                self.logger.info("sample {0}/{1} successfully updated".format(doc['projectid'], doc['sampleid']))
                            else:
                                self.logger.error("sample {0}/{1} failed to be updated : {2}".format(doc['projectid'], doc['sampleid'], rq.text))
                elif doc['charon_doctype'] == 'libprep':
                    url = "{0}/api/v1/libprep/{1}/{2}/{3}".format(self.charon_url, doc['projectid'], doc['sampleid'], doc['libprepid'])
                    r = session.get(url, headers=headers)
                    if r.status_code == 404:
                        url = "{0}/api/v1/libprep/{1}/{2}".format(self.charon_url, doc['projectid'], doc['sampleid'])
                        rq = session.post(url, headers=headers, data=json.dumps(doc))
                        if rq.status_code == requests.codes.created:
                            self.logger.info("libprep {0}/{1}/{2} successfully updated".format(doc['projectid'], doc['sampleid'], doc['libprepid']))
                        else:
                            self.logger.error("libprep {0}/{1}/{2} failed to be updated : {3}".format(doc['projectid'], doc['sampleid'], doc['libprepid'], rq.text))
                    else:
                        pj = r.json()
                        merged = merge(pj, doc)
                        if merged != pj:
                            rq = session.put(url, headers=headers, data=json.dumps(merged))
                            if rq.status_code == requests.codes.no_content:
                                self.logger.info("libprep {0}/{1}/{2} successfully updated".format(doc['projectid'], doc['sampleid'], doc['libprepid']))
                            else:
                                self.logger.error("libprep {0}/{1}/{2} failed to be updated : {3}".format(doc['projectid'], doc['sampleid'], doc['libprepid'], rq.text))
                elif doc['charon_doctype'] == 'seqrun':
                    url = "{0}/api/v1/seqrun/{1}/{2}/{3}/{4}".format(self.charon_url, doc['projectid'], doc['sampleid'], doc['libprepid'], doc['seqrunid'])
                    r = session.get(url, headers=headers)
                    if r.status_code == 404:
                        url = "{0}/api/v1/seqrun/{1}/{2}/{3}".format(self.charon_url, doc['projectid'], doc['sampleid'], doc['libprepid'])
                        rq = session.post(url, headers=headers, data=json.dumps(doc))
                        if rq.status_code == requests.codes.created:
                            self.logger.info("seqrun {0}/{1}/{2}/{3} successfully updated".format(doc['projectid'], doc['sampleid'], doc['libprepid'], doc['seqrunid']))
                        else:
                            self.logger.error("seqrun {0}/{1}/{2}/{3} failed to be updated : {4}".format(doc['projectid'], doc['sampleid'], doc['libprepid'], doc['seqrunid'], rq.text))
                    else:
                        pj = r.json()
                        merged = merge(pj, doc)
                        if merged != pj:
                            rq = session.put(url, headers=headers, data=json.dumps(merged))
                            if rq.status_code == requests.codes.no_content:
                                self.logger.info("seqrun {0}/{1}/{2}/{3} successfully updated".format(doc['projectid'], doc['sampleid'], doc['libprepid'], doc['seqrunid']))
                            else:
                                self.logger.error("seqrun {0}/{1}/{2}/{3} failed to be updated : {4}".format(doc['projectid'], doc['sampleid'], doc['libprepid'], doc['seqrunid'], rq.text))
            except Exception as e:
                self.logger.error("Error handling document \n{} \n\n{}".format(doc, e))

if __name__ == "__main__":
    usage = "Usage:       python acheron_sql.py [options]"
    parser = argparse.ArgumentParser(usage=usage)
    parser.add_argument("-k", "--processes", dest="processes", default=12, type=int,
                        help="Number of child processes to start")
    parser.add_argument("-a", "--all", dest="all", default=False, action="store_true",
                        help="Try to upload all IGN projects. This will wipe the current information stored in Charon")
    parser.add_argument("-n", "--new", dest="new", default=False, action="store_true",
                        help="Try to upload new IGN projects. This will NOT erase the current information stored in Charon")
    parser.add_argument("-p", "--project", dest="proj", default=None,
                        help="-p <projectname> will try to upload the given project to charon")
    parser.add_argument("-t", "--token", dest="token", default=os.environ.get('CHARON_API_TOKEN'),
                        help="Charon API Token. Will be read from the env variable CHARON_API_TOKEN if not provided")
    parser.add_argument("-u", "--url", dest="url", default=os.environ.get('CHARON_BASE_URL'),
                        help="Charon base url. Will be read from the env variable CHARON_BASE_URL if not provided")
    parser.add_argument("-v", "--verbose", dest="verbose", default=False, action="store_true",
                        help="prints results for everything that is going on")
    parser.add_argument("-l", "--log", dest="logfile", default=os.path.expanduser("~/acheron.log"),
                        help="location of the log file")
    parser.add_argument("-z", "--test", dest="test", default=False, action="store_true",
                        help="Testing option")
    args = parser.parse_args()

    if not args.token:
        print("No valid token found in arg or in environment. Exiting.")
    if not args.url:
        print("No valid url found in arg or in environment. Exiting.")
        sys.exit(-1)
    main(args)
