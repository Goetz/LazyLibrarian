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

import Queue
import json
import os
import shutil
import threading

import lazylibrarian
from lazylibrarian import logger, database
from lazylibrarian.bookwork import setWorkPages, getBookCovers, getWorkSeries, getWorkPage, setAllBookSeries, \
    getBookCover, getAuthorImage, getAuthorImages, getSeriesMembers, getSeriesAuthors, deleteEmptySeries, \
    getBookAuthors
from lazylibrarian.cache import cache_img
from lazylibrarian.common import clearLog, cleanCache, restartJobs, showJobs, checkRunningJobs, dbUpdate, setperm, \
    formatAuthorName
from lazylibrarian.csvfile import import_CSV, export_CSV
from lazylibrarian.formatter import today
from lazylibrarian.gb import GoogleBooks
from lazylibrarian.gr import GoodReads
from lazylibrarian.importer import addAuthorToDB, addAuthorNameToDB, update_totals
from lazylibrarian.librarysync import LibraryScan
from lazylibrarian.magazinescan import magazineScan, create_covers
from lazylibrarian.manualbook import searchItem
from lazylibrarian.postprocess import processDir, processAlternate
from lazylibrarian.searchmag import search_magazines
from lazylibrarian.searchnzb import search_nzb_book
from lazylibrarian.searchrss import search_rss_book
from lazylibrarian.searchtorrents import search_tor_book

cmd_dict = {'help': 'list available commands. ' +
                    'Time consuming commands take an optional &wait parameter if you want to wait for completion, ' +
                    'otherwise they return OK straight away and run in the background',
            'showMonths': 'List installed monthnames',
            'dumpMonths': 'Save installed monthnames to file',
            'getIndex': 'list all authors',
            'getAuthor': '&id= get author by AuthorID and list their books',
            'getAuthorImage': '&id= get an image for this author',
            'setAuthorImage': '&id= &img= set a new image for this author',
            'setAuthorLock': '&id= lock author name/image/dates',
            'setAuthorUnlock': '&id= unlock author name/image/dates',
            'setBookLock': '&id= lock book details',
            'setBookUnlock': '&id= unlock book details',
            'setBookImage': '&id= &img= set a new image for this book',
            'getAuthorImages': '[&wait] get images for all authors without one',
            'getWanted': 'list wanted books',
            'getSnatched': 'list snatched books',
            'getHistory': 'list history',
            'getLogs': 'show current log',
            'clearLogs': 'clear current log',
            'getMagazines': 'list magazines',
            'getIssues': '&name= list issues of named magazine',
            'createMagCovers': '[&wait] [&refresh] create covers for magazines, optionally refresh existing ones',
            'forceMagSearch': '[&wait] search for all wanted magazines',
            'forceBookSearch': '[&wait] search for all wanted books',
            'forceProcess': 'process books/mags in download dir',
            'pauseAuthor': '&id= pause author by AuthorID',
            'resumeAuthor': '&id= resume author by AuthorID',
            'ignoreAuthor': '&id= ignore author by AuthorID',
            'unignoreAuthor': '&id= unignore author by AuthorID',
            'refreshAuthor': '&name= [&refresh] reload author (and their books) by name, optionally refresh cache',
            'forceActiveAuthorsUpdate': '[&wait] [&refresh] reload all active authors and book data, optionally refresh cache',
            'forceLibraryScan': '[&wait] rescan whole book library',
            'forceMagazineScan': '[&wait] rescan whole magazine library',
            'getVersion': 'show lazylibrarian current/git version',
            'shutdown': 'stop lazylibrarian',
            'restart': 'restart lazylibrarian',
            'update': 'update lazylibrarian',
            'findAuthor': '&name= search goodreads/googlebooks for named author',
            'findBook': '&name= search goodreads/googlebooks for named book',
            'moveBooks': '&fromname= &toname= move all books from one author to another by AuthorName',
            'moveBook': '&id= &toid= move one book to new author by BookID and AuthorID',
            'addAuthor': '&name= add author to database by name',
            'addAuthorID': '&id= add author to database by AuthorID',
            'removeAuthor': '&id= remove author from database by AuthorID',
            'addMagazine': '&name= add magazine to database by name',
            'removeMagazine': '&name= remove magazine and all of its issues from database by name',
            'queueBook': '&id= mark book as Wanted',
            'unqueueBook': '&id= mark book as Skipped',
            'readCFG': '&name=&group= read value of config variable "name" in section "group"',
            'writeCFG': '&name=&group=&value= set config variable "name" in section "group" to value',
            'loadCFG': 'reload config from file',
            'getBookCover': '&id= fetch a link to a cover from bookfolder/cache/librarything/goodreads/google for a BookID',
            'getAllBooks': 'list all books in the database',
            'getNoLang': 'list all books in the database with unknown language',
            'listIgnoredAuthors': 'list all authors in the database marked ignored',
            'listIgnoredBooks': 'list all books in the database marked ignored',
            'listIgnoredSeries': 'list all series in the database marked ignored',
            'listMissingWorkpages': 'list all books with errorpage or no workpage',
            'searchBook': '&id= [&wait] search for one book by BookID',
            'searchItem': '&item= get search results for an item (author, title, isbn)',
            'showJobs': 'show status of running jobs',
            'restartJobs': 'restart background jobs',
            'showThreads': 'show threaded processes',
            'checkRunningJobs': 'ensure all needed jobs are running',
            'vacuum': 'vacuum the database',
            'getWorkSeries': '&id= Get series from Librarything BookWork using BookID',
            'getSeriesMembers': '&id= Get list of series members from Librarything using SeriesID',
            'getSeriesAuthors': '&id= Get all authors from Librarything for a series and import them',
            'getWorkPage': '&id= Get url of Librarything BookWork using BookID',
            'getBookCovers': '[&wait] Check all books for cached cover and download one if missing',
            'getBookAuthors': '&id= Get list of authors associated with this book',
            'cleanCache': '[&wait] Clean unused and expired files from the LazyLibrarian caches',
            'deleteEmptySeries': 'Delete any book series that have no members',
            'setWorkPages': '[&wait] Set the WorkPages links in the database',
            'setAllBookSeries': '[&wait] Set the series details from book workpages',
            'importAlternate': '[&wait] [&dir=] Import books from named or alternate folder and any subfolders',
            'importCSVwishlist': '[&wait] [&dir=] Import a CSV wishlist from named or alternate directory',
            'exportCSVwishlist': '[&wait] [&dir=] Export a CSV wishlist to named or alternate directory'
            }


class Api(object):
    def __init__(self):

        self.apikey = None
        self.cmd = None
        self.id = None

        self.kwargs = None

        self.data = None

        self.callback = None

    def checkParams(self, **kwargs):

        if not lazylibrarian.CONFIG['API_ENABLED']:
            self.data = 'API not enabled'
            return
        if not lazylibrarian.CONFIG['API_KEY']:
            self.data = 'API key not generated'
            return
        if len(lazylibrarian.CONFIG['API_KEY']) != 32:
            self.data = 'API key is invalid'
            return

        if 'apikey' not in kwargs:
            self.data = 'Missing api key'
            return

        if kwargs['apikey'] != lazylibrarian.CONFIG['API_KEY']:
            self.data = 'Incorrect API key'
            return
        else:
            self.apikey = kwargs.pop('apikey')

        if 'cmd' not in kwargs:
            self.data = 'Missing parameter: cmd, try cmd=help'
            return

        if kwargs['cmd'] not in cmd_dict:
            self.data = 'Unknown command: %s, try cmd=help' % kwargs['cmd']
            return
        else:
            self.cmd = kwargs.pop('cmd')

        self.kwargs = kwargs
        self.data = 'OK'

    def fetchData(self):

        threadname = threading.currentThread().name
        if "Thread-" in threadname:
            threading.currentThread().name = "API"

        if self.data == 'OK':
            logger.info('Received API command: %s %s' % (self.cmd, self.kwargs))
            methodToCall = getattr(self, "_" + self.cmd)
            methodToCall(**self.kwargs)
            if 'callback' not in self.kwargs:
                if isinstance(self.data, basestring):
                    return self.data
                else:
                    return json.dumps(self.data)
            else:
                self.callback = self.kwargs['callback']
                self.data = json.dumps(self.data)
                self.data = self.callback + '(' + self.data + ');'
                return self.data
        else:
            return self.data

    @staticmethod
    def _dic_from_query(query):

        myDB = database.DBConnection()
        rows = myDB.select(query)

        rows_as_dic = []

        for row in rows:
            row_as_dic = dict(zip(row.keys(), row))
            rows_as_dic.append(row_as_dic)

        return rows_as_dic

    def _help(self):
        self.data = dict(cmd_dict)

    def _getHistory(self):
        self.data = self._dic_from_query(
            "SELECT * from wanted WHERE Status != 'Skipped' and Status != 'Ignored'")

    def _showThreads(self):
        self.data = [n.name for n in [t for t in threading.enumerate()]]

    def _showMonths(self):
        self.data = lazylibrarian.MONTHNAMES

    @staticmethod
    def _dumpMonths():
        json_file = os.path.join(lazylibrarian.DATADIR, 'monthnames.json')
        with open(json_file, 'w') as f:
            json.dump(lazylibrarian.MONTHNAMES, f)

    def _getWanted(self):
        self.data = self._dic_from_query(
            "SELECT * from books WHERE Status='Wanted'")

    def _vacuum(self):
        self.data = self._dic_from_query("vacuum; pragma integrity_check")

    def _getSnatched(self):
        self.data = self._dic_from_query(
            "SELECT * from books WHERE Status='Snatched'")

    def _getLogs(self):
        self.data = lazylibrarian.LOGLIST

    def _clearLogs(self):
        self.data = clearLog()

    def _getIndex(self):
        self.data = self._dic_from_query(
            'SELECT * from authors order by AuthorName COLLATE NOCASE')

    def _getNoLang(self):
        q = 'SELECT BookID,BookISBN,BookName,AuthorName from books,authors where books.AuthorID = authors.AuthorID'
        q += ' and BookLang="Unknown" or BookLang="" or BookLang is NULL'
        self.data = self._dic_from_query(q)

    def _listIgnoredSeries(self):
        q = 'SELECT SeriesID,SeriesName from series where Status="Ignored"'
        self.data = self._dic_from_query(q)

    def _listIgnoredBooks(self):
        q = 'SELECT BookID,BookName from books where Status="Ignored"'
        self.data = self._dic_from_query(q)

    def _listIgnoredAuthors(self):
        q = 'SELECT AuthorID,AuthorName from authors where Status="Ignored"'
        self.data = self._dic_from_query(q)

    def _listMissingWorkpages(self):
        # first the ones with no workpage
        q = 'SELECT BookID from books where length(WorkPage) < 4'
        res = self._dic_from_query(q)
        # now the ones with an error page
        cache = os.path.join(lazylibrarian.CACHEDIR, "WorkCache")
        # ensure directory is unicode so we get unicode results from listdir
        if os.path.isdir(cache):
            for cached_file in os.listdir(cache):
                target = os.path.join(cache, cached_file)
                if os.path.isfile(target):
                    if os.path.getsize(target) < 500 and '.' in cached_file:
                        bookid = cached_file.split('.')[0]
                        res.append({"BookID": bookid})
        self.data = res

    def _getAuthor(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return
        else:
            self.id = kwargs['id']

        author = self._dic_from_query(
            'SELECT * from authors WHERE AuthorID="' + self.id + '"')
        books = self._dic_from_query(
            'SELECT * from books WHERE AuthorID="' + self.id + '"')

        self.data = {'author': author, 'books': books}

    def _getMagazines(self):
        self.data = self._dic_from_query('SELECT * from magazines order by Title COLLATE NOCASE')

    def _getAllBooks(self):
        q = 'SELECT authors.AuthorID,AuthorName,AuthorLink,BookName,BookSub,BookGenre,BookIsbn,BookPub,'
        q += 'BookRate,BookImg,BookPages,BookLink,BookID,BookDate,BookLang,BookAdded,books.Status '
        q += 'from books,authors where books.AuthorID = authors.AuthorID'
        self.data = self._dic_from_query(q)

    def _getIssues(self, **kwargs):
        if 'name' not in kwargs:
            self.data = 'Missing parameter: name'
            return
        else:
            self.id = kwargs['name']

        magazine = self._dic_from_query(
            'SELECT * from magazines WHERE Title="' + self.id + '"')
        issues = self._dic_from_query(
            'SELECT * from issues WHERE Title="' + self.id + '" order by IssueDate DESC')

        self.data = {'magazine': magazine, 'issues': issues}

    def _createMagCovers(self, **kwargs):
        if 'refresh' in kwargs:
            refresh=True
        else:
            refresh=False
        if 'wait' in kwargs:
            self.data = create_covers(refresh=refresh)
        else:
            threading.Thread(target=create_covers, name='API-MAGCOVERS', args=[refresh]).start()

    def _getBook(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return
        else:
            self.id = kwargs['id']

        book = self._dic_from_query('SELECT * from books WHERE BookID="' + self.id + '"')
        self.data = {'book': book}

    def _queueBook(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return
        else:
            self.id = kwargs['id']

        myDB = database.DBConnection()
        controlValueDict = {'BookID': self.id}
        newValueDict = {'Status': 'Wanted'}
        myDB.upsert("books", newValueDict, controlValueDict)

    def _unqueueBook(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return
        else:
            self.id = kwargs['id']

        myDB = database.DBConnection()
        controlValueDict = {'BookID': self.id}
        newValueDict = {'Status': 'Skipped'}
        myDB.upsert("books", newValueDict, controlValueDict)

    def _addMagazine(self, **kwargs):
        if 'name' not in kwargs:
            self.data = 'Missing parameter: name'
            return
        else:
            self.id = kwargs['name']

        myDB = database.DBConnection()
        controlValueDict = {"Title": self.id}
        newValueDict = {
            "Regex": None,
            "Status": "Active",
            "MagazineAdded": today(),
            "IssueStatus": "Wanted",
            "Reject": None
        }
        myDB.upsert("magazines", newValueDict, controlValueDict)

    def _removeMagazine(self, **kwargs):
        if 'name' not in kwargs:
            self.data = 'Missing parameter: name'
            return
        else:
            self.id = kwargs['name']

        myDB = database.DBConnection()
        myDB.action('DELETE from magazines WHERE Title="%s"' % self.id)
        myDB.action('DELETE from wanted WHERE BookID="%s"' % self.id)
        myDB.action('DELETE from issues WHERE Title="%s"' % self.id)

    def _pauseAuthor(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return
        else:
            self.id = kwargs['id']

        myDB = database.DBConnection()
        controlValueDict = {'AuthorID': self.id}
        newValueDict = {'Status': 'Paused'}
        myDB.upsert("authors", newValueDict, controlValueDict)

    def _ignoreAuthor(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return
        else:
            self.id = kwargs['id']

        myDB = database.DBConnection()
        controlValueDict = {'AuthorID': self.id}
        newValueDict = {'Status': 'Ignored'}
        myDB.upsert("authors", newValueDict, controlValueDict)

    def _unignoreAuthor(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return
        else:
            self.id = kwargs['id']

        myDB = database.DBConnection()
        controlValueDict = {'AuthorID': self.id}
        newValueDict = {'Status': 'Active'}
        myDB.upsert("authors", newValueDict, controlValueDict)

    def _resumeAuthor(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return
        else:
            self.id = kwargs['id']

        myDB = database.DBConnection()
        controlValueDict = {'AuthorID': self.id}
        newValueDict = {'Status': 'Active'}
        myDB.upsert("authors", newValueDict, controlValueDict)

    def _refreshAuthor(self, **kwargs):
        refresh = False
        if 'refresh' in kwargs:
            refresh = True
        if 'name' not in kwargs:
            self.data = 'Missing parameter: name'
            return
        else:
            self.id = kwargs['name']

        try:
            addAuthorToDB(self.id, refresh=refresh)
        except Exception as e:
            self.data = str(e)

    def _forceActiveAuthorsUpdate(self, **kwargs):
        refresh = False
        if 'refresh' in kwargs:
            refresh = True
        if 'wait' in kwargs:
            self.data = dbUpdate(refresh=refresh)
        else:
            threading.Thread(target=dbUpdate, name='API-DBUPDATE', args=[refresh]).start()

    def _forceMagSearch(self, **kwargs):
        if lazylibrarian.USE_NZB() or lazylibrarian.USE_TOR() or lazylibrarian.USE_RSS():
            if 'wait' in kwargs:
                search_magazines(None, True)
            else:
                threading.Thread(target=search_magazines, name='API-SEARCHMAGS', args=[None, True]).start()
        else:
            self.data = 'No search methods set, check config'

    def _forceBookSearch(self, **kwargs):
        if lazylibrarian.USE_NZB():
            if 'wait' in kwargs:
                search_nzb_book()
            else:
                threading.Thread(target=search_nzb_book, name='API-SEARCHNZB', args=[]).start()
        if lazylibrarian.USE_TOR():
            if 'wait' in kwargs:
                search_tor_book()
            else:
                threading.Thread(target=search_tor_book, name='API-SEARCHTOR', args=[]).start()
        if lazylibrarian.USE_RSS():
            if 'wait' in kwargs:
                search_rss_book()
            else:
                threading.Thread(target=search_rss_book, name='API-SEARCHRSS', args=[]).start()
        if not lazylibrarian.USE_RSS() and not lazylibrarian.USE_NZB() and not lazylibrarian.USE_TOR():
            self.data = "No search methods set, check config"

    @staticmethod
    def _forceProcess():
        processDir()

    @staticmethod
    def _forceLibraryScan(**kwargs):
        if 'wait' in kwargs:
            LibraryScan()
        else:
            threading.Thread(target=LibraryScan, name='API-LIBRARYSCAN', args=[]).start()

    @staticmethod
    def _forceMagazineScan(**kwargs):
        if 'wait' in kwargs:
            magazineScan()
        else:
            threading.Thread(target=magazineScan, name='API-MAGSCAN', args=[]).start()

    def _deleteEmptySeries(self, **kwargs):
        self.data = deleteEmptySeries()

    def _cleanCache(self, **kwargs):
        if 'wait' in kwargs:
            self.data = cleanCache()
        else:
            threading.Thread(target=cleanCache, name='API-CLEANCACHE', args=[]).start()

    def _setWorkPages(self, **kwargs):
        if 'wait' in kwargs:
            self.data = setWorkPages()
        else:
            threading.Thread(target=setWorkPages, name='API-SETWORKPAGES', args=[]).start()

    def _setAllBookSeries(self, **kwargs):
        if 'wait' in kwargs:
            self.data = setAllBookSeries()
        else:
            threading.Thread(target=setAllBookSeries, name='API-SETALLBOOKSERIES', args=[]).start()

    def _getBookCovers(self, **kwargs):
        if 'wait' in kwargs:
            self.data = getBookCovers()
        else:
            threading.Thread(target=getBookCovers, name='API-GETBOOKCOVERS', args=[]).start()

    def _getAuthorImages(self, **kwargs):
        if 'wait' in kwargs:
            self.data = getAuthorImages()
        else:
            threading.Thread(target=getAuthorImages, name='API-GETAUTHORIMAGES', args=[]).start()

    def _getVersion(self):
        self.data = {
            'install_type': lazylibrarian.CONFIG['INSTALL_TYPE'],
            'current_version': lazylibrarian.CONFIG['CURRENT_VERSION'],
            'latest_version': lazylibrarian.CONFIG['LATEST_VERSION'],
            'commits_behind': lazylibrarian.CONFIG['COMMITS_BEHIND'],
        }

    @staticmethod
    def _shutdown():
        lazylibrarian.SIGNAL = 'shutdown'

    @staticmethod
    def _restart():
        lazylibrarian.SIGNAL = 'restart'

    @staticmethod
    def _update():
        lazylibrarian.SIGNAL = 'update'

    def _findAuthor(self, **kwargs):
        if 'name' not in kwargs:
            self.data = 'Missing parameter: name'
            return

        authorname = formatAuthorName(kwargs['name'])
        if lazylibrarian.CONFIG['BOOK_API'] == "GoogleBooks":
            GB = GoogleBooks(authorname)
            queue = Queue.Queue()
            search_api = threading.Thread(target=GB.find_results, name='API-GBRESULTS', args=[authorname, queue])
            search_api.start()
        else:  # lazylibrarian.CONFIG['BOOK_API'] == "GoodReads":
            queue = Queue.Queue()
            GR = GoodReads(authorname)
            search_api = threading.Thread(target=GR.find_results, name='API-GRRESULTS', args=[authorname, queue])
            search_api.start()

        search_api.join()
        self.data = queue.get()

    def _findBook(self, **kwargs):
        if 'name' not in kwargs:
            self.data = 'Missing parameter: name'
            return

        if lazylibrarian.CONFIG['BOOK_API'] == "GoogleBooks":
            GB = GoogleBooks(kwargs['name'])
            queue = Queue.Queue()
            search_api = threading.Thread(target=GB.find_results, name='API-GBRESULTS', args=[kwargs['name'], queue])
            search_api.start()
        else:  # lazylibrarian.CONFIG['BOOK_API'] == "GoodReads":
            queue = Queue.Queue()
            GR = GoodReads(kwargs['name'])
            search_api = threading.Thread(target=GR.find_results, name='API-GRRESULTS', args=[kwargs['name'], queue])
            search_api.start()

        search_api.join()
        self.data = queue.get()

    def _moveBook(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return
        if 'toid' not in kwargs:
            self.data = 'Missing parameter: toid'
            return
        try:
            myDB = database.DBConnection()
            authordata = myDB.match(
                'SELECT AuthorName from authors WHERE AuthorID="%s"' % kwargs['toid'])
            if not authordata:
                self.data = "No destination author [%s] in the database" % kwargs['toid']
            else:
                bookdata = myDB.match(
                    'SELECT AuthorID, BookName from books where BookID="%s"' % kwargs['id'])
                if not bookdata:
                    self.data = "No bookid [%s] in the database" % kwargs['id']
                else:
                    controlValueDict = {'BookID': kwargs['id']}
                    newValueDict = {'AuthorID': kwargs['toid']}
                    myDB.upsert("books", newValueDict, controlValueDict)
                    update_totals(bookdata[0])  # we moved from here
                    update_totals(kwargs['toid'])  # to here
                    self.data = "Moved book [%s] to [%s]" % (bookdata[1], authordata[0])
            logger.debug(self.data)
        except Exception as e:
            self.data = str(e)

    def _moveBooks(self, **kwargs):
        if 'fromname' not in kwargs:
            self.data = 'Missing parameter: fromname'
            return
        if 'toname' not in kwargs:
            self.data = 'Missing parameter: toname'
            return
        try:
            myDB = database.DBConnection()
            q = 'SELECT bookid,books.authorid from books,authors where books.AuthorID = authors.AuthorID'
            q += ' and authorname="%s"' % kwargs['fromname']
            fromhere = myDB.select(q)

            tohere = myDB.match(
                'SELECT authorid from authors where authorname="%s"' % kwargs['toname'])
            if not len(fromhere):
                self.data = "No books by [%s] in the database" % kwargs['fromname']
            else:
                if not tohere:
                    self.data = "No destination author [%s] in the database" % kwargs['toname']
                else:
                    myDB.action('UPDATE books SET authorid="%s", where authorname="%s"' %
                                (tohere[0], kwargs['fromname']))
                    self.data = "Moved %s books from %s to %s" % (len(fromhere), kwargs['fromname'], kwargs['toname'])
                    update_totals(fromhere[0][1])  # we moved from here
                    update_totals(tohere[0])  # to here

            logger.debug(self.data)
        except Exception as e:
            self.data = str(e)

    def _addAuthor(self, **kwargs):
        if 'name' not in kwargs:
            self.data = 'Missing parameter: name'
            return
        else:
            self.id = kwargs['name']
        try:
            self.data = addAuthorNameToDB(author=self.id, refresh=False)
        except Exception as e:
            self.data = str(e)

    def _addAuthorID(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return
        else:
            self.id = kwargs['id']
        try:
            self.data = addAuthorToDB(refresh=False, authorid=self.id)
        except Exception as e:
            self.data = str(e)

    def _searchItem(self, **kwargs):
        if 'item' not in kwargs:
            self.data = 'Missing parameter: item'
            return
        else:
            self.data = searchItem(kwargs['item'])

    def _searchBook(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return
        else:
            self.id = kwargs['id']

        books = [{"bookid": id}]
        if lazylibrarian.USE_RSS():
            if 'wait' in kwargs:
                search_rss_book(books)
            else:
                threading.Thread(target=search_rss_book, name='API-SEARCHRSS', args=[books]).start()
        if lazylibrarian.USE_NZB():
            if 'wait' in kwargs:
                search_nzb_book(books)
            else:
                threading.Thread(target=search_nzb_book, name='API-SEARCHNZB', args=[books]).start()
        if lazylibrarian.USE_TOR():
            if 'wait' in kwargs:
                search_tor_book(books)
            else:
                threading.Thread(target=search_tor_book, name='API-SEARCHTOR', args=[books]).start()
        if not lazylibrarian.USE_RSS() and not lazylibrarian.USE_NZB() and not lazylibrarian.USE_TOR():
            self.data = "No search methods set, check config"

    def _removeAuthor(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return
        else:
            self.id = kwargs['id']

        myDB = database.DBConnection()
        authorsearch = myDB.select('SELECT AuthorName from authors WHERE AuthorID="%s"' % id)
        if len(authorsearch):  # to stop error if try to remove an author while they are still loading
            AuthorName = authorsearch[0]['AuthorName']
            logger.info(u"Removing all references to author: %s" % AuthorName)
            myDB.action('DELETE from authors WHERE AuthorID="%s"' % id)
            myDB.action('DELETE from books WHERE AuthorID="%s"' % id)

    def _writeCFG(self, **kwargs):
        if 'name' not in kwargs:
            self.data = 'Missing parameter: name'
            return
        if 'value' not in kwargs:
            self.data = 'Missing parameter: value'
            return
        if 'group' not in kwargs:
            self.data = 'Missing parameter: group'
            return
        try:
            self.data = '["%s"]' % lazylibrarian.CFG.get(kwargs['group'], kwargs['name'])
            lazylibrarian.CFG.set(kwargs['group'], kwargs['name'], kwargs['value'])
            with open(lazylibrarian.CONFIGFILE, 'wb') as configfile:
                lazylibrarian.CFG.write(configfile)
            lazylibrarian.config_read(reloaded=True)
        except Exception as e:
            self.data = 'Unable to update CFG entry for %s: %s, %s' % (kwargs['group'], kwargs['name'], str(e))

    def _readCFG(self, **kwargs):
        if 'name' not in kwargs:
            self.data = 'Missing parameter: name'
            return
        if 'group' not in kwargs:
            self.data = 'Missing parameter: group'
            return
        try:
            self.data = '["%s"]' % lazylibrarian.CFG.get(kwargs['group'], kwargs['name'])
        except Exception:
            self.data = 'No CFG entry for %s: %s' % (kwargs['group'], kwargs['name'])

    @staticmethod
    def _loadCFG():
        lazylibrarian.config_read(reloaded=True)

    def _getSeriesAuthors(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
        else:
            self.id = kwargs['id']
            count = getSeriesAuthors(self.id)
            self.data = "Added " + count

    def _getSeriesMembers(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return
        else:
            self.id = kwargs['id']
        self.data = getSeriesMembers(self.id)

    def _getBookAuthors(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return
        else:
            self.id = kwargs['id']
        self.data = getBookAuthors(self.id)

    def _getWorkSeries(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return
        else:
            self.id = kwargs['id']
        self.data = getWorkSeries(self.id)

    def _getWorkPage(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return
        else:
            self.id = kwargs['id']
        self.data = getWorkPage(self.id)

    def _getBookCover(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return
        else:
            self.id = kwargs['id']
        self.data = getBookCover(self.id)

    def _getAuthorImage(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return
        else:
            self.id = kwargs['id']
        self.data = getAuthorImage(self.id)


    def _lock(self, table, itemid, state):
        myDB = database.DBConnection()
        dbentry = myDB.match('SELECT %sID from %ss WHERE %sID=%s' % (table, table, table, itemid))
        if dbentry:
            myDB.action('UPDATE %ss SET Manual="%s" WHERE %sID=%s' % (table, state, table, itemid))
        else:
            self.data = "%sID %s not found" % (table, itemid)


    def _setAuthorLock(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return
        else:
            self._lock("author", kwargs['id'], "1")


    def _setAuthorUnlock(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return
        else:
            self._lock("author", kwargs['id'], "0")


    def _setAuthorImage(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return
        else:
            self.id = kwargs['id']
        if 'img' not in kwargs:
            self.data = 'Missing parameter: img'
            return
        else:
            self._setimage("author", kwargs['id'], kwargs['img'])


    def _setBookImage(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return
        else:
            self.id = kwargs['id']
        if 'img' not in kwargs:
            self.data = 'Missing parameter: img'
            return
        else:
            self._setimage("book", kwargs['id'], kwargs['img'])


    def _setimage(self, table, itemid, img):
        msg = "%s Image [%s] rejected" % (table, img)
        # Cache file image
        if os.path.isfile(img):
            extn = os.path.splitext(img)[1].lower()
            if extn and extn in ['.jpg','.jpeg','.png']:
                destfile = os.path.join(lazylibrarian.CACHEDIR, itemid + '.jpg')
                try:
                    shutil.copy(img, destfile)
                    setperm(destfile)
                    msg = ''
                except Exception as why:
                    msg += " Failed to copy file: %s" %  str(why)
            else:
                msg += " invalid extension"

        if img.startswith('http'):
            # cache image from url
            extn = os.path.splitext(img)[1].lower()
            if extn and extn in ['.jpg','.jpeg','.png']:
                cachedimg, success = cache_img(table, itemid, img)
                if success:
                    msg = ''
                else:
                    msg += " Failed to cache file"
            else:
                msg += " invalid extension"
        elif msg:
            msg += " Not found"

        if msg:
            self.data = msg
            return

        myDB = database.DBConnection()
        dbentry = myDB.match('SELECT %sID from %ss WHERE %sID=%s' % (table, table, table, itemid))
        if dbentry:
            myDB.action('UPDATE %ss SET %sImg="%s" WHERE %sID=%s' %
                        (table, table, 'cache' + os.sep + itemid + '.jpg', table, itemid))
        else:
            self.data = "%sID %s not found" % (table, itemid)


    def _setBookLock(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return
        else:
            self._lock("book", kwargs['id'], "1")


    def _setBookUnlock(self, **kwargs):
        if 'id' not in kwargs:
            self.data = 'Missing parameter: id'
            return
        else:
            self._lock("book", kwargs['id'], "0")


    @staticmethod
    def _restartJobs():
        restartJobs(start='Restart')

    @staticmethod
    def _checkRunningJobs():
        checkRunningJobs()

    def _showJobs(self):
        self.data = showJobs()

    def _importAlternate(self, **kwargs):
        if 'dir' in kwargs:
            usedir = kwargs['dir']
        else:
            usedir = lazylibrarian.CONFIG['ALTERNATE_DIR']
        if 'wait' in kwargs:
            self.data = processAlternate(usedir)
        else:
            threading.Thread(target=processAlternate, name='API-IMPORTALT', args=[usedir]).start()

    def _importCSVwishlist(self, **kwargs):
        if 'dir' in kwargs:
            usedir = kwargs['dir']
        else:
            usedir = lazylibrarian.CONFIG['ALTERNATE_DIR']
        if 'wait' in kwargs:
            self.data = import_CSV(usedir)
        else:
            threading.Thread(target=import_CSV, name='API-IMPORTCSV', args=[usedir]).start()

    def _exportCSVwishlist(self, **kwargs):
        if 'dir' in kwargs:
            usedir = kwargs['dir']
        else:
            usedir = lazylibrarian.CONFIG['ALTERNATE_DIR']
        if 'wait' in kwargs:
            self.data = export_CSV(usedir)
        else:
            threading.Thread(target=export_CSV, name='API-EXPORTCSV', args=[usedir]).start()
