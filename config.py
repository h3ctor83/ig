'''
   Add the environment variables "BOT_TOKEN", "IG_USERNAME", etc with the
   respective information.
'''
import os
BOT_TOKEN = os.environ['BOT_TOKEN']                    #bot token
IG_USERNAME = os.environ['IG_USERNAME']                #instagram username
IG_PASSWORD = os.environ['IG_PASSWORD']                #instagram password
DATABASE_URL = os.environ['JAWSDB_URL']                #full url for mysql database (with credentials)
WEBHOOK_URL = os.environ['WEBHOOK_URL']                #your app's address e.g. https://yourapp.herokuapp.com/
LEECHER_CHECKERS = int(os.environ['LEECHER_CHECKERS']) #how many accounts to check at the same time. I don't know if IG might block you if set too high

'''
   If you are hosting the bot on a personal computer, add the bot's token, etc
   below. Also, delete the "#" of the next lines and all lines above this
'''
#BOT_TOKEN = ""
#IG_USERNAME = ""
#IG_PASSWORD = ""
#DATABASE_URL = 'mysql://user:password@localhost/test'
#WEBHOOK_URL = None
#LEECHER_CHECKERS = 10

'''
   Add to this list the Telegram user ids of all people who should be able to
   administer the bot (start / stop groups, etc). You can get your user id by
   talking to @myidbot
   Also, every admin will receive a warning via private message in the event of
   an error that prevents the bot from checking the leechers
'''
ADMINS = [
    231234498, #you can write a name for each admin after a "#"
    238537969, #Noel
    ]

'''Settings applicable to the group'''
ROUND_SCHED = "12 18 21 24" #local hours when to start a new round. No fractions. Separate with space
PERCENTAGE_TO_LEECH = 20    #if a user fails to like this % of names, count as a leech
LEECHES_TO_BAN = 2          #when a user leeches this many rounds, he is banned
ALLOW_TALK = 1              #allow off-topic conversations without any nagging (0 for OFF, or 1 for ON)
STEP1_LEN = 1800            #seconds to spend collecting drops. This starts before the scheduled round time
STEP1_CALLS = 300           #seconds between reminders to drop. Default = 600
STEP2_LEN = 3600            #seconds users have to do the liking (waiting for "dones"). Default = 3600
TIMEZONE = +8               #UTC+X of the group's time zone

'''More general bot settings'''
IG_VALID_CHARS = set('abcdefghijklmnopqrstuvwxyz1234567890_.') #valid characters for an instagram username
MAX_MSG_AGE = 30            #to avoid flood when bot comes online, only accept messages younger than this [seconds]
DEBUG_LEECHER_MESSAGE = 0   #Send leecher statistics after checking (0 for OFF, or 1 for ON)
