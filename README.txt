Charon
======

Database for IGN projects and samples, with RESTful interface. Built on
top of Tornado and CouchDB.

API
---

The RESTful API is documented at http://charon.scilifelab.se/apidoc .

Note that each call to the API must include an API token which is the
only mechanism used for authentication in the API. The API token is
specific for the user account, and is available in the user page for the
account.

A number of code examples for using the API can be found in the nosetest
``test_*.py`` files.

The nosetest examples require that the environment variables
CHARON\_API\_TOKEN and CHARON\_BASE\_URL are set.

Design notes
~~~~~~~~~~~~

The API is designed such that all data sent to and received from the
interface is JSON containing pure application data. Metadata, such as
the API access token, is passed as a HTTP header item, so as not to
clutter up the data namespace. This also allows for sending other types
of data as body content, such as images, which cannot contain API access
tokens.

**Tip**: Use the
`requests <http://docs.python-requests.org/en/latest/>`_ package for all
HTTP client code. It is way better than the urllib2 package in the
standard Python distribution.

Development server
------------------

The development server is at http://charon-dev.scilifelab.se/ . It is
currently reachable only from within SciLifeLab Stockholm.

Installation
~~~~~~~~~~~~

The development server is installed as an ordinary Python package in
``/usr/lib/python2.6/site-packages/charon`` . The controlling
configuration file ``tools-dev.yaml`` (which is not part of the GitHub
stuff) is located there. I have set the owner of that directory to
``per.kraulis`` to make it simpler for me...

The development server is upgraded thus:

::

    $ pip install --upgrade --no-deps git+https://github.com/NationalGenomicsInfrastructure/charon

The Tornado service is controlled by the upstart script
``/etc/init/charon.conf``.

The Apache server handles the redirect from the domain name to the
Tornado server which runs on port 8881. See
``/etc/httpd/conf/httpd.conf``.

The log file written by the Tornado server currently goes to the install
directory.

Production server
-----------------

The production server is available at http://charon.scilifelab.se/ and
is reachable from outside SciLifeLab to approved accounts, which are set
up using Userman at http://userman.scilifelab.se/ .

The production server is upgraded in a similar way as the development
server.

Service setup
~~~~~~~~~~~~~

The source code used in production is located in:

::

    /usr/lib/python2.6/site-packages/charon

The configuration file tools.yaml is located in:

::

    /var/local/charon

The log file charon.log is located in:

::

    /var/log/charon

The production server is upgraded thus:

::

    $ pip install --upgrade --no-deps git+https://github.com/pekrau/charon

The production server is currently started manually by Per Kraulis under
the account genomics.www using the following command:

::

    $ cd /usr/lib/python2.6/site-packages/charon
    $ sudo -b -u genomics.www python2.6 app_charon.py /var/local/charon/tools.yaml

*Yes, this is awful!* But the /etc/init.d stuff has not been written
yet...
