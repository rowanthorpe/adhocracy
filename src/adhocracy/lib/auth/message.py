from pylons import tmpl_context as c
from authorization import has


def show(check, msg):
    check.other('is_not_creator_or_recipient', c.user != msg.creator and
                c.user not in (r.recipient for r in msg.recipients))


def show_recipients(check, msg):
    show(check, msg)
    check.other('is_not_creator', c.user != msg.creator)
