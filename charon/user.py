" Charon: User account handling."

import logging
import json
import urllib.parse

import tornado.web
import requests

from . import constants
from . import settings
from . import utils
from .requesthandler import RequestHandler
from .saver import Saver


class UserSaver(Saver):

    doctype = constants.USER


class Login(RequestHandler):
    "Login handler."

    def get(self):
        self.render('login.html',
                    error=None,
                    next=self.get_argument('next', None))

    def post(self):
        self.check_xsrf_cookie()
        try:
            self.authenticate_user(self.get_argument('email'),
                                   self.get_argument('password'))
            url = self.get_argument('next', None)
            if not url:
                url = self.reverse_url('home')
            self.redirect(url)
        except (tornado.web.MissingArgumentError, ValueError) as msg:
            logging.debug("login error: %s", msg)
            self.render('login.html',
                        error=str(msg),
                        next=self.get_argument('next', None))

    def authenticate_user(self, email, password):
        """Authenticate the given email and password.
        This is done by consulting the Userman web service.
        Save or update the user in this database.
        Raise ValueError if any error.
        """
        if not email:
            raise ValueError('no email given')
        if not password:
            raise ValueError('no password given')
        url = "{0}/{1}".format(settings['AUTH']['AUTH_HREF'],
                               urllib.parse.quote(email))
        data = json.dumps(dict(password=password, service='Charon'))
        headers = {'X-Userman-API-token': settings['AUTH']['API_TOKEN']}
        response = requests.post(url, data=data, headers=headers)
        if response.status_code != requests.codes.ok:
            raise ValueError(str(response.reason))
        try:
            user = self.get_user(email)
        except tornado.web.HTTPError:
            user = response.json()
        else:
            user.update(response.json())
        with UserSaver(doc=user, rqh=self) as saver:
            # All other changes already made.
            if not user.get('api_token'):
                saver['api_token'] = utils.get_iuid()
        self.set_secure_cookie(constants.USER_COOKIE_NAME, email,
                               expires_days=settings['LOGIN_EXPIRES_DAYS'])


class Logout(RequestHandler):
    "Logout handler."

    def post(self):
        self.check_xsrf_cookie()
        self.set_secure_cookie(constants.USER_COOKIE_NAME, '')
        self.redirect(self.reverse_url('login'))


class User(RequestHandler):
    "User account handler."

    @tornado.web.authenticated
    def get(self, email):
        user = self.get_user(email)
        current_user = self.get_current_user()
        privileged = current_user == user or current_user['role'] == 'admin'
        self.render('user.html',
                    user=user,
                    privileged=privileged,
                    logs=self.get_logs(user['_id']))


class UserApiToken(RequestHandler):
    "API token handler for user account."

    @tornado.web.authenticated
    def post(self, email):
        "Set the API token for the user."
        self.check_xsrf_cookie()
        user = self.get_user(email)
        current_user = self.get_current_user()
        privileged = current_user == user or current_user['role'] == 'admin'
        if not privileged:
            raise tornado.web.HTTPError(403)
        with UserSaver(doc=user, rqh=self) as saver:
            saver['api_token'] = utils.get_iuid()
        self.redirect(self.reverse_url('user', user['email']))


class Users(RequestHandler):
    "Display all users."

    @tornado.web.authenticated
    def get(self):
        view = self.db.view('user/email')
        users = [self.get_user(r['key']) for r in view]
        self.render('users.html', users=users)
