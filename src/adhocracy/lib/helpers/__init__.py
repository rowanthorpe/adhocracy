"""Helper functions

Consists of functions to typically be used within templates, but also
available to Controllers. This module is available to templates as 'h'.
"""
import cgi
from datetime import datetime
import hashlib
import json
import urllib
import logging

from pylons import tmpl_context as c, request
from pylons.i18n import _, get_lang
from webhelpers.html import literal
from webhelpers.html.tags import file
from webhelpers.pylonslib import Flash as _Flash
from webhelpers.text import truncate

from adhocracy import config
from adhocracy.lib import cache
from adhocracy.lib import democracy
from adhocracy.lib import sorting
from adhocracy.lib import version
from adhocracy.lib.auth.authentication import allowed_login_types
from adhocracy.lib.auth.authorization import has as has_permission
from adhocracy.lib.auth.csrf import url_token, field_token
from adhocracy.lib.helpers import site_helper as site
from adhocracy.lib.helpers import user_helper as user
from adhocracy.lib.helpers import proposal_helper as proposal
from adhocracy.lib.helpers import text_helper as text
from adhocracy.lib.helpers import page_helper as page
from adhocracy.lib.helpers import delegateable_helper as delegateable
from adhocracy.lib.helpers import tag_helper as tag
from adhocracy.lib.helpers import poll_helper as poll
from adhocracy.lib.helpers import comment_helper as comment
from adhocracy.lib.helpers import selection_helper as selection
from adhocracy.lib.helpers import delegation_helper as delegation
from adhocracy.lib.helpers import instance_helper as instance
from adhocracy.lib.helpers import abuse_helper as abuse, tutorial
from adhocracy.lib.helpers import milestone_helper as milestone
from adhocracy.lib.helpers import recaptcha_helper as recaptcha
from adhocracy.lib.helpers import staticpage_helper as staticpage
from adhocracy.lib.helpers import badge_helper as badge
from adhocracy.lib.helpers import treatment_helper as treatment
from adhocracy.lib.helpers import category_helper as category
from adhocracy.lib.helpers import message_helper as message

from adhocracy.lib.helpers.fanstatic_helper import (FanstaticNeedHelper,
                                                    get_socialshareprivacy_url)
from adhocracy.lib.helpers import feedback_helper as feedback
from adhocracy.lib.helpers.url import build
from adhocracy.lib.helpers.site_helper import base_url, velruse_url
from adhocracy.lib.text import (render, markdown_to_plain_text,
                                html_to_plain_text)
from adhocracy.lib.helpers import velruse_helper as velruse
from adhocracy.lib.watchlist import make_watch, find_watch
from adhocracy import model, static
from adhocracy.i18n import countdown_time, format_date
from adhocracy.i18n import date_tag
from adhocracy.i18n import datetime_tag
from adhocracy.model.text import Text


log = logging.getLogger(__name__)


flash = _Flash()
recaptcha = recaptcha.Recaptcha()
need = FanstaticNeedHelper(static)


def allow_user_registration():
    return (config.get_bool('adhocracy.allow_registration')
            and not config.get_bool('adhocracy.readonly'))


def sorted_flash_messages():
    '''
    Return the flash messages sorted by priority, keeping
    the order.
    '''
    order = ['error', 'warning', 'success', 'notice']
    sorted_ = []
    unsorted = flash.pop_messages()
    for category in order:
        for message in unsorted:
            if message.category == category:
                sorted_.append(message)
    return sorted_


def immutable_proposal_message():
    return _("This proposal is currently being voted on and cannot "
             "be modified.")


def comments_sorted(comments, root=None, variant=None, key=None,
                    include_deleted=False):
    from adhocracy.lib.tiles.comment_tiles import CommentTile
    comments = [c for c in comments if c.reply == root and
                ((variant is None and c.variant == Text.HEAD)
                 or c.variant == variant)]
    if not include_deleted:
        comments = filter(lambda x: not x.is_deleted(), comments)
    _comments = []
    if key is None:
        comments = sorting.comment_order(comments)
    else:
        comments = sorted(comments, key=key)
    for comment in comments:
        tile = CommentTile(comment)
        _comments.append((comment, tile))
    return _comments


def contains_delegations(user, delegateable, recurse=True):
    for delegation in user.agencies:
        if (not delegation.revoke_time and
            (delegation.scope == delegateable or
             (delegation.scope.is_sub(delegateable) and recurse))):
            return True
    for delegation in user.delegated:
        if (not delegation.revoke_time and
            (delegation.scope == delegateable or
             (delegation.scope.is_sub(delegateable) and recurse))):
            return True
    return False


def poll_position_css(poll):
    @cache.memoize('poll_position_css')
    def _cached(user, poll):
        pos = user.position_on_poll(poll)
        if pos == 1:
            return "upvoted"
        elif pos == -1:
            return "downvoted"
        else:
            return ""
    if c.user:
        return _cached(c.user, poll)
    return u""


def add_meta(name, content):
    '''
    Add information to be rendered as a meta tag
    by a template in the html head. *value* will be used for the
    name attribute, *content* for the content attribute of the
    meta tag.
    '''
    if not c.html_meta:
        c.html_meta = dict()
    c.html_meta[name] = content


def add_html_head_link(title, link, rel, type):
    '''
    Add information to be rendered as a link tag
    by a template in the html head. The parameters
    correspondent to the attributes of the link tag.
    '''
    if not c.html_head_links:
        c.html_head_links = []
    c.html_head_links.append({'title': title,
                              'href': link,
                              'rel': rel,
                              'type': type})


def add_rss(title, link):
    '''
    Add information to be rendered as a link tag in the html
    head with rel="alternate" and type="application/rss+xml"
    '''
    add_html_head_link(title, link, rel='alternate',
                       type='application/rss+xml')


def help_link(text, page, anchor=None):
    url = base_url('/static/%s.%s', None)
    if anchor is not None:
        url += "#" + anchor
    full_url = url % (page, 'html')
    return (u"<a target='_new' class='staticlink_%s' href='%s' "
            u">%s</a>") % (page, full_url, text)


def get_redirect_url(target=u'login', entity=None, **kwargs):
    '''
    Builds an URL similar to  ".../login?came_from=http...." pointing to the
    target path in the current instance domain. If we already have a
    ``came_from`` parameter in the path, this is going to be used as the new
    ``came_from`` target. Otherwise, if ``entity`` is set, this will redirect
    to the given entity after successful login. If ``entity`` is None, it will
    redirect to the current URL.
    '''
    if c.came_from == u'':
        if entity is None:
            c.came_from = base_url(request.path,
                                   query_string=request.query_string)
        else:
            c.came_from = entity_url(entity, **kwargs)

    return build(c.instance, '', target, query={'came_from': c.came_from})


def login_redirect_url(entity=None, **kwargs):
    return get_redirect_url(u'login', entity, **kwargs)


def register_redirect_url(entity=None, **kwargs):
    return get_redirect_url(u'register', entity, **kwargs)


def join_redirect_url(entity=None, **kwargs):
    return get_redirect_url(u'instance/%s/ask_join' % c.instance.key, **kwargs)


def validate_redirect_url(entity=None, **kwargs):
    return get_redirect_url(u'user/%s/ask_activate' % c.user.user_name, entity,
                            **kwargs)


def entity_url(entity, **kwargs):
    if isinstance(entity, model.User):
        return user.url(entity, **kwargs)
    elif isinstance(entity, model.Proposal):
        return proposal.url(entity, **kwargs)
    elif isinstance(entity, model.Page):
        return page.url(entity, **kwargs)
    elif isinstance(entity, model.Text):
        return text.url(entity, **kwargs)
    elif isinstance(entity, model.Delegateable):
        return delegateable.url(entity, **kwargs)
    elif isinstance(entity, model.Poll):
        return poll.url(entity, **kwargs)
    elif isinstance(entity, model.Selection):
        return selection.url(entity, **kwargs)
    elif isinstance(entity, model.Comment):
        return comment.url(entity, **kwargs)
    elif isinstance(entity, model.Instance):
        return instance.url(entity, **kwargs)
    elif isinstance(entity, model.Delegation):
        return delegation.url(entity, **kwargs)
    elif isinstance(entity, model.Milestone):
        return milestone.url(entity, **kwargs)
    elif isinstance(entity, model.Tag):
        return tag.url(entity, **kwargs)
    elif isinstance(entity, model.StaticPage):
        return staticpage.url(entity, **kwargs)
    elif isinstance(entity, model.Treatment):
        return treatment.url(entity, **kwargs)
    elif isinstance(entity, model.Message):
        return message.url(entity, **kwargs)
    raise ValueError("No URL maker for: %s" % repr(entity))


def logo_url(entity, y, x=None, **kwargs):
    if isinstance(entity, model.User):
        return user.logo_url(entity, y, x=x, **kwargs)
    elif isinstance(entity, model.Page):
        return page.logo_url(entity, y, x=x, **kwargs)
    elif isinstance(entity, model.Instance):
        return instance.logo_url(entity, y, x=x, **kwargs)
    elif isinstance(entity, model.CategoryBadge):
        return category.logo_url(entity, y, x=x, **kwargs)
    raise ValueError("No logo URL maker for: %s" % repr(entity))


def json_dumps(data, encoding='utf-8'):
    return json.dumps(data, default=_json_entity,
                      encoding=encoding, indent=4)


def json_loads(s, encoding='utf-8'):
    return json.loads(s, object_hook=_json_entity_decoder)


def _json_entity(o):
    if isinstance(o, datetime):
        return o.isoformat() + "Z"
    if hasattr(o, 'to_dict'):
        return o.to_dict()
    raise TypeError("This is not serializable: " + repr(o))


def _json_entity_decoder(d):
    if isinstance(d, list):
        pairs = enumerate(d)
    elif isinstance(d, dict):
        pairs = d.items()
    result = []
    for k, v in pairs:
        if isinstance(v, basestring):
            for (format, getter) in (('%Y-%m-%dT%H:%M:%S.%f', lambda x: x),
                                     ('%Y-%m-%dT%H:%M:%S.%fZ', lambda x: x),
                                     ('%Y-%m-%d', lambda x: x.date())):
                try:
                    dateobj = datetime.strptime(v, format)
                    v = getter(dateobj)
                    break
                except ValueError:
                    pass

        elif isinstance(v, (dict, list)):
            v = _json_entity_decoder(v)

        result.append((k, v))
    if isinstance(d, list):
        return [x[1] for x in result]
    elif isinstance(d, dict):
        return dict(result)


def overlay_link():
    overlay_path = request.params.get('overlay_path', None)
    if overlay_path is None:
        return None
    else:
        return overlay_path.replace('.overlay', '.html')


def need_js_i18n(resource):
    from adhocracy.static import js_i18n
    if str(c.locale) in js_i18n[resource]:
        locale = str(c.locale)
    else:
        locale = c.locale.language
    if locale in js_i18n[resource]:
        res = js_i18n[resource][locale]
        return res.need()
    else:
        log.warn('no js localization for resource %s and locale %s'
            % (resource, c.locale))
