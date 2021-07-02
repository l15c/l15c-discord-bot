# import discord
#
# client = discord.Client()
#
# @client.event
# async def on_voice_state_update(member,oldState, newState):
#     voiceCollection = []
#     if not oldState.channel_id and newState.channel_id == '860145983287721994':
#         channel = await  newState.member.create_voice_channel(member.display_name)
#         member.voice.setChannel(channel)
#         voiceCollection[0] = member.id
#         voiceCollection[1] = channel.id
#     elif not newState.channel_id:
#         if oldState.channel_id == voiceCollection[1]:
#             return oldState.channel_id.delete()
#
# client.run("ODYwMTY2MTgwNTg5MTQyMDI2.YN3SLg.kSTXIB13zZgk5i0fluE5Kb_ZykY")

import discord
from discord.ext import commands,tasks

bot = commands.Bot(command_prefix='l15c')
bot.load_extension("cogs.voiceChannelCog")


@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="Cây táo nở hoa"))
    print("BOT is online!")



bot.run("ODYwMjYyNDA1MjEyOTk1NTk0.YN4rzA.oYqDuDjOUTxy2Fdfc22m5r6WHIQ")