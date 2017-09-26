import config
from messages import messages
import pymysql
import urllib.parse

import config as S

con = None

def initialize():
    '''Create the tables if they don't exist'''
    global con
    urllib.parse.uses_netloc.append("mysql")
    url = urllib.parse.urlparse(S.DATABASE_URL)
    con = pymysql.connect(
        db=url.path[1:],
        user=url.username,
        password=url.password,
        host=url.hostname,
        port=url.port,
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,)
    
    with con.cursor() as cur:
        #uid            telegram user id
        #rounds_joined  total number of rounds where that user dropped a username
        #names_given    total number of times that user has dropped a username
        #names_liked    total number times that user has liked someone else
        #times_leeched  number of rounds he was considered a leecher
        #first_name     last recorded telegram first_name
        try:
            cur.execute('''CREATE TABLE users (
                uid             INT PRIMARY KEY NOT NULL,
                rounds_joined   INT DEFAULT 0,
                names_given     INT DEFAULT 0,
                names_liked     INT DEFAULT 0,
                rounds_leeched  INT DEFAULT 0,
                first_name      TEXT
                );''')
        except pymysql.err.InternalError as e:
            #ignore table already exist error
            if e.args[0] != 1050:
                raise e
        
        #cid            telegram chat id
        #curr_round     current round's serial number
        #curr_step      0=stopped, 1=round start, 2=round closed, 3=check leech, 4=cooldown
        #step_start     time the current step started
        #step1_len      seconds to spend in step1
        #step1_calls    remind users to drop every X seconds while in step1
        #step2_len      seconds to spend in step2
        #timezone       hours to add to current time when displaying to others
        #round_sched    hours when to start a new round
        #allow_talk     allow off-topic conversations without any nagging
        try:
            cur.execute('''CREATE TABLE chats (
                cid         BIGINT PRIMARY KEY NOT NULL,
                curr_round  INT DEFAULT 0,
                curr_step   INT DEFAULT 0,
                step_start  INT,
                step1_len   INT DEFAULT 1800,
                step1_calls INT DEFAULT 600,
                step2_len   INT DEFAULT 3600,
                timezone    INT DEFAULT 0,
                round_sched TEXT NOT NULL,
                allow_talk  BOOL DEFAULT 1
                );''')
        except pymysql.err.InternalError as e:
            #ignore table already exist error
            if e.args[0] != 1050:
                raise e
        
        #uid        reference to the user id
        #cid        reference to the chat id
        #mid        message id of message that created the entry
        #update_mid message id of message that updated the entry (e.g "done with...")
        #round_num  the chat's round number when that entry was entered
        #uname      IG username to be liked
        #wname      IG username that will do the liking
        #checked    wether this entry was checked for leeching
        try:
            cur.execute('''CREATE TABLE entries (
                uid             INT NOT NULL,
                cid             BIGINT NOT NULL,
                mid             INT NOT NULL,
                update_mid      INT,
                round_num       INT NOT NULL,
                uname           TEXT NOT NULL,
                wname           TEXT NOT NULL,
                unames_leeched  INT NOT NULL DEFAULT 0,
                checked         BOOL NOT NULL DEFAULT 0,
                FOREIGN KEY(uid) REFERENCES users(uid) ON DELETE CASCADE,
                FOREIGN KEY(cid) REFERENCES chats(cid) ON DELETE CASCADE
                );''')
        except pymysql.err.InternalError as e:
            #ignore table already exist error
            if e.args[0] != 1050:
                raise e
        
        cur.execute('SELECT uid FROM users WHERE rounds_leeched >= %s;', (config.LEECHES_TO_BAN,))
        config.BANNED = set(result['uid'] for result in cur.fetchall())

def select(sql, args=tuple(), fetch=None):
    '''Execute a fetch, wrapped into a connect - close'''
    con.ping(reconnect=True)
    with con.cursor() as cur:
        if fetch == 'one':
            cur.execute(sql, args)
            results = cur.fetchone()
        elif fetch == 'all':
            cur.execute(sql, args)
            results = cur.fetchall()
        else:
            raise ValueError('Must fetch something')
    return results

def execute(sql, args=None):
    '''Exec a statement with ping'''
    con.ping(reconnect=True)
    with con.cursor() as cur:
        cur.execute(sql, args)

def add_entries(chat, msg, entries):
    '''enters entries (uname, wname) if they are all valid'''
    con.ping(reconnect=True)
    with con.cursor() as cur:
        #check if duplicate of both uname and wname of entry in both uname and wname of db
        args = [chat.cid, chat.curr_round] + ([entry['uname'] for entry in entries]+[entry['wname'] for entry in entries if entry['wname'] != entry['uname']])*2
        #dynamically set the sql to match the number of entries
        names = ','.join(['%s']*((len(args)-2)//2))
        cur.execute(
            """SELECT uname, uid
               FROM users INNER JOIN entries USING (uid)
               WHERE cid=%s AND round_num=%s AND (uname IN ({names}) OR wname in ({names}));""".format(names=names), args)
        duplicate = cur.fetchall()
        if duplicate:
            message = '\n'.join(messages['err_duplicate'].format(
                        igname = row['uname'],
                        )
                    for row in duplicate)
            return (message, None)
        
        #insert the user
        try:
            cur.execute('INSERT INTO users (uid) VALUES (%s);', (msg['from']['id'],))
        except pymysql.err.IntegrityError as e:
            pass
        #check if uid already has dropped in this round
        args = (msg['from']['id'], chat.cid, chat.curr_round)
        cur.execute('SELECT count(*) count FROM entries WHERE uid=%s AND cid=%s AND round_num=%s;', args)
        dropped = cur.fetchone()
        
        #truncate name if too long and remove bad chars
        first_name = msg['from']['first_name']
        if len(first_name) > 12: first_name = first_name[:10]+'…'
        #update rounds joined, names given, name of user
        args = (0 if dropped['count'] else 1, len(entries), first_name, msg['from']['id'])
        cur.execute('UPDATE users SET rounds_joined=rounds_joined+%s, names_given=names_given+%s, first_name=%s WHERE uid = %s;', args)
        
        #finally insert the entries
        args = ((msg['from']['id'], chat.cid, msg['message_id'], chat.curr_round, entry['uname'], entry['wname'])
                    for entry in entries)
        cur.executemany('INSERT INTO entries (uid, cid, mid, round_num, uname, wname) VALUES (%s, %s, %s, %s, %s, %s);', args)
        print('Inserted', entries)
        return ("grp_gooddrop", None)

def update_entries(chat, msg, dones):
    '''check a list of {uname, wname} and update the entry if change was made'''
    con.ping(reconnect=True)
    with con.cursor() as cur:
        #get all unames and wnames to check for ownership / diplicity
        args = (chat.cid, chat.curr_round)
        cur.execute('SELECT uid, uname, wname FROM entries WHERE cid=%s AND round_num=%s;', args)
        results = cur.fetchall()
        owned = set(row['uname'] for row in results if row['uid'] == msg['from']['id'])
        locked = (set(row['uname'] for row in results) | set(row['wname'] for row in results)) - owned
        errors = set()
        #append into errors every done he doesn't own or that are locked
        for done in dones:
            if (done['uname'] not in owned
                or done['uname'] in locked
                ):
                    errors.add(done['uname'])
            elif done['wname'] in locked:
                #check that this wname isnt the original pair of the uname
                #e.g: if the drop was "@a with @b" and now the done is "D @a with @b"
                for result in results:
                    if result['uname'] == done['uname']:
                        if result['wname'] != done['wname']:
                            errors.add(done['wname'])
                        break
        #send error message if there are any
        if errors:
            message = '\n'.join(messages['err_donebad'].format(
                        igname = error)
                    for error in errors)
            return (message, None)
        #apply any changed wname
        args = tuple((done['wname'], msg['message_id'], chat.cid, chat.curr_round, done['uname'])
                for done in dones if done['wname'] )
        if args:
            cur.executemany('UPDATE entries SET wname=%s, update_mid=%s WHERE cid=%s AND round_num=%s AND uname=%s;', args)
            print('Updated entry', dones)
        #send confirmation message
        message = '\n'.join(messages['grp_doneok_with' if done['wname'] else 'grp_doneok'].format(
                    igname = done['uname'],
                    igwith = done['wname'])
                for done in dones)
        return (message, None)

def remove_entry(chat, msg, entry):
    '''remove one uname from entries'''
    con.ping(reconnect=True)
    with con.cursor() as cur:
        #try to delete right away
        affected = cur.execute('DELETE FROM entries WHERE uid=%s AND cid=%s AND round_num=%s AND (uname=%s OR wname=%s);',
                                (msg['from']['id'], chat.cid, chat.curr_round, entry, entry))
        #if no row was affected, show error
        if affected == 0:
            return ('err_removebad', {'igname': entry})
        else:
            cur.execute('UPDATE users SET names_given = names_given - 1 WHERE uid=%s;',
                            (msg['from']['id'],))
            print('Removed entry', entry)
            return ('grp_removeok', {'igname': entry})