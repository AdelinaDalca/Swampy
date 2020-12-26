#  PROJECT : bdiscord
#  FILE : time.py
#  LAST MODIFIED : 14-12-2020
#  AUTHOR : Sam (sam@hey.com)
#
#
#  Copyright (c) 2020, Sam (sam@hey.com)

import datetime
from functools import partial
import re

from dateparser.search.search import DateSearchWithDetection
import discord
from discord.ext import commands

from utils import converters


class TimerConverter(commands.Converter):

    def __init__(self, default_message='...'):
        self.ddp = DateSearchWithDetection()
        self.settings = {'TIMEZONE': 'UTC', 'PREFER_DATES_FROM': 'future'}
        self.search_dates = partial(self.ddp.search_dates, settings=self.settings, languages=['en'])
        # TODO `\timer set 20s b1s` -> times: [1s 20s], message: b
        #  DONE `\timer set 20s b1s` -> times: [20s], message: b1s
        # FIXME?
        self._delimiter = 3
        self.default_message = default_message


    def _merge_intervals(self, intervals, sort=True):
        # designed to evaluate the density of datetime-like objects
        # in the parsing string: intervals are merged if the distance between is less
        # than 4 (' \w\w ') (empirically and logically(?)), the number of
        # merged intervals is kept since is the key to the density
        prev, cnt = range(2)
        to_merge = intervals[0]
        merge = []
        for cumm, (f, s) in enumerate(intervals[1:], start=1):
            if f - to_merge[1] < self._delimiter:
                cnt += 1
                to_merge = (to_merge[0], s)
            else:
                merge.append((cnt, to_merge, slice(prev, cumm)))
                cnt, prev = 1, cumm
                to_merge = (f, s)
        merge.append((cnt, to_merge, slice(prev, len(intervals))))

        # the bigger the cnt, the 'smaller', then the regular rules for intervals
        if sort:
            return sorted(merge, key=lambda _: (-_[0], _[1]))
        return merge

    def search_shorts(self, date):
        # matches with `in|on|at` without including them in the result
        #                                 [ ]*?
        #                                  \b
        # now should work in cases like `4w3s` -> 4 weeks 3 seconds, `3m b2s` -> 3 minutes 'b2s'
        pat = re.compile(r"""(?:in|on|at)?(?:(?<=\d[ywdhms])|(?<=\dmo)|(?<=\b))(?:(?:(?P<years>\d+)[ ]*?(?:years?|y))|
                       (?:(?P<months>\d+)[ ]*?(?:months?|mo))|
                       (?:(?P<weeks>\d+)[ ]*?(?:weeks?|w))|
                       (?:(?P<days>\d+)[ ]*?(?:days?|d))|
                       (?:(?P<hours>\d+)[ ]*?(?:hours?|h))|
                       (?:(?P<minutes>\d+)[ ]*?(?:minutes?|mins?|m))|
                       (?:(?P<seconds>\d+)[ ]*?(?:seconds?|secs?|s)))
                       """, re.VERBOSE)

        print('date', date)
        dates = {r.span(): (g, r.groupdict()[g]) for r in pat.finditer(date) if (g:=r.lastgroup)}
        order = {'': -1, 'years': 0, 'months': 1, 'weeks': 2, 'days': 3, 'hours': 4, 'minutes': 5, 'seconds': 6}

        indexes = list(dates.keys())
        if not indexes:
            return [], date, (0, 0)
        _, (s, f), _slice = self._merge_intervals(indexes)[0]
        date = date[:s] + date[f:]
        vals = list(dates.values())[_slice]
        strs = ['']

        # ('', '') will have order -1, which is less than any possible one
        # will add the second argument to the '' -> 'the second argument'
        # `strs[~0]` = curr_str
        for (n, v), (_n, _v) in zip([('', '')] + vals, vals):
            if order[n] < order[_n]:
                strs[~0] += f'{_v} {_n} '
            else:
                strs.append(f'{_v} {_n} ')

        # print(strs)
        dates = [self.search_dates(_)['Dates'][0][1] for _ in strs]
        return dates, date.strip(' .,'), (s, f)

    async def convert(self, ctx, argument):
        # since channel's and guild's names can contain non-alphanumeric characters
        # it seems useless to come up with any regex
        _c = argument.find('-c ')
        if _c != -1:
            # text channels cannot have spaces in their names (for now)
            # hence splitting by the rightmost space
            _ch = argument[_c + 3:].rsplit(maxsplit=1)
            # striping the channel name and '-c '
            argument = argument[:_c]
            if len(_ch) > 1:
                _guild, _ch = _ch

                # is preserving ctx.guild necessary? If any exception in `GuildConverter` were raised
                # `ctx.guild = ` is not executed(?). If `_ch` is not found, an exception is also raised,
                # which doesn't change `ctx.channel`
                # __guild = ctx.guild
                ctx.guild = await converters.GuildConverter().convert(ctx, _guild)
            else:
                _ch = _ch[0]
            # `TextChannelConverter` searches by name in the ctx.guild, so if it weren't altered above,
            # we can proceed, if it were, the search would be done in the destination guild
            _ch = await commands.TextChannelConverter().convert(ctx, _ch)
        else:
            _ch = ctx.channel

        if not isinstance(_ch, discord.DMChannel):
            for user, perm in zip((ctx.author, _ch.guild.me),
                                  ('MissingPermissions', 'BotMissingPermissions')):
                if not _ch.permissions_for(user).send_messages:
                    raise getattr(commands, perm)(['send_messages'], _ch, ctx.guild)

        pat = re.compile(r"'([\w:,./-\\ ]+)'")
        if (res := pat.search(argument)):
            s, f = res.span()
            times, unparsed_times, _ = self.search_shorts(res.group())
            dates = self.search_dates(unparsed_times)['Dates']
            message = argument[:s] + argument[f:]
        else:
            # hopefully this works (tests were made, but in a lazy manner)
            times, message, (f, s) = self.search_shorts(argument)
            dates = self.search_dates(message)['Dates']

        for text, time in dates:
            if (pos := argument.find(text)) != -1:
                # [](f, s)[]
                #         ^ pos
                if pos - s < self._delimiter:
                    s = pos + len(text)
                # [](f, s)[]
                # ^ pos
                elif pos + len(text) - f < self._delimiter:
                    f = pos
                times.append(time)
                message = message.replace(text, '', 1)

        if not (message:=message.strip(',. ')):
            message = self.default_message
        return sorted(times), message, _ch


def test():
    t = TimerConverter()
    d = datetime.timedelta
    print(datetime.datetime.utcnow())
    # print(t.search_shorts('at 2 h 3 mins 5 m tell my boss about conference at 4hours'))
    # print(t.search_shorts('5mins 22nd December print me'))
    # print(t.search_shorts('5mins, 2secs3hours my damn text'))
    # print(t.search_shorts('5mins cu in 5min'))
    # print(t.search_shorts('5 mins 4mins daet 8mins 7mins date 9mins 1min'))

    print(t.convert(None, 'at 2 h 3 mins 5 m tell my boss about conference at 4hours'))
    print(t.convert(None, '5mins 22nd December 4pm print me'))
    print(t.convert(None, '5mins, 2secs3hours my damn text on 22nd December 4pm'))
    print(t.convert(None, '5mins 08/08/08 cu in 5min 08/08/08'))
    print(t.convert(None, '5 mins 4mins daet 8mins 7mins date 9mins 1min'))

    # print(search_dates('monday next week'))
    # print(d(minutes=5))
    # assert t.search_shorts('in 5 mins') == d(minutes=5)
    # assert t.search_shorts('5 mins') == d(minutes=5)
    # assert t.search_shorts('in 5    secs') == d(seconds=5)
    # assert t.search_shorts('5s') == d(seconds=5)
    # assert t.search_shorts('in 5secs') == d(seconds=5)
    # assert t.search_shorts('in 5 y') == d(days=1826)  # at least for today
    # assert t.search_shorts('in 5years') == d(days=1826)
    # assert t.search_shorts('in 5w') == d(weeks=5)
    # assert t.search_shorts('in 15mo') == d(days=455)
    print('passed')


if __name__ == '__main__':
    test()