#!/usr/bin/python
# coding: utf-8

########################

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin
import json
import time
import datetime
import os
import operator
import arrow
import sys
import simplecache
import hashlib

########################

PYTHON3 = True if sys.version_info.major == 3 else False

ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo('id')
ADDON_VERSION = ADDON.getAddonInfo('version')

''' Python 2<->3 compatibility
'''
if not PYTHON3:
    ADDON_PATH = ADDON.getAddonInfo('path').decode('utf-8')
else:
    ADDON_PATH = ADDON.getAddonInfo('path')

NOTICE = xbmc.LOGNOTICE
WARNING = xbmc.LOGWARNING
DEBUG = xbmc.LOGDEBUG
ERROR = xbmc.LOGERROR

DIALOG = xbmcgui.Dialog()

COUNTRY_CODE = ADDON.getSettingString('country_code')
DEFAULT_LANGUAGE = ADDON.getSettingString('language_code')
FALLBACK_LANGUAGE = 'en'

CACHE = simplecache.SimpleCache()
CACHE.enable_mem_cache = False
CACHE_ENABLED = ADDON.getSettingBool('cache_enabled')
CACHE_PREFIX = ADDON_ID + '_' + ADDON_VERSION + '_' + DEFAULT_LANGUAGE + COUNTRY_CODE + '_'

########################

def log(txt,loglevel=DEBUG,json=False,force=False):
    if force:
        loglevel = NOTICE

    if json:
        txt = json_prettyprint(txt)

    if not PYTHON3:
        if isinstance(txt, str):
            txt = txt.decode('utf-8')

    message = u'[ %s ] %s' % (ADDON_ID,txt)

    if not PYTHON3:
        xbmc.log(msg=message.encode('utf-8'), level=loglevel)
    else:
        xbmc.log(msg=message, level=loglevel)


def get_cache(key):
    if CACHE_ENABLED:
        return CACHE.get(CACHE_PREFIX + key)


def write_cache(key,data,cache_time=336):
    if data:
        CACHE.set(CACHE_PREFIX + key,data,expiration=datetime.timedelta(hours=cache_time))


def format_currency(integer):
    try:
        integer = int(integer)
        if integer < 1:
            raise Exception

        return '{:,.0f}'.format(integer)

    except Exception:
        return ''


def sort_dict(items,key,reverse=False):
    ''' Dummy date to always add planned or rumored items at the end of the list
        if no release date is available yet.
    '''
    for item in items:
        if not item.get(key):
            if not reverse:
                item[key] = '2999-01-01'
            else:
                item[key] = '1900-01-01'

    return sorted(items,key=operator.itemgetter(key),reverse=reverse)


def remove_quotes(label):
    if not label:
        return ''

    if label.startswith("'") and label.endswith("'") and len(label) > 2:
        label = label[1:-1]
        if label.startswith('"') and label.endswith('"') and len(label) > 2:
            label = label[1:-1]

    return label


def get_date(date_time):
    date_time_obj = datetime.datetime.strptime(date_time, '%Y-%m-%d %H:%M:%S')
    date_obj = date_time_obj.date()

    return date_obj


def execute(cmd):
    xbmc.executebuiltin(cmd)


def condition(condition):
    return xbmc.getCondVisibility(condition)


def busydialog(close=False):
    if not close and not condition('Window.IsVisible(busydialognocancel)'):
        execute('ActivateWindow(busydialognocancel)')
    elif close:
        execute('Dialog.Close(busydialognocancel)')


def textviewer(params):
    DIALOG.textviewer(remove_quotes(params.get('header', '')), remove_quotes(params.get('message', '')))


def winprop(key, value=None, clear=False, window_id=10000):
    window = xbmcgui.Window(window_id)

    if clear:
        window.clearProperty(key.replace('.json', '').replace('.bool', ''))

    elif value is not None:

        if key.endswith('.json'):
            key = key.replace('.json', '')
            value = json.dumps(value)

        elif key.endswith('.bool'):
            key = key.replace('.bool', '')
            value = 'true' if value else 'false'

        window.setProperty(key, value)

    else:
        result = window.getProperty(key.replace('.json', '').replace('.bool', ''))

        if result:
            if key.endswith('.json'):
                result = json.loads(result)
            elif key.endswith('.bool'):
                result = result in ('true', '1')

        return result


def date_format(value,date='short',scheme='YYYY-MM-DD'):
    try:
        date_time = arrow.get(value, scheme)
        value = date_time.strftime(xbmc.getRegion('date%s' % date))
    except Exception as error:
        log(error + ' ---> ' + str(value), WARNING)

    return value


def date_delta(date):
    date = arrow.get(date, 'YYYY-MM-DD').date()
    return date - datetime.date.today()


def date_weekday(date):
    try:
        weekdays = (xbmc.getLocalizedString(11), xbmc.getLocalizedString(12), xbmc.getLocalizedString(13), xbmc.getLocalizedString(14), xbmc.getLocalizedString(15), xbmc.getLocalizedString(16), xbmc.getLocalizedString(17))
        date = arrow.get(date, 'YYYY-MM-DD').date()
        weekday = date.weekday()
        return weekdays[weekday], weekday

    except Exception:
        return


def time_format(value):
    try:
        utc = arrow.get(value)
        utc_offset = time.timezone / -(60*60)
        local = utc.shift(hours=utc_offset)
        format = xbmc.getRegion('time').replace('%I%I', '%I').replace('%H%H', '%H').replace(':%S', '')

        if format.startswith('%I'):
            ampm = 'AM' if utc.hour < 12 else 'PM'
            return local.strftime(format) + ' ' + ampm

        else:
            return local.strftime(format)

    except Exception as error:
        log(error + ' ---> ' + str(value), WARNING)
        return ''


def get_bool(value,string='true'):
    try:
        if value.lower() == string:
            return True
        raise Exception

    except Exception:
        return False


def get_joined_items(item):
    if len(item) > 0:
        item = ' / '.join(item)
    else:
        item = ''
    return item


def get_first_item(item):
    if len(item) > 0:
        item = item[0]
    else:
        item = ''

    return item


def json_call(method,properties=None,sort=None,query_filter=None,limit=None,params=None,item=None,options=None,limits=None):
    json_string = {'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': {}}

    if properties is not None:
        json_string['params']['properties'] = properties

    if limit is not None:
        json_string['params']['limits'] = {'start': 0, 'end': int(limit)}

    if sort is not None:
        json_string['params']['sort'] = sort

    if query_filter is not None:
        json_string['params']['filter'] = query_filter

    if options is not None:
        json_string['params']['options'] = options

    if limits is not None:
        json_string['params']['limits'] = limits

    if item is not None:
        json_string['params']['item'] = item

    if params is not None:
        json_string['params'].update(params)

    json_string = json.dumps(json_string)

    result = xbmc.executeJSONRPC(json_string)

    ''' Python 2 compatibility
    '''
    try:
        result = unicode(result, 'utf-8', errors='ignore')
    except NameError:
        pass

    return json.loads(result)


def set_plugincontent(content=None,category=None):
    if category:
        xbmcplugin.setPluginCategory(int(sys.argv[1]), category)
    if content:
        xbmcplugin.setContent(int(sys.argv[1]), content)


def json_prettyprint(string):
    return json.dumps(string, sort_keys=True, indent=4, separators=(',', ': '))


def urljoin(*args):
    ''' Joins given arguments into an url. Trailing but not leading slashes are
        stripped for each argument.
    '''
    arglist = [arg for arg in args if arg is not None]
    return '/'.join(map(lambda x: str(x).rstrip('/'), arglist))


def md5hash(value):
    if not PYTHON3:
        return hashlib.md5(str(value)).hexdigest()

    value = str(value).encode()
    return hashlib.md5(value).hexdigest()