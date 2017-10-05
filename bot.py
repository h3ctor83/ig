#!/usr/bin/env python3
__author__ = 'https://t.me/fyodorob'

import sys
import signal
import time
import threading
import calendar
import logging
from multiprocessing.dummy import Pool as ThreadPool
import logging
import collections

import telepot
from InstagramAPI import Instagram, InstagramException
from pymysql.err import OperationalError
from urllib3.exceptions import ProtocolError, ReadTimeoutError

from messages import messages
import config
import db

"""TODO
 original bot shows confirmations and errors on multiple "done"
 Delete when kicked from group
2.0
 "Drop if you haven't" add timeleft and partial info: "x users, y acounts"
 when sending a tg username, use first name with links
 check that the username exists when dropping
 specific error message for each syntaxerror
 per-group settings and config
"""

logging.basicConfig(level=logging.ERROR, filename='error.log')
chats = dict()
btn_spammers = set()

class User():
    def sendMessage(uid, text, format=None, parse_mode='HTML', disable_web_page_preview=True):
        '''send a private message to a user'''
        if text in messages:
            text = messages[text]
        if format:
            text = text.format(**format)
        bot.sendMessage(uid, text, parse_mode=parse_mode, disable_web_page_preview=disable_web_page_preview)
    def answerCbq(msg, text, format=None, show_alert=False):
        if text in messages:
            text = messages[text]
        if format:
            text.format(**format)
        if msg.get('id'):
            bot.answerCallbackQuery(msg['id'], text=text, show_alert=show_alert)
            del msg['id']
    #commands received in private
    def cmd(msg):
        #ignore what isn't a command
        if not msg['text'].startswith('/'): return
        
        uid = msg['from']['id']
        command = msg['text'][:msg['text'].index(' ')] if ' ' in msg['text'] else msg['text']
        command = command.lower()
        if command in User.commands:
            getattr(User, User.commands[command])(uid, msg)
            #command might be from a button, so answer the cbq
            User.answerCbq(msg, None)
    def cmd_help(uid, msg):
        '''send help message'''
        if uid in config.ADMINS:
            User.sendMessage(uid, 'prv_adm_help')
        else:
            User.sendMessage(uid, 'prv_hello')
    def cmd_start(uid, msg):
        '''send hello message'''
        User.sendMessage(uid, 'prv_hello')
    def cmd_unban(uid, msg):
        if uid not in config.ADMINS: return
        args = msg['text'].split()
        #remove the first @ if present
        if args[1].startswith('@'):
            args[1] = args[1][1:]
        #search for the username in db
        try:
            target_uid = int(args[1])
            result = db.select('SELECT uid, first_name FROM users WHERE uid = %s;',
                (target_uid,), fetch='one')
        except ValueError:
            result = db.select('SELECT uid, first_name FROM users WHERE username = %s;',
                (args[1].lower(),), fetch='one')
        if result:
            db.execute('UPDATE users SET rounds_leeched = 0 WHERE uid = %s;',
                (result['uid'],))
            config.BANNED.discard(result['uid'])
            User.sendMessage(uid, 'Unbanned <a href="tg://user?id={uid}">{fname}</a>', format={'uid':result['uid'], 'fname':html(result['first_name'])})
        else:
            User.sendMessage(uid, "Not found")
    def cmd_ban(uid, msg):
        if uid not in config.ADMINS: return
        args = msg['text'].split()
        #remove the first @ if present
        if args[1].startswith('@'):
            args[1] = args[1][1:]
        #search for the username in db
        try:
            target_uid = int(args[1])
            result = db.select('SELECT uid, first_name FROM users WHERE uid = %s;',
                (target_uid,), fetch='one')
        except ValueError:
            result = db.select('SELECT uid, first_name FROM users WHERE username = %s;',
                (args[1].lower(),), fetch='one')
        if result:
            db.execute('UPDATE users SET rounds_leeched = 99 WHERE uid = %s;',
                (result['uid'],))
            config.BANNED.add(result['uid'])
            User.sendMessage(uid, 'Banned <a href="tg://user?id={uid}">{fname}</a>', format={'uid':result['uid'], 'fname':html(result['first_name'])})
        else:
            User.sendMessage(uid, "Not found")
    def cmd_test_insta(uid, msg):
        '''Test connection to instagram'''
        if uid not in config.ADMINS: return
        test_insta(uid)
    def cmd_toggle_debug(uid, msg):
        '''toggle leecher check debug messages'''
        if uid not in config.ADMINS: return
        config.DEBUG_LEECHER_MESSAGE = int(not config.DEBUG_LEECHER_MESSAGE)
        User.sendMessage(uid, 'Leecher debug messages are now [{state}]', format={'state':'ON' if config.DEBUG_LEECHER_MESSAGE else 'OFF'})
    def cmd_toggle_talk(uid, msg):
        '''toggle "shush" players who try to chat in the chat'''
        if uid not in config.ADMINS: return
        config.ALLOW_TALK = int(not config.ALLOW_TALK)
        User.sendMessage(uid, 'Talking is now [{state}]', format={'state':'OK' if config.ALLOW_TALK else 'FORBIDDEN'})
    def cmd_show_dropped(uid, msg):
        for chat in chats.values():
            results = db.select("SELECT * FROM entries INNER JOIN users USING (uid) WHERE cid = %s AND round_num = %s;", args=(chat.cid, chat.curr_round), fetch='all')
            dropped = '\n'.join('<b>@{iguname}</b>{igwname} by <a href="tg://user?id={tguid}">{fname}</a>'.format(
                            iguname=entry['uname'],
                            tguid=entry['uid'],
                            fname=html(entry['first_name']),
                            igwname=' with <b>@{}</b>'.format(entry['wname']) if entry['wname'] != entry['uname'] else '')
                        for entry in results)
            round_info = 'Showing prev round' if chat.curr_step >= 3 else 'Drops open' if chat.curr_step == 1 else 'Drops closed' if chat.curr_step == 2 else 'Group stopped'
            User.sendMessage(uid, 'Group: {cid}\n{round_info} (round {rnum})\n{dropped}'.format(cid=chat.cid, round_info=round_info, rnum=chat.curr_round, dropped=dropped if dropped else 'None'))
    commands = {
        '/start': 'cmd_start',
        '/help': 'cmd_help',
        '/ban': 'cmd_ban',
        '/unban': 'cmd_unban',
        '/ig': 'cmd_test_insta',
        '/debug': 'cmd_toggle_debug',
        '/talk': 'cmd_toggle_talk',
        '/dropped': 'cmd_show_dropped',
        }
class Chat():
    '''Chats and their timers'''
    def __init__(self, row):
        self.cid = row['cid']
        self.curr_round = row.get('curr_round')
        self.curr_step = row.get('curr_step')
        self.step_start = row.get('step_start')
        self.step1_len = config.STEP1_LEN #row['step1_len']
        self.step1_calls = config.STEP1_CALLS #row['step1_calls']
        self.step2_len = config.STEP2_LEN #row['step2_len']
        self.timezone = config.TIMEZONE #row['timezone']
        self.round_sched = config.ROUND_SCHED #row['round_sched']
        self.allow_talk = config.ALLOW_TALK #row['allow_talk']
        self.timer = None
        self.lists = None
        #change round schedule back to UTC
        #I use a string instead of a list so it can be easily moved to env variable
        self.round_sched = map(int, self.round_sched.split())
        self.round_sched = sorted((t-self.timezone)%24 for t in self.round_sched)
    #start running chats when bot boots
    def boot_timers():
        '''Starts the timers for running groups when the bot boots'''
        #gets all groups from DB
        results = db.select('SELECT * FROM chats;', fetch='all')
        for res in results:
            chat = Chat(res)
            chats[res['cid']] = chat
            
            #step1: waiting for username drops
            if chat.curr_step == 1:
                print(chat.cid, 'resuming step1')
                timeleft = chat.calc_timeleft(to='step2', format='s')
                next_call = chat.calc_timeleft(to='call', format='s')
                if next_call < timeleft:
                    chat.timer = threading.Timer(next_call, chat.call_step1)
                else:
                    chat.timer = threading.Timer(timeleft, chat.start_step2)
                chat.timer.start()
            
            #step2: waiting for done
            elif chat.curr_step == 2:
                print(chat.cid, 'resuming step2')
                timeleft = res['step_start']+res['step2_len']-time.time()
                chat.timer = threading.Timer(timeleft, chat.start_step3)
                chat.timer.start()
            
            #step3: checking leechers
            elif chat.curr_step == 3:
                print(chat.cid, 'resuming step3')
                #no real timeleft, just do the leecher check
                chat.timer = threading.Timer(0, chat.start_step3, args=(True,))
                chat.timer.start()
            
            #step4: cooldown before next round
            elif chat.curr_step == 4:
                print(chat.cid, 'resuming step4')
                timeleft = chat.calc_timeleft(to='step1', format='s')
                chat.timer = threading.Timer(timeleft, chat.start_step1)
                chat.timer.start()
    
    #receive drops
    def start_step1(self):
        '''Send message and set timer for step2'''
        print(self.cid, 'starting step1 - Receive drops')
        now = time.time()
        db.execute('UPDATE chats SET curr_step = 1, step_start = %s, curr_round = curr_round+1 WHERE cid = %s;', (now, self.cid))
        self.curr_step = 1
        self.curr_round += 1
        self.step_start = now
        timeleft = self.calc_timeleft(to='step2', format='s')
        next_call = self.calc_timeleft(to='call', format='s')
        if next_call < timeleft:
            self.timer = threading.Timer(next_call, self.call_step1)
        else:
            self.timer = threading.Timer(timeleft, self.start_step2)
        self.timer.start()
        self.sendMessage('grp_step1', format={
                'm':config.STEP1_LEN//60,
                }
            )
    
    #call while waiting for drops
    def call_step1(self):
        timeleft = self.calc_timeleft(to='step2', format='s')
        next_call = self.calc_timeleft(to='call', format='s')
        #do whatever should come first
        if next_call < timeleft-10:
            self.timer = threading.Timer(next_call, self.call_step1)
        else:
            self.timer = threading.Timer(timeleft, self.start_step2)
        self.timer.start()
        self.sendMessage('grp_step1.5')
    
    #receive done's
    def start_step2(self):
        '''Compile lists, send message and set timer for step3'''
        print(self.cid, 'starting step2 - Wait for dones and likes')
        now = int(time.time())
        #round info
        args = (self.cid, self.curr_round)
        info = db.select('SELECT count(DISTINCT uid) as participants, count(DISTINCT uname) as accounts FROM entries WHERE cid = %s AND round_num = %s;', args, fetch='one')
        self.sendMessage('grp_step2', format={'participants':info['participants'], 'accounts':info['accounts'], 'igdm_lists':len(self.get_lists()['igdm'])})
        #if there are accounts dropped, wait for step3
        if info['accounts']:
            db.execute('UPDATE chats SET curr_step = 2, step_start = %s WHERE cid = %s;', (now, self.cid))
            self.curr_step = 2
            self.step_start = now
            timeleft = self.step_start+self.step2_len-time.time()
            self.timer = threading.Timer(timeleft, self.start_step3)
            self.timer.start()
            #send message with lists button
            button = {'inline_keyboard':[[{'text':messages['btn_igdm_lists'], 'callback_data':'/igdm_list {} {}'.format(self.cid, self.curr_round)}]]}
            self.sendMessage('grp_step2.5', format={'timeleft':self.step2_len//60}, reply_markup=button)
        #if no account was dropped, go straight to step 4
        else:
            self.start_step4()
            self.sendMessage('grp_nextround')
    
    #check leechers
    def start_step3(self, silentstart=False):
        '''Check for leechers, then go to step4'''
        print(self.cid, 'starting step3 - Check leechers')
        now = int(time.time())
        db.execute('UPDATE chats SET curr_step = 3, step_start = %s WHERE cid = %s;',
                    (now, self.cid))
        self.curr_step = 3
        self.step_start = now
        if not silentstart:
            self.sendMessage('grp_step3', format={
                    'nextsched':self.calc_timeleft(to='step2', format='date'),
                    'tz':self.timezone,
                    'm':config.STEP1_LEN//60
                })
        
        #make sure I am logged in and working
        error = test_insta()
        if error:
            if type(error) == InstagramException and error.args[0].startswith('login_required'):
                message = 'Instagram error: "login_required". Leecher check will not work this round.'
            elif type(error) == InstagramException and error.args[0].startswith('checkpoint_required'):
                message = 'Instagram error: "checkpoint_required". Instagram account was probably flagged for unusual behaviour, (e.g logged in from different country) and requires unlocking. Leecher check will not work this round.'
            else:
                message = 'Instagram error: "{}". Leecher check skipped this round.'.format(error)
            print(message)
            for admin in config.ADMINS:
                try:
                    bot.sendMessage(admin, message)
                except:
                    pass
            self.start_step4()
            return
        #if there's no error, lets check leechers
        entries = db.select('SELECT uid, uname, wname, checked FROM entries WHERE cid=%s AND round_num=%s;',
                            (self.cid, self.curr_round), fetch='all')
        #set of all those who should do the liking
        self.DROPPED = set(entry['wname'] for entry in entries)
        #mark all entries that failed to like anyone
        pool = ThreadPool(config.LEECHER_CHECKERS)
        self.LEECH = collections.Counter()
        self.DEBUG_LEECHER_MESSAGE = ['#Check round {}'.format(self.curr_round),]
        results = pool.map(self.check_leechers, entries)
        pool.close()
        pool.join()
        #mark all current entries as checked
        db.execute('UPDATE entries SET checked=1 WHERE cid=%s AND round_num=%s;',
                            (self.cid, self.curr_round))
        #mark all individual leeches
        db.executemany('UPDATE entries SET unames_leeched=unames_leeched+%s WHERE cid=%s AND round_num=%s AND wname=%s;',
                    args = tuple( (self.LEECH[wname], self.cid, self.curr_round, wname) for wname in self.LEECH ))

        print(self.cid, 'leecher check done')
        if config.DEBUG_LEECHER_MESSAGE:
            #send leechers per name
            group_size = 25
            for i in range(0, len(self.DEBUG_LEECHER_MESSAGE), group_size):
                for admin in config.ADMINS:
                    try:
                        bot.sendMessage(admin, '\n'.join(self.DEBUG_LEECHER_MESSAGE[i:i + group_size]), parse_mode='HTML')
                    except:
                        pass
            leechers = db.select('SELECT uid, first_name, wname, unames_leeched FROM users INNER JOIN entries USING (uid) WHERE cid=%s AND round_num=%s AND unames_leeched > 0;',
                        (self.cid, self.curr_round), fetch='all')
            if leechers:
                for i in range(0, len(leechers), group_size*2):
                    message = "Leecher percentage:\n" + '\n'.join('<b>@{drop}</b> by <a href="tg://user?id={uid}">{fname}</a>: {percent:.0%}'.format(
                                drop = leecher['wname'],
                                uid = leecher['uid'],
                                fname = html(leecher['first_name']),
                                percent = leecher['unames_leeched']/len(entries))
                            for leecher in leechers[i:i + group_size*2])
                    print(message)
                    for admin in config.ADMINS:
                        try:
                            bot.sendMessage(admin, message, parse_mode='HTML')
                        except:
                            pass
        #finally, punish the leechers
        leechers = db.select('SELECT uid, first_name, rounds_leeched FROM users INNER JOIN entries USING (uid) WHERE cid=%s AND round_num=%s AND unames_leeched/%s >= %s GROUP BY uid;',
                    (self.cid, self.curr_round, float(len(entries)), config.PERCENTAGE_TO_LEECH/100), fetch='all')
        if leechers:
            group_size = 60
            for i in range(0, len(leechers), group_size):
                message = '\n'.join(messages['grp_leecher' if leecher['rounds_leeched'] < config.LEECHES_TO_BAN -1 else 'grp_banned'].format(uid=leecher['uid'], name=html(leecher['first_name']))
                    for leecher in leechers[i:i + group_size])
                self.sendMessage(message)
            db.execute('UPDATE users SET rounds_leeched=rounds_leeched+1 WHERE uid in (SELECT uid FROM entries WHERE cid=%s AND round_num=%s AND unames_leeched/%s >= %s GROUP BY uid);',
                (self.cid, self.curr_round, float(len(entries)), config.PERCENTAGE_TO_LEECH/100))
            config.BANNED.update(leecher['uid'] for leecher in leechers if leecher['rounds_leeched']+1 >= config.LEECHES_TO_BAN)
        elif config.DEBUG_LEECHER_MESSAGE:
            for admin in config.ADMINS:
                try:
                    bot.sendMessage(admin, 'No leechers', parse_mode='HTML')
                except:
                    pass
        self.start_step4()
    
    #wait for next round
    def start_step4(self):
        '''Just set timer for step1'''
        print(self.cid, 'starting step4 - Wait for next round')
        now = int(time.time())
        db.execute('UPDATE chats SET curr_step = 4, step_start = %s WHERE cid = %s;', (now, self.cid))
        self.curr_step = 4
        self.step_start = now
        timeleft = self.calc_timeleft(to='step1', format='s')
        self.timer = threading.Timer(timeleft, self.start_step1)
        self.timer.start()
    
    #calculate time left in seconds or h:m:s
    def calc_timeleft(self, to='step1', format='s'):
        '''calculate time left for start of next round'''
        now = time.time()
        #no need to calculate all this if only for the next call
        if to != 'call':
            sched = self.round_sched
            struct = time.gmtime(now)
            #finds the next hour to start a round
            for t in sched:
                #if it finds a time in the future today, that's it
                if struct.tm_hour < t:
                    #replace now's hour with the next one, zero min/sec
                    struct = list(struct)
                    struct[3] = t
                    struct[4] = 0
                    struct[5] = 0
                    next = calendar.timegm(tuple(struct))
                    break
            #if none is found, get the first one for the next day
            else:
                #replace now's hour with the first one, zero min/sec, then add 24h
                struct = list(struct)
                struct[3] = sched[0]
                struct[4] = 0
                struct[5] = 0
                next = calendar.timegm(tuple(struct))+60*60*24
        if to == 'step1':
            timeleft = next-now-self.step1_len
        elif to == 'step2':
            timeleft = next-now
        elif to == 'call':
            time_passed = now - self.step_start
            timeleft = self.step1_calls - (time_passed % self.step1_calls)
        else:
            raise ValueError('"to" must be "call", "step1" or "step2"')
        if format == 's':
            return timeleft
        elif format == 'hms':
            timeleft = int(timeleft)
            return '{}:{:02}:{:02}'.format(timeleft//3600, timeleft%3600//60, timeleft%60)
        elif format == 'date':
            #when printing the time, convert back to timezone
            return time.strftime("%F %T", time.gmtime(next + self.timezone*3600))
        else:
            raise ValueError('"format" must be "hms" or "s"')
        
    #get the lists of names
    def get_lists(self):
        '''return a tuple of pages for each ig software'''
        #if not cached, or wrong round number, create it
        if not self.lists or self.curr_round != self.lists['round']:
            args = (self.cid, self.curr_round)
            entries = db.select('SELECT uname FROM entries WHERE cid=%s AND round_num=%s;', args, fetch='all')
            self.lists = {'round': self.curr_round}
            
            #build igdm list
            self.lists['igdm'] = []
            NAMES_PER_PAGE = 14
            for page_num, i in enumerate(range(0, len(entries), NAMES_PER_PAGE)):
                self.lists['igdm'].append(messages['prv_lists_igdm'].format(
                        page = page_num+1,
                        total = len(entries)//NAMES_PER_PAGE + (1 if len(entries)%NAMES_PER_PAGE else 0),
                        usernames = '\n'.join('@'+entry['uname'] for entry in entries[i:i+NAMES_PER_PAGE]))
                    )
        return self.lists
    
    #send group message watching for exceptions            
    def sendMessage(self, text, reply_markup=None, reply_to_message_id=None, disable_web_page_preview=True, parse_mode='HTML', format=None):
        #apply formatting on specific messages
        if text == "grp_nextround":
            text = messages[text].format(
                    hms = self.calc_timeleft(to='step2', format='hms'),
                    m=config.STEP1_LEN//60
                )
        elif text in messages:
            text = messages[text]
        #apply general kwargs formatting
        if format:
            text = text.format(**format)
        #send the message, retry in case of timeout
        retries = 3
        while retries:
            try:
                bot.sendMessage(self.cid, text, reply_markup=reply_markup, reply_to_message_id=reply_to_message_id, disable_web_page_preview=disable_web_page_preview, parse_mode=parse_mode)
                retries = 0
            except (telepot.exception.BotWasKickedError, telepot.exception.MigratedToSupergroupChatError):
                print('Bot was kicked or migrated from', self.cid, ', deleting.')
                if self.timer: self.timer.cancel()
                chats.pop(self.cid, None)
                db.execute('DELETE FROM chats WHERE cid = %s;', (self.cid,))
                retries = 0
            except (ProtocolError, ReadTimeoutError):
                #in case of timeouts, try again
                retries -= 1
    #send a list to a user
    def send_list(self, uid, list_code):
        try:
            btn_spammers.add(uid)
            bot.sendMessage(uid, messages['prv_lists_header'])
            for page in self.get_lists()[list_code]:
                bot.sendMessage(uid, page, parse_mode='HTML')
            bot.sendMessage(uid, messages['prv_lists_footer'])
        finally:
            btn_spammers.discard(uid)
    #mark leecher entries
    def check_leechers(self, entry):
        '''Check if everyone liked this entry. Add individual leeches to LEECH, record to db later'''
        ig = Instagram(config.IG_USERNAME, config.IG_PASSWORD)
        if entry['checked']:
            return
        try:
            #id = ig.getUsernameId(entry)
            #feed = ig.getUserFeed(id)
            #pics = feed.getItems()
            #last_pic = pics[0].id
            #likers_obj = ig.getMediaLikers(last_pic)
            #likers = likers_obj.likers
            #liker_username = likers[i].username
            print(' -', entry['uname'],'Checking')
            igid = ig.getUsernameId(entry['uname'])
            last_pic = ig.getUserFeed(igid).getItems()[0].id
            likers = set(liker.username for liker in ig.getMediaLikers(last_pic).likers)
            #mark the leeches made in each entry
            leeches = self.DROPPED - likers - {entry['wname']}
            if leeches:
                #add one to the leech count of every entry that didn't like this
                self.LEECH.update(leeches)
                print(' -', entry['wname'], leeches, 'didnt like last photo')
                if config.DEBUG_LEECHER_MESSAGE:
                    self.DEBUG_LEECHER_MESSAGE.append("<b>@{}</b> checked. <b>{}</b> didn't like last photo.".format(entry['uname'], leeches))
            else:
                print(' -', entry['wname'], 'everyone liked it')
                if config.DEBUG_LEECHER_MESSAGE:
                    self.DEBUG_LEECHER_MESSAGE.append("<b>@{}</b> checked. Everyone liked it.".format(entry['uname']))
        except InstagramException as e:
            if e.args[0].startswith('login_required') or e.args[0].startswith('Not logged in'):
                print(e)
                if config.DEBUG_LEECHER_MESSAGE:
                    self.DEBUG_LEECHER_MESSAGE.append("{} Leecher error: could not login to instagram".format(entry['uname']))
            elif e.args[0].startswith('checkpoint_required'):
                print(e)
                if config.DEBUG_LEECHER_MESSAGE:
                    self.DEBUG_LEECHER_MESSAGE.append("{} Leecher error: could not login to instagram".format(entry['uname']))
            elif e.args[0].startswith('User not found') or e.args[0].startswith('Not authorized to view user'):
                print(' -', entry['wname'], 'not found or private')
                if config.DEBUG_LEECHER_MESSAGE:
                    self.DEBUG_LEECHER_MESSAGE.append("<b>@{}</b> not found or private.".format(entry['uname']))
            else:
                logging.exception(time.strftime('get_likers @ %Y-%m-%d %H:%M:%S'))
                print(' -', entry['uname'], e)
                if config.DEBUG_LEECHER_MESSAGE:
                    self.DEBUG_LEECHER_MESSAGE.append("<b>@{}</b> {}".format(entry['uname'], e))
        except IndexError as e:
            print(' -', entry['wname'], 'has no photos')
            if config.DEBUG_LEECHER_MESSAGE:
                self.DEBUG_LEECHER_MESSAGE.append("<b>@{}</b> has no photos".format(entry['uname']))
        except Exception as e:
            logging.exception(time.strftime('get_likers @ %Y-%m-%d %H:%M:%S'))
            print(' -', entry['wname'], e)
            if config.DEBUG_LEECHER_MESSAGE:
                self.DEBUG_LEECHER_MESSAGE.append("<b>@{}</b> error:{}".format(entry['uname'], e))
    #commands received in a group
    def cmd(msg):
        cid = msg['chat']['id']
        uid = msg['from']['id']
        #delete messages from banned
        if uid in config.BANNED and (uid not in config.ADMINS or not msg['text'].startswith('/')):
            try:
                print('Banned user, ignoring')
                bot.deleteMessage((cid, msg['message_id']),)
            except Exception as e:
                pass
            return
        #normal commands
        if msg['text'].startswith('/'):
            #get the first part of the command
            command = msg['text'][:msg['text'].index(' ')] if ' ' in msg['text'] else msg['text']
            #remove the bot username
            command = command.lower().replace('@'+config.BOT_USERNAME.lower(), '')
            #send the command to the correct method
            if command in Chat.commands:
                #if cid not in chats, create a dummy chat
                chat = chats.get(cid, Chat({'cid':cid}))
                getattr(chat, Chat.commands[command])(uid, msg)
                #command might be from a button, so answer the cbq
                User.answerCbq(msg, None)
        #if it doesn't start with "/" treat as drop
        elif cid in chats:
            chats[cid].cmd_drop(uid, msg)
    def cmd_start(self, uid, msg):
        '''start the bot and its timers in this group'''
        if uid not in config.ADMINS:
            return
        elif self.cid in chats:
            if self.curr_step:
                self.sendMessage('grp_running', reply_to_message_id=msg['message_id'])
            else:
                #start countdown to scheduled start
                self.start_step4()
                self.sendMessage('grp_running', reply_to_message_id=msg['message_id'])
                self.sendMessage('grp_nextround')
                print(self.cid, 'started')
        else:
            self.sendMessage('grp_disallowed', reply_to_message_id=msg['message_id'])
    def cmd_help(self, uid, msg):
        print(2)
        pass
    def cmd_nextround(self, uid, msg):
        '''If runnning, say how long until the next round starts'''
        if self.cid in chats and self.curr_step:
            self.sendMessage('grp_nextround')
    def cmd_remove(self, uid, msg):
        '''Remove a dropped username if in step 1'''
        if self.cid in chats and self.curr_step == 1:
            pieces = msg['text'].lower().split()
            #check for errors
            if len(pieces) != 2 or not is_valid_iguname(pieces[1]):
                self.sendMessage('grp_badremove', reply_to_message_id=msg['message_id'])
                return
            #finally if I got here there were no errors, try to remove
            message = db.remove_entry(self, msg, pieces[1][1:])
            #send confirm or error message
            self.sendMessage(message[0], format=message[1], reply_to_message_id=msg['message_id'])
    def cmd_allow(self, uid, msg):
        '''Allow the bot to start working in this group'''
        if uid not in config.ADMINS:
            return
        elif self.cid in chats:
            if self.curr_step:
                self.sendMessage('grp_running', reply_to_message_id=msg['message_id'])
            else:
                self.sendMessage('grp_allow', reply_to_message_id=msg['message_id'])
        else:
            #don't allow if other groups are allowed
            if chats:
                self.sendMessage('grp_in_use', reply_to_message_id=msg['message_id'])
            else:
                self.sendMessage('grp_allow', reply_to_message_id=msg['message_id'])
                db.execute('INSERT INTO chats (cid, round_sched) VALUES (%s, %s);', (self.cid, config.ROUND_SCHED))
                chat = Chat(db.select('SELECT * FROM chats WHERE cid = %s;', (self.cid,), fetch='one'))
                chats[self.cid] = chat
                print(self.cid, 'allowed')
    def cmd_config(self, uid, msg):
        '''send private config options for that group'''
        if uid not in config.ADMINS:
            return
        elif self.cid in chats:
            if self.curr_step:
                self.sendMessage('grp_running', reply_to_message_id=msg['message_id'])
            else:
                #TODO send private config
                self.sendMessage('grp_config', reply_to_message_id=msg['message_id'])
                print(self.cid, 'sent config message')
        else:
            self.sendMessage('grp_disallowed', reply_to_message_id=msg['message_id'])
    def cmd_stop(self, uid, msg):
        '''Cancel the round and stop the running timers in the chat'''
        if uid not in config.ADMINS:
            return
        elif self.cid in chats:
            if self.curr_step:
                self.timer.cancel()
                db.execute('UPDATE chats SET curr_step = 0 WHERE cid = %s;', (self.cid,))
                self.curr_step = 0
                print(self.cid, 'stopped')
            self.sendMessage('grp_stop', reply_to_message_id=msg['message_id'])
        else:
            self.sendMessage('grp_disallowed', reply_to_message_id=msg['message_id'])
    def cmd_disallow(self, uid, msg):
        '''Completely delete the group from memory and DB'''
        if uid not in config.ADMINS:
            return
        elif self.cid in chats:
            if self.curr_step:
                self.timer.cancel()
            del chats[self.cid]
            db.execute('DELETE FROM chats WHERE cid = %s;', (self.cid,))
        self.sendMessage('grp_disallowed', reply_to_message_id=msg['message_id'])
        print(self.cid, 'disallowed')
    def cmd_advance(self, uid, msg):
        '''Force the step advance, independent of time'''
        if self.cid not in chats or uid not in config.ADMINS: return
        self.timer.cancel()
        if self.curr_step == 1:
            self.start_step2()
        elif self.curr_step == 2:
            self.start_step3()
        elif self.curr_step == 3:
            self.start_step4()
        elif self.curr_step == 4:
            self.start_step1()
    def cmd_drop(self, uid, msg):
        '''Receive a message that is supposed to be a drop or done'''
        if self.cid not in chats or not self.curr_step:
            return
        text = msg['text'].lower()
        #if receiving drops
        if self.curr_step == 1:
            #first trivial test for invalid drop
            if not text.startswith('@'):
                if not config.ALLOW_TALK:
                    self.sendMessage('grp_baddrop', reply_to_message_id=msg['message_id'])
                    return
            #separate individual drops by comma and newline
            separators = ',\n'
            drops = []
            i = 0
            for f, x in enumerate(text):
                if x in separators:
                    drop = text[i:f].strip()
                    if drop:
                        drops.append(drop)
                    i=f+1
            else:
                drop = text[i:].strip()
                if drop: drops.append(drop)
                
            #separate complex drops and try to catch all errors
            try:
                names = set()
                for i, drop in enumerate(drops):
                    pieces = drop.split()
                    #if dropping a single name
                    if len(pieces) == 1:
                        uname = pieces[0][1:]
                        if (    not is_valid_iguname(pieces[0])
                                or uname in names
                                ):
                            raise SyntaxError
                        else:
                            #have the uname and the wname be the same
                            drops[i] = {'uname':uname, 'wname':uname}
                            names.add(uname)
                    #if dropping "name with other"
                    elif len(pieces) == 3:
                        #check each piece for errors
                        uname = pieces[0][1:]
                        wname = pieces[2][1:]
                        if (    not is_valid_iguname(pieces[0])
                                or pieces[1] != 'with'
                                or not is_valid_iguname(pieces[2])
                                or uname in names
                                or wname in names
                                ):
                            raise SyntaxError
                        else:
                            #remove @ from uname and wname
                            drops[i] = {'uname':pieces[0][1:], 'wname':pieces[2][1:]}
                            names.add(uname)
                            names.add(wname)
                    #any other size is invalid
                    else:
                        if not config.ALLOW_TALK:
                            raise SyntaxError
                        return
            #if the drop is invalid, send warning message and return
            except SyntaxError:
                self.sendMessage('grp_baddrop', reply_to_message_id=msg['message_id'])
                return
            #finally if I got here there were no errors, try to add
            message = db.add_entries(self, msg, drops)
            #send the result of the adding
            self.sendMessage(message[0], format=message[1], reply_to_message_id=msg['message_id'])
        
        #if confirming
        elif self.curr_step == 2:
            #first trivial test for invalid done
            if not text.startswith('d'):
                if not config.ALLOW_TALK:
                    self.sendMessage('grp_quiet', reply_to_message_id=msg['message_id'])
                    return
            
            #separate individual dones by comma and newline
            separators = ',\n'
            dones = []
            i = 0
            for f, x in enumerate(text):
                if x in separators:
                    done = text[i:f].strip()
                    if done:
                        dones.append(done)
                    i=f+1
            else:
                done = text[i:].strip()
                if done: dones.append(done)
            
            #separate complex dones and try to catch all errors
            try:
                names = set()
                for i, done in enumerate(dones):
                    pieces = done.split()
                    #if confirming one username "d @username"
                    if len(pieces) == 2:
                        uname = pieces[1][1:]
                        #check each piece for errors
                        if (    not (pieces[0] == 'd' or pieces[0] == 'done:')
                                or not is_valid_iguname(pieces[1])
                                or uname in names
                                ):
                            raise SyntaxError
                        else:
                            names.add(uname)
                            dones[i] = {'uname':uname, 'wname':None}
                    #if confirming with alteration "d @username with @other"
                    elif len(pieces) == 4:
                        #check each of the 4 pieces for invalidity
                        uname = pieces[1][1:]
                        wname = pieces[3][1:]
                        if (    not (pieces[0] == 'd' or pieces[0] == 'done:')
                                or not is_valid_iguname(pieces[1])
                                or pieces[2] != 'with'
                                or not is_valid_iguname(pieces[3])
                                or uname in names
                                or wname in names
                                ):
                            raise SyntaxError
                        else:
                            #remove @ from uname and wname
                            dones[i] = {'uname':uname, 'wname':wname}
                            names.add(uname)
                            names.add(wname)
                    else:
                        if not config.ALLOW_TALK:
                            raise SyntaxError
                        return
            except SyntaxError:
                self.sendMessage('grp_quiet', reply_to_message_id=msg['message_id'])
                return
            #finally if I got here there were no errors, try to check / update
            message = db.update_entries(self, msg, dones)
            #send confirm or error message
            self.sendMessage(message[0], format=message[1], reply_to_message_id=msg['message_id'])
        elif self.curr_step > 2:
            if not config.ALLOW_TALK:
                self.sendMessage('grp_idle', reply_to_message_id=msg['message_id'])
    def cmd_sendlist(self, uid, msg):
        #if gorup is not running, alert
        if not self.curr_step:
            User.answerCbq(msg, 'popup_not_runnig', show_alert=True)
            return
        #split the command into its arguments
        cmd = msg['text'].split()
        #check if it's the most current button
        if self.curr_round != int(cmd[2]):
            User.answerCbq(msg, 'popup_expired_round', show_alert=True)
        else:
            #check if user has started the bot
            try:
                bot.sendChatAction(uid, 'typing')
                User.answerCbq(msg, 'popup_sending_list', show_alert=True)
                self.send_list(uid, 'igdm')
            #if bot not started or blocked, redirect to bot
            except (telepot.exception.UnauthorizedError, telepot.exception.BotWasBlockedError, telepot.exception.TelegramError):
                User.answerCbq(msg, 'err_bot_blocked', show_alert=True)
    #what method is called for each command
    commands = {
        '/start': 'cmd_start',
        '/help': 'cmd_help',
        '/config': 'cmd_config',
        '/nextround': 'cmd_nextround',
        '/remove': 'cmd_remove',
        '/allow': 'cmd_allow',
        '/stop': 'cmd_stop',
        '/disallow': 'cmd_disallow',
        '/adv': 'cmd_advance',
        '/igdm_list': 'cmd_sendlist',
        }
def on_chat_message(msg):
    content_type, chat_type, cid, msg_date, msg_id = telepot.glance(msg, long=True)
    #ignore messages that are not text
    if content_type != 'text':
        return
    #ignore messages that have no "from" field
    if 'from' not in msg:
        return
    #ignore messages that are too old
    if time.time()-config.MAX_MSG_AGE > msg_date:
        return
    
    #welcome new users
    if content_type == 'new_chat_member' or content_type == 'new_chat_members':
        new_members = ', '.join(member['first_name'] for member in msg['new_chat_members'] if member['id'] != config.BOT_UID )
        if cid in chats and chats[cid].curr_step > 0 and new_members:
            bot.sendMessage(cid, messages['grp_new_member'].format(member=new_members))
    
    #handle the message according if it's group or private
    if chat_type == 'supergroup' or chat_type == 'group':
        threading.Thread(target=Chat.cmd, args=(msg,)).start()
    elif chat_type == 'private':
        threading.Thread(target=User.cmd, args=(msg,)).start()

def on_callback_query(msg):
    uid = msg['from']['id']
    cid = msg['message']['chat']['id'] if 'message' in msg else None
    
    #anti button spam
    if uid in btn_spammers:
        bot.answerCallbackQuery(msg['id'])
        return
    
    #add text in the message to treat is as a written command
    msg['text'] = msg['data']
    #handle the button press according if it's group or private
    if uid == cid:
        threading.Thread(target=User.cmd, args=(msg,)).start()
    elif cid:
        msg['chat'] = {'id':cid}
        threading.Thread(target=Chat.cmd, args=(msg,)).start()
def is_valid_iguname(uname):
    '''checks if a string is a valid ig username. must include the first @'''
    return (uname.startswith('@')
            and len(uname) >= 2
            and set(uname[1:]) <= config.IG_VALID_CHARS
            and not uname.endswith('.')
            )

def test_insta(uid=None):
    '''test if instagram connection is ok. send priv messages if a uid is given (manual test)'''
    if uid:
        reply = bot.sendMessage(uid, "Testing instagram connection, please wait")
    ig = Instagram(config.IG_USERNAME, config.IG_PASSWORD)
    try:
        result = ig.getUsernameId('instagram')
        if uid:
            bot.editMessageText((uid, reply['message_id']), '✅ Instagram connection looks good!')
    except InstagramException as e:
        if e.args[0].startswith('login_required') or e.args[0].startswith('Not logged in'):
            if uid:
                bot.editMessageText((uid, reply['message_id']), 'Error: login_required. Trying to login now.')
            try:
                ig.login()
                if uid:
                    bot.editMessageText((uid, reply['message_id']), 'Logged in, doing more testing.')
                ig.getUsernameId('instagram')
                if uid:
                    bot.editMessageText((uid, reply['message_id']), '✅ Instagram connection looks good!')
            except InstagramException as f:
                if f.args[0].startswith('checkpoint_required'):
                    if uid:
                        bot.editMessageText((uid, reply['message_id']), '❌ Error: checkpoint_required\nThis most likely means Instagram detected unusual login behaviour (like connect from another country) and wants to check you are legit.')
                    else:
                        return f
                else:
                    if uid:
                        bot.editMessageText((uid, reply['message_id']), '❌ Error: {}'.format(f))
                    else:
                        return f
            except Exception as f:
                if uid:
                    bot.editMessageText((uid, reply['message_id']), '❌ Error: {}'.format(f))
                else: return f
        elif e.args[0].startswith('checkpoint_required'):
            if uid:
                bot.editMessageText((uid, reply['message_id']), '❌ Error: checkpoint_required\nThis most likely means Instagram detected unusual login behaviour (like connect from another country) and wants to check you are legit.')
            else:
                return e
        else:
            raise
    except Exception as e:
        if uid:
            bot.editMessageText((uid, reply['message_id']), '❌ Error: {}'.format(e))
        else:
            return e

def html(text, reverse=False):
    '''replace <, >, &, " for its HTML entities, or reverse'''
    if reverse:
        return text.replace('&lt;','<').replace('&gt;','>').replace('&quot;','"').replace('&amp;','&')
    return text.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('"','&quot;')
def shutdown(signum, frame):
    '''exit in case of sigint/sigterm'''
    if config.POWERED_ON:
        config.POWERED_ON = False
        print('SHUTING DOWN')
        for chat in chats.values():
            print(' Stopping timer for', chat.cid)
            chat.timer.cancel()
        print(' Good bye')
        sys.exit(0)
    else:
        print('SHUT DOWN - sorry Im already shutting down')
#start everything
print('+------------------------+')
print('| Likes Bot by @fyodorob |')
print('+------------------------+')
config.POWERED_ON = True
#prepare bot to exit in case of interruptions
signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)
#init the bot but don't listen for messages yet
try:
    print('1/5 - Starting bot')
    bot = telepot.Bot(config.BOT_TOKEN)
    config.BOT_USERNAME = bot.getMe()['username']
    config.BOT_UID = config.BOT_TOKEN[:config.BOT_TOKEN.index(':')]
    print('2/5 - Started bot', config.BOT_USERNAME)
except telepot.exception.UnauthorizedError as e:
    print('2/5 - !!! ERROR INITIALIZING BOT:', e.args[0])
    print('      !!! Looks like something is wrong with the token. Fix it first and try again.')
    sys.exit(0)
#connect to db
try:
    print('3/5 - Connecting to database')
    db.initialize()
    print('4/5 - Database connected')
    #after DB is connected, boot timers
    Chat.boot_timers()
except OperationalError as e:
    print('4/5 - !!! WARNING DATABASE ERROR:', e.args[1])
    print('      !!! Bot might be responsive in private messages, but stuff will break in the group!')
#start listening for messages
if config.WEBHOOK_URL:
    from flask import Flask, request
    from telepot.loop import OrderedWebhook
    import os
    app = Flask(__name__)
    webhook = OrderedWebhook(bot, {'chat': on_chat_message,
                                  'callback_query': on_callback_query})
    
    @app.route('/', methods=['POST', 'GET'])
    def root():
        return '<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 3.2 Final//EN"><title>404 Not Found</title><h1>Not Found</h1><p>The requested URL was not found on the server.  If you entered the URL manually please check your spelling and try again.</p>'
    
    @app.route('/'+config.BOT_TOKEN, methods=['POST'])
    def pass_update():
        webhook.feed(request.data)
        return 'OK'
    
    if __name__ == "__main__":
        bot.setWebhook(config.WEBHOOK_URL + ('' if config.WEBHOOK_URL[-1].endswith('/') else '/') + config.BOT_TOKEN,
            allowed_updates=['message', 'callback_query'])
        webhook.run_as_thread()
        print("5/5 - Now listening for messages")
        app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
else:
    from telepot.loop import MessageLoop
    bot.deleteWebhook()
    MessageLoop(
            bot,
            {
                'chat': on_chat_message,
                'callback_query': on_callback_query,
            },
        ).run_as_thread(allowed_updates=['message', 'callback_query'])
    print("5/5 - Now listening for messages")
    while True:
        time.sleep(10)
#end
