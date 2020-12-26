import os

import random
from dotenv import load_dotenv

import discord
from discord.ext import commands

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix='\\', intents=intents)

@bot.event
async def on_ready():
    print(f'{bot.user.name} is connected to Discord!')


@bot.command(name='99')
async def nine_nine(ctx):
    brooklyn_99_quotes = [
            "Cool!",
            "Bingpot!",
            "I'm the human form of the 😀 emoji!"
            ]

    response = random.choice(brooklyn_99_quotes)
    await ctx.send(response)


@bot.command(name='list', help='Show the list of the server\' users')
async def list(ctx):
    await ctx.send(f"List of members of this server:\n\t - {f'{chr(10)}{chr(9)} - '.join(_.name for _ in ctx.guild.members)}")


@bot.command(name='roll_dice', help='Simulates rolling dice')
async def dice(ctx, number_of_dice: int, number_of_sides: int):
    dice = [
        str(random.choice(range(1, number_of_sides + 1)))
        for _ in range(number_of_dice)
            ]
    await ctx.send(', '.join(dice))


@bot.command(name='create_channel', help='Creates new channel with specified name')
@commands.has_role('admin')
async def create(ctx, *channel_name: str):
    guild = ctx.guild
    channel_name = ' '.join(channel_name)
    existing_channel = discord.utils.get(guild.channels, name=channel_name)
    if existing_channel:
        await ctx.send('Such a channel already exists')
    else:
        await ctx.send(f'Creating new channel: {channel_name}')
        await guild.create_text_channel(channel_name)


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.errors.CheckFailure):
        await ctx.send('You don\'t have the correct role for this command')

bot.run(TOKEN)
