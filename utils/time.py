#  PROJECT : bdiscord
#  FILE : time.py
#  LAST MODIFIED : 14-12-2020
#  AUTHOR : Sam (sam@hey.com)
#
#
#  Copyright (c) 2020, Sam (sam@hey.com)

import datetime
import re

from dateparser.search.search import DateSearchWithDetection
from discord.ext import commands


from utils import converters

class TimerConverter(commands.Converter):

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

        # print(date)
        # match = re.search(pat, date)
        # print(match.group())
        # print(match.lastgroup)
        # print(match.groupdict())
        # print(re.findall(pat, date))
        # print(re.fullmatch(pat, date))
        # for r in re.finditer(pat, date):
        #     # print(r.start(), r.end(), r.group(0), r.lastgroup, r.groupdict(), r.group())
        #     if r.group():
        #         # print(dir(r.group()))
        #         r = {v: k for v,k in r.groupdict().items() if k}
        #         print(r)
        #         # print(r.start(), r.end(), r.group(0), r.lastgroup, r.groupdict(), r.group())
        #         print(datetime.datetime.utcnow() + datetime.timedelta(hours=3))
        #         print(search_dates(f'in {"".join(f"{v} {k}" for k, v in r.items())}'))
        #         print(search_dates(f'in {"".join(f"{v} {k}" for k, v in r.items())}')[0][1] - (datetime.datetime.utcnow() + datetime.timedelta(hours=3)))
        #         return search_dates(f'in {"".join(f"{v} {k}" for k, v in r.items())}')[0][1] - (datetime.datetime.utcnow() + datetime.timedelta(hours=3))


        dates = [f'in {r.groupdict()[g]} {g}' for r in pat.finditer(date) if (g:=r.lastgroup)]
        # dates, indexes = [], []
        ddp = DateSearchWithDetection()
        settings = {'TIMEZONE': 'UTC', 'PREFER_DATES_FROM': 'future'}
        print('date', date)
        dates = {}
        # print('s_dates', ddp.search_dates(date, settings=settings, languages=['en'])['Dates'][0][1])
        for r in pat.finditer(date):
            if g := r.lastgroup:
                # indexes.append(r.span())
                # dates.append((g, r.groupdict()[g]))

                dates[r.span()] = (g, r.groupdict()[g])
                # dates.append(ddp.search_dates(f'{r.groupdict()[g]} {g}',
                #                               languages=['en'], settings=settings)['Dates'][0][1])
                # dates.append(ddp.search_dates("".join(f'{v} {k}' for k, v in r.groupdict().items() if v),
                #                               languages=['en'], settings=settings)['Dates'][0][1])
                # dates.append(f'{r.groupdict()[g]} {g}')

        order = {'years': 0, 'months': 1, 'weeks': 2, 'days': 3, 'hours': 4, 'minutes': 5, 'seconds': 6}
        indexes = list(dates.keys())
        strs = []
        deleted_chars = 0
        # first, second
        for f, s in zip([(0, 0)] + indexes, indexes):
            print(f, s)
            # _s - second_start, _e - second_end
            _s, _e = s
            # 4 is dummy number for non-times in-between
            # 4 = ' \w\w ' - THE message
            if _s - f[1] >= 4:
                dates.pop(s)
                continue

            # deleting matched parts of `date`
            date = date[:_s - deleted_chars] + date[_e - deleted_chars:]
            # should be working
            deleted_chars += _e - _s

            # joining found time parts based on the `order`
            # so '5 minutes', '3 seconds' becomes '5 minutes 3 seconds'
            # but '5 minutes', '3 minutes' remains unchanged
            if f == (0, 0):
                curr_str = f'{dates[s][1]} {dates[s][0]} '
                continue
            (n, v), (_n, _v) = dates[f], dates[s]
            if order[n] >= order[_n]:
                strs.append(curr_str)
                curr_str = f'{_v} {_n} '
            else:
                curr_str += f'{_v} {_n} '

        strs.append(curr_str)


        # reduce
        # _dates = list(dates.values())
        # strs = []
        # curr_str = f'{_dates[0][1]} {_dates[0][0]} '
        # for f, s in zip(_dates, _dates[1:]):
        #     if order[f[0]] >= order[s[0]]:
        #         strs.append(curr_str)
        #         curr_str = f'{s[1]} {s[0]} '
        #     else:
        #         curr_str += f'{s[1]} {s[0]} '
        # strs.append(curr_str)

        print(dates)
        print(strs)

        # order = {'years': 0, 'months': 1, 'weeks': 2, 'days': 3, 'hours': 4, 'minutes': 5, 'seconds': 6}
        # # reduce
        # strs = []
        # curr_str = f'{dates[0][1]} {dates[0][0]} '
        # for f, s in zip(dates, dates[1:]):
        #     if order[f[0]] >= order[s[0]]:
        #         strs.append(curr_str)
        #         curr_str = f'{s[1]} {s[0]} '
        #     else:
        #         curr_str += f'{s[1]} {s[0]} '
        # strs.append(curr_str)
        #
        # print(indexes)
        # indexes.reverse()
        # from itertools import zip_longest
        # # s - start first, e - end first, _s - start second, _e - end second
        # for (s, e), (_s, _e) in zip_longest(indexes, indexes[1:], fillvalue=(0, 0)):
        #     # 4 is dummy number for non-times in-between
        #     # 4 = ' \w\w ' - THE message
        #     if s - _e >= 4:
        #         print('g')
        #         continue
        #     date = date[:s] + date[e:]
        print(f'date: {date!r}')
        # print(dates)
        # print(strs)
        # print(*map(lambda _: ddp.search_dates(_, settings=settings, languages=['en'])['Dates'][0][1], strs))
        # return tuple(map(search_dates, dates))



        # for match in re.search(pat, date):
        #     # any short names are better be replaces with their full?
        #     print(match.groupdict())
        #     pass

    def parse_time(self, text):
        for date in search_dates(text, ['en']):
            pass

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

        times, message = parse(argument[:_c])

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