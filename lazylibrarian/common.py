#  This file is part of Lazylibrarian.
#
#  Lazylibrarian is free software':'you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  Lazylibrarian is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with Lazylibrarian.  If not, see <http://www.gnu.org/licenses/>.

import os
import platform
import shutil
import time
import datetime
import traceback
import threading
import urllib2

import lazylibrarian
from lazylibrarian import logger, database
from lazylibrarian.formatter import plural, next_run, is_valid_booktype, datecompare, getList

USER_AGENT = 'LazyLibrarian' + ' (' + platform.system() + ' ' + platform.release() + ')'
# Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/52.0.2743.116 Safari/537.36

# Notification Types
NOTIFY_SNATCH = 1
NOTIFY_DOWNLOAD = 2

notifyStrings = {NOTIFY_SNATCH: "Started Download", NOTIFY_DOWNLOAD: "Added to Library"}


def formatAuthorName(author):
    """ get authorame in a consistent format """

    if "," in author:
        postfix = getList(lazylibrarian.CONFIG['NAME_POSTFIX'])
        words = author.split(',')
        if len(words) == 2:
            # Need to handle names like "L. E. Modesitt, Jr." or "J. Springmann, Phd"
            # use an exceptions list for now, there might be a better way...
            if words[1].strip().strip('.').strip('_').lower() in postfix:
                surname = words[1].strip()
                forename = words[0].strip()
            else:
                # guess its "surname, forename" or "surname, initial(s)" so swap them round
                forename = words[1].strip()
                surname = words[0].strip()
            if author != forename + ' ' + surname:
                logger.debug('Formatted authorname [%s] to [%s %s]' % (author, forename, surname))
                author = forename + ' ' + surname
    # reformat any initials, we want to end up with L.E. Modesitt Jr
    if author[1] in '. ':
        surname = author
        forename = ''
        while surname[1] in '. ':
            forename = forename + surname[0] + '.'
            surname = surname[2:].strip()
        if author != forename + ' ' + surname:
            logger.debug('Stripped authorname [%s] to [%s %s]' % (author, forename, surname))
            author = forename + ' ' + surname

    return ' '.join(author.split())  # ensure no extra whitespace


def internet():
  """
  Check for an active internet connection
  Return True or False
  """
  try:
      _ = urllib2.urlopen("http://www.google.com", timeout=5)
      return True
  except Exception:  # as e:
      #logger.debug(str(e)
      return False


def setperm(file_or_dir):
    """
    Force newly created directories to rwxr-xr-x and files to rw-r--r--
    """
    if not file_or_dir:
        return

    if os.path.isdir(file_or_dir):
        perm = lazylibrarian.CONFIG['DIR_PERM']
    elif os.path.isfile(file_or_dir):
        perm = lazylibrarian.CONFIG['FILE_PERM']
    else:
        return False
    try:
        os.chmod(file_or_dir, perm)
        return True
    except:
        #  logger.debug("Failed to set permission %s for %s" % (perm, file_or_dir))
        return False


def any_file(search_dir=None, extn=None):
    # find a file with specified extension in a directory, any will do
    # return full pathname of file, or empty string if none found
    if search_dir is None or extn is None:
        return ""
    # ensure directory is unicode so we get unicode results from listdir
    if isinstance(search_dir, str):
        search_dir = search_dir.decode(lazylibrarian.SYS_ENCODING)
    if extn and search_dir and os.path.isdir(search_dir):
        for fname in os.listdir(search_dir):
            if fname.endswith(extn):
                return os.path.join(search_dir, fname)
    return ""


def opf_file(search_dir=None):
    return any_file(search_dir, '.opf')


def bts_file(search_dir=None):
    return any_file(search_dir, '.bts')


def csv_file(search_dir=None):
    return any_file(search_dir, '.csv')


def book_file(search_dir=None, booktype=None):
    # find a book/mag file in this directory, any book will do
    # return full pathname of book/mag, or empty string if none found
    if search_dir is None or booktype is None:
        return ""
    # ensure directory is unicode so we get unicode results from listdir
    if isinstance(search_dir, str):
        search_dir = search_dir.decode(lazylibrarian.SYS_ENCODING)
    if search_dir and os.path.isdir(search_dir):
        for fname in os.listdir(search_dir):
            if is_valid_booktype(fname, booktype=booktype):
                return os.path.join(search_dir, fname)
    return ""


def scheduleJob(action='Start', target=None):
    """ Start or stop or restart a cron job by name eg
        target=search_magazines, target=processDir, target=search_tor_book """
    if target is None:
        return

    if action == 'Stop' or action == 'Restart':
        for job in lazylibrarian.SCHED.get_jobs():
            if target in str(job):
                lazylibrarian.SCHED.unschedule_job(job)
                logger.debug("Stop %s job" % target)

    if action == 'Start' or action == 'Restart':
        for job in lazylibrarian.SCHED.get_jobs():
            if target in str(job):
                logger.debug("%s %s job, already scheduled" % (action, target))
                return  # return if already running, if not, start a new one
        if 'processDir' in target and int(lazylibrarian.CONFIG['SCAN_INTERVAL']):
            lazylibrarian.SCHED.add_interval_job(
                lazylibrarian.postprocess.cron_processDir,
                minutes=int(lazylibrarian.CONFIG['SCAN_INTERVAL']))
            logger.debug("%s %s job in %s minutes" % (action, target, lazylibrarian.CONFIG['SCAN_INTERVAL']))
        elif 'search_magazines' in target and int(lazylibrarian.CONFIG['SEARCH_INTERVAL']):
            if lazylibrarian.USE_TOR() or lazylibrarian.USE_NZB() or lazylibrarian.USE_RSS():
                lazylibrarian.SCHED.add_interval_job(
                    lazylibrarian.searchmag.cron_search_magazines,
                    minutes=int(lazylibrarian.CONFIG['SEARCH_INTERVAL']))
                logger.debug("%s %s job in %s minutes" % (action, target, lazylibrarian.CONFIG['SEARCH_INTERVAL']))
        elif 'search_nzb_book' in target and int(lazylibrarian.CONFIG['SEARCH_INTERVAL']):
            if lazylibrarian.USE_NZB():
                lazylibrarian.SCHED.add_interval_job(
                    lazylibrarian.searchnzb.cron_search_nzb_book,
                    minutes=int(lazylibrarian.CONFIG['SEARCH_INTERVAL']))
                logger.debug("%s %s job in %s minutes" % (action, target, lazylibrarian.CONFIG['SEARCH_INTERVAL']))
        elif 'search_tor_book' in target and int(lazylibrarian.CONFIG['SEARCH_INTERVAL']):
            if lazylibrarian.USE_TOR():
                lazylibrarian.SCHED.add_interval_job(
                    lazylibrarian.searchtorrents.cron_search_tor_book,
                    minutes=int(lazylibrarian.CONFIG['SEARCH_INTERVAL']))
                logger.debug("%s %s job in %s minutes" % (action, target, lazylibrarian.CONFIG['SEARCH_INTERVAL']))
        elif 'search_rss_book' in target and int(lazylibrarian.CONFIG['SEARCHRSS_INTERVAL']):
            if lazylibrarian.USE_RSS():
                lazylibrarian.SCHED.add_interval_job(
                    lazylibrarian.searchrss.search_rss_book,
                    minutes=int(lazylibrarian.CONFIG['SEARCHRSS_INTERVAL']))
                logger.debug("%s %s job in %s minutes" % (action, target, lazylibrarian.CONFIG['SEARCHRSS_INTERVAL']))
        elif 'checkForUpdates' in target and int(lazylibrarian.CONFIG['VERSIONCHECK_INTERVAL']):
            lazylibrarian.SCHED.add_interval_job(
                lazylibrarian.versioncheck.checkForUpdates,
                hours=int(lazylibrarian.CONFIG['VERSIONCHECK_INTERVAL']))
            logger.debug("%s %s job in %s hours" % (action, target, lazylibrarian.CONFIG['VERSIONCHECK_INTERVAL']))
        elif 'authorUpdate' in target and int(lazylibrarian.CONFIG['CACHE_AGE']):
            # Try to get all authors scanned evenly inside the cache age
            minutes = lazylibrarian.CONFIG['CACHE_AGE'] * 24 * 60
            myDB = database.DBConnection()
            authors = myDB.match(
                "select count('AuthorID') as counter from Authors where Status='Active' or Status='Loading'")
            authcount = authors['counter']
            if not authcount:
                minutes = 60
            else:
                minutes = int(minutes / authcount)
            if minutes < 10:  # set a minimum interval of 10 minutes so we don't upset goodreads/librarything api
                minutes = 10
            if minutes <= 600:  # for bigger intervals switch to hours
                lazylibrarian.SCHED.add_interval_job(authorUpdate, minutes=minutes)
                logger.debug("%s %s job in %s minutes" % (action, target, minutes))
            else:
                hours = int(minutes / 60)
                lazylibrarian.SCHED.add_interval_job(authorUpdate, hours=hours)
                logger.debug("%s %s job in %s hours" % (action, target, hours))


def authorUpdate():
    threadname = threading.currentThread().name
    if "Thread-" in threadname:
        threading.currentThread().name = "AUTHORUPDATE"

    try:
        if not internet():
            logger.warn('No internet connection')
            return

        myDB = database.DBConnection()
        author = myDB.match('SELECT AuthorID, AuthorName, DateAdded from authors WHERE Status="Active" \
                            order by DateAdded ASC')
        if author and lazylibrarian.CONFIG['CACHE_AGE']:
            dtnow = datetime.datetime.now()
            diff = datecompare(dtnow.strftime("%Y-%m-%d"), author['DateAdded'])
            if diff > lazylibrarian.CONFIG['CACHE_AGE']:
                logger.info('Starting update for %s' % author['AuthorName'])
                authorid = author['AuthorID']
                # noinspection PyUnresolvedReferences
                lazylibrarian.importer.addAuthorToDB(refresh=True, authorid=authorid)
            else:
                logger.debug('Oldest author info is %s day%s old' % (diff, plural(diff)))
    except Exception:
        logger.error('Unhandled exception in AuthorUpdate: %s' % traceback.format_exc())


def dbUpdate(refresh=False):
    try:
        myDB = database.DBConnection()
        activeauthors = myDB.select('SELECT AuthorID from authors WHERE Status="Active" \
                                    or Status="Loading" order by DateAdded ASC')
        logger.info('Starting update for %i active author%s' % (len(activeauthors), plural(len(activeauthors))))
        for author in activeauthors:
            authorid = author['AuthorID']
            # noinspection PyUnresolvedReferences
            lazylibrarian.importer.addAuthorToDB(refresh=refresh, authorid=authorid)
        logger.info('Active author update complete')
        return 'Updated %i active author%s' % (len(activeauthors), plural(len(activeauthors)))
    except Exception:
        msg = 'Unhandled exception in dbUpdate: %s' % traceback.format_exc()
        logger.error(msg)
        return msg

def restartJobs(start='Restart'):
    scheduleJob(start, 'processDir')
    scheduleJob(start, 'search_nzb_book')
    scheduleJob(start, 'search_tor_book')
    scheduleJob(start, 'search_rss_book')
    scheduleJob(start, 'search_magazines')
    scheduleJob(start, 'checkForUpdates')
    scheduleJob(start, 'authorUpdate')

def ensureRunning(jobname):
    found = False
    for job in lazylibrarian.SCHED.get_jobs():
        if jobname in str(job):
            found = True
            break
    if not found:
        scheduleJob('Start', jobname)


def checkRunningJobs():
    # make sure the relevant jobs are running
    # search jobs start when something gets marked "wanted" but are
    # not aware of any config changes that happen later, ie enable or disable providers,
    # so we check whenever config is saved
    # processdir is started when something gets marked "snatched"
    # and cancels itself once everything is processed so should be ok
    # but check anyway for completeness...

    myDB = database.DBConnection()
    snatched = myDB.match("SELECT count('Status') as counter from wanted WHERE Status = 'Snatched'")
    wanted = myDB.match("SELECT count('Status') as counter FROM books WHERE Status = 'Wanted'")
    if snatched:
        ensureRunning('processDir')
    if wanted:
        if lazylibrarian.USE_NZB():
            ensureRunning('search_nzb_book')
        if lazylibrarian.USE_TOR():
            ensureRunning('search_tor_book')
        if lazylibrarian.USE_RSS():
            ensureRunning('search_rss_book')
    else:
        scheduleJob('Stop', 'search_nzb_book')
        scheduleJob('Stop', 'search_tor_book')
        scheduleJob('Stop', 'search_rss_book')

    if lazylibrarian.USE_NZB() or lazylibrarian.USE_TOR() or lazylibrarian.USE_RSS():
        ensureRunning('search_magazines')
    else:
        scheduleJob('Stop', 'search_magazines')

    ensureRunning('authorUpdate')

def showJobs():
    result = ["Cache %i hit%s, %i miss" % (int(lazylibrarian.CACHE_HIT),
                                           plural(int(lazylibrarian.CACHE_HIT)), int(lazylibrarian.CACHE_MISS))]
    myDB = database.DBConnection()
    snatched = myDB.match("SELECT count('Status') as counter from wanted WHERE Status = 'Snatched'")
    wanted = myDB.match("SELECT count('Status') as counter FROM books WHERE Status = 'Wanted'")
    result.append("%i item%s marked as Snatched" % (snatched['counter'], plural(snatched['counter'])))
    result.append("%i item%s marked as Wanted" % (wanted['counter'], plural(wanted['counter'])))
    author = myDB.match('SELECT AuthorID, AuthorName, DateAdded from authors WHERE Status="Active" \
                                or Status="Loading" order by DateAdded ASC')
    dtnow = datetime.datetime.now()
    diff = datecompare(dtnow.strftime("%Y-%m-%d"), author['DateAdded'])
    result.append('Oldest author info is %s day%s old' % (diff, plural(diff)))
    for job in lazylibrarian.SCHED.get_jobs():
        job = str(job)
        if "search_magazines" in job:
            jobname = "Magazine search"
        elif "checkForUpdates" in job:
            jobname = "Check LazyLibrarian version"
        elif "search_tor_book" in job:
            jobname = "TOR book search"
        elif "search_nzb_book" in job:
            jobname = "NZB book search"
        elif "search_rss_book" in job:
            jobname = "RSS book search"
        elif "processDir" in job:
            jobname = "Process downloads"
        elif "authorUpdate" in job:
            jobname = "Update authors"
        else:
            jobname = job.split(' ')[0].split('.')[2]

        # jobinterval = job.split('[')[1].split(']')[0]
        jobtime = job.split('at: ')[1].split('.')[0]
        jobtime = next_run(jobtime)
        jobinfo = "%s: Next run in %s" % (jobname, jobtime)
        result.append(jobinfo)
    return result


def clearLog():
    logger.lazylibrarian_log.stopLogger()
    error = False
    if os.path.exists(lazylibrarian.CONFIG['LOGDIR']):
        try:
            shutil.rmtree(lazylibrarian.CONFIG['LOGDIR'])
            os.mkdir(lazylibrarian.CONFIG['LOGDIR'])
        except OSError as e:
            error = e.strerror
    logger.lazylibrarian_log.initLogger(loglevel=lazylibrarian.LOGLEVEL)

    if error:
        return 'Failed to clear log: %s' % error
    else:
        lazylibrarian.LOGLIST = []
        return "Log cleared, level set to [%s]- Log Directory is [%s]" % (
            lazylibrarian.LOGLEVEL, lazylibrarian.CONFIG['LOGDIR'])


def cleanCache():
    """ Remove unused files from the cache - delete if expired or unused.
        Check JSONCache  WorkCache  XMLCache  SeriesCache Author  Book
        Check covers and authorimages referenced in the database exist and change database entry if missing """

    myDB = database.DBConnection()
    result = []
    cache = os.path.join(lazylibrarian.CACHEDIR, "JSONCache")
    # ensure directory is unicode so we get unicode results from listdir
    if isinstance(cache, str):
        cache = cache.decode(lazylibrarian.SYS_ENCODING)
    cleaned = 0
    kept = 0
    if os.path.isdir(cache):
        for cached_file in os.listdir(cache):
            target = os.path.join(cache, cached_file)
            cache_modified_time = os.stat(target).st_mtime
            time_now = time.time()
            if cache_modified_time < time_now - (
                        lazylibrarian.CONFIG['CACHE_AGE'] * 24 * 60 * 60):  # expire after this many seconds
                # Cache is old, delete entry
                os.remove(target)
                cleaned += 1
            else:
                kept += 1
    msg = "Cleaned %i file%s from JSONCache, kept %i" % (cleaned, plural(cleaned), kept)
    result.append(msg)
    logger.debug(msg)

    cache = os.path.join(lazylibrarian.CACHEDIR, "XMLCache")
    # ensure directory is unicode so we get unicode results from listdir
    if isinstance(cache, str):
        cache = cache.decode(lazylibrarian.SYS_ENCODING)
    cleaned = 0
    kept = 0
    if os.path.isdir(cache):
        for cached_file in os.listdir(cache):
            target = os.path.join(cache, cached_file)
            cache_modified_time = os.stat(target).st_mtime
            time_now = time.time()
            if cache_modified_time < time_now - (
                        lazylibrarian.CONFIG['CACHE_AGE'] * 24 * 60 * 60):  # expire after this many seconds
                # Cache is old, delete entry
                os.remove(target)
                cleaned += 1
            else:
                kept += 1
    msg = "Cleaned %i file%s from XMLCache, kept %i" % (cleaned, plural(cleaned), kept)
    result.append(msg)
    logger.debug(msg)

    cache = os.path.join(lazylibrarian.CACHEDIR, "WorkCache")
    # ensure directory is unicode so we get unicode results from listdir
    if isinstance(cache, str):
        cache = cache.decode(lazylibrarian.SYS_ENCODING)
    cleaned = 0
    kept = 0
    if os.path.isdir(cache):
        for cached_file in os.listdir(cache):
            target = os.path.join(cache, cached_file)
            try:
                bookid = cached_file.split('.')[0]
            except IndexError:
                logger.error('Clean Cache: Error splitting %s' % cached_file)
                continue
            item = myDB.match('select BookID from books where BookID="%s"' % bookid)
            if not item:
                # WorkPage no longer referenced in database, delete cached_file
                os.remove(target)
                cleaned += 1
            else:
                kept += 1
    msg = "Cleaned %i file%s from WorkCache, kept %i" % (cleaned, plural(cleaned), kept)
    result.append(msg)
    logger.debug(msg)

    cache = os.path.join(lazylibrarian.CACHEDIR, "SeriesCache")
    # ensure directory is unicode so we get unicode results from listdir
    if isinstance(cache, str):
        cache = cache.decode(lazylibrarian.SYS_ENCODING)
    cleaned = 0
    kept = 0
    if os.path.isdir(cache):
        for cached_file in os.listdir(cache):
            target = os.path.join(cache, cached_file)
            try:
                seriesid = cached_file.split('.')[0]
            except IndexError:
                logger.error('Clean Cache: Error splitting %s' % cached_file)
                continue
            item = myDB.match('select SeriesID from series where SeriesID="%s"' % seriesid)
            if not item:
                # SeriesPage no longer referenced in database, delete cached_file
                os.remove(target)
                cleaned += 1
            else:
                kept += 1
    msg = "Cleaned %i file%s from SeriesCache, kept %i" % (cleaned, plural(cleaned), kept)
    result.append(msg)
    logger.debug(msg)

    cache = lazylibrarian.CACHEDIR
    cleaned = 0
    kept = 0
    cachedir = os.path.join(cache, 'author')
    if os.path.isdir(cachedir):
        for cached_file in os.listdir(cachedir):
            target = os.path.join(cachedir, cached_file)
            if os.path.isfile(target):
                try:
                    imgid = cached_file.split('.')[0].rsplit(os.sep)[-1]
                except IndexError:
                    logger.error('Clean Cache: Error splitting %s' % cached_file)
                    continue
                item = myDB.match('select AuthorID from authors where AuthorID="%s"' % imgid)
                if not item:
                    # Author Image no longer referenced in database, delete cached_file
                    os.remove(target)
                    cleaned += 1
                else:
                    kept += 1
    cachedir = os.path.join(cache, 'book')
    if os.path.isdir(cachedir):
        for cached_file in os.listdir(cachedir):
            target = os.path.join(cachedir, cached_file)
            if os.path.isfile(target):
                try:
                    imgid = cached_file.split('.')[0].rsplit(os.sep)[-1]
                except IndexError:
                    logger.error('Clean Cache: Error splitting %s' % cached_file)
                    continue
                item = myDB.match('select BookID from books where BookID="%s"' % imgid)
                if not item:
                    # Book Image no longer referenced in database, delete cached_file
                    os.remove(target)
                    cleaned += 1
                else:
                    kept += 1

    # at this point there should be no more .jpg files in the root of the cachedir
    # any that are still there are for books/authors deleted from database
    for cached_file in os.listdir(cache):
        if cached_file.endswith('.jpg'):
            os.remove(os.path.join(cache, cached_file))
            cleaned += 1
    msg = "Cleaned %i file%s from ImageCache, kept %i" % (cleaned, plural(cleaned), kept)
    result.append(msg)
    logger.debug(msg)

    # verify the cover images referenced in the database are present
    images = myDB.action('select BookImg,BookName,BookID from books')
    cachedir = os.path.join(lazylibrarian.CACHEDIR, 'book')
    cleaned = 0
    kept = 0
    for item in images:
        keep = True
        imgfile = ''
        if item['BookImg'] is None or item['BookImg'] == '':
            keep = False
        if keep and not item['BookImg'].startswith('http') and not item['BookImg'] == "images/nocover.png":
            # html uses '/' as separator, but os might not
            imgname = item['BookImg'].rsplit('/')[-1]
            imgfile = os.path.join(cachedir, imgname)
            if not os.path.isfile(imgfile):
                keep = False
        if keep:
            kept += 1
        else:
            cleaned += 1
            logger.debug('Cover missing for %s %s' % (item['BookName'], imgfile))
            myDB.action('update books set BookImg="images/nocover.png" where Bookid="%s"' % item['BookID'])

    msg = "Cleaned %i missing cover file%s, kept %i" % (cleaned, plural(cleaned), kept)
    result.append(msg)
    logger.debug(msg)

    # verify the author images referenced in the database are present
    images = myDB.action('select AuthorImg,AuthorName,AuthorID from authors')
    cachedir = os.path.join(lazylibrarian.CACHEDIR, 'author')
    cleaned = 0
    kept = 0
    for item in images:
        keep = True
        imgfile = ''
        if item['AuthorImg'] is None or item['AuthorImg'] == '':
            keep = False
        if keep and not item['AuthorImg'].startswith('http') and not item['AuthorImg'] == "images/nophoto.png":
            # html uses '/' as separator, but os might not
            imgname = item['AuthorImg'].rsplit('/')[-1]
            imgfile = os.path.join(cachedir, imgname)
            if not os.path.isfile(imgfile):
                keep = False
        if keep:
            kept += 1
        else:
            cleaned += 1
            logger.debug('Image missing for %s %s' % (item['AuthorName'], imgfile))
            myDB.action('update authors set AuthorImg="images/nophoto.png" where AuthorID="%s"' % item['AuthorID'])

    msg = "Cleaned %i missing author image%s, kept %i" % (cleaned, plural(cleaned), kept)
    result.append(msg)
    logger.debug(msg)
    return result
