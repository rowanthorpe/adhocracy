from pylons import tmpl_context as c, config, request, g
from pylons.i18n import _

def name():
    return config.get('adhocracy.site.name', _("Adhocracy"))
    
def base_url(instance, path=None):
    url = "http://"
    if instance is not None and g.single_instance is None:
        url += instance.key + "."
    url += request.environ.get('adhocracy.domain')
    port = int(request.environ.get('SERVER_PORT'))
    if port != 80:
        url += ':' + str(port)
    if path is not None:
        url += path
    return url