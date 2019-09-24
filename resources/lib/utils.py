#!/usr/bin/python
# coding: utf-8

########################

import json
import sys
import xbmc
import xbmcgui
import requests
import datetime

''' Python 2<->3 compatibility
'''
try:
    from urllib import urlencode
except ImportError:
    from urllib.parse import urlencode

from resources.lib.helper import *

########################

API_KEY = ADDON.getSettingString('tmdb_api_key')
API_URL = 'https://api.themoviedb.org/3/'
IMAGEPATH = 'https://image.tmdb.org/t/p/original'

OMDB_API_KEY = ADDON.getSettingString('omdb_api_key')
OMDB_URL = 'http://www.omdbapi.com/'

########################

def get_local_media():
    local_media = get_cache('local_items')

    if not local_media:
        local_media = {}
        local_media['shows'] = query_local_media('tvshow',
                                                get='VideoLibrary.GetTVShows',
                                                properties=['title', 'originaltitle', 'year', 'playcount', 'episode', 'watchedepisodes']
                                                )
        local_media['movies'] = query_local_media('movie',
                                                get='VideoLibrary.GetMovies',
                                                properties=['title', 'originaltitle', 'year', 'imdbnumber', 'playcount', 'file']
                                                )

        write_cache('local_items',local_media,1)

    return local_media


def query_local_media(dbtype,get,properties):
    items = json_call(get,properties,sort={'order': 'descending', 'method': 'year'})

    try:
        items = items['result']['%ss' % dbtype]
    except Exception:
        return

    local_items = []
    for item in items:
        local_items.append({'title': item.get('title',''),
                            'originaltitle': item.get('originaltitle',''),
                            'imdbnumber': item.get('imdbnumber',''),
                            'year': item.get('year',''),
                            'dbid': item.get('%sid' % dbtype,''),
                            'playcount': item.get('playcount',''),
                            'episodes': item.get('episode',''),
                            'watchedepisodes': item.get('watchedepisodes',''),
                            'file': item.get('file','')}
                            )

    return local_items


def omdb_call(imdbnumber=None,title=None,year=None,content_type=None):
    omdb = {}

    if imdbnumber:
        url = '%s?i=%s&apikey=%s' % (OMDB_URL,imdbnumber,OMDB_API_KEY)
    elif title and year and content_type:
        url = '%s?t=%s&year=%s&type=%s&apikey=%s' % (OMDB_URL,title,year,content_type,OMDB_API_KEY)
    else:
        return omdb

    omdb_cache = get_cache(url)

    if omdb_cache:
        return omdb_cache

    else:
        try:
            request = requests.get(url)
            result = request.json()

            omdb['awards'] = result.get('Awards')
            omdb['imdbRating'] = result.get('imdbRating')
            omdb['imdbVotes'] = result.get('imdbVotes')
            omdb['DVD'] = date_format(result.get('DVD'))

            delete_keys = [key for key,value in omdb.items() if value == 'N/A' or value == 'NA']
            for key in delete_keys:
                del omdb[key]

            for rating in result['Ratings']:
                if rating['Source'] == 'Rotten Tomatoes':
                    omdb['rotten'] = rating['Value'][:-1]
                elif rating['Source'] == 'Metacritic':
                    omdb['metacritic'] = rating['Value'][:-4]

        except Exception as error:
            log('OMDB Error: %s' % error)
            pass

        else:
            write_cache(url,omdb)

        return omdb


def omdb_properties(list_item,imdbnumber):
    if OMDB_API_KEY and imdbnumber:
        omdb = omdb_call(imdbnumber)
        if omdb:
            list_item.setProperty('rating.metacritic', omdb.get('metacritic',''))
            list_item.setProperty('rating.rotten', omdb.get('rotten',''))
            list_item.setProperty('rating.imdb', omdb.get('imdbRating',''))
            list_item.setProperty('votes.imdb', omdb.get('imdbVotes',''))
            list_item.setProperty('awards', omdb.get('awards',''))
            list_item.setProperty('release', omdb.get('DVD',''))


def tmdb_call(request_url,error_check=False,error=ADDON.getLocalizedString(32019)):
    try:
        for i in range(1,10):
            request = requests.get(request_url)
            if not str(request.status_code).startswith('5'):
                break
            log('TMDb server error: Code ' + str(request.status_code))
            xbmc.sleep(500)

        if request.status_code == 401:
            error = ADDON.getLocalizedString(32022)
            raise Exception

        elif request.status_code == 404:
            raise Exception

        elif request.status_code != requests.codes.ok:
            error = 'Code ' + str(request.status_code)
            raise Exception

        result = request.json()

        if error_check:
            if len(result) == 0: raise Exception
            if 'results' in result and len(result['results']) == 0: raise Exception

        return result

    except Exception:
        tmdb_error(error)


def tmdb_query(action,call=None,get=None,season=None,season_get=None,params=None,use_language=True,language=DEFAULT_LANGUAGE,error_check=False):
    args = {}
    args['api_key'] = API_KEY

    if use_language:
        args['language'] = language

    if params:
        args.update(params)

    call = '/' + str(call) if call else ''
    get = '/' + get if get else ''
    season = '/' + str(season) if season else ''
    season_get = '/' + season_get if season_get else ''

    url = API_URL + action + call + get + season + season_get
    url = '{0}?{1}'.format(url, urlencode(args))

    return tmdb_call(url,error_check)


def tmdb_search(call,query,year=None,include_adult='false'):
    if call == 'person':
        params = {'query': query, 'include_adult': include_adult}

    elif call == 'movie':
        params = {'query': query, 'year': year, 'include_adult': include_adult}

    elif call == 'tv':
        params = {'query': query, 'year': year}

    else:
        return ''

    result = tmdb_query(action='search',
                        call=call,
                        params=params,
                        error_check=True
                        )

    try:
        return result['results']
    except TypeError:
        return ''


def tmdb_find(call,external_id):
    if external_id.startswith('tt'):
        external_source = 'imdb_id'
    else:
        external_source = 'tvdb_id'

    result = tmdb_query(action='find',
                        call=str(external_id),
                        params={'external_source': external_source},
                        use_language=False
                        )

    if call == 'movie':
        result = result['movie_results']
    else:
        result = result['tv_results']

    if not result:
        tmdb_error(ADDON.getLocalizedString(32019))

    return result

def tmdb_select_dialog(list,call):
    indexlist = []
    selectionlist = []

    if call == 'person':
        default_img = 'DefaultActor.png'
        img = 'profile_path'
        label = 'name'
        label2 = ''

    elif call == 'movie':
        default_img = 'DefaultVideo.png'
        img = 'poster_path'
        label = 'title'
        label2 = 'tmdb_get_year(item.get("release_date",""))'

    elif call == 'tv':
        default_img = 'DefaultVideo.png'
        img = 'poster_path'
        label = 'name'
        label2 = 'first_air_date'
        label2 = 'tmdb_get_year(item.get("first_air_date",""))'

    else:
        return

    index = 0
    for item in list:
        icon = IMAGEPATH + item[img] if item[img] is not None else ''
        list_item = xbmcgui.ListItem(item[label])
        list_item.setArt({'icon': default_img,'thumb': icon})

        try:
            list_item.setLabel2(str(eval(label2)))
        except Exception:
            pass

        selectionlist.append(list_item)
        indexlist.append(index)
        index += 1

    busydialog(close=True)

    selected = DIALOG.select(xbmc.getLocalizedString(424), selectionlist, useDetails=True)

    if selected == -1:
        return -1

    busydialog()

    return indexlist[selected]


def tmdb_select_dialog_small(list):
    indexlist = []
    selectionlist = []

    index = 0
    for item in list:
        list_item = xbmcgui.ListItem(item)
        selectionlist.append(list_item)
        indexlist.append(index)
        index += 1

    busydialog(close=True)

    selected = DIALOG.select(xbmc.getLocalizedString(424), selectionlist, useDetails=False)

    if selected == -1:
        return -1

    busydialog()

    return indexlist[selected]


def tmdb_calc_age(birthday,deathday=None):
    if deathday is not None:
        ref_day = deathday.split("-")
    elif birthday:
        date = datetime.date.today()
        ref_day = [date.year, date.month, date.day]
    else:
        return ''

    born = birthday.split('-')
    age = int(ref_day[0]) - int(born[0])

    if len(born) > 1:
        diff_months = int(ref_day[1]) - int(born[1])
        diff_days = int(ref_day[2]) - int(born[2])

        if diff_months < 0 or (diff_months == 0 and diff_days < 0):
            age -= 1

    return age


def tmdb_error(message=ADDON.getLocalizedString(32019)):
    busydialog(close=True)
    DIALOG.ok(ADDON.getLocalizedString(32000),message)


def tmdb_studios(list_item,item,key):
    if key == 'production':
        key_name = 'production_companies'
        prop_name = 'studio'
    elif key == 'network':
        key_name = 'networks'
        prop_name = 'network'
    else:
        return

    i = 0
    for studio in item[key_name]:
        icon = IMAGEPATH + studio['logo_path'] if studio['logo_path'] is not None else ''
        if icon:
            list_item.setProperty(prop_name + '.' + str(i), studio['name'])
            list_item.setProperty(prop_name + '.icon.' + str(i), icon)
            i += 1


def tmdb_check_localdb(local_items,title,originaltitle,year,imdbnumber=False):
    found_local = False
    local = {'dbid': -1, 'playcount': 0, 'watchedepisodes': '', 'episodes': '', 'unwatchedepisodes': '', 'file': ''}

    if local_items:
        for item in local_items:
            dbid = item['dbid']
            playcount = item['playcount']
            episodes = item.get('episodes','')
            watchedepisodes = item.get('watchedepisodes','')
            file = item.get('file','')

            if imdbnumber and item['imdbnumber'] == imdbnumber:
                found_local = True
                break

            try:
                tmdb_year = int(tmdb_get_year(year))
                item_year = int(item['year'])

                if item_year == tmdb_year:
                    if item['originaltitle'] == originaltitle or item['title'] == originaltitle or item['title'] == title:
                        found_local = True
                        break
                elif tmdb_year in [item_year-2,item_year-1,item_year+1,item_year+2]:
                    if item['title'] == title and item['originaltitle'] == originaltitle:
                        found_local = True
                        break

            except ValueError:
                pass

    if found_local:
        local['dbid'] = dbid
        local['file'] = file
        local['playcount'] = playcount
        local['episodes'] = episodes
        local['watchedepisodes'] = watchedepisodes
        local['unwatchedepisodes'] = episodes - watchedepisodes if episodes else ''

    return local


def tmdb_handle_person(item):
    if item.get('gender') == 2:
        gender = 'male'
    elif item.get('gender') == 1:
        gender = 'female'
    else:
        gender = ''

    icon = IMAGEPATH + item['profile_path'] if item['profile_path'] is not None else ''
    list_item = xbmcgui.ListItem(label=item['name'])
    list_item.setProperty('birthday', date_format(item.get('birthday')))
    list_item.setProperty('deathday', date_format(item.get('deathday')))
    list_item.setProperty('age', str(tmdb_calc_age(item.get('birthday',''),item.get('deathday',None))))
    list_item.setProperty('biography', tmdb_fallback_info(item,'biography'))
    list_item.setProperty('place_of_birth', item.get('place_of_birth',''))
    list_item.setProperty('known_for_department', item.get('known_for_department',''))
    list_item.setProperty('gender', gender)
    list_item.setProperty('id', str(item.get('id','')))
    list_item.setProperty('call', 'person')
    list_item.setArt({'icon': 'DefaultActor.png','thumb': icon})

    return list_item


def tmdb_handle_movie(item,local_items=None,full_info=False):
    icon = IMAGEPATH + item['poster_path'] if item['poster_path'] is not None else ''
    backdrop = IMAGEPATH + item['backdrop_path'] if item['backdrop_path'] is not None else ''

    label = item['title'] or item['original_title']
    originaltitle = item.get('original_title','')
    imdbnumber = item.get('imdb_id','')
    collection = item.get('belongs_to_collection','')
    premiered = item.get('release_date')
    duration = item.get('runtime') * 60 if item.get('runtime',0) > 0 else ''
    local_info = tmdb_check_localdb(local_items,label,originaltitle,premiered,imdbnumber)
    dbid = local_info['dbid']
    is_local = True if dbid > 0 else False

    list_item = xbmcgui.ListItem(label=label)
    list_item.setInfo('video', {'title': label,
                                'originaltitle': originaltitle,
                                'dbid': dbid,
                                'playcount': local_info['playcount'],
                                'imdbnumber': imdbnumber,
                                'rating': item.get('vote_average',''),
                                'votes': item.get('vote_count',''),
                                'premiered': premiered,
                                'mpaa': tmdb_get_cert(item),
                                'tagline': item.get('tagline',''),
                                'duration': duration,
                                'status': item.get('status',''),
                                'plot': tmdb_fallback_info(item,'overview'),
                                'director': tmdb_join_items_by(item.get('crew',''),key_is='job',value_is='Director'),
                                'writer': tmdb_join_items_by(item.get('crew',''),key_is='department',value_is='Writing'),
                                'country': tmdb_join_items(item.get('production_countries','')),
                                'genre': tmdb_join_items(item.get('genres','')),
                                'studio': tmdb_join_items(item.get('production_companies','')),
                                'mediatype': 'movie'}
                                 )
    list_item.setArt({'icon': 'DefaultVideo.png','thumb': icon,'fanart': backdrop})
    list_item.setProperty('role', item.get('character',''))
    list_item.setProperty('budget', format_currency(item.get('budget')))
    list_item.setProperty('revenue', format_currency(item.get('revenue')))
    list_item.setProperty('homepage', item.get('homepage',''))
    list_item.setProperty('file', local_info.get('file',''))
    list_item.setProperty('id', str(item.get('id','')))
    list_item.setProperty('call', 'movie')

    if full_info:
        tmdb_studios(list_item,item,'production')
        omdb_properties(list_item,imdbnumber)

        if collection:
            list_item.setProperty('collection', collection['name'])
            list_item.setProperty('collection_id', str(collection['id']))
            list_item.setProperty('collection_poster', IMAGEPATH + collection['poster_path'] if collection['poster_path'] is not None else '')
            list_item.setProperty('collection_fanart', IMAGEPATH + collection['backdrop_path'] if collection['backdrop_path'] is not None else '')

    return list_item, is_local


def tmdb_handle_tvshow(item,local_items=None,full_info=False):
    icon = IMAGEPATH + item['poster_path'] if item['poster_path'] is not None else ''
    backdrop = IMAGEPATH + item['backdrop_path'] if item['backdrop_path'] is not None else ''

    label = item['name'] or item['original_name']
    originaltitle = item.get('original_name','')
    premiered = item.get('first_air_date')
    imdbnumber = item['external_ids']['imdb_id'] if item.get('external_ids') else ''
    next_episode = item.get('next_episode_to_air','')
    last_episode = item.get('last_episode_to_air','')
    tvdb_id = item['external_ids']['tvdb_id'] if item.get('external_ids') else ''
    local_info = tmdb_check_localdb(local_items,label,originaltitle,premiered,tvdb_id)
    dbid = local_info['dbid']
    is_local = True if dbid > 0 else False

    list_item = xbmcgui.ListItem(label=label)
    list_item.setInfo('video', {'title': label,
                                'originaltitle': originaltitle,
                                'dbid': dbid,
                                'playcount': local_info['playcount'],
                                'status': item.get('status',''),
                                'rating': item.get('vote_average',''),
                                'votes': item.get('vote_count',''),
                                'imdbnumber': imdbnumber,
                                'premiered': premiered,
                                'mpaa': tmdb_get_cert(item),
                                'season': str(item.get('number_of_seasons','')),
                                'episode': str(item.get('number_of_episodes','')),
                                'plot': tmdb_fallback_info(item,'overview'),
                                'director': tmdb_join_items(item.get('created_by','')),
                                'genre': tmdb_join_items(item.get('genres','')),
                                'studio': tmdb_join_items(item.get('networks','')),
                                'mediatype': 'tvshow'}
                                )
    list_item.setArt({'icon': 'DefaultVideo.png','thumb': icon,'fanart': backdrop})
    list_item.setProperty('TotalEpisodes', str(local_info['episodes']))
    list_item.setProperty('WatchedEpisodes', str(local_info['watchedepisodes']))
    list_item.setProperty('UnWatchedEpisodes', str(local_info['unwatchedepisodes']))
    list_item.setProperty('homepage', item.get('homepage',''))
    list_item.setProperty('role', item.get('character',''))
    list_item.setProperty('tvdb_id', str(tvdb_id))
    list_item.setProperty('id', str(item.get('id','')))
    list_item.setProperty('call', 'tv')

    if full_info:
        tmdb_studios(list_item,item,'production')
        tmdb_studios(list_item,item,'network')
        omdb_properties(list_item,imdbnumber)

        if last_episode:
            list_item.setProperty('lastepisode', last_episode.get('name'))
            list_item.setProperty('lastepisode_plot', last_episode.get('overview'))
            list_item.setProperty('lastepisode_number', str(last_episode.get('episode_number')))
            list_item.setProperty('lastepisode_season', str(last_episode.get('season_number')))
            list_item.setProperty('lastepisode_date', date_format(last_episode.get('air_date')))
            list_item.setProperty('lastepisode_thumb', IMAGEPATH + last_episode['still_path'] if last_episode['still_path'] is not None else '')

        if next_episode:
            list_item.setProperty('nextepisode', next_episode.get('name'))
            list_item.setProperty('nextepisode_plot', next_episode.get('overview'))
            list_item.setProperty('nextepisode_number', str(next_episode.get('episode_number')))
            list_item.setProperty('nextepisode_season', str(next_episode.get('season_number')))
            list_item.setProperty('nextepisode_date', date_format(next_episode.get('air_date')))
            list_item.setProperty('nextepisode_thumb', IMAGEPATH + next_episode['still_path'] if next_episode['still_path'] is not None else '')

    return list_item, is_local


def tmdb_handle_season(item,tvshow_details,full_info=False):
    backdrop = IMAGEPATH + tvshow_details['backdrop_path'] if tvshow_details['backdrop_path'] is not None else ''
    icon = IMAGEPATH + item['poster_path'] if item['poster_path'] is not None else ''
    if not icon and tvshow_details['poster_path']:
        icon = IMAGEPATH + tvshow_details['poster_path']

    imdbnumber = tvshow_details['external_ids']['imdb_id'] if tvshow_details.get('external_ids') else ''
    season_nr = str(item.get('season_number',''))
    tvshow_label = tvshow_details['name'] or tvshow_details['original_name']

    episodes_count = 0
    for episode in item.get('episodes',''):
        episodes_count += 1

    list_item = xbmcgui.ListItem(label=tvshow_label)
    list_item.setInfo('video', {'title': item['name'],
                                'tvshowtitle': tvshow_label,
                                'premiered': item.get('air_date',''),
                                'episode': episodes_count,
                                'season': season_nr,
                                'plot': item.get('overview',''),
                                'genre': tmdb_join_items(tvshow_details.get('genres','')),
                                'rating': tvshow_details.get('vote_average',''),
                                'votes': tvshow_details.get('vote_count',''),
                                'mpaa': tmdb_get_cert(tvshow_details),
                                'mediatype': 'season'}
                                )
    list_item.setArt({'icon': 'DefaultVideo.png','thumb': icon, 'fanart': backdrop})
    list_item.setProperty('TotalEpisodes', str(episodes_count))
    list_item.setProperty('id', str(tvshow_details['id']))
    list_item.setProperty('call', 'tv')
    list_item.setProperty('call_season', season_nr)

    if full_info:
        tmdb_studios(list_item,tvshow_details,'production')
        tmdb_studios(list_item,tvshow_details,'network')
        omdb_properties(list_item,imdbnumber)

    return list_item


def tmdb_fallback_info(item,key):
    key_value = item.get(key)

    if key_value:
        return key_value.replace('&amp;', '&')

    try:
        for translation in item['translations']['translations']:
            if translation.get('iso_639_1') == FALLBACK_LANGUAGE:
                if translation['data'][key]:
                    key_value = translation['data'][key]
                    return key_value.replace('&amp;', '&')

    except Exception:
        pass

    return ''


def tmdb_handle_images(item):
    icon = IMAGEPATH + item['file_path'] if item['file_path'] is not None else ''
    list_item = xbmcgui.ListItem(label=str(item['width']) + 'x' + str(item['height']) + 'px')
    list_item.setArt({'icon': 'DefaultPicture.png','thumb': icon})
    list_item.setProperty('call', 'image')

    return list_item


def tmdb_handle_credits(item):
    icon = IMAGEPATH + item['profile_path'] if item['profile_path'] is not None else ''
    list_item = xbmcgui.ListItem(label=item['name'])
    list_item.setLabel2(item['label2'])
    list_item.setArt({'icon': 'DefaultActor.png','thumb': icon})
    list_item.setProperty('id', str(item.get('id','')))
    list_item.setProperty('call', 'person')

    return list_item


def tmdb_handle_yt_videos(item):
    icon = 'https://img.youtube.com/vi/%s/0.jpg' % str(item['key'])
    list_item = xbmcgui.ListItem(label=item['name'])
    list_item.setLabel2(item.get('type',''))
    list_item.setArt({'icon': 'DefaultVideo.png','thumb': icon})
    list_item.setProperty('ytid', str(item['key']))
    list_item.setProperty('call', 'youtube')

    return list_item


def tmdb_join_items_by(item,key_is,value_is,key='name'):
    values = []
    for value in item:
        if value[key_is] == value_is:
            values.append(value[key])

    return get_joined_items(values)


def tmdb_join_items(item,key='name'):
    values = []
    for value in item:
        values.append(value[key])

    return get_joined_items(values)


def tmdb_get_year(item):
    try:
        year = str(item)[:-6]
        return year
    except Exception:
        return ''


def tmdb_get_cert(item):
    try:
        if COUNTRY_CODE == 'DE':
            prefix = 'FSK '
        else:
            prefix = ''

        if item.get('content_ratings'):
            for cert in item['content_ratings']['results']:
                if cert['iso_3166_1'] == COUNTRY_CODE:
                    mpaa = prefix + cert['rating']
                    return mpaa

        elif item.get('release_dates'):
            for cert in item['release_dates']['results']:
                if cert['iso_3166_1'] == COUNTRY_CODE:
                    mpaa = prefix + cert['release_dates'][0]['certification']
                    return mpaa

        else:
            return ''

    except Exception:
        return ''