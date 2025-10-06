" Charon: Context handler for saving an entity. "

import logging

import ibm_cloud_sdk_core

from . import constants
from . import utils


class Field(object):
    "Specification of a data field for an entity."

    type ='text'

    def __init__(self, key, title=None, description=None,
                 mandatory=False, editable=True, default=None):
        assert key
        self.key = key
        self.title = title or key.capitalize().replace('_', ' ')
        self.description = description or self.__doc__
        self.mandatory = mandatory             # A non-None value is requried.
        self.editable = editable               # Changeable once set?
        self.default=default
        self.none_value='None'

    def store(self, saver, data=None, check_only=False):
        """Check, convert and store the field value.
        If 'data' is None, then obtain the value from HTML form parameter.
        If 'check_only' is True, then just do validity checking, no update.
        """
        if not saver.is_new() and not self.editable: return
        logging.debug("Field.store(%s)", data)
        value = self.get(saver, data=data)
        try:
            value = self.process(saver, value)
        except ValueError as msg:
            raise ValueError("field '{0}': {1}".format(self.key, msg))
        if check_only: return
        if self.default is not None and value is None:
            value = self.default
        if value == saver.doc.get(self.key):
            logging.debug("Field.store: '%s' value equal", self.key)
            return
        saver.doc[self.key] = value
        saver.changed[self.key] = value

    def get(self, saver, data=None):
        "Obtain the value from data, if given, else from HTML form parameter."
        if data is None:
            value = saver.rqh.get_argument(self.key, default=None)
            if value == self.none_value:
                return None
            else:
                return value
        else:
            try:
                return data[self.key]
            except KeyError:
                return saver.get(self.key)

    def process(self, saver, value):
        """Check validity and return converted to the appropriate type.
        Raise ValueError if there is a problem."""
        self.check_mandatory(saver, value)
        self.check_valid(saver, value)
        return value or None

    def check_mandatory(self, saver, value):
        "Check that a value is provided when required."
        if self.mandatory and value is None:
            raise ValueError('a defined value is mandatory')

    def check_valid(self, saver, value):
        "Check that the value, if provided, is valid."
        pass

    def html_display(self, entity):
        "Return the field value as valid HTML."
        return str(entity.get(self.key) or '-')

    def html_create(self):
        "Return an appropriate HTML input field for a create form."
        return '<input type="text" name="{0}">'.format(self.key)

    def html_edit(self, entity):
        "Return an appropriate HTML input field for an edit form."
        if self.editable:
            return '<input type="text" name="{0}" value="{1}">'.\
                format(self.key, entity.get(self.key) or '')
        else:
            return entity.get(self.key) or '-'


class ListField(Field):
    type = "list"

    def __init__(self, key, title=None, description=None, default=[]):
        super(ListField, self).__init__(key, title=title,
                                      description=description,
                                      mandatory=False, editable=True,
                                      default=default)
        self.none_value = []

    def process(self, saver, value):
        self.check_mandatory(saver, value)
        old_value = saver.doc.get(self.key)
        if old_value is None:
            old_value=[]
        if value not in [None, '']:
            if isinstance(value, list):
                old_value = value
            elif value.startswith('[') and value.endswith(']'):
                old_value=[]
                #assume it's a serialized list
                values=value[1:-1].split(",")
                for val in values:
                    if val.strip().startswith("u'") and val.endswith("'"):
                        old_value.append(val[2:-1])
                    else:
                        old_value.append(val)
            else:
                old_value = [value]
        return old_value



class IdField(Field):
    "The identifier for the entity."

    type ='identifier'

    def __init__(self, key, title=None, description=None):
        super(IdField, self).__init__(key, title=title,
                                      description=description,
                                      mandatory=True, editable=False)

    def check_valid(self, saver, value):
        "Only allow a subset of ordinary ASCII characters."
        logging.debug('IdField.check_valid')
        if not constants.ALLOWED_ID_CHARS.match(value):
            raise ValueError('invalid identifier value (disallowed characters)')


class SelectField(Field):
    "Select one of a set of values."

    none_value = 'None'

    def __init__(self, key, title=None, description=None,
                 mandatory=False, editable=True, options=[]):
        super(SelectField, self).__init__(key, title=title,
                                          description=description,
                                          mandatory=mandatory,
                                          editable=editable)
        self.options = options

    def get(self, saver, data=None):
        "Obtain the value from data, if given, else from HTML form parameter."
        if data is None :
            value = saver.rqh.get_argument(self.key, default=None)
            if value == self.none_value:
                return None
            else:
                return value
        else:
            try:
                return data[self.key]
            except KeyError:
                return saver.get(self.key)


    def check_valid(self, saver, value):
        "Check that the value, if provided, is valid."
        if value is None or value == self.none_value: return
        if value not in self.options:
            logging.debug("invalid select value: %s", value)
            raise ValueError("invalid value '{0}; not among options for select".
                             format(value))

    def html_create(self):
        "Return the field HTML input field for a create form."
        options = ["<option>{0}</option>".format(o) for o in self.options]
        if not self.mandatory:
            options.insert(0, "<option>{0}</option>".format(self.none_value))
        return '<select name="{0}">{1}</select>'.format(self.key, options)

    def html_edit(self, entity):
        "Return the field HTML input field for an edit form."
        value = entity.get(self.key)
        if self.editable:
            options = []
            if not self.mandatory:
                if value is None:
                    options.append("<option selected>{0}</option>".format(
                            self.none_value))
                else:
                    options.append("<option>{0}</option>".format(
                            self.none_value))
            for option in self.options:
                if value == option:
                    options.append("<option selected>{0}</option>".format(option))
                else:
                    options.append("<option>{0}</option>".format(option))
            return '<select name="{0}">{1}</select>'.format(self.key, options)
        else:
            return value or '-'


class NameField(Field):
    "The name for the entity, unique if non-null."

    def __init__(self, key, title=None, description=None):
        super(NameField, self).__init__(key, title=title,
                                        description=description,
                                        mandatory=False)


class FloatField(Field):
    "A floating point value field."

    type ='float'

    def __init__(self, key, title=None, description=None,
                 mandatory=False, editable=True, default=None):
        super(FloatField, self).__init__(key,
                                           title=title,
                                           description=description,
                                           mandatory=mandatory,
                                           editable=editable, default=default)

    def process(self, saver, value):
        self.check_mandatory(saver, value)
        if value is None: return None
        if value == '': return None
        return float(value)

    def html_display(self, entity):
        "Return the field value as valid HTML."
        value = entity.get(self.key)
        if value is None:
            value = '-'
        else:
            value = str(value)
        return '<span class="number">{0}</span>'.format(value)

    def html_edit(self, entity):
        "Return the field HTML input field for an edit form."
        value = entity.get(self.key)
        if value is None:
            if self.editable:
                return '<input type="text" name="{0}">'.format(self.key)
            else:
                return '-'
        else:
            if self.editable:
                return '<input type="text" name="{0}" value="{1}">'.\
                    format(self.key, value)
            else:
                return str(value)


class RangeFloatField(FloatField):
    "A floating point value field, with an allowed range."

    def __init__(self, key, minimum=None, maximum=None,
                 title=None, description=None,
                 mandatory=False, editable=True):
        super(RangeFloatField, self).__init__(key,
                                              title=title,
                                              description=description,
                                              mandatory=mandatory,
                                              editable=editable)
        self.minimum = minimum
        self.maximum = maximum

    def process(self, saver, value):
        value = super(RangeFloatField, self).process(saver, value)
        if value is None: return None
        if self.minimum is not None:
            if value < self.minimum: raise ValueError('value too low')
        if self.maximum is not None:
            if value > self.maximum: raise ValueError('value too high')
        return value


class Saver(object):
    "Context handler defining the fields of the entity and saving the data."

    doctype = None
    fields = []
    field_keys = []

    def __init__(self, doc=None, rqh=None, db=None):
        self.fields_lookup = dict([(f.key, f) for f in self.fields])
        assert self.doctype
        if rqh is not None:
            self.rqh = rqh
            self.db = rqh.db
            self.current_user = rqh.current_user
        elif db is not None:
            self.db = db
            self.current_user = dict()
        else:
            raise AttributeError('neither db nor rqh given')
        self.doc = doc or dict()
        self.changed = dict()
        if '_id' in self.doc:
            assert self.doctype == self.doc[constants.DB_DOCTYPE]
        else:
            self.doc['_id'] = utils.get_iuid()
            self.doc[constants.DB_DOCTYPE] = self.doctype
            self.initialize()

    def __enter__(self):
        return self

    def __exit__(self, type, value, tb):
        if type is not None: return False # No exceptions handled here
        self.finalize()
        try:
            self.db.save(self.doc)
        except ibm_cloud_sdk_core.ApiException as err:
            raise IOError('document revision update conflict')
        if self.changed:
            utils.log(self.db, self.doc,
                      changed=self.changed,
                      current_user=self.current_user)

    def __setitem__(self, key, value):
        "Update the key/value pair."
        try:
            field = self.fields_lookup[key]
        except KeyError:
            try:
                checker = getattr(self, "check_{0}".format(key))
            except AttributeError:
                pass
            else:
                checker(value)
            try:
                converter = getattr(self, "convert_{0}".format(key))
            except AttributeError:
                pass
            else:
                value = converter(value)
            try:
                if self.doc[key] == value: return
            except KeyError:
                pass
            self.doc[key] = value
            self.changed[key] = value
        else:
            field.store(self, value)

    def __getitem__(self, key):
        return self.doc[key]

    def initialize(self):
        "Perform actions when creating the entity."
        self.doc['created'] = utils.timestamp()

    def is_new(self):
        "Is the entity new, i.e. not previously saved in the database?"
        return '_rev' not in self.doc

    def store(self, data=None, check_only=False):
        """Given the fields, store the data items.
        If data is None, then obtain the value from HTML form parameter.
        If 'check_only' is True, then just do validity checking, no update.
        """
        for field in self.fields:
            field.store(self, data=data, check_only=check_only)

    def finalize(self):
        "Perform any final modifications before saving the entity."
        self.doc['modified'] = utils.timestamp()

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default
