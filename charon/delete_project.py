"""Development script for deleting explicitly a project and all its stuff.
WARNING: Destructive! Must not be used in the production instance."""

from charon import utils

if __name__ == '__main__':
    import sys
    if len(sys.argv) != 2:
        sys.exit('give project identifier')
    utils.load_settings()
    db = utils.get_db()
    view = db.view('project/projectid', include_docs=True, key=sys.argv[1])
    rows = list(view)
    if len(rows) != 1:
        sys.exit('no such project')
    project = rows[0]['doc']
    print('Project', project['projectid'], project.get('title', '[no title]'))
    answer = input('really delete? (y/n) > ')
    if utils.to_bool(answer):
        utils.delete_project(db, project)
        print('deleted')
