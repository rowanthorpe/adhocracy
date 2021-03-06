from copy import copy
import hashlib
import os
import logging
from datetime import datetime

from babel import Locale
from pylons.i18n import _

from sqlalchemy import Table, Column, func, or_
from sqlalchemy import Boolean, DateTime, Integer, Unicode, UnicodeText
from sqlalchemy.orm import eagerload_all

from adhocracy import config
from adhocracy.model import meta
from adhocracy.model import instance_filter as ifilter
from adhocracy.model.core import JSONEncodedDict
from adhocracy.model.core import MutationDict
from adhocracy.model.instance import Instance

log = logging.getLogger(__name__)


user_table = Table(
    'user', meta.data,
    Column('id', Integer, primary_key=True),
    Column('user_name', Unicode(255), nullable=False, unique=True, index=True),
    Column('display_name', Unicode(255), nullable=True, index=True),
    Column('bio', UnicodeText(), nullable=True),
    Column('email', Unicode(255), nullable=True, unique=True),
    Column('email_priority', Integer, default=3),
    Column('activation_code', Unicode(255), nullable=True, unique=False),
    Column('reset_code', Unicode(255), nullable=True, unique=False),
    Column('password', Unicode(80), nullable=True),
    Column('locale', Unicode(7), nullable=True),
    Column('create_time', DateTime, default=datetime.utcnow),
    Column('access_time', DateTime, default=datetime.utcnow,
           onupdate=datetime.utcnow),
    Column('delete_time', DateTime),
    Column('banned', Boolean, default=False),
    Column('no_help', Boolean, default=False, nullable=True),
    Column('page_size', Integer, default=10, nullable=True),
    Column('proposal_sort_order', Unicode(50), default=None, nullable=True),
    Column('gender', Unicode(1), default=None),
    Column('_is_organization', Boolean, default=False),
    Column('email_messages', Boolean, default=True),
    Column('welcome_code', Unicode(255), nullable=True),
    Column('optional_attributes', MutationDict.as_mutable(JSONEncodedDict)),
)


class User(meta.Indexable):

    IMPORT_MARKER = 'i__'

    def __init__(self, user_name, email, password, locale, display_name=None,
                 bio=None):
        self.user_name = user_name
        self.email = email
        self.password = password
        self.locale = locale
        self.display_name = display_name
        self.bio = bio
        self.banned = False

    @property
    def name(self):
        if self.delete_time:
            return self.user_name
        if self.display_name and len(self.display_name.strip()) > 0:
            return self.display_name.strip()
        return self.user_name

    def _get_locale(self):
        if not self._locale:
            return None
        return Locale.parse(self._locale)

    def _set_locale(self, locale):
        self._locale = unicode(locale)

    locale = property(_get_locale, _set_locale)

    def _get_email(self):
        return self._email

    def _set_email(self, email):
        import adhocracy.lib.util as util
        if not self._email == email:
            self.activation_code = util.random_token()
        self._email = email

    email = property(_get_email, _set_email)

    @property
    def email_hash(self):
        return hashlib.sha1(self.email).hexdigest()

    @property
    def is_organization(self):
        allow = config.get_bool('adhocracy.allow_organization')
        return allow and self._is_organization

    def badge_groups(self):
        current_instance = ifilter.get_instance()
        groups = []
        for badge in self.badges:
            group = badge.group
            if (group is not None and group not in groups
               and badge.instance in [None, current_instance]):
                groups.append(group)
        return groups

    def get_badges(self, instance=None):
        """
        Get user badges which are appropriate in the given context.
        """
        return [b for b in self.badges if b.instance is None
                or b.instance is instance]

    def membership_groups(self):
        from membership import Membership
        current_instance = ifilter.get_instance()

        memberships_q = meta.Session.query(Membership).filter(
            Membership.user_id == self.id)

        if current_instance is None:
            memberships_q = memberships_q.filter(
                Membership.instance_id == None)  # noqa
        else:
            memberships_q = memberships_q.filter(or_(
                Membership.instance_id == None,  # noqa
                Membership.instance_id == current_instance.id
            ))

        memberships = memberships_q.all()
        return [m.group for m in memberships if not m.is_expired()]

    @property
    def groups(self):
        return list(set(self.badge_groups() + self.membership_groups()))

    def instance_groups(self):
        return filter(lambda g: g.is_instance_group(), self.groups)

    def _has_permission(self, permission_name):
        for group in self.groups:
            for perm in group.permissions:
                if perm.permission_name == permission_name:
                    return True
        return False

    def instance_membership(self, instance):
        if not instance:
            return None

        from membership import Membership
        memberships = meta.Session.query(Membership).filter(
            Membership.user_id == self.id,
            Membership.instance_id == instance.id)\
            .all()
        for membership in memberships:
            if not membership.is_expired():
                return membership
        return None

    def is_member(self, instance):
        return self.instance_membership(instance) is not None

    @property
    def instances(self):
        return self.get_instances()

    def get_instances(self, include_hidden=False):
        instances = []
        for membership in self.memberships:
            if (not membership.is_expired()) and \
                    (membership.instance is not None) and \
                    (include_hidden or not membership.instance.hidden):
                instances.append(membership.instance)
        return list(set(instances))

    def real_instances(self, exclude_current=False):
        excluded_keys = copy(Instance.SPECIAL_KEYS)
        if exclude_current:
            current_instance = ifilter.get_instance()
            if current_instance is not None:
                excluded_keys.append(ifilter.get_instance().key)
        return sorted(
            filter(lambda i: i.key not in excluded_keys, self.instances),
            key=lambda i: i.key)

    @property
    def twitter(self):
        for twitter in self.twitters:
            if not twitter.is_deleted():
                return twitter
        return None

    @property
    def openids(self):
        _ids = []
        for openid in self._openids:
            if not openid.is_deleted():
                _ids.append(openid)
        return _ids

    @property
    def velruse(self):
        _ids = []
        for velruse in self._velruse:
            if not velruse.is_deleted():
                _ids.append(velruse)
        return _ids

    @property
    def num_watches(self):
        from watch import Watch
        q = meta.Session.query(Watch)
        q = q.filter(Watch.user == self)
        q = q.filter(or_(Watch.delete_time == None,  # noqa
                         Watch.delete_time >= datetime.utcnow()))
        return q.count()

    def _set_password(self, password):
        """Hash password on the fly."""
        if isinstance(password, unicode):
            password_8bit = password.encode('ascii', 'ignore')
        else:
            password_8bit = password

        salt = hashlib.sha1(os.urandom(60))
        hash = hashlib.sha1(password_8bit + salt.hexdigest())
        hashed_password = salt.hexdigest() + hash.hexdigest()

        if not isinstance(hashed_password, unicode):
            hashed_password = hashed_password.decode('utf-8')
        self._password = hashed_password

        # Invalidate temporary password recovery codes
        self.reset_code = None
        self.welcome_code = None

    def _get_password(self):
        """Return the password hashed"""
        return self._password

    def validate_password(self, password):
        """
        Check the password against existing credentials.

        :param password: the password that was provided by the user to
            try and authenticate. This is the clear text version that we will
            need to match against the hashed one in the database.
        :type password: unicode object.
        :return: Whether the password is valid.
        :rtype: bool
        """
        if self.password is None:
            return False
        if isinstance(password, unicode):
            password_8bit = password.encode('ascii', 'ignore')
        else:
            password_8bit = password
        if self.banned or self.delete_time:
            return False
        hashed_pass = hashlib.sha1(password_8bit + self.password[:40])
        return self.password[40:] == hashed_pass.hexdigest()

    password = property(_get_password, _set_password)

    def initialize_welcome(self):
        """ Sign up the user for the welcome feature (on user import or so) """
        import adhocracy.lib.util as util
        self.welcome_code = util.random_token()
        self._password = None

    def current_agencies(self, instance_filter=True):
        ds = filter(lambda d: not d.is_revoked(), self.agencies)
        if ifilter.has_instance() and instance_filter:
            ds = filter(lambda d: d.scope.instance == ifilter.get_instance(),
                        ds)
        return ds

    def current_delegated(self, instance_filter=True):
        ds = filter(lambda d: not d.is_revoked(), self.delegated)
        if ifilter.has_instance() and instance_filter:
            ds = filter(lambda d: d.scope.instance == ifilter.get_instance(),
                        ds)
        return ds

    @classmethod
    def complete(cls, prefix, limit=5, instance_filter=True):
        q = meta.Session.query(User)
        prefix = prefix.lower()
        q = q.filter(or_(func.lower(User.user_name).like(prefix + u"%"),
                         func.lower(User.display_name).like(prefix + u"%")))
        q = q.limit(limit)
        completions = q.all()
        if ifilter.has_instance() and instance_filter:
            inst = ifilter.get_instance()
            completions = filter(lambda u: u.is_member(inst), completions)
        return completions

    @classmethod
    # @meta.session_cached
    def find(cls, user_name, instance_filter=True, include_deleted=False):
        from membership import Membership
        try:
            q = meta.Session.query(User)
            try:
                q = q.filter(User.id == int(user_name))
            except ValueError:
                q = q.filter(User.user_name == unicode(user_name))
            if not include_deleted:
                q = q.filter(or_(User.delete_time == None,  # noqa
                                 User.delete_time > datetime.utcnow()))
            if ifilter.has_instance() and instance_filter:
                q = q.join(Membership)
                q = q.filter(or_(Membership.expire_time == None,  # noqa
                                 Membership.expire_time > datetime.utcnow()))
                q = q.filter(Membership.instance == ifilter.get_instance())
            return q.limit(1).first()
        except Exception, e:
            log.debug("find(%s): %s" % (user_name, e))
            return None

    @classmethod
    def find_by_email(cls, email, include_deleted=False):
        return cls.all_q(None, include_deleted)\
            .filter(func.lower(User.email) == unicode(email).lower())\
            .limit(1).first()

    @classmethod
    def find_by_user_name(cls, user_name, include_deleted=False):
        return cls.find(user_name, include_deleted=include_deleted)

    @classmethod
    def find_by_shibboleth(cls, persistent_id, include_deleted=False):
        from shibboleth import Shibboleth
        return cls.all_q(None, include_deleted)\
            .join(Shibboleth)\
            .filter(Shibboleth.persistent_id == persistent_id)\
            .limit(1).first()

    @classmethod
    def find_all(cls, unames, instance_filter=True, include_deleted=False):
        from membership import Membership
        q = meta.Session.query(User)
        q = q.filter(User.user_name.in_(unames))
        if not include_deleted:
            q = q.filter(or_(User.delete_time == None,  # noqa
                             User.delete_time > datetime.utcnow()))
        if ifilter.has_instance() and instance_filter:
            q = q.join(Membership)
            q = q.filter(or_(Membership.expire_time == None,  # noqa
                             Membership.expire_time > datetime.utcnow()))
            q = q.filter(Membership.instance == ifilter.get_instance())
        # log.debug("QueryAll: %s" % q)
        # log.debug("LEN: %s" % len(q.all()))
        return q.all()

    _index_id_attr = 'user_name'

    @classmethod
    def all_q(cls, instance=None, include_deleted=False):
        from membership import Membership
        q = meta.Session.query(User)
        if not include_deleted:
            q = q.filter(or_(User.delete_time == None,  # noqa
                             User.delete_time > datetime.utcnow()))
        if instance:
            q = q.options(eagerload_all('memberships'))
            q = q.join(Membership)
            q = q.filter(or_(Membership.expire_time == None,  # noqa
                             Membership.expire_time > datetime.utcnow()))
            q = q.filter(Membership.instance == instance)
        return q

    @classmethod
    def all(cls, instance=None, include_deleted=False):
        return cls.all_q(instance=instance,
                         include_deleted=include_deleted).all()

    def delete(self, delete_time=None):
        from watch import Watch

        if delete_time is None:
            delete_time = datetime.utcnow()
        self.revoke_delegations()
        for twitter in self.twitters:
            twitter.delete(delete_time=delete_time)
        for openid in self.openids:
            openid.delete(delete_time=delete_time)
        for velruse in self.velruse:
            velruse.delete(delete_time=delete_time)
        for comment in self.comments:
            comment.delete(delete_time=delete_time)
        for membership in self.memberships:
            membership.delete(delete_time=delete_time)
        for watch in Watch.all_by_user(self):
            watch.delete(delete_time=delete_time)

        # for vote in self.votes:
        #     vote.delete(delete_time=delete_time)
        self.delete_time = delete_time

    def undelete(self):
        from watch import Watch

        for twitter in self.twitters:
            twitter.delete_time = None
        for openid in self.openids:
            openid.delete_time = None
        for velruse in self.velruse:
            velruse.delete_time = None
        for comment in self.comments:
            comment.delete_time = None
        for membership in self.memberships:
            membership.expire_time = None
        for watch in Watch.all_by_user(self):
            watch.delete_time = None

        self.delete_time = None

    def is_deleted(self, at_time=None):
        if at_time is None:
            at_time = datetime.utcnow()
        return ((self.delete_time is not None) and
                self.delete_time <= at_time)

    def revoke_delegations(self, instance=None):
        from delegation import Delegation
        q = meta.Session.query(Delegation)
        q = q.filter(or_(Delegation.agent == self,
                         Delegation.principal == self))
        q = q.filter(or_(Delegation.revoke_time == None,  # noqa
                         Delegation.revoke_time > datetime.utcnow()))
        for delegation in q:
            if instance is None or delegation.scope.instance == instance:
                delegation.revoke()

    def is_email_activated(self):
        return self.email is not None and self.activation_code is None

    def set_email_verified(self):
        # for adhocracy, None means email is verified
        self.activation_code = None
        meta.Session.commit()

    def delegation_node(self, scope):
        from adhocracy.lib.democracy import DelegationNode
        return DelegationNode(self, scope)

    def number_of_votes_in_scope(self, scope):
        """
        May be a bit too much as multiple delegations are counted for each user
        they are delegated to. (This is the safety net delegation)
        """
        if not self._has_permission('vote.cast'):
            return 0
        return self.delegation_node(scope).number_of_delegations() + 1

    def position_on_poll(self, poll):
        from adhocracy.lib.democracy.decision import Decision
        return Decision(self, poll).result

    def any_position_on_proposal(self, proposal):
        # this is fuzzy since it includes two types of opinions
        from adhocracy.lib.democracy.decision import Decision
        if proposal.adopt_poll:
            dec = Decision(self, proposal.adopt_poll)
            if dec.is_decided():
                return dec.result
        if proposal.rate_poll:
            return Decision(self, proposal.rate_poll).result

    @classmethod
    def create(cls, user_name, email, password=None, locale=None,
               openid_identity=None, global_admin=False, display_name=None,
               autojoin=True, shibboleth_persistent_id=None):
        """
        Create a user. If user_name is None, a random user name is generated.
        """
        from group import Group
        from membership import Membership

        import adhocracy.lib.util as util
        if password is None:
            password = util.random_token()

        import adhocracy.i18n as i18n
        if locale is None:
            locale = i18n.get_default_locale()

        while user_name is None:
            # Note: This can theoretically lead to IntegrityErrors if the same
            # username is generated at the same time. This is very unlikely
            # though.
            from adhocracy.lib.util import random_username
            try_user_name = random_username()
            if cls.find(try_user_name) is None:
                user_name = try_user_name
                from adhocracy.lib import helpers as h
                h.flash(_('The random username %s has been assigned to you.') %
                        user_name, 'success')

        user = User(user_name, email, password, locale,
                    display_name=display_name)
        meta.Session.add(user)

        # Add the global default group
        default_group = Group.by_code(Group.CODE_DEFAULT)
        default_membership = Membership(user, None, default_group)
        meta.Session.add(default_membership)

        # Autojoin the user in instances
        config_autojoin = config.get('adhocracy.instances.autojoin')
        if autojoin and config_autojoin:
            instances = Instance.all(include_hidden=True)
            if config_autojoin != 'ALL':
                instance_keys = [key.strip() for key in
                                 config_autojoin.split(",")]
                instances = [instance for instance in instances
                             if instance.key in instance_keys]
            for instance in instances:
                autojoin_membership = Membership(user, instance,
                                                 instance.default_group)
                meta.Session.add(autojoin_membership)

        if global_admin:
            admin_group = Group.by_code(Group.CODE_ADMIN)
            admin_membership = Membership(user, None, admin_group)
            meta.Session.add(admin_membership)

        if openid_identity is not None:
            from adhocracy.model.openid import OpenID
            openid = OpenID(unicode(openid_identity), user)
            meta.Session.add(openid)

        if shibboleth_persistent_id is not None:
            from adhocracy.model.shibboleth import Shibboleth
            shib = Shibboleth(shibboleth_persistent_id, user)
            meta.Session.add(shib)

        meta.Session.flush()
        return user

    def to_dict(self):
        from adhocracy.lib import helpers as h
        d = dict(id=self.id,
                 user_name=self.user_name,
                 locale=self._locale,
                 url=h.entity_url(self),
                 create_time=self.create_time,
                 mbox=self.email_hash)
        if self.display_name:
            d['display_name'] = self.display_name
        if self.bio:
            d['bio'] = self.bio
        # d['memberships'] = map(lambda m: m.instance.key,
        #                        self.memberships)
        return d

    def to_index(self):
        index = super(User, self).to_index()

        index.update(dict(
            title=self.name,
            tag=[self.user_name],
            body=self.bio,
            user=self.user_name,
        ))
        return index

    def __repr__(self):
        return u"<User(%s,%s)>" % (self.id, self.user_name)

    @property
    def title(self):
        return self.name
