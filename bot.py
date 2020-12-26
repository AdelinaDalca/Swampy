#  PROJECT : bdiscord
#  FILE : bot.py
#  LAST MODIFIED : 04-12-2020
#  AUTHOR : Sam (sam@hey.com)
#
#
#  Copyright (c) 2020, Sam (sam@hey.com)

import aiohttp
import asyncio
import datetime
from dotenv import load_dotenv
from collections import Counter
import logging
import os
import random
import re
import traceback

import discord
from discord.ext import commands
import discord.utils

from utils import context, db, cache
from utils.config import Config
import settings
import uutils as u

logger = u.get_logger(__name__)
logger.parent.setLevel(logging.DEBUG)
# from pprint import pprint
# pprint(logging.Logger.manager.loggerDict)

bot = commands.Bot(command_prefix='\\')

ERROR_CHANNEL = 781917704529510400


# class BlackListTable(db.Table, table_name='blacklist'):
#
#     columns = [
#         'id PRIMARY KEY'
#     ]


class GuildTable(db.Table, table_name='guilds'):

    columns = [
        'id BIGINT PRIMARY KEY',
        'prefixes TEXT[]'  # NOT NULL DEFAULT \'{"<@762409092106289193> ", "<@!762409092106289193> "}\'::TEXT[]'
    ]


# class BlackListConfig:
#
#     @classmethod
#     async def from_record(cls, record):
#         self = cls()
#
#         self.id = record['id']
#         return self
#
#     def __repr__(self):
#         return f'{self.__class__.__name__}: {self.id}'


class GuildConfig(db.ConfigBase):

    __slots__ = ('id', 'prefixes')

    @classmethod
    async def from_record(cls, record):
        self = cls()
        print(record)
        self.id = record['id']
        self.prefixes = record['prefixes']
        return self


initial_extensions = (
    'cogs.basic',
    'cogs.timer',
    'cogs.webscrapping',
    'cogs.admin'
)


# TODO change error handler from email one to the discord/email: when discord is not available at the moment, use email (webhook?)
#  auto blocking spammers -> table?
#  change type of `prefixes` in the table to `jsonb` as it is internally organized for searching?


load_dotenv()


class Swampy(commands.Bot):

    def __init__(self, pool):
        intents = discord.Intents.all()
        intents.bans, intents.integrations, intents.webhooks, intents.voice_states = False, False, False, False
        super().__init__(command_prefix=self.get_prefixes, intents=intents)

        self.session = aiohttp.ClientSession()
        self.pool = pool

        self.spam_bucket = commands.CooldownMapping.from_cooldown(7, 9.0, commands.BucketType.user)
        self._auto_spam_counter = Counter()
        self.blacklist = Config('blacklist.json')

        self.d_prefixes = ['\\']

        for extension in initial_extensions:
            try:
                self.load_extension(extension)
            except Exception as e:
                logger.error('Failed to load cog {0!r}\n{1}'.format('extension',
                                                                    "".join(traceback.format_exception(type(e), e, e.__traceback__))))

    async def get_prefixes(self, bot, msg):
        base = [f'<@{bot.user.id}> ', f'<@!{bot.user.id}> ']
        if msg.guild is not None:
            config = await self.get_prefix_config(msg.guild.id)
            # await msg.channel.send(f'get_prefixes {self.get_prefix_config.get_stats()}')
            if config.prefixes is not None:
                return base + config.prefixes
        return base + self.d_prefixes

    @cache.cache()
    async def get_prefix_config(self, guild_id):
        query = '''SELECT * FROM guilds WHERE id=$1'''
        async with self.pool.acquire() as conn:
            record = await conn.fetchrow(query, guild_id)
            if record is None:
                record = await conn.fetchrow('''INSERT INTO guilds(id) VALUES ($1) RETURNING *''', guild_id)
            return await GuildConfig.from_record(record)

    async def set_prefix_config(self, guild_id, prefix):
        query = '''UPDATE guilds SET prefixes=$2::TEXT[] WHERE id=$1'''
        # query = '''INSERT INTO guilds(id, prefixes) VALUES ($1, $2::TEXT[]) ON CONFLICT (id) DO UPDATE SET prefixes=$2'''
        if len(prefix) >= 10:
            raise commands.TooManyArguments('Server cannot have more than 10 custom prefixes')
        async with self.pool.acquire() as conn:
            status = await conn.execute(query, guild_id, prefix)
            # print(self.get_prefix_config.cache)
            # print(self, guild_id, prefix[:~0])
            self.get_prefix_config.invalidate(self, guild_id)
            # print(self.get_prefix_config.cache)
            return status

    async def on_ready(self):
        if not hasattr(self, 'uptime'):
            self.uptime = datetime.datetime.utcnow()
        logger.info('%s is connected to Discord! (ID: %s)' % (self.user, self.user.id))

    async def on_message(self, msg):
        if msg.author.id == self.user.id:
            return
        await self.process_commands(msg)

    async def on_guild_join(self, guild):
        if guild.id in self.blacklist:
            await guild.leave()

    # def get_guild_prefixes(self, guild):
    #     dummy_msg = discord.Object(id=0)
    #     dummy_msg.guild = guild
    #     return _command_prefix(self, dummy_msg)
    #
    # def get_raw_guild_prefixes(self, guild):
    #     return self.prefixes.get(guild.id, self.d_prefixes)
    #
    # async def set_guild_prefixes(self, guild, prefixes):
    #     if len(prefixes) == 0:
    #         await self.prefixes.put(guild.id, [])
    #     elif len(prefixes) >= 10:
    #         raise commands.TooManyArguments('Server cannot have more than 10 prefixes')
    #     else:
    #         await self.prefixes.put(guild.id, sorted(set(prefixes), reverse=True))

    async def add_to_blacklist(self, id):
        await self.blacklist.put(id, True)

    async def remove_from_blacklist(self, id):
        await self.blacklist.remove(id)

    def webhook(self):
        wh = discord.Webhook.from_url(os.getenv('B_WEBHOOK'), adapter=discord.AsyncWebhookAdapter(self.session))
        return wh

    async def inform_spammer(self, ctx, message, retry_after, *, autoblock=False):
        guild_name = getattr(ctx.guild, 'name', 'DM')
        guild_id = getattr(ctx.guild, 'id', None)
        fmt = 'User %s (ID: %s) in guild %r (ID: %s) is spamming, retry after: %.2fs'
        logger.warning(fmt, message.author, message.author.id, guild_name, guild_id, retry_after)
        if not autoblock:
            return

        wh = self.webhook()
        e = discord.Embed(title='Auto-blocked user', color=discord.Colour.dark_green(), timestamp=datetime.datetime.utcnow())
        e.add_field(name='Member', value=f'{message.author} (ID: {message.author.id})', inline=False)
        e.add_field(name='Guild', value=f'{guild_name} (ID: {guild_id})', inline=False)
        e.add_field(name='Channel', value=f'{message.channel} (ID: {message.channel.id})')
        await wh.send(embed=e)

    async def process_commands(self, message):
        ctx = await self.get_context(message, cls=context.Context)

        if ctx.command is None or \
           ctx.author.id in self.blacklist or \
           ctx.guild is not None and ctx.guild.id in self.blacklist:
            return

        bucket = self.spam_bucket.get_bucket(message)
        curr_time = message.created_at.replace(tzinfo=datetime.timezone.utc).timestamp()
        retry_after = bucket.update_rate_limit(curr_time)

        if retry_after and self.owner_id != message.author.id:
            self._auto_spam_counter[message.author.id] += 1
            if self._auto_spam_counter[message.author.id] >= 5:
                await self.add_to_blacklist(message.author.id)
                del self._auto_spam_counter[message.author.id]
                await self.inform_spammer(ctx, message, retry_after, autoblock=True)
            else:
                await self.inform_spammer(ctx, message, retry_after)
        else:
            self._auto_spam_counter.pop(message.author.id, None)

        try:
            await self.invoke(ctx)
        finally:
            await ctx.release()

    async def close(self):
        await super().close()
        await self.session.close()

    async def on_disconnect(self):
        logger.debug('Aye! I\'ve disconnected now')

    async def on_command_error(self, ctx, exception):
        print('global on_command_error')
        await ctx.send(exception)

    def run(self):
        super().run(os.getenv('DISCORD_TOKEN'), reconnect=True)


@bot.command()
async def ext(ctx):
    for ex in initial_extensions:
        try:
            ctx.bot.load_extension(ex)
        except Exception as e:
            await ctx.bot.get_channel(ERROR_CHANNEL).send(f'Failed loading extension {ex!r}:\n'
                                                          f'```py\n{"".join(traceback.format_exception(type(e), e, e.__traceback__))}\n```\n\n'
                                                          f'{traceback.print_exc()}')

@bot.command()
async def test(ctx, channel: commands.TextChannelConverter):
    logger.debug(channel.id)
    guild = 762408410595065868
    guild = bot.get_guild(guild)

    ch = bot.get_channel(767715065998213130)
    await ch.send('hehe')



@bot.command()
async def mentions(ctx):
    logger.debug(bot.allowed_mentions)
    user = ctx.message.author
    logger.debug(user.mention)
    await ctx.send(f"Biba {user.mention}, <@{user.id}>, "
                   f"admins @admin {';'.join(role.mention for role in ctx.guild.roles)}",
                   allowed_mentions=discord.AllowedMentions.all())


@bot.command()
async def emoji(ctx):
    await ctx.send(bot.emojis)

@bot.event
async def on_command_error(ctx, error):

    if hasattr(ctx.command, 'on_error'):
        logger.debug('%s was handled in its own error handler' % ctx.command)
        return

    msg = ctx.message
    # command, *arg = msg.content.split(maxsplit=1)
    if isinstance(error, commands.errors.CheckFailure):
        logger.error('Unhandled permissions for %s command' % ctx.command)
    elif isinstance(error, commands.errors.CommandNotFound):
        await ctx.send(f'Wrong command `{ctx.invoked_with}` :(\n'
                       f'Try using `{bot.command_prefix}help` for more info on commands')
        logger.info('%s from "%s" tried to invoke `%s` command' %
                    (msg.author, msg.guild if msg.guild else 'DM', msg.content))
    elif isinstance(error, commands.errors.BadArgument):
        logger.debug(error)
        logger.error('%s used `%s` command in %s, which argument was not valid' % (msg.author, msg.content, msg.guild))
    else:
        logger.exception(''.join(traceback.format_exception(type(error), error, error.__traceback__)))


@bot.command()
async def avatar(ctx):
    await ctx.send(ctx.message.author.permissions_in(ctx.message.channel))


@bot.command()
async def ss(ctx):
    channel = ctx.message.channel
    await channel.send('Send me that 👍 reaction, mate')

    def check(reaction, user):
        return user == ctx.message.author and str(reaction.emoji) == '👍'

    try:
        reaction, user = await bot.wait_for('reaction_add', timeout=10.0, check=check)
    except asyncio.TimeoutError:
        await channel.send('👎')
    else:
        await channel.send('👍')

# @bot.event
# async def on_message_delete(message):
#     channel = message.channel
#     await channel.send(content=message.content)
