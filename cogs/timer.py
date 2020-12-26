#  PROJECT : bdiscord
#  FILE : timer.py
#  LAST MODIFIED : 04-12-2020
#  AUTHOR : Sam (sam@hey.com)
#
#
#  Copyright (c) 2020, Sam (sam@hey.com)


import asyncio
import asyncpg
import datetime
import getopt
import logging
from pathlib import Path
import re

from discord import Permissions, Forbidden
from discord.ext import commands, tasks
from discord import utils
import discord

import __init__
import uutils as u
from utils import converters as conv, db, embed

logger = u.get_logger(__name__)
logger.parent.setLevel(logging.DEBUG)


class TimerTable(db.Table, table_name='timers'):
    columns = [
        'id SERIAL PRIMARY KEY',
        'event TEXT NOT NULL',
        'created_at TIMESTAMP DEFAULT (now() at time zone \'UTC\')',
        'expires TIMESTAMP',
        'times JSONB DEFAULT (\'[]\'::JSONB)',
        'extra JSONB DEFAULT (\'{}\'::JSONB)',
    ]
    indexes = [{'name': 'expires_idx', 'col': 'expires'}]


class TimerConfig(db.ConfigBase):
    __slots__ = ('id', 'event', 'created_at', 'expires', 'times', 'args', 'kwargs')

    @classmethod
    def from_record(cls, record):
        self = cls()
        print(record)
        self.id = record['id']
        self.event = record['event']
        self.created_at = record['created_at']
        self.expires = record['expires']
        self.times = record['times']
        self.args = record['extra'].get('a', [])
        self.kwargs = record['extra'].get('kw', {})

        print('returning with record...')

        return self


# class GuildChannelConverter(commands.Converter):
#
#     async def convert(self, ctx, argument):
#         bot = ctx.bot
#         guild, channel = argument.split('<separator>')
#
#         if guild:
#             check = 'name id'.split()[guild.isdigit()]
#
#             if _guild := utils.find(lambda g: guild.lower() == str(getattr(g, check)).lower(), bot.guilds):
#                 if ctx.author in _guild.members:
#                     ctx.guild = _guild
#                 else:
#                     raise NotInDestinationGuild(_guild)
#             else:
#                 raise GuildNotFound(guild)
#         channel = await commands.TextChannelConverter().convert(ctx, channel)
#
#         for user, perm in zip((ctx.author, channel.guild.me),
#                               ('MissingPermissions', 'BotMissingPermissions')):
#             if not channel.permissions_for(user).send_messages:
#                 raise getattr(commands, perm)(['send_messages'], channel, ctx.guild)
#
#         return channel


def time_parser(times):
    t = []
    pattern = re.compile(r'(?P<hm>\d(?:h)\d{1,2}(?:m))|'
                         r'(?P<h>\d(?:h))|(?P<t>\d{1,2}(?::)\d{1,2})|'
                         r'(?P<s>\d{1,4}(?:s))|(?P<m>\d{1,3})')

    for time in times.split():
        res = re.match(pattern, time)
        if res:
            print(res.lastgroup, *map(int, re.sub(r'\D', ' ', res.group()).split()))
            if 't' in res.lastgroup:
                t.append(datetime.time.fromisoformat(res.group()))
            else:
                d = {}
                for i, v in zip(res.lastgroup, map(int, re.sub(r'\D', ' ', res.group()).split())):
                    d[i.replace('s', 'seconds').replace('m', 'minutes').replace('h', 'hours')] = v
                t.append(datetime.datetime.utcnow() + datetime.timedelta(**d))
    return t


# class TimerConverter(commands.Converter):
#
#     async def convert(self, ctx, argument):
#         # pattern = re.compile(r'(?P<guild>-s.*?\w[\w \']+\w).*?(?=$|-)|'
#         #                      r'(?P<channel>-c.*?\w[\w \']+\w).*?(?=$|-)|'
#         #                      r'(?P<message>-m.*?\w[\w \']+\w).*?(?=$|-)|'
#         #                      r'(?P<times>-t.*?\w[\w \']+\w).*?(?=$|-)')
#         # pattern = re.compile(r'(-\w.*?\w[\w \']+\w).*?(?=$|-)')
#         res = re.findall(r'-(\w.*?\w?[\w \']*\w).*?(?=$|-)', argument)
#
#         opts = {r[0]: r[2:] for r in res}
#
#         guild = opts.get('s', None)
#         channel = opts.get('c', None)
#         message = opts.get('m', None)
#         times = time_parser(opts.get('t', None))
#
#         guild = await conv.GuildConverter().convert(ctx, guild)
#         if guild:
#             ctx.guild = guild
#         channel = await commands.TextChannelConverter().convert(ctx, channel)
#         # channel = await GuildChannelConverter().convert(ctx, f'{guild}<separator>{channel}')
#
#         return channel, message, times


class TimerConverter(commands.Converter):

    async def convert(self, ctx, argument):
        print(argument)
        times, msg = argument.split(' <sep> ')
        self.times = time_parser(times)
        self.extra = [msg, ctx.channel.id]
        return self


class Timer(commands.Cog, name=Path(__file__).stem):

    def __init__(self, bot):
        self.bot = bot
        self._have_data = asyncio.Event()
        self._current_timer = None
        self._task = asyncio.get_event_loop().create_task(self.dispatch_timers())

    def cog_unload(self):
        self._task.cancel()

    async def cog_command_error(self, ctx, error):
        print(error)

    async def get_active_timer(self, *, days=7):
        query = '''SELECT * FROM timers WHERE expires < (CURRENT_TIMESTAMP + $1::INTERVAL) ORDER BY expires LIMIT 1'''
        async with self.bot.pool.acquire() as conn:
            record = await conn.fetchrow(query, datetime.timedelta(days=days))
            if record:
                print('about to return...')
                return TimerConfig.from_record(record)
            return None

    async def dispatch_timers(self):
        try:
            while not self.bot.is_closed():
                print('trying to get the timer')
                timer = self._current_timer = await self.wait_for_active_timers(days=40)
                print('timer', timer)
                now  = datetime.datetime.utcnow()
                print('now', now)
                if timer.expires >= now:
                    print('is ready to be expired')
                    await asyncio.sleep((timer.expires - now).total_seconds())

                print('is already expired')
                await self.call_timer(timer)
        except asyncio.CancelledError as e:
            print('>', e)
            # raise
        except (OSError, asyncpg.PostgresConnectionError, discord.ConnectionClosed) as e:
            print(e)
            self._task.cancel()
            self._task = asyncio.get_event_loop().create_task(self.dispatch_timers())
        print('here')

    async def wait_for_active_timers(self, days=7):
        print('in waiting...')
        timer = await self.get_active_timer(days=days)
        print(timer)
        if timer is not None:
            print('data is being set')
            self._have_data.set()
            return timer

        print('timer is NOne 0_o')
        self._have_data.clear()
        self._current_timer = None
        print('Waiting', '*' * 30)
        await self._have_data.wait()
        print('Done waiting', '*' * 30)
        return await self.get_active_timer(days=days)

    async def call_timer(self, timer):
        print('skipping timer in call_timer')
        print(await self._skip_timer(timer.id))
        print('dispatching?')
        self.bot.dispatch(f'{timer.event}_timer_complete', timer)


    async def _set_timer(self, *a, **kw):
        print(a)
        event, times, args = a
        expires, *times = times
        if isinstance(expires, str):
            print('str')
            expires = datetime.datetime.fromisoformat(expires)
        print('setting the timer up here')
        print(event, expires, times, args)
        print(kw)
        try:
            created_at = kw.pop('created_at')
        except KeyError:
            created_at = datetime.datetime.utcnow()

        try:
            _id = kw.pop('id')
        except KeyError:
            _id = None

        *times, = map(str, times)

        # ugly and, hopefully, safe insert (`_id` is only set internally)
        # other than this, I haven't found \ come up with anything else
        cols = 'id event created_at times extra expires'.split()[not bool(_id):]
        # query = f'''INSERT INTO timers (id, event, created_at, times, extra, expires)
        # VALUES ({['DEFAULT',_id][bool(_id)]}, $1, $2, $3, $4, $5)'''
        query = f'''INSERT INTO timers ({', '.join(cols)}) 
                VALUES ({', '.join(f"${i}" for i, _ in enumerate(cols, 1))})'''
        print(query)
        payload = [_id, event, created_at, times, {'a': args, 'kw': kw}, expires][not bool(_id):]
        async with self.bot.pool.acquire() as conn:
            print('new timer creation')
            print(event, created_at, times, {'a':args, 'kw':kw}, expires)
            try:
                # res = await conn.execute(query, event, created_at, times, {'a': args, 'kw': kw}, expires)
                res = await conn.execute(query, *payload)
            except Exception as e:
                print(e)
            print('new timer created')
        if (expires - created_at).total_seconds() < 86400 * 40:
            print('_have_data is being set up')
            self._have_data.set()
            print('_have_data set')

        print(self._current_timer)

        if self._current_timer and expires < self._current_timer.expires:
            print('here')
            self._task.cancel()
            self._task = asyncio.get_event_loop().create_task(self.dispatch_timers())

        record_timer = {
            'id': _id,
            'event': event,
            'created_at': created_at,
            'expires': expires,
            'times': times,
            'extra': {'a': args, 'kw': kw}
        }

        print('hete')

        return TimerConfig.from_record(record_timer)

    @commands.group(name='timer', invoke_without_command=True)
    async def timer(self, ctx):
        # put `timer list` in here?
        pass

    @timer.command(name='set')
    async def set_timer(self, ctx, *, args: TimerConverter):  # TODO parser
        """Sets the timer: <times> <message> [-c channel]

        The timer can either be one-shot or with multiple times, i.e. `timer set 5s 10s` will
        blast two times: in 5 seconds and in 10 seconds

        Optional arguments:
            -c - destination timer channel (one should be in the channel's server and has "Send Messages" permission)
                 (defaults to the current)

        """
        timer = await self._set_timer('this', args.times, args.extra, created_at=ctx.message.created_at,
                                      author_id=ctx.author.id, message_id=ctx.message.id)
        await ctx.send('The timer is set')

    @timer.command(name='skip', aliases=['delete', 'cancel'])
    async def skip_timer(self, ctx, id: int, times: int = 1):
        """Skip the timer with given ID given number of times

        If the `times` is greater than the the remaining number of blasts, the timer
        is cancelled.
        If invoked with `delete` or `cancel`, deletes the timer despite the number of
        remaining blasts
        """
        times = max(1, times)
        if ctx.invoked_with in ('delete', 'cancel'):
            times = 0

        if not ctx.author.permissions_in(ctx.channel).manage_messages:
            query = '''DELETE FROM timers WHERE id=$1 AND event='this' AND extra#>'{"kw","author_id"}'=$2'''
            q_args = [id, ctx.author.id]
            res = await self._skip_timer(q_args, times=times, delete=True, query=query)
        else:
            res = await self._skip_timer(id, times=times, delete=True)
        await ctx.send(res)

    async def _skip_timer(self, q_args, times: int = 1, delete=False, query=None):
        # is this even needed?
        if not delete and times < 1:
            raise ValueError(f'Times ({times}) cannot be less than 1!')
        if not query:
            query = '''DELETE FROM timers WHERE id=$1 RETURNING *'''
        if not isinstance(q_args, list):
            q_args = [q_args]

        print('_skip_timer before conn')
        async with self.bot.pool.acquire() as conn:
            print('about to delete and receive the record in _skip_timer')
            records = await conn.fetch(query, *q_args)
            if not records:
                # `clear_timers` doesn't use id as its q_args...
                # not anymore, since UX has been applied
                return f'Couldn\'t find the timer with ID {q_args[0]}'
            # shifting: the next time in `record.times` becomes `record.expires`
            # in, actually, _set_timer during argument parsing
            msg = ''
            for record in records:
                timer = TimerConfig.from_record(record)
                if not times:
                    timer.times = []
                timer.times = timer.times[times-1:]
                print('timer\'s times', timer.times)
                if timer.times:
                    # `timer.id` is passed as I want the timer to preserve its id (when it is a repetitive one)
                    timer = await self._set_timer(timer.event, timer.times, timer.args, **timer.kwargs,
                                                  created_at=timer.created_at, id=timer.id)
                    msg += f'Timer (ID {timer.id}) was successfully skipped {times} time{"s"*(times > 1)}\n'
                else:
                    msg += f'Timer (ID {timer.id}) is exhausted\n'

                # `delete` is needed to actually delete the current timer, i.e. to skip the one, that is running
                # right now. It is only set on user's `skip_timer` command, because `_skip_timer` is also
                # an internal 'down-counter'. If there was no `delete`, `call_timer` couldn't dispatch
                # the last timer, as the task would've been cancelled -> no dispatch in `call_timer`

                # `delete` actually deletes the timer: it is not in the db anymore (see query above),
                # only a variable. Cancelling the task would clear this variable by setting new value
                # to it in `dispatch_timers`. If `delete` is False, then this is skipped and the func
                # just slices `timer.times` (skipping)

                # Why not running it without delete? `call_timer` precedes this function,
                # if the current timer is canceled, `call_timer` cannot run as well

                # This function acts as a 'down counter' for the timer: `expires` + `times` are
                # its 'counter value'. When the func is called, `times[0]` becomes `expires` and
                # `times` becomes `times[1:]` (if `kw_times==1`) -> subtracting the counter.
                # If there was no `delete`, the 'counter' would've been ended on 0, but, without
                # doing the subsequent function (`dispatch` in this case), which is not logical:
                # the timer exists, but doesn't call the func, why was it run then?
                # This problem might've been solved with changing the order in which functions
                # are called: `dispatch`, `_skip_timer` instead of `_skip_timer`, `dispatch`,
                # but I decided this might not be the right decision: the `dispatch` calls
                # another async func, which might take some time to finish, during which another
                # timer might be ready to blast, however it wouldn't be able to, since the other
                # is still pending as the current one -> who needs stale timers?

                # If used with `times = 0`, the current timer is cancelled, while the new one is
                # waiting for its turn in the db, which, may be the next `_current_timer`
                if delete and self._current_timer and self._current_timer.id == timer.id:
                    self._task.cancel()
                    self._task = asyncio.get_event_loop().create_task(self.dispatch_timers())
            return msg


    @timer.command(name='list')
    async def list_timers(self, ctx):
        """Lists all of your timers despite the channel"""
        query = '''SELECT * FROM timers WHERE event='this' AND
         extra #> '{"kw","author_id"}'=$1 ORDER BY expires LIMIT 10'''
        async with ctx.acquire():
            records = await ctx.con.fetch(query, ctx.author.id)

        title = f"You{[' have no', 'r'][bool(records)]} timers, "
        e = embed.Embed(timestamp=ctx.message.created_at, title=title)
        e.set_footer(author=ctx.author)
        for record in records:
            record = TimerConfig.from_record(record)
            e.add_field(name=f'ID {record.id} in {(record.expires - datetime.datetime.utcnow()).seconds} secs',
                        value=f'**{["One-shot timer**",f"With remaining blasts:** {record.times}"][bool(record.times)]}\n{record.args[0]}')
        await ctx.send(embed=e)

    @timer.command(name='clear')
    async def clear_timers(self, ctx):
        """Removes all of your timers despite the channel"""
        # is running two queries good? The other one is in `_skip_timer`
        # might use two queries for the UX purposes, i.e. for action confirmation?
        query = '''SELECT id FROM timers WHERE event='this' AND extra #> '{"kw", "author_id"}'=$1'''
        async with ctx.acquire():
            res = await ctx.con.fetch(query, ctx.author.id)
        if not res:
            await ctx.send('You have no timers to delete')
        else:
            confirm = await ctx.prompt(f'You\'re about to delete all of your timers, IDs: '
                                       f'{", ".join(map(lambda _:str(_["id"]),res))}\nAre you sure?')
            _ = {
                None: 'Took you way too long to decide, try again when you\'re morally ready',
                True: 'All your timers are successfully gone!',
                False: 'Darn! All that work is for nothing?.. Hope you had a very good reason'
            }
            if confirm:
                for record in res:
                    await self._skip_timer(record['id'], delete=True, times=0)
            await ctx.send(_[confirm])
            # msg = await ctx.send(f'You\'re about to delete all of your timers, IDs: {", ".join(*map(lambda _:str(_["id"]),res))}\nAre you sure?')
            # await msg.add_reaction(ctx.tick(True))
            # await msg.add_reaction(ctx.tick(False))
            #
            # confirm = None
            #
            # def ch(payload):
            #     nonlocal confirm
            #     if payload.message_id == msg.id and payload.user_id == ctx.author.id:
            #         if str(payload.emoji) == str(ctx.tick(True)):
            #             confirm = True
            #             return True
            #         elif str(payload.emoji) == str(ctx.tick(False)):
            #             confirm = False
            #             return True
            #     return False
            #
            # try:
            #     await self.bot.wait_for('raw_reaction_add', timeout=15.0, check=ch)
            #     print('here')
            # except asyncio.TimeoutError:
            #     await ctx.send('Took you way too long to decide, try again when you\'re morally ready')
            # else:
            #     if confirm:
            #         for record in res:
            #             await self._skip_timer(record['id'], delete=True, times=0)
            #         await ctx.send('All your timers are successfully gone!')
            #     else:
            #         await ctx.send('Darn! All that work is for nothing?.. Hope you had a very good reason')

        # query = '''DELETE FROM timers WHERE event='this' AND extra #> '{"kw", "author_id"}'=$1 RETURNING *'''
        # msg = await self._skip_timer(ctx.author.id, query=query, delete=True, times=0)
        # # startswith 'C' means, there are no timers (see _skip_timer)
        # await ctx.send('You don\'t have any timers set' if msg.startswith('C') else 'All your timers are gone')

    @timer.command(name='info')
    async def info_timer(self, ctx, *, id: int):
        """Return the info about the timer with the given ID"""
        query = '''SELECT * FROM timers WHERE id=$1 AND event='this' and extra #> '{"kw", "author_id"}'=$2'''
        async with ctx.acquire():
            record = await ctx.con.fetchrow(query, id, ctx.author.id)
        if not record:
            return await ctx.send(f'Couldn\'t find the timer with the ID {id}')

        record = TimerConfig.from_record(record)
        e = embed.Embed(title=f'Info about timer ID {id}', timestamp=ctx.message.created_at)
        e.set_footer(author=ctx.author)
        e.add_field(name='Blast in', value=f'{(record.expires - datetime.datetime.utcnow()).seconds} seconds', inline=False)
        e.add_field(name='Message', value=record.args[0], inline=False)
        e.add_field(name='Remaining blasts', value=record.times, inline=False)
        await ctx.send(embed=e)

    @timer.command(name='channel')
    @commands.has_permissions(manage_messages=True)
    async def channel_timers(self, ctx):
        """Returns the list of timers, that will be run in this channel"""
        query = '''SELECT * FROM timers WHERE event='this' AND extra #> '{"a",1}'=$1'''
        async with ctx.acquire():
            records = await ctx.con.fetch(query, ctx.channel.id)
        if not records:
            return await ctx.send('This channel has no timers set')

        e = embed.Embed(title='This channel\'s timers', timestamp=ctx.message.created_at)
        e.set_footer(author=ctx.author)
        guild_id = lambda _:ch.guild.id if isinstance(ch:=self.bot.get_channel(_),discord.TextChannel)else'@me'
        e.description = '\n'.join(f'[`ID {r.id}, set by`](https://discordapp.com/channels/'
                                  f'{guild_id(ch:=r.args[1])}/{ch}/{(kw:=r.kwargs)["message_id"]})'
                                  f' {self.bot.get_user(kw["author_id"]).mention}'
                                for r in map(TimerConfig.from_record, records))
        # for record in records:
        #     record = TimerConfig.from_record(record)
        #     e.add_field(name=f'ID {record.id}', value=f'Set by {self.bot.get_user(record.kwargs["author_id"]).display_name}', inline=False)
        await ctx.send(embed=e)

    @timer.command(name='current')
    @commands.is_owner()
    async def current_timer(self, ctx):
        if self._current_timer is None:
            await ctx.send('There is no current timer')
        else:
            await ctx.send(self._current_timer)

    @commands.Cog.listener()
    async def on_this_timer_complete(self, timer):
        print('ON THIS TIMER COMPLETE')
        print(timer)
        msg, channel = timer.args
        channel = self.bot.get_channel(channel)
        await channel.send(f'Timer alarm with time {(datetime.datetime.utcnow() - timer.created_at).seconds} seconds: {msg}')

    @timer.error
    async def timer_error(self, ctx, error):
        if isinstance(error, commands.ChannelNotFound):
            await ctx.send(f'Channel "{error.argument}" wasn\'t found among text channels in server "{ctx.guild}"')
        elif isinstance(error, conv.NotInDestinationGuild):
            await ctx.send(error)
        elif isinstance(error, commands.MissingPermissions):
            if 'send_messages' in error.missing_perms:
                await ctx.send(f'You don\'t have the "Send Messages" permission in the channel "{error.args[1].name}" '
                               f'of server "{error.args[2].name}"')
            else:
                await ctx.send(error)
        elif isinstance(error, commands.BotMissingPermissions):
            if 'send_messages' in error.missing_perms:
                await ctx.send(f'I don\'t have the "Send Messages" permission in the channel "{error.args[1].name}"  '
                               f'of server "{error.args[2].name}"')
            else:
                await ctx.send(error)
        else:
            await ctx.send(error)


def setup(bot):
    bot.add_cog(Timer(bot))
