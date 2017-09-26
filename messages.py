'''All the messages sent by the bot are here. It follows the pattern:

       "message_code":
       """message to be sent and {placeholder}"""

   {placeholders} are dynamically replaced by something else before being sent.
   
   It's ok to remove a placeholder completely.
   
   Adding a new placeholder, changing a placeholder's code, or changing the
   message_code WILL BREAK the message and the bot won't be able to send it.
   
   The only HTML tags supported are <b>, <i>, <code> and <a href="...">. Any
   other tag, as well as nesting and unclosed tags are not supported and WILL
   BREAK the message. If you want to send "<" or ">" use "&lt;" and "&gt;" instead.
'''


messages = {
"grp_allow":
"""I am allowed in this group. An admin can /start, or /disallow."""

,"grp_in_use":
"""I am already working in another group. /disallow me there first."""

,"grp_running":
"""I am running in this group. An admin can /stop or /disallow."""

,"grp_stop":
"""I am stopped in this group. An admin can /start or /disallow."""

,"grp_disallowed":
"""I am not allowed in this group. An admin must /allow me here first."""

,"grp_new_member":
"""Hello, {member}, welcome to the group. Please read the pinned message."""

,"grp_step1":
"""❤️ LIKE RECENT ROUND ❤️
Round akan dimulakan dalam masa {m} minit.

❤️ D R O P - <b>@username</b>
── OR ──
❤️ D R O P - <b>@username</b> with <b>@givinglikes</b>

Untuk keluar dari round lepas anda dah drop name, type /remove <b>@username</b>"""

,"grp_step1.5":
"""❤️ DROP IG USERNAME SEKARANG ❤️"""

,"grp_step2":
"""❤️ MASA DROP SUDAH TAMAT ❤️

👁🗨ROUND INFO👁🗨
Participants: {participants}
Accounts: {accounts}
DM Lists: {igdm_lists}"""

,"grp_step2.5":
"""❤️❤️ LIKE Post Terbaru Sahaja ❤️❤️
Bagi yang pertama kali join round:
1. Private message BOT dan type /start
2. Pergi ke ROUND GROUP dan KLIK UTK DAPATKAN LIST di atas
3. BOT akan PM senarai akaun untuk di LIKE
.
Pastikan anda selesai LIKE dalam masa {timeleft}!
Sesiapa yg drop nama tapi tidak LIKE akaun dalam list = BAN.

PM admins for any issues"""

,"grp_step3":
"""Checking Leechers!

NEXT AUTO ROUND @ {nextsched} (UTC{tz:+d})
Dropping starts {m} minutes before."""

,"grp_nextround":
"""👉👉 Next round akan bermula dalam masa: {hms} 👈👈
Dropping starts {m} minutes before."""

,"grp_baddrop":
"""Please drop correctly: <b>@example</b>"""

,"grp_gooddrop":
"""Joined this round"""

,"grp_badremove":
"""Please remove one at a time: <b>/remove @example</b>"""

,"grp_removeok":
"""Removed: <b>@{igname}</b>"""

,"grp_quiet":
"""Please don't speak here!"""

,"grp_idle":
"""No Current Round!"""

,"grp_doneok":
"""Done: [<b>@{igname}</b>]"""

,"grp_doneok_with":
"""Done: [<b>@{igname}</b> engaged with: <b>@{igwith}</b>]"""

,"grp_leecher":
"""LEECHER: <a href="tg://user?id={uid}">{name}</a>"""

,"grp_banned":
"""BANNED: <a href="tg://user?id={uid}">{name}</a>"""

,"err_removebad":
"""ERROR: <b>@{igname}</b> not found! anda hanya boleh remove jika anda dah drop utk join round kali ini!"""

,"err_donebad":
"""ERROR: <b>@{igname}</b> not found or it's not dropped by you!"""

,"err_duplicate":
"""ERROR: <b>@{igname}</b> was already dropped."""

,"err_bot_blocked":
"""/start me privately first, then press this button again."""

,"btn_igdm_lists":
"""KLIK UTK DAPATKAN LIST"""

,"prv_hello":
"""Hello, I am a round bot."""

,"prv_lists_header":
"""SENARAI AKAUN UNTUK ROUND INI"""

,"prv_lists_igdm":
"""List {page} of {total}
<b>{usernames}</b>"""

,"prv_lists_footer":
"""Pastikan anda LIKE semua akaun dalam list ni. Kegagalan 2x = BAN"""

,"prv_adm_help":
"""Group commands:
/allow * allow the bot to function in a group
/disallow * remove permission for group
/start * start rounds according to settings
/stop * abort current round and wait for start
/adv * immediately advances to the next step
/nextround - time left for next round

Private commands:
/ban <b>@username</b> * bans the user with that TG username
/unban <b>@username</b> * unbans the user with that TG username
/dropped * lists all names dropped for this round so far
/ig * check instagram connection
/debug * turn on/off sending detailed leecher percentage messages
/talk * turn on/off sending "don't talk" or correction messages
/help * show this message (admin only)
/start or /help - show intro message

*: can only be used by admins"""

,"popup_not_runnig":
"""This group is not running."""

,"popup_sending_list":
"""I'm sending you the lists now."""

,"popup_expired_round":
"""This round has already expired."""
}
