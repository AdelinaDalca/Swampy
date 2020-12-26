#  PROJECT : bdiscord
#  FILE : basic.py
#  LAST MODIFIED : 04-12-2020
#  AUTHOR : Sam (sam@hey.com)
#
#
#  Copyright (c) 2020, Sam (sam@hey.com)


import asyncio
from pathlib import Path
import traceback
import random
import re

from asyncpg import BitString
import discord
from discord.ext import commands, tasks

from utils import db, cache
import uutils as u

logger = u.get_logger(__name__)


class BasicTable(db.Table, table_name='basic'):

    columns = [
        'guild_id BIGINT',
        # 'spam BIT(3) NOT NULL DEFAULT 7::BIT(3)',
        'cat_name TEXT NOT NULL DEFAULT \'announcements\'',
        'ch_name TEXT NOT NULL DEFAULT \'news\'',
        'pins BOOLEAN NOT NULL DEFAULT true',
        'PRIMARY KEY (guild_id)',
        'FOREIGN KEY (guild_id) REFERENCES guilds(id) ON DELETE CASCADE'
    ]


class ChannelsTable(db.Table, table_name='channels'):

    columns = [
        'guild_id BIGINT',
        'id BIGINT PRIMARY KEY',
        'spam BIT(3) NOT NULL DEFAULT 7::BIT(3)',
        'FOREIGN KEY (guild_id) REFERENCES guilds(id) ON DELETE CASCADE',
    ]


class BasicConfig:

    __slots__ = ('guild_id', 'cat_name', 'ch_name', 'pins')  # , spam)

    @classmethod
    async def from_record(cls, record):
        self = cls()

        self.guild_id = record['guild_id']
        # self.spam = record['spam'].to_int() # BitString
        self.cat_name = record['cat_name']
        self.ch_name = record['ch_name']
        self.pins = record['pins']

        return self

    def __repr__(self):
        return f'<{self.__class__.__name__}>: {"; ".join(f"({_} {repr(getattr(self, _))})" for _ in self.__slots__)}'


class ChannelsConfig:

    __slots__ = ('spam')

    @classmethod
    async def from_record(cls, record):
        self = cls()

        self.spam = record['spam'].to_int() # BitString
        return self

    def __repr__(self):
        return f'<{self.__class__.__name__}>: {"; ".join(f"({_} {repr(getattr(self, _))})" for _ in self.__slots__)}'


# TODO on_member_join\update, on_role_delete, on_guild_role_update?


class BasicCog(commands.Cog, name=Path(__file__).stem):

    def __init__(self, bot):
        self.bot = bot
        self.change_status.start()

    def cog_unload(self):
        self.change_status.cancel()

    @commands.command()
    async def be(self, ctx):
        await ctx.send('me')

    @tasks.loop(seconds=60.0)
    async def change_status(self):
        statuses = [
            discord.Streaming(name='swimming', url='https://www.youtube.com/watch?v=dQw4w9WgXcQ'),
            discord.Streaming(name='dancing', url='https://www.youtube.com/watch?v=rRPQs_kM_nw'),
            discord.Activity(name='over Uranus', type=discord.ActivityType.watching)
        ]
        await self.bot.change_presence(activity=random.choice(statuses))

    @change_status.before_loop
    async def before_change_status(self):
        await self.bot.wait_until_ready()

    @commands.command(name='spam', help='Defines the behaviour of spamming messages')
    @commands.has_permissions(manage_messages=True)
    async def spam(self, ctx, mode: int = None):
        """Manages spam messages on this particular channel

        Without argument returns current settings:
            :strong: - if bold, bot will spam on every encounter of word 'strong'
            :rush: - if bold, bot will spam on every 'rush'-related message
            :farm: - if bold, bot will spam on every 'farm'-related message

        To change the behaviour, pass in a number [0..7] as an argument: each bit of which
        will represent the enable \ disable state of the settings

        If, for instance, `5` was passed in as an argument, the following logic is applied:
            `5` - is 101 in binary -> :strong: and :farm: is enabled, while :rush: is disabled

        To manage, have Manage Messages permission
        """

        config = await self.get_basic_config(ctx.guild.id)
        spam = config.spam

        if mode:
            if 0 > mode or mode > 7:
                await ctx.send('The mode number should be within [0, 7]')
                logger.info('%s, input value: %s', ctx.message.author.name, mode)
                return
            query = '''INSERT INTO basic(guild_id, spam) VALUES($1, $2) ON CONFLICT (guild_id) DO UPDATE SET spam=$2 RETURNING spam'''
            async with ctx.acquire():
                # `spam` in the table is of `BitString` type, hence the need in `from_int` and `to_int` here
                spam = (await ctx.con.fetchval(query, ctx.guild.id, BitString.from_int(mode, 3))).to_int()
            self.get_basic_config.invalidate(self, ctx.guild.id)
        await ctx.send(', '.join(
            f'{(s := "*~"[b == "0"] * 2)}{w}{s}' for b, w in zip(f'{spam:03b}', 'strong rush farm'.split())))

        logger.info('%s changed the spam behaviour', ctx.message.author.name)

    @spam.error
    async def spam_error(self, ctx, error):
        command, *arg = ctx.message.content.split(maxsplit=1)
        if isinstance(error, commands.errors.CheckFailure):
            await ctx.send("Only Gods themselves shall rule the Spam!\n||doesn't mean YOU can't become one||")
        elif isinstance(error, commands.errors.BadArgument):
            await ctx.send(f'Unfortunately, {command} takes one integer argument, not "{" ".join(arg)}"\n'
                           f'For instance, ```python\n{command} 5```', embed=True)
        else:
            logger.exception(''.join(traceback.format_exception(type(error), error, error.__traceback__)))

    @commands.Cog.listener('on_message')
    async def on_message(self, msg):
        if msg.author.id == self.bot.user.id:
            return
        # await msg.channel.send(f'basic message {self.get_basic_config.get_stats()}')

        spammer = [
            (r'\b(farm|free|low)\b', random.choice('🌾 💰 🏧 💸'.split())),
            (r'\b(race|rush)\b', random.choice('🏁 🏃 🏇 🐎 🏎'.split())),
            (r'\b(sg|swamp|gator|strong)\b', '💪')
        ]

        config = await self.get_basic_config(msg.guild.id)
        spam = config.spam
        response = ' '.join(r for i, (t, r) in enumerate(spammer) if spam >> i & 1 and re.search(t, msg.content.lower()))
        if response:
            await msg.channel.send(f'🐊{response}')

    @cache.cache()
    async def get_basic_config(self, guild_id):
        query = '''SELECT * FROM basic WHERE guild_id=$1'''
        async with self.bot.pool.acquire() as conn:
            record = await conn.fetchrow(query, guild_id)
            if record is None:
                record = await conn.fetchrow('''INSERT INTO basic(guild_id) VALUES($1) 
                ON CONFLICT (guild_id) DO NOTHING RETURNING *''', guild_id)
            return await BasicConfig.from_record(record)

    @cache.cache()
    async def get_channels_config(self, channel_id):
        query = '''SELECT * FROM channels WHERE channel_id=$1'''
        async with self.bot.pool.acquire() as conn:
            record = await conn.fetchrow(query, channel_id)
            if record is None:
                record = await conn.fetchrow('''INSERT INTO channels(channel_id) VALUES($1)
                ON CONFLICT (channel_id) DO NOTHING RETURNING *''', channel_id)
            return await ChannelsConfig.from_record(record)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Checks whether the joined member's name is in GSheet's (©Xylo) players
        If not, offers to change the current one, using `{prefix}alias` or contacting leadership
        to be added to the sheet (©Xylo)

        :param member: joined member
        :return: None
        """
        # member.display_name

        pass

    @commands.Cog.listener()
    async def on_member_update(self, member):
        """To verify the changes user's name is still\now in GSheet(©Xylo)

        :param member: member, changes something in their profile
        :return: None
        """
        pass

    @commands.Cog.listener()
    async def on_role_delete(self, role):
        """To warn that deleting particular role might disable some functions
        :param role: role that was deleted
        :return: None
        """
        pass

    @commands.Cog.listener()
    async def on_guild_role_update(self, before, after):
        """To warn that changing particular role might disable some functions
        :param before: role that was before
        :param after: role that became after
        :return: None
        """
        pass

    @commands.command(name='pins')
    @commands.has_permissions(manage_messages=True, manage_channels=True)
    async def change_pins_behaviour(self, ctx, *, change: str = ''):
        """Changes the behaviour of the bot regarding pinned messages

        Without arguments returns current settings:
            :cat: - the name of the category of the channel to send pinned messages to
            :ch: - the name of the channel to send the pinned messages to
            :pins: - whether enable or disable sending pinned messages

        To change any of the parameters, follow the syntax below:
            `cat=<category name> ch=<channel name> pins=<enable\disable pins>`,
            where values between the `<>` included are your values

        Example:
            `cat=my category ch = 'my channel', pins=+` will result in changing the category name to
            `my category`, channel name to `'my channel'` and in enabling pins

        To use, have Manage Messages and Manage Channels permissions
        """

        keys = 'cat ch pins'.split()

        if change in 'restore default defaults'.split():
            query = '''UPDATE basic SET cat_name=DEFAULT, ch_name=DEFAULT, pins=DEFAULT WHERE guild_id=$1
            RETURNING cat_name, ch_name, pins'''
            async with ctx.acquire():
                values = await ctx.con.fetchrow(query, ctx.guild.id)
            self.get_basic_config.invalidate(self, ctx.guild.id)

            payload = dict(zip(keys, values))
            # is this message needed? Decided to replace with `add_reaction`
            # await ctx.send('Pins\' default settings were successfully restored!')
            await ctx.message.add_reaction(ctx.tick(True))
        else:
            config = await self.get_basic_config(ctx.guild.id)
            cat, ch, pins = config.cat_name, config.ch_name, config.pins
            payload = dict(zip(keys, (cat, ch, pins)))

            if change:
                logger.debug(change)
                changed = False

                # 'cat=, ch=, pins='
                for key, val in payload.items():
                    # logger.debug(re.findall(fr'{key} ?= ?(\w+(?![_ ]?\w+=)[_ ]?\w+|[\w+])', change)+[''])
                    # logger.debug(re.findall(fr'{key} *= *([\w _\']+(?!.*?\w+=)|[\w+]+)', change) + [''])
                    # logger.debug(re.findall(fr'{key} *= *([\w _\']+(?!\w+ *=)[\w\']|[\w+])', change) + [''])
                    if o := (re.findall(fr'{key} *= *([\w _\']+(?!\w+ *=)[\w\']|[\w+])', change) + [''])[0].lower():
                        if key == 'pins':
                            o = o in 'true t 1 enable on set yes y +'.split()
                        changed = True
                        payload[key] = o

                query = '''UPDATE basic SET cat_name=$2, ch_name=$3, pins=$4 WHERE guild_id=$1'''
                async with ctx.acquire():
                    status = await ctx.con.execute(query, ctx.guild.id, *payload.values())
                self.get_basic_config.invalidate(self, ctx.guild.id)
                if changed:
                    await ctx.message.add_reaction(ctx.tick(status.endswith('1')))

        await ctx.send(', '.join(f'**{k}**: {repr(v if k != "pins" else "yneos"[1-v::2])}' for k, v in payload.items()))

    # if `bef` and `aft` has embeds, if any pair of cartesian product of embed lists is a match
    _equal_embeds = lambda _, bef, aft: bef and aft and any(a.to_dict() == b.to_dict() for b in bef for a in aft)

    # check of embeds is first since they have no content -> contents of any embeds are always equal empty
    _eq_msgs = lambda _, f, s: _.equal_embeds(f.embeds, s.embeds) or f.content and f.content == s.content

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        guild = before.guild

        config = await self.get_basic_config(guild.id)
        cat_name, ch_name, pins = config.cat_name, config.ch_name, config.pins

        if not (category := discord.utils.get(before.guild.categories, name=cat_name)) and pins:
            category = await guild.create_category(name=cat_name)
            await category.edit(position=0)
        if not (ch := discord.utils.get(guild.channels, name=ch_name,
                                        category=category)) and after.pinned and pins:
            ch = await guild.create_text_channel(name=ch_name, category=category)

            # no need to do all the stuff below, since `ch` is needed to send\look for messages,
            # which can't be done with `ch` equals to `None`
            # pretty obvious, huh?
            if not ch:
                return

        if after.pinned and not before.pinned and pins:
            async for msg in ch.history():
                if self._eq_msgs(msg, before):
                    break
            else:
                if after.content:
                    return await ch.send(after.content)
                for embed in after.embeds:
                    await ch.send(embed=embed)
                    await asyncio.sleep(1)
                return
        elif before.pinned and not after.pinned:
            # delete messages that meet `check` criteria
            # why after, not before?
            # doesn't matter, since all the pinned messages are edited according to their originals
            # => after = before and before = after
            await ch.purge(check=lambda m: self._eq_msgs(m, after))
        elif before.pinned and after.pinned:
            async for msg in ch.history():
                if msg.content == before.content:
                    return await msg.edit(content=after.content)
                elif self._equal_embeds(msg.embeds, before.embeds):
                    # can webhook edit its embeds? I doubt
                    # only webhooks can post up to 10 embeds in one message,
                    # so we're going to edit only one

                    # `_equal_embeds` finds any matches, however since we're dealing with only
                    # one in both `before` and `msg`, we're going to have only one pair to compare
                    return await msg.edit(embed=after.embeds[0])

            # decided to disable
            #
            # # controversial: if `pins` where not allowed when the message was pinned,
            # # but was edited when `pins` became enabled and the message was still pinned,
            # # it will be posted to the currently specified channel
            # else:
            #     await ch.send(after.content)

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        guild = message.guild

        # TODO if the message is pinned, but the `pins` are off, do nothing?
        if message.pinned:
            print(message)
            config = await self.get_basic_config(guild.id)
            cat_name, ch_name = config.cat_name, config.ch_name
            if cat := discord.utils.get(guild.channels, name=cat_name):
                if ch := discord.utils.get(guild.channels, name=ch_name, category_id=cat.id):
                    await ch.purge(check=lambda m: self._eq_msgs(m, message))
                else:
                    # the channel was deleted, oops
                    pass
            else:
                # the category was deleted, what a pity
                pass

    # @commands.Cog.listener()
    # async def on_guild_channel_pins_update(self, channel, last_pin):
    #     guild = channel.guild
    #     if not (ch := discord.utils.get(guild.channels, name='news')):
    #         ch = await guild.create_text_channel(name='news')
    #
    #     try:
    #         last = (await channel.pins())[0]
    #     except IndexError:
    #         return
    #
    #     async for message in ch.history():
    #         if message.content == last.content:
    #             break
    #     else:
    #         await ch.send(last.content)
    #
    # if not (pin := discord.utils.find(lambda m,p=(await channel.pins())[0]: m.content==p.content, ))
    #
    # await ch.send((await channel.pins())[0].content)
    #
    # if pin := discord.utils.get(await channel.pins(), edited_at=last_pin, pinned=True):
    #     await ch.send(pin.content)
    # else:
    #     logger.debug('Pin was either deleted or error')
    #     logger.debug(await channel.pins())
    # for pin in await channel.pins():
    #     await ch.send(pin.content)
    #     logger.debug(pin)


def setup(bot):
    bot.add_cog(BasicCog(bot))
