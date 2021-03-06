from datetime import datetime
import logging
import re

from pylons.i18n import _
from sqlalchemy import Table, Column, ForeignKey, func, or_, not_
from sqlalchemy import Integer, Unicode, UnicodeText, Boolean

import meta
from delegateable import Delegateable
import instance_filter as ifilter

log = logging.getLogger(__name__)


page_table = Table(
    'page', meta.data,
    Column('id', Integer, ForeignKey('delegateable.id'), primary_key=True),
    Column('function', Unicode(20)),
    Column('formatting', Boolean, default=False),
    Column('sectionpage', Boolean, default=True),
    Column('allow_comment', Boolean, default=True),
    Column('allow_selection', Boolean, default=True),
    Column('always_show_original', Boolean, default=True),
    Column('abstract', Unicode(255), default=u'', nullable=True),
)


class Page(Delegateable):

    DESCRIPTION = u"description"
    NORM = u"norm"
    CONTAINER = u"container"

    FUNCTIONS = [DESCRIPTION, NORM, CONTAINER]
    PARENT_FUNCTIONS = [NORM, CONTAINER]
    WITH_VARIANTS = [NORM]  # [DESCRIPTION, NORM]
    LISTED = [NORM, CONTAINER]

    def __init__(self, instance, alias, creator, function, formatting=False,
                 sectionpage=False, allow_comment=True, allow_selection=True,
                 always_show_original=True, abstract=None):
        self.init_child(instance, alias, creator)
        self.function = function
        self.formatting = formatting
        self.sectionpage = sectionpage
        self.allow_comment = allow_comment
        self.allow_selection = allow_selection
        self.always_show_original = always_show_original
        self.abstract = abstract

    @property
    def selections(self):
        return [s for s in self._selections if not s.is_deleted()]

    @property
    def texts(self):
        return [t for t in self._texts if not t.is_deleted()]

    @classmethod
    def find_fuzzy(cls, id, instance_filter=True, include_deleted=False):
        page = cls.find(id, instance_filter=instance_filter,
                        include_deleted=include_deleted)
        if page is None:
            from text import Text
            q = meta.Session.query(Page)
            q = q.join(Text)
            q = q.filter(Text.title.like(id))
            if not include_deleted:
                q = q.filter(or_(Page.delete_time == None,  # noqa
                                 Page.delete_time > datetime.utcnow()))
            if ifilter.has_instance() and instance_filter:
                q = q.filter(Page.instance == ifilter.get_instance())
            q = q.order_by(Text.create_time.asc())
            page = q.limit(1).first()
        return page

    @classmethod
    def find(cls, id, instance_filter=True, include_deleted=False):
        try:
            q = meta.Session.query(Page)
            try:
                id = int(id)
                q = q.filter(Page.id == id)
            except ValueError:
                # from adhocracy.lib.text import title2alias
                q = q.filter(Page.label == id)
            if not include_deleted:
                q = q.filter(or_(Page.delete_time == None,  # noqa
                                 Page.delete_time > datetime.utcnow()))
            if ifilter.has_instance() and instance_filter:
                q = q.filter(Page.instance == ifilter.get_instance())
            return q.limit(1).first()
        except Exception, e:
            log.warn("find(%s): %s" % (id, e))
            return None

    @classmethod
    def all_q(cls, instance=None, functions=[], exclude=[],
              include_deleted=False):
        q = meta.Session.query(Page)
        if not include_deleted:
            q = q.filter(or_(Page.delete_time == None,  # noqa
                             Page.delete_time > datetime.utcnow()))
        if functions != []:
            q = q.filter(Page.function.in_(functions))
        if instance is not None:
            q = q.filter(Page.instance == instance)
        if exclude != []:
            q = q.filter(not_(Page.id.in_([p.id for p in exclude])))
        return q

    @classmethod
    def all(cls, include_sectionpages=True, **kwargs):
        pages = cls.all_q(**kwargs).all()
        if not include_sectionpages:
            pages = filter(lambda p: not p.is_sectionpage(), pages)
        return pages

    @classmethod
    def unusedTitle(cls, title, instance_filter=True, functions=None,
                    include_deleted=False, selection=None):
        q = meta.Session.query(Page)\
            .filter(Page.label == title)
        if not include_deleted:
            q = q.filter(or_(Page.delete_time == None,  # noqa
                             Page.delete_time > datetime.utcnow()))
        if ifilter.has_instance() and instance_filter:
            q = q.filter(Page.instance == ifilter.get_instance())

        matches = q.all()

        if selection is not None:
            def same_selection(page):
                try:
                    return (page.function == Page.DESCRIPTION and
                            page.proposal.is_amendment and
                            page.proposal.selection.page == selection)
                except Exception as e:
                    log.warn(e)
                    return False
            matches = filter(same_selection, matches)

        return not bool(matches)

    @classmethod
    def count(cls, **kwargs):
        return cls.all_q(**kwargs).count()

    @classmethod
    def create(cls, instance, title, text, creator, function=NORM, tags=None,
               wiki=False, formatting=False, sectionpage=False,
               allow_comment=True, allow_selection=True,
               always_show_original=True, abstract=None):
        from adhocracy.lib.text import title2alias
        from text import Text
        from tagging import Tagging
        if function not in Page.FUNCTIONS:
            raise AttributeError("Invalid page function type")
        label = title2alias(title)
        page = Page(instance, label, creator, function, formatting,
                    sectionpage, allow_comment, allow_selection,
                    always_show_original, abstract)
        meta.Session.add(page)
        meta.Session.flush()
        Text(page, Text.HEAD, creator, title, text, wiki)

        if tags is not None:
            page.taggings = Tagging.create_all(page, tags, creator)

        return page

    def establish_variant(self, variant, user):
        for selection in self.selections:
            selection.make_variant_poll(variant, user)

    def variant_polls(self, variant):
        polls = [s.variant_poll(variant) for s in self.selections]
        polls = [p for p in polls if p is not None]
        return polls

    def variant_tally(self, variant):
        from tally import Tally
        polls = self.variant_polls(variant)
        return Tally.combine_polls(polls)

    def variant_tallies(self):
        return [self.variant_tally(v) for v in self.variants]

    @property
    def proposal(self):
        if self.function == Page.DESCRIPTION:
            return self._proposal[-1]
        return None

    @property
    def parent(self):
        for d in self.parents:
            if (isinstance(d, Page) and d.function in self.LISTED and not
                    d.is_deleted()):
                return d

    @property
    def subpages(self):
        return [c for c in self.children if isinstance(c, Page) and
                c.function in self.LISTED and not c.is_deleted()]

    def sectionpage_root(self):
        """This returns the nearest ancestor sectionpage of this page.
        If non exists this returns None"""
        # I tried to avoid is_sectionpage() here as that is recursice itself
        if self.sectionpage:
            return self
        elif self.parent is not None:
            return self.parent.sectionpage_root()
        else:
            return None

    @property
    def has_variants(self):
        return self.function in Page.WITH_VARIANTS and self.allow_selection

    @property
    def variants(self):
        from text import Text
        if not self.has_variants:
            return [Text.HEAD]
        return list(set([t.variant for t in self.texts]))

    def variant_head(self, variant):
        for text in self.texts:
            if text.variant == variant:
                return text
        return None

    def variant_at(self, variant, at_time):
        for text in self.variant_history(variant):
            if text.create_time <= at_time:
                return text
        return None

    def variant_history(self, variant):
        head = self.variant_head(variant)
        if head:
            return head.history
        return []

    def variant_changes_count(self, variant):
        head = self.variant_head(variant)
        if head:
            return head.history_q().count() - 1
        return 0

    def variant_comments(self, variant):
        return [c for c in self.comments if
                ((not c.is_deleted()) and c.variant == variant)]

    def rename_variant(self, old_name, new_name):
        from text import Text
        if old_name == Text.HEAD or new_name in self.variants:
            return
        for text in self._texts:
            if text.variant == old_name:
                text.variant = new_name
        for selection in self._selections:
            poll = selection.variant_poll(old_name)
            poll.subject = selection.variant_key(new_name)

    @property
    def heads(self):
        from text import Text
        if not self.has_variants:
            return [self.variant_head(Text.HEAD)]
        return [self.variant_head(h) for h in self.variants]

    @property
    def head(self):
        from text import Text
        return self.variant_head(Text.HEAD)

    @property
    def title(self):
        if not self.head or not self.head.title:
            return _("(Untitled)")
        title = self.head.title
        if self.is_sectionpage():
            # section titles are "root_label( index)*"
            # this transforms that title into a more human-friendly one
            root = self.sectionpage_root()
            if root != self:
                match = re.match('^%s( \d+)+$' % root.label, title)

                # legacy
                if match is None:
                    match = re.match('^%s( \d+)+$' % root.title, title)

                if match is not None:
                    section_no = [unicode(int(g.strip(), 10) + 1)
                                  for g in match.groups()]
                    section_no = u'.'.join(section_no)
                    return _(u"%s (section %s)") % (root.title, section_no)
        return title

    @property
    def full_title(self):
        from adhocracy.lib.helpers import truncate
        title = truncate(self.title, length=40, whole_word=True)
        if self.parent:
            title = self.parent.full_title + " - " + title
        return title

    def render(self, variant=None, line_based=None):
        from text import Text
        if variant is None:
            # FIXME always_show_original should be used here
            variant = Text.HEAD
        if line_based is None:
            line_based = not self.formatting
        return self.variant_head(variant).render(line_based)

    def _get_parent(self):
        for parent in self.parents:
            if isinstance(parent, Page):
                return parent
        return None

    def _set_parent(self, parent):
        parents = []
        for old_parent in self.parents:
            if not isinstance(old_parent, Page):
                parents.append(old_parent)
        if parent is not None:
            parents.append(parent)
        self.parents = parents

    parent = property(_get_parent, _set_parent)

    @property
    def changing_selections(self):
        from text import Text
        selections = []
        for selection in self.selections:
            if selection.is_deleted():
                continue
            if selection.proposal.adopted:
                continue
            if selection.selected != Text.HEAD:
                selections.append(selection)
        return selections

    def is_sectionpage(self):
        if self.sectionpage:
            return True
        else:
            return self.is_section()

    def is_section(self):
        if self.parent:
            return self.parent.is_sectionpage()
        else:
            return False

    def supporting_selections(self, variant):
        selections = []
        for selection in self.selections:
            if selection.is_deleted():
                continue
            if selection.proposal.adopted:
                continue
            if selection.selected == variant:
                selections.append(selection)
        return selections

    def delete(self, delete_time=None):
        if delete_time is None:
            delete_time = datetime.utcnow()
        for selection in self.selections:
            selection.delete(delete_time=delete_time)
        if self.delete_time is None:
            self.delete_time = delete_time

    def is_deleted(self, at_time=None):
        if at_time is None:
            at_time = datetime.utcnow()
        return ((self.delete_time is not None) and
                self.delete_time <= at_time)

    def purge_variant(self, variant, delete_time=None):
        if delete_time is None:
            delete_time = datetime.utcnow()
        for text in self.texts:
            if text.variant == variant:
                text.delete(delete_time=delete_time)
        for selection in self._selections:
            poll = selection.variant_poll(variant)
            poll.end()

    def is_mutable(self):
        if self.function == self.DESCRIPTION and self.proposal:
            return self.proposal.is_mutable()
        return not self.instance.frozen

    def is_frozen(self):
        if self.function == self.DESCRIPTION and self.proposal:
            return self.proposal.frozen
        else:
            return self.frozen

    def user_position(self, user):
        if self.function == self.DESCRIPTION and self.proposal:
            return self.proposal.user_position(user)
        return 0

    def _index_id(self):
        return self.id

    def contributors(self):
        from user import User
        from text import Text
        q = meta.Session.query(User)
        q = q.join(Text)
        q = q.add_column(func.count(Text.id))
        q = q.filter(Text.page == self)
        q = q.group_by(User.id)
        q = q.order_by(func.count(Text.id).desc())
        cbs = super(Page, self).contributors()
        return self._join_contributors(cbs, q.all(), second_factor=2)

    def to_dict(self, text=None):
        if text is None:
            text = self.head
        from adhocracy.lib import helpers as h
        d = dict(id=self.id,
                 url=h.entity_url(self),
                 create_time=self.create_time,
                 label=self.label,
                 title=self.title,
                 full_title=self.full_title,
                 text=text,
                 function=self.function,
                 creator=self.creator.user_name)
        if self.parent:
            d['parent'] = self.parent.id
        return d

    def to_index(self):
        index = super(Page, self).to_index()
        if self.function == self.DESCRIPTION:
            index['skip'] = True
            return index
        if self.head is not None:
            index.update(dict(
                body=self.head.text,
            ))
        return index

    def __repr__(self):
        return u"<Page(%s)>" % (self.id)
