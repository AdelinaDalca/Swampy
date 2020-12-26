#  PROJECT : bdiscord
#  FILE : time.py
#  LAST MODIFIED : 14-12-2020
#  AUTHOR : Sam (sam@hey.com)
#
#
#  Copyright (c) 2020, Sam (sam@hey.com)

import datetime
from functools import partial
from collections import Counter
import re

from dateparser.search.search import DateSearchWithDetection
from discord.ext import commands


from utils import converters

class TimerConverter(commands.Converter):

    def __init__(self):
        self.ddp = DateSearchWithDetection()
        self.settings = {'TIMEZONE': 'UTC', 'PREFER_DATES_FROM': 'future'}
        self.search_dates = partial(self.ddp.search_dates, settings=self.settings, languages=['en'])

    @staticmethod
    def _merge_intervals(intervals, sort=True):
        cnt = 1
        prev = 0
        to_merge = intervals[0]
        merge = []
        for cumm, (f, s) in enumerate(intervals[1:], start=1):
            if f - to_merge[1] < 4:
                cnt += 1
                to_merge = (to_merge[0], s)
            else:
                merge.append((cnt, to_merge, slice(prev, cumm)))
                cnt = 1
                prev = cumm
                to_merge = (f, s)
        merge.append((cnt, to_merge, slice(prev, len(intervals))))

        # the bigger the cnt, the 'smaller', then the regular rules for intervals
        if sort:
            return sorted(merge, key=lambda _: (-_[0], _[1]))
        return merge

    def search_shorts(self, date):
        # matches with `in|on|at` without including them in the result
        pat = re.compile(r"""(?:in|on|at)?[ ]*?(?:(?:(?P<years>\d+)[ ]*?(?:years?|y))|
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


        # # first, second
        # for f, s in zip([(0, 0)] + indexes[_slice], indexes[_slice]):
        #     print(f, s)
        #     # _s - second_start, _e - second_end
        #     _s, _e = s
        #
        #     # deleting matched parts of `date`
        #     date = date[:_s - deleted_chars] + date[_e - deleted_chars:]
        #     # should be working
        #     deleted_chars += _e - _s
        #
        #     # joining found time parts based on the `order`
        #     # so '5 minutes', '3 seconds' becomes '5 minutes 3 seconds'
        #     # but '5 minutes', '3 minutes' remains unchanged
        #     if f == (0, 0):
        #         curr_str = f'{dates[s][1]} {dates[s][0]} '
        #         continue
        #     (n, v), (_n, _v) = dates[f], dates[s]
        #     if order[n] >= order[_n]:
        #         strs.append(curr_str)
        #         curr_str = f'{_v} {_n} '
        #     else:
        #         curr_str += f'{_v} {_n} '
        # strs.append(curr_str)

        print(strs)
        dates = [self.search_dates(_)['Dates'][0][1] for _ in strs]
        return dates, date.strip(' .,'), (s, f)

    # def parse_time(self, text):
    #     for date in search_dates(text, ['en']):
    #         pass

    async def convert(self, ctx, argument):
        # first step: parsing into `time` `message` `-c channel`
        # -c *('[\w' ]*[\w' ]'|[\w' ]+) *\. *('[\w' ]*[\w' ]'|\w+)
        # -c *([\w' \\\.]+) *\. *([\w' \\\.]+)
        # -c *([\w' .]+) *\. *([\w' .]+)

        # since channel's and guild's names can contain non-alphanumeric characters
        # it seems useless to come up with any regex
        _c = argument.find('-c ')
        if _c != -1:
            # text channels cannot have spaces in their names (for now)
            # hence splitting by the rightmost space
            _ch = argument[:_c].rsplit()
            if len(_ch) > 1:
                _guild, _ch = _ch

                _guild = await converters.GuildConverter().convert(ctx, _guild)
                _ch = await commands.TextChannelConverter().convert(ctx, _ch)
        else:
            _ch = ctx.channel

        #         for user, perm in zip((ctx.author, channel.guild.me),
        #                               ('MissingPermissions', 'BotMissingPermissions')):
        #             if not channel.permissions_for(user).send_messages:
        #                 raise getattr(commands, perm)(['send_messages'], channel, ctx.guild)

        times, message, pos = self.search_shorts(argument[:_c])

        dates = self.search_dates(message)['Dates']
        for text, time in dates:
            times.append(time)
            message = message.replace(text, '')

        return times, message, _ch


def time_parser(times):
    t = []
    pattern = re.compile(r'(?P<hm>\d(?:h)\d{1,2}(?:m))|'
                         r'(?P<h>\d(?:h))|(?P<t>\d{1,2}(?::)\d{1,2})|'
                         r'(?P<s>\d{1,4}(?:s))|(?P<m>\d{1,3})')

    for time in times.split():
        res = re.match(pattern, time)
        if res:
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

def test():
    t = TimerConverter()
    d = datetime.timedelta
    print(datetime.datetime.utcnow())
    print(t.search_shorts('at 2 h 3 mins 5 m tell my boss about conference at 4hours'))
    print(t.search_shorts('5mins 22nd December print me'))
    print(t.search_shorts('5mins, 2secs3hours my damn text'))
    print(t.search_shorts('5mins cu in 5min'))
    print(t.search_shorts('5 mins 4mins daet 8mins 7mins date 9mins 1min'))

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


def time():
    from time import perf_counter
    from dateparser.search.search import DateSearchWithDetection
    ddp = DateSearchWithDetection()
    # ddp.search_dates('5 minutes')
    dates = ['12:20', '5 minutes', '5 minutes', 'today', '2 days']
    for n, d in enumerate(dates):
        s = perf_counter()
        ddp.search_dates(d, languages=['en'])
        print(f'#{n} {d!r}: {perf_counter() - s:.2f}')

if __name__ == '__main__':
    # from time import perf_counter
    # s = perf_counter()
    # time()
    # print(f'{perf_counter() - s:.2f}')
    test()