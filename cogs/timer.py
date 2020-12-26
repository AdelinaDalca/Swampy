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
import traceback
import re

from discord import Permissions, Forbidden
from discord.ext import commands, tasks
from discord import utils
import discord

import __init__
import uutils as u
from utils import converters as conv, db, embed, time
from utils.formats import human_delta, hjoin


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

        self.id = record['id']
        self.event = record['event']
        self.created_at = record['created_at']
        self.expires = record['expires']
        self.times = record['times']
        self.args = record['extra'].get('a', [])
        self.kwargs = record['extra'].get('kw', {})

        return self


class Timer(commands.Cog, name=Path(__file__).stem):

    def __init__(self, bot):
        self.bot = bot
        self._have_data = asyncio.Event()
        self._current_timer = None
        self._task = asyncio.get_event_loop().create_task(self.dispatch_timers())

    def cog_unload(self):
        self._task.cancel()

    async def get_ch_g(self, channel, attr='id'):
        if isinstance(channel, int):
            try:
                channel = self.bot.get_channel(channel) or await self.bot.fetch_channel(channel)
            except discord.HTTPException:
                # if the channel was deleted, for instance
                return None, None
        if isinstance(channel, discord.DMChannel):
            return channel, '@me'
        return channel, getattr(channel.guild, attr)

    async def cog_command_error(self, ctx, error):
        print('here')
        print(error)

    async def get_active_timer(self, *, days=7):
        query = '''SELECT * FROM timers WHERE expires < (CURRENT_TIMESTAMP + $1::INTERVAL) ORDER BY expires LIMIT 1'''
        async with self.bot.pool.acquire() as conn:
            record = await conn.fetchrow(query, datetime.timedelta(days=days))
            if record:
                return TimerConfig.from_record(record)
            return None

    async def dispatch_timers(self):
        try:
            while not self.bot.is_closed():
                timer = self._current_timer = await self.wait_for_active_timers(days=40)
                now = datetime.datetime.utcnow()
                if timer.expires >= now:
                    await asyncio.sleep((timer.expires - now).total_seconds())

                await self.call_timer(timer)
        except asyncio.CancelledError:
            # Y?
            raise
        except (OSError, asyncpg.PostgresConnectionError, discord.ConnectionClosed) as e:
            self._task.cancel()
            self._task = asyncio.get_event_loop().create_task(self.dispatch_timers())

    async def wait_for_active_timers(self, days=7):
        timer = await self.get_active_timer(days=days)
        if timer is not None:
            self._have_data.set()
            return timer

        self._have_data.clear()
        self._current_timer = None
        await self._have_data.wait()
        return await self.get_active_timer(days=days)

    async def call_timer(self, timer):
        await self._skip_timer(timer.id)
        self.bot.dispatch(f'{timer.event}_timer_complete', timer)


    async def _set_timer(self, *a, **kw):
        event, times, args = a

        if not times:
            raise discord.InvalidArgument("Invalid time provided")

        expires, *times = times
        if isinstance(expires, str):
            expires = datetime.datetime.fromisoformat(expires)
        created_at = kw.pop('created_at', datetime.datetime.utcnow())
        _id = kw.pop('id', None)

        *times, = map(str, times)

        # ugly and, hopefully, safe insert (`_id` is only set internally)
        # other than this, I haven't found \ come up with anything else
        cols = 'id event created_at times extra expires'.split()[not bool(_id):]
        query = f'''INSERT INTO timers ({', '.join(cols)}) 
                VALUES ({', '.join(f"${i}" for i, _ in enumerate(cols, 1))})'''
        payload = [_id, event, created_at, times, {'a': args, 'kw': kw}, expires][not bool(_id):]

        async with self.bot.pool.acquire() as conn:
            res = await conn.execute(query, *payload)

        if (expires - created_at).total_seconds() < 86400 * 40:
            self._have_data.set()

        if self._current_timer and expires < self._current_timer.expires:
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

        return TimerConfig.from_record(record_timer)

    @commands.group(name='timer', invoke_without_command=True)
    async def timer(self, ctx):
        # put `timer list` in here?
        pass

    @timer.command(name='set')
    async def set_timer(self, ctx, *, args: time.TimerConverter):  # TODO parser
        """Sets the timer: <times> <message> [-c channel]

        The timer can either be one-shot or with multiple times, i.e. `timer set 5s 10s` will
        blast two times: in 5 seconds and in 10 seconds

        Optional arguments:
            -c - destination timer channel (one should be in the channel's server and has "Send Messages" permission)
                 (defaults to the current)

        """
        times, message, ch = args
        timer = await self._set_timer('this', times, (message, ch.id), created_at=ctx.message.created_at,
                                      author_id=ctx.author.id, message_id=ctx.message.id)
        if ch == ctx.channel:
            dest = "**this channel**"
        else:
            dest = f"channel **{ch}** of **{ch.guild}** server"
        # TODO blast in 'this guild other channel'?
        #  or to change only if ctx.channel != ch?
        await ctx.send(f'The timer is set! In {hjoin([*map(human_delta, times)])} with the following message {message!r}\n'
                       f'Await the blast in {dest}')

    @set_timer.error
    async def on_set_timer_error(self, ctx, error):
        error = getattr(error, 'original', error)

        if isinstance(error, discord.InvalidArgument):
            await ctx.send(error)
        elif isinstance(error, commands.MissingRequiredArgument):
            pass
            # await ctx.send(error)
        elif isinstance(error, commands.ChannelNotFound):
            await ctx.send(f'Channel **{error.argument}** wasn\'t found')
        elif isinstance(error, conv.GuildNotFound):
            await ctx.send(error)
        elif isinstance(error, conv.NotInDestinationGuild):
            await ctx.send(error)
        else:
            await ctx.send("".join(traceback.format_exception(type(error), error, error.__traceback__)))

    @timer.command(name='skip', aliases=['delete', 'cancel'])
    async def skip_timer(self, ctx, *, id: int, times: int = 1):
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

        async with self.bot.pool.acquire() as conn:
            records = await conn.fetch(query, *q_args)
            if not records:
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
            e.add_field(name=f'ID {record.id} in {human_delta(record.expires)}',
                        value=f'**{["One-shot timer**",f"With remaining blasts:** {chr(10).join(map(human_delta, record.times))}"][bool(record.times)]}\n'
                              f'_Message_: {record.args[0]}')
        await ctx.send(embed=e)

    @timer.command(name='clear')
    async def clear_timers(self, ctx):
        """Removes all of your timers despite the channel"""
        query = '''SELECT id FROM timers WHERE event='this' AND extra #> '{"kw", "author_id"}'=$1'''
        async with ctx.acquire():
            res = await ctx.con.fetch(query, ctx.author.id)
        if not res:
            await ctx.send('You have no timers to delete')
        else:
            confirm = await ctx.prompt(f'You\'re about to delete all of your timers, IDs: '
                                       f'{", ".join(map(lambda _:str(_["id"]),res))}\nAre you sure?', delete_after=True)
            _ = {
                None: 'Took you way too long to decide, try again when you\'re morally ready',
                True: f'All ({len(res)}) of your timers are successfully gone!',
                False: 'Darn! All that work is for nothing?.. Hope you had a very good reason'
            }
            if confirm:
                for record in res:
                    await self._skip_timer(record['id'], delete=True, times=0)
            await ctx.send(_[confirm])

    @timer.command(name='info')
    async def info_timer(self, ctx, *, id: int):
        """Return the info about the timer with the given ID"""
        query = '''SELECT * FROM timers WHERE id=$1 AND event='this' and extra #> '{"kw", "author_id"}'=$2'''
        async with ctx.acquire():
            record = await ctx.con.fetchrow(query, id, ctx.author.id)
        if not record:
            return await ctx.send(f'Couldn\'t find the timer with the ID {id}')

        record = TimerConfig.from_record(record)
        ch, g = await self.get_ch_g(record.args[1], 'name')
        if not ch:
            # this shouldn't happen, since I delete all the messages
            # from the deleted channels, but who knows
            logger.exception('Channel and guild are None, timer wasn\'t deleted '
                             'when the channel was?')
            return

        e = embed.Embed(title=f'Info about timer ID {id}', timestamp=ctx.message.created_at)
        e.set_footer(author=ctx.author)
        e.add_field(name='Blast in', value=f'{human_delta(record.expires)}', inline=False)
        e.add_field(name='Message', value=record.args[0], inline=False)
        if record.times:
            e.add_field(name='Remaining blasts', value='\n'.join(map(human_delta, record.times)), inline=False)
        e.add_field(name='Origin', value=f'{ch}' + f' in {g}' * (not isinstance(ch, discord.DMChannel)))
        await ctx.send(embed=e)

    @timer.command(name='channel')
    async def channel_timers(self, ctx):
        """Returns the list of timers, that will be run in this channel"""
        if isinstance(ctx.channel, discord.TextChannel):
            if not ctx.channel.permissions_for(ctx.author).manage_messages:
                raise commands.MissingPermissions('manage_messages')

        query = '''SELECT * FROM timers WHERE event='this' AND extra #> '{"a",1}'=$1'''
        async with ctx.acquire():
            records = await ctx.con.fetch(query, ctx.channel.id)
        if not records:
            return await ctx.send('This channel has no timers set')

        e = embed.Embed(title='This channel\'s timers', timestamp=ctx.message.created_at)
        e.set_footer(author=ctx.author)

        async def _util(record):
            return record, await self.get_ch_g(record.args[1])
        e.description = '\n'.join(f'[`ID {r.id}, set by`](https://discordapp.com/channels/{g}/{ch.id}/' \
                                  f'{(kw:=r.kwargs)["message_id"]}) {self.bot.get_user(kw["author_id"]).mention}'
                                  for r, (ch, g) in await asyncio.gather(*map(_util, map(TimerConfig.from_record, records)))
                                  if ch and g)
        await ctx.send(embed=e)

    @channel_timers.error
    async def on_channel_timers_error(self, ctx, error):
        error = getattr(error, 'origin', error)

        await ctx.send("".join(traceback.format_exception(type(error), error, error.__traceback__)))

    @timer.command(name='current')
    @commands.is_owner()
    async def current_timer(self, ctx):
        if self._current_timer is None:
            await ctx.send('There is no current timer')
        else:
            await ctx.send(self._current_timer)

    @commands.Cog.listener()
    async def on_this_timer_complete(self, timer):
        # TODO some fancy formatting
        # FIXME embeds are not mentionable :'(
        msg, channel = timer.args
        channel, guild_id = await self.get_ch_g(channel)
        # this shouldn't happen, since I delete all the messages
        # from the deleted channels, but who knows
        if not channel:
            logger.exception('Channel and guild are None, timer wasn\'t deleted '
                             'when the channel was?')
            return

        author = self.bot.get_user(timer.kwargs["author_id"])
        await channel.send(f'{author.mention}, {human_delta(timer.created_at)}: {msg}\n'
                           f'https://discordapp.com/channels/{guild_id}/{channel.id}/{timer.kwargs["message_id"]}')

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        query = '''DELETE FROM timers WHERE extra #> '{"a", 1}' = $1 RETURNING *'''
        print(channel)
        await self._skip_timer(channel.id, delete=True, query=query)

    @commands.Cog.listener()
    async def on_private_channel_delete(self, channel):
        # I couldn't reproduce since don't know how to delete private channels :'(
        query = '''DELETE FROM timers WHERE extra #> '{"a", 1}' = $1 RETURNING *'''
        await self._skip_timer(channel.id, delete=True, query=query)

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

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        error = getattr(error, 'original', error)
        if isinstance(error, discord.InvalidArgument):
            print(error)
        print('on_command_error')
        print(f'{error!r}')

def setup(bot):
    bot.add_cog(Timer(bot))
