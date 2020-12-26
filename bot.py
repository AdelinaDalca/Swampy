import os

from dotenv import load_dotenv
import discord
import random


load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.members = True

client = discord.Client(intents=intents)

@client.event
async def on_ready():
    guild = discord.utils.get(client.guilds, id=int(os.getenv("DISCORD_GUILD_ID")))
    print(f"{client.user} has connected to Discord!")
    print(f"{guild} - is one guild of many with id: {guild.id}")
    members = '\n - '.join([member.name for member in guild.members])
    print(f'Guild Members:\n - {members}')


@client.event
async def on_member_join(member):
    await member.create_dm()
    await member.dm_channel.send(f'Hi, {member.name}, welcome to my brand new server!')



@client.event
async def on_message(message):
    if message.author == client.user:
        return

    brooklyn_99_quotes = [
        "I'm the human form of the 😀 emoji",
        "Bingpot!",
        "Cool."
            ]

    if message.content == '99!':
        response = random.choice(brooklyn_99_quotes)
        await message.channel.send(response)
    else:
        raise discord.DiscordException


@client.event
async def on_error(event, *args, **kwargs):
    with open('err.log', 'a') as f:
        if event == 'on_message':
            f.write(f'Unhandled message {args[0]}\n')
        else:
            raise


client.run(TOKEN)

